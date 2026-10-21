# 代码清理记录 · 2026-10-21

本次重构依据 [DESIGN_CONTRACT](../../DESIGN_CONTRACT.md) 的单一职责和唯一执行路径要求，先保存工作区快照，再核对导入、CLI、测试、文档引用和运行进程。已有未提交修改一并纳入备份；没有回退到 Git HEAD。

## 公共能力归位

| 能力 | 现在的唯一 owner | 清理结果 |
|---|---|---|
| 场景发现、文档、manifest 校验 | `scenario_design/catalog.py` | `scripts/scenario_docs.py` 只解析 CLI 参数，领域和网站调用方直接导入 owner |
| 固定 appraisal 路由选择 | `pipeline/runtime.py::appraisal_route_config` | 离线构建不再导入历史续跑脚本；保留原槽位、采样设置及传输限制 |
| Provider 调用计数 | `providers/base.py::call_count` | T1–T4 无需为计数导入 T2 的环境运行服务 |
| JSON 原子写入 | `shared/artifacts.py::atomic_json` | 33 份相同实现合并为 1 份，UTF-8、缩进、末尾换行及替换方式一致 |
| 场景 JSON 内容哈希 | `shared/artifacts.py::canonical_json_sha256` | 环境、rollout 和网站共用一份实现；保留原规范 JSON 字节格式 |
| T2 请求总量 | `tasks/T2/runtime.py::count_requests` | 回放完成阶段和产物汇总共用一份规则，排除元数据及缓存 total |
| 离线选择题回答校验 | `tasks/offline_choice.py::validate_answer` | T1/T2/T3 共用解析和版本集合，保留 v1/v2 与旧概率协议的分发 |

领域模块不再直接导入 `scripts/`。`pipeline/cli.py` 的命令分发仍允许调用脚本；新测试检查该边界，并验证导入离线构建不会加载历史实验编排器。原有批次脚本之间仍有调用关系，不因文件名包含版本号就删除。

新运行的任务构建指纹已纳入抽取出的公共依赖，探索批次的源码冻结目录也覆盖 `shared/` 和 `scenario_design/`。测试确认公共实现变化会改变构建指纹；已有批次的冻结清单不回写。

## 删除及退役

删除 8 个经全仓库引用检查确认无调用方的函数：

- `environment/prompts.py::build_response_prompt`
- `evaluation/pipeline_acceptance.py::load_trajectory_pool`、`load_local_interventions`
- `evaluation/rollout_gate.py::_tail_has_repetitive_loop`
- `scripts/prepare_batch_gate2.py::scenario_covered_timescale_payload`
- `scripts/run_environment_interventions.py::_existing_e5` 及其独占辅助函数 `_subtract`
- `tasks/T1/t1_probability_utils.py::normalize_scores`

以下单次脚本已完成预定任务，没有代码、CLI、测试或文档调用方，正文从活跃目录撤除：

| 退役入口 | 保留的结果证据 |
|---|---|
| `scripts/prepare_role_visible_pilot.py` | `observed_evidence_v6_pilot_preparation/manifest.json` |
| `scripts/recover_exploratory_empty_response.py` | `unified_current_trust_v1_empty_response_recovery/01_GPT50_026_gpt/result.json`，状态 completed |
| `scripts/validate_observed_evidence_candidate.py` | `observed_evidence_v6_fixed/results.json`，状态 completed |

结果均位于 `data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/`，未修改或删除。原脚本 SHA、完整结果路径、删除理由与恢复规则保存在 [代码退役清单](../../scripts/retired.json)。不增加自动恢复或转发兼容层。

## 配置与实验边界

- 126 个 JSON 配置内容保持不变；没有规范化 JSON 完全相同的副本。
- 56 个配置引用已退役 prompt，保留历史来源身份，不能替换 ID 后冒充原实验。其余配置也不能仅凭未引用退役 prompt 就视为通过运行条件。
- Prompt、schema、题库发布文件与正在运行的 T4 恢复/编排脚本均保留；本次没有触发 API 实验。
- 原扩展批次冻结目录的 499 个文件、新 41 场景批次冻结目录的 500 个文件，均逐一通过对应 `runtime_manifest.json` 的 SHA 校验。
- 旧 GPT50 编排链、历史配置和仍有调用方的任务协议继续保留。历史批次要在匹配的冻结运行目录复现，不能回写旧 manifest 来适配新源码。

配置逐文件清单见 [config_inventory.json](../../build/code_cleanup_20261021/config_inventory.json)。

## 验证

重构前先运行完整本地测试，记录基线；重构后对比失败用例集合，不把已有错误归为本次通过。

| 检查 | 结果 |
|---|---|
| 重构前核心测试 | 931 项；4 failures、15 errors、11 skipped |
| 重构后核心测试 | 946 项；原有失败/错误用例集合不变，无新增回归 |
| 新增公共边界测试 | 10 项通过：文件完整性、哈希、路由隔离、计数、跨任务协议、依赖方向、导入、独立 CLI 启动和代码指纹 |
| 网站测试 | 56 项通过 |
| CLI | 场景文档及 4 个公共写入调用脚本可从临时目录以 `python -I ... --help` 启动；不调用模型 |

原有 19 个失败/错误涉及历史 prompt 退役、缺失或过期的冻结资产、已有对话校验预期及场景角色校验。此次未通过删除这些测试、放宽规则或改写历史输入使其消失。

复核期间共享工作区还新增了 5 项离线媒体测试及 2 项网站测试，已纳入最终结果；对应的媒体配对工作保留并单独标记，不计入本次重构。此次代码清理涉及 90 个 Python 文件，净减少 556 行；逐文件归属见 [source_changes.json](../../build/code_cleanup_20261021/source_changes.json)。

完整基线、回归日志及核验汇总位于 [build/code_cleanup_20261021](../../build/code_cleanup_20261021/)。

最终 `git diff --check` 通过，143 个 Markdown 文件的本地链接检查通过。改动保留在工作区；当前 `.git` 为只读权限，本次没有提交或推送，也没有覆盖原有未提交工作。

## 备份与恢复

修改前的 757 个代码、配置、prompt、schema、文档及测试文件保存在 `archives/code-cleanup-2026-10-21/before_cleanup.tar.gz`；同目录 `manifest.json` 记录逐文件 SHA 和修改前 Git 状态。备份不含凭据、数据轨迹或运行中服务环境。

恢复时先解压到独立目录，对照 SHA 和本次之后的变更；不能将整包直接覆盖当前工作区。快照包含本次重构开始前已有的未提交开发工作，历史实验结果另在原有 artifact 中保存。
