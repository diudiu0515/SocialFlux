# SocialFlux Annotation Studio

网站是 20 个 canonical scenario、完整 Rollout Screening 人工队列与历史 180 个 T1/T2/T3
开发实例的只读可视化和人工标注草稿工作台。当前旧筛选库存 184 条均因只有 6 轮而被
新版 20 轮 Gate 判为 REJECT，不存在 provisional winner；它们仍完整呈现，供人工审计旧失败与筛选规则。网站读取
`configs/scenarios/scenario_NNN/`、`build/pipeline_v2/` 和 Talking Head
资产，不复制或修改环境状态机。

界面包含：

- Scenario 情节、被测角色身份与 explicit goal、环境角色目标、完整 persona/hidden intention、关键历史、选择空间、S0/D0 与视频阈值审核；
- 被测模型使用配置指定的 T4 prompt（当前示例为 `task_t4_action_v17`），并展示首轮真实渲染输入、公开字段和明确排除的私有字段；
- Rollout 逐轮对话、状态变化、六维质量和 hard-reject 标注；
- T1/T2/T3 逐实例题面、专属 Gate 4 检查和人工标签草稿；
- `/task_examples.html` 集中展示三项高质量示例、完整公开历史、机器答案与 text/text+video 配对；
- 该页审核结果保存在浏览器 localStorage，并可单独导出 JSON；机器答案始终保持 `ground_truth=null`；
- 自然语言 scenario、完整 rollout 与 task 抽查文档；
- 浏览器自动保存、审核进度和 JSON 导出。

浏览器记录只是本机草稿，不会写入仓库，也不构成真人签名、Gate 通过或正式
human GT。导出的 JSON 仍需走项目中的 hash 绑定、两人同样本独立抽查和
分歧仲裁流程；只有抽查通过后才能发布全量机器建议标签。

启动：

```bash
python -m web.server --host 0.0.0.0 --port 8000
```

本机访问 `http://127.0.0.1:8000/`。远程服务器推荐端口转发：

```bash
ssh -L 8000:127.0.0.1:8000 <host>
```

然后访问 `http://127.0.0.1:8000/`。

验证：

```bash
python -m unittest discover -s web/tests -v
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/annotation-contract
curl http://127.0.0.1:8000/api/task-examples
```
