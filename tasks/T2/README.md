# T2 source-adapted pipeline v2

Before every run, read the repository-wide
[`DESIGN_CONTRACT.md` pre-run engineering discipline](../../DESIGN_CONTRACT.md#21-每次运行前必读代码结构与修改纪律).
T2 changes must extend the owner modules below; do not add scenario-specific
branches, duplicate builders, or wrapper chains around this pipeline.

The active construction path is:

1. `source_selection.py` checks whether rollout A has enough meaningful public
   history and no saved machine/model hard rejection. Weak sources are recorded
   as `skipped_source_quality` before any model request.
2. `branch_authoring.py` writes the complete B suffix in one call. It does not
   generate policy and environment turns independently.
3. `pair_builder.py` restores the same checkpoint for A and B and replays every
   turn through Structured Appraisal → deterministic Python update → Response.
   The authored public B response is controlled, while the Response call still
   produces its ledger events, expression intent, and observable behavior.
4. `quality_review.py` reads the full pair. It records every reviewed environment
   turn and emits detailed annotations only for actual repetition, request,
   ownership, fact, completion, character, or naturalness problems. It never
   rewrites dialogue.
5. `answering.py` generates the candidate answer for human verification.
   Determinate comparisons require bilateral evidence. A missing side is allowed
   only when `cannot_determine` is the highest-probability label; a state with no
   public evidence on either side is invalid.
6. `pair_completion.py` owns pair review, answer generation, and answer review.
   These stages can resume without rerunning A/B environment calls.
7. `run_artifacts.py` scopes artifacts to a run manifest. Summaries read only the
   expected files for that run, so stale pairs cannot silently become successes.

`model_pair_review` and `model_answer_review` are model diagnostics, never human
acceptance. The original rollout, failed attempts, request counts including
retries, private replay logs, and pending human status remain in the artifact.

The command-line entry point is `scripts/build_t2_source_adapted_pairs.py`.
`scripts/run_t2_source_adapted_pairs.sh` runs the current three-pair development
configuration in the background with one run ID. It reads the single active
`configs/model_routes.frontier_api.json`: branch authoring uses
`t2_branch_authoring`, answers use `t2_answer`, and reviews use
`t2_pair_review` / `t2_answer_review`. Formal replay keeps separate
`appraisal` and `response` providers with deterministic Python state update
between them.

The active AutoDL route requires `AUTODL_API_KEY` in its process environment.
It never starts local vLLM or accepts an endpoint override.
The route file hash is bound into the run manifest; changing models requires a
new run ID.
