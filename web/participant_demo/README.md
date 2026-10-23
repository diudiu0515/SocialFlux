# SocialFlux 人工标注与 GT

2026-10-23 改为 **逐场景顺序标注**：新领取的 offline 任务按冻结分组的场景顺序完成。每场景 8 道盲答全部锁定后，先完成该场景已分配的独立环境判断，再开放本场景机器候选答案对照、私有证据和 GT 核对。全部 GT 与环境／媒体核对提交后，才进入下一场景。后续场景的材料、答案和写入均受服务端限制；旧恢复码保持原流程与冻结材料，已锁定数据不迁移、不覆盖。

当前 400/400 道题均有对应有效选项的机器候选答案；候选并非已确认的正确答案。每个场景单独记录盲答锁定、环境判断锁定和提交时间。已完成场景的盲答与 GT 不可覆盖，跨设备恢复保留当前场景。导出仍为 `socialflux_human_gt_v1`，保留全部 40 题与场景顺序记录，现有 Lab 校验器可导入。题库、视频文件及素材质量状态未变。本次版本是否已发布以研究仓库的发布回执为准。

本轮材料是 50 场景、400 道 T1–T3 题，以及 475 个唯一 offline 审核任务：当前媒体 150、scenario 50、rollout 50（7 条部分轨迹）、必要环境专项 225。S1/S2 等机器消融不派人工；E1–E9 中已冻结的必要人工专项保留。其中 85 项为独立环境判断、390 项为后续审核。当前媒体 150 个与 E8 的 40 个旧批次视频不重合，全库实际涉及 190 个不同视频文件；每人只看所分配的片段。题目盲答、机器辅助 GT 与这些审核任务分别记录，材料准备不代表审核通过或正式 Gate 准入。

直接使用 [offline 均衡分配表：40 个分配](../../reports/experiments/2026-10-22_offline_annotation_assignments_balanced.csv)（每组 2 文字＋2 音视频）或 [offline 节省分配表：30 个分配](../../reports/experiments/2026-10-22_offline_annotation_assignments_economical.csv)（每组 1 文字＋2 音视频）。每题分别计划 4／3 名独立 GT 审核人，每媒体 2 名音视频审核人；分配数不是人数，同人不能跨相同场景条件。匿名编号、北京时间截止时间、回执收齐和核验状态待研究者填写。完整参与说明、逐组审核量、培训、裁决和签署要求见 [本轮 offline 派发指南](../../docs/operations/ANNOTATION_DEMO.md#2026-10-22-offline-派发准备分配与回收本地未发布)。

当前研究版 release：`annotation400-en-20261022-v1`。50 个已 rollout 场景，每场景 8 道英文题（T1/T2/T3 = 3/2/3），共 400 题。普通/Hard 配额为 T1 90/60、T2 60/40、T3 90/60；选项答案 A/B/C/D 各 100 个。Hard 是设计难度，尚待人工判断，机器候选不自动成为 GT。

沿用原 Sites 项目、公开受众和邀请/恢复码。原六题、综合视频审核、300 题人工 GT 及首次 400 题发布会话按原冻结版本恢复。

## T1–3

英文文字及音视频条件各 10 组，每组 5 场景 / 40 题。Sites v12 已开放全部 50 场景 / 400 题及 150 个音视频节点。素材已经过机器筛查，尚待人工质量核对；本地新版将逐视频审核纳入音视频组的最终提交要求，同一文件被多题引用时只审核一次。

每个 T2 题的两个历史共用同一个 ending 视频。视频只包含公开台词和表情线索，启用声音播放；私有状态和机器答案始终经阶段门控制。50 段 `identity-ref-*` 静音视频仅供生成时保持原有合成人物外观，不作为标注音视频材料。

工作台同时显示全库题量和本次分配题量。恢复旧记录时会明确提示新旧题量，并提供「保存并进入新版题库」入口：先保存旧草稿，返回最新版任务选择并保留匿名编号；领取新版时签发新的恢复码。旧恢复码仍绑定原题目和答案，旧答案不转填到新版。新任务仍需原邀请与参与确认，跨版本接触继续计入曝光排除。

新任务显示场景完成顺序，后续场景标记未解锁；只允许在当前场景内切换题目。GT 阶段提供独立的「场景与 rollout 核对」入口，完成最后一题后直接进入本场景核对，再继续下一场景。独立环境判断也按场景呈现，场景核对每人只填一次。切换前保存，已有会话与冻结分组保持不变。

当前顺序为：整组盲答及把握程度锁定 → 独立环境判断锁定 → 机器辅助 GT 与媒体／场景审核 → 最终提交。只有两次锁定后才开放合法私有 state、environment 材料、受控回放／分支和机器候选；原始盲答不可覆盖。GT 阶段提交最终答案、可接受选项、可用／修改／剔除及依据；多解不能标为唯一可用。当前没有单独的“私有证据 GT 初判锁定后再看机器建议”阶段，本轮不新增该阶段。所有标签均由人确认，机器候选不自动成为 GT。

私有证据只保存在服务端压缩包中，经恢复凭据及阶段门控制的 `/api/demo/evidence` 返回。初始页面、状态接口和客户端 JS 中不包含私有包；同组全部盲答锁定前直接请求也拒绝。T1 按截止点、T2 按 A/B 同结尾、T3 按预测窗口确定证据范围。

## T4（历史与后续范围，本轮不派发）

以下保留既有采样和评分说明。当前 offline 新任务入口不提供 T4 分配；本节不表示本轮完成了 T4 人工审核。

固定抽样 50 条已生成完整轨迹：总体 200（CF150 + GPT50），完整且格式有效 182；分层哈希抽样 CF150 38、GPT50 12，不查看分数选样。其余 18 条的排除原因与完整抽样名单在研究仓库 `reports/experiments/2026-10-22_human_gt_release.json`。此处是历史轨迹的评分校准，不是新 text/video 策略试验。

10 组，每组 5 轨迹。按目标达成、状态适应、风险管理、挫折恢复、关系结果打 0–10 整数分，每维说明依据并引用 1–3 轮。只有恢复可在没有挫折及修复机会时选择不适用。使用与 Claude 同样的公开文字证据及原始锚点评分；隐藏模型名称与机器分数，整组提交后显示逐维人工−Claude 差值。缺失分数不填零。

原有 11 条严格匹配的 Claude 评分。39 条补评使用用户明确授权的 www.autodl.art / claude-fable-5，由研究仓库后台执行，每条至多 2 次请求、最多 78 次，成功不重采样。调用及失败记录留存；JSON 引号修复保留原始文本及操作记录，不修改分数。补评分作为独立 server-only 文件附加，冻结材料与旧会话 hash 不变。

补评已于北京时间 2026-10-22 01:20 完成：39 次实际调用，31 条有效、8 条失败；连同原有 11 条，可用对照为 42/50。失败均缺少恢复维度的证据引用，CF150_001 还存在 JSON 代码块后的额外文字。失败保留原始输出并维持缺失，未换样、补零或重采样。执行报告位于研究仓库 `reports/experiments/2026-10-22_human_t4_claude_calibration.json`。

## 保存、汇总与论文表

标注工作区旁常驻「人工核对清单」，桌面随页面滚动保持可见，窄屏在顶部紧凑显示。本轮 T1–T3／Gate2 按阶段提示先盲答、再独立环境判断、最后核对私有材料和已分配媒体。提示卡与实际表单分别呈现，只有表单记录计入完成度。T4 触发与视频表单及其材料继续保留用于后续工作，缺口不计入本轮 offline 完成度；保留实现不表示已经部署。



答案自动保存到 D1，当前设备保留草稿；恢复码可跨设备继续。revision 冲突停止自动保存并保留本地草稿。阶段锁定与最终提交在服务端校验，提交后只读。个人下载格式 `socialflux_human_gt_v1`，保留材料/视频/轨迹哈希、盲答、机器辅助 GT、独立 T4 分数和曝光声明。

研究者在 Lab `/lab#human` 导入参与者 JSON；回执按 ID/revision 去重、原文件不覆盖。同一匿名编号只算一名审核人。两人一致形成共识 GT；任何分歧或题目问题进入第三人裁决，保留全部原始判断。本人盲答评测排除本人的 GT。共识标签不自动替代来源 Gate 准入。

Lab 论文表提供 GT 覆盖/分歧、人类盲答基线、T4 五维偏差/MAE/RMSE、逐轨迹差值及 Claude 评分覆盖/失败原因，均可导出 CSV、Markdown、LaTeX。没有人工数据时 n=0、指标 N/A。T4 先按轨迹对不同人取均值，再与同一轨迹同证据 Claude 分数配对。人的盲答也按同一人、同一题、同一条件去重，冲突重复不纳入统计。

## 开发与发布

本轮只做本地 offline 整理与验证，不执行发布，也不处理 Sites token。以下命令与历史托管步骤保留供后续明确安排发布时使用。

沿用下文的 Sites 构建、邀请与安全配置。新增 schema migration `0002_marvelous_hannibal_king.sql` 只追加 `assignment_json` / `workflow_json`，默认空对象，不改写旧列。

```sh
node node_modules/typescript/bin/tsc --noEmit --incremental false
node --experimental-strip-types --test tests/protocol.test.mjs tests/multimodal.test.mjs tests/research.test.mjs
```

隔离本地 D1 后运行 `tests/research-browser.cjs`（Playwright），仅允许 loopback 地址；测试含两个旧版本恢复、视频 URL、盲答泄漏边界、并发版本冲突、跨设备 GT 恢复、锁定、T4 不适用和手机布局。测试数据不进入生产 D1。

研究仓库：`python -m scripts.prepare_human_gt_release` 冻结数据；`python -m scripts.sync_human_t4_scores` 附加已完成且哈希匹配的补评分，再按 Sites source helper 发布；该同步不改变 dataset SHA。不要重新生成冻结包覆盖已分配会话。

---

以下为保留的第 2 版视频审核说明，**只适用于旧会话**。

# SocialFlux 受邀标注 demo

独立托管的参与者网站。匿名编号与随机恢复码用于找回一份标注，无需 ChatGPT 登录。新任务整合 **52 段视频、45 个场景、270 道关联公开题目**：45 段非语言前史视频与 7 段英文 talking-head 样片。按场景连续审核，每个视频只判断一次；不包含 author、参考答案、oracle、机器建议或研究后台。

7 段英文样片只覆盖选定场景的 T2 共同回应；45 段前史视频只有非语言线索。完整前史对白尚未齐全，本页面用于素材可用性筛选，不代表完整多模态条件已经就绪。没有视频的另外 5 个场景、30 道题不进入本次审核。

## 参与流程

研究者分发完整邀请链接，参与者填写匿名编号、既往参考答案接触情况及参与确认，保存恢复码后开始。场景中显示视频、英文台词（适用时）、公开表情与动作、关联题目及完整公开对话。视频可标为可用、需修改、不可用、无法判断，并记录台词、口型、自然度、表情、画音、情境或播放问题。

视频审核与题目答案分开保存。**52 段视频的审核为必填，270 道题作答选填**；已选答案需填写把握程度。完整播放会自动标记已查看，也可手动确认；无法播放时可直接记录播放问题。`watched` 是参与者自报或浏览器播放结束记录，不是独立验证的观看证明。负面判断须选择问题或填写说明，标为可用时须清除勾选的问题。

修改后自动保存到 D1，切换场景前也会保存；当前设备备份未保存草稿。用编号和恢复码可跨设备继续。revision 冲突时停止自动重试并保留本地输入；刷新后加载云端版本，旧草稿仍可下载。最终提交需独立审核确认，提交后锁定，可下载本人答案与视频审核 JSON。

旧版 GPT50_001 六题记录按原恢复码继续进入冻结文字任务，仍要求六题全部作答；新领取的任务进入综合审核。查看旧任务后可退出、用原邀请链接领取新的综合任务，并保存新的恢复码。

邀请凭据在 URL fragment 中传入，验证后移入 HttpOnly cookie 并从地址栏移除。邀请凭据仅用于领取新任务；已领取者凭个人恢复码访问记录。恢复码含 256 位随机数，服务器只用 SHA-256 摘要查询记录。数据库列 `user_id` 存的是该摘要，与平台账户无关。编号本身不授权访问，编号不要求全局唯一。

## 数据与复现

- `data/questions.json` 保留原六题冻结包，字节不变。`data/multimodal.json` 是新审核包，题目同样经过 `tasks.offline_choice.public_instance` 白名单投影；原始题库留在研究仓库本地，不进入网站源码。
- 新包 release 为 `offline-multimodal-review-20261021-v1`，dataset SHA-256 为 `5912f0b36db69f2a3d6f12fd602d604333f318f41c79dc9cbe9ebaf85a873e27`。52 个原始 MP4 放在 `public/media/`，用完整内容 SHA 命名；284 个视频与题目的绑定保留对应证据 ID。
- 在研究仓库根目录运行 `python -m scripts.export_participant_multimodal --help` 查看复现导出参数。脚本核验题库、题目和视频 SHA，不会生成新视频或发布私有标签。
- `dataset_sha256` 标识发布包；每个 item 哈希指向原始完整题目，供研究者本地审计。不要在同一发布版本中重写题目。
- `demo_sessions` 保存匿名编号、既往接触情况、答案、视频审核、备注、版本、时间戳及题目/媒体哈希。新增迁移只追加 `media_reviews_json` 和 `media_hashes_json` 两列，默认 `{}`，不改写旧记录。无姓名、邮箱或平台用户标识；备注中应避免个人信息。
- 并发修改使用 revision 比较更新，冲突返回 409，保留客户端输入。重复提交返回同一回执。演示结果标记 `formal_ground_truth: false`，不能直接作为正式 GT。
- 网站所有者可使用 Sites 的数据库查看功能读取 `demo_sessions`。没有公开的全量导出接口；参与者导出始终由自己的恢复凭据限定。
- 新导出格式为 `socialflux_multimodal_review_v1`，包含 `answers`、`media_reviews`、`item_hashes`、`media_hashes`。视频评价不自动成为题目标准答案，也不自动批准素材；本次混合查看不是随机分配的 text / video 对照实验。旧记录保留原文字导出格式。

## 本地开发

Node >= 22.13。保留 Sites 的 Vinext 构建集成与 `.openai/hosting.json`；生产绑定为 `DB`。先安装依赖，再执行：

```sh
npm run db:generate  # 仅在修改 schema 时生成新的迁移
npm run build
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0000_bright_prism.sql
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0001_bouncy_frightful_four.sql
npm start -- --port 8012
```

本地启动前将 `DEMO_INVITE_SHA256` 放到 `dist/server/.dev.vars`，这是随机邀请字符串的 SHA-256 hex 值；文件必须保持忽略。生产环境通过 Sites runtime secret 配置同名键，不写进 hosting manifest 或源码。邀请链接格式为 `https://<site>/#invite=<random-url-safe-token>`；不要提交真实邀请凭据或恢复码。

## 验证与发布

```sh
node node_modules/typescript/bin/tsc --noEmit --incremental false
node --experimental-strip-types --test tests/protocol.test.mjs tests/multimodal.test.mjs
```

`tests/multimodal-browser.cjs` 通过 stdin 接收 `{url, invite, output, legacyCode, legacyAlias}`，需要 Playwright 和已安装 Chromium。仅针对独立本地数据库运行，先在旧结构中写入一份六题测试草稿，再应用第二个迁移。覆盖 52 段视频地址及字节核验、原生播放与跳转、英文台词、选填答题、乱序审核、跨设备恢复、冲突草稿、校验、最终提交、锁定、幂等、导出、旧版恢复，以及 1440px 桌面与 360/390px 手机布局。本地静态资源模拟器对 Range 请求可返回完整文件，此时校验完整 SHA；未据此声称验证了生产分段传输。测试数据不进入生产 D1。原 `tests/browser.cjs` 留作首版流程参考，当前新任务验收使用综合测试。

发布使用 Sites skill 的 source helper：检查/构建 → 提交并推送精确源码 → 打包 → save_site_version → deploy_site_version。托管入口允许匿名浏览，应用层仍验证邀请及个人恢复码；机器人索引已关闭。D1 迁移由托管部署应用。`.dev.vars`、`.wrangler`、浏览器 QA 输出及生产凭据都不进入发布包。

中文字体沿用 Noto Sans SC 的 OFL 授权，子集覆盖全部公开题面和界面文案。新增文字后可执行 `python scripts/subset-font.py /path/to/NotoSansSC.ttf` 重建，需要 `fonttools[woff]`。


## Gate2 随题人工核对（2026-10-22）

新增离线任务先锁定整组盲答，再独立判断 E1 状态方向和 E4 释义等价性；锁定后，在各场景题目旁核对场景、完整 rollout、E2 五维、E3/E5/E7 干预、E8 视频音轨与 E9 时间尺度。同一场景只填一份，自动保存并随恢复码恢复。旧任务保留原流程。

私有材料只从服务器开放，未锁定独立判断时不能访问机器结果。回执增加 `gate2_human_review`，记录材料哈希、任务哈希、锁定时间与人工原始判断。lab 导入后按任务与匿名编号去重；材料准备和人工覆盖不自动代表 Gate2 正式通过。

材料由 `scripts/build_gate2_annotation.py` 从冻结证据生成。服务器包保留历史版本，后续加入释义样本不会破坏既有任务的恢复与回执。E2 的一条失败前缀标明“部分轨迹，仅诊断”。

验证：`node --experimental-strip-types --test tests/gate2.test.mjs`；浏览器检查 `tests/gate2-browser.cjs` 只允许隔离的 loopback D1。


## 逐场景流程验证

`node --experimental-strip-types --test tests/scene-sequence.test.mjs` 验证跨场景防绕过、不可覆盖、完整审核前禁止前进及逐场景时间记录。`tests/scene-sequence-browser.cjs` 必须连接隔离本地 D1；覆盖五场景／40 题、自动保存、答案对照、刷新与跨设备恢复、完整回执、音视频材料及手机布局。生产数据库不写入测试记录。
