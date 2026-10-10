# 独立逐变量 state appraisal：有边界修复结论

状态：**未通过正式 rollout 回归门禁；停止新增版本、holdout、六条轨迹与批量生成。**

本轮 appraisal 实际使用 `gpt-6-astra`、`reasoning_effort=low`、固定采样与既有 calibration v6。Fable 仅存在于候选 rollout 的环境 response 路由；本轮固定集验证没有调用 response，因此本轮失败不能归因于 Fable appraiser。

## 修改清单

- Provider 完整性：保存无密钥的完整实际请求、原始输出、finish reason 与 usage；`max_tokens`、截断、解析/结构失败显式记为调用失败，不再静默转为空候选。
- Calibration v6：先完成候选资格判定，再计算强事件预算和选择；不合格候选不占位；排序不使用变量名；只有决定性的 `cross_turn_slow` 证据优先于普通即时证据。诊断保存原始候选、资格理由、排序、选择/排除原因和最终 delta，阈值、幅度与预算未变。
- 职责拆分：state appraisal 与 interaction appraisal 读取同一更新前快照并行执行；Python 合并 ledger、验证候选并只更新一次；response 在更新后独立生成。
- 逐变量 state appraisal：场景全部 state/dynamics 变量逐项返回四类判断、方向、原文、directness、feature 与变量特定依据；普通新增证据可以被识别而不立即更新。
- 确定性回放：保存历史基线与 002/003/026/030 四个 checkpoint；scenario 003 的已保存 trust 候选在 v6 回放中为 rank 1、eligible、selected、`moderate_increase`，不需要新 API 请求。
- 唯一修正 v2：修复 `build_state_semantics()` 的嵌套 `variables` 查表，合法 feature 从误报 mismatch 恢复为 `valid`；新增统一的“当前已完成行为 vs 未来履行”及 repeated 标签一致性原则，无 scenario 编号、目标答案或单句例外。

## 固定小集对照

预注册固定集为 8 例：002/003/026/030 各含正例和重复/相邻负例；标签在调用前冻结，人工确认仍为 pending。所有固定集和边界调用均完整，无截断或调用失败。

| 方案 | 变量识别 | 证据强度 | 最终更新 | 调用完整性 | 预定边界全四项通过 |
|---|---:|---:|---:|---:|---:|
| 综合 Astra v36（原始运行） | 5/8 | 4/8 | 5/8 | 8/8 | — |
| 独立逐变量 v1 | 3/8 | 5/8 | 5/8 | 8/8 | 3/4 |
| 综合 Astra v36（修正版同批对照） | 6/8 | 5/8 | 5/8 | 8/8 | — |
| 独立逐变量 v2（唯一修正） | 2/8 | 4/8 | 5/8 | 8/8 | 2/4 |

独立逐变量逐例结果：

| 样例 | 冻结期望 | v1 | v2 | 结论 |
|---|---|---|---|---|
| 002 trust 正例 | decisive，非零更新 | no relevant，similar | no relevant，similar | 两版失败 |
| 002 trust 负例 | no relevant，similar | repeated，similar | repeated，similar | 不更新正确，细分类别失败 |
| 003 trust 正例 | decisive，非零更新 | ordinary，feature 误报，similar | ordinary，feature valid，similar | 工程接口修好；强度与更新仍失败 |
| 003 trust 重复负例 | repeated，similar | no relevant，similar | no relevant，similar | 不更新正确，细分类别失败 |
| 026 fairness 正例 | decisive，非零更新 | ordinary，feature 误报，similar | ordinary，feature valid，similar | 工程接口修好；强度与更新仍失败 |
| 026 fairness 相邻负例 | no relevant，similar | 通过 | 通过 | 稳定通过 |
| 030 safety 普通正例 | ordinary，similar | 通过但 feature 误报 | 通过且 feature valid | v2 完整通过 |
| 030 safety 相邻负例 | no relevant，similar | 通过 | ordinary decrease，similar | v2 新增语义误识别；预算阻止了错误更新 |

## 六条轨迹及审核入口

六条完整候选**未生成**。原因不是测试数量不足，而是唯一修正版仍未通过既有语义回归，并新增 030 safety 相邻负例误识别。按预先约定，未进入新 holdout、版本冻结、GPT/Claude 各三条轨迹或批量 rollout。

人工核验入口：

- 标签、原文、前史与依据：`data/gpt50/experiment/state_v3_validation/v3227_independent_per_variable/fixed_set_preregistration.json`
- v1 完整请求、原始输出、配置、逐例结果与边界复测：`data/gpt50/experiment/state_v3_validation/v3227_independent_per_variable/fixed_set_results.json`
- v2 唯一修正版完整证据：`data/gpt50/experiment/state_v3_validation/v3227_independent_per_variable/fixed_set_correction_results.json`
- 历史基线归档：`data/gpt50/experiment/state_v3_validation/v3227_independent_per_variable/baseline_archive.json`
- calibration v6 无 API 回放：`data/gpt50/experiment/state_v3_validation/v3227_independent_per_variable/deterministic_replay_v6.json`

关键 SHA-256：

- 预注册：`798c87842b14d722d5845302f010ba529ae64b18922f1bc28270836054212c2f`
- v1 结果：`81854afe649e56e35f641910c0c8682566c759f059da184a1a32928a483afeea`
- v2 结果：`dac4e0f937421b3f3fa44d2ee1a2bed5df3afd6c378bea0f6c4acedc6a39a2ae`

## 剩余问题

- Astra 对 002 的关系主体/对象出现偏差：把 evaluated agent 接受安排误写成不能证明 environment agent 的可靠性。
- Astra 持续把 003 的已完成代价性坦诚、026 的当前程序性发声权判为普通证据，未达到冻结的 decisive 标签。
- `no_relevant_evidence` 与 `repeated_evidence_only` 不稳定；同一 003 负例在 v1 固定运行与预定复测间发生漂移，v2 仍未稳定。
- v2 对 030 信息确认产生 safety 普通下降误识别，虽被慢变量更新门槛阻止，但变量识别与证据强度不可靠。
- 历史旧 runner 未保存实际序列化请求和 raw output；基线归档中的这些部分只能从冻结源、prompt 和 builder 重建并明确标记，不能冒充历史原件。
- 标签仍需人工确认，尤其是 002/003 的 no-vs-repeated 边界及 002/003/026 的 decisive 标准；在人工确认与新的、独立设计变更前，不应恢复 rollout。
- 无 API 回归 137/137 通过；完整 prompt catalog 另有一个与本轮无关的未登记文件 `talking_head_generation_v4.md`，因此 catalog 全量检查仍报 1 个工作区既有失败，本轮未擅自修改该多模态资产。
