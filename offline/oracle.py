"""Hash-bound omniscient reference authoring; machine proposals are never human GT.

The evaluated projection remains tasks.offline_choice.public_instance. Private
packets contain the actual selected state variables, checkpoint histories and
controlled outcomes, never inferred replacements for missing simulator state.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from environment.delta_mapper import flatten_state
from environment.state_ontology import STATE_VARIABLE_ONTOLOGY
from offline.choice_builder import load, save, save_text, sha, write_bundle
from offline.choice_pipeline import runtime
from offline.provider_compat import OfflineLoggedProvider, OfflineSamplingProvider
from offline.reuse_audit import digest
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from providers.structured import _parse_json_output
from tasks.offline_choice import public_instance, validate_item
from tasks.offline_design import grouped_record

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "tasks/examples/offline_scenarios_v2"

AUTHOR_PROMPT = """你是合成社会理解基准的上帝视角出题者。你得到完整的制作侧人物设定、实际私有状态和受控回放；被测者只能看到 public_input。
目标：为给定的两道题产生可由公开材料合理推断、且与实际私有记录相容的唯一最佳答案。旧题没有提供作者答案。
尽量保留题面；若目标变量不存在、旧选项没有正确项、唯一性不足或与实际状态冲突，修改题干/选项/目标变量，保留 instance_id、subtype、冻结公开输入、人物方向和时间窗口。
仅可选择 allowed_state_paths 中实际记录的变量。不得把非所选变量当作已记录状态。T1 用截止点及指定比较区间，禁止未来倒灌；T2 用相同初始快照、相同结尾的 A/B 实际回放；T3 用两条候选分支和指定窗口。
数值状态是0-10的私有操作化记录，不能把一个等级的小变化说成巨变，不能用台词修辞推翻实际记录。同值就不能声称一方确定更高。同时阅读人物目标、状态判定依据和互动事实；合作、情绪、信任、风险不能互相替代。
T3每个行动只有一条实现轨迹，不能把某次随机实现说成已估计的普遍概率或必然规律；可问有公开机制支持且与回放相容的方向/取舍；若材料仍不能支持唯一答案，必须在 unresolved_issues 中说明，绝不硬造通过。不要把隐藏的未来细节写入题干作为已知事实。
四个选项均要合理、长度相近，不靠极端措辞泄漏答案。保留原题 subtype；组合题两变量；证据题用公开证据；风险题明确事件和窗口；T3明确比较基准和时间。公开 evidence_ids 只能引用 context、公开turn_id、ending、action_1/action_2，私有证据另写 oracle_evidence_ids。
只返回 JSON {"questions":[...]}，每题完整字段：
{"instance_id":"原ID","subtype":"原形式","question":"中文题干","options":{"A":"...","B":"...","C":"...","D":"..."},"target_spec":{完整原spec，允许改target_state_ids及相应risk/goal字段，不改checkpoint、horizon、comparison或comparison_interval},"answer":"A",
"rationale":"公开推理理由，不泄露私有未来","oracle_rationale":"私有状态、人物和分支支持的上帝视角解释，并解释最强竞争项","oracle_evidence_ids":["private:t2","action_1:immediate"],
"evidence_ids":["t1","t2"],"counterevidence_ids":[],"option_errors":{"B":"unsupported_inference","C":"state_dimension_confusion","D":"history_ignored"},
"option_variable_map":{"A":{"所选变量":"判断"},"B":{"所选变量":"判断"},"C":{"所选变量":"判断"},"D":{"所选变量":"判断"}},
"changes":"保留或修订原因","unresolved_issues":[]}
每题必须有非空的 oracle_rationale 和实际存在的 oracle_evidence_ids。无法做到唯一且可靠时仍返回最佳候选并明确 unresolved_issues。"""

REVIEW_PROMPT = """独立核验合成基准的上帝视角答案，未给你作者选项或解释。public_input 是被测信息，private_evidence 仅供定答。逐题独立选择最佳选项并核对实际私有记录、目标变量、时点和分支窗口。实际状态同值不能凭台词声称数值高低；合作不等于信任；一条未来分支不能证明普遍概率。T1不得引用截止点以后事件。T2共同表达完全相同。T3应有公开的行动机制，不能靠隐藏的偶然未来才能选对。检查选项唯一性和主体方向。
仅返回JSON {"answers":[{"instance_id":"...","answer":"A","plausible_answers":["A"],"issues":[],"reason":"具体私有证据及限制","oracle_evidence_ids":["private:t2"]}]}。
issues 用实际问题：missing_state、state_conflict、ambiguous、private_only、scope_mismatch、branch_overclaim、wrong_subject、option_cue；没有问题则空。"""


def now():
    return datetime.now(timezone.utc).isoformat()


def bound_source(source, kind):
    path = (ROOT / source[kind + "_path"]).resolve()
    if ROOT not in path.parents or sha(path) != source[kind + "_sha256"]:
        raise ValueError("source hash/path mismatch: " + kind)
    return load(path)


def private_turn(turn, evidence_id):
    return {
        "evidence_id": evidence_id,
        "turn_id": turn.get("turn_id"),
        "action": turn.get("policy_action", {}).get("text"),
        "response": turn.get("environment_response"),
        "observable_expression": turn.get("observable_expression"),
        "state_before": flatten_state(turn["state_before"]),
        "state_after": flatten_state(turn.get("state_after_public_events", turn["state_after"])),
        "state_judgments": turn.get("state_judgments"),
        "interaction_events": turn.get("environment_response_ledger_events"),
        "public_events": turn.get("segment_transition_after"),
    }


def canonical_expression(expression):
    """Omitted optional public cues mean no cue, not a new private observation."""
    allowed = {"facial_expression", "gaze", "speech_style", "prosody", "behavioral_cues"}
    if set(expression) - allowed:
        raise ValueError("unknown controlled expression field")
    return {key: deepcopy(expression.get(key, [] if key == "behavioral_cues" else ""))
            for key in sorted(allowed)}


def validate_t2_replay(item, trajectory, replay):
    snapshot = deepcopy(trajectory["turns"][1]["environment_snapshot_before"])
    snapshot["counterfactual_timeline_lock"] = True
    ending = item["input"]["shared_ending"]
    for side in ("a", "b"):
        log = replay[side]
        if (log["environment_snapshot_before"] != snapshot
                or log["policy_action"]["text"] != item["input"]["history_" + side][-1]["evaluated_agent"]
                or log["environment_response"] != ending["current_response"]
                or canonical_expression(log["observable_expression"]) != canonical_expression(ending["observable_expression"])):
            raise ValueError("T2 replay does not match frozen history, ending or snapshot")
    return replay


def ensure_t2(item, run):
    source = item["authoring"]["construction_source"]
    trajectory = bound_source(source, "trajectory")
    if source.get("replay_path") and item["authoring"]["replay_status"] == "validated":
        try:
            old = validate_t2_replay(item, trajectory, bound_source(source, "replay"))
            return old, {k: source[k] for k in ("replay_path", "replay_sha256")}
        except (ValueError, KeyError, TypeError):
            # Retain old evidence, but never reuse a cache for a different input.
            pass
    directory = run / "t2" / item["story_id"]
    binding = digest({"input": item["input"], "source": source, "code": sha(Path(__file__))})
    path = directory / "replay.json"
    if path.exists():
        saved = load(path)
        if saved["binding"] != binding:
            raise ValueError("T2 run binding changed; use a new run")
        return validate_t2_replay(item, trajectory, saved["replay"]), {
            "replay_path": str((directory / "logs.json").relative_to(ROOT)),
            "replay_sha256": sha(directory / "logs.json"),
        }
    config = load(ROOT / "configs/offline_gpt50_t1_t3.json")
    config.update(request_timeout=100, transport_attempts=1, call_log_dir=str(directory / "calls"))
    factory, _ = runtime(config, bound_source(source, "scenario"), int(item["story_id"].split("_")[-1]) - 1)
    save(directory / "runtime.json", {"binding": binding, "environment": factory.provenance})
    replay = {}
    for side in ("a", "b"):
        side_path = directory / (side + ".json")
        if side_path.exists():
            part = load(side_path)
            if part["binding"] != binding:
                raise ValueError("partial T2 binding changed")
            replay[side] = part["log"]
            continue
        env = factory()
        env.restore(trajectory["turns"][1]["environment_snapshot_before"],
                    episode_id="oracle-" + item["story_id"] + "-" + side)
        env.session["counterfactual_timeline_lock"] = True
        ending = {k: deepcopy(item["input"]["shared_ending"][k])
                  for k in ("current_response", "observable_expression")}
        ending["observable_expression"] = canonical_expression(ending["observable_expression"])
        _, log = env.step(
            {"text": item["input"]["history_" + side][-1]["evaluated_agent"]},
            controlled_observation={**ending, "media": [], "control_scope": "t2_shared_ending"})
        replay[side] = log
        save(side_path, {"binding": binding, "log": log})
    validate_t2_replay(item, trajectory, replay)
    save(directory / "logs.json", replay)
    save(path, {"binding": binding, "replay": replay})
    return replay, {"replay_path": str((directory / "logs.json").relative_to(ROOT)),
                    "replay_sha256": sha(directory / "logs.json")}


def evidence_packet(item, run, *, replay=True):
    source = item["authoring"]["construction_source"]
    scenario = bound_source(source, "scenario")
    trajectory = bound_source(source, "trajectory")
    turns = trajectory["turns"]
    cutoff = item["target_spec"]["checkpoint"]
    if cutoff == "ending":
        cutoff = item["input"]["history_a"][-1]["turn_id"].split(":")[-1]
    cutoff_index = next(i for i, t in enumerate(turns) if t["turn_id"] == cutoff)
    selected = flatten_state(trajectory["initial_state"])
    packet = {
        "scope": "author_and_GT_review_only",
        "task": item["task"],
        "public_input": deepcopy(item["input"]),
        "private_character": {k: deepcopy(scenario.get(k)) for k in (
            "environment_agent", "environment_background", "environment_visible_narrative",
            "mechanism", "initialization_notes", "selected_state_variables")},
        "initial_state": selected,
        "prefix": [private_turn(t, "private:" + t["turn_id"]) for t in turns[:cutoff_index + 1]],
        "sources": deepcopy(source),
        "caveat": "Simulator state is operationalized evidence, not human-attested truth; branch samples do not estimate outcome probabilities.",
    }
    state_sets = [set(selected)] + [
        set(t["state_before"]) & set(t["state_after"]) for t in packet["prefix"]]
    if item["task"] == "T2":
        if not replay:
            raise ValueError("T2 requires controlled replay")
        pair, binding = ensure_t2(item, run)
        packet["sources"].update(binding)
        packet["replays"] = {side: private_turn(log, "private:" + side.upper() + ":ending")
                             for side, log in pair.items()}
        # The original t2 response is not either controlled history's ending.
        packet["prefix"] = packet["prefix"][:-1]
        state_sets.extend(set(t["state_after"]) for t in packet["replays"].values())
    elif item["task"] == "T3":
        branches = bound_source(source, "replay")
        actions = item["input"]["candidate_actions"]
        if len(branches) != len(actions) or len({b["snapshot_sha256"] for b in branches}) != 1:
            raise ValueError("T3 common origin mismatch")
        packet["branches"] = []
        for action, branch in zip(actions, branches):
            if action["text"] != branch["candidate_action"]["text"]:
                raise ValueError("T3 action mismatch")
            if not branch["window_complete"] or len(branch["future_turns"]) < 5:
                raise ValueError("T3 missing full branch window")
            branch_turns = [private_turn(t, action["action_id"] + ":" + ("immediate" if i == 0 else f"step{i+1}"))
                            for i, t in enumerate(branch["future_turns"])]
            state_sets.extend(set(t["state_after"]) for t in branch_turns)
            packet["branches"].append({"action_id": action["action_id"], "turns": branch_turns,
                                       "sample_count": 1, "window_complete": True,
                                       "snapshot_sha256": branch["snapshot_sha256"],
                                       "external_event_plan_hash": branch.get("external_event_plan_hash")})
    packet["allowed_state_paths"] = sorted(set.intersection(*state_sets))
    packet["state_definitions"] = {p: STATE_VARIABLE_ONTOLOGY[p] for p in packet["allowed_state_paths"]}
    packet["evidence_ids"] = ["private:initial"] + [t["evidence_id"] for t in packet["prefix"]]
    packet["evidence_ids"] += [t["evidence_id"] for t in packet.get("replays", {}).values()]
    packet["evidence_ids"] += [t["evidence_id"] for b in packet.get("branches", []) for t in b["turns"]]
    return packet


def patch_item(original, proposal, packet, artifact):
    item = deepcopy(original)
    if proposal["instance_id"] != item["instance_id"] or proposal["subtype"] != item["subtype"]:
        raise ValueError("item identity/form changed")
    spec = proposal["target_spec"]
    for key in ("checkpoint", "state_owner", "state_target", "horizon", "comparison",
                "comparison_interval", "delayed_horizon", "immediate_anchor"):
        if spec.get(key) != item["target_spec"].get(key):
            raise ValueError("frozen target scope changed: " + key)
    if not set(spec["target_state_ids"]) <= set(packet["allowed_state_paths"]):
        raise ValueError("unrecorded state variable")
    ids = proposal.get("oracle_evidence_ids", [])
    if not ids or not set(ids) <= set(packet["evidence_ids"]) or not proposal.get("oracle_rationale"):
        raise ValueError("missing/unknown oracle evidence")
    if not isinstance(proposal.get("unresolved_issues"), list):
        raise ValueError("missing unresolved issue list")
    item.update(question=proposal["question"], options=proposal["options"], target_spec=spec)
    author = item["authoring"]
    for key in ("answer", "rationale", "evidence_ids", "counterevidence_ids",
                "option_errors", "option_variable_map"):
        author[key] = deepcopy(proposal[key])
    # Keep the original preregistered balance without asking the model to favor
    # a letter. Rotate all option-indexed annotations together.
    letters = "ABCD"
    shift = (letters.index(original["authoring"]["answer"]) - letters.index(author["answer"])) % 4
    mapping = {letter: letters[(i + shift) % 4] for i, letter in enumerate(letters)}
    for obj, key in ((item, "options"), (author, "option_errors"), (author, "option_variable_map")):
        obj[key] = dict(sorted((mapping[k], v) for k, v in obj[key].items()))
    author["answer"] = mapping[author["answer"]]
    author.pop("acceptable_answers", None)
    author.pop("api_screening", None)
    author["construction_source"] = deepcopy(packet["sources"])
    author["generation_source"] = {
        "kind": "api_authored_with_omniscient_evidence",
        "path": str(artifact.relative_to(ROOT)), "prompt_sha256": digest(AUTHOR_PROMPT),
        "result_sha256": digest(proposal), "previous_item_sha256": digest(original),
    }
    author["oracle_reference"] = {
        "status": "machine_proposed_pending_independent_check",
        "answer": author["answer"], "rationale": proposal["oracle_rationale"],
        "evidence_ids": ids, "unresolved_issues": proposal["unresolved_issues"],
        "changes": proposal["changes"], "human_verified": False,
        "packet_path": str(artifact.with_name("evidence.json").relative_to(ROOT)),
        "packet_sha256": sha(artifact.with_name("evidence.json")),
    }
    author["review_status"] = "pending_human_review"
    author["source_admission"] = {"formal_admitted": False, "reason": "pending_source_and_human_review"}
    if item["task"] == "T2":
        author["replay_status"] = "validated"
        author["history_control"]["state_check"] = {
            "status": "controlled_replay_verified",
            "path": packet["sources"]["replay_path"],
            "sha256": packet["sources"]["replay_sha256"],
        }
    bindings = []
    for variable in spec["target_state_ids"]:
        row = {"state_id": variable, "owner": spec["state_owner"], "object": spec["state_target"]}
        if variable.startswith("consequence_risk."):
            row.update(risk_event=spec.get("risk_event"), risk_window=spec.get("risk_window"))
        bindings.append(row)
    item["analysis"]["state_bindings"] = bindings
    item["ground_truth"], item["label_status"] = None, "pending_human_annotation"
    validate_item(item)
    return item


def json_call(run, name, prompt, payload, config, validate, tokens=6500):
    directory = run / name
    result_path = directory / "result.json"
    binding = digest({"prompt": prompt, "payload": payload, "provider": public_provider_config(config)})
    if result_path.exists():
        record = load(result_path)
        if record["binding"] != binding:
            raise ValueError("cached API input changed: " + name)
        validate(record["result"])
        return record["result"]
    provider = OfflineLoggedProvider(OfflineSamplingProvider(build_provider(config)), directory / "calls")
    messages = [{"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    existing = list((directory / "calls").glob("*.json"))
    if len(existing) >= 3:
        raise RuntimeError("three logged attempts exhausted: " + name)
    for attempt in range(3 - len(existing)):
        try:
            raw = provider.complete(messages, temperature=0, max_tokens=tokens)
            data = _parse_json_output(raw)
            validate(data)
            save(result_path, {"binding": binding, "result": data,
                               "provider": public_provider_config(config), "completed_at": now()})
            return data
        except Exception as exc:
            save(directory / "errors" / (str(time.time_ns()) + ".json"),
                 {"error": type(exc).__name__, "message": str(exc)})
            if attempt == 2 - len(existing):
                raise
            messages.append({"role": "user", "content": "请重新输出完整JSON并修正：" + str(exc)[:700]})


def group_job(items, run, config):
    name = items[0]["story_id"] + "-" + items[0]["task"]
    directory = run / "groups" / name
    packet = evidence_packet(items[0], run)
    evidence_path = directory / "evidence.json"
    if evidence_path.exists() and load(evidence_path) != packet:
        raise ValueError("frozen oracle packet changed")
    save(evidence_path, packet)
    artifact = directory / "result.json"
    payload = {"public_input": packet["public_input"],
               "private_evidence": {k: v for k, v in packet.items() if k != "public_input"},
               "allowed_state_paths": packet["allowed_state_paths"],
               "questions": [{k: x[k] for k in ("instance_id", "task", "subtype", "question", "options", "target_spec")} for x in items]}
    from tasks.offline_choice import ERROR_TYPES
    payload["allowed_option_errors"] = sorted(ERROR_TYPES)
    def validate(data):
        rows = data["questions"]
        if [x["instance_id"] for x in rows] != [x["instance_id"] for x in items]:
            raise ValueError("need both original question IDs in order")
        for original, proposal in zip(items, rows):
            patch_item(original, proposal, packet, artifact)
    data = json_call(run, "groups/" + name, AUTHOR_PROMPT, payload, config, validate)
    revised = [patch_item(x, q, packet, artifact) for x, q in zip(items, data["questions"])]
    save(directory / "items.json", revised)
    return revised


def review_group(items, run, config):
    name = items[0]["story_id"] + "-" + items[0]["task"]
    packet = load(run / "groups" / name / "evidence.json")
    payload = {"public_input": packet["public_input"],
               "private_evidence": {k: v for k, v in packet.items() if k != "public_input"},
               "questions": [{k: x[k] for k in ("instance_id", "task", "subtype", "question", "options", "target_spec")} for x in items]}
    def validate(data):
        rows = data["answers"]
        if len(rows) != len(items) or {r["instance_id"] for r in rows} != {x["instance_id"] for x in items}:
            raise ValueError("review IDs mismatch")
        for row in rows:
            if (row["answer"] not in "ABCD" or row["answer"] not in row["plausible_answers"]
                    or not set(row["plausible_answers"]) <= set("ABCD")
                    or not isinstance(row["issues"], list)
                    or not row["oracle_evidence_ids"]
                    or not set(row["oracle_evidence_ids"]) <= set(packet["evidence_ids"])):
                raise ValueError("invalid oracle review")
    data = json_call(run, "reviews/" + name, REVIEW_PROMPT, payload, config, validate, 3000)
    return data


def summarize(run):
    source = [json.loads(l) for l in (run / "source.items.jsonl").read_text().splitlines()]
    authored = [x for p in sorted((run / "groups").glob("*/items.json")) for x in load(p)]
    checked, passed, concerns, blind = 0, 0, [], 0
    for item in authored:
        name = item["story_id"] + "-" + item["task"]
        ref = item["authoring"]["oracle_reference"]
        path = run / "reviews" / name / "result.json"
        if path.exists():
            data = load(path)["result"]
            row = next(r for r in data["answers"] if r["instance_id"] == item["instance_id"])
            checked += 1
            ref["independent_check"] = row
            ok = not row["issues"] and row["plausible_answers"] == [ref["answer"]] and not ref["unresolved_issues"]
            ref["status"] = "machine_consistent_pending_human" if ok else "machine_concerns_pending_revision"
            if ok:
                passed += 1
            else:
                concerns.append(item["instance_id"])
        path = run / "blind" / "blind_review" / (name + ".json")
        if path.exists():
            data = load(path)
            row = next((r for r in data["result"]["answers"] if r["instance_id"] == item["instance_id"]
                        and r["public_sha256"] == digest(public_instance(item))), None)
            if row:
                blind += 1
                item["authoring"]["api_screening"] = {**row, "reviewer_type": "blind_model_screen_not_human",
                                                      "model": data["provider"]["model"]}
                if row["issues"] or row["plausible_answers"] != [ref["answer"]]:
                    ref["status"] = "machine_concerns_pending_revision"
                    if item["instance_id"] not in concerns:
                        concerns.append(item["instance_id"])
    summary = {
        "format": "socialflux_omniscient_reference_v1", "updated_at": now(),
        "source_items": len(source), "authored_items": len(authored),
        "independently_checked_items": checked, "oracle_agreement_items": passed,
        "public_blind_checked_items": blind, "machine_concern_ids": sorted(concerns),
        "t2_replay_groups": len(list((run / "t2").glob("*/replay.json"))),
        "human_verified_items": 0, "formal_admitted_items": 0,
        "pending_groups": sorted({x["story_id"] + "-" + x["task"] for x in source}
                                 - {x["story_id"] + "-" + x["task"] for x in authored}),
        "api_calls": len(list(run.glob("**/calls/**/*.json"))),
    }
    save(run / "progress.json", summary)
    save_text(run / "candidate.items.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in authored))
    return summary, authored


def publish(run):
    summary, items = summarize(run)
    if len(items) != 300 or summary["independently_checked_items"] != 300 or summary["public_blind_checked_items"] != 300:
        raise ValueError("all 300 items require authored, omniscient and public-only checks before publication")
    old_items = {x["instance_id"]: x for x in map(json.loads, (run / "source.items.jsonl").read_text().splitlines())}
    for item in items:
        validate_item(item)
    # Preserve the complete previous release, including modality bindings.
    archive = run / "previous_release"
    if not archive.exists():
        archive.mkdir()
        for path in BANK.iterdir():
            if path.is_file():
                (archive / path.name).write_bytes(path.read_bytes())
    old_manifest = load(archive / "manifest.json")
    manifest = write_bundle(items, BANK)
    manifest.update({k: v for k, v in old_manifest.items() if k not in manifest})
    manifest.update(format="socialflux_offline_choice_v2", oracle_run=str(run.relative_to(ROOT)),
                    oracle_summary=summary, machine_flagged_ids=summary["machine_concern_ids"],
                    blind_reviewed_items=summary["public_blind_checked_items"],
                    answer_positions=dict(Counter(x["authoring"]["answer"] for x in items)))
    save(BANK / "manifest.json", manifest)
    save_text(BANK / "records.jsonl", "".join(json.dumps(grouped_record(x), ensure_ascii=False) + "\n" for x in items))
    previous_pairs = [json.loads(l) for l in (archive / "paired.items.jsonl").read_text().splitlines()]
    index = {x["instance_id"]: x for x in items}
    pairs = []
    for previous in previous_pairs:
        identity = previous["metadata"]["modality_pair_id"]
        current = deepcopy(index[identity])
        if current["input"] != old_items[identity]["input"]:
            raise ValueError("public material changed; media cannot be reused")
        current.update(instance_id=previous["instance_id"], modality=previous["modality"])
        current["metadata"]["modality_pair_id"] = identity
        for key in ("media_manifest", "media_human_review", "matched_assets"):
            if key in previous["authoring"]:
                current["authoring"][key] = previous["authoring"][key]
        pairs.append(current)
    save_text(BANK / "paired.items.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in pairs))
    save_text(BANK / "paired.public.jsonl", "".join(json.dumps(public_instance(x), ensure_ascii=False) + "\n" for x in pairs))
    save(run / "published.json", {"at": now(), "items_sha256": sha(BANK / "items.jsonl"), "summary": summary})
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="data/offline_oracle_20261020")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--phase", choices=("author", "review", "blind", "summary", "publish"), default="author")
    args = parser.parse_args()
    run = (ROOT / args.run).resolve()
    run.mkdir(parents=True, exist_ok=True)
    source_path = run / "source.items.jsonl"
    if not source_path.exists():
        source_path.write_bytes((BANK / "items.jsonl").read_bytes())
    items = [json.loads(l) for l in source_path.read_text().splitlines()]
    config = ModelRoutes.load(ROOT / "configs/gpt50_experiment/model_routes.hybrid.v3_2.json").provider_config("quality_review")
    config.update(timeout=120, max_transport_attempts=1, retry_backoff_seconds=0, max_tokens=7000)
    manifest_path = run / "manifest.json"
    freeze = {"source_sha256": sha(source_path), "code_sha256": sha(Path(__file__)),
              "author_prompt_sha256": digest(AUTHOR_PROMPT), "review_prompt_sha256": digest(REVIEW_PROMPT),
              "provider": public_provider_config(config), "human_gt_policy": "never auto-promote"}
    if manifest_path.exists() and load(manifest_path) != freeze:
        raise ValueError("run definition changed; freeze a new run")
    save(manifest_path, freeze)
    if args.phase in ("summary", "publish"):
        print(json.dumps(publish(run) if args.phase == "publish" else summarize(run)[0], ensure_ascii=False))
        return
    groups = defaultdict(list)
    if args.phase != "author":
        items = [x for p in sorted((run / "groups").glob("*/items.json")) for x in load(p)]
    for item in items:
        groups[item["story_id"] + "-" + item["task"]].append(item)
    selected = sorted(groups.items())[:args.limit] if args.limit else sorted(groups.items())
    from offline.scenario_v2_review import review as blind_review
    def job(name, rows):
        if args.phase == "author":
            return group_job(rows, run, config)
        if args.phase == "review":
            return review_group(rows, run, config)
        return blind_review(name, rows, run / "blind", config)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        active = {pool.submit(job, name, rows): name for name, rows in selected}
        for future in as_completed(active):
            name = active[future]
            try:
                future.result()
                print(args.phase, name, "completed", flush=True)
            except Exception as exc:
                save(run / "failures" / (name + "-" + str(time.time_ns()) + ".json"),
                     {"phase": args.phase, "error": type(exc).__name__, "message": str(exc)})
                print(args.phase, name, "FAILED", type(exc).__name__, str(exc)[:300], flush=True)
            summarize(run)
    print(json.dumps(summarize(run)[0], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
