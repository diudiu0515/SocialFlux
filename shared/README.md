# Shared Ontology

`STATE_ONTOLOGY_v2.md` 是 SocialFlux 当前 Persona/State/Dynamics 的唯一事实源：私有稳定 Persona；emotion、behavioral_disposition、relationship、consequence_risk 四维动态 state；以及独立的外部 interaction dynamics。

所有固定模型指令已经集中到 `prompts/`。本目录不再保存 prompt 兼容副本，避免出现第二个事实源。

`artifacts.py` 提供跨模块共用的 JSON 原子写入和规范 JSON 内容哈希。
这些函数不依赖任务、实验脚本或 provider，也不改变既有文件格式。
同一目标文件的并发写入仍由调用方同步；文件字节哈希与 JSON 内容哈希不能混用。
