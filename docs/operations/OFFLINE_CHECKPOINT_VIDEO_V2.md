# Offline 4–5 秒 checkpoint 视频：v18 已发布

本轮按研究者要求把每个视频改成一句 checkpoint，目标 **4.6 秒**，主要观察口型、神情和注视。完整公开回复仍保留为文字。新短句是公开原文的摘句或忠实精简，不声称视频仍逐字朗读完整回复。

这是独立的素材修订。**400 道题与 150 条短片已随 Sites v18 发布，并通过公网只读检查；人工质量审核仍为 pending。** 发布与机器检查不代表人工验收通过。原 v15 长视频、旧题库及全部历史审核版本均保留，新媒体不得沿用旧视频哈希对应的通过记录。

## 配置与输出

- `configs/offline_checkpoint_v2_20261022.json`：150 条短句、完整原回复、精确支撑引文、是否逐字摘句和省略说明；仅含公开材料。
- `data/offline_checkpoint_v2_20261022/manifest.json`：候选请求清单。每个目录以新请求 SHA 分版，源题库 SHA 与原请求 SHA 保留。
- `scripts/render_annotation400_revision.py`：prepare、audio、asr、motion、video、sync，以及逐节点串联的 render 阶段。
- `offline/revision_motion.py`：短片专用非循环动作曲线；明确线索控制表情或注视，没有公开线索时不增加情绪动作。001-t1 的短暂紧张幅度经过单帧对照校准，其他角色不共用其放大系数。
- `scripts/package_checkpoint_revision.py`：制作可离线查看的 HTML 和 MP4 预览包，内嵌公开材料，无 API、登录、外部字体或服务器依赖。
- `scripts/export_checkpoint_annotation.py`：向独立站点副本导出新的 400 题媒体版本及对应 Gate2 媒体审核；不写原冻结题库和审核目录，不自动部署或激活。
- `scripts/build_research_storage.py`：从站点当前冻结输入生成去重旧版本和压缩历史映射，精确校验展开结果；只改变运行时存储，不修改原始文件或 dataset SHA。
- `data/offline_checkpoint_annotation_20261023/`：本地新版 `release.json`、`gate2-release.json`、覆盖统计及旧素材 SHA 保留记录；这些制作侧数据不进入 GitHub。

旧题库、角色图、模型权重和原始媒体是本地依赖，按原素材清单恢复；GitHub 源码不内嵌这些文件。脚本不会自动下载模型或调用收费生成 API。

## 400 题标注页接入

新版 `annotation400-checkpoint-20261023-v2` 保留 50 个场景、400 道完整文字题、题目 SHA、私有证据和分组；每题仍绑定两个对应位置的视频，共用 150 个独立片段，每条 4.6 秒、合计 690 秒。媒体字段分别保存短 `spoken_text`、`spoken_scope=checkpoint_sentence`、完整 `full_public_response` 和精确 `source_quote`。页面明确说明短片只朗读一句 checkpoint，完整回复仍须阅读题面。

最终接入源码合并了远端 v16 的逐场景流程。每组仍为 5 个场景、40 题，新会话先显示当前场景的 8 题：完成并锁定盲答，再完成独立环境判断、题目与媒体审核，才解锁下一场景。场景完成记录、原盲答和独立判断保持锁定；当前场景的私有材料及机器候选仅在相应阶段开放。历史无 `sceneSequence` 的整组会话仍按原流程恢复。

进行中的逐场景回执导出仅包含已完成场景与当前场景的媒体绑定及 Gate2 `task_hashes`，不导出尚未解锁场景的视频 URL、SHA，或含视频 SHA 的媒体审核任务 ID；全部场景完成后才导出整组媒体与任务。旧整组回执的导出保持原样。此次过滤与页面/API 的场景范围控制配套，避免通过导出绕过后续场景的材料限制。

当前已发布数据 SHA 为 `4859edec0ed4a00e5ee98b908b44efc930f7a1b56e774fa50c6ec34aa75ef854`，Gate2 包 SHA 为 `3be0b7a12e695461f7771529a0da866cdf8cbb71726fad9231c337c0d2adf7ec`。导出保留原 11 个 Gate2 版本及 422 项非媒体审核，另生成 150 项新版逐片审核。旧会话按原 dataset、媒体和审核包哈希恢复，不能静默换成新短片。

150 条短片的当前输入 SHA、独立 ASR、逐轨迹同步证据及实测时长均通过机器检查；20 条有帧级抽查，其中 7 条需要重点复核神情。这些提示仅出现在盲答后的媒体审核材料，不向盲答者显示；它们是“帧级抽查，非完整观感验收”，不构成人工通过结论。

先在 `build/` 下准备带齐原冻结数据和历史媒体的独立站点副本，再运行：

```bash
python scripts/export_checkpoint_annotation.py \
  --site build/annotation-checkpoint-integration-20261023/site \
  --source-site build/annotation-checkpoint-integration-20261023/frozen-v15-source \
  --visual-review build/offline-video-revision-audit/visual-combined-review.json
python -m unittest tests.test_checkpoint_annotation_export tests.test_checkpoint_package
```

本轮将原 v15 的三份 `data/` 站点输入保存在上述 `frozen-v15-source` 目录。发布后重建必须显式选择这一冻结长片输入，不能把已切换为短片的当前站点当作原版来源。该目录不提交 GitHub，应随冻结材料备份恢复。

每次导出、替换当前数据或合并到另一站点副本后，**必须在实际将要构建的副本运行存储生成器，再执行 build**：

```bash
python scripts/build_research_storage.py \
  --site build/annotation-checkpoint-integration-20261023/site \
  --audit build/annotation-checkpoint-integration-20261023/research-storage-roundtrip-audit.json
npm --prefix build/annotation-checkpoint-integration-20261023/site run build
```

将示例 `--site` 换成实际最终发布副本路径。生成器写出 `data/research-previous-delta-server.json` 和 `data/research-media-history-server.json`；旧完整版本中的 619 个相同证据 blob 及 `t4`、`rubric`、`sampling` 从当前版本复用，历史媒体数组使用 gzip 存储。生成后展开的完整对象须与原件逐项一致；原 `research-server.json`、`research-20261022-v1-server.json` 和 `research-media-history.json` 均保留原字节。运行时只读取派生文件和当前版本，按 base dataset SHA 拒绝过期派生文件，不会静默混用版本。Python 仅用于发布前生成，不进入 Sites 运行时依赖。更换根目录的数据后也须针对 `web/participant_demo` 重新生成，不能跨不同 base 直接复制派生文件。

研究者回执汇总使用本地 `data/human_gt_20261022/candidate-releases.json` 显式登记 dataset SHA、release 文件路径与文件 SHA，以及 Gate2 文件路径与文件 SHA。登记只允许识别该版本回执；只有设置 `active_dataset_sha256` 才会切换 Lab 当前统计视图，移除该字段即可回到原版本。无效或变化的激活材料会报错，旧回执仍按旧版本校验。新旧版本的 GT、视频基线、Gate2 票数和裁决独立统计，不因题目文字或个别任务 SHA 相同而合并。注册表和实际回执不提交 GitHub。

正式 400 题采集页面是 `web/participant_demo`，其运行依赖标注 API、持久化数据库以及服务器端冻结材料。旧 Lab `/offline-annotation` 只保留历史会话恢复。仓库的 GitHub Actions `lab-pages.yml` 仅构建 Lab 静态门户，链接和数据请求转到 `LAB_BACKEND_URL`；没有可访问后端时，仅配置 Actions 或 Pages 不能提供完整标注功能，也不会自动托管 150 条视频或发布参与者站点。

`tests/scene-sequence.test.mjs` 检查逐场景锁定、后续场景写入拒绝和已完成判断不可改写。`tests/checkpoint-integration-browser.cjs` 保留为旧整组候选流程的回归，初始 40 题断言不适用于逐场景会话；新版浏览器检查使用 `tests/checkpoint-scene-sequence-browser.cjs`。浏览器写入测试仅使用隔离本地数据库，测试记录不是人工审核结果。

## 正式发布包的媒体范围

正式打包必须以已托管的最新站点源码为基线，合并本轮代码和新媒体，并保留其 `data/offline-dispatch-assets.json` 排除清单。不要把全量本地 `public/media` 复制回发布目录：本地保存了 33 个尚未托管、留待 online 派发的 `review-*.mp4` 别名副本，共 54,306,821 字节，原 offline 包已明确排除。

这 33 个精确 URL 仅用于 T4 视频审核及其人物参考片段，不被当前或历史 offline 任务引用。部分内容 SHA 与 E8 相同，但 E8 使用另一个已发布文件名，必须保留这些实际播放文件。此次打包保留原已托管 277 个媒体，再加入 150 条新短片，共 **427 个 MP4**；原 277 个文件逐一与远端基线 Git blob 核对，150 条新片逐一与新版媒体 SHA 核对，字节均未改变。历史审核版本和回执绑定不随排除副本而改写。精确核验记录位于本地 `build/annotation-checkpoint-integration-20261023/offline-asset-scope-audit.json`。

当前原生发布链路同时限制压缩 archive 与解包后文件总量，二者均须低于 **256 MiB（268,435,456 字节）**。媒体范围修正后的首个 archive 虽为 262,562,266 字节（约 250.4 MiB），解包后仍达 273,382,412 字节，尚不满足上限，因此进一步采用上述运行时数据去重。生成器报告的是输入文件体积节省，不能替代实际产物测量；每次正式打包必须重新核对压缩大小与 tar 成员解包总大小。原始冻结输入继续留在源码目录，构建只将实际导入的派生数据纳入运行产物。最终本地 archive 为 **259,301,651 字节**，解包后文件合计 **267,557,380 字节**，495 个文件，两项均低于上限。服务器规范化后保存的 archive 为 267,950,080 字节；其内容 SHA 与本地原 archive SHA 分别记录，不相互替代。v17 的远端构建失败保留为历史，v18 原生发布已成功。

## v18 发布与验证回执

[正式标注站点](https://socialflux-annotation-demo-20261021.junqiao24.chatgpt.site) 已于 `2026-10-23T04:48:30.352242+00:00` 发布成功，仍需研究者分发原完整邀请链接领取任务。Sites 版本为 `appgprj_6ad82de6ff188191b48c72ec8787d069~appgver_4667078cd0708191ba451de9f47547e5`，部署为 `appgdep_6adae70918808191ab725abadb5a3629`，源码为 `ba5b42658a35dea0b64615b0d39dc5bb5cbf3522`。完整证据见 [发布报告](../../reports/experiments/2026-10-23_offline_checkpoint_annotation_integration.json)。

匿名公网页面及状态 API 返回 200，显示 50 场景、400 题、150 个媒体和 20 个 offline 分组；320／390 像素手机无横向溢出。抽查的新片实际完整播放 4.6 秒并解码音频，文件 SHA 一致；旧 31.16 秒视频样本下载与 SHA、元数据检查通过，公网未完整播放该旧片。公网检查未领取任务、未写生产记录，也未使用生产恢复码；完整逐场景流程、3 条短片完整播放、旧 v15 会话恢复与未来场景材料隔离由最终隔离本地的 6 项浏览器检查覆盖。

本地研究数据已同步并显式激活新版 dataset；数据文件一致不等于全部本地源码与发布源码一致，本地新增的目录元数据代码另行保留。GitHub Pages 地址本次仍返回 404，仅配置 Actions 不提供标注后端。当前人工质量状态、7 条神情重点复核及正式 Gate 仍待实际审核；本轮不派发 Online／T4。

## 本地生成

在仓库根目录运行。TTS、ASR 与画面渲染使用各自已有环境；下面 GPU 编号只是示例，运行前检查空闲资源。

```bash
python scripts/render_annotation400_revision.py prepare --lines configs/offline_checkpoint_v2_20261022.json
CUDA_VISIBLE_DEVICES=0 .local_models/annotation400-tts-env/bin/python scripts/render_annotation400_revision.py audio
CUDA_VISIBLE_DEVICES=0 .local_models/offline-asr-env/bin/python scripts/render_annotation400_revision.py asr
CUDA_VISIBLE_DEVICES=0 .local_models/annotation400-av-env/bin/python scripts/render_annotation400_revision.py render --shard 0 --shards 4
```

在其余空闲 GPU 分别运行 shard 1、2、3，保持 `--shards 4`。也可不传分片参数按单 GPU 顺序完成。音频独立转写不通过时，视频生成会拒绝该节点并记入失败清单。

音频以自然语速重新合成，保留首尾语音安全余量，仅做有限的保音高调速。无法在允许速度内说完的句子明确报错，不能通过截断尾词凑时长。每条实际音视频时长需要落在 4–5 秒。

画面使用 LivePortrait 的公开动作控制和按原始嘴部开合阈值启用的闭口归一化；口型使用 LatentSync 40 步、关闭 DeepCache。缓存绑定输入波形、动作、身份、模型、配置、mask 与实现指纹。初次 guidance 1.0 的完整片段同步检查失败时，只允许自动重试一次 1.5，并保留失败视频及分数；未通过的片段仍显示待修订。

机器检查包括独立无提示词 ASR、逐轨迹 SyncNet 和音视频时长。ASR、Sync 回执均校验检查前后的媒体与请求 SHA；旧版回执不可沿用。同步检查记录原始检测帧、插值框、完整轨迹覆盖及每条轨迹的分数，不以平均 offset 抵消失败。当前本地 SyncNet 的五帧窗口实现不使用最后一帧，这个模型边缘限制单独记录，不能据此忽略丢失的轨迹或检测帧。它们不能证明表情自然、情绪强度恰当或人体动作无伪影；候选版的人工状态始终为 pending。

## 可携带预览包

```bash
python scripts/package_checkpoint_revision.py --zip
# 如有与当前视频 SHA 绑定的帧级抽查记录，可加入重点复核提示：
python scripts/package_checkpoint_revision.py --visual-review build/offline-video-revision-audit/visual-combined-review.json --zip
python scripts/package_checkpoint_revision.py --verify build/offline-checkpoint-preview
```

发送 `build/offline-checkpoint-preview.zip`，接收者解压后打开 `index.html`，保留旁边的 `videos` 目录即可。页面可按场景或检查状态筛选，展开完整回复及公开表情说明，播放每条视频。短句、视频文件和检查记录采用实际 SHA 绑定；缺失或过期分数不会显示成通过。预览包不包含答案、私有证据或任何标注者回执。可选的帧级抽查记录仅在视频 SHA 一致时展示；“神情重点复核”筛选用于定位需要完整播放确认的片段，不代表人工验收通过。

```bash
python -m unittest tests.test_revision_motion tests.test_annotation400_public_motion tests.test_checkpoint_revision tests.test_checkpoint_package tests.test_revision_checks
```

这组检查覆盖动作线索、冻结目录保护、模型缓存失效、尾词保留、分片输入绑定及可分享文件完整性。不会产生正式人工记录。
