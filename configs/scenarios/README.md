# Scenario Bundles

每个 `scenario_NNN/` 必须同时包含：

- `scenario_NNN.json`：canonical machine truth；
- `scenario_NNN.md`：确定性生成的自然语言说明；
- `rollouts/`：本地 natural model trajectory、manifest 与 `dialogues.md`。

JSON 更新后运行：

```bash
python scripts/scenario_docs.py
python scripts/scenario_docs.py --check
```

Catalog `manifest.json` 记录 JSON/Markdown hash、source mix 与 prompt hash；`coverage_matrix.json` 汇总 source、关系、权力、goal conflict、information asymmetry、state family 和 validation suitability。

当前 10 个 scenario 是 revision migration candidate：5 个 narrative-derived、5 个 synthetic-script，但 quality gate 与 S0/D0 均未获得真实审核。正式 rollout 前必须将完整审核记录落实到 scenario status；`--allow-unreviewed` 只能用于开发。
