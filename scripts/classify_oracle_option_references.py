"""Distinguish T2 history labels from option labels before deterministic relabeling."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from offline.choice_builder import load, save, sha
from offline.oracle import ROOT, json_call
from offline.oracle_release import RUN, LETTER
from offline.reuse_audit import digest
from providers.model_routes import ModelRoutes

PROMPT = """你只做文字指代分类，不重写题目或判断答案。T2解释里 A/B 可能指历程，也可能指选项；C/D是选项。
根据完整题目、原始选项和解释，指出 occurrences 中哪些 position 是在指选择题的选项字母。
历程A/B、A:t1/B:t2和状态值比较中的A/B不是选项。逐个位置判断，勿把同一字母的所有出现混为一类。
仅返回 {"rows":[{"id":"原id","option_positions":[整数位置,...]}]}。原文与字母索引不可改动。"""


def main():
    rows = []
    for path in sorted((RUN / "groups").glob("*/items.json")):
        for item in load(path):
            if item["task"] != "T2":
                continue
            author = item["authoring"]
            data = load(ROOT / author["generation_source"]["path"])
            proposal = next(q for q in data.get("result", data)["questions"] if q["instance_id"] == item["instance_id"])
            if author["answer"] == proposal["answer"]:
                continue
            for key in ("rationale", "oracle_rationale"):
                text = proposal[key]
                occurrences = [{"position": m.start(), "letter": m.group()} for m in LETTER.finditer(text)]
                if occurrences:
                    rows.append({"id": item["instance_id"] + "-" + key, "text": text,
                                 "question": proposal["question"], "original_options": proposal["options"],
                                 "occurrences": occurrences})
    config = ModelRoutes.load(ROOT / "configs/gpt50_experiment/model_routes.hybrid.v3_2.json").provider_config("quality_review")
    config.update(timeout=120, max_transport_attempts=1, retry_backoff_seconds=0)
    def job(batch):
        name = digest(batch)[:20]
        def validate(result):
            if {r["id"] for r in result["rows"]} != {r["id"] for r in batch}:
                raise ValueError("classification IDs mismatch")
            for row, classified in ((r, next(v for v in result["rows"] if v["id"] == r["id"])) for r in batch):
                possible = {v["position"] for v in row["occurrences"]}
                certain = {v["position"] for v in row["occurrences"] if v["letter"] in "CD"}
                if not certain <= set(classified["option_positions"]) <= possible:
                    raise ValueError("invalid option reference classification")
        result = json_call(RUN, "option_reference_calls/" + name, PROMPT, {"rows": batch}, config, validate, 2200)
        for row in batch:
            classified = next(v for v in result["rows"] if v["id"] == row["id"])
            save(RUN / "option_references" / (row["id"] + ".json"),
                 {**classified, "text_sha256": digest(row["text"]),
                  "source": str((RUN / "option_reference_calls" / name / "result.json").relative_to(ROOT)),
                  "script_sha256": sha(Path(__file__))})
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(job, rows[n:n+8]) for n in range(0, len(rows), 8)]
        for future in as_completed(futures):
            future.result()
    print("classified", len(rows), "T2 explanation fields")


if __name__ == "__main__":
    main()
