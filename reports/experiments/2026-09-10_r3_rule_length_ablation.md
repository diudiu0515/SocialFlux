# R3 rule-profile × horizon diagnostic — 2026-09-10

## Status and scope

- Branch: `r3-diagnostic-rule-length-ablation`.
- v53 is the frozen pre-diagnostic baseline. v54 changes were prepared but no v54 rollout was generated; they are superseded by this diagnostic.
- The formal research contract remains fixed at 20 turns. `natural_max_20` is a diagnostic condition only.
- All complete and partial trajectories, all rejected candidates, and physical request counts are retained under `build/r3_rule_length_ablation_v1/`.
- Review in this report is **model semantic review by Codex**, not human acceptance. Human review has not started.

## Architecture invariant

Every environment step retains the required architecture:

1. one structured-appraisal LLM stage;
2. deterministic calibration and numeric state/dynamics update, with no model call in between;
3. one state-conditioned response-generation LLM stage.

Candidate validation retries can make more than two physical environment requests in a turn. The evaluated-agent policy is a separate third logical stage. Both stage count and physical request count are reported.

## Design

The same Qwen3-32B-AWQ local model and source sampling configuration were used for IA003 (friendship loan), IA019 (equity/governance), and IA010 (new development scenario: safety versus launch pressure). One trajectory was generated per cell:

| Rule profile | Fixed 20 turns | Maximum 20, natural closure allowed |
|---|---|---|
| Current full rules | Baseline | Length diagnostic |
| Hard errors only | Rule diagnostic | Joint rule/length diagnostic |

The hard-only profile blocks malformed dialogue, private simulator language, clear role/action-ownership reversal, pending promise reported as completion, and unsupported reversal of an owned pending commitment. Repetition, topic duration, focus switching, and lexical fiction heuristics remain diagnostic signals rather than online rejection rules. Its prompt ledger contains only established facts, active proposals, commitments, and the current answer obligation.

## Results

| Scenario | Full + fixed20 | Full + natural≤20 | Hard-only + fixed20 | Hard-only + natural≤20 |
|---|---:|---:|---:|---:|
| IA003 loan | failed before t1 | failed after 10 | failed after 4 | generated 20; semantic reject |
| IA019 equity | failed after 1 | failed after 13 | generated 20; semantic reject | generated 20; semantic reject |
| IA010 safety | failed after 3 | generated 20; semantic reject | generated 20; semantic reject | failed before t1 due quote-format false positive |

Generation completed in 5/12 cells. Model semantic review accepted 0/12 as a high-quality trajectory. No natural-horizon cell triggered a reliable natural terminal state in the original matrix.

Physical cost across the 12 cells:

| Stage | Requests |
|---|---:|
| Evaluated-agent policy | 229 |
| Structured appraisal | 144 |
| Environment response | 228 |
| Environment total | 372 |
| All stages | 601 |

There were 131 completed turns and 138 attempted turns. The no-retry nominal cost for 138 attempted turns is 276 environment requests and 414 all-stage requests; observed retry overhead was therefore 96 environment requests and 187 total requests. “Two environment LLM stages” must not be reported as “exactly two API requests per turn.”

By rule profile, full rules generated 1/6 cells with 310 requests for 47 completed turns; hard-only generated 4/6 with 291 requests for 84 completed turns. This shows that current validators materially constrain generation, but the hard-only outputs show that removing those blockers does not itself produce quality.

## Causal attribution from saved trajectories

### Validator/measurement false positives

- IA003 full+fixed: all 12 first-turn environment candidates directly answered the requested first repayment amount (for example, a tentative 3,000 or 5,000), but `evades_latest_obligation` rejected all of them as changing domain.
- IA010 full+fixed: a reasonable request to clarify the available scheduling window was repeatedly rejected as merely renewing the agent's earlier promise to list risks.
- IA019 full+natural: candidates that accepted the proposed valuation start and addressed the explicitly invited future-participation issue were rejected as “added another condition or process.”
- IA010 hard-only+natural: all 12 policy candidates were direct utterances wrapped in Chinese quotation marks. Treating harmless whole-utterance quote wrapping as a hard failure caused zero completed turns.
- The original natural-stop detector rejected IA003's bilateral t8 closure because the environment said “我会记住这个安排”; generic `我会` was incorrectly treated as opening a future process.

### Agent policy failures

- IA003 hard-only trajectories reversed the lender role into the borrower: “那我下周按时还你2000块” and “那我一个月后准时转账.” The existing policy role validator missed these phrasings. The following environment ownership rejection was correct, but downstream of the policy error.
- IA003 hard-only+natural repeated essentially the same “wait until next week / 2,000 / notify me” exchange from t6 through t20.
- IA010 trajectories asserted newly completed work without elapsed time, such as dependencies being confirmed or documents already prepared/shared.

### Environment response failures

- IA003 hard-only+fixed reversed borrower/lender ownership at t2 by saying it hoped to *receive* the 3,000 repayment.
- IA010 full+natural refused the agent's explicit t19 closure by reopening an implementation requirement, then both speakers started a new review process at t20.
- IA019 responses repeatedly invented authorization flows, legal-team records, completed document delivery, and external review procedures.

### Ledger and validator false negatives

- Commitment records correctly preserved many promises as pending, but role checks did not cover common first-person transfer wording and therefore allowed the policy to poison the next turn's ownership context.
- Completion checks missed several policy-side claims such as “依赖项已确认” and “文档已共享.”
- The old machine audit marked the 10-turn IA003 and 13-turn IA019 partial trajectories as passing even though generation had failed. A structural audit result is therefore not an acceptance decision.

### Scenario capacity and termination

- IA003 reached a workable repayment arrangement in roughly 4–8 turns. Without a successful terminal move, hard-only generation collapsed into exact repetition through t20.
- IA019 had more facets, but hard-only generation replaced genuine progress with invented legal/consulting workflows and then exact document loops.
- IA010 supported more substantive turns than IA003, yet by the middle/late section it also became a future-document/testing loop.
- Allowing natural closure did not reliably cause the model to stop. Length is a real contributor, but not the sole cause; explicit terminal-state understanding and consequential-fact grounding are also limiting factors.

## Evidence-backed fixes after the matrix

1. Whole-utterance Chinese/ASCII quote wrapping is deterministically stripped in hard-only mode before format validation. IA010's matched 3-turn smoke then generated successfully with 9 nominal requests instead of exhausting 12 policy retries before t1.
2. Lender role validation now covers unprefixed “我……还你/转账给你/准时转账” phrasing.
3. Natural closure no longer treats every `我会` as a reopened future process; it requires an actual future action such as contacting, sending, arranging work, discussing, executing, transferring, or repaying. The original IA003 t8 bilateral closure now passes deterministic replay.
4. A fresh IA003 full+natural rerun still failed after 7 turns because the agent repeatedly tried to close while the environment reopened the repayment plan. That is a generation/interaction problem, not another stop-detector false negative.

Focused regression after all diagnostic and appraisal-probe changes: 126/126 passed. Full suite: 304/308 passed; all four errors are pre-existing stale `configs/scenarios/manifest.json` / coverage artifacts, which this diagnostic deliberately did not overwrite.

## Decision

The dominant constraints are ordered as follows:

1. validator false positives and overlapping hard rules inflate retries and can block valid local answers;
2. the evaluated policy and environment lack a robust shared terminal decision and often keep future work alive;
3. hard-only prompting is insufficient to prevent consequential invented facts;
4. narrow immediate scenarios, especially IA003, do not naturally carry 20 substantive rounds;
5. the model contributes role confusion and repetitive fallback behavior, but the current experiment does not justify attributing all failures to model capacity.

Do not resume regex accumulation. The next R3 implementation should add evidence-cited semantic judgments to the existing structured appraisal output for (a) whether a turn adds a new explanation/position/tradeoff/evidence, (b) whether a claimed new fact changes responsibility, rights, feasibility, or task answer, and (c) whether the latest exchange creates a genuine reason to continue. Code should validate evidence and record these judgments; numeric state updates remain deterministic and response generation remains a separate second environment LLM call. This changes the measurement representation, not the quality standard. Formal temporal progression or multi-episode interaction remains deferred pending research-setting approval.

## Experimental semantic-appraisal v4 probe

A backward-compatible experimental appraisal v4 was added without changing the default formal environment. It appends three evidence-cited diagnostics to the existing structured appraisal: substantive novelty, high-impact new claims, and continuation status. Every evidence span is validated as an exact substring of the latest evaluated action and is recorded in the private ledger. The deterministic calibrator ignores these diagnostic fields, and response generation remains the separate second environment LLM stage.

The first IA019 probe produced one valid turn and then exhausted three appraisal schema retries. After preserving all structured retry candidates, a second three-turn probe completed, but used six appraisal requests for three logical appraisal stages. Its first-turn diagnosis correctly marked the asserted broken oral agreement as unsupported and a conditional legal-process statement as hypothetical. Its second-turn diagnosis recognized “I have recordings and emails” as new evidence but failed to list that newly invented evidence asset as a consequential claim, and mislabeled the claimed signature agreement as hypothetical. The v4 prompt now explicitly distinguishes evidence-possession claims, factual premises, and proposals.

Conclusion: evidence-cited semantic measurement is feasible and more aligned with the target construct than lexical rules, but this first schema is not yet stable or accurate enough to become a hard gate. It remains an instrumented probe; the formal default stays appraisal v3.
