"""Recover exact recorded formatting defects, keeping the earliest full answer."""
import json
import re

from offline.choice_builder import load, save, sha
from offline.oracle import ROOT, REVIEW_PROMPT, review_group, now, summarize
from offline.oracle_release import RUN
from offline.reuse_audit import digest
from providers.factory import public_provider_config
from providers.model_routes import ModelRoutes


def main():
    config = ModelRoutes.load(ROOT / "configs/gpt50_experiment/model_routes.hybrid.v3_2.json").provider_config("quality_review")
    config.update(timeout=120, max_transport_attempts=1, retry_backoff_seconds=0, max_tokens=7000)
    for name in ("GPT50_044-T3", "GPT50_045-T3"):
        directory = RUN / "reviews" / name
        if (directory / "result.json").exists():
            continue
        items = load(RUN / "groups" / name / "items.json")
        packet = load(RUN / "groups" / name / "evidence.json")
        payload = {"public_input": packet["public_input"],
                   "private_evidence": {k: v for k, v in packet.items() if k != "public_input"},
                   "questions": [{k: x[k] for k in ("instance_id", "task", "subtype", "question", "options", "target_spec")} for x in items]}
        for path in sorted((directory / "calls").glob("*.json"), key=lambda p: load(p).get("started_at_unix", 0)):
            raw = load(path).get("raw_output", "").strip()
            fixed, rule = raw, None
            if raw.endswith("}] см}"):
                fixed, rule = raw[:-4] + "}", "remove exact stray ' см' token outside every JSON string"
            else:
                fixed = re.sub(r"(?:</final>|</\|im_end\|>|<\|im_end\|>)+$", "", raw)
                if fixed != raw:
                    rule = "remove exact trailing channel closing delimiter"
            if rule is None:
                continue
            data = json.loads(fixed)
            save(directory / "result.json", {
                "binding": digest({"prompt": REVIEW_PROMPT, "payload": payload, "provider": public_provider_config(config)}),
                "result": data, "provider": public_provider_config(config), "completed_at": now(),
                "recovered_from": str(path.relative_to(ROOT)), "raw_call_sha256": sha(path),
                "recovery": rule + "; first complete answer only; all failed attempts retained"})
            review_group(items, RUN, config)
            print("recovered", name, path.name)
            break
    summarize(RUN)


if __name__ == "__main__":
    main()
