# Offline 4–5 秒 checkpoint 视频候选版

本轮按研究者要求把每个视频改成一句 checkpoint，目标 **4.6 秒**，主要观察口型、神情和注视。完整公开回复仍保留为文字。新短句是公开原文的摘句或忠实精简，不声称视频仍逐字朗读完整回复。

这是独立的素材修订。**400 道题与 150 条短片的新版媒体绑定已经完成；本轮发布状态待确认，人工质量审核仍为 pending。** 本地接入和机器检查不代表部署成功或人工验收通过。原 v15 长视频、旧题库及全部历史审核版本均保留，新媒体不得沿用旧视频哈希对应的通过记录。

## 配置与输出

- `configs/offline_checkpoint_v2_20261022.json`：150 条短句、完整原回复、精确支撑引文、是否逐字摘句和省略说明；仅含公开材料。
- `data/offline_checkpoint_v2_20261022/manifest.json`：候选请求清单。每个目录以新请求 SHA 分版，源题库 SHA 与原请求 SHA 保留。
- `scripts/render_annotation400_revision.py`：prepare、audio、asr、motion、video、sync，以及逐节点串联的 render 阶段。
- `offline/revision_motion.py`：短片专用非循环动作曲线；明确线索控制表情或注视，没有公开线索时不增加情绪动作。001-t1 的短暂紧张幅度经过单帧对照校准，其他角色不共用其放大系数。
- `scripts/package_checkpoint_revision.py`：制作可离线查看的 HTML 和 MP4 预览包，内嵌公开材料，无 API、登录、外部字体或服务器依赖。
- `scripts/export_checkpoint_annotation.py`：向独立站点副本导出新的 400 题媒体版本及对应 Gate2 媒体审核；不写原冻结题库和审核目录，不自动部署或激活。
- `data/offline_checkpoint_annotation_20261023/`：本地新版 `release.json`、`gate2-release.json`、覆盖统计及旧素材 SHA 保留记录；这些制作侧数据不进入 GitHub。

旧题库、角色图、模型权重和原始媒体是本地依赖，按原素材清单恢复；GitHub 源码不内嵌这些文件。脚本不会自动下载模型或调用收费生成 API。

## 400 题标注页接入

新版 `annotation400-checkpoint-20261023-v2` 保留 50 个场景、400 道完整文字题、题目 SHA、私有证据和分组；每题仍绑定两个对应位置的视频，共用 150 个独立片段，每条 4.6 秒、合计 690 秒。媒体字段分别保存短 `spoken_text`、`spoken_scope=checkpoint_sentence`、完整 `full_public_response` 和精确 `source_quote`。页面明确说明短片只朗读一句 checkpoint，完整回复仍须阅读题面。

最终接入源码合并了远端 v16 的逐场景流程。每组仍为 5 个场景、40 题，新会话先显示当前场景的 8 题：完成并锁定盲答，再完成独立环境判断、题目与媒体审核，才解锁下一场景。场景完成记录、原盲答和独立判断保持锁定；当前场景的私有材料及机器候选仅在相应阶段开放。历史无 `sceneSequence` 的整组会话仍按原流程恢复。

进行中的逐场景回执导出仅包含已完成场景与当前场景的媒体绑定及 Gate2 `task_hashes`，不导出尚未解锁场景的视频 URL、SHA，或含视频 SHA 的媒体审核任务 ID；全部场景完成后才导出整组媒体与任务。旧整组回执的导出保持原样。此次过滤与页面/API 的场景范围控制配套，避免通过导出绕过后续场景的材料限制。

当前候选数据 SHA 为 `4859edec0ed4a00e5ee98b908b44efc930f7a1b56e774fa50c6ec34aa75ef854`，Gate2 包 SHA 为 `3be0b7a12e695461f7771529a0da866cdf8cbb71726fad9231c337c0d2adf7ec`。导出保留原 11 个 Gate2 版本及 422 项非媒体审核，另生成 150 项新版逐片审核。旧会话按原 dataset、媒体和审核包哈希恢复，不能静默换成新短片。

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

研究者回执汇总使用本地 `data/human_gt_20261022/candidate-releases.json` 显式登记 dataset SHA、release 文件路径与文件 SHA，以及 Gate2 文件路径与文件 SHA。登记只允许识别该版本回执；只有设置 `active_dataset_sha256` 才会切换 Lab 当前统计视图，移除该字段即可回到原版本。无效或变化的激活材料会报错，旧回执仍按旧版本校验。新旧版本的 GT、视频基线、Gate2 票数和裁决独立统计，不因题目文字或个别任务 SHA 相同而合并。注册表和实际回执不提交 GitHub。

正式 400 题采集页面是 `web/participant_demo`，其运行依赖标注 API、持久化数据库以及服务器端冻结材料。旧 Lab `/offline-annotation` 只保留历史会话恢复。仓库的 GitHub Actions `lab-pages.yml` 仅构建 Lab 静态门户，链接和数据请求转到 `LAB_BACKEND_URL`；没有可访问后端时，仅配置 Actions 或 Pages 不能提供完整标注功能，也不会自动托管 150 条视频或发布参与者站点。

`tests/scene-sequence.test.mjs` 检查逐场景锁定、后续场景写入拒绝和已完成判断不可改写。`tests/checkpoint-integration-browser.cjs` 保留为旧整组候选流程的回归，初始 40 题断言不适用于逐场景会话；新版浏览器检查使用 `tests/checkpoint-scene-sequence-browser.cjs`。浏览器写入测试仅使用隔离本地数据库，测试记录不是人工审核结果。

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
