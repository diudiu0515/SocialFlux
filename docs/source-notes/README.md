# Source Design Notes

这些文件是需求和修订的原始输入，保留用于论文设计追溯，不是运行时 Prompt，也不是单独的完成声明。

- `revision.md`：自由 rollout、统一环境与 rollout-derived task 的架构修订来源。
- `prompt_check.md`：Prompt 结构、职责和信息边界检查来源；部分旧 controlled-policy 建议已被 revision 取代。
- `talkinghead_generation.md`：当前两条 state-triggered Talking Head 资产实现的设计来源。
- `multimodel.md`：2026-09-08 新增的三事件 multimodal prompt 方案。最高优先级事件和单轮最多一个视频的 runtime 语义已进入环境；但 scenario/schema/资产仍为每场景两条视频，因此整体状态为 **partially integrated proposal**。在 20 个 scenario 配置、文档、三事件资产和完整测试迁移前不得称为全部实现。
