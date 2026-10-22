"""Release machine-proposed task labels only after a passed human Gate 4 audit."""

from evaluation.rollout_gate import content_sha256


FORMAT = "socialflux_formal_audited_machine_gt_v1"
LABEL_STATUS = "formal_machine_proposal_human_audited"


def release_audited_machine_labels(instances, proposal_payload, four_gate_report):
    """Bind complete machine proposals to instances after all four gates pass."""
    instances = list(instances)
    gate4 = four_gate_report.get("gates", {}).get("gate_4_task_instance_quality", {})
    audit = gate4.get("human_review_audit") or {}
    if four_gate_report.get("research_ready") is not True or gate4.get("passed") is not True:
        raise ValueError("audited machine label release requires a research-ready four-gate report")
    if audit.get("passed") is not True or audit.get("pending_instance_ids") or audit.get("rejected_instance_ids"):
        raise ValueError("audited machine label release requires a completed, all-approved Gate 4 sample")
    if gate4.get("instance_count") != len(instances):
        raise ValueError("Gate 4 report instance count does not match label population")
    if proposal_payload.get("format") != "socialflux_machine_task_proposals_v1":
        raise ValueError("unsupported machine proposal format")

    proposals = proposal_payload.get("records", [])
    if proposal_payload.get("population_count") != len(instances) or len(proposals) != len(instances):
        raise ValueError("machine proposals do not cover the full task population")
    proposal_by_id = {item.get("instance_id"): item for item in proposals}
    instance_ids = [item.get("instance_id") for item in instances]
    if len(proposal_by_id) != len(proposals) or set(proposal_by_id) != set(instance_ids):
        raise ValueError("machine proposal IDs do not exactly match task instance IDs")

    records = []
    for instance in instances:
        proposal_record = proposal_by_id[instance["instance_id"]]
        if proposal_record.get("instance_sha256") != content_sha256(instance):
            raise ValueError(f"machine proposal hash mismatch for {instance['instance_id']}")
        proposal = proposal_record.get("proposal", {})
        if proposal.get("status") != "machine_proposal_not_ground_truth":
            raise ValueError(f"incomplete machine proposal for {instance['instance_id']}")
        released = {key: value for key, value in proposal.items() if key != "status"}
        records.append({
            "instance_id": instance["instance_id"],
            "instance_sha256": proposal_record["instance_sha256"],
            "ground_truth": released,
            "decision": "machine_proposal_released_after_gate4_sample_audit",
            "label_status": LABEL_STATUS,
        })
    return {
        "format": FORMAT,
        "instance_count": len(records),
        "label_origin": "frozen_simulator_machine_proposal",
        "human_review_mode": "same_deterministic_sample_double_audit",
        "gate4_sample_size": audit.get("sample_size"),
        "records": records,
    }
