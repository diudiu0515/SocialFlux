# Rollout Screening Protocol v1 Execution Log

- Run time: 2026-09-07T13:56:35Z
- Protocol: `docs/protocols/SocialFlux_Rollout_Screening_Protocol_v1.md`
- Generator: `scripts/build_rollout_screening.py`
- Machine-readable local report: `build/rollout_screening_v1/screening_report.json`
- Canonical local materialization: `build/rollout_screening_v1/selected/`
- Selection status: **provisional pending human comparative review**

## Scope and result

The inventory scan found 184 recoverable trajectories across the 20 scenarios:
60 active candidates, 123 rejected/archive trajectories, and 1 orphan archive
trajectory. Deterministic Protocol v1 decisions are PASS=64, REVIEW=108 and
REJECT=12. All 184 appear in the website human-review queue.

The user-required final cardinality is one canonical rollout per scenario. The
automatic ranker therefore emits exactly one provisional winner for each of 20
scenarios. It ranks by decision tier, mean quality, critical-dimension floor,
state-response consistency and interaction progression. Model identity is not a
ranking feature and no family quota is applied.

This run does **not** human-freeze those winners. All legacy quality judgments
lack the v2 contract's explicit per-dimension turn-ID evidence, and all three
active candidates in each scenario require comparative review. Consequently,
`human_review_queue_count=184` and the generated `selected/` directory is a
provisional working view, not `data/formal/selected` and not a clean pool.

## Provisional winners

| Scenario | Trajectory ID | Policy model | Auto decision | Mean |
|---|---|---:|---:|---:|
| IA_PIPE_001 | b9d80695890c4a47b4a2508798ff74f2 | Qwen3.5-9B | PASS | 4.000 |
| IA_PIPE_002 | 09b6344cc85242e9af7393d4b47b2ebe | GLM-4-9B | PASS | 4.500 |
| IA_PIPE_003 | e7d688c4f36545a4a52f2031fa42a3e0 | Qwen3-32B-AWQ | PASS | 4.500 |
| IA_PIPE_004 | dcdb5dc88c9d4048a01808e50b730d46 | Qwen3.5-9B | PASS | 4.500 |
| IA_PIPE_005 | cb5412cbce1644498b73bf6499d4b89b | Qwen3.5-9B | PASS | 4.333 |
| IA_PIPE_006 | 1e99cf8bdd1549a29bb5cd01ca15cb9b | Qwen3.5-9B | PASS | 4.500 |
| IA_PIPE_007 | 4087ad12d218446fb5c4c7fd8a30b4cc | Qwen3.5-9B | PASS | 4.500 |
| IA_PIPE_008 | 2a0002aa592d4099b60072b9134710ab | Qwen3.5-9B | PASS | 5.000 |
| IA_PIPE_009 | 5f926a29878d47c89a1618b13ad531c2 | Qwen3-32B-AWQ | PASS | 4.667 |
| IA_PIPE_010 | 3c250d2171c3413d8bc1228950e51074 | Qwen3.5-9B | PASS | 5.000 |
| IA_PIPE_011 | 54866cb065dd4401a4d172956cf71e7f | GLM-4-9B | PASS | 4.417 |
| IA_PIPE_012 | c642d13bffe24fd69a81e2f373d5d324 | Qwen3.5-9B | PASS | 4.500 |
| IA_PIPE_013 | a099cb0a8a534b88b235e7e5604fd64e | Qwen3.5-9B | PASS | 4.583 |
| IA_PIPE_014 | 7e50a92b9c2244a48ff36706ac110263 | Qwen3-32B-AWQ | PASS | 5.000 |
| IA_PIPE_015 | f908e9fbbd1f48558c1f8389d2f1fd74 | Qwen3.5-9B | PASS | 4.500 |
| IA_PIPE_016 | e85a62bcf42445f983689a6352b48c4a | Qwen3.5-9B | PASS | 4.500 |
| IA_PIPE_017 | e28017b180d74a39a2a41d42b6e03217 | Qwen3.5-9B | PASS | 4.500 |
| IA_PIPE_018 | 424bae60fd324e46bafdd7813cba2e9f | Qwen3.5-9B | PASS | 4.500 |
| IA_PIPE_019 | d7fb464268f64007b7ed18d14554e094 | Qwen3.5-9B | PASS | 4.583 |
| IA_PIPE_020 | ede63883236c43f9b42addd64181ac90 | Qwen3.5-9B | PASS | 4.500 |

Distribution: Qwen3.5-9B=15, Qwen3-32B-AWQ=3, GLM-4-9B=2. This is an
artifact of the active development pool and legacy Judge evidence, not evidence
that the 9B model is intrinsically better.

## Human review surface

For every queued rollout the website shows the full observable trajectory,
source stage, model/seed provenance, outcome, six dimension scores, mean,
hard-reject list, Judge rationale, history-intervention evidence, missing
turn-evidence warning, automatic decision and queue reason. The reviewer then
answers the protocol's five audit questions and, for active candidates, chooses
one winner for the scenario. Choosing a different winner clears the previous
local winner flag.

The dedicated manual checklist additionally exposes every item that still needs
a person: Gate 1 scenario and S0/D0 freeze, Gate 2 environment evidence, Gate 3
rollout comparison, Gate 4 T1/T2/T3 checks, formal three-person GT,
expression/continuity/speech/multimodal video checks, filter-holdout evaluation,
and release duplicate/leakage/contamination audit. Missing files remain visible
as pending; the UI does not hide them.

## Model-capacity decision

The present active pool used Qwen3.5-9B heavily for iteration speed and because
that service was already deployed. It is a development pool, and its same-family
environment/policy overlap is not acceptable evidence for the formal pool.

The next matched formal pilot should keep Qwen3.5-9B environment-only and compare
Qwen3-32B-AWQ, a quantized GLM-4-32B deployment if it fits, and the DeepSeek
family under identical scenarios, seeds, token budgets, Judge contract and blind
human review. A larger hosted DeepSeek policy can contribute at most 30% only
when credentials and complete provenance are available. Parameter count is not
a selection feature.

At the time of this run, all four 48GB GPUs were occupied by the separate
Qwen3.5 environment, Qwen3-32B, GLM-4-9B and DeepSeek-V2-Lite services. Giant
235B/671B MoE models still require distributing their total weights even though
only a subset is activated per token, so they cannot simply replace one service
in the current four-service layout. Any upgrade must record memory, parallelism,
quantization, throughput and failure evidence before changing the formal config.

## Verification

- `python -m unittest discover -s tests -v`: 149/149 passed.
- `python -m unittest discover -s web/tests -v`: 7/7 passed.
- `python scripts/scenario_docs.py --check`: 20/20 scenario pairs plus manifest
  and coverage passed.
- `git diff --check`: passed.
- Updated server API/page smoke: 20 scenarios, 184 queued rollouts, 8 manual
  review categories, and one provisional winner per scenario.
