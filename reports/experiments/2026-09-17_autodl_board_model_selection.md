# AutoDL board-level model selection — 2026-09-17

## Outcome

The active SocialFlux route table now uses `claude-fable-5` for every tested
production board except T3 candidate-action authoring, which uses
`gpt-6-astra`. `DeepSeek-V4-Pro` remains comparison evidence but won no route
under this endpoint because visible-final response reliability was materially
lower. This is a project-role selection, not a general intelligence ranking.

The comparison used three models exposed by the same AutoDL Chat Completions
endpoint:

- `gpt-6-astra`, corresponding to OpenAI's current most capable model:
  <https://developers.openai.com/api/docs/models/gpt-6-astra>
- `claude-fable-5`, a frontier Claude model:
  <https://www.anthropic.com/claude/fable>
- `DeepSeek-V4-Pro`, from the current DeepSeek family:
  <https://api-docs.deepseek.com/news/news260813/>

All outputs remain model proposals or model reviews pending human verification.

## Evidence and accounting

The three selection runs plus the scale-50 confirmation produced 1,008 logical
cases and 1,315 cumulative actual requests:

| Run | Logical cases | Actual requests | Scope |
| --- | ---: | ---: | --- |
| `api_model_gap_benchmark_autodl_v2` | 60 | 61 | scenario authoring, task extraction, quality review |
| `api_model_role_benchmark_autodl_v1` | 78 | 93 | policy, appraisal, response, T2 construction, task answer, semantic review |
| `task_model_benchmark_autodl_pilot_v1` | 120 | 133 | T1/T2/T3 answers, T3 actions, T4 judge on all 8 currently eligible heterogeneous scenarios |
| `task_model_benchmark_autodl_scale50_v1` | 750 | 1,028 | 50 scenarios × 5 task boards × 3 models, including one preserved error-only retry pass |

The gap run originally recorded 45 requests because failures lost access to the
helper-local provider call index. Inspection found fourteen one-request
empty-visible-stream failures and one two-attempt structured-output failure.
The saved result now records 61 and retains the original 45 in
`request_accounting_correction`; the runner now constructs the provider before
dispatch. Smoke tests and the explicitly invalid first gap configuration are
kept outside the 1,315 valid matched-request total.

After routing was frozen, one minimal non-private smoke request was sent through
the active Claude policy route and one through the Astra T3-action route. Both
returned visible assistant content via the private-file secret fallback. These
two smoke requests are operational checks and are not included in the matched
benchmark totals above.

## Schema-valid completion results

### Generation and review gaps

| Board | DeepSeek | Claude | Astra |
| --- | ---: | ---: | ---: |
| Scenario authoring | 2/4 | **4/4** | 3/4 |
| Task extraction | 4/8 | **8/8** | 7/8 |
| Quality review | 3/8 | **8/8** | 6/8 |

Claude also flagged both saved known-quality trajectories, IA004 and IA252.
IA252 matched a predeclared expected category; IA004 was flagged as repetition
rather than either of its two predeclared categories, so the strict known-issue
matcher records 1/2. DeepSeek's main failure was a streamed response without
visible final assistant content; this is an endpoint/protocol result, not a
claim that the model is generally less capable.

### Rollout and T2 execution chain

| Board | DeepSeek | Claude | Astra |
| --- | ---: | ---: | ---: |
| Policy | 6/6 | **6/6** | 5/6 |
| Structured Appraisal | 3/6 | **6/6** | 3/6 |
| Environment Response | 3/6 | **6/6** | 5/6 |
| T2 branch construction | 2/2 | **2/2** | 1/2 |
| Small task-answer probe | 2/2 | **2/2** | 2/2 |
| Semantic review | 4/4 | **4/4** | 3/4 |

Full-output reading favored Claude for contextual continuity, unresolved-request
handling, and natural responses. The architecture remains two independent
environment calls with deterministic Python state/dynamics update between
Appraisal and Response.

### Task pilot on eight scenarios

| Board | DeepSeek | Claude | Astra |
| --- | ---: | ---: | ---: |
| T1 answer | 3/8 | **8/8** | 7/8 |
| T2 answer | 4/8 | **8/8** | 6/8 |
| T3 action authoring | 4/8 | 8/8 | **8/8** |
| T3 answer | 2/8 | **8/8** | 7/8 |
| T4 judge | 2/8 | **8/8** | 4/8 |

For T2, Claude more often retained uncertainty where public bilateral evidence
did not justify a unique trust or hostility comparison; Astra and DeepSeek were
more likely to emit confident directional answers. For T3 actions, Astra won the
tie because all eight completed without retry and its options stayed distinct
while introducing fewer unsupported exact amounts, timings, or extra conditions.

### Scale-50 confirmation

| Board | DeepSeek | Claude | Astra |
| --- | ---: | ---: | ---: |
| T1 answer | 50/50 | **50/50** | 50/50 |
| T2 answer | 49/50 | **50/50** | 39/50 |
| T3 action authoring | 50/50 | 50/50 | **49/50** |
| T3 answer | 50/50 | **50/50** | 39/50 |
| T4 judge | 50/50 | **50/50** | 49/50 |

Bold indicates the final route, not success count alone. Claude completed all
five boards at 50/50 and used the fewest requests and lowest latency on each
board except the content-selected T3 action route. Across successful T3 action
outputs, all three models had zero exact duplicate candidates. Astra introduced
zero new numeric specifics absent from the task input, compared with three for
Claude and one for DeepSeek. Full-text review of IA003, IA018, IA074, IA144,
IA252, and IA296 also found Astra's actions more consistently bounded by
observable facts. That content advantage outweighs its one residual empty-final
failure; failed instances remain failures and are not hidden.

After one preserved retry pass, 725/750 records succeeded. The 25 residual
failures were: Astra T2 answer 11, Astra T3 answer 11, Astra T3 action 1, Astra
T4 judge 1, and DeepSeek T2 answer 1. The cumulative count is 1,028 requests:
805 latest-attempt requests plus 223 requests retained in `attempt_history`.

## Active routing decision

> 2026-09-18 policy update: the project owner selected a single-model
> development setting. All active routes now use `claude-fable-5`. The
> board-specific comparison below remains the empirical historical result and
> is not rewritten; in particular, Astra's T3-action content advantage remains
> documented as an ablation finding.

- Claude: every active semantic route, with independent provider calls per role.
- Astra: historical T3 candidate-action ablation only; no active route.
- DeepSeek: no active winner route in this provider setup.
- `legacy_task_bundle`: historical recovery only, not allowed for new formal
  construction.

T3 branch continuation reuses policy → appraisal → deterministic update →
response. It is not a separate hidden generation pipeline.

## Limits and next decision

This selection is strong enough to replace the earlier Paratera routing and to
run a larger development batch, but it is not yet a 300-scenario quality claim.
Scenario writing used four briefs, execution-chain probes used six rollout cases
(and smaller T2/review subsets). The completed task pilot used a frozen,
reproducible eight-scenario sample. The strict scale-50 confirmation then used
50 unique packages selected from 81 that met the same source/version/task
criteria; it is complete and recorded above.
Before freezing publication data, humans still need to assess naturalness,
factual responsibility, state evidence, and answer correctness on the generated
artifacts. The old Paratera results remain archived but are explicitly
superseded and are not used for routing.
