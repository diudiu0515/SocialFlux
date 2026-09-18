import unittest

from scripts.benchmark_task_models_scale50 import (
    cumulative_latency,
    cumulative_requests,
    summarize,
)


class TaskModelBenchmarkAccountingTest(unittest.TestCase):
    def test_retry_history_is_included_in_cumulative_totals(self):
        row = {
            "role": "t2_answer",
            "model": "model",
            "status": "success",
            "request_count": 1,
            "latency_seconds": 4.0,
            "attempt_history": [
                {
                    "status": "error",
                    "request_count": 2,
                    "latency_seconds": 7.5,
                }
            ],
        }
        self.assertEqual(cumulative_requests(row), 3)
        self.assertEqual(cumulative_latency(row), 11.5)
        summary = summarize({"case": row})["t2_answer"]["model"]
        self.assertEqual(summary["requests"], 3)
        self.assertEqual(summary["mean_latency_seconds"], 11.5)


if __name__ == "__main__":
    unittest.main()
