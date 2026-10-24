# Benchmark 公共接口合同

本文记录当前可测试的开发接口；不表示题库已获开源授权、人工验收或正式准入。
运行语义以 [DESIGN_CONTRACT](../../DESIGN_CONTRACT.md)、canonical 实现和版本化
schema 为准。新接入复用现有接口，不另写环境状态机或按模型复制评测路径。

## 安装与统一 CLI

使用[Conda 环境](../operations/DEVELOPMENT_ENVIRONMENT.md)。公开命令入口为
`python -m pipeline`；参数帮助不调用模型。真实题库必须通过参数显式提供，不能
假设外部用户拥有本机 `data/`、私有 endpoint 或密钥文件。

T1–T3 使用现有[选择题协议](OFFLINE_T1_T3_CHOICE_V2.md)：题面从
`tasks.offline_choice.public_instance` 投影，被测模型的主输出为
`{"answer":"B"}`，由[回答 schema](../../schemas/offline_choice_output.schema.json)
及 `parse_answer` 验证。参考答案、作者审计材料与评分流程独立于被测模型输入。

模型适配扩展 `providers.base.ModelProvider.complete(messages, **generation)`，
由 `providers.factory.build_provider` 装配；策略复用 `ModelPolicy.generate(observation)`。
endpoint、模型名、采样参数与凭据来源由配置提供。公开示例优先使用 `endpoint_env`
和 `api_key_env`；不嵌入个人网关、私有密钥文件路径或某次实验的机器目录。

## T4 开发会话 HTTP API v1

实现为 `scripts/serve_qwen_task4.py` 和 `QwenTask4Session`。当前是本机服务，
监听 `127.0.0.1`，无互联网认证层；远程开发通过 SSH 隧道访问。正式公开托管属于
单独部署工作，需要另行设计认证、配额和数据访问权限。

机器合同为 [task4_session.schema.json](../../schemas/task4_session.schema.json)：
根 schema 校验会话响应；`$defs/create` 和 `$defs/step` 校验请求；`$defs/error`
校验错误响应。合同编号 v1 描述 wire 格式，与模型/prompt profile v1/v2 分开。
公开字段或语义发生不兼容变化时须新增合同版本和迁移说明，不能静默复用旧版本。

| 方法与路径 | 输入 | 结果 |
| --- | --- | --- |
| `GET /health` | 无 | 200/503；模型可用性、profile、model、reward_status |
| `GET /scenarios` | 无 | 200；冻结 catalog 中的 scenario_ids |
| `POST /sessions` | `{"scenario_id":"..."}` | 201；初始会话响应 |
| `GET /sessions/{episode_id}` | 无 | 200；当前会话响应；未知会话为 404 |
| `POST /sessions/{episode_id}/step` | `{"text":"自由文本行动","expected_turn_id":0}` | 200；下一观察；环境生成失败为 502 |
| `DELETE /sessions/{episode_id}` | 无 | 200；`{"closed":true}`；保留本地审计证据 |

客户端只从 `/scenarios` 选择 ID，不能提交服务器文件路径。POST 使用 UTF-8 JSON
对象，正文上限 65536 字节。`text` 必须非空；`expected_turn_id` 必须使用上一观察的
非负整数 `turn_id`，不能传布尔值。协议没有固定 action ID 或预定义策略菜单。

会话响应字段固定为 `episode_id`、`observation`、`reward`、`terminated`、
`truncated`、`failed`、`info`。三个结束信号必须分开统计：

- `terminated=true`：自然结束。
- `truncated=true`：轮次上限等非自然截断。
- `failed=true`：环境生成失败，不能计为正常结束或零分样本。

`reward=null` 和 `info.reward_status=unconfigured` 表示尚未配置奖励；不能转换为
数值 0 训练 RL。`formal_admission=false` 必须如实保留。

400 表示请求无效；404 表示资源不存在；409 表示轮次过期、会话结束/失败或容量
限制；503 表示模型未就绪或生成槽忙。客户端收到超时或连接中断后先 GET 当前
会话确认轮次，不盲目重发 POST；旧轮次会被拒绝，失败会话不能继续 step。
重启不恢复内存会话，DELETE 也不删除轨迹；持久会话和奖励接口尚未实现。

## 公开与作者侧数据

`observation` 由 `environment.observation.build_policy_observation` 统一生成。
对方仅公开身份，己方公开角色/目标和允许的自我 persona 可见；状态、动力学、
对方 persona、hidden intention、appraisal、未来分支和作者轨迹均不能传入模型。

JSON Schema 检查结构，并不自动判断自由文本中是否泄漏私有事实。来源投影和
语义审查仍须执行。失败正文、模型请求与私有轨迹只留在作者侧 run 目录，不作为
错误响应返回客户端，也不随 Git 或公开数据包自动发布。

## 可独立验证的边界

```bash
python -m unittest tests.test_public_task4_api tests.test_offline_choice tests.test_qwen_task4_policy -v
```

HTTP 测试启动临时本机端口，使用明确标注的合成工程 fixture 和无模型状态替身，
复用真实会话、HTTP handler 及公开观察投影，检查轮次冲突、失败隔离、结束状态和
源码/场景哈希约束。这些测试不证明真实模型输出质量或研究指标达标。

后续开源包须分别准备代码依赖、经授权的公开题面/媒体、评分材料及可复现配置；
不能直接打包整个 `data/` 或 `build/`。许可证、数据/媒体授权、正式划分与人工
GT 仍须按项目发布流程明确，当前变更不会自动赋予许可证或发布研究数据。
