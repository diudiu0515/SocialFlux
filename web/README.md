# SocialFlux Scenario Visualizer

网站是当前 canonical scenario 与自然 rollout 的只读研究者视图。它读取 `configs/scenarios/scenario_NNN/`、`build/pipeline_v2/` 和 `build/acceptance_v2/`；不接受 action，不维护 session，也不复制环境状态机。

启动：

```bash
python -m web.server --host 0.0.0.0 --port 8000
```

本机访问 `http://127.0.0.1:8000/`；远程服务器可做 SSH 端口转发。没有自然 rollout 时仍可查看 10 个 scenario、来源、质量/S0 状态、初始 state、视频阈值和配套 Markdown；界面会明确显示 rollout pending。

验证：

```bash
python -m unittest discover -s web/tests -v
curl http://127.0.0.1:8000/api/health
```
