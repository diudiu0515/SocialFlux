#!/usr/bin/env python3
"""Build the Scale200 generation/framework report without human claims."""

from pathlib import Path

import build_scale150_review as report

ROOT = Path(__file__).resolve().parents[1]
report.MATRIX = ROOT / "configs/scale200_v1/design_matrix.json"
report.OUTPUT = ROOT / "build/scale200_v1/review.json"
report.MARKDOWN = ROOT / "build/scale200_v1/review.md"
report.ROLLOUT_ROOTS = report.ROLLOUT_ROOTS + (
    ("qwen32_policy_qwen35_environment_scale200_source_order_bug", ROOT / "build/scale200_v1/rollouts_content_v1_source_order_bug"),
    ("qwen32_policy_qwen35_environment_scale200_corrected", ROOT / "build/scale200_v1/rollouts_content_v2"),
    ("ia089_retry_connection_refused", ROOT / "build/scale200_v1/rollouts_content_v3_ia089"),
    ("ia089_qwen35_role_failure", ROOT / "build/scale200_v1/rollouts_content_v4_ia089"),
    ("ia089_qwen32_all_stages_partial", ROOT / "build/scale200_v1/rollouts_content_v5_ia089_qwen32all"),
)
report.TARGET_COUNT = 200
report.REPORT_LABEL = "Scale200"
report.REPORT_FORMAT = "socialflux_scale200_review_v1"
report.MODEL_REVIEW_FILES = report.MODEL_REVIEW_FILES + (
    ROOT / "build/scale200_v1/model_semantic_sample_reviews.codex.json",
)

if __name__ == "__main__":
    report.main()
