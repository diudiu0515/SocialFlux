# SocialFlux Project Progress

更新时间：2026-09-18

## 当前主线

- 唯一生产入口：`python -m pipeline`。
- 阶段顺序：Claude 直建 300 Scenario → 人工 Gate 1 → 每场景 3 个 Fable
  seed rollout → Gate 2 → Gate 3 canonical selection → T1/T2/T3 与 T4 → Gate 4。
- Scale300 不再继承 Scale20/150/200；旧 catalog 和继承构建器已经删除。
- 当前 `configs/scale300_v1/scenarios` 的 300 个候选暂时保留，等待 Claude
  直建的新批次替换。
- `scripts/build_scale300_v1.py` 只做 300 文件完整性、schema 和确定性投影
  校验，不调用模型，也不能批准 Gate 1。
- Policy、Appraisal、Response、task construction/review 与 T4 均从同一 route
  table 解析到 `claude-fable-5`；Appraisal 与 Response 仍是两次独立请求。

## Gate 状态

| Gate | 当前状态 | 下一步 |
|---|---|---|
| Gate 1 | pending | Claude 直建后生成 hash-bound review template，由真人逐场景审核并冻结 S0/D0 |
| Gate 2 | pending | 对冻结场景完成 E1–E6 environment validity 证据 |
| Gate 3 | pending | 生成 300×3 raw candidates，完成 Judge/history 证据并逐场景选择 1 条 canonical trajectory |
| Gate 4 | pending | 从 selected pool 构建 T1/T2/T3、运行 T4，并对任务实例与答案做人审抽查 |

当前没有可发布的 `data/formal/` 产物，不能宣称 benchmark release ready。

## 人工与媒体边界

- Web 审核页面保留；浏览器草稿不是签名证据。
- Talking Head 代码、manifest、请求和资产保留；多模态有效性仍需人工审核。
- 现存历史报告仅作方法与失败审计。已被当前方法取代的报告已在
  `reports/README.md` 单列，待明确授权后删除。

## 下一次运行

```bash
python scripts/build_scale300_v1.py --check
python scripts/build_scale300_v1.py
python scripts/build_scale300_review_template.py
python -m pipeline preflight
```

之后先完成人工 Gate 1；未冻结前不得开始正式 rollout。
