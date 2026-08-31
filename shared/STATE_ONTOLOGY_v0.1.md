# EmoTree 统一状态词表 v0.1

## 1. 使用原则

统一词表的作用不是要求每个故事使用所有状态，而是避免不同编剧用不同名字描述同一概念，或者把情绪、性格和现实风险混在一起。

每个故事推荐选择：

- 3–6 个情绪状态；
- 2–4 个应对倾向；
- 2–4 个关系状态；
- 1–3 个情境风险。

总数推荐 8–14 个。太少无法表达历史差异，太多会使标注疲劳且数值失去意义。

全部维度范围为 0–100。`50` 不是“正常人水平”，只表示该故事量尺中的中等程度。

## 2. 第一层：情绪状态 `emotion`

情绪变化较快，回答的是“角色此刻大致体验到什么”。

| ID | 中文名 | 操作定义 | 不要与什么混淆 |
|---|---|---|---|
| `sadness` | 难过 | 面对失去、失败或关系破裂的低唤醒负性体验 | `pain` 更强调持续心理负担 |
| `anger` | 愤怒 | 因阻碍、不公或越界产生的对抗性负性体验 | 不等于实际采取对抗行动 |
| `fear` | 恐惧 | 对明确威胁或损失的警觉 | `anxiety` 的对象可以更不确定 |
| `anxiety` | 焦虑 | 对不确定未来结果的持续紧张 | 不等于现实风险本身 |
| `guilt` | 内疚 | 认为自己的行为可能伤害他人或违背责任 | `shame` 更指向自我评价 |
| `shame` | 羞耻 | 感到自己被贬低、暴露或“不够好” | 不等于低自尊这一长期状态 |
| `pain` | 心理痛苦 | 难以快速消退的主观心理负担 | 不作临床疼痛或诊断解释 |
| `disappointment` | 失望 | 重要期待落空后的负性体验 | 需要存在先前期待 |
| `betrayal` | 被背叛感 | 可信任对象违背承诺或关系义务的体验 | 不直接等同于客观背叛事实 |
| `relief` | 释然 | 威胁降低或负担暂时解除后的放松 | 不必意味着问题完全解决 |
| `hope` | 希望 | 认为重要目标仍有实现可能 | 不等于客观成功概率 |
| `gratitude` | 感激 | 认为他人为自己提供了有价值帮助 | 不等于义务或服从 |
| `loneliness` | 孤独 | 感到缺少理解、支持或关系连接 | 不等于物理上独处 |

第一版建议优先使用前 10 项；后 3 项按故事需要加入。

## 3. 第二层：动机状态 `motivation`

这类状态比瞬时情绪稳定，但又不是人格。它回答“角色此刻有多强的行动准备”。

| ID | 中文名 | 操作定义 |
|---|---|---|
| `resolve` | 决心 | 继续某项行动或坚持目标的准备程度 |
| `avoidance_urge` | 回避冲动 | 退出、沉默或减少接触的倾向 |
| `repair_intent` | 修复意愿 | 主动修复关系或弥补后果的准备程度 |
| `resistance_intent` | 抵抗意愿 | 拒绝压力、规则或不公平要求的准备程度 |

说明：现有故事为了兼容性可能把 `resolve` 放在 `emotion` 中；从 v0.2 起建议迁移到 `motivation`。

## 4. 第三层：应对倾向 `coping`

应对倾向只表示角色在本故事中的行为取向，不声称其人格永久改变。

| ID | 中文名 | 操作定义 | 价值中立说明 |
|---|---|---|---|
| `assertiveness` | 坚定表达 | 清楚表达需求、边界和不同意见 | 不等于攻击性 |
| `endurance` | 忍耐 | 在压力下继续承担或延迟反应 | 可能保护长期目标，也可能累积伤害 |
| `self_respect` | 自尊维护 | 维护自己贡献、边界和主体性的程度 | 不等于自恋或面子 |
| `moral_courage` | 道德勇气 | 在个人有代价时仍按责任原则行动 | 不预设每次冒险都正确 |
| `strategic_patience` | 策略耐心 | 为长期目标延迟对抗并保存行动空间 | 不等于胆怯 |
| `compliance` | 服从倾向 | 按权威或制度要求行动的倾向 | 不自动等于错误选择 |
| `emotion_suppression` | 情绪压抑 | 主动减少外显表达或不处理当前感受 | 不等于情绪本身较弱 |
| `evidence_seeking` | 证据导向 | 倾向记录、核实和通过程序行动 | 不等于缺乏情感 |

现有 JSON 使用组名 `trait`。为兼容 v0.1 可以继续使用，但研究文档和标注界面应显示为“故事内应对倾向”，不要称为稳定人格。

## 5. 第四层：关系状态 `relationship`

| ID | 中文名 | 操作定义 |
|---|---|---|
| `trust` | 信任 | 相信对方会诚实、可靠并顾及自己重要利益 |
| `hostility` | 敌意 | 对方采取惩罚、排斥或对抗行为的倾向 |
| `perceived_safety` | 关系安全感 | 在对方面前表达真实需求而不受报复的预期 |
| `respect` | 尊重 | 承认对方能力、贡献、边界或主体性的程度 |
| `affiliation` | 亲近 | 希望维持连接、合作或情感接近的程度 |
| `dependence` | 依赖 | 自己的重要目标受对方资源控制的程度 |
| `power_asymmetry` | 权力不对称 | 双方控制资源、规则或退出成本的不平衡程度 |
| `obligation` | 义务感 | 认为自己应向对方回报、服从或承担责任的程度 |

具体故事可以给关系状态加角色前缀，例如 `advisor_trust`、`director_hostility`。其 `ontology_ref` 分别指向 `relationship.trust` 和 `relationship.hostility`。

## 6. 第五层：情境风险 `risk`

风险是世界状态，不是情绪。角色可能风险很高但并不焦虑，也可能风险较低却非常焦虑。

| ID | 中文名 | 操作定义 |
|---|---|---|
| `goal_failure_risk` | 目标失败风险 | 核心目标无法实现的可能性与严重度 |
| `retaliation_risk` | 报复风险 | 因表达、举报或拒绝而受到惩罚的风险 |
| `career_risk` | 职业风险 | 失业、晋升、推荐或职业声誉受损风险 |
| `graduation_risk` | 毕业风险 | 答辩、签字、延期或学位获得受阻风险 |
| `financial_risk` | 经济风险 | 收入、债务或关键资源受损风险 |
| `social_exclusion_risk` | 社会排斥风险 | 被团队、家庭或社群排除的风险 |
| `physical_safety_risk` | 人身安全风险 | 自身或他人的身体安全受到影响的风险 |
| `user_safety_risk` | 用户安全风险 | 产品或服务对用户造成严重负面影响的风险 |
| `evidence_loss_risk` | 证据灭失风险 | 关键记录无法保存、核验或追溯的风险 |

现有 JSON 为简化引擎，把风险维度放在 `relationship` 组中。v0.1 Schema 继续兼容；后续数据迁移时建议拆成独立 `risk` 组。

## 7. 命名规则

1. 机器 ID 使用小写 `snake_case`；
2. 一个 ID 只表达一个概念，避免 `sad_and_angry`；
3. 角色特定状态使用 `<role>_<canonical_id>`；
4. 每个状态声明 `name`、`min`、`max`，建议再声明 `ontology_ref`；
5. 新增词必须给出操作定义和与相邻词的区别；
6. 不使用带道德结论的词，如 `goodness`、`cowardice`、`correctness`；
7. 不把选择动作写成状态，如 `reported_to_school` 应是 flag，不是心理状态。

推荐声明方式：

```json
{
  "advisor_trust": {
    "name": "对导师的信任",
    "ontology_ref": "relationship.trust",
    "type": "integer",
    "min": 0,
    "max": 100,
    "target_character_id": "STUDENT",
    "toward_character_id": "ADVISOR"
  }
}
```


## 8. v0.1 推荐核心词表

如果想先快速统一所有故事，可以优先只使用以下 20 个概念：

```text
emotion:
sadness, anger, fear, anxiety, guilt, shame, pain,
disappointment, relief, hope

motivation/coping:
resolve, assertiveness, endurance, self_respect,
moral_courage, strategic_patience

relationship/risk:
trust, hostility, perceived_safety, goal_failure_risk
```

题材特有风险如 `graduation_risk` 和 `user_safety_risk` 可以在此基础上增加。

