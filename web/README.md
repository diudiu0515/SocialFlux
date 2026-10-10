# SocialFlux Annotation Studio

Offline T1–T3 开发题标注入口：

```text
http://127.0.0.1:8000/offline-review
```

默认读取 `data/offline_gpt50_t1_t3/items.jsonl`，对应 50 个 scenario 的 T1/T3
开发批次，T2 暂停；页面显示实际题数与缺项。来源是固定版本的 scenario + rollout，
T3 另有候选行动分支。题库选择器保留原 60 题，也可用 `?bank=dev60` 进入。
入口也在 `/gpt50` 和 `/gpt50-live` 导航中。
支持任务、四维 state、单维／组合、标注进度筛选，以及按题号或场景搜索。
可用 `/offline-review#SFG50-010-T1-01` 直接打开某题；旧 `#SFO-005` 书签仍选择原题库。

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
