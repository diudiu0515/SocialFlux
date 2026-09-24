# SocialFlux T2 Controlled History-B Authoring v1

一次性编写完整的 History B 分叉段，不要把 policy 和 environment 分成彼此独立的生成任务。

History B 与 rollout A 必须共享人物、背景、fork 前历史、protected_facts、时间线和给定 shared ending，只改写 adaptation_point 指定的关键经历。两个人都要依据前文自然回应；可以出现克制、误解、澄清、拒绝或有限让步，但不能逐轮套用固定节奏。

不得为了制造差异而新增制度、证据、权力、关键外部事件或已经完成的行动，不得替对方执行动作。必须区分提案、承诺、行为报告和可核验结果。分叉段属于同一次接触；不能让新提出的未来期限在相邻轮次自动到达，也不能把尚未到期的承诺写成已经履约或违约。

给定 shared ending 必须在 A/B 两侧都自然，但不得在分叉段提前复述或改写 ending。不得把隐藏状态、构造说明或 benchmark 标签写入人物台词。必须严格保持给定 turn ID、轮数和双说话人结构。

只返回以下 JSON 结构，不增加字段：

{{output_schema_json}}

受控改编材料：

{{payload_json}}
