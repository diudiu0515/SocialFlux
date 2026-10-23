# SocialFlux 人工标注站

## 逐场景标注流程 v2

沿用已发布的逐场景流程 v2，本次将绑定的视频更新为原生 Seedance state 素材。

新领取的 offline 任务依次完成：公开背景与角色卡 → 逐轮公开对话 → 题目视频 → 8 道首次作答（T1/T2/T3 = 3/2/3）→ 机器答案对照与最终答案 → 逐轮 state 审核 → 下一场景。已有恢复码保留原流程。

每一步由服务端校验并锁定，原始答案与最终答案分别保存。机器答案合理性须逐题选择；全部 8 题锁定后可查看机器答案、私有证据与所有已提供 state。state 以更新前、变化量、更新后的表格展示，每轮及初始状态都须判断；未完成不能进入下一场景。公开对话审核只使用各题公开历史，A/B 差异保留，不提前展示私有 state 或未来分支。同一视频复用时审核一次，允许不影响判断的轻微瑕疵。

GPT50_001/009/023/033 仅有 3 轮同源记录，035/040/050 分别有 6/4/5 轮。页面明确提示不完整，并要求确认缺失部分无法审核；不得用其他轨迹替代或补造。其余 43 个场景提供 10–12 轮。新流程审核导出在 `scenario_human_review`，版本和阶段锁定保留在 `workflow.scenarioFlow`；历史 `gate2_human_review` 不冒充新流程审核。

验证：`node --test tests/scenario-flow.test.mjs tests/scene-sequence.test.mjs tests/research.test.mjs tests/gate2.test.mjs`。浏览器：`tests/scenario-flow-browser.cjs`，仅允许隔离本地地址和数据库。

入口：[SocialFlux 标注站](https://socialflux-annotation-demo-20261021.junqiao24.chatgpt.site)。沿用原 Sites 项目和持久化 D1；参与者保存答案不依赖 AutoDL。GitHub 保存源码，GitHub Pages 尚未启用。

`annotation400-seedance-state-20261023-v3` 已随 Sites v21 发布，沿用原站点和 D1。视频流程见 [State 视频说明](../../docs/operations/SEEDANCE_STATE_VIDEOS.md)。

## 材料与作答流程

50 场景、400 道英文题，每场景 T1/T2/T3 为 3/2/3。全部 300 道 T1/T3 使用 100 段约 5 秒的原生 Seedance 视频，同一历史节点供多道题复用；100 道 T2 只使用文字。短片只朗读对应 checkpoint 短句，完整对白保留在题面。Online 使用 326 段约 4 秒的新版素材，原素材 ID、事件类别和触发条件保持不变。

每组 5 场景、40 题，按固定顺序进行：公开背景与角色审核 → 逐轮公开对话审核 → 视频审核 → 当前场景 8 题作答并锁定 → 查看机器答案与显式 state、修订最终答案并判断机器答案合理性 → 逐轮 state 审核 → 提交后进入下一场景。不能任意选择场景；后续场景的证据与答案由服务端隔离。机器候选答案不等同于人工确认的正确答案。

进行中导出只包含已完成及当前场景的媒体绑定和审核任务哈希，完成整组后导出全部 40 题。格式仍为 `socialflux_human_gt_v1`，Lab 可导入；新旧媒体版本分别统计，不沿用旧片的人工通过记录。机器语音、口型和文件检查也不代表人工自然度审核通过。

Lab 主标注入口指向同一站点。`/lab#human` 提供回执导入与裁决；`/offline-annotation` 仅保留旧任务恢复。

## 保存与旧记录

公开页面无需平台账户；领取任务使用研究者原完整 `#invite` 链接。邀请验证后进入 HttpOnly cookie，并从地址栏移除。答案自动保存到 D1 的 `demo_sessions`；匿名编号与个人恢复码支持跨设备恢复。revision 冲突返回 409，保留客户端草稿。不得把真实邀请、恢复码或参与者记录提交 Git。

旧题目、标注和恢复码保留。按用户要求清理的旧视频由页面明确标为已退役，不将新片冒充旧证据。旧会话点击“保存并进入新版入口”可另开新版任务；原答案不自动转填。导出旧记录仍可用，接触排除保持有效。

新任务继续开放 offline 文字和视频两种条件；T2 在视频组中也只有文字。历史 T4 记录按原版本恢复，当前不新增 T4 派发。参与者只可下载本人记录。

## 源码与构建

- `app/demo.tsx`、`app/research-workspace.tsx`：入口和逐场景作答。
- `lib/research-protocol.ts`、`lib/store.ts`：阶段锁定、持久化与版本恢复。
- `lib/research.ts`、`lib/gate2.ts`：冻结材料及阶段可见范围。
- `app/media-video.tsx`、`data/retired-media.json`：旧视频退役提示。
- `data/*server.json`、历史媒体映射及 `public/media/`：从同一冻结备份恢复。GitHub 不包含私有证据、视频、回执和数据库，仅克隆源码不能构建完整标注站。

Node >= 22.13。保留 `.openai/hosting.json` 原 project ID、DB 绑定和 Vinext 集成。研究仓库生成完整材料后，在站点目录构建。发布必须使用 Sites source helper 同步源码并打包。

首次创建隔离本地数据库时，按顺序执行 `drizzle/0000_bright_prism.sql`、`0001_bouncy_frightful_four.sql`、`0002_marvelous_hannibal_king.sql`，Wrangler 必须使用 `d1 execute DB --local`。已有库只应用尚未执行的迁移。`DEMO_INVITE_SHA256` 使用被忽略的本地环境文件，生产沿用原 Sites secret。

## 验证

类型检查：`node node_modules/typescript/bin/tsc --noEmit`。

场景锁定与版本恢复：`node --test tests/scene-sequence.test.mjs tests/research-storage.test.mjs tests/research-snapshots.test.mjs tests/research.test.mjs`。

完整浏览器回归：`tests/scenario-flow-browser.cjs`、`tests/legacy-flow-recovery-browser.cjs`，只连接隔离本地地址和数据库，不向生产写测试标注。最终包只保留当前 100 段 Offline 与 326 段 Online；历史题目和回执版本映射保留。发布压缩包、解包文件和 tar 均须低于 256 MiB。
