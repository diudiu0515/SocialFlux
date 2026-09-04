# SocialFlux Pipeline v2

## 1. 创建 scenario

Synthetic 来源先从 brief 生成原创自然剧本：

```bash
python scripts/scenario_sources.py generate-script \
  --input brief.json --provider-config provider.local.json \
  --output build/scenario_work/script.md
```

Narrative-derived 来源先提交只含作品标题、媒介和分析目标的 JSON 请求，再抽取高层社会机制：

```bash
python scripts/scenario_sources.py extract-structure \
  --input source_request.json --provider-config provider.local.json \
  --output build/scenario_work/structure.json
```

结构抽取必须丢弃原作角色、台词、标志性物件/机构及情节序列，并要求新场域、新人物、新事件、新 stakes 与原创语言。两类来源都先经过质量门；下面以 narrative-derived 为例：

```bash
python scripts/scenario_sources.py quality-check \
  --input build/scenario_work/structure.json \
  --source-type narrative-derived \
  --provenance-id screen-structure-021 \
  --provider-config provider.local.json \
  --output build/scenario_work/quality.json
```

模型只能写 `pending_human_review`。真人确认 11 项均为 `pass` 后，才可把 `review_status` 改为 `approved`。随后 normalization：

```bash
python scripts/scenario_sources.py normalize \
  --input build/scenario_work/structure.json \
  --quality-report build/scenario_work/quality.json \
  --source-type narrative-derived \
  --provenance-id screen-structure-021 \
  --provider-config provider.local.json \
  --output build/scenario_work/blueprint.json
```

最后单独生成候选 S0/D0、expression 和稀疏视频阈值：

```bash
python scripts/scenario_sources.py initialize \
  --input build/scenario_work/blueprint.json \
  --provider-config provider.local.json \
  --output configs/scenarios/scenario_011/scenario_011.json
python scripts/scenario_docs.py
python scripts/scenario_docs.py --check
```

候选仍必须由真人 freeze。每个 scenario JSON 必须有同目录同名 Markdown；rollout 后的 trajectory JSON、逐轮自然语言 `dialogues.md` 和逐 T1/T2/T3 instance 的自然语言 `tasks.md` 放在该 bundle 的 `rollouts/`。

## 2. 配置模型池

`configs/rollout_pool.example.json` 定义：

- 一个固定 environment model/config；
- 一个 T2/T3 construction model/config；
- 至少两个不同 model/sampling policy specs；
- 每个 spec 的 temperature、seed 与 runs。

`configs/rollout_qwen35_full.example.json` 固定本轮 3 seeds × 6 turns、T1=6、T2=2、T3=1、5 轮延迟分支的可复现开发配置；只需替换模型绝对路径和本地 endpoint。

密钥只通过 `api_key_env` 指向环境变量。日志和公开 manifest 不记录密钥或环境变量名。

GPT–Qwen 匹配 pilot 使用 `configs/rollout_comparison.example.json`：固定同一个 environment/construction model、scenario、turns、temperature 与 seeds，Qwen/GPT 轨迹交错排列；T2 设置 `within_source_model` 并按来源模型分层轮询，避免交叉模型 history pair。把 Qwen 绝对路径和 `YOUR_GPT_MODEL` 替换为本机值，并在 shell 设置 `OPENAI_API_KEY`。本地 Transformers server 必须确认 sampling 已开启；provider 会按 base seed + call index 推进请求 seed。

## 3. 生成自然轨迹与离线任务

```bash
python -m scripts.run_pipeline \
  --scenarios configs/scenarios \
  --rollout-config configs/rollout_pool.local.json \
  --output build/pipeline_v2

# 可重复 --scenario-id 做可复现实验子集
python -m scripts.run_pipeline \
  --scenario-id IA_PIPE_011 \
  --rollout-config configs/rollout_pool.local.json \
  --output build/pipeline_v2 \
  --allow-unreviewed
```

正式运行会拒绝未通过质量门或未 human_frozen 的场景。开发联调可显式加 `--allow-unreviewed`，产物不可视为正式数据。`--build-only` 只复用 provenance 为 `free_form_model_interaction` 且能与当前 model config 匹配的轨迹。

产物：

- `configs/scenarios/scenario_NNN/rollouts/`：private master trajectories、manifest、逐轮自然语言 `dialogues.md`、逐 instance 人工抽查 `tasks.md`。
- `build/pipeline_v2/scenario_NNN/offline/instances.jsonl`：T1/T2/T3 candidate。
- `build/pipeline_v2/scenario_NNN/validation/local_action_interventions.json`：局部 checkpoint 分支。
- `build/pipeline_v2/manifest.json`：去密钥的聚合 provenance 与计数。

T1 的 target 必须是持有 latent state 的环境角色；T2/T3 也必须显式携带同一 target character 与目标 state IDs。生成后运行结构质量审计：

```bash
python scripts/evaluate_instance_quality.py \
  --pipeline-output build/pipeline_v2
python scripts/audit_scenario_bundles.py \
  --pipeline-output build/pipeline_v2
```

若质量报告只拒绝 T2，可保留真实 rollout、T1 和 T3，使用 `scripts/rebuild_t2_instances.py` 对指定 scenario 重新检索无重复历史并以 `t2_shared_observation_v3` 重建 O*；该命令会同步刷新 `tasks.md`、scenario manifest 与聚合 JSONL。

自动分数检查合同、泄漏、重复历史、T2 双方角色/private divergence、T3 分支完整性，并另报完整轨迹的 action/response 唯一率与 latent 边界占比。可用 `--judge-provider-config` 增加去 model/provenance 的盲化语义诊断，但同模型自评可能明显偏乐观，仍不是 human ground truth。`run_acceptance.py` 会自动读取同一 pipeline output 下的质量报告；轨迹质量失败时不能把 Full-Trajectory 标为 provisionally ready。

## 4. 验收

```bash
python scripts/run_acceptance.py \
  --scenarios configs/scenarios \
  --pipeline-output build/pipeline_v2 \
  --output build/acceptance_v2
```

报告固定列出九项验收。代码可准备结构、seed 与局部干预证据，但 State Update、Persona、Paraphrase、History、Neutral Stability、Response-State 与完整轨迹合理性仍需规定的人类评审。任何 pending 都不能改写成 passed。

## 5. 开发检查与网站

```bash
python scripts/update_prompt_manifest.py
python scripts/scenario_docs.py --check
python -m unittest discover -s tests -v
python -m unittest discover -s web/tests -v
python -m web.server --host 0.0.0.0 --port 8000
```

网站只读当前 scenario、质量状态、自然轨迹、状态变化、Talking Head trigger 与 `tasks.md` 人工抽查包，不生成另一个 session。多 GPU/多机器可分别运行 scenario 子集，再用 `scripts/merge_pipeline_outputs.py --input <shard> ... --output build/pipeline_v2` 合并；合并后必须运行 bundle audit。
