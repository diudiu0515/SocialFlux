# SocialFlux Runtime Prompt Catalog

本目录只保存运行时实际加载的固定 Prompt。每个 Prompt 使用稳定 `prompt_id` 和 `_vN.md` 文件名，由 `manifest.json` 记录路径与 SHA-256；代码通过 `prompts.loader` 校验后加载。

## 修改流程

1. 新建新版本，不覆盖已有版本的研究含义。
2. 同步对应 JSON schema 和 Python caller/validator。
3. 运行 `python scripts/update_prompt_manifest.py`。
4. 运行 `python -m unittest tests.test_prompt_catalog tests.test_rollout_quality_judge -v`。
5. 在 [`Prompt Audit`](PROMPT_AUDIT.md) 记录职责、信息边界和变化原因。

## Rollout 筛选 Prompt

- `rollout_quality_judge_v2.md`：当前 production screening Prompt，遵循 Screening Protocol v1，使用六维 1–5 评分、10 项 hard reject，并要求每个维度引用 1–3 个真实 turn ID。
- `rollout_quality_judge_v1.md`：legacy 开发证据解释版本。保留用于论文追溯和旧报告复现，新 Judge caller 不再默认加载。

## 信息边界

Evaluated-agent Prompt 不得获得 hidden intention、latent state、appraisal、delta、trigger threshold、未来 branch 或 source model metadata。Author-side environment Prompt 只在对应私有阶段读取必要信息；Talking Head 请求只能包含可观察表达与安全外观描述。完整映射见 Prompt Audit。

设计讨论稿位于 [`docs/source-notes/`](../source-notes/)，不得直接加入 manifest。
