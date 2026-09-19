# SocialFlux Annotation Studio

当前默认页面是 GPT 小规模实验的人工 Gate 1：

```text
http://127.0.0.1:8000/gpt50
```

它展示完整 scenario、角色、关键历史、S0/D0、trigger 与 schema 状态，并导出绑定 scenario SHA-256 的人工审核草稿。通过 Gate 1 后每个场景只生成一条 rollout。

旧 Qwen rollout 和旧 Scale300 场景已移出活跃目录，保存在本地忽略归档中。历史四 Gate 页面、任务审核页、示例页和可选媒体路由仍保留；旧 Talking Head 素材与本地生成引擎已永久删除，当前媒体清单为空；接入与审核框架等待外部 API。没有活跃数据时页面会显示归档状态，不会将旧结果当作当前候选。

浏览器记录仅保存在 localStorage，不写仓库，也不构成真人签名、Gate 通过或 human GT。正式 Gate 4 仍要求两人独立审核同一确定性样本，只有分歧项进入仲裁。

## 启动

```bash
python -m web.server --host 127.0.0.1 --port 8000
```

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
