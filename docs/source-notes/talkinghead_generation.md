# SocialFlux Talking Head Integration

## 定位

Talking Head 是 canonical environment 的稀疏可观察输出层，不是独立剧情生成器，也不参与 latent state 更新。普通轮次只返回文字；只有 state/dynamics 满足 scenario 定义的 threshold、crossing 或 state-change 条件时，trigger engine 才产生 media event specification。

## 每个 scenario 必须说明

同名 scenario Markdown 由 `scripts/scenario_docs.py` 自动写明：

- 初始故事、persona、目标与信息不对称；
- 初始可观察背景与环境状态；
- 每个 trigger 的变量、operator、threshold、mode、cooldown；
- 对应 facial expression、gaze、speech style、prosody 和 behavioral cues；
- duration、asset status 与人工审核状态。

这些 author-side 阈值不得进入 evaluated model、T1/T2/T3 输入或视频生成请求。

## Runtime 顺序

```text
free-form action
→ appraisal
→ semantic and numeric state update
→ text response
→ private trigger evaluation
→ safe observable-expression specification
→ optional 3–15 second media request
```

`ObservableExpressionLayer` 负责确定性 trigger 与 public media metadata。`environment_response_v25` 和 `talking_head_generation_v1` 固定 provider-neutral 输入输出边界；`scripts/run_autodl_seedance_video.py` 负责 AutoDL Seedance 2.0 的付费提交、断点续查、立即下载和 SHA-256 记录。新任务必须显式传入 `--submit-new`，已有 task ID 可安全续跑。

## 隐私边界

公开 expression/media 只描述可观察行为。不得含：

- latent state 名称或数值；
- semantic delta、appraisal、hidden intention；
- trigger ID、threshold 或 simulator mechanics；
- benchmark 答案或未来 branch；
- 把某一状态机械映射为夸张表情的刻板编码。

Private trajectory 可保留 trigger provenance 供研究者审计，网站作为 researcher view 可以展示它。

## Expression rendering policy

批量生成统一使用 `subtle_contextual_v1`：默认低到中等强度，每个 clip 最多两个可相容的 observable cues，尽量顺序展现而不是同时堆叠。表情必须与 public line 及当前可观察 context 一致，不得为了“有画面”而夸张表演，也不得由 latent state 数值直接机械映射。

## 资产质量

真实视频需检查 3–15 秒时长、人物身份一致、视线/口型/语调自然、跨轮 temporal continuity、无文字答案泄漏。正式发布还需 MV1 Trigger Validity、MV2 Expression-State Consistency、MV3 Temporal Continuity、MV4 Text vs Text+Video 的人工或实验记录。

## English-only generation

视频 provider 的 prompt、spoken line 和同步音频统一使用英文。中文 source rollout 不直接送入视频模型；另存经语义一致性审核的英文 public response，同时保留 source text 供 provenance 审计。Seedance runner 会拒绝含 CJK 字符的生成 prompt。
