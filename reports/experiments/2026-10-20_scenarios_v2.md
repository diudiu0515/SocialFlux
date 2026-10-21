# 50 场景新版离线题库 · 2026-10-20

> 这是公开材料初稿阶段的历史报告。默认题库现已升级为上帝视角版本；最新 300 题复核、50 组 T2 回放和 138 题争议见[本次发布报告](2026-10-20_oracle_reference_and_annotation.md)。下文原始筛查数字保留用于审计，不作为当前通过结论。

当前编配 300 题，50 个场景。每个场景 T1/T2/T3 各 2 题；旧 460 题退出默认题库，原始快照保留用于溯源。

[网站 Demo](http://127.0.0.1:8000/offline-demo) · [完整题面](../../tasks/examples/offline_scenarios_v2/examples.md) · [三组字段](../../tasks/examples/offline_scenarios_v2/records.jsonl) · [旧题替换清单](../../tasks/examples/offline_scenarios_v2/replacement_ledger.json)

| 场景 | T1 | T2 | T3 | 合计 |
|---|---:|---:|---:|---:|
| GPT50_001 | 2 | 2 | 2 | 6 |
| GPT50_002 | 2 | 2 | 2 | 6 |
| GPT50_003 | 2 | 2 | 2 | 6 |
| GPT50_004 | 2 | 2 | 2 | 6 |
| GPT50_005 | 2 | 2 | 2 | 6 |
| GPT50_006 | 2 | 2 | 2 | 6 |
| GPT50_007 | 2 | 2 | 2 | 6 |
| GPT50_008 | 2 | 2 | 2 | 6 |
| GPT50_009 | 2 | 2 | 2 | 6 |
| GPT50_010 | 2 | 2 | 2 | 6 |
| GPT50_011 | 2 | 2 | 2 | 6 |
| GPT50_012 | 2 | 2 | 2 | 6 |
| GPT50_013 | 2 | 2 | 2 | 6 |
| GPT50_014 | 2 | 2 | 2 | 6 |
| GPT50_015 | 2 | 2 | 2 | 6 |
| GPT50_016 | 2 | 2 | 2 | 6 |
| GPT50_017 | 2 | 2 | 2 | 6 |
| GPT50_018 | 2 | 2 | 2 | 6 |
| GPT50_019 | 2 | 2 | 2 | 6 |
| GPT50_020 | 2 | 2 | 2 | 6 |
| GPT50_021 | 2 | 2 | 2 | 6 |
| GPT50_022 | 2 | 2 | 2 | 6 |
| GPT50_023 | 2 | 2 | 2 | 6 |
| GPT50_024 | 2 | 2 | 2 | 6 |
| GPT50_025 | 2 | 2 | 2 | 6 |
| GPT50_026 | 2 | 2 | 2 | 6 |
| GPT50_027 | 2 | 2 | 2 | 6 |
| GPT50_028 | 2 | 2 | 2 | 6 |
| GPT50_029 | 2 | 2 | 2 | 6 |
| GPT50_030 | 2 | 2 | 2 | 6 |
| GPT50_031 | 2 | 2 | 2 | 6 |
| GPT50_032 | 2 | 2 | 2 | 6 |
| GPT50_033 | 2 | 2 | 2 | 6 |
| GPT50_034 | 2 | 2 | 2 | 6 |
| GPT50_035 | 2 | 2 | 2 | 6 |
| GPT50_036 | 2 | 2 | 2 | 6 |
| GPT50_037 | 2 | 2 | 2 | 6 |
| GPT50_038 | 2 | 2 | 2 | 6 |
| GPT50_039 | 2 | 2 | 2 | 6 |
| GPT50_040 | 2 | 2 | 2 | 6 |
| GPT50_041 | 2 | 2 | 2 | 6 |
| GPT50_042 | 2 | 2 | 2 | 6 |
| GPT50_043 | 2 | 2 | 2 | 6 |
| GPT50_044 | 2 | 2 | 2 | 6 |
| GPT50_045 | 2 | 2 | 2 | 6 |
| GPT50_046 | 2 | 2 | 2 | 6 |
| GPT50_047 | 2 | 2 | 2 | 6 |
| GPT50_048 | 2 | 2 | 2 | 6 |
| GPT50_049 | 2 | 2 | 2 | 6 |
| GPT50_050 | 2 | 2 | 2 | 6 |

任务形式：`{"T1/evidence_support": 25, "T1/current_state": 26, "T2/history_comparison": 34, "T2/expression_meaning": 27, "T3/action_selection": 50, "T3/consequence_explanation": 50, "T1/state_combination": 23, "T1/interval_change": 26, "T2/history_evidence": 19, "T2/joint_comparison": 20}`。

状态维度覆盖：`{"T1/Behavioral Disposition": 72, "T1/Emotion": 1, "T1/Interaction Risk": 2, "T1/Relationship": 32, "T2/Behavioral Disposition": 40, "T2/Emotion": 4, "T2/Interaction Risk": 2, "T2/Relationship": 54, "T3/Behavioral Disposition": 25, "T3/Emotion": 1, "T3/Interaction Risk": 48, "T3/Relationship": 28}`。

主要能力：`{"situational_evidence_integration": 167, "temporal_dynamics_reasoning": 84, "multidimensional_state_distinction": 49}`；设计难度：`{"ordinary": 230, "hard": 70}`。

答案位置：`{"A": 75, "B": 75, "C": 75, "D": 75}`。

已有公开材料的独立 API 盲试答覆盖 300 题；机器指出问题或答案存在争议的题号：[]。

T3 复用 50 组已有相同起点的完整五轮分支。本批为连续互动窗口，无额外排定的外部事件（event_plan.selection=none）；核对共同起始时间、事件计划、公开时间线及窗口内未跨越外部事件，并保存条件哈希。部分事实轨迹的原始分支锁标志为 false，原样保留，未冒称两侧均开启锁定。分支结构和窗口核对不等于逐题答案已获人工批准。未来内容与隐藏状态未发送给出题/试答接口，也不进入被测输入。T2 的 5 组已有受控历史保留原回放；其余 45 组只编辑一处历史表达并记录原文和修改，公开证据核验与环境状态回放状态分开，后者仍待完成。

保留 270 对文字／文字+视频条件，题干、选项与答案相同；30 题无匹配素材，未用其他场景的视频补位。T2 焦点表达没有新增音视频。

全部为新版开发题。T1/T2 人工核验、T3 人工标注均待完成，ground_truth=null；API 一致不等于人工通过，旧来源审核状态也保留。

生成来源：144 个场景／任务组由接口生成初稿；6 个接口超时组依据同一公开材料由助手补写。后续 API 修订与助手编辑均保留原稿及内容哈希，不伪称人工审阅。

复现：`python -m offline.scenario_v2 --export-only`；仅补查改动或缺失题面：`python -m offline.scenario_v2_review --refresh-items`；发布数据及报告：`python -m scripts.publish_scenarios_v2`。`curate_scenarios_v2.py`、`refine_scenarios_v2.py`、`finalize_scenarios_v2.py` 记录公开证据补写与修订配方，按顺序使用；原始 API 记录不覆盖。
