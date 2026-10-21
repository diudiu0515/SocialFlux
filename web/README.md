# SocialFlux Annotation Studio

受邀者使用独立托管的 [匿名标注 demo](participant_demo/README.md)，支持公开材料、恢复码及持久化提交；发布与验收说明见 [操作文档](../docs/operations/ANNOTATION_DEMO.md)。

## 实验管理台

独立入口：`http://127.0.0.1:8000/lab`，沿用现有服务与 SSH 隧道。

- **实验总览**：当前批次、开发题库、四个 Gate 和下一步计划。
- **实验计划**：新增或编辑研究问题、方法、完成标准、负责人、优先级、
  日期、状态、结果指标与结论，保留修改记录；支持 CSV 导出。
- **实时结果**：读取已登记的 T4 run、E1–E9 与新版题库摘要，每 30 秒更新。
  批次单独展示，失败、移交、有效 n 和 N/A 保持原统计口径。
- **报告与数据**：自动索引 `reports/experiments/` 下的 MD、TXT、JSON、
  JSONL、CSV（含历史归档），支持搜索、来源原文、SHA-256 和文件下载；
  可导出含计划、文件索引与实时摘要的 JSON 汇总。

计划与修改历史持久化在 `data/experiment_hub/notebook.sqlite3`，不依赖
浏览器 localStorage，换浏览器仍可继续。初次使用从已有文档整理 9 项待办，
均为待开展的计划建议；不代表已经运行、人工批准或来源 Gate 通过。
并发修改使用版本号检查，旧页面不会覆盖新内容。实验状态只管理研究计划，
不会调用模型、改写原始实验结果或批准正式 GT。备份时需包含该 SQLite 文件；
服务运行中使用 SQLite backup API 制作一致备份。

报告库的收录范围在页面上明确显示，原始轨迹、视频及 provider 调用日志保留
在原目录；实时摘要沿用 `web/experiment_status.py` 的批次注册。新增批次时应
先核对协议，再登记摘要适配，不能把不同运行的结果直接混算。

验证：`python -m unittest web.tests.test_experiment_hub -v`。浏览器验证使用
`web/tests/experiment_hub_browser.cjs`，仅可对设置临时 `experiment_hub.STORE`
的测试服务运行，并传入 `LAB_TEST_URL` 与 `LAB_TEST_ISOLATED=1`。

中文字体优先使用系统字体，缺失时回退到随站点提供的 Noto Sans SC 子集
`static/fonts/socialflux-cjk.woff2`（覆盖界面与当前报告字符）。字体来自
[Google Fonts](https://github.com/google/fonts/tree/main/ofl/notosanssc)，
采用 [SIL Open Font License](static/fonts/OFL-NotoSansSC.txt)。

新版任务设计 Demo（2026-10-20）：

```text
http://127.0.0.1:8000/offline-demo
```

默认读取 `tasks/examples/offline_scenarios_v2/`：50 场景按 T1/T2/T3 各 2 题编配，
共 300 题。场景筛选显示各任务题数，也可按主要能力、普通/Hard、状态维度筛选。
先独立作答，再展开参考、反证、难度理由、API 盲试答、T2 编辑与 T3 分支。
可用 `?scene=GPT50_001` 定位场景。完整进度、来源与核验缺口见
[50 场景新版报告](../reports/experiments/2026-10-20_scenarios_v2.md)。
文字/视频配对复用原资产，缺少视频不会回退成不对应的素材；新 T2 的共同焦点
表达没有匹配音视频，新增历史编辑仍待环境回放。全部待人工审核。
2026-10-21 已按当前题目与冻结前史重新核对 270 对、45 段非语言视频，另外 30 题缺素材。
“配对材料”显示实际覆盖的历史轮次和未覆盖位置；T2 明确显示 A/B 共用前史视频，
共同结尾仍为文字。运行 `python -m scripts.match_offline_multimodal` 可独立刷新配对和
评测抽帧清单，保留题目与参考答案。详见离线 v2 协议的“多模态与统计”。
原 24 道题型示例改由 `?bank=design-v2` 查看，旧 460 题移入历史批次。
完整设计见 [离线 v2 协议](../docs/protocols/OFFLINE_T1_T3_CHOICE_V2.md)。

旧题 API 适配结果见 `/offline-review?bank=dev60` 和 `?bank=gpt50-t1-t3`，
使用“新版适配”筛选原题保留、轻改、重写或只复用材料；按题目 SHA 绑定，题目修改后
旧复核不会继续套用。参考区显示模型依据及助手核对出的争议，均不自动变成人工批准。
完整进度与方法见 [旧题迁移核验](../reports/experiments/2026-10-20_legacy_task_migration.md)。

Offline T1–T3 开发题标注入口：

```text
http://127.0.0.1:8000/offline-review
```

台词视频小批预览入口：`http://127.0.0.1:8000/offline-talking-preview`。
当前仅选择 GPT50_001–008，共 24 个公开说话节点、37 个分段。预览清单绑定
新版题库 SHA；页面只显示选中节点、原文和已校验视频。原人物参考 URL 过期且
截帧被供应商人像规则拒绝，本批以全新虚构人物建立场景内一致性，不宣称与旧版
演员一致。人工作品审核保持 pending；本地 ASR 只筛查转写差异，不自动批准素材。

只运行已选预览范围：

```bash
python -m offline.talking_head --phase run --preview --submit-new --workers 4 \
  --manifest data/offline_talking_head_v1/c1d1f3fd60e94e0c/manifest.json
```

八场景预览不调用 `publish`，不会扩展到其余 42 个场景。

默认同样使用新版 50 场景题库。历史 `?bank=gpt50-t1-t3` 读取
`data/offline_gpt50_t1_t3/items.jsonl`，原 60 题用 `?bank=dev60` 进入。
页面显示实际题数与缺项；新增题目生成时刷新即可继续检查。
入口也在 `/gpt50` 和 `/gpt50-live` 导航中。
支持任务、四维 state、单维／组合、标注进度筛选，以及按题号或场景搜索。
可用 `/offline-review#SFV2-010-T1-01` 直接打开新版题；旧 `#SFO-005` 与 `#SFG50-010-T1-01` 书签仍选择原题库。

默认只读取模型可见材料；点击“查看参考答案与来源”才请求作者参考、原始 scenario、
相关 state、T2 改写位置和 T3 未来分支。原始 source 路径与 SHA 必须匹配才会展示；
接口不传出 provider 原始请求、调用日志或运行快照。参考答案仍待人工审核，
原 60 题中 4 道未完成 T3 回放会显示为开发候选，新批次完整分支才计入生成进度。文字／视频模式复用已配对资产，视频绑定
历史证据 ID，并检查文件 SHA；T2 视频只对应共同前缀，不充当共同 ending。

标注内容包括个人答案、其他可接受选项、证据 ID、四项质量判断、题目审核意见及
修改建议。草稿保存在当前浏览器；完成标注须填标注人，导出保留题库 SHA、逐题
SHA、标注人及查看参考的记录。导入严格匹配版本，保留未涉及的本地题目；已查看
参考的题目不能通过旧导入恢复成盲标。网页不调用模型，也不自动写入正式 GT 或
放行来源 Gate。导出的 `socialflux_offline_choice_annotations_v1` 是待汇总的人工
审核记录，不能直接作为 `offline-eval --responses` 的模型回答文件。

当前默认页面是 GPT 小规模实验的人工 Gate 1：

```text
http://127.0.0.1:8000/gpt50
```

它展示完整 scenario、角色、关键历史、initial state、runtime dynamics seed、trigger 与 schema 状态，并导出绑定 scenario SHA-256 的人工审核草稿。Gate 1 只人工冻结 initial state，runtime dynamics seed 由机器合同校验；通过后每个场景只生成一条 rollout。

当前在线多模态有效批次的视频审核页：

```text
http://127.0.0.1:8000/multimodal
```

`/gpt50-live` 的场景详情已内嵌只读多模态播放器，沿用浅绿主题。
支持状态表达／语音口型筛选、有声播放，以及所选轨迹的原始触发证据。
视频不会自动播放，不叠加字幕；非语言素材没有台词。
素材预览不等于轨迹实际触发：状态素材只按同场景、精确素材 ID 关联；
口型视频还须匹配轨迹 ID、轮次及回复正文。缺少对应视频时明确显示待补。
触发记录来自原始 rollout，即使正文正在展示英文翻译也不会用翻译结果替换事件。
此入口不生成新素材、不调用模型、不更改 policy 输入，也不自动批准人工审核。

旧 Qwen rollout 和旧 Scale300 场景不在活跃目录。已被现有路由替代的旧
index/review/scale150/scale300_tasks/t2_dev_review 页面及专用 app.js 已删除；
旧 URL 仍映射到 GPT50 工作台，统一由 `web/server.py` 的页面注册表管理。
仍可直接访问的 `task_examples.html` 及其 styles.css 保留用于旧示例协议复现。
旧 Talking Head manifest 与当前 GPT50/Claude150 多模态批次相互独立；旧清单
为空不代表当前批次没有视频。接口没有对应数据时返回空集，不把旧结果当作当前候选。

浏览器记录仅保存在 localStorage，不写仓库，也不构成真人签名、Gate 通过或 human GT。正式 Gate 4 仍要求两人独立审核同一确定性样本，只有分歧项进入仲裁。

## 启动

日常使用仓库内的 Supervisor 配置，网站进程异常退出后自动重启。
首次准备独立管理环境（不会修改模型任务的 Python 依赖）：

```bash
mkdir -p build/web-service
python -m venv --system-site-packages build/web-service/venv
build/web-service/venv/bin/python -m pip install -r configs/web-service.requirements.txt
```

启动前用 `status` 确认没有已运行的实例，不要重复启动 daemon：

```bash
build/web-service/venv/bin/python -m supervisor.supervisorctl -c configs/web.supervisord.conf status
build/web-service/venv/bin/python -m supervisor.supervisord -c configs/web.supervisord.conf
```

管理已启动的网站：

```bash
build/web-service/venv/bin/python -m supervisor.supervisorctl -c configs/web.supervisord.conf restart socialflux-web
build/web-service/venv/bin/python -m supervisor.supervisorctl -c configs/web.supervisord.conf stop socialflux-web
```

日志、PID、控制 socket 和管理环境统一放在 Git 忽略的 `build/web-service/`。
管理 socket 仅允许当前用户访问；网站仍只监听 `127.0.0.1:8000`，远程访问
继续使用原有 SSH 端口转发。该配置负责进程退出后的恢复；容器重启后仍需执行
启动命令。

临时前台调试仍用 `python -m web.server --host 127.0.0.1 --port 8000`，
先停止托管实例以免争用端口。

远程访问：

```bash
ssh -p 22 -L 8000:127.0.0.1:8000 root@SERVER_IP
```

保持隧道终端开启，然后在本机浏览器打开 `http://127.0.0.1:8000/gpt50`。

## 验证

```bash
python -m unittest discover -s web/tests -v
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/gpt50-review
```
# 四个 Gate 与实验结果

`/experiments` 每 30 秒读取当前 Gate2/Gate3、新版题库和独立 T4 run 的实际摘要。
`/api/experiment-status` 只返回白名单统计、来源路径及哈希，不返回轨迹、私有状态或调用消息。
页面保留失败、未送达视频、不支持视频及移交槽位；逐维显示有效 n，恢复 N/A 不补零，
五维完整子集与配对差值分开。旧 Gate2 和历史 T4 只在独立折叠区展示。
`python -m scripts.publish_experiment_status` 生成同源报告快照，不调用模型。

# 人类盲答与上帝视角 GT

`/offline-annotation` 提供独立采集流程：完整场景组盲答锁定、私有证据独立初判、机器建议、最终人工审核。记录保存在 `data/human_annotations/sessions/`，会话码保存在当前浏览器，可刷新继续和导出。此目录含制作侧信息与人工记录，不通过静态文件服务公开。

文字条件使用与模型完全相同的 `public_instance`。服务器强制整组解锁和不可覆盖提交；身份为本地自报 ID。`web.annotation_sessions.human_results()` 提供独立人类一致标签与排除本人标签后的基线分数。机器候选、人工 GT 与正式来源准入分开记录。

可重复检查：`python -m unittest web.tests.test_annotation_sessions tests.test_offline_oracle`；浏览器流程见 `web/tests/offline_annotation_browser.cjs`，须使用临时 `STORE` 的测试服务，避免测试记录污染真实标注。
