"""Retain blind public T4 evidence and separate, unfilled human rating forms."""

import hashlib
import json
from pathlib import Path

from evaluation.t4_batch import digest, save
from evaluation.t4_evaluation import T4_DIMENSIONS, public_t4_judge_packet


def export_human_review(trajectory, scenario, episode_directory, review_root):
    episode_directory, review_root = Path(episode_directory).resolve(), Path(review_root)
    review_id = hashlib.sha256(str(episode_directory).encode()).hexdigest()[:20]
    packet = public_t4_judge_packet(trajectory, scenario)
    evidence = {"review_id": review_id, "evidence": packet}
    packet_path = review_root / "packets" / f"{review_id}.json"
    if packet_path.exists() and json.loads(packet_path.read_text()) != evidence:
        raise ValueError("human review evidence changed for an existing review ID")
    save(packet_path, evidence)
    # A separate form never inherits machine scores and is never overwritten.
    form_path = review_root / "ratings" / f"{review_id}.json"
    if not form_path.exists():
        save(form_path, {"review_id": review_id, "evidence_sha256": digest(evidence),
             "rating_status": "pending", "reviewer_id": "", "rated_at": None,
             "dimensions": {key: {"score": None, "not_applicable": False,
                                  "evidence_turn_ids": [], "rationale": ""}
                            for key in T4_DIMENSIONS},
             "notes": "Unfilled form; null is not yet an N/A judgment. Only recovery may be N/A."})
    save(review_root / "admin" / f"{review_id}.json", {
        "review_id": review_id, "trajectory": str(episode_directory / "trajectory.json"),
        "trajectory_sha256": digest(trajectory), "evidence_sha256": digest(evidence),
        "scenario_id": scenario["scenario_id"],
        "condition": trajectory.get("policy_provenance", {}).get("observation_condition"),
        "policy_provenance": trajectory.get("policy_provenance", {}),
        "video_deliveries": str(episode_directory / "video_deliveries.json"),
        "machine_result": str(episode_directory / "result.json"),
        "human_validation_status": "pending_human_review",
    })
    return {"review_id": review_id, "packet": str(packet_path), "rating_form": str(form_path)}
