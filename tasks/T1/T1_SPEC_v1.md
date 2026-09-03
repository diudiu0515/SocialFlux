# T1 Specification v1

输入来自 `build_t1_checkpoints`：目标角色、完整可观察历史与自然轨迹当前 checkpoint。禁止 private state、hidden intention、appraisal、delta、trigger conditions、未来内容和 source metadata。

被测模型为每个 target state 输出 intensity/change 概率、observable evidence IDs 与 calibrated confidence，合同为 `schemas/task_t1_output.schema.json`。人类标注员独立判断；未完成三人标注与 adjudication 前，`ground_truth=null`。正式采样应跨 scenario、state family、intensity 和 trajectory depth 平衡。
