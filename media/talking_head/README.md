# Talking Head 资产说明

本目录保存 20 个 scenario 的稀疏 Talking Head 配套信息。每个 scenario 有 3 条由 trigger 选中的短视频资产，共 60 条。视频不是逐轮生成，而是在对应公开表现条件首次满足时作为可观察社会信号出现。

## 文件关系

- `manifest.json`：60 条资产的唯一索引，记录 scenario、trigger、公开台词、声线、韵律参数、输入/输出路径、SHA-256 和质量检查。
- `requests/scenario_NNN/*.json`：可提交、可复核的安全生成请求。只含公开角色表现、公开台词、动态目标时长和参考图路径，不含 latent state、阈值、appraisal 或 benchmark 答案。
- `assets/scenario_NNN/reference.png`：每个 scenario 的原创虚构人物参考肖像。
- `assets/scenario_NNN/*.wav`：24 kHz 单声道公开台词音频。
- `assets/scenario_NNN/*.mp4`：MuseTalk 1.5 实际生成的有声视频。
- `av_sync_screen.json`、`visual_stability_screen.json`、`quality_gate_report.json`：自动筛查与四项媒体 gate 的证据。

`assets/` 是体积较大的可再生产物，默认不提交 Git。网站使用视频 SHA-256 作为 URL 缓存键；重新生成后不会继续播放浏览器缓存中的旧视频。

## 音频与视频生成

公开台词经明确授权后发送到 Microsoft Edge TTS。角色声线和基础韵律由 `configs/talking_head_voice_profiles.json` 固定；当前覆盖 5 种普通话声线，并按事件语义在有界范围内调整语速、音高和音量。后处理会去除服务返回的多余尾静音，再保留约 110 ms 开头余量与 420 ms 自然收尾。输出采用真实语音长度，不再统一补成 6 秒，总时长严格限制为 3–8 秒。

视频使用 MIT 许可的 `TMElyralab/MuseTalk 1.5` 本地生成，25 fps，H.264/yuv420p。生成请求保持参考肖像身份、服装和背景连续，并要求普通话音素与唇形同步。

## 重建

```bash
python scripts/prepare_talking_head_assets.py --synthesize-audio
python scripts/generate_talking_head_musetalk.py --prepare
python scripts/generate_talking_head_musetalk.py --run-shard 0
python scripts/generate_talking_head_musetalk.py --run-shard 1
python scripts/generate_talking_head_musetalk.py --run-shard 2
python scripts/generate_talking_head_musetalk.py --run-shard 3
python scripts/generate_talking_head_musetalk.py --collect

.local_models/musetalk-env/bin/python scripts/audit_talking_head_av_sync.py
.local_models/musetalk-env/bin/python scripts/audit_talking_head_visual_stability.py
python scripts/audit_talking_head_release.py --base-url http://127.0.0.1:8000
```

四个 `--run-shard` 分别绑定 GPU 0–3，可并行运行。收集阶段用 ffprobe 检查音视频流、3–8 秒时长、尺寸、25 fps、编码和请求时长误差，写入 SHA-256，并把 asset ID 同步回 scenario JSON 与 Markdown。

## 验收边界

自动检查包括：

- 20 个 scenario × 3 个 trigger，合计 60 条；
- request 的公开/私有信息边界；
- 音频采样率、真实时长、声线和韵律元数据；
- MP4 音视频流、编码、帧率、尺寸和时长；
- 音频能量与口部运动的粗粒度同步筛查；
- 人脸可检测、上半脸与非脸区域稳定性；
- manifest、scenario、网站 asset ID 与实际文件一致。

自动 gate 用于排除结构错误、冻嘴、显著错位、崩脸和传输错误，不能替代真人对口型精细度、语音自然度、表情—状态一致性和整体真人感的观看判断。网站为 60 条视频逐条提供播放器、合成参数、四项人工勾选与问题记录。
