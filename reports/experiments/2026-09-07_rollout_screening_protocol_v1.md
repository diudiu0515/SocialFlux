# Rollout Screening Protocol v1 Execution Log

- Current rerun: 2026-09-08T13:03:21Z
- Protocol: `docs/protocols/SocialFlux_Rollout_Screening_Protocol_v1.md`
- Historical generator: removed after Gate 3 was consolidated into `python -m pipeline gate3`
- Machine-readable local report: `build/rollout_screening_v1/screening_report.json`
- Required horizon: exactly 20 turns
- Selection status: **no eligible 20-turn candidates**

## Current result

The recoverable legacy inventory contains 184 trajectories across 20 scenarios: 60 active candidates, 123 rejected archives and 1 orphan archive. Every trajectory has only 6 turns. Under the revised exact-20-turn contract each receives hard reject `meaningless_premature_ending`, so the deterministic result is REJECT=184, REVIEW=0, PASS=0 and provisional winner=0.

The older 2026-09-07 result (PASS=64, REVIEW=108, REJECT=12 and 20 provisional winners) is superseded because it was calculated before the 20-turn hard requirement. It must not be cited as the current clean pool. The files remain available as historical evidence; none may source new Task 1–4 instances.

## Human review surface

All 184 old trajectories remain visible in the website because they are useful for auditing the horizon migration, old Judge evidence and filter behavior. The website does not hide rejected candidates or fabricate a winner when all candidates fail. New20-turn candidates will need the same full observable trajectory, provenance, six dimensions, hard-reject reasons, turn-ID evidence, protocol five questions and within-scenario comparative review before one candidate can be confirmed.

## Next run

`configs/rollout_20turn_multimodel_development.local.json` defines 20 scenarios × 12 candidates using a Qwen3.5-9B environment and environment-separated Qwen3-32B, GLM and DeepSeek policies. `scripts/generate_long_rollout_pool.py` writes each accepted 20-turn trajectory atomically, preserves rejected attempts and resumes by slot. Completion of generation is not equivalent to Protocol PASS or human confirmation.
