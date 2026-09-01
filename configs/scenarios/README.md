# Scenario Catalog Contract

本目录是 SocialFlux pipeline 的唯一场景输入。每个场景必须形成：

```text
scenario_NNN.json   # canonical machine definition
scenario_NNN.md     # generated human-readable pair
manifest.json       # generated catalog
```

同名 Markdown 用自然语言说明故事初始化、角色与目标、S0/D0、目标状态、三类 action 的 state/dynamics 变化、默认外显表达、视频 trigger 的 AND 阈值/crossing/cooldown/时长，以及 T1/T2/T3 配置。文档记录 JSON SHA-256，不允许脱离 JSON 单独维护。

新增或修改场景：

```bash
python scripts/scenario_docs.py configs/scenarios/scenario_NNN.json
python scripts/scenario_docs.py --check
python -m scripts.run_pipeline --scenarios configs/scenarios --output build/pipeline_v1
python scripts/run_acceptance.py --scenarios configs/scenarios --output build/pipeline_v1
```

生成器自动维护 manifest。Pipeline、acceptance 和测试会拒绝缺失/过期 Markdown 或与目录不一致的 manifest。
