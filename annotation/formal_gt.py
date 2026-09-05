"""Human-only formal ground-truth packet, agreement, and adjudication tools."""

from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json

from evaluation.instance_quality import blind_instance_packet


DIRECTIONS = {"decrease", "similar", "increase", "cannot_determine"}
T2_DIRECTIONS = {"higher_in_a", "similar", "higher_in_b", "cannot_determine"}
INTENSITIES = {"low", "medium", "high", "cannot_determine"}


def _annotation_contract(instance):
    task_type = instance.get("task_type")
    target_states = instance.get("target_spec", {}).get("target_state_ids", [])
    contract = {
        "task_type": task_type,
        "target_state_ids": target_states,
        "evidence_turn_ids_must_reference_visible_input": True,
    }
    if task_type == "T1_state_tracking":
        contract.update({
            "label_fields": ["predictions"],
            "per_state_fields": ["state_id", "intensity", "change", "evidence_turn_ids"],
            "intensity_labels": sorted(INTENSITIES),
            "change_labels": sorted(DIRECTIONS),
        })
    elif task_type == "T2_history_sensitive_merge":
        contract.update({
            "label_fields": ["predictions"],
            "per_state_fields": ["state_id", "direction", "evidence_a", "evidence_b", "causal_relevance"],
            "direction_labels": sorted(T2_DIRECTIONS),
        })
    elif task_type == "T3_counterfactual_choice_effect":
        contract.update({
            "label_fields": ["options"],
            "action_indices": list(range(len(instance.get("input", {}).get("candidate_actions", [])))),
            "per_state_fields": ["state_id", "immediate", "delayed", "evidence_turn_ids"],
            "direction_labels": sorted(DIRECTIONS),
        })
    else:
        raise ValueError(f"unsupported formal annotation task type {task_type!r}")
    return contract


def stable_packet_id(instance_id):
    return "ann-" + hashlib.sha256(instance_id.encode("utf-8")).hexdigest()[:16]


def _packet_sha256(packet):
    value = {key: item for key, item in packet.items() if key != "packet_sha256"}
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def build_annotation_packets(instances):
    packets = []
    for instance in instances:
        packet = blind_instance_packet(instance)
        packet["annotation_id"] = stable_packet_id(instance["instance_id"])
        packet["instance_id"] = instance["instance_id"]
        packet["required_annotators"] = 3
        packet["label_status"] = "pending_human_annotation"
        packet["annotation_contract"] = _annotation_contract(instance)
        packet["packet_sha256"] = _packet_sha256(packet)
        packets.append(packet)
    return packets


def _canonical_label(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _visible_turn_ids(packet):
    identifiers = set()
    def visit(value):
        if isinstance(value, dict):
            if "turn_id" in value:
                raw = str(value["turn_id"])
                identifiers.add(raw)
                identifiers.add(raw if raw.startswith("t") else "t" + raw)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(packet.get("input", {}))
    return identifiers


def _validate_evidence(values, field, visible_ids, required):
    if not isinstance(values, list) or any(not isinstance(item, str) or not item for item in values):
        raise ValueError(f"formal annotation {field} must be a string list")
    if required and not values:
        raise ValueError(f"formal annotation {field} requires visible evidence")
    if set(values) - visible_ids:
        raise ValueError(f"formal annotation {field} references a non-visible turn")


def _validate_state_rows(rows, contract, required_fields, direction_fields=()):
    if not isinstance(rows, list) or not rows:
        raise ValueError("formal annotation state predictions must be a non-empty list")
    expected_states = contract["target_state_ids"]
    if [item.get("state_id") for item in rows] != expected_states:
        raise ValueError("formal annotation must cover target states once in canonical order")
    for row in rows:
        if set(row) != set(required_fields):
            raise ValueError("formal annotation state fields mismatch")
        for field, allowed in direction_fields:
            if row.get(field) not in allowed:
                raise ValueError(f"formal annotation has invalid {field}")


def _validate_label(packet, label):
    if not isinstance(label, dict):
        raise ValueError("formal annotation label must be an object")
    contract = packet["annotation_contract"]
    task_type = contract["task_type"]
    visible_ids = _visible_turn_ids(packet)
    if task_type == "T1_state_tracking":
        if set(label) != {"predictions"}:
            raise ValueError("T1 human label fields mismatch")
        rows = label["predictions"]
        _validate_state_rows(
            rows, contract,
            ("state_id", "intensity", "change", "evidence_turn_ids"),
            (("intensity", INTENSITIES), ("change", DIRECTIONS)),
        )
        for row in rows:
            required = row["intensity"] != "cannot_determine" or row["change"] != "cannot_determine"
            _validate_evidence(row["evidence_turn_ids"], "evidence_turn_ids", visible_ids, required)
    elif task_type == "T2_history_sensitive_merge":
        if set(label) != {"predictions"}:
            raise ValueError("T2 human label fields mismatch")
        rows = label["predictions"]
        _validate_state_rows(
            rows, contract,
            ("state_id", "direction", "evidence_a", "evidence_b", "causal_relevance"),
            (("direction", T2_DIRECTIONS),),
        )
        for row in rows:
            required = row["direction"] != "cannot_determine"
            for field in ("evidence_a", "evidence_b", "causal_relevance"):
                _validate_evidence(row[field], field, visible_ids, required)
    elif task_type == "T3_counterfactual_choice_effect":
        if set(label) != {"options"} or not isinstance(label["options"], list):
            raise ValueError("T3 human label fields mismatch")
        if [item.get("action_index") for item in label["options"]] != contract["action_indices"]:
            raise ValueError("T3 human label must cover action indices once in canonical order")
        for option in label["options"]:
            if set(option) != {"action_index", "state_predictions"}:
                raise ValueError("T3 option fields mismatch")
            rows = option["state_predictions"]
            _validate_state_rows(
                rows, contract,
                ("state_id", "immediate", "delayed", "evidence_turn_ids"),
                (("immediate", DIRECTIONS), ("delayed", DIRECTIONS)),
            )
            for row in rows:
                required = row["immediate"] != "cannot_determine" or row["delayed"] != "cannot_determine"
                _validate_evidence(row["evidence_turn_ids"], "evidence_turn_ids", visible_ids, required)
    else:
        raise ValueError("unsupported formal annotation task type")
    return label


def _fleiss_kappa(groups):
    groups = [group for group in groups if len(group) == 3]
    if not groups:
        return None
    categories = sorted({label for group in groups for label in group})
    if len(categories) == 1:
        return 1.0
    n = 3
    agreement = sum(
        (sum(count * count for count in Counter(group).values()) - n) / (n * (n - 1))
        for group in groups
    ) / len(groups)
    counts = Counter(label for group in groups for label in group)
    total = len(groups) * n
    expected = sum((counts[label] / total) ** 2 for label in categories)
    if expected == 1:
        return 1.0
    return (agreement - expected) / (1 - expected)


def finalize_ground_truth(packets, annotations, adjudications):
    if not packets:
        raise ValueError("formal ground truth requires at least one packet")
    packet_identifiers = [item.get("annotation_id") for item in packets]
    if any(not item for item in packet_identifiers) or len(set(packet_identifiers)) != len(packet_identifiers):
        raise ValueError("formal packets have empty or duplicate annotation IDs")
    for packet in packets:
        if packet.get("packet_sha256") != _packet_sha256(packet):
            raise ValueError("formal packet content does not match packet_sha256")
    packet_ids = {item["annotation_id"]: item for item in packets}
    grouped = defaultdict(list)
    seen = set()
    for item in annotations:
        annotation_id = item.get("annotation_id")
        annotator_id = str(item.get("annotator_id", "")).strip()
        if annotation_id not in packet_ids or not annotator_id:
            raise ValueError("annotation references unknown packet or empty annotator")
        key = (annotation_id, annotator_id)
        if key in seen:
            raise ValueError("duplicate annotation by the same annotator")
        seen.add(key)
        if item.get("human_attestation") is not True:
            raise ValueError("formal annotation requires human_attestation=true")
        packet = packet_ids[annotation_id]
        if item.get("packet_sha256") != packet.get("packet_sha256"):
            raise ValueError("formal annotation is not bound to the exact packet")
        _validate_label(packet, item.get("label"))
        try:
            timestamp = datetime.fromisoformat(
                str(item.get("annotated_at_utc", "")).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("formal annotation requires a valid timestamp") from exc
        if timestamp.tzinfo is None:
            raise ValueError("formal annotation timestamp requires timezone")
        grouped[annotation_id].append(item)
    adjudication_ids = [item.get("annotation_id") for item in adjudications]
    if len(set(adjudication_ids)) != len(adjudication_ids):
        raise ValueError("duplicate adjudication records")
    unknown_adjudications = set(adjudication_ids) - set(packet_ids)
    if unknown_adjudications:
        raise ValueError("adjudication references unknown packet")
    adjudicated = {item["annotation_id"]: item for item in adjudications}
    final = []
    agreement_groups = []
    for annotation_id, packet in packet_ids.items():
        votes = grouped.get(annotation_id, [])
        if len(votes) != packet["required_annotators"]:
            raise ValueError(f"{annotation_id} requires exactly three human annotations")
        labels = [_canonical_label(item["label"]) for item in votes]
        agreement_groups.append(labels)
        counts = Counter(labels)
        winner, count = counts.most_common(1)[0]
        if count == 3:
            if annotation_id in adjudicated:
                raise ValueError(f"{annotation_id} has unnecessary adjudication for unanimous labels")
            label = json.loads(winner)
            decision = "unanimous"
        else:
            review = adjudicated.get(annotation_id)
            if not review or review.get("human_attestation") is not True:
                raise ValueError(f"{annotation_id} disagreement requires human adjudication")
            if (
                not str(review.get("adjudicator_id", "")).strip()
                or review.get("packet_sha256") != packet.get("packet_sha256")
            ):
                raise ValueError(f"{annotation_id} adjudication identity/hash is invalid")
            try:
                adjudicated_at = datetime.fromisoformat(
                    str(review.get("adjudicated_at_utc", "")).replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ValueError(f"{annotation_id} adjudication timestamp is invalid") from exc
            if adjudicated_at.tzinfo is None:
                raise ValueError(f"{annotation_id} adjudication timestamp requires timezone")
            label = _validate_label(packet, review.get("label"))
            decision = "human_adjudication"
        final.append({
            "instance_id": packet["instance_id"],
            "annotation_id": annotation_id,
            "ground_truth": label,
            "decision": decision,
            "label_status": "formal_human_gt",
        })
    exact = sum(len(set(group)) == 1 for group in agreement_groups) / len(agreement_groups)
    return {
        "format": "socialflux_formal_human_gt_v1",
        "instance_count": len(final),
        "annotators_per_instance": 3,
        "unanimous_fraction": round(exact, 4),
        "fleiss_kappa_exact_label": round(_fleiss_kappa(agreement_groups), 4),
        "records": final,
    }
