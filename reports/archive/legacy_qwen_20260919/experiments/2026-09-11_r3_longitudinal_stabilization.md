# R3 longitudinal stabilization and controlled diagnostic — 2026-09-11

## Status

R3 remains in development stabilization. IA003 v55–v69 contains fifteen preserved attempts: one contemporaneous machine-precheck pass (v62), zero model-semantic-review passes, and zero human reviews. Machine precheck is not reported as quality acceptance. After the v70-era rule/horizon diagnosis, the current line is the semantic-ledger series (`r3_semantic_ledger_v10+`).

All artifacts remain under their versioned `build/r3_longitudinal_v*_probe/` directories. Rejected and partial trajectories were not removed or hidden.

## Architecture invariant

Every environment turn keeps the required ordering and separation:

1. structured appraisal LLM call;
2. deterministic state/dynamics calibration, ledger update, and numeric update;
3. independent state-conditioned response LLM call.

The evaluated-agent policy is separate from the two environment stages. Validation retries can create more physical requests; actual policy/appraisal/response counts are recorded in each trajectory.

## Longitudinal measurement design implemented

- One trajectory is the same people and relationship across variable-length interaction fragments with shared history, state, commitments, and public timeline.
- Formal trajectories allow at most 20 total turns and may end naturally before the cap; no individual fragment or whole trajectory is stretched to a fixed length. The observed length distribution is retained for later analysis.
- Every recontact has an authored elapsed time and reason.
- Elapsed time alone has zero state effect and never proves performance.
- Fulfilled, partially fulfilled, and unfulfilled outcomes come from a frozen scenario-authored event pool and are linked to a qualifying pending commitment.
- A repayment commitment must include an observable amount and deadline before an outcome node can adjudicate it.
- Partial/unfulfilled performance closes the old promise as an observed failed/partial outcome instead of leaving it pending as though untouched.
- T1/T2-visible history includes realized time and event records. T3 keeps the exogenous outcome plan frozen across counterfactual candidates; action-mediated consequences may differ.
- IA003 performance amounts and remaining balance are calculated deterministically from the public commitment and authored outcome fraction, then emitted in the public event. The v65 implementation missed amounts held only in commitment context; v66 fixed that path and produced a public 500/500/0/2500 numeric record.

## IA003 iteration evidence

| Version | Completed turns | Physical requests | Machine result | Full-trajectory/model-semantic finding | Primary attribution |
|---|---:|---:|---|---|---|
| v55 | 20 | not instrumented | reject | t7–t20 exact repetition; event timing contradicted the promise | scenario timing + both speakers + ledger |
| v56 | 0 | 8 | generation error | future promise rejected as off-screen completion | validator false positive |
| v57 | 9 | 31 | generation error | repeated negotiation; static opening implied an event whose precondition failed; appraisal schema failure | scenario opening + both speakers + appraisal |
| v58 | 3 | 14 | generation error | minimum-fragment length forced repetition; appraisal mislabeled/failed exact evidence | fragment design + appraisal |
| v59 | 2 | 11 | generation error | repayment promise classified as communication because the sentence mentioned communication; appraisal taxonomy mismatch | ledger focus + appraisal |
| v60 | 20 | 71 | reject | opening reversed lender/borrower roles; stale pending commitments; arithmetic error; t15–t20 exact mutual copying | scenario role + ledger + both speakers |
| v61 | 9 | 32 | generation error | role fixed; optional consequential-claim evidence span aborted otherwise valid appraisal; conditional notice misread as repayment | appraisal robustness + commitment semantics |
| v62 | 20 | 61 | machine precheck pass | semantic reject: invented remaining 2200 after amount-unknown partial performance; t10–t13 loop; later role reversal and repayment reopening | response facts + both speakers + precheck false negative |
| v63 | 7 | 32 | generation error | response invented paid 400/remaining 2000 and reversed repayment ownership; policy correctly refused the unsupported balance | response + role validator gap |
| v64 | 10 | 43 | generation error | response stopped inventing unknown amounts and moved to responsibility/boundary; appraisal paraphrased a valid `must_answer` evidence span | appraisal evidence representation |
| v65 | 4 | 17 | generation error | valid acceptance candidates were rejected because “通知我确认” was misread as first-person action ownership; numeric event remained static because the amount appeared only in commitment context | validator false positive + numeric materialization |
| v66 | 11 | 41 | generation error | first public event correctly emitted due 500, paid 500, unpaid 0, balance 2500; a compound 800-yuan repayment-plus-notice utterance was stored only as a communication promise, causing false precondition failures and repeated renegotiation; final ownership rejection was also a false positive | compound commitment ledger + downstream policy/response loop + validator false positive |
| v67 | 20 | 67 | machine reject under v67 audit | all three nodes materialized coherently (500 paid in full; 600 with 300 paid; 300 unfulfilled); t11–t20 looped on future performance proving trust. The audit omitted public transition events and falsely called the grounded 300 ungrounded; embedded “观察是否” clauses created fake reply obligations; six fragments lacked capacity after earlier natural pauses | audit history + reply-obligation ledger + fragment transition/capacity + both speakers |
| v68 | 4 | 17 | generation error | the first clear “14天内先还800元” capacity statement was stored only as a notice promise, so semantic pause exposed a false precondition failure. Later role-correct candidates (“我记下来/等你提供记录”) were rejected because “我们…是否能…还款” and future waiting were parsed as the lender taking over repayment | repayment commitment grammar + role/pending validator false positives |
| v69 | 8 | 28 | generation error | all three numeric outcomes were coherent (1000 full; 1500 with 750 paid; 750 unfulfilled). In the no-new-amount third checkpoint, the response opened another “21天后补750元” promise; the next appraisal correctly labeled a new boundary/can-close but copied a prior near-synonym as novelty evidence and exhausted schema retries | response fragment-scope violation + appraisal evidence anchoring |

Contemporaneous machine-precheck rate for v55–v69 is 1/15. Verified high-quality rate is 0/15. Re-auditing v67 with the v68 public-event history fix clears every hard check but leaves five dialogue diagnostics failed, so the sample remains a semantic reject. The v62 machine pass is also retained as a false-negative example, not promoted.

## Controlled IA003 rule × horizon diagnostic

All four cells used the same Qwen3-32B-AWQ model, sampling family, action v7, appraisal v4, response v9, and the same appraisal → deterministic update → response architecture. Only validation profile and horizon mode differed. The diagnostic supported the later confirmed formal setting of natural termination at or before 20 turns.

| Condition | Completed turns | Physical requests | Retry overhead above 3× attempted turns | Terminal result |
|---|---:|---:|---:|---|
| full rules + fixed20 | 5 | 40 | 22 | appraisal optional claim-domain schema failure |
| full rules + natural≤20 | 11 | 88 | 52 | response exhausted 12 mutually conflicting validation attempts |
| hard-only + fixed20 | 5 | 21 | 3 | policy exhausted four ownership-reversal candidates |
| hard-only + natural≤20 | 17 | 57 | 3 | appraisal evidence-ID schema failure; dialogue already in exact loop |

Evidence: `build/r3_rule_length_ablation_v62_ia003/summary.json` and all four complete partial trajectories in its `trajectories/` directory.

## Causal conclusion

The bottleneck is not one variable:

- Full lexical/turn-count rules strongly inflate retries and can make valid local continuation unreachable.
- Relaxing those rules removes much of the retry overhead but does not make the dialogue high quality; exact and semantic loops remain.
- Natural maximum-20 lets some trajectories continue farther, but the model rarely emits the explicit closure phrases used by the original detector. Length contributes but is not sufficient.
- IA003 previously lacked enough grounded event detail and overemphasized “public records,” which induced record/amount churn.
- Appraisal v4's semantic labels are useful, but optional claim annotations and evidence-ID formatting were too brittle. v63 intersects IDs with retrieved evidence; v64/v65 anchor a paraphrased continuation span to the full current action without changing its semantic status.
- Hard precheck alone has false negatives. A separate whole-trajectory semantic judge/model review remains required before human audit.

## Measurement decisions

- Exact/near repetition, topic duration, and focus switching remain diagnostic signals, not universal hard gates.
- After model-semantic review confirms an exact same-speaker loop inside one unchanged fragment and no new challenge exists, generation may retry within the same policy/response stage. Cross-event necessary confirmation remains allowed.
- Clear role inversion, unsupported consequential facts, promise-as-completion, contradictory arithmetic, and hidden information leakage are hard failures.
- Natural trajectory termination has a diagnostic semantic path: final authored fragment + appraisal `can_close` + no pending answer obligation. It does not skip a scheduled future fragment.
- From v68, a non-final fragment may advance after its authored minimum length when appraisal says `can_close` and the response leaves no reply obligation. This is a deterministic use of the existing appraisal output, not another LLM stage.
- Codex reading a trajectory is recorded as model semantic review, never human acceptance.

## Verification through v70 implementation

- v64 full backend: 328/328 passed; web: 8/8 passed; scenario docs/manifests consistent.
- v65 focused tests: 145/145 passed; full backend: 328/328 passed; web: 8/8 passed; scenario docs/manifests consistent.
- v66 full backend: 329/329 passed; web: 8/8 passed; scenario docs/manifests consistent.
- v67 compound-commitment focused regression: 48/48 passed; full backend: 331/331 passed; web: 8/8 passed.
- v68 targeted ledger/transition/validator/audit regression: 166/166 passed; full backend: 336/336 passed; web: 8/8 passed; all 20 scenarios validate; IA003 docs/manifests/coverage are current.
- v69 targeted regression: 167/167 passed; full backend: 337/337 passed; web: 8/8 passed; IA003 docs/manifests/coverage are current.
- v70 targeted regression: 181/181 passed; full backend: 338/338 passed; web: 8/8 passed; all 20 scenarios validate; IA003 docs/manifests/coverage are current.
- Prompt manifest contains versioned action v9, appraisal v4, and response v11; v67–v70 change deterministic ledger, transition, validator, and audit logic without changing the two-call prompt architecture.

## Next acceptance sequence

1. Run and review IA003 v70; do not accept a machine pass without full-trajectory semantic review.
2. Once IA003 is stable across representative candidates, freeze the mechanism and migrate IA019 as the second development scenario.
3. Freeze all tuning before defining/running the untouched holdout scenario. A systemic holdout failure returns work to development and requires a new holdout for final acceptance.
4. Re-run E4/E6 only after R3 is stable, then run R4 state-distribution analysis.
5. Human gates and audits remain pending and must be shown in the website; no model review may sign those fields.

## v25–v29 final acceptance/termination checkpoint

The final line for this checkpoint uses appraisal v9, deterministic state/dynamics/ledger update, response v21, and natural termination at or before 20 turns. Acceptance-only restatements are normalized against active proposals; a genuinely separate owned future action is retained. Fixed-20 lexical closure rules no longer apply to offline natural-max-20 rollouts.

| Evidence | Result | Physical requests | Residual issue |
|---|---:|---:|---|
| v25 IA003 full attempt | 0/1; 19 turns | policy 24, appraisal 28, response 34 = 86 | t11–t17 acceptance/contact restatement; old t20 lexical closure false positive |
| v26 13-case appraisal/ledger probe | 11/13 | 17 | pure acceptance and acceptance restatement became proposals |
| v27 13-case appraisal/ledger probe | 11/13 | 17 | active-proposal acceptance normalization was not wired into appraisal call site |
| v29 13-case appraisal/ledger probe | 13/13 | 14 | none in this isolated extraction set |
| v29 real two-stage environment probe | failed before commit | appraisal 4, response 1 | structured appraisal schema exhausted retries |

The v29 joint probe attempts consistently understood the action as acceptance plus a request to communicate if repayment changes. Attempt 1 emitted unsupported `conditional_offer`; attempts 2–3 emitted the correct `request/open` ledger event but used schema-external `social_act=acceptance`. The established failed check is therefore `structured_appraisal_schema`, not dialogue naturalness or ledger ownership.

### Declared stop-condition outcome

- v29 IA003 was not run because the real two-stage short probe failed.
- A second IA003 seed and a different development scenario were not run because they were conditional on a passing first full trajectory.
- No sample was hidden, no quality threshold was relaxed, and no event was invented to fill turns.
- R3 remains pending; E4/E6 recheck and R4 remain blocked behind a passing development trajectory.

### Human-visible diagnostic evidence

`data/formal/environment/r3_current_diagnostic_review.json` indexes the v29 short probes and the v25 IA003 rejected trajectory. The local annotation website exposes the exact blocker in “人工总清单” and the full 19-turn trajectory with per-turn appraisal/response events, ownership, obligations, proposals, commitments, public events, and ending classification under IA003 → “Rollout 轨迹”. This is pending human diagnostic review and cannot promote the rejected sample into the formal pool.


## newrequest natural-max-20 v6 batch

The final v6 batch combines the revised `DESIGN_CONTRACT.md` measurement policy with the explicit generation rule that bounded plausible invention is allowed, while unsupported facts that alter responsibility, rights, performance, feasibility, or a task answer remain prohibited. Repetition is judged by whether a turn adds a material explanation, position, trade-off, criterion, or evidence; lexical overlap and topic duration are diagnostics rather than automatic rejection rules. The prompts explicitly prohibit serial confirmation chains and other no-information wheel-spinning.

The architecture remains policy call → structured appraisal call → deterministic calibration/state/dynamics/ledger update → separate response call. Qwen3-32B was used for policy, appraisal, and response, but appraisal and response were separate requests. Candidate retries are included in the physical request count.

| Metric | v6 result |
|---|---:|
| Scenarios × requested candidates | 20 × 3 |
| Materialized attempt artifacts | 60/60 |
| Active Gate-3 candidates | 0/60 |
| Complete natural-short trajectories | 49 |
| Generation-error partial trajectories | 11 |
| Physical LLM requests | 598 |
| Requests per attempt | min 3, mean 9.97, max 46 |

Complete short lengths were: 1 turn ×16, 2 ×12, 3 ×10, 4 ×5, 5 ×1, 6 ×1, 7 ×2, 8 ×1, and 9 ×1. The 11 partial attempts stopped at 0 ×3, 1 ×4, 2 ×1, 3 ×1, 7 ×1, and 13 ×1 turns. Residual failures were three appraisal-schema exhaustions, three tentative-to-agreement policy upgrades, three response-schema exhaustions, one role contradiction, and one environment-owned pending commitment.

This is complete generation coverage, not completion of the high-quality rollout pool. The dominant outcome is now honest natural termination rather than padded repetition: most current scenario configurations do not independently sustain 10–20 meaningful turns. Those short attempts and every failure are visible in the website for human review, but none is promoted into Gate 3. Codex inspection remains model semantic review, not human acceptance.

Verification on the final implementation: backend 416/416 passed; website 9/9 passed; scoped `git diff --check` passed. The next scale decision should be based on human review of these visible attempts. Refill should target scenarios that receive grounded longitudinal event capacity, not blindly rerun all 60 slots or reintroduce lexical bans.


## v7–v9 role-driven dialogue and semantic-ledger probes

v7 replaced the adversarial confirmation-chain action style with role-driven dialogue. It permits one bounded, attributable, locally plausible elaboration while prohibiting invention that rewrites responsibility, rights, performance, feasibility, or task answers. It also tells both speakers to stop after two no-information repetitions. Appraisal and response remain separate LLM calls with the deterministic numeric update between them.

| Version / scenario | Outcome | Physical requests | Model semantic review |
|---|---:|---:|---|
| v7 IA001 | generation error after 1 turn | 7 | appraisal used plausible alias `new_proposal`; schema false reject |
| v7 IA009 | natural short, 2 turns | 8 | coherent pause, but no long-history capacity |
| v7 IA019 | natural short, 4 turns | 15 | reject: t3–t4 environment near-repeats the same future-review deferral |
| v8 IA003 | machine-precheck candidate, 14 turns | 52 | reject: tentative 800 proposal is called a commitment; t8–t11 contain semantic mirroring; nine authored fragments extend the relationship to 938 days and dominate the apparent length |
| v9 IA009 | generation error after 3 turns | 19 | request ownership is retained correctly, but the dialogue cycles on making and checking a contribution list |
| v9 IA016 | natural short, 5 turns | 15 | first two turns contain a real expertise/standardization trade-off; later turns contract into repeated record-workflow coordination |

v8 normalizes the observed schema-only novelty alias `new_proposal → new_position`. v9 stops the response validator from discarding an LLM-extracted, quote-grounded semantic request merely because its declarative wording lacks a question mark. This implements the `DESIGN_CONTRACT.md` rule that the existing structured call supplies semantic event binding and code performs structural/evidence validation; a lexical detector no longer overrides that semantic event.

The v9 IA009 comparison confirms that the ledger fix prevents a false natural ending, but does not create quality by itself: the conversation continues for one turn and then repeats the same artifact workflow. The IA016 comparison shows that even a richer scenario naturally completes in five turns when it is a single meeting. The v8 IA003 machine pass is retained as a false-accept example and is not human acceptance.

All six probes are visible in the annotation website alongside the original v6 20×3 archive. Final verification: backend 418/418 passed; website 9/9 passed. The remaining research-design issue is interaction capacity: a 10–20-turn trajectory requires grounded later contact or a genuinely multi-stage situation. It must not be obtained by padding a one-meeting scenario or adding event fragments because turns are missing.


## v10 strengthened 20-scenario design and representative probes

All 20 scenario configurations were redesigned as five grounded interaction fragments under one continuing relationship. Each fragment has a 2–4 turn range, so the authored trajectory capacity is 10–20 turns while the global `max_turns=20` contract and natural ending remain unchanged. Every scenario now states a decision deadline, role/power asymmetry, relevant history, meaningful choices, fragment-specific live questions, an explicit pause condition, and an authored reason for later contact. Nineteen scenarios use no outcome pool. IA003 alone retains two transfer-record outcome pools because public performance evidence is necessary to distinguish a repayment promise from performance. Time advancement itself has no state effect and never counts as completion.

The scenario manifest is now included in the rollout quality fingerprint. Consequently, trajectories generated from earlier scenario definitions cannot be resumed or presented as v10 evidence. Construction and quality-gate status remain pending human review.

| Scenario | Machine outcome | Turns | Ending | Physical requests | Model semantic review |
|---|---:|---:|---|---:|---|
| IA003 | accepted | 18 | natural completion | 72 | reject: t9–t18 repeatedly mirror the same no-transfer/risk-boundary position; generated commitment was not reliably bound, so the public node correctly reported no qualifying commitment |
| IA009 | generation error | 6 complete before error | none | 27 | validator/schema failure: a reasonable acceptance-plus-own-commitment response was repeatedly rejected as action takeover; one retry also emitted unsupported `conditional_commitment` |
| IA019 | accepted | 14 | natural completion | 55 | reject: multiple agent/environment turns mirror the same wording about information access, board objection, and friendship termination |

Machine acceptance was 2/3, but semantic acceptance was 0/2 for the two machine-accepted samples. These samples therefore remain diagnostic evidence, not Gate-3 candidates. They show that the strengthened scenarios now sustain the requested range and segment progression, while the residual blockers are response/policy mirroring, IA003 commitment binding, and an action-ownership validator false positive. No quality threshold was relaxed, and no rejected sample was hidden.

Verification on this version: all 20 scenarios pass schema and 10–20 capacity checks; targeted longitudinal/two-call/ledger regression 106/106; full backend 418/418; website 9/9. The architecture remains policy call → structured appraisal call → deterministic calibration/state/dynamics/ledger update → separate response call.
