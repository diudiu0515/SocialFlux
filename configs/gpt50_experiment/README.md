# GPT-50 single-rollout experiment

This development experiment is isolated from the active Fable route. It uses
`gpt-6-astra` to author 50 fresh candidates and, after human Gate 1, produces
exactly one logical natural rollout per approved scenario. Astra authors the
policy actions; Claude Fable supplies the reference appraisal and response
environment. This role partition tests the GPT policy and downstream task
design without substituting an unstable environment for the primary system.

The GPT route never reads the Claude credential. It resolves only
`AUTODL_GPT_API_KEY` or the repository-external mode-600 file
`/root/.config/socialflux/autodl_gpt_api_key`; the active Claude route keeps
using `AUTODL_API_KEY` or `/root/.config/socialflux/autodl_api_key`.

The Astra route uses non-streaming Chat Completions. The same endpoint can emit
an empty visible final on long SSE requests; non-streaming keeps the complete
assistant payload available to the schema validator.

The route explicitly uses low reasoning effort. A minimal JSON probe confirmed
that this endpoint accepts the parameter; without it, the first normalization
smoke spent 360 seconds without returning a response. This is an experimental
latency control, while schema validation and human Gate 1 remain the quality
controls.

Rollout role budgets are sized to their contracts: policy action 250 tokens,
structured appraisal 900, and response 300. Larger generic caps caused the
Astra endpoint to spend minutes before the first logical turn, even though
measured historical outputs are far smaller. Route-defined appraisal budgets
take precedence over the legacy 2,800-token fallback; the fallback applies only
when neither sampling nor the provider route defines a positive output budget.

Scenario authoring uses a 700–1,000-word dossier rather than a screenplay. The
quality request has an exact six-field JSON contract. These bounds are part of
the experiment: verbosity and schema-repair loops are counted as failures, not
hidden by higher concurrency.

The single-rollout rule is strict:

- one policy slot and one seed per scenario;
- `--retry-limit 1`, so a rejected trajectory is evidence rather than a request
  for a replacement sample;
- provider transport recovery and schema correction remain technical retries,
  but never create an alternative trajectory for selection;
- Claude transport recovery may resend the same failed request up to four times;
  after exhaustion, `--resume` retains the failed first pass and cannot create
  a replacement policy sample;
- Gate 3 is pass/fail on the sole trajectory; there is no canonical best-of-N
  selection;
- task yield and scores always report the original Gate-1-approved denominator,
  including scenarios whose only rollout failed.

## Scale decision

This 50-scenario GPT run is a pipeline design audit, not the primary dataset.
It must exercise scenario authoring, human Gate 1, the sole rollout, Gates 2–3,
all T1/T2/T3 builders, T4, leakage checks, scoring, and a multi-model review.
Its report must list schema failures, retries, rejected trajectories, task yield,
ambiguous labels, leakage, and judge disagreement against the original
Gate-1-approved denominator. GPT artifacts are not silently promoted into the
Claude corpus.

Only after the audit is reviewed do we freeze the corrected design and start
the next primary batch: up to 200 Claude-authored scenarios, with the same
one-rollout rule. The existing 300-scenario catalog remains the compatibility
baseline until that explicit replacement decision; it is not used as a parent
template for either new batch.

Smoke authoring:

```bash
python scripts/generate_scale300_candidates.py \
  --brief configs/scale300_v1/authoring_brief.example.json \
  --model-routes configs/gpt50_experiment/model_routes.astra.json \
  --expected-model gpt-6-astra \
  --output data/gpt50/smoke/scenario
```

Every stage is checkpointed. Resume from the first missing or invalid artifact
with `--resume`; the smoke uses `--max-attempts 1` so a schema failure is
reported rather than silently replaced by several expensive generations.

Human Gate 1 is available at `/gpt50_gate1.html` (or the short
`/gpt50` route) on the annotation server. The page automatically selects one
active GPT batch, shows the exact scenario, roles, history, S0/D0 and triggers,
and stores hash-bound drafts in the current browser. It never mixes invalid
authoring checkpoints into the queue.

After reviewing, export `gpt50-gate1-review.json` from the page. Validate the
export before changing any scenario:

```bash
python scripts/apply_gpt50_gate1.py \
  --draft /path/to/gpt50-gate1-review.json \
  --scenarios data/gpt50/smoke/scenario_v2/scenarios \
  --output data/gpt50/smoke/review.signed.json \
  --dry-run
```

When the dry run reports the expected approved IDs, rerun without
`--dry-run`. That deterministic application step changes only approved
scenarios to `quality_gate=approved` and `initial_state=human_frozen`,
refreshes their Markdown projections, and writes the final post-freeze
SHA-bound registry. Stale hashes, incomplete attestations, missing real
reviewer identity, or sub-threshold scores stop the operation before mutation.

After human Gate 1, smoke rollout:

```bash
python -m pipeline rollout \
  --scenarios data/gpt50/smoke/scenario_v2/scenarios \
  --rollout-config configs/gpt50_experiment/rollout.hybrid.single.json \
  --development-role-partition \
  --review-registry data/gpt50/smoke/review.signed.json \
  --output data/gpt50/smoke/rollout \
  --workers 1 --retry-limit 1
```

`--allow-unreviewed` is permitted only for the one-scenario plumbing smoke. The
50-scenario experiment waits for real Gate 1 signatures.

`rollout.single.json` is retained as the all-Astra negative probe. Three bounded
smokes reached the policy action but timed out in appraisal before turn one,
including after the malformed narrative-list payload was corrected and the
request shrank by 36%. It is evidence, not a candidate pool or fallback route.

The hybrid smoke crossed the blocked boundary once: Astra policy plus Claude
appraisal/response completed one full turn. That run then stopped when the next
Claude appraisal exhausted two 429 retries. A later run used the production-like
four transport attempts; Astra policy completed in 39.54 seconds, but all four
Claude appraisal requests received overload responses. Therefore the role
partition is structurally viable, while the current service window is not ready
for a 50-scenario launch. Do not start that batch until the human Gate 1 set is
signed and a fresh sustained-capacity probe crosses several consecutive turns.

The hybrid route table includes every downstream GPT authoring, answer, review,
and judge role needed for T1/T2/T3/T4 and scoring. Those stages remain an audit
of pipeline design; they do not silently promote GPT artifacts into the primary
Claude corpus.
