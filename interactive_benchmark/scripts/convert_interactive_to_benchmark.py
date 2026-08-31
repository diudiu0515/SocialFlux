#!/usr/bin/env python3
"""Convert EmoTree interactive story DAGs into unlabeled T1/T2/T3 instances."""

import argparse
import copy
import json
import hashlib
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prompts.loader import get_prompt

TASK_T1 = "T1_state_tracking"
TASK_T2 = "T2_history_sensitive_merge"
TASK_T3 = "T3_counterfactual_choice_effect"


def slug(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")


def graph(story):
    nodes = {node["node_id"]: node for node in story["nodes"]}
    edges = {}
    for node_id, node in nodes.items():
        if node["node_type"] == "decision":
            edges[node_id] = [(option["target_node_id"], option) for option in node["options"]]
        elif node["node_type"] == "ending":
            edges[node_id] = []
        else:
            edges[node_id] = [(node["next_node_id"], None)]
    return nodes, edges


def paths_to(story, target_node_id):
    nodes, edges = graph(story)
    root = story["scenario"]["root_node_id"]
    if target_node_id not in nodes:
        raise ValueError(f"unknown target node: {target_node_id}")
    found = []

    def walk(node_id, node_path, choices, visiting):
        if node_id in visiting:
            raise ValueError(f"cycle detected at {node_id}")
        next_nodes = node_path + [node_id]
        if node_id == target_node_id:
            found.append({"node_ids": next_nodes, "choices": choices})
            return
        visiting.add(node_id)
        for next_id, option in edges[node_id]:
            next_choices = choices
            if option is not None:
                next_choices = choices + [{
                    "decision_node_id": node_id,
                    "option_id": option["option_id"],
                    "label": option["label"],
                    "player_action": option["player_action"],
                }]
            walk(next_id, next_nodes, next_choices, visiting)
        visiting.remove(node_id)

    walk(root, [], [], set())
    return found


def choice_ids(path):
    return [choice["option_id"] for choice in path["choices"]]


def public_scene(node, modality):
    scene = node.get("scene", {})
    result = {key: scene[key] for key in ("location", "time", "stage_direction") if key in scene}
    talking_head = scene.get("talking_head")
    media = []
    if talking_head:
        result["talking_head_transcript"] = talking_head["line"]
        if modality == "text_video":
            media.append({
                "media_id": f"{node['node_id']}_TALKING_HEAD",
                "media_type": "video",
                "role": "decision_stimulus",
                "asset_status": "spec_only",
                "asset_path": None,
                "duration_seconds": talking_head["duration_seconds"],
                "transcript": talking_head["line"],
                "generation_spec": copy.deepcopy(talking_head),
            })
    return result, media


def public_node(node, modality, selected=None):
    scene, media = public_scene(node, modality)
    item = {
        "node_id": node["node_id"],
        "node_type": node["node_type"],
        "round_range": node["round_range"],
    }
    if scene:
        item["scene"] = scene
    if node.get("dialogue"):
        item["dialogue"] = copy.deepcopy(node["dialogue"])
    if selected:
        item["selected_option"] = copy.deepcopy(selected)
    return item, media


def render_path(story, path, modality, exclude_last=False):
    nodes, _ = graph(story)
    selected = {choice["decision_node_id"]: choice for choice in path["choices"]}
    node_ids = path["node_ids"][:-1] if exclude_last else path["node_ids"]
    history, media = [], []
    for node_id in node_ids:
        item, node_media = public_node(nodes[node_id], modality, selected.get(node_id))
        history.append(item)
        media.extend(node_media)
    return history, media


def render_node_sequence(story, node_ids, path, modality):
    nodes, _ = graph(story)
    selected = {choice["decision_node_id"]: choice for choice in path["choices"]}
    history, media = [], []
    for node_id in node_ids:
        item, node_media = public_node(nodes[node_id], modality, selected.get(node_id))
        history.append(item)
        media.extend(node_media)
    return history, media


def selected_option_id(path, node_id):
    for choice in path["choices"]:
        if choice["decision_node_id"] == node_id:
            return choice["option_id"]
    return None


def split_comparison_paths(path_a, path_b):
    ids_a = path_a["node_ids"][:-1]
    ids_b = path_b["node_ids"][:-1]
    index = 0
    while index < min(len(ids_a), len(ids_b)):
        node_a, node_b = ids_a[index], ids_b[index]
        if node_a != node_b:
            break
        if selected_option_id(path_a, node_a) != selected_option_id(path_b, node_b):
            break
        index += 1
    return ids_a[:index], ids_a[index:], ids_b[index:]


def covered_rounds(nodes, node_ids):
    return sorted({round_id for node_id in node_ids for round_id in range(nodes[node_id]["round_range"][0], nodes[node_id]["round_range"][1] + 1)})


def base_record(story, instance_id, task, modality):
    scenario = story["scenario"]
    design = story["benchmark_design"]
    return {
        "instance_id": instance_id,
        "benchmark_version": design["benchmark_version"],
        "story_id": scenario["scenario_id"],
        "story_version": story["schema_version"],
        "task_type": task,
        "language": scenario["language"],
        "split": "unassigned",
        "modality": modality,
        "input": {},
        "target_spec": {},
        "ground_truth": None,
        "label_status": "pending_human_annotation",
        "metadata": {
            "source_type": "synthetic_interactive_story",
            "author_effects_exposed": False,
        },
    }


def selected_t1_candidates(story):
    """Select exactly the preregistered number of semantic T1 instances."""
    design = story["benchmark_design"]
    sampling = design["t1_sampling_plan"]
    buckets = []
    for checkpoint in design["checkpoints"]:
        if TASK_T1 not in checkpoint["supported_tasks"]:
            continue
        buckets.append([
            {"checkpoint": checkpoint, "path_index": index, "path": path}
            for index, path in enumerate(paths_to(story, checkpoint["node_id"]), 1)
        ])
    target = sampling["semantic_instances_per_world"]
    selected = []
    offsets = [0] * len(buckets)
    while len(selected) < target:
        progressed = False
        for bucket_index, bucket in enumerate(buckets):
            if offsets[bucket_index] >= len(bucket):
                continue
            selected.append(bucket[offsets[bucket_index]])
            offsets[bucket_index] += 1
            progressed = True
            if len(selected) == target:
                break
        if not progressed:
            break
    if len(selected) != target:
        raise ValueError(
            f"{story['scenario']['scenario_id']}: requested {target} semantic T1 instances, "
            f"but only {len(selected)} candidates are available"
        )
    return selected


def t1_records(story):
    scenario_id = story["scenario"]["scenario_id"]
    design = story["benchmark_design"]
    sampling = design["t1_sampling_plan"]
    nodes, _ = graph(story)
    for candidate_index, candidate in enumerate(selected_t1_candidates(story), 1):
        checkpoint = candidate["checkpoint"]
        path_index = candidate["path_index"]
        path = candidate["path"]
        for modality in sampling["required_variants"]:
            semantic_id = slug(f"{scenario_id}_{TASK_T1}_S{candidate_index}_{checkpoint['checkpoint_id']}_P{path_index}")
            variant_id = modality
            iid = slug(f"{semantic_id}_{variant_id}")
            record = base_record(story, iid, TASK_T1, modality)
            record["semantic_instance_id"] = semantic_id
            record["variant_id"] = variant_id
            history, media = render_path(story, path, modality, exclude_last=True)
            history_node_ids = path["node_ids"][:-1]
            history_rounds = sorted({
                round_id
                for node_id in history_node_ids
                for round_id in range(nodes[node_id]["round_range"][0], nodes[node_id]["round_range"][1] + 1)
            })
            minimum_history = checkpoint.get("minimum_history_rounds", 8)
            if len(history_rounds) < minimum_history:
                raise ValueError(
                    f"{checkpoint['checkpoint_id']}: T1 path has {len(history_rounds)} history rounds, "
                    f"expected at least {minimum_history}"
                )
            current_scene, current_media = public_node(nodes[checkpoint["node_id"]], modality)
            visible_evidence = [node_id for node_id in checkpoint.get("key_evidence_node_ids", []) if node_id in history_node_ids]
            current_start = nodes[checkpoint["node_id"]]["round_range"][0]
            evidence_rounds = [nodes[node_id]["round_range"][0] for node_id in visible_evidence]
            record["input"] = {
                "instruction": get_prompt("task_t1_v0.2"),
                "target_character_id": design["target_character_id"],
                "history_view": "full_history",
                "history": history,
                "change_anchor_node_id": checkpoint["change_anchor_node_id"],
                "current_scene": current_scene,
                "media": media + current_media,
            }
            record["target_spec"] = {
                "prediction_format": "subjective_state_tracking_v0.2",
                "target_state_ids": checkpoint["target_state_ids"],
                "intensity_labels": ["absent", "mild", "moderate", "strong", "very_strong", "cannot_determine"],
                "intensity_scale_type": "ordinal_with_unknown",
                "require_intensity_probability_distribution": True,
                "allowed_change_directions": ["increase", "similar", "decrease", "cannot_determine"],
                "require_change_probability_distribution": True,
                "require_evidence_node_ids": True,
                "require_self_reported_confidence": False,
                "model_confidence_source": "predicted_probability_distribution",
            }
            record["metadata"].update({
                "t1_sampling_strategy": sampling["selection_strategy"],
                "t1_sampling_seed": sampling["seed"],
                "t1_semantic_index_within_world": candidate_index,
                "checkpoint_id": checkpoint["checkpoint_id"],
                "checkpoint_node_id": checkpoint["node_id"],
                "history_path_node_ids": path["node_ids"],
                "choice_path": choice_ids(path),
                "history_start_round": history_rounds[0],
                "history_end_round": history_rounds[-1],
                "history_length_rounds": len(history_rounds),
                "checkpoint_round": current_start,
                "change_anchor_node_id": checkpoint["change_anchor_node_id"],
                "key_evidence_node_ids": visible_evidence,
                "causal_distance_rounds": current_start - min(evidence_rounds) if evidence_rounds else None,
                "decision_count_in_history": len(path["choices"]),
                "merge_count_in_history": sum(nodes[node_id]["node_type"] == "merge_dialogue" for node_id in history_node_ids),
                "human_confidence_scale": ["low", "medium", "high", "very_high"],
            })
            yield record

def select_path(story, node_id, required_choice_path):
    matches = [path for path in paths_to(story, node_id) if choice_ids(path) == required_choice_path]
    if len(matches) != 1:
        raise ValueError(f"{node_id}: expected one path for {required_choice_path}, found {len(matches)}")
    return matches[0]


def t2_records(story):
    scenario_id = story["scenario"]["scenario_id"]
    design = story["benchmark_design"]
    sampling = design["t2_sampling_plan"]
    comparisons = design["merge_comparisons"]
    if len(comparisons) != sampling["semantic_instances_per_world"]:
        raise ValueError(
            f"{scenario_id}: expected {sampling['semantic_instances_per_world']} T2 comparisons, "
            f"found {len(comparisons)}"
        )
    nodes, _ = graph(story)
    characters = {character["character_id"]: character for character in story["characters"]}
    target_id = design["target_character_id"]
    target_character = {
        "character_id": target_id,
        "name": characters[target_id]["name"],
        "identity": characters[target_id]["identity"],
    }
    for semantic_index, comparison in enumerate(comparisons, 1):
        path_a = select_path(story, comparison["merge_node_id"], comparison["history_a"]["choice_path"])
        path_b = select_path(story, comparison["merge_node_id"], comparison["history_b"]["choice_path"])
        shared_ids, delta_a_ids, delta_b_ids = split_comparison_paths(path_a, path_b)
        if not delta_a_ids or not delta_b_ids:
            raise ValueError(f"{comparison['comparison_id']}: histories do not contain a usable divergence")
        merge_node = nodes[comparison["merge_node_id"]]
        merge_round = merge_node["round_range"][0]
        divergence_round = min(nodes[delta_a_ids[0]]["round_range"][0], nodes[delta_b_ids[0]]["round_range"][0])
        shared_rounds = covered_rounds(nodes, shared_ids)
        rounds_a = covered_rounds(nodes, shared_ids + delta_a_ids)
        rounds_b = covered_rounds(nodes, shared_ids + delta_b_ids)
        semantic_id = slug(f"{scenario_id}_{TASK_T2}_S{semantic_index}_{comparison['comparison_id']}")
        for modality in sampling["required_variants"]:
            variant_id = modality
            iid = slug(f"{semantic_id}_{variant_id}")
            record = base_record(story, iid, TASK_T2, modality)
            record["semantic_instance_id"] = semantic_id
            record["variant_id"] = variant_id
            shared_history, media_shared = render_node_sequence(story, shared_ids, path_a, modality)
            history_a_delta, media_a = render_node_sequence(story, delta_a_ids, path_a, modality)
            history_b_delta, media_b = render_node_sequence(story, delta_b_ids, path_b, modality)
            current_scene, current_media = public_node(merge_node, modality)
            current_hash = hashlib.sha256(
                json.dumps(current_scene, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            record["input"] = {
                "instruction": get_prompt("task_t2_v0.2"),
                "target_character": target_character,
                "shared_history_prefix": shared_history,
                "history_a_delta": history_a_delta,
                "history_b_delta": history_b_delta,
                "shared_current_scene": current_scene,
                "media_shared_prefix": media_shared,
                "media_a_delta": media_a,
                "media_b_delta": media_b,
                "shared_current_media": current_media,
            }
            record["target_spec"] = {
                "prediction_format": "pairwise_state_difference_v0.2",
                "target_state_ids": comparison["target_state_ids"],
                "direction_labels": ["higher_in_a", "similar", "higher_in_b", "cannot_determine"],
                "require_direction_probability_distribution": True,
                "require_evidence_node_ids": True,
                "candidate_causal_choice_ids": comparison["causal_choice_ids"],
                "require_causal_choice_probabilities": True,
                "require_self_reported_confidence": False,
                "model_confidence_source": "predicted_probability_distribution",
            }
            record["metadata"].update({
                "t2_sampling_strategy": sampling["selection_strategy"],
                "t2_sampling_seed": sampling["seed"],
                "t2_semantic_index_within_world": semantic_index,
                "comparison_id": comparison["comparison_id"],
                "merge_node_id": comparison["merge_node_id"],
                "shared_current_scene_hash": f"sha256:{current_hash}",
                "shared_prefix_node_ids": shared_ids,
                "history_a_delta_node_ids": delta_a_ids,
                "history_b_delta_node_ids": delta_b_ids,
                "shared_prefix_length_rounds": len(shared_rounds),
                "history_a_length_rounds": len(rounds_a),
                "history_b_length_rounds": len(rounds_b),
                "divergence_round": divergence_round,
                "merge_round": merge_round,
                "causal_distance_rounds": merge_round - divergence_round,
                "decision_depth": max(len(path_a["choices"]), len(path_b["choices"])),
                "merge_depth": sum(nodes[node_id]["node_type"] == "merge_dialogue" for node_id in shared_ids),
                "controlled_current_scene": comparison["controlled_current_scene"],
                "canonical_history_a_choice_path": choice_ids(path_a),
                "canonical_history_b_choice_path": choice_ids(path_b),
                "candidate_causal_choice_ids": comparison["causal_choice_ids"],
                "presentation_order_policy": "balanced_ab_ba",
            })
            yield record

def selected_t3_candidates(story):
    design = story["benchmark_design"]
    sampling = design["t3_sampling_plan"]
    buckets = []
    for decision_node_id in design["counterfactual_decision_node_ids"]:
        buckets.append([
            {"decision_node_id": decision_node_id, "path_index": index, "path": path}
            for index, path in enumerate(paths_to(story, decision_node_id), 1)
        ])
    target = sampling["semantic_instances_per_world"]
    selected = []
    offsets = [0] * len(buckets)
    while len(selected) < target:
        progressed = False
        for bucket_index, bucket in enumerate(buckets):
            if offsets[bucket_index] >= len(bucket):
                continue
            selected.append(bucket[offsets[bucket_index]])
            offsets[bucket_index] += 1
            progressed = True
            if len(selected) == target:
                break
        if not progressed:
            break
    if len(selected) != target:
        raise ValueError("{}: requested {} semantic T3 instances, but only {} candidates are available".format(story["scenario"]["scenario_id"], target, len(selected)))
    return selected


def ordered_t3_state_ids(story, decision, minimum, maximum):
    affected = {state_id for option in decision["options"] for group in option["effects"].values() for state_id in group}
    ontology_order = [state_id for group in story["state_schema"].values() for state_id in group]
    state_ids = [state_id for state_id in ontology_order if state_id in affected]
    if len(state_ids) < minimum:
        raise ValueError("{}: only {} T3 states; minimum is {}".format(decision["node_id"], len(state_ids), minimum))
    return state_ids[:maximum]


def t3_records(story):
    scenario_id = story["scenario"]["scenario_id"]
    design = story["benchmark_design"]
    sampling = design["t3_sampling_plan"]
    nodes, _ = graph(story)
    for semantic_index, candidate in enumerate(selected_t3_candidates(story), 1):
        decision_node_id = candidate["decision_node_id"]
        path_index = candidate["path_index"]
        path = candidate["path"]
        decision = nodes[decision_node_id]
        if decision["node_type"] != "decision":
            raise ValueError("{} is not a decision".format(decision_node_id))
        state_ids = ordered_t3_state_ids(story, decision, sampling["minimum_target_state_count"], sampling["maximum_target_state_count"])
        semantic_id = slug("{}_{}_S{}_{}_P{}".format(scenario_id, TASK_T3, semantic_index, decision_node_id, path_index))
        for modality in sampling["required_variants"]:
            iid = slug("{}_{}".format(semantic_id, modality))
            record = base_record(story, iid, TASK_T3, modality)
            record["semantic_instance_id"] = semantic_id
            record["variant_id"] = modality
            history, media = render_path(story, path, modality, exclude_last=True)
            scene, decision_media = public_scene(decision, modality)
            options = [{"option_id": option["option_id"], "label": option["label"], "player_action": option["player_action"]} for option in decision["options"]]
            target_character = next(character for character in story["characters"] if character["character_id"] == design["target_character_id"])
            record["input"] = {
                "instruction": get_prompt("task_t3_v0.2"),
                "target_character": {"character_id": target_character["character_id"], "name": target_character["name"], "identity": target_character["identity"]},
                "history_view": "full_history",
                "shared_history": history,
                "decision": {"node_id": decision_node_id, "round_range": decision["round_range"], "scene": scene, "prompt": decision["prompt"]},
                "candidate_options": options,
                "media": media + decision_media,
            }
            record["target_spec"] = {
                "prediction_format": "counterfactual_option_effects_v0.2",
                "target_state_ids": state_ids,
                "time_horizons": ["immediate", "delayed"],
                "horizon_definitions": {"immediate": "该行动发生后至对方首个直接回应结束。", "delayed": "直接回应之后，直到下一选择情景或当前故事路径结局。"},
                "change_direction_labels": ["increase", "similar", "decrease", "cannot_determine"],
                "require_change_probability_distribution": True,
                "require_evidence_node_ids": True,
                "derive_pairwise_rankings_from_probabilities": True,
                "require_self_reported_confidence": False,
                "model_confidence_source": "predicted_probability_distribution",
            }
            record["metadata"].update({
                "t3_sampling_strategy": sampling["selection_strategy"],
                "t3_sampling_seed": sampling["seed"],
                "t3_semantic_index_within_world": semantic_index,
                "decision_node_id": decision_node_id,
                "history_path_node_ids": path["node_ids"],
                "history_choice_path": choice_ids(path),
                "history_length_rounds": len(covered_rounds(nodes, path["node_ids"][:-1])),
                "candidate_option_ids": [option["option_id"] for option in decision["options"]],
                "option_count": len(decision["options"]),
            })
            yield record


def records(story):
    yield from t1_records(story)
    yield from t2_records(story)
    yield from t3_records(story)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stories", nargs="+")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for filename in args.stories:
        story = json.loads(Path(filename).read_text(encoding="utf-8"))
        rows.extend(records(story))
    ids = [row["instance_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate benchmark instance_id")
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    counts = {}
    for row in rows:
        key = (row["story_id"], row["task_type"], row["modality"])
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({
        "output": str(output),
        "instance_count": len(rows),
        "counts": [{"story_id": k[0], "task": k[1], "modality": k[2], "count": v} for k, v in sorted(counts.items())],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
