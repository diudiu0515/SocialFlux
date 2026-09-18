# 20-turn rollout and T4 smoke log

- Date: 2026-09-08
- Scope: long-horizon contract and runtime validation, not formal benchmark evidence
- Scenario: `IA_PIPE_001`
- Evaluated policy: Qwen3-32B-AWQ
- Environment: Qwen3.5-9B
- T4 judge: GLM-4-9B

## Fixed prompts

| Prompt | SHA-256 |
|---|---|
| `task_t4_action_v3` | `35455364a18cf1d15ee745002d9d68ee284f72539272cce0fbcb6676d21417a4` |
| `environment_response_v4` | `aeb5e4cc5d3e0d60d61242b1945d3c0c67d388bfc0055331f58d64eb35f230fe` |
| `t4_judge_v2` | `3ff5f73b99ebe70908aa114326d66eee48deb881730ebecd051de193a4edad75` |

## Runs and findings

1. `/tmp/socialflux_t4_smoke_v3/IA_PIPE_001.json` completed exactly 20 turns and reached `t20/max_turns`. The automatic scores were Goal=8, Adaptation=9, Risk=7, Recovery=6, Relationship=7. Manual inspection found evaluated/environment role drift at late turns, so the result was excluded. This exposed over-optimistic judge behavior.
2. `/tmp/socialflux_t4_smoke_v4/IA_PIPE_001.json` completed exactly 20 turns. Automatic scores were Goal=3, Adaptation=7, Risk=5, Recovery=6, Relationship=4. Manual inspection found recurring proposals and unsupported off-screen administrative claims. The result was excluded.
3. The runtime validators were then tightened to reject quote-framed/narrated speech, unsupported deadlines or third-party completed actions, and semantically repeated drafts. Rejection feedback is now returned to the model on retry instead of repeating the same prompt and seed unchanged.
4. `build/long_rollout_smoke_qwen32/` subsequently produced one Qwen3-32B trajectory with 20 contiguous turns and `t20/max_turns`; its exact-turn, structural and machine hard-reject prechecks passed on the first attempt. This validates the resumable raw generator, not the six-dimensional Judge or human plausibility gate.

## Decision

None of the T4 smoke results is a benchmark score. The first two remain negative calibration evidence; the third is only a raw rollout generation smoke. Full20-scenario T4 scoring and judge–human agreement remain pending.
