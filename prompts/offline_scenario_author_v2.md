你为 SocialFlux-Eval 新版按场景编写题目。只输出 JSON，不要代码围栏。材料全是合成公开材料；没有私有状态、未来分支或人工答案。沿用给定人物、背景和已发生事实，不虚构履约、认可或新外部事件。人物内在状态可以由公开证据合理推断，不要把题目改成单纯检索行为。

每批同一场景同一任务恰好两题，判断目标须不同。可参考旧题及其机器问题清单，合适内容可保留，不合适的重写；旧题与机器审核都可能错。所有答案只是作者建议，不得声称人工通过。

本批所有题的状态主体只能是 public_input.target_character（环境人物），关系对象为 public_input.role（行动角色）。题干不得反过来测量行动角色的状态。每题返回 state_owner=该环境人物 character_id 与 state_target=行动角色 character_id；题干中状态主体使用环境人物姓名。evidence_support 必须让选项列出四个具体证据片段并比较支持力，不能把普通状态判断仅换名为证据题。原始行动角色说了什么，可作为判断环境人物状态的证据，但不能把行动角色的状态写进目标变量。

共享能力：situational_evidence_integration（整合情境证据）、multidimensional_state_distinction（区分不同步状态）、temporal_dynamics_reasoning（跨时积累/保持/修复/影响）。每题一个主要能力，辅助可空。状态变量是判断对象，使用给定 ontology 名称。按材料挑变量，不强迫每题四维。

T1：只判断 t2 结束的当前状态或 t1 至 t2 的变化。subtype 从 current_state、interval_change、evidence_support、state_combination 选。题干写清状态主体、关系对象；变化写明 t1/t2；风险写清风险事件及现有安排下的范围。不得比较新行动。强/很强不能区分时改写；基本不变要有持续要求等正面证据，不等于证据不足。两题优先覆盖建议题型，但材料不支持可选择其他形式。

T2：比较 History A/B，背景、人物、外部条件和共同表达必须相同。已有 paired_input 时直接使用，不做编辑。否则 history_a 从给定 history 复制，只把 t2 的人物回应和表达移到共同 ending；A:t2 的 evaluated_agent 原文不变。你只编辑 B:t2 的 evaluated_agent，改变一个互动因素（如回应关切/施压、信息披露/隐瞒、承担/转嫁），不能改变患者状况、截止时间、资源、既往履约或实际外部事实。编辑必须是合理可说的话，不故意制造愚蠢或极端对比。共同 ending 为两侧都自然成立、尚可继续协商的简短回应，表情/语气中性并完全一致，不宣布任何一侧已实现目标。返回 history_edit={factor,b_action,shared_response,shared_expression:{facial_expression,prosody,behavioral_cues},rationale}。这是受控改写，尚未回放，不能伪称已验证。
T2 两题从 history_comparison、expression_meaning、joint_comparison、history_evidence 选；至少一题需要具体 A/B 差异，另一题可整合早期与近期证据。不能只看 ending 就选对，干扰项也要用真实历史。允许部分状态相近，不能为制造差异而强推不同。evidence_ids 可用 context,A:t1,A:t2,B:t1,B:t2,ending；每题必须引用 A/B 两侧，表达解释还须引用 ending。

T3：candidate_actions 不得改动，固定共同 t2 起点、人物及外部条件。第一题 subtype=action_selection，给定明确可评估目标，选择更可能实现该目标的行动。第二题 subtype=consequence_explanation，预测即时、延迟或跨时后果。行动写“行动 1/行动 2”，答案写 A/B/C/D。immediate 是行动及下一次环境回应后；delayed 是含该即时回应的五轮末，最多十轮。题干必须明确时间和相对 t2 还是另一行动。优先关注行动造成的风险通道、关切回应、合作边界等可推断机制，不武断预测遥远情绪。分支材料仅在本地核验，不出现在此请求；不要假装看过分支。概率措辞而非必然。多维后果可分情绪/信任、合作/风险。不得把承诺当履约。若建议窗口难以支持，选择更有依据的即时题。

所有题四选一。选项具体程度、长度、语气接近；每个错项有局部合理性，不能三个绝对短句配一个谨慎长正确项；题干中立，不先提示正确理论。单维也可 hard，多维也可 ordinary。hard 必须给具体难度依据。不要把所有题都设为 hard，也不要默认状态都不同步。不得为了好猜而把正确项限定为“现有证据不足”；材料适合时优先明确可证实的判断。

输出结构：
{"history_edit":仅新T2需要的对象或null,"questions":[两项]}
每题字段：
{"subtype":"...","question":"中文题干，保留人物原名","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"B","target_state_ids":["relationship.trust"],"time_scope":"明确范围","risk_event":"风险题必填，否则空","risk_window":"风险题必填，否则空","comparison_interval":{"start":"t1:after_environment_response","end":"t2:after_environment_response"},"horizon":"仅T3:immediate|delayed|immediate_delayed","comparison":{"kind":"pre_action|between_actions","action_ids":["action_1","action_2"]},"goal":"选择行动题必填的明确目标","evidence_ids":["context","t1","t2"],"counterevidence_ids":[],"rationale":"100字内，具体支持与限制，不复述正确项","option_errors":{"A":"history_ignored","C":"state_dimension_confusion","D":"unsupported_inference"},"option_variable_map":{"A":{"relationship.trust":"判断短标签"},"B":{"relationship.trust":"判断短标签"},"C":{"relationship.trust":"判断短标签"},"D":{"relationship.trust":"判断短标签"}},"primary_capability":"...","auxiliary_capabilities":[],"design_difficulty":"ordinary|hard","difficulty_reason":"hard必填","based_on":["旧题ID，可空"]}
非当前任务字段可省略。option_errors 只含三个错误选项，值限 history_ignored、expression_as_state、state_dimension_confusion、promise_as_fulfillment、immediate_delayed_confusion、actor_reversal、goal_constraint_ignored、unsupported_inference。每个选项的变量坐标须完全一致，覆盖 target_state_ids；跨时可用 state@immediate/state@delayed。T1/T3证据仅可引 context,t1,t2 及 T3 的 action_1/action_2。不要复制材料进输出。总输出保持紧凑。
