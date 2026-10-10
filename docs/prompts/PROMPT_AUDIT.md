# SocialFlux Prompt 审计

2026-10-10 按已确认的调用链删除 39 份被替代的模板，Markdown 注册项从 89
减少到 50。保留的 50 份正文及两个注入规则文件均未改写。
实际链路、各模板用途和兼容入口统一见 [运行时目录](RUNTIME_PROMPT_CATALOG.md)。

## 已删除内容

| 类别 | 撤下版本 | 数量 |
|---|---|---:|
| Combined appraisal 中间实验 | v13–v21（含 v15 environment-owned）、v23–v35 | 23 |
| Response 中间实验 | v26、v27、v27 decision-continuity、v28–v30 | 6 |
| Independent state 中间实验 | v2–v5 | 4 |
| Online 非语言生成旧版 | v1、v2 | 2 |
| Talking-head 旧版 | v1、v2、v3 delivery | 3 |
| 公开台词压缩旧版 | v1 | 1 |

完整 ID、原路径和 SHA 保存于 `prompts/retired.json`，其中不保存 prompt 正文。
`prompts/manifest.json` 只注册仍可调用的模板。loader 区分 retired 与 unknown；
环境 factory 在创建 provider 前检查实际调用的模板，引用已撤下版本时明确报错。
不会用新 prompt 冒充旧 prompt，也不会自动从归档加载。

同步删除了 16 个只检查这些旧模板措辞的测试方法；历史 state-transition 合同、
结构校验和旧 provenance 读取测试继续保留。生成入口的质量指纹已移除对已删
文件的依赖，并纳入当前独立判断模板与注入规则。新指纹不等于旧实验指纹。

## 历史配置与恢复

56 份历史配置仍引用已撤下的模板，保留它们是为了说明历史结果如何产生，
它们现在不能直接发起对应旧模型调用。当前 offline 配置及文档列出的兼容入口
继续使用保留的模板。不要通过批量替换旧配置中的 ID 来恢复执行。

本地恢复包为 `archives/prompt-cleanup-2026-10-10/before_cleanup.tar.gz`，
清单为同目录的 `manifest.json`。它们不参与运行时加载，也不提交为第二套 prompt
源码。修改前的全部模板、注册表、相关代码与文档都在包中；需要历史复现时，应在
独立工作目录恢复匹配的配置、代码、模板及原始注册表，并核对各自的冻结哈希。

当前资料中有 6 份预注册记录绑定了已删除的文件。其 SHA 和历史结果没有回写；
旧冻结批次不能在清理后的源码上宣称代码未变。恢复包只提供本次清理前的副本，
不保证该副本就是每个更早实验的完整代码快照。`prompts/manifest.json.orig`
仍作为已有冻结记录的输入保留，它不是运行时注册表，也不能用于启动新调用。

## 验证记录

`build/prompt_cleanup_20261010/` 保存删除计划、逐 ID 引用扫描、受影响历史配置、
冻结记录影响以及测试结果。检查覆盖：注册表重建、当前统一环境、人物方向绑定、
旧协议兼容、回放入口、offline 选择题和网站标注。保留模板的 SHA 与清理前逐一
一致；题库、源 rollout、视频和人工标注没有因本次清理而重建。
