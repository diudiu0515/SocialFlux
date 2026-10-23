# Qwen Task4 独立环境接口

`qwen_task4_thinking_v1` 使用已经部署的
`Qwen/Qwen3.8-Flash-Next-FP8`（模型 API 为 `127.0.0.1:8010`）。它为
Task4 的环境角色提供独立配置和补充提示，复用同一个 canonical
`StatefulEnvironment`、逐变量/交互 appraisal、确定性 v7 状态更新及 v31
回复校验。现有 GPT/Claude prompt、配置、工厂及 provider 均未修改。

这是开发版本。可用于交互与后续 RL 工程接入，机器通过不代表人工验收或正式
benchmark 质量通过。服务为文本模式；既有 Claude 多模态 Task4 入口保持原样。

## 配置与边界

- [独立环境配置](../../configs/qwen_task4/environment.json)
- [独立提示清单](../../prompts/qwen_task4/manifest.json)：三个补充提示及所依赖的原始
  prompt/接口文件都有 hash。原始 prompt 仍由原来的中央 manifest 验证；新增补充
  提示由此清单验证，不向已有 GPT prompt ID 注册或替换内容。
- [工厂](../../environment/qwen_task4.py)：显式创建
  `QwenTask4EnvironmentFactory(scenario)` 才启用该版本。直接调用旧工厂仍是旧行为。
- [公开交互接口](../../environment/qwen_task4_session.py)：返回公开 observation；
  私有状态、appraisal、失败正文和实际 HTTP 请求只保存在本地 episode 目录。

补充提示给出 direction/directness、字段、角色 ID、事件与状态的配对约束，以及
`expression_intent` 的 160 字符上限。重试反馈用 JSON Schema 描述被拒输出的字段
错误；最终接受仍由原有 validator 决定。不映射 positive/negative、不删除模型
输出事件，也不增加重试层。原上限为 state 3 次、interaction 3 次、response 4 次；
每次模型请求只有一次 transport attempt。实际发送的完整提示见 `*_requests.json`
的 `request.messages`，而非上游尚未添加补充提示的 `request_messages`。

各阶段显式使用 `enable_thinking=true`、`reasoning_effort=medium`，temperature 1、
top_p .95、top_k 20。state 总输出上限 6000 / 思考 1536 token；interaction
3500 / 768；response 4096 / 768。`thinking_token_budget` 是发送到 vLLM 的顶层
请求参数，不在 `chat_template_kwargs` 内。总输出预算包含思考与最终 JSON。

Task4 最多 20 轮、从第 1 轮起允许自然结束。与早先用于 offline 的 10 轮最短
设置不同，因此此版本整体性能不能当作只改 prompt 的严格单因素对照。当前配置
不生成视频、不自动调用被测 policy 或 judge。外部模型、人工和 RL 都可提供自由文本
action；环境输出不暴露 private trajectory。

## 启动冻结服务

在已有 Qwen 模型服务运行后执行（每次使用新的 run 目录）：

```bash
python scripts/prepare_qwen_task4.py \
  --output build/qwen_task4/run_20261024_v1 \
  --preregistration data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/unified_current_trust_v1_gpt50_active/preregistration.json
export QWEN_TASK4_RUN="$PWD/build/qwen_task4/run_20261024_v1"
build/qwen_deployment/venv/bin/supervisord -c configs/qwen_task4/supervisord.conf
build/qwen_deployment/venv/bin/supervisorctl -c configs/qwen_task4/supervisord.conf status
curl --fail http://127.0.0.1:8011/health
```

准备命令复制代码、prompt、schema、配置和 scenario，并记录 hash；已有目录会被
拒绝覆盖。服务运行冻结副本。无需重启或加载第二份 Qwen 模型。环境进程需要
[requirements-qwen-task4.txt](../../requirements-qwen-task4.txt)；部署使用已有 Qwen
venv。更新时关闭旧环境服务后指定新的 run，不在运行中修改冻结文件。

`127.0.0.1:8011` 仅本机可访问。`GET /scenarios` 返回可用 ID；本次准备命令使用
已有开发场景目录，并未把它们指定为 RL 训练集。以后须单独冻结训练/验证/测试划分。
并行环境应在明确 GPU 容量后扩展；当前服务一次执行一个环境 step，繁忙时返回 503，
不自动排队生成。一个 step 内 state/interaction 仍按 canonical 路径并行。

## 交互 / RL 客户端

```python
import requests

base = "http://127.0.0.1:8011"
r = requests.post(base + "/sessions", json={"scenario_id": "GPT50_006"})
r.raise_for_status()
episode = r.json()

# 把 observation 交给人工或任意被测 policy；它只含公开信息。
action = "我想先确认目前哪些事项仍需要双方决定。"
r = requests.post(base + f"/sessions/{episode['episode_id']}/step", json={
    "text": action,
    "expected_turn_id": episode["observation"]["turn_id"],
}, timeout=4800)
episode = r.json()
# 502 表示环境生成失败；保留失败样本，不能当成正常终止或零奖励。
r.raise_for_status()
assert not episode["failed"]
```

`expected_turn_id` 防止超时重发同一 action 导致多走一轮。409 表示轮次过期或
episode 不再可用；可用 `GET /sessions/{id}` 读取当前公开观察。生成失败后该
episode 不再接受 step，故障与所有请求保存在冻结 run 的 `episodes/{id}/`。
`DELETE /sessions/{id}` 释放内存槽，保留本地记录。服务重启不恢复会话，已有
轨迹/失败证据保留在原目录。
如果进程被强制杀死，`step_status.json` 中遗留的 `in_progress` 表示未完成尝试，
不能计为成功或静默重跑。正常关闭会等待正在执行的请求结束。

返回值中 `terminated` 仅指自然结束；`truncated` 指达到上限等非自然截断；
`failed` 独立表示生成失败。**`reward` 为 null，奖励函数尚未配置**，不能解释成
0 分或直接用于训练。训练时应显式接入奖励/终局评分，并保留环境失败与预算截断。
本任务没有启动 RL 训练或自动把开发案例加入训练集。

Python 内部的 Task4 rollout 可直接把 `QwenTask4EnvironmentFactory(scenario)`
传给现有 `RolloutRunner`。需要逐步交互时使用 `QwenTask4Session(factory, output)`；
`step(text, expected_turn_id=...)` 与 HTTP 的返回合同相同。不要把 canonical
`environment.step()` 的第二个返回值（private turn log）交给被测 policy。

## 2026-10-24 部署验收

冻结实例为 `build/qwen_task4/run_20261024_v1`，包含 287 个运行文件和 50 个开发场景。
29 项相关测试通过；305 个已有相关文件的 hash 均保持不变，原有 Git 暂存内容也保留。
模型 API 与独立 Task4 API 均已启动。

两例真实验收来自同一个开发场景：HTTP 初始交互耗时 387.088 秒，历史失败 checkpoint
耗时 372.548 秒。两例都完成，state 和 response 均首次通过，interaction 共出现
3 次被拒输出，总计 9 次物理模型请求。实际思考 token 用量均在配置上限内。
两例整个 step 均不是 first-pass；未跑完整 15 例对照或 20 轮评测。

语义质量尚未通过验收：一例引入未经输入支持的口头同意前提；另一例仍把“接受错失
资金的风险/不能保证批准”加强为“最终拒绝/路径完全关闭”。也观察到事件类型和
行为归属问题。结构化通过不能作为 RL 正确性奖励；此版本只说明工程接入与已知
direction 枚举问题的复测完成。完整计数和限制见
[部署验收记录](../../reports/analysis/2026-10-24_qwen_task4_deployment.json)。

## E6 环境迁移验证衔接

本任务同时为[环境有效性六维协议](../protocols/ENVIRONMENT_VALIDATION_V1.md)的新版 E6 提供 Qwen 环境迁移证据。复用本任务的冻结配置、场景和 episode，不另起一套环境生成；Qwen 承担 appraisal 与 response，而不是只充当被测 policy。

评估侧读取 run manifest、配置/prompt/schema 哈希、评估场景清单、episode ID、公开轨迹及作者侧状态/ledger/请求记录，统计完整执行、首次通过、重试、失败、耗时、不变量与结束类型，并按 E1/E2/E9 的标准核查语义和轨迹质量。只读作者侧证据不能进入被测 policy 的 observation。

当前 catalog 的 50 个场景不等于完成的测试集；训练、调试与独立评估划分需绑定到运行清单。已有 prompt 诊断和修复案例属于开发集。复用另一侧预先冻结的评估划分，至少覆盖 10 个独立评估场景；完整轨迹人工审核按 E2 的 15–20 条要求准备。每个指标保留计划、成功、失败和不适用分母。

迁移不要求 Qwen 逐维复制源模型的状态方向；检查相同机制下的执行与语义质量。补充提示、采样、思考预算和结束规则的差异都需报告。文字接口不提供多模态泛化或 RL 收益证据；`reward=null` 仍表示奖励未配置。旧 E6 的结果和验证器格式保留，新迁移产物接入正式评分前保持 `formal_admission=false`。
