# Scale300 Claude 直建模板

Scale300 不继承 Scale20、Scale100、Scale150 或 Scale200。Claude 直接创建
300 个完整 canonical scenario；旧目录、旧 design matrix 和旧场景不能作为
复制源或默认模板。

## 每个场景的输出

第 `NNN` 个场景只写入：

```text
configs/scale300_v1/scenarios/scenario_NNN/scenario_NNN.json
```

JSON 必须符合 `schemas/scenario.schema.json`，并满足：

- `scenario_id` 严格为 `IA_PIPE_NNN`；
- `max_turns` 为 20；
- `construction_status.quality_gate` 保持待人工审核；
- `construction_status.initial_state` 保持候选、不得由模型标为 frozen；
- S0/D0、状态变量和 trigger 必须由本场景的人物、历史、目标与冲突推出；
- 不得包含 action taxonomy、`action_effects`、response template、预设最佳策略或预设结局；
- 应存在真实 trade-off、信息不对称、至少三条合理行动方向和长期适应空间；
- Narrative-derived 场景只抽象关系机制，人物、事实、事件和对白必须原创并记录 provenance；
- 生成器不得填写真人姓名、审核时间、`human_attestation=true` 或 Gate 1 pass。

Claude 可以参考 `DESIGN_CONTRACT.md`、`schemas/scenario.schema.json`、
`prompts/scenario_script_generation_v1.md`、
`prompts/scenario_candidate_normalization_v1.md` 和
`prompts/scenario_candidate_initialization_v1.md`，但不得读取旧 Scale catalog
来续写。

可执行直建入口为：

```bash
python scripts/generate_scale300_candidates.py \
  --brief configs/scale300_v1/authoring_brief.example.json \
  --output data/scenario_authoring/run_001
```

该入口依次进行原创 narrative、独立机器质量检查、blueprint normalization
和 S0/D0 proposal；任何机器检查都不会批准 Gate 1。每次运行写入新的 versioned
目录，保留模型 provenance、token usage、质量报告和中间产物。

## 完整性检查

Claude 写完 300 个 JSON 后运行：

```bash
python scripts/build_scale300_v1.py --check
python scripts/build_scale300_v1.py
python scripts/build_scale300_review_template.py
```

第二条命令只生成 Markdown、manifest、coverage 和 design matrix，不修改场景
语义。第三条命令生成 unsigned、hash-bound Gate 1 表，之后才进入人工审核。
