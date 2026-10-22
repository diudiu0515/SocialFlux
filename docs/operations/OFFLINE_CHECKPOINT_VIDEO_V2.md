# Offline 4–5 秒 checkpoint 视频候选版

本轮按研究者要求把每个视频改成一句 checkpoint，目标 **4.6 秒**，主要观察口型、神情和注视。完整公开回复仍保留为文字。新短句是公开原文的摘句或忠实精简，不声称视频仍逐字朗读完整回复。

这是独立的素材修订，**尚未上线，也不是已通过人工质量审核的发放包**。现有 400 道题、线上 v15 媒体和已冻结审核包均保持原版本；新媒体不得沿用旧视频哈希对应的通过记录。正式换包时还需生成新的媒体绑定与审核包版本，再发布和派发。

## 配置与输出

- `configs/offline_checkpoint_v2_20261022.json`：150 条短句、完整原回复、精确支撑引文、是否逐字摘句和省略说明；仅含公开材料。
- `data/offline_checkpoint_v2_20261022/manifest.json`：候选请求清单。每个目录以新请求 SHA 分版，源题库 SHA 与原请求 SHA 保留。
- `scripts/render_annotation400_revision.py`：prepare、audio、asr、motion、video、sync，以及逐节点串联的 render 阶段。
- `offline/revision_motion.py`：短片专用非循环动作曲线；明确线索控制表情或注视，没有公开线索时不增加情绪动作。001-t1 的短暂紧张幅度经过单帧对照校准，其他角色不共用其放大系数。
- `scripts/package_checkpoint_revision.py`：制作可离线查看的 HTML 和 MP4 预览包，内嵌公开材料，无 API、登录、外部字体或服务器依赖。

旧题库、角色图、模型权重和原始媒体是本地依赖，按原素材清单恢复；GitHub 源码不内嵌这些文件。脚本不会自动下载模型或调用收费生成 API。

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
