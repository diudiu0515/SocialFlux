# Talking Head 资产说明

本目录保存 20 个 scenario 的稀疏 Talking Head 配套信息。每个 scenario 有两条由私有状态 trigger 选中的短视频资产，共 40 条。视频不是逐轮生成，而是在 threshold/crossing 首次满足时作为可观察社会信号出现。

## 文件关系

- `manifest.json`：40 条资产的唯一索引，记录 scenario、trigger、台词、语音、输入/输出路径、生成器和校验元数据。
- `requests/scenario_NNN/*.json`：可提交、可复核的安全生成请求。只含公开角色表现、台词、目标时长和参考图路径，不含 latent state、阈值、appraisal 或 benchmark 答案。
- `assets/scenario_NNN/reference.png`：每个 scenario 的原创虚构人物参考肖像。
- `assets/scenario_NNN/*.wav`：固定台词音频。
- `assets/scenario_NNN/*.mp4`：EchoMimicV2 实际生成的视频。

`assets/` 是体积较大的可再生产物，默认不提交 Git；请求、manifest、prompt 和生成脚本提交仓库。网站在本机存在已校验 MP4 时显示播放器，否则明确显示“视频待生成”。

## 生成模型

默认实现使用 Apache-2.0 的 `BadToBest/EchoMimicV2` accelerated inference。选择它是因为项目需要由静态肖像与中文音频生成半身人物，而不是通用文生视频；本地四卡可以按 scenario trigger 并行生成。

固定 prompt 位于 `prompts/talking_head_generation_v1.md`。运行请求由 `scripts/prepare_talking_head_assets.py` 投影，不把私有触发条件写进视频 prompt。

## 重建

```bash
python scripts/prepare_talking_head_assets.py --synthesize-audio
python scripts/generate_talking_head_videos.py --prepare
python scripts/generate_talking_head_videos.py --run-shard 0
python scripts/generate_talking_head_videos.py --run-shard 1
python scripts/generate_talking_head_videos.py --run-shard 2
python scripts/generate_talking_head_videos.py --run-shard 3
python scripts/generate_talking_head_videos.py --collect
```

四个 `--run-shard` 可分别绑定四张 GPU 并行运行。默认输出 768×768、24 fps、4–5 秒、有声 MP4；`--collect` 用 ffprobe 检查音视频流、尺寸和时长，写入 SHA-256，并把 asset ID 同步回 scenario JSON 和配对 Markdown。

## 验收边界

自动完成的检查包括：

- 20 个 scenario × 2 个 trigger 覆盖；
- request schema 与公开/私有信息边界；
- MP4 同时有视频流和音频流；
- 时长在 3–8 秒；
- manifest、scenario 和网站 asset ID 一致。

MV2 Expression-State Consistency 与 MV3 Temporal Continuity 仍必须由真人观看后记录，不能由“文件生成成功”替代。
