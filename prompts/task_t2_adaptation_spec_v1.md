# SocialFlux T2 Controlled Adaptation Specification v1

从一条已经通过来源筛选的真实 rollout A 中选择一个受控历史改编窗口。

只能选择 candidate_windows 中给出的 fork/ending 组合。History B 必须保留：
- 人物身份、社会关系与公开背景；
- fork 前的完整共同历史；
- 已经成立的公开事实；
- 公开时间线和制度边界。

只能改写 fork（含）到 ending（不含）之间一段会影响情绪、动机或关系理解的公开经历。不得新增分叉前往事、区间外事件、隐藏背景、制度、权力、关键证据或已经完成的行动。改编点必须由 source_anchor_evidence 锚定到所选区间内真实发生的台词；只返回轮次和说话人，caller 会附加原文。

ending 的行动、回复、可观察表达和媒体随后会从 A 原样复用。history_b_direction 必须解释怎样使同一 ending 在 B 中仍然自然，但本阶段不要编写 B 的逐轮台词。

候选窗口不跨公开时间或事件边界，视为同一次接触。新提出的未来期限不能在相邻轮次自动变成已经到期、履约或违约。protected_facts 只列必须保持不变的已成立公开事实。shared_ending_behavior 只能描述两侧共享的客观可见或可听表现，不能输出隐藏状态或心理解释。

只返回以下 JSON 结构，不增加字段：

{{output_schema_json}}

公开材料：

{{payload_json}}
