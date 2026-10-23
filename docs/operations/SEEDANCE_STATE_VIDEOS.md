# State 驱动的原生 Seedance 视频

范围：50 场景，Offline 100 段历史节点短片覆盖全部 300 道 T1/T3，100 道 T2 保留文字。同一节点供多道题复用。每个场景仍为 3/2/3 共 8 题，整场盲答锁定后开放答案与 state，完成核对才进入下一场景。

素材目录的 `t1` / `t2` 表示历史第 1 / 2 轮，与题型 `T1` / `T2` 不同；题型 T2 不绑定任何视频。

Online 更新原有 326 个素材位。素材 ID、事件类别、场景绑定、时长和触发阈值、冷却、频次规则保持原样。Offline 请求 5 秒、Online 请求 4 秒，原生文件可能分别约为 5.088 秒和 4.096 秒。

## 入口

| 用途 | 文件 |
|---|---|
| 当前 state、人格、公开线索转为长表演提示词 | `environment/state_performance.py` |
| 冻结输入、首段生成、断点续跑、审计 | `scripts/seedance_state_batch.py` |
| Online 重生成与完整清单核验 | `scripts/refresh_online_state_videos.py` |
| 使用无对白原片完成 Offline 续片及质量修复 | `scripts/complete_seedance_dialogue.py` |
| 修复 Online 意外对白 | `scripts/repair_seedance_nonverbal.py` |
| 检查参考动作是否被复制 | `scripts/audit_seedance_motion.py` |
| 有界替换确认重复的动作 | `scripts/refresh_seedance_motion.py` |
| 原生语音转写、完整口型检查、网页压缩 | `scripts/check_seedance_videos.py` |
| 新版绑定、历史保留、发布素材导出 | `scripts/export_seedance_release.py` |

提示词在本地生成，不额外调用文本模型，不发送题目、选项、机器答案或未来 state。Online 只使用原触发事件的语义类别，不编造具体 state 数值或新对白。

续片优先参考同场景已生成且通过无对白检查的 Online 原片，避免旧台词干扰。个别场景持续带入旧人声时，使用模型直接生成、关闭音轨生成的原生人物参考；检查提供方参数、原片 SHA 和零音轨回执，不对现有视频静音后冒充原片。此参考不进入 426 段交付清单。输入使用未经修改的原生模型产物；网页副本只做 H.264 压缩，保留帧序、时长和音轨。原片、任务 ID、提示词、使用量和失败记录独立保存。

新任务先写状态再提交；已有任务 ID 只查询原任务，没有 ID 的不确定提交不自动重试。已生成但台词/口型不合格的输出可有限次重做，旧证据进入节点 `attempts/`。服务拒绝与不确定提交不走质量重试。自动检查不等于人工认可自然度，逐片段人工审核继续保留。

人物参考会使模型复刻原片动作，只有 ASR 和时长合格不能证明情绪已更新。续片提示词明确要求只生成参考结束后的新镜头，并在开头给出当前事件的连续表演方向。动作检查对比完整采样与分段面部变化，疑似重复项单独留档重做；它只检测复制，不把相关性当成情绪自然度评分。最终发布绑定当前原片 SHA、动作检查文件 SHA 和抽查记录，旧检查不能覆盖后来生成的视频。

对仍复刻动作的片段，`refresh_seedance_motion.py prepare-still / generate-still` 使用同账号 Seedance 直接返回的原始尾帧图片作为人物参考，输入不再包含视频动作时间线。尾帧通过 `return_last_frame` 获取，校验原任务参数、原视频 SHA、图片 SHA 和提供方返回 URL；不从本地视频截帧后冒充原始产物。参见[提供方原始产物说明](https://docs.volcengine.com/docs/ark/seedance-portrait-asset-guide?lang=zh)。这类片段仍需语音、时长、实际表情及身份连续性检查。

## 数据和发布

- Offline：`data/seedance_state_v2_20261023/`。
- Online：`data/gpt50/experiment/seedance_state_online_v4/`。
- 完整核验后才切换 `configs/online_multimodal_assets.json` 的 `active_manifest`，Lab 从该清单读取。
- 沿用原标注站及 D1 数据库，保留匿名编号、恢复码、旧题目与标注记录。网页视频使用文件哈希作为 URL。
- 删除的旧视频列入站点 `data/retired-media.json`；旧会话明确提示素材已清理，不将新片替代原始标注证据。
- 完成数量以任务状态、质检和发布回执为准，候选目录存在不表示已经上线。
- 最终素材清单在 T4 审核绑定后保持不变；上线状态另存发布回执，不能为改一个状态字段而破坏清单哈希。

旧 Kokoro、LivePortrait、LatentSync 合成权重退役。保留 Whisper 转写环境和 SyncNet / S3FD 检查依赖。旧 checkpoint JSON 是原题和短句的冻结来源，不能删除或改写；旧本地渲染文档仅作历史记录。

官方参考：[Seedance 2.0 教程](https://docs.volcengine.com/docs/ark/seedance-2-0?lang=en)。
