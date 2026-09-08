# SocialFlux Talking Head Integration

## 定位

Talking Head 是 canonical environment 的稀疏可观察输出层，不是独立剧情生成器，也不参与 latent state 更新。普通轮次只返回文字；只有 state/dynamics 满足 scenario 定义的 threshold、crossing 或 state-change 条件时，trigger engine 才产生 media event specification。

## 每个 scenario 必须说明

同名 scenario Markdown 由 `scripts/scenario_docs.py` 自动写明：

- 初始故事、persona、目标与信息不对称；
- candidate/frozen S0 与 D0；
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
→ optional 3–8 second media request
```

`ObservableExpressionLayer` 当前负责确定性 trigger 与 public media metadata。`observable_expression_v1` 和 `talking_head_generation_v1` 固定了未来真实 provider adapter 的输入输出边界；未接 provider 时 `asset_status=spec_only`，不得假装视频已经生成。

## 隐私边界

公开 expression/media 只描述可观察行为。不得含：

- latent state 名称或数值；
- semantic delta、appraisal、hidden intention；
- trigger ID、threshold 或 simulator mechanics；
- benchmark 答案或未来 branch；
- 把某一状态机械映射为夸张表情的刻板编码。

Private trajectory 可保留 trigger provenance 供研究者审计，网站作为 researcher view 可以展示它。

## 资产质量

真实视频需检查 3–8 秒时长、人物身份一致、视线/口型/语调自然、跨轮 temporal continuity、无文字答案泄漏。正式发布还需 MV1 Trigger Validity、MV2 Expression-State Consistency、MV3 Temporal Continuity、MV4 Text vs Text+Video 的人工或实验记录。
