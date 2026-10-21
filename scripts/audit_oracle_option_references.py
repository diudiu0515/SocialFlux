"""Assistant audit of option-label positions; history A/B must never rotate."""
from offline.choice_builder import load, save, sha
from offline.oracle_release import RUN
from pathlib import Path

# Character offsets inspected against the complete, hash-bound original text.
# Every unlisted field contains only history labels and therefore has no edits.
OPTIONS = {
    "001-02": [98, 109, 124, 126], "004-01": [168], "004-02": [183, 211, 253],
    "005-01": [120, 147, 161], "008-02": [77, 107, 119, 134], "012-01": [118, 127, 134, 168],
    "013-01": [122], "014-01": [110], "014-02": [96], "016-01": [189], "019-01": [92, 117],
    "021-02": [138], "023-01": [108, 132], "024-01": [135, 152], "024-02": [123, 151],
    "026-02": [109], "030-01": [172], "030-02": [103, 144, 157, 159], "031-01": [120],
    "031-02": [115], "032-01": [75, 90], "034-01": [190], "034-02": [72, 164],
    "038-01": [146], "040-01": [102], "041-01": [107], "041-02": [134], "043-02": [0],
    "045-02": [130, 142, 146], "049-01": [107], "049-02": [94, 129], "050-01": [130],
    "050-02": [123],
}


def main():
    for path in sorted((RUN / "option_references").glob("*.json")):
        record = load(path)
        identifier, field = path.stem.split("-", 4)[:4], path.stem.split("-", 4)[4]
        # SFV2-001-T2-02-oracle_rationale
        key = identifier[1] + "-" + identifier[3]
        expected = OPTIONS.get(key, []) if field == "oracle_rationale" else ([0] if key == "043-02" else [])
        if not record.get("assistant_audit"):
            save(RUN / "option_reference_model_originals" / path.name, record)
        record.update(option_positions=expected, assistant_audit={
            "reviewer_type": "assistant_not_human", "method": "full_original_text_character_offset_review",
            "script_sha256": sha(Path(__file__)), "does_not_change_answer_or_reasoning": True})
        save(path, record)
    print("audited", len(list((RUN / "option_references").glob("*.json"))), "fields")


if __name__ == "__main__":
    main()
