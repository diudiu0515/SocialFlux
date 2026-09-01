# Shared Story Specifications

这里保存所有 world 共用的创作层约束：Story Schema、统一状态词表和故事生成 Prompt。模型输出与标注约束统一位于根目录 `tasks/`。


当前 stateful pipeline 的新 scenario 生成应使用 `prompts/scenario_generation_v1.md`。模型输出 canonical JSON；保存后由 `scripts/scenario_docs.py` 生成同名自然语言 Markdown 和 manifest。旧 Story World prompt 仅用于 legacy interactive-world 格式。
