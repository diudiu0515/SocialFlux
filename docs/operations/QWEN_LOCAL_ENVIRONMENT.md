# Qwen 本地环境部署与 prompt 诊断

本配置面向后续多模型比较与真人交互的环境模型。当前部署目标为
`Qwen/Qwen3.8-Flash-Next-FP8`，环境调用仍经过现有
`UnifiedEnvironmentFactory` / `StatefulEnvironment`。
部署和诊断是否成功，以本地运行产物为准；本文件不是成功声明。

## 模型选择

- [官方模型卡](https://huggingface.co/Qwen/Qwen3.8-Flash-Next-FP8)：
  125B 主模型、51B n-gram embedding、4B MTP，官方 FP8 权重约 186GB。
- [官方 vLLM recipe](https://recipes.vllm.ai/Qwen/Qwen3.8-Flash-Next)：
  使用 CPU embedding offload；本机配置为 4 × 48GB RTX 4090、TP4、
  expert parallel、32K context，先用 eager 模式验证。
- 系列旗舰 [Qwen3.8-2.4T-A95B](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B)
  超出本机存储及 GPU 容量；Flash-Next 是此次选择的本地部署候选，
  不能称为整个系列的绝对最强模型。

配置在 [qwen_local_deployment.json](../../configs/qwen_local_deployment.json)。
所有权重、依赖、请求和诊断保存在被 Git 排除的 `build/qwen_deployment/`。
服务仅监听 `127.0.0.1:8010`，采用 OpenAI-compatible chat-completions 协议。

## 2026-10-23 部署验收

北京时间 20:33:31，`--deploy-only` 部署完成。vLLM 0.32.0 / PyTorch
2.13.0+cu130 在四张 RTX 4090 上加载成功，权重占用每卡约 31.84GiB，
上下文上限 32768 tokens；CPU 保存 offload 的 n-gram embedding。
本次以 `--language-model-only` 启动，用于文字环境交互，未启用图像/视频输入。

`/health` 和 `/v1/models` 返回 HTTP 200，模型 ID 与配置一致；一次实际
chat-completions 请求生成 `{"status":"ok"}`，6 个输出 token，
`finish_reason=stop`。回执保存在 `build/qwen_deployment/smoke.json`。
独立 Supervisor 状态为 RUNNING，服务可在部署脚本退出后继续运行。
这只确认服务可用，不构成能力、吞吐或 prompt 质量评估。

依用户要求，本轮未运行 environment prompt 测试：状态记录
`ready=true`、`diagnostic_requested=false`、`diagnostic_completed=false`。
后续调用使用 base URL `http://127.0.0.1:8010/v1`、模型 ID
`Qwen/Qwen3.8-Flash-Next-FP8`；如需关闭思考，在请求中传
`chat_template_kwargs={"enable_thinking":false}`。

## 启动与检查

依赖使用独立环境 `build/qwen_deployment/venv`，版本固定为 vLLM 0.32.0。
依赖安装由 `scripts/install_qwen_runtime.py` 负责：先固定解析版本，从
PyPI 元数据选择当前 Python/平台可用的 wheel，再分片下载并核对 SHA-256，
最后离线安装。下载中断可以保留已有分片重试，避免重新流式下载大型 CUDA 包。
权重必须完成下载和校验后再启动：

```bash
python scripts/serve_qwen_local.py --print-command
python scripts/serve_qwen_local.py
curl --fail http://127.0.0.1:8010/v1/models
```

持久服务使用独立的 [Supervisor 配置](../../configs/qwen.supervisord.conf)：

```bash
build/qwen_deployment/venv/bin/supervisord -c configs/qwen.supervisord.conf
build/qwen_deployment/venv/bin/supervisorctl -c configs/qwen.supervisord.conf status
```

只部署、不运行 environment prompt 诊断时，使用
`python scripts/deploy_qwen_local.py --deploy-only`。此模式只做模型身份和一次
实际生成检查，成功后记录 `ready=true`、`diagnostic_requested=false`，不会读取
或执行已准备的 15 个诊断样本。服务管理程序和模型均使用独立环境。

此次后台部署由 `scripts/deploy_qwen_local.py` 串联下载、依赖、服务、
真实生成检查与已准备的诊断。阶段及异常写入
`build/qwen_deployment/status.json`；`ready` 只在模型实际生成成功后为 true，
`diagnostic_completed` 只在所有预定样本都尝试后为 true，失败样本仍计数。
后台流程在启动服务前检查四张 GPU 的可用显存；已有标注视频渲染任务占用
显卡时记录 `waiting_for_gpu` 并等待，最长 24 小时，不终止已有任务。

`configs/qwen_local_deployment.json` 的 `provider` 可用于环境各阶段。
state 和 interaction 仍分别调用，之后 Python 更新数值，再调用 response。
首轮诊断关闭 thinking，以测量直接结构化输出及交互延迟；此模式的结果
不代表 thinking 模式的上限。若比较 thinking，必须另建配置和独立运行目录。

## 当前 prompt 的固定诊断

复用当前 observed-evidence v6、actor binding、trust evidence 规则、
schema-bound interaction 和 response v31。运行时不修改 prompt。

```bash
python scripts/evaluate_environment_prompt.py \
  --prepare-only --scenario-count 6 \
  --output build/qwen_deployment/prompt_eval_non_thinking

python scripts/evaluate_environment_prompt.py \
  --run-prepared \
  --output build/qwen_deployment/prompt_eval_non_thinking
```

准备阶段按固定哈希顺序选取有完整来源的 6 个开发场景，每场景选择早期与
中期 checkpoint，另为前三个场景加入中性输入，共 15 例。运行前记录
源文件、代码、prompt 与配置哈希。已失败的本次样本不以新样本替换。
`manifest.json` 保留不可用来源名单与选择口径。
准备时同时复制输入与运行代码，后台流程从该冻结副本执行，避免下载期间
项目的后续修改改变本次试验。

每例使用真实 snapshot，通过完整环境的 `restore` / `step` 执行。
`results.json` 给出完成率、首次通过数、真实请求次数、延迟及源模型状态
变化方向对照；各 case 目录保留 `turn.json` 和各阶段请求/输出。

源模型一致率不是人工正确率。中性输入在具体上下文中仍可能产生合理的
状态变化，需要逐例阅读证据。格式通过也不能替代角色、事实、承诺归属、
历史使用及回复自然度的语义审核。此次诊断不授予 formal admission，
真人交互上线前仍需完整轨迹与真人验收。

## 2026-10-23 实际诊断结果

北京时间 20:47:21 至 21:50:46，使用此前冻结的 6 个开发场景，运行
12 个原行动 checkpoint 和 3 个中性对照。采用非思考模式，全程未修改
prompt、替换失败样本或增加约定外的重试。完整统计、逐例回复和助手审查见
[诊断报告](../../reports/analysis/2026-10-23_qwen_environment_prompt_diagnostic.json)。

| 指标 | 实测结果 |
| --- | --- |
| 完成 / 失败 | 14 / 1，共 15 例 |
| 首次通过 | 5/15；另 9 例经重试完成 |
| 实际模型调用 | 61 次，其中 17 次为结构化输出重试 |
| 被拒绝的结构化输出 | 18 次，包含最终失败的一次 |
| 传输错误 / 输出截断 | 0 / 0，61 次均以 stop 结束 |
| 成功用例耗时中位数 | 208.974 秒，约 3 分 29 秒 |
| 全部用例最长耗时 | 409.363 秒，为失败用例 |
| 整批耗时 | 63 分 25 秒 |
| 最终回复语言 | 中文 8，英文 6；prompt 要求中文 |

失败用例为 `GPT50_011_t6`：state appraisal 连续三次使用
`positive/negative`，未按合同返回 `increase/decrease`，因此没有进入
response 阶段。其他重试原因包括遗漏字段或 dynamics 判断、证据引文不是
当前行动的精确片段、枚举取值混淆和回复义务与互动记录不一致。

逐例审查发现以下内容问题，均保留原始请求和输出：

- `GPT50_006_t2` 与 `GPT50_025_t2` 在校验重试后清空互动记录，回复中却仍有
  新的提案或问话。当前语义模式校验字段间的一致性，未阻止这类内容遗漏。
- `GPT50_006_t6` 将“接受失去资金的风险”加强成“放弃资金”，state appraisal
  也以目标已经放弃为依据降低期限压力。
- `GPT50_025_t6` 把并行协调描述为能确保截止前完成所有协调，并把
  medication reconciliation 误译为“和解”；`GPT50_043_t2` 把比赛头衔
  title 误译为“标题”。

也有明确的正面结果：模型在多个场景保留了待核实证据、尚未授权、县方标准
未定及补救仅为请求等边界。三个中性对照中，两个不改变数值，一个仅增加
合作意愿 1；这个变化本身不计为错误。14 个完成用例的状态均未越界，
变量集合均保持完整。

本轮结论是服务和完整调用链可用，但当前非思考模式下的输出规范执行、
互动记录覆盖和事实确定性仍不稳定；现有延迟也不适合直接用于实时人机交互。
后续优先改进结构化输出约束、明确字段级纠错反馈并检查互动记录与回复内容
的一致性，再在新运行目录复测。此次只是助手审查和开发诊断，完成率不是
语义正确率，也不构成对 thinking 模式能力或正式 benchmark 准入的结论。
评测后 Qwen 服务健康检查仍返回 HTTP 200。

## 2026-10-24 思考模式诊断

本次复用了上一轮冻结的案例、prompt、schema 和环境更新逻辑，分别在独立目录
测试默认强思考及中等思考。原计划的 15 例对照**没有跑完**：默认强思考先遇到
预算耗尽，中等思考完成同一场景的两个 checkpoint 与一个中性输入后，因确认了
输出合同缺口而收尾。未运行案例和中断请求均保留在统计中，未替换失败样本。
详见[思考模式诊断报告](../../reports/analysis/2026-10-24_qwen_thinking_environment_prompt_diagnostic.json)。

| 配置 | 已得到结果的案例 | 完整流程完成 | 主要观察 |
| --- | --- | --- | --- |
| 默认 xhigh，沿用原预算 | 3 | 0 | state 的 6000 token 全用于思考，没有最终 JSON |
| 默认 xhigh，state 上限增至 12000 | 1 | 0 | 12000 token 仍全用于思考 |
| medium，采用官方建议的采样参数 | 3 | 1 | 0 例首次通过；2 例耗尽结构化重试 |

第一轮另有一个在途案例在停止过程中收尾，其 2 次请求单列为中断记录。
三轮环境请求共 26 次，加上两个连通检查共 28 次。中等思考这一轮使用
16 次请求，包含 8 次额外重试、10 次被拒绝的结构化输出，无输出截断，
实际运行约 51 分 10 秒；剩余 12 例未运行。唯一完成的案例耗时 897.3 秒。
同样三个输入在此前非思考模式下均完成，但两轮的采样与预算不同，不能把
差异仅归因于思考开关，也不能从一个场景推断模型整体能力。

已确认的输出合同缺口是：

- [state prompt](../../prompts/environment_state_appraisal_v6_observed_evidence.md)
  要求提供 `direction`，却没有声明非空值必须为 `increase/decrease`，示例只有
  `null`；[validator](../../environment/independent_appraisal.py) 则严格要求这两个值。
- `GPT50_006_t6` 三次返回 `positive/negative`，每次收到的反馈只是
  `state_judgments new evidence needs a direction`，没有字段实际值和合法取值。
  三次均未修正，耗时约 21 分 47 秒，没有进入回复阶段。

语义上，`GPT50_006_t2` 的最终回复正确记录了追问，没有复现上一轮清空
互动记录的问题；但 `GPT50_006_t6` 的被拒绝草稿仍把“不能承诺十一点前批准”
加强为“该时间窗口已确定不可能”。中性案例的四次回复尝试分别因表达意图过长、
JSON 语法、表达意图过长和回复义务一致性被拒绝。拒绝的草稿不是已完成环境轮次。
这些结论来自助手审查，不是人工正确率或正式准入结果。

下一步应先从统一 schema 明确输出字段与枚举，并让纠错反馈给出字段路径、
实际值和允许值，不要静默把 `positive/negative` 转换为数值方向。
另外，当前 vLLM 的
[独立思考预算](https://docs.vllm.ai/en/stable/features/reasoning_outputs/#thinking-budget-control)
已通过小型连通检查：设置 `thinking_token_budget=32` 后实际思考 31 token，
随后输出正确 JSON；该参数尚未在 environment 案例上评估。
补齐合同并冻结新的配置后，再完成全量对照。此次没有修改生产 prompt、validator
或默认非思考配置；Qwen 服务继续运行，健康检查返回 HTTP 200。
