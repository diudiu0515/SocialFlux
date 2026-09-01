import unittest
from pathlib import Path


class SelfCheckContractTest(unittest.TestCase):
    def test_self_check_is_persistent_and_every_todo_has_status(self):
        text = Path("self_check.md").read_text(encoding="utf-8")
        self.assertIn("不得删除既有条目", text)
        rows = []
        table = 0
        for line in text.splitlines():
            if line.startswith("| Phase") or line.startswith("| #"):
                table += 1
                continue
            if not line.startswith("|") or "---" in line:
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if table and cells:
                rows.append(cells)
        self.assertGreaterEqual(len(rows), 100)
        self.assertTrue(all(row[-1] in {"[x]", "[ ]"} for row in rows))


if __name__ == "__main__":
    unittest.main()
