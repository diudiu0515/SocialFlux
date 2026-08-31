# Scenario Observatory

这是 SocialFlux pipeline 的唯一网站层，不包含独立状态机、独立 demo scenario 或交互会话。它只读取：

- `configs/scenarios/scenario_*.json`：场景定义、persona、action effects、Talking Head triggers；
- `build/pipeline_v1/`：本地生成的 rollout、manifest 和 acceptance report。

## 启动

```bash
python web/server.py --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000/>。新增 scenario 后运行：

```bash
python -m scripts.run_pipeline --scenarios configs/scenarios --output build/pipeline_v1
python scripts/run_acceptance.py --scenarios configs/scenarios --output build/pipeline_v1
```

网站会自动从目录发现新 scenario；没有 pipeline 构建产物时仍可查看 scenario 配置，但轨迹区会提示先运行构建。
