# SocialFlux 人工标注站

当前入口：[SocialFlux 标注站](https://socialflux-annotation-demo-20261021.junqiao24.chatgpt.site)。使用原 Sites 项目和持久化 D1；参与者保存答案不依赖 AutoDL。GitHub 保存源码，GitHub Pages 尚未启用，不把待发布地址当作可用站点。

**Sites v18 已于 `2026-10-23T04:48:30.352242+00:00` 发布成功。** 已发布源码为 `ba5b42658a35dea0b64615b0d39dc5bb5cbf3522`，部署为 `appgdep_6adae70918808191ab725abadb5a3629`。公网匿名页面与状态 API 返回 200，50 场景／400 题／150 媒体／20 个 offline 分组；1 条 4.6 秒新片完整播放并解码音频，1 条旧 31.16 秒样本下载 SHA 与元数据通过，320／390 像素手机无溢出。公网未领取任务或写生产记录，旧会话恢复及完整逐场景流程由隔离本地检查覆盖。详见 [发布报告](../../reports/experiments/2026-10-23_offline_checkpoint_annotation_integration.json)。

使用已绑定当前版本的 [均衡 40 个分配](../../reports/experiments/2026-10-23_offline_annotation_assignments_balanced.csv) 或 [节省 30 个分配](../../reports/experiments/2026-10-23_offline_annotation_assignments_economical.csv)。研究者仍需填写实际匿名编号、截止时间及回执位置；分配数不是人数，同场景槽位必须由不同实际参与者承担。[派发指南](../../docs/operations/ANNOTATION_DEMO.md#2026-10-23-offline-派发指南) 说明独立覆盖、回收和第三人裁决。人工观感审核及正式 Gate 仍未完成，7 条神情重点复核不能视为通过。

## 当前材料与流程

当前短片 release 为 `annotation400-checkpoint-20261023-v2`，dataset SHA 为 `4859edec0ed4a00e5ee98b908b44efc930f7a1b56e774fa50c6ec34aa75ef854`。50 个场景、400 道英文题，每场景 T1/T2/T3 为 3/2/3。150 段题目视频均为 4.6 秒，每段只朗读一句 checkpoint；完整对白保留在文字题面。短句并不声称覆盖完整对白。机器筛查不代表人工质量通过。

每组 5 场景、40 题，按冻结顺序进行：当前场景 8 道盲答全部锁定 → 独立环境判断锁定 → 查看本场景机器候选及私有证据、完成 GT 和已分配审核 → 提交后进入下一场景。400 道题均有机器候选，但不直接当作正确答案。后续场景内容和写入受服务端限制，已锁定判断不可覆盖。

进行中导出只包含已完成及当前场景的媒体绑定和审核任务哈希，完成整组后导出全部 40 题。格式仍为 `socialflux_human_gt_v1`，可由 Lab 导入；新旧版本分别统计，不能沿用旧视频的人工通过记录。

页面保留场景进度、当前题目导航和实际作答／核对表。重复核对侧栏和当前场景的禁用导航已删除。Lab 主入口跳到同一标注站；`/offline-annotation` 仅供旧任务恢复，不再新建长视频任务。

## 邀请、保存与旧记录

公开访问无需平台账户；领取任务仍使用研究者的完整 `#invite` 链接。邀请验证后移入 HttpOnly cookie，并从地址栏移除。匿名编号与个人恢复码用于跨设备恢复；恢复码含 256 位随机数，服务器以 SHA-256 摘要查询。不得将真实邀请或恢复码提交 Git。

答案自动保存到 `demo_sessions`，revision 冲突返回 409，保留客户端草稿。既有六题、综合审核、300／400 题以及 T4 会话按原冻结版本恢复。旧长片任务会明确提示，并提供“保存并进入新版入口”；保留旧恢复码后可另开新版，原答案不转填。首次独立作答的接触排除保持有效。

新任务只开放 offline 文字和音视频条件，T4 不在本轮新分配中。历史 T4 评分、媒体及恢复支持保留。参与者只能下载本人的记录；所有者可通过 Sites 数据库工具读取汇总，没有公开的全量导出接口。

## 源码结构与本地构建

- `app/demo.tsx`：邀请、领取和恢复入口；`app/research-workspace.tsx`：逐场景作答与核对。
- `lib/research-protocol.ts`：阶段转换和锁定；`lib/store.ts`：持久化、版本与并发控制。
- `lib/research.ts`、`lib/gate2.ts`：冻结材料及阶段可见范围；`lib/research-storage.ts`：还原去重历史输入。
- `data/*server.json`、媒体历史映射及 `public/media/`：从同一冻结备份恢复。GitHub 不包含私有证据、视频、真实回执或数据库，仅克隆源码不能构建完整站点。

Node >= 22.13。保留 `.openai/hosting.json` 的原 project ID、DB 绑定和 Vinext 集成。安装依赖后，在研究仓库根目录运行存储生成器，再进入站点构建：

```sh
python scripts/build_research_storage.py --site web/participant_demo --audit build/research-storage-audit.json
cd web/participant_demo
npm run build
```

首次创建隔离本地数据库时，依次执行 `drizzle/0000_bright_prism.sql`、`0001_bouncy_frightful_four.sql`、`0002_marvelous_hannibal_king.sql`，使用 Wrangler `d1 execute DB --local`。数据库已存在时只应用未执行的迁移。`DEMO_INVITE_SHA256` 通过忽略的本地环境文件配置；生产使用原 Sites secret。`npm start -- --port 8012` 启动本地站点。

## 验证与发布

类型检查：`node node_modules/typescript/bin/tsc --noEmit`。场景锁定与旧版本恢复：`node --test tests/scene-sequence.test.mjs tests/research-storage.test.mjs tests/research-snapshots.test.mjs`。浏览器回归使用 `tests/checkpoint-scene-sequence-browser.cjs`，必须指定隔离本地地址和数据库，不向生产写入测试标注。

通过 Sites source helper 同步精确源码并打包，保存版本后部署；必须看到成功回执才可宣称上线。压缩 archive、解包后的全部文件以及 tar 本身体积均须低于 256 MiB。发布包保留 277 个历史媒体及 150 个短片，共 427 个 MP4；不把本地 33 个未派发 T4 别名副本复制回来。删除历史媒体前须确认所有恢复版本的实际 URL 引用。

当前发布回执见 `build/short-video-publication-20261023.json`；历史流程与部署记录见 `docs/operations/ANNOTATION_DEMO.md`。历史文字描述不代表当前线上版本。
