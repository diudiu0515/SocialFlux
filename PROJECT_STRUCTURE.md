# Project Structure

```text
SocialFlux/
├── configs/
│   ├── rollout_pool.example.json
│   └── scenarios/
│       ├── manifest.json
│       ├── coverage_matrix.json
│       └── scenario_NNN/
│           ├── scenario_NNN.json
│           ├── scenario_NNN.md
│           └── rollouts/                 # local/generated
├── environment/                          # single canonical stateful environment
├── policies/                             # free-form model policy
├── rollout/                              # natural runs + local checkpoint branches
├── offline/                              # rollout-derived T1/T2/T3 builders
├── evaluation/                           # nine-item acceptance + leakage checks
├── annotation/                           # independent human label overlays
├── prompts/                              # all fixed prompts + hash manifest
├── schemas/                              # scenario/trajectory/construction contracts
├── tasks/                                # current task specs + probability utilities
├── scripts/                              # source, docs, pipeline, acceptance commands
├── web/                                  # read-only visualizer
├── tests/                                # contract and smoke tests
└── build/                                # reproducible local artifacts, gitignored
```

删除的 legacy 范围包括 demo/interactive benchmark、world converter、controlled policies、action interpreter、template response、v0.2 world task schemas、旧 prompt 版本和旧 committed build。当前没有第二套环境或网站状态机。

`revision.md`、`prompt_check.md` 是本轮设计输入，`self_check.md` 是必须持续维护的任务账本，因此保留。
