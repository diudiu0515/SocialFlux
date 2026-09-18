# T2 历史差异与表达不一致开发批次

日期：2026-09-16。范围：4 组开发配对；未启动全量生成。
本报告中的“完整阅读复核”是 Codex 模型语义复核，不是人工验收。

## 本轮实现

- 保留 `共享前史 → History A/B → 字节一致 ending`，两侧分别经过 Appraisal → Python 确定性更新 → Response；没有增加第三个环境 LLM 阶段。
- Response v24 在同一次调用中输出私有表达意图与公开可观察行为；受控 ending 的台词、行为及未来媒体引用必须一致。
- T2 只询问正式更新后实际产生差异的少量、场景已批准变量；这一步选择问题，不手工指定比较答案。
- LLM 答案证据改为 `turn_id + target_quote + interpretation`，程序要求引文逐字来自该侧 `environment_character`，从结构上阻止说话人混淆。

## 实际请求与生成结果

| Scenario | 关系 | 历史轮次 | 结束 | 实际请求 | 媒体 |
|---|---|---:|---|---:|---|
| IA_PIPE_011 | 职场上下级 | A/B 各 5 + 共同 t6 | 受控 T2 ending | 30（含最后 4 次失败答案请求） | 未生成 |
| IA_PIPE_012 | 分居伴侣与共同照护 | A/B 各 5 + 共同 t6 | 受控 T2 ending | 27 | 未生成 |
| IA_PIPE_014 | 手足与共同董事 | A/B 各 5 + 共同 t6 | 受控 T2 ending | 29 | 未生成 |
| IA_PIPE_020 | 职业督导与初级律师 | A/B 各 5 + 共同 t6 | 受控 T2 ending | 28 | 未生成 |

请求数包括环境 Appraisal/Response 的实际重试、初始答案/Judge、答案修订/Judge；不是“每轮固定两次”的名义计数。

## 分层复核结论

| Scenario | 程序/模型结果 | 完整阅读结论 | 具体原因 |
|---|---|---|---|
| IA_PIPE_011 | 新证据结构 4 次失败 | reject | 答案持续引用非目标人物；A t5 还把助理承担的执行动作写成总监执行。保留失败证据，未用旧答案冒充成功。 |
| IA_PIPE_012 | 程序方向一致；Judge approve | needs_revision | `compromise_readiness: A>B` 的双侧证据成立；但表达解释把 A t5 的“我接受这个条件”误称为 A/B 共享 ending。 |
| IA_PIPE_014 | 引文合法；Judge approve；方向不一致 | needs_revision | 配对本身自然且可用；B t5 明确把无保障的权力转移称为风险，LLM 却回答治理失败风险 A>B。Judge 误放行。 |
| IA_PIPE_020 | 引文合法；Judge needs_revision | reject | B t3 与 t5 逐字重复、没有吸收新信息；答案四方向均 0.25，rationale 又偏向 A，结论内部不一致。 |

人工验收仍全部 pending；program check、LLM Judge 与 Codex 阅读均未被记为人工 GT。

## 当前最好样例

IA_PIPE_012 的核心比较最接近可用：目标人物周航在 A 中接受可逆试行、复盘和条件约束，在 B 中更强调先行动与责任分担；共同 ending 都是“先把这周的接送和联系时间定下来，长期安排仍然保留”。
后台更新为 `motivation.compromise_readiness: A=7, B=4`，LLM 回答 A 更高（0.70），并分别引用 A t3/t5 与 B t4/t5 的目标人物原话。
它可构造 T2 状态差异、双侧证据、关键事件及表达功能题；但表达解释子项需修订后才可成为完整优秀例子。
完整 A/B 每轮正文、共同 ending、状态、表达意图、题目和答案见下列 pair JSON 与网页，不在报告中截断。

## 多模态状态

本批媒体均未生成，也没有开展 text/text+video 消融或实际音视频核验；不能据此声称视觉增益。后续生成时 A/B 必须引用同一资产。

## 是否值得扩展

受控配对机制与角色安全证据结构值得保留，但当前不应扩到全量：环境自然度与答案/Judge 可靠性尚未跨关系稳定。
下一步最有信息量的是修正 IA012 的共享表达解释、重新回答 IA014，并用一个不同模型对照 IA011 的角色引用失败；不应继续增加在线对话硬规则。

## 可追溯产物

- `build/t2_expression_dev_v1/pair_*.json`：完整公开历史、后台状态、表达意图、答案、请求数与版本。
- `build/t2_expression_dev_v1/codex_semantic_reviews.json`：逐组完整阅读结论与具体轮次。
