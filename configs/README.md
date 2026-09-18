# SocialFlux runtime configurations

The active single-model baseline has five canonical configuration files:

- `model_routes.frontier_api.json`: the only model-to-role mapping; every role
  resolves to `claude-fable-5`.
- `formal_rollout_pool.json`: one non-replacement rollout per approved scenario.
- `review_models.json`: rollout and instance model-review profiles.
- `t4_evaluation.json`: online T4 policy, two-stage environment, and terminal judge.
- `t2_source_adaptation_v2.json`: source A selection, authored B, formal A/B
  replay, shared ending, answer, and model review.

Scenario revision uses the same `scenario_normalization` route through
`scenario_design/revision.py`; the resumable batch entry point is
`scripts/revise_scale300_scenarios.py`. Its output is a new candidate catalog,
never an in-place human-approved replacement.

`scripts/author_t2_pair_specs.py` authors source-bound T2 specifications into
`build/t2_pair_specs/`. Its generated `runtime_config.json` is the scale input
for `scripts/build_t2_source_adapted_pairs.py`.

All five point to the same route table. Structured Appraisal and Response Generation are always
separate requests even though they use the same model. Deterministic calibration
and numeric state/dynamics update occur between those requests.

The active route uses the Anthropic Messages protocol through
`providers/anthropic.py`. It is not an OpenAI-compatible production path and it
does not invoke the Claude Code agent. Seed progression, token usage, endpoint,
and model provenance are recorded by the provider owner. Transient transport
failures use bounded retries, and metrics count every HTTP attempt rather than
only logical LLM stages.

Files whose names contain `benchmark` or `ablation` are retained only when
they still support a documented diagnostic. Unreferenced probe/repair/local
configs were removed after the Fable route was frozen. Historical artifacts and
reports remain audit evidence; they are not current generation output.
