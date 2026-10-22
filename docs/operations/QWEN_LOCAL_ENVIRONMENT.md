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
supervisord -c configs/qwen.supervisord.conf
supervisorctl -c configs/qwen.supervisord.conf status
```

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
