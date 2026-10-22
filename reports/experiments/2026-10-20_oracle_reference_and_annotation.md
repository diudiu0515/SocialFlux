# 上帝视角参考、人工盲答与 GT 采集

报告时间（北京时间）：2026-10-20T23:00:51.367797+08:00。

已发布 50 场景、300 道开发题。每个场景 T1/T2/T3 各 2 题；300 题均绑定真实保存的私有状态、完成独立私有证据核验及公开材料盲答。机器综合标记 138 题需修订或裁决，其余 162 题仍待人工审核。人工 GT 与正式准入均为 0，不能把本次生成完成称为正式测试集通过。

| 配置 | 当前值 |
|---|---|
| T1 | 每场景 2 题，完整公开前史 t1–t2；当前状态／区间变化／证据支持／双变量组合 |
| T2 | 每场景 2 题，A/B 历史各 2 轮、一个共同 ending；50 组同快照受控回放均已验证 |
| T3 | 每场景 2 题，2 个候选行动；每个行动保存 5 次环境回应，按即时或指定延迟窗口判断 |
| 选项 | 四选一，A/B/C/D 各 75 个候选答案；组合题恰好两个实际记录变量 |
| 视频配对 | 270 个逻辑配对；素材待人工。T2 只复用未改变的 t1 视频 |
| Gate4 人工抽样 | 同一固定样本 30 题，每任务 10 题；两人独立审核，分歧待第三人裁决 |

上帝视角证据包括人物设定、完整相关对话、实际状态与更新依据，以及 T2 的两侧受控回放／T3 的行动分支。T1 禁止用截止点以后的事实解释当前状态；即时 T3 不得用后续分支证据。每条分支只有一个实现样本，不能据此声称一般发生概率。

本次修订了 90 题的目标变量。GPT50_044 的 T2 删除无依据的选民偏好断言；GPT50_050 的 T2 将既有权限分工改成肯定表达。两个修订均另存版本并重放；原始自然轨迹和失败记录保持原样。

公开盲答与私有复核均为独立请求，未向检查者提供候选答案；出题和这两类检查沿用同一模型系列，仍可能存在相关偏差。它们是题目质量筛查，不是独立模型能力准确率。

私有侧唯一答案一致且无问题：197/300；综合公开／私有检查后无标记：162/300。

私有复核问题（可重叠）：`{"private_only": 32, "scope_mismatch": 4, "ambiguous": 11, "state_conflict": 5, "option_cue": 2, "missing_state": 1, "wrong_subject": 1, "branch_overclaim": 5}`。

公开盲答问题（可重叠）：`{"subject_mismatch": 3, "history_independent": 17, "option_cue": 7, "ambiguous": 4, "wrong_form": 3, "unsupported": 1}`。

## 人工流程

入口 `/offline-annotation`。先完成分配范围内全部公开材料盲答并锁定；再开放相关私有证据，完成全部独立 GT 初判；最后按需查看机器候选，提交最终人工判断。三个阶段分别落盘，刷新可恢复，原盲答不可覆盖。当前采集固定为文字条件，与文字被测输入同一白名单投影。

两名不同标注人的有效一致结论仅形成待冻结的人类共识；分歧、修改／拒绝意见继续待裁决。某位参与者的人类基线只使用另外至少两人的一致标签，排除其本人 GT；没有独立标签时准确率为 N/A。重复参与或声明已看过私有材料者不进入盲测基线。标注人 ID 为自报身份，需由实验组织者分配和核对。

原 `/offline-demo` 是探索与题库审核入口，可筛选机器争议题。正式采集应从新入口开始；已看过旧页面参考答案者须如实声明暴露。没有模拟测试记录写入生产人工库。

## 来源与复现

- 题库：`tasks/examples/offline_scenarios_v2`；完整原版本：`data/offline_oracle_20261020_complete/previous_release`。
- 主冻结批次、失败请求、修订历史和逐题证据：`data/offline_oracle_20261020_complete`。
- Gate4 机器检查与固定抽样：`data/offline_oracle_20261020_complete/gate4_machine.json`。
- 主批次实际日志请求 867 次（含失败、修订与解释字母核对，不含之前两个启动批次；详见原始日志）。
- 刷新本报告：`python -m scripts.report_oracle_release`；四 Gate 和 T4 快照：`python -m scripts.publish_experiment_status`。

## 逐题机器争议

| 题号 | 作者保留问题 | 私有核验问题 | 公开盲答问题／分歧 |
|---|---|---|---|
| SFV2-001-T1-02 | — | — | subject_mismatch |
| SFV2-001-T2-01 | — | private_only | history_independent |
| SFV2-001-T2-02 | — | private_only | history_independent |
| SFV2-003-T3-01 | 来源安全损害风险本身不在 allowed_state_paths 中，且两条回放均未记录该变量；因此只能依据公开的接触差异作方向性判断，不能断言实际安全风险数值或普遍概率。; 私有 goal_failure_risk 在两条分支的即时记录同为 6，不能据此称行动 2 的该项记录更低。 | — | — |
| SFV2-004-T2-01 | — | scope_mismatch | ；盲答 A，候选 C |
| SFV2-004-T3-01 | — | ；独立答案 A，可接受 ['A']，候选 C | — |
| SFV2-005-T1-02 | — | — | option_cue |
| SFV2-005-T2-01 | — | ambiguous | ；盲答 D，候选 A |
| SFV2-005-T3-01 | — | ；独立答案 D，可接受 ['D']，候选 A | ；盲答 D，候选 A |
| SFV2-006-T2-02 | — | ambiguous | — |
| SFV2-006-T3-01 | — | private_only | — |
| SFV2-006-T3-02 | 两条回放的relationship.perceived_responsiveness即时终值相同（行动1与行动2均由6升至7）。因此，若本题必须严格以该数值状态作唯一高低比较，唯一性不足；当前答案D依据的是公开对话中行动2对时限关切提供了更具体替代路径，而不是声称私有数值更高。 | private_only | — |
| SFV2-007-T1-02 | — | — | ambiguous |
| SFV2-007-T2-01 | 题干询问对特定结论立场的理解，而 target_state_ids 仅含 perceived_responsiveness；该变量 A/B 回放同值，不能支持唯一的状态比较。按要求保留目标变量时只能给出公开语义最佳答案，非状态差异答案。 | — | — |
| SFV2-007-T2-02 | expression_meaning 的公开语义与 evidence_seeking 状态并非同一变量；回放显示该状态 A/B 均为 3、无新证据，因此选项 B 不能作为私有状态差异的答案，只能作为公开表达的最佳解释。 | — | — |
| SFV2-007-T3-01 | 私有状态记录没有decision_error_risk变量；reputational_harm_risk是最接近且实际存在的风险变量，但不等同于决策错误概率。答案据此作操作化解释，不应泛化为普遍因果规律。 | ；独立答案 D，可接受 ['D']，候选 A | — |
| SFV2-007-T3-02 | 即时窗口内两个分支的relationship.perceived_responsiveness都从6升至7，故目标变量同值，无法给出可靠的方向性唯一答案。依要求仍列最佳候选B，但不应视为通过；若要得到可判分的唯一答案，应改成询问行动2回应是否体现合作或是否承诺扩大核查等可直接核验的公开行为，而非比较该私有状态的高低。 | — | — |
| SFV2-008-T1-02 | — | state_conflict | — |
| SFV2-008-T3-02 | — | — | ；盲答 C，候选 D |
| SFV2-009-T3-02 | — | private_only | — |
| SFV2-010-T2-01 | 焦虑记录只相差一个等级，不应夸大为显著变化，也不能由单次回放推断普遍因果规律。 | — | ；盲答 A，候选 C |
| SFV2-010-T2-02 | 公开话语中的金额决策权差异可支持程序公平性的方向性讨论，但实际回放两分支该状态同为5，不能据此声称存在确定差异。 | — | ；盲答 C，候选 D |
| SFV2-010-T3-01 | — | ；独立答案 A，可接受 ['A']，候选 C | ；盲答 A，候选 C |
| SFV2-011-T1-01 | — | ambiguous；独立答案 D，可接受 ['D']，候选 A | ；盲答 D，候选 A |
| SFV2-011-T1-02 | — | option_cue | — |
| SFV2-011-T2-01 | — | — | history_independent |
| SFV2-012-T1-01 | — | — | ；盲答 B，候选 C |
| SFV2-012-T2-01 | — | private_only；独立答案 D，可接受 ['D']，候选 C | ；盲答 D，候选 C |
| SFV2-012-T2-02 | 原题询问的 relationship.trust 不在 allowed_state_paths，故不能回答该变量的实际私有状态；修订题目改问允许记录的 perceived_responsiveness。 | missing_state; private_only | history_independent |
| SFV2-013-T1-02 | — | ambiguous | — |
| SFV2-013-T2-01 | — | ；独立答案 C，可接受 ['C']，候选 A | ；盲答 C，候选 A |
| SFV2-013-T3-02 | — | — | ；盲答 A，候选 B |
| SFV2-014-T1-02 | — | — | ；盲答 B，候选 D |
| SFV2-014-T2-02 | — | private_only | — |
| SFV2-015-T1-02 | — | state_conflict | — |
| SFV2-015-T2-01 | 私有记录中 A、B 的 perceived_responsiveness 终值相同，不能把本题解释为已记录状态的数值比较；答案只比较公开回应对特定顾虑的具体程度。 | — | — |
| SFV2-015-T2-02 | 两支回放的 cooperation_readiness 终值相同，故本题不能支持 A/B 准备度高低比较；答案只辨认各支公开提出的协作方向。 | — | — |
| SFV2-016-T3-02 | — | — | ；盲答 B，候选 D |
| SFV2-017-T2-01 | 两分支的公平感私有数值相同，公开材料支持对责任分配方式的方向性判断，但不能据此声称A的数值状态确定高于B。 | ambiguous; state_conflict；独立答案 C，可接受 ['C']，候选 A | — |
| SFV2-017-T3-02 | — | — | ；盲答 B，候选 B |
| SFV2-018-T1-02 | — | ；独立答案 C，可接受 ['C']，候选 D | ；盲答 C，候选 D |
| SFV2-019-T2-01 | — | ；独立答案 D，可接受 ['D']，候选 A | ；盲答 D，候选 A |
| SFV2-019-T3-02 | — | — | ；盲答 A，候选 B |
| SFV2-020-T1-02 | — | wrong_subject | — |
| SFV2-020-T2-01 | — | — | history_independent |
| SFV2-020-T3-01 | — | private_only | — |
| SFV2-020-T3-02 | — | private_only | — |
| SFV2-021-T1-02 | — | — | wrong_form |
| SFV2-021-T2-01 | — | — | history_independent |
| SFV2-021-T2-02 | — | — | history_independent |
| SFV2-021-T3-01 | 两分支的goal_failure_risk即时数值均从7降至6；B是由公开机制与回应支持的目标推进判断，不是私有数值上行动2严格优于行动1的断言。每个行动只有一条实现轨迹，不能由此估计普遍概率。 | — | — |
| SFV2-021-T3-02 | 若目标被解释为私有操作化relationship.perceived_responsiveness的严格分支排序，行动1数值更高；本题改为比较哪项公开行动更直接回应安全与学校安排关切。分支各只有一条轨迹，不能把单次数值或回应推断为普遍规律。 | — | — |
| SFV2-022-T3-01 | institutional_harm_risk 不是披露决策错误风险的专门测量；答案的唯一性主要由公开行动文本及回应对目标的直接匹配支持，不能据此声称量化风险差异。 | — | — |
| SFV2-022-T3-02 | 题面询问“预期风险”，但分支即时记录对该风险变量同值；公开文本可解释行动 2 的潜在后续优势，却不能支持即时唯一的方向差异。答案因此仅能是当前节点无确定差异，实际之后的传达时点及安全效果仍未决。 | — | ；盲答 C，候选 D |
| SFV2-023-T2-01 | — | — | history_independent；盲答 B，候选 A |
| SFV2-023-T2-02 | — | ambiguous；独立答案 C，可接受 ['C']，候选 B | — |
| SFV2-023-T3-01 | 两行动的即时合作准备度均由8升至9，因此该状态变量本身不能区分行动优劣；A仅是结合目标中当天成员审阅这一条件的最佳选项，不构成数值优越或普遍效果结论。 | — | — |
| SFV2-023-T3-02 | — | ；独立答案 C，可接受 ['C']，候选 B | ；盲答 C，候选 B |
| SFV2-024-T1-01 | — | ；独立答案 D，可接受 ['D']，候选 C | ；盲答 D，候选 C |
| SFV2-024-T3-02 | 回应性在五轮末行动1与行动2都达到10，不能据此断言行动1最终高于行动2；题目将该变量表述为行动1分支内的上升，而非跨分支胜出。 | branch_overclaim | — |
| SFV2-025-T1-02 | — | — | wrong_form |
| SFV2-025-T2-01 | — | private_only | ；盲答 C，候选 A |
| SFV2-025-T2-02 | — | private_only；独立答案 A，可接受 ['A']，候选 B | ；盲答 A，候选 B |
| SFV2-025-T3-01 | — | ；独立答案 C，可接受 ['C']，候选 A | ；盲答 C，候选 A |
| SFV2-025-T3-02 | — | state_conflict | ambiguous；盲答 A，候选 B |
| SFV2-026-T1-02 | — | scope_mismatch | — |
| SFV2-026-T2-01 | — | private_only；独立答案 B，可接受 ['B']，候选 C | — |
| SFV2-026-T2-02 | — | private_only；独立答案 C，可接受 ['C']，候选 D | — |
| SFV2-026-T3-02 | — | branch_overclaim | ambiguous；盲答 B，候选 D |
| SFV2-027-T2-01 | 两侧relationship.perceived_responsiveness结尾记录相同，不能据此判定B的私有数值状态更高；答案仅比较公开回应对题目所指关切的直接程度。 | — | — |
| SFV2-027-T2-02 | — | — | history_independent |
| SFV2-028-T2-01 | — | private_only | history_independent；盲答 A，候选 C |
| SFV2-028-T2-02 | — | private_only | — |
| SFV2-029-T1-02 | — | ；独立答案 A，可接受 ['A']，候选 B | ；盲答 A，候选 B |
| SFV2-029-T2-02 | — | — | history_independent |
| SFV2-029-T3-01 | — | ambiguous | — |
| SFV2-029-T3-02 | — | branch_overclaim | unsupported |
| SFV2-030-T2-01 | 公平性记录两侧同为4，公开证据只支持对流程机制的有限比较，不支持A的实际公平性状态更高。 | — | — |
| SFV2-030-T2-02 | A、B公平性私有终值相同；材料支持两边均有有限改善证据，不支持两侧实际状态值存在高低差异。 | — | — |
| SFV2-030-T3-01 | — | ambiguous；独立答案 C，可接受 ['C', 'D']，候选 C | — |
| SFV2-031-T2-01 | — | private_only；独立答案 D，可接受 ['D']，候选 A | history_independent; option_cue；盲答 D，候选 A |
| SFV2-031-T2-02 | — | private_only | history_independent; option_cue |
| SFV2-031-T3-01 | — | private_only | — |
| SFV2-031-T3-02 | — | private_only | — |
| SFV2-032-T3-02 | — | scope_mismatch | — |
| SFV2-033-T2-02 | — | private_only | — |
| SFV2-035-T2-01 | — | private_only | — |
| SFV2-035-T2-02 | — | private_only | — |
| SFV2-035-T3-01 | 两条实际分支的合作准备度都由8升至9，因此不能可靠地断言行动1在该单一变量上高于行动2；答案依赖题干所述的综合目标契合度，而非更高的合作准备度状态值。 | — | — |
| SFV2-035-T3-02 | 两条回放在第5次回应结束时的consequence_risk.institutional_harm_risk均为1，不能据此判定行动1的风险数值更低。行动1作为最佳答案只表示其前置交接留痕机制更直接匹配题设风险事件；两分支只有单次实现，不能推广为普遍概率或必然结果。 | — | — |
| SFV2-036-T2-01 | — | ；独立答案 A，可接受 ['A']，候选 C | ；盲答 A，候选 C |
| SFV2-036-T2-02 | 边界状态在两分支中同为7；选项描述的是对话呈现的范围处理差异，不能解读为A、B的boundary_assertion状态高低不同。 | — | — |
| SFV2-036-T3-01 | — | private_only | — |
| SFV2-036-T3-02 | — | private_only | — |
| SFV2-037-T1-01 | — | ；独立答案 D，可接受 ['D']，候选 A | ；盲答 D，候选 A |
| SFV2-038-T1-01 | — | — | ；盲答 A，候选 C |
| SFV2-038-T3-01 | 两行动回放的目标状态增幅相同，不能从该次样本推出行动 2 在结果上确定优于行动 1，也不能估计普遍概率；唯一最佳项依赖题干所述具体关切覆盖与审查方式。 | — | — |
| SFV2-038-T3-02 | 两分支目标变量即时变化同为增加 1，无法据实际记录认定行动 2 的公平感确定高于行动 1；单条分支回放也不能建立普遍概率排序。 | — | — |
| SFV2-039-T1-01 | — | ；独立答案 D，可接受 ['D']，候选 A | — |
| SFV2-039-T2-01 | — | ；独立答案 C，可接受 ['C']，候选 A | ；盲答 C，候选 A |
| SFV2-039-T3-01 | — | ；独立答案 D，可接受 ['D']，候选 A | — |
| SFV2-039-T3-02 | — | branch_overclaim | — |
| SFV2-040-T1-02 | — | — | ambiguous |
| SFV2-040-T3-01 | — | private_only；独立答案 A，可接受 ['A']，候选 C | ；盲答 A，候选 C |
| SFV2-040-T3-02 | 原指定的 goal_failure_risk 没有实际记录，所选机构风险变量并不等同于期限前未提交建议的专门风险。现有材料不能支持对该特定事件作精确的私有状态判断；答案D仅为最佳候选，结论不应解读为已记录的目标失败风险数值。 | private_only | — |
| SFV2-041-T2-01 | — | private_only；独立答案 D，可接受 ['D']，候选 A | ；盲答 D，候选 A |
| SFV2-041-T2-02 | — | private_only；独立答案 C，可接受 ['C']，候选 B | ；盲答 C，候选 B |
| SFV2-041-T3-02 | 延迟窗口回放未实际呈现访谈、学校联系结果或最终安置决定；因此结论只能是该条件性风险方向的最佳判断，不能据此断言事件必然发生或估计发生概率。 | branch_overclaim | — |
| SFV2-042-T1-01 | — | — | option_cue |
| SFV2-042-T1-02 | — | — | option_cue |
| SFV2-042-T2-01 | — | — | history_independent |
| SFV2-043-T1-01 | — | — | subject_mismatch |
| SFV2-043-T1-02 | — | — | subject_mismatch |
| SFV2-043-T2-01 | A、B 的 perceived_responsiveness 实际值相同（均为 5），因此若将题目解释为比较私有状态高低，则无法得到唯一答案；答案仅对应题面修订后的公开证据判断。 | — | — |
| SFV2-043-T2-02 | 两支回放的 behavioral_disposition.evidence_seeking 均为 6，角色询问未形成该状态的记录变化；若要求比较私有证据寻求状态，材料不支持唯一高低答案。 | — | — |
| SFV2-043-T3-01 | institutional_harm_risk 是对机构功能与责任履行风险的操作化记录，并非直接测量审查误判概率；不能据此断言某项审查必然判断错误或正确。 | private_only | — |
| SFV2-044-T2-01 | 回应感知在 A、B ending 后均为 8；因此本题唯一差异来自角色正当性，不能推断回应感知也有分支差异。 | — | — |
| SFV2-044-T2-02 | — | — | history_independent |
| SFV2-044-T3-02 | 所选 institutional_harm_risk 是广义机构任务风险记录，并非专门的选民排除风险变量；题面将其限定到指定迟延事件，但操作化对应仍不完全。; T3每条分支只有一条实现轨迹，答案只比较该次回放，不代表普遍概率或必然规律。 | scope_mismatch | — |
| SFV2-045-T2-01 | 两条回放的 reputational_harm_risk 结尾同为 5，不能据此断言 B 的实际私有风险等级高于 A；唯一答案来自公开安排对“未审核措辞进入转载”这一特定事件的比较。 | — | — |
| SFV2-045-T3-01 | — | — | ；盲答 D，候选 A |
| SFV2-045-T3-02 | — | — | ；盲答 D，候选 B |
| SFV2-046-T2-02 | — | — | history_independent |
| SFV2-046-T3-01 | — | — | ；盲答 B，候选 C |
| SFV2-046-T3-02 | — | — | ；盲答 A，候选 D |
| SFV2-047-T1-01 | — | — | wrong_form |
| SFV2-047-T2-01 | A、B的relationship.perceived_responsiveness私有终值相同，因此若题目要求判断数值哪一边更高，则无法唯一作答；本题按公开材料中的互动质量解释作答。 | — | — |
| SFV2-047-T2-02 | — | state_conflict; ambiguous；独立答案 D，可接受 ['D']，候选 B | — |
| SFV2-048-T1-01 | — | option_cue | — |
| SFV2-048-T2-02 | — | ；独立答案 A，可接受 ['A']，候选 D | — |
| SFV2-048-T3-02 | 该变量在两条即时回放中均由6升至7，因此若问题要求比较私有操作化数值的高低，则没有一方更高；现题保留为对可观察互动中哪项行动更直接回应推进关切的判断，不能解释为私有数值差异。 | — | — |
| SFV2-049-T2-01 | — | private_only | — |
| SFV2-049-T2-02 | — | private_only | — |
| SFV2-049-T3-01 | — | ambiguous | ；盲答 B，候选 A |
| SFV2-049-T3-02 | — | ambiguous | — |
| SFV2-050-T2-01 | — | — | history_independent; option_cue |
| SFV2-050-T2-02 | — | — | option_cue |
| SFV2-050-T3-02 | — | ；独立答案 C，可接受 ['C']，候选 D | — |
