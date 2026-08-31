# EmoTree 项目结构

```text
emotree/
├── worlds/                         # 按 Story World 组织的数据
│   ├── IA001/
│   │   ├── story.json              # 机器可读 Story World
│   │   ├── screenplay.md           # 人类可读剧本与剧情树
│   │   └── tasks/
│   │       ├── T1/                 # 本 world 的 T1 配对实例包
│   │       ├── T2/                 # 本 world 的 T2 配对实例包
│   │       └── T3/                 # 本 world 的 T3 配对实例包
│   └── IA002/                      # 与 IA001 使用相同结构
├── tasks/                          # 跨 world 统一任务约束
│   ├── README.md                   # 三任务索引与固定数量
│   ├── TASKS_OVERVIEW_v0.2.md      # 总体定义、标签与划分原则
│   ├── T1/
│   │   ├── TASK1_SPEC_v0.2.md
│   │   ├── model_output_schema_v0.2.json
│   │   ├── human_annotation_schema_v0.2.json
│   │   └── t1_probability_utils.py
│   ├── T2/                         # 同样四类文件
│   └── T3/                         # 同样四类文件
├── prompts/                        # 全部固定、版本化的运行/任务/标注 prompt
├── talkinghead_generation.md        # 状态触发式 Talking Head 设计
├── shared/                         # Story World 共用创作规范与兼容入口
│   ├── interactive_story_generation_prompt.md
│   ├── STATE_ONTOLOGY_v0.1.md
│   └── schema/interactive_story_schema_v0.1.json
├── interactive_benchmark/          # 共用转换、实例 Schema 与测试
│   ├── scripts/convert_interactive_to_benchmark.py
│   ├── schema/
│   │   ├── benchmark_instance_schema_v0.2.json
│   │   └── annotation_overlay_schema_v0.1.json
│   └── tests/
├── demo/                            # On-Policy 交互环境、状态引擎与三端网站
├── environment/                     # 状态、记忆、响应、终止和 multimodal 表达层
├── providers/                       # 统一模型 provider 与 OpenAI-compatible 适配
├── policies/                        # 模型 policy 与 controlled validation policy
├── rollout/                         # 完整轨迹 runner 与原子日志
├── offline/                         # 从 rollout 提取 T1/T2/T3 候选
├── evaluation/                      # 环境有效性 scorecard
├── configs/scenarios/               # 0–10 Phase-A MVP 场景配置
├── scripts/                         # 可直接运行的 Phase-A 脚本
├── build/interactive_benchmark_v0.2/ # 48 条全局汇总实例
├── TOP_CONFERENCE_RESEARCH_PLAN.md
└── PROJECT_STRUCTURE.md
```

## 分层职责

### `worlds/`

一个 world 的剧情源和所有任务实例放在同一目录。`story.json` 是 converter 的唯一剧情数据源；`screenplay.md` 用于人工审稿。`tasks/T1|T2|T3` 各包含 `instances.jsonl`、两个模态子集、`manifest.json` 和简短 README，不重复保存全局任务约束。

### `tasks/`

三个任务的统一规范中心。每个任务固定放置四件核心资产：任务定义、模型输出 Schema、人类标注 Schema、概率/评分工具。修改任务含义时先改这里，再重建所有 world 实例。

### prompts/

所有会传给模型的固定 prompt 都放在这里，以带版本号的 Markdown 文件保存。manifest.json 保存 SHA-256，prompts.loader 在读取时校验内容未被静默修改。运行时代码不得重新硬编码 prompt；新增或修改 prompt 时必须新增版本、更新 manifest 并运行回归测试。

### shared/

保存生成新 world 时共同使用的 Story Schema、状态词表和创作规范。旧的 shared/interactive_story_generation_prompt.md 仅作为兼容入口，规范正文以 prompts/story_generation_v0.1.md 为准。

### `interactive_benchmark/`

保存跨 world 的构建基础设施。converter 将 `worlds/*/story.json` 转成 benchmark instance；通用 Schema 约束所有任务共享的 envelope；测试检查数量、配对、泄漏和任务专用约束。

### `build/`

保存可再生聚合产物。interactive_benchmark_v0.2 的 48 条公开实例由 converter 生成并可提交；pipeline_v1 含私有 master trajectory，默认只在本地生成并由 .gitignore 排除。这里的文件不手工编辑。

## 新增 world

1. 建立 `worlds/IAxxx/story.json` 与 `screenplay.md`；
2. 用 `shared/schema/interactive_story_schema_v0.1.json` 校验；
3. converter 生成全局实例；
4. 按 `tasks/T1|T2|T3` 的固定采样规则写入该 world 的三个任务包；
5. 确保同一 `semantic_instance_id` 的 text/text_video variant 不跨 split。
