# SocialFlux Annotation Studio

当前默认页面是 GPT 小规模实验的人工 Gate 1：

```text
http://127.0.0.1:8000/gpt50
```

它展示完整 scenario、角色、关键历史、initial state、runtime dynamics seed、trigger 与 schema 状态，并导出绑定 scenario SHA-256 的人工审核草稿。Gate 1 只人工冻结 initial state，runtime dynamics seed 由机器合同校验；通过后每个场景只生成一条 rollout。

旧 Qwen rollout 和旧 Scale300 场景已移出活跃目录，保存在本地忽略归档中。历史四 Gate 页面、任务审核页、示例页和可选媒体路由仍保留；旧 Talking Head 素材与本地生成引擎已永久删除，当前媒体清单为空；接入与审核框架等待外部 API。没有活跃数据时页面会显示归档状态，不会将旧结果当作当前候选。

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
