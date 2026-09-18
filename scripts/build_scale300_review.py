#!/usr/bin/env python3
"""Build the Scale300 live generation/framework report without human claims."""

from pathlib import Path

import build_scale200_review as scale200


ROOT = Path(__file__).resolve().parents[1]
report = scale200.report
report.MATRIX = ROOT / "configs/scale300_v1/design_matrix.json"
report.OUTPUT = ROOT / "build/scale300_v1/review.json"
report.MARKDOWN = ROOT / "build/scale300_v1/review.md"
report.ROLLOUT_ROOTS = report.ROLLOUT_ROOTS + (
    ("qwen32_all_scale300_thinking_enabled_failure", ROOT / "build/scale300_v1/rollouts_v1"),
    ("qwen32_all_scale300_new100", ROOT / "build/scale300_v1/rollouts_v2"),
    ("qwen32_policy_qwen35_environment_scale300", ROOT / "build/scale300_v1/rollouts_v3_hybrid"),
)
report.TARGET_COUNT = 300
report.REPORT_LABEL = "Scale300"
report.REPORT_FORMAT = "socialflux_scale300_review_v1"
report.MODEL_REVIEW_FILES = report.MODEL_REVIEW_FILES + (
    ROOT / "build/scale300_v1/model_semantic_reviews.json",
)


if __name__ == "__main__":
    report.main()
