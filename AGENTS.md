# Project working rules

Read `DESIGN_CONTRACT.md` before changing runtime semantics or running experiments.

- Manage new Python environments with Conda. Use `environment.yml` and
  `scripts/create_conda_env.sh`; keep GPU/video stacks in separate environments.
  Do not install project packages into `base` or introduce new unmanaged venvs.
- Keep environments, download caches, model weights and temporary builds on the
  data disk. The default is the ignored `build/runtime/`; use
  `SOCIALFLUX_STORAGE_ROOT` when the checkout is not on a data disk.
- Preserve an active experiment's frozen code, prompts and runtime. Migrate
  legacy runtimes only at a new deployment/run boundary with explicit validation.
- Prepare for external benchmark users: use portable paths and environment-based
  credentials, reuse the canonical CLI/provider/environment interfaces, and keep
  model inputs separate from author-only state, answers and audit artifacts.
- Maintain the public wire contract in `schemas/task4_session.schema.json` and
  `docs/protocols/PUBLIC_BENCHMARK_API.md`. Public interface tests must run in the
  core Conda environment without private datasets, credentials, GPUs or model calls.
- Preserve unrelated user changes and original experiment evidence. Code cleanup
  and passing engineering tests do not authorize releasing private data or confer
  benchmark admission, media rights or an open-source license.
