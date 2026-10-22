# SocialFlux-Eval T1–T3 设计落实 · 2026-10-20

已在现有网站接入 [新版 Demo](http://127.0.0.1:8000/offline-demo)，原 `/offline-review` 仍可切换旧批次。新页可按任务、主要能力、状态维度和设计难度筛选；试答只选择一个选项并显示 `{"answer":"B"}`。人工审核表单可选展开，作者答案、反证、Hard 理由、T2 编辑和 T3 分支按需加载。

- [任务边界、生成模板与字段协议](../../docs/protocols/OFFLINE_T1_T3_CHOICE_V2.md)
- [24 道完整示例](../../tasks/examples/offline_design_v2/examples.md)，T1/T2/T3 各 8 道，每个任务覆盖四维；9 普通、15 Hard，A/B/C/D 各 6 道。
- [三组字段 JSONL](../../tasks/examples/offline_design_v2/records.jsonl)与[被测输入 JSONL](../../tasks/examples/offline_design_v2/public.jsonl)。运行器兼容格式仍为 [items.jsonl](../../tasks/examples/offline_design_v2/items.jsonl)。
- [旧题结构筛查](../../tasks/examples/offline_design_v2/legacy_reuse_audit.json)：460 道中，11 道原题用于 12 道新版改写，378 道是补标签后再审核的候选，67 道需重写，4 道需补分支证据。此为早期助手结构筛查，不是逐题语义批准；后续实际 API 对新版任务设计的逐题核验见 [旧题迁移报告](2026-10-20_legacy_task_migration.md)，不得把 378 道直接视为可保留题。

12 道新版改写题的原场景、轨迹及对应受控回放在当前工作区均通过 SHA 核对；12 道老师／小陈的受控写作示例没有被包装成真实环境 rollout。它们的 T2 状态核验、T3 分支证据以及所有题目的人工审核仍待完成。未更改旧题快照或重计旧成绩，所有新版 `ground_truth=null`，正式模式全部拒绝。

旧材料改写题保留 12 对文字／文字+视频条件，答案一致。T2 只复用共同前史视频，共同焦点表达仍是同一份文字记录；本批没有共同焦点音视频或新课堂视频。上述 24 题的确定性构建没有新增模型调用或媒体生成，也未声称实测能力提升；后续旧题 API 适配核验单独记录在迁移报告中。

验证结果：

- 61 项针对性 Python 测试通过，覆盖新合同、460 道旧题兼容、输入隔离、回放窗口、配对一致性、评分分组与网站数据接口。
- 24 道题均通过 Python 合同和 JSON Schema；`offline-eval --check-only` 验证 24 道，provider 调用为 0。
- 新版 Demo 和原 60 题审核页的实际 Chromium 检查通过：筛选、T2 单份共同表达、数字行动编号、最小回答显示、草稿保存刷新、参考隔离、视频播放／字节范围、原页导入导出及手机布局。
- 现有 Supervisor 网站服务已启动，监听 `127.0.0.1:8000`，可沿用原 SSH 端口转发。

设计难度与模型实测难度分开保存，当前实测难度均为 null。这里的验证结果是实现与数据结构检查，不是 benchmark 模型成绩。
