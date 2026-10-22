# Source Design Notes

这些文件是需求和修订的原始输入，保留用于论文设计追溯，不是运行时 Prompt，也不是单独的完成声明。

- `benchmark-outline.md`：最初的 benchmark 需求草案，原先散落于仓库根目录。
- `assets/project-reference.png`：原始项目参考图；不作为网站运行时资产。

- `revision.md`：自由 rollout、统一环境与 rollout-derived task 的架构修订来源。
- `prompt_check.md`：Prompt 结构、职责和信息边界检查来源；部分旧 controlled-policy 建议已被 revision 取代。
- `talkinghead_generation.md`：state-triggered Talking Head 接入框架的历史设计来源；旧本地实现与资产已删除。
- `multimodel.md`：2026-09-08 新增的三事件 multimodal prompt 方案。最高优先级事件和单轮最多一个视频的 runtime 语义已进入环境；旧本地资产已删除，因此整体状态为 **framework only / external API pending**。在新 provider、资产和完整测试接入前不得称为已实现多模态评测。
