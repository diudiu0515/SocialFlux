"""Persisted blind -> private-evidence -> machine-assisted human annotation.

Assignments freeze complete scene groups. A browser token identifies a session;
reviewer IDs are self-reported, not an external identity/authentication service.
Blind responses are immutable, and scoring excludes the participant's own GT.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
from threading import RLock

from offline.choice_builder import save
from tasks.offline_choice import public_instance
from web.offline_review import (
    ROOT, BANK_PATHS, author_reference, checked_source, item_digest,
    bound_video_materials, frozen_media_available,
)

STORE = ROOT / "data/human_annotations"
LOCK = RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def current_items(bank):
    if bank not in BANK_PATHS:
        raise ValueError("未知题库")
    raw = (ROOT / BANK_PATHS[bank] / "items.jsonl").read_bytes()
    return [json.loads(line) for line in raw.splitlines() if line.strip()], hashlib.sha256(raw).hexdigest()


def catalog(bank="scenarios-v2"):
    items, bank_sha = current_items(bank)
    counts = Counter(x["story_id"] for x in items)
    videos = bound_video_materials(items, bank)
    ready = Counter(x['story_id'] for x in items if videos[x['instance_id']]['ready'])
    return {"bank": bank, "bank_sha256": bank_sha,
            "default_modality": "text+video",
            "scenes": [{"scene": scene, "questions": counts[scene],
                        "video_questions": ready[scene], "video_available": ready[scene] == counts[scene]}
                       for scene in sorted(counts)]}


def session_path(token):
    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ValueError("标注会话无效")
    return STORE / "sessions" / (token + ".json")


def load_session(token):
    path = session_path(token)
    if not path.exists():
        raise ValueError("找不到标注会话，请使用原浏览器或保存的会话码")
    return json.loads(path.read_text())


def event(session, action, **payload):
    session["events"].append({"at": now(), "action": action, **payload})


def scene_progress(session):
    rows = []
    for scene in dict.fromkeys(x["story_id"] for x in session["items"]):
        ids = [x["instance_id"] for x in session["items"] if x["story_id"] == scene]
        blind, independent, final = (sum(identity in session[key] for identity in ids)
                                     for key in ("blind", "private_judgments", "final_judgments"))
        stage = ("complete" if final == len(ids) else "machine_review" if independent == len(ids)
                 else "private_review" if blind == len(ids) else "blind")
        rows.append({"scene": scene, "total": len(ids), "blind": blind, "private": independent, "final": final, "stage": stage})
    return rows


def status(session):
    total = len(session["items"])
    blind = len(session["blind"])
    independent = len(session["private_judgments"])
    final = len(session["final_judgments"])
    stage = ("complete" if final == total else "machine_review" if independent == total
             else "private_review" if blind == total else "blind")
    progress = scene_progress(session)
    sequential = session.get("workflow") == "scene-sequence-v1"
    active = next((row for row in progress if row["stage"] != "complete"), None)
    if sequential:
        stage = active["stage"] if active else "complete"
    return {"token": session["token"], "reviewer": session["reviewer"], "bank": session["bank"],
            "bank_sha256": session["bank_sha256"], "stage": stage, "modality": session["modality"],
            "sequential": sequential, "scenes": progress,
            "active_scene": active["scene"] if sequential and active else None,
            "items": [{"instance_id": x["instance_id"], "scene": x["story_id"],
                       "blind_submitted": x["instance_id"] in session["blind"],
                       "evidence_opened": x["instance_id"] in session["evidence_opened"],
                       "private_submitted": x["instance_id"] in session["private_judgments"],
                       "machine_opened": x["instance_id"] in session["machine_opened"],
                       "final_submitted": x["instance_id"] in session["final_judgments"]} for x in session["items"]],
            "counts": {"total": total, "blind": blind, "private": independent, "final": final},
            "baseline_eligible": session["baseline_eligible"], "baseline_exclusions": session["baseline_exclusions"],
            "identity_basis": "self_reported_reviewer_id", "ground_truth_status": "human_proposals_pending_independent_consensus"}


def start(payload):
    reviewer = str(payload.get("reviewer", "")).strip()
    if not reviewer or len(reviewer) > 100:
        raise ValueError("请填写不超过 100 字的标注人 ID")
    if payload.get("prior_exposure") not in (True, False):
        raise ValueError("请声明是否已经看过该场景的私有材料或参考答案")
    modality = payload.get("modality", "text+video")
    if modality not in ("text", "text+video"):
        raise ValueError("展示条件无效")
    bank = payload.get("bank", "scenarios-v2")
    items, bank_sha = current_items(bank)
    all_video = bound_video_materials(items, bank) if modality == 'text+video' else {}
    scenes = sorted({x["story_id"] for x in items})
    if all_video:
        scenes = [scene for scene in scenes if all(all_video[x['instance_id']]['ready'] for x in items if x['story_id'] == scene)]
    if not scenes:
        raise ValueError("当前场景缺少与当前题目版本匹配的视频，暂无可分配任务")
    requested = payload.get("scenes")
    if requested is not None and requested != scenes:
        raise ValueError("场景由系统按固定顺序分配，不能选择或跳过场景；缺少与当前题目版本匹配的视频的场景暂不分配")
    selected = [x for scene in scenes for x in items if x["story_id"] == scene]
    video_inputs = {x['instance_id']: all_video[x['instance_id']] for x in selected} if all_video else {}
    missing = [x['instance_id'] for x in selected if video_inputs and not video_inputs[x['instance_id']]['ready']]
    if missing:
        raise ValueError("所选场景缺少与当前题目版本匹配的视频，不能按视频条件分配：" + '、'.join(missing))
    exclusions = ["self_reported_prior_exposure"] if payload["prior_exposure"] else []
    # Cross-release exposure and repeat-test checks are participant/scene scoped.
    for path in (STORE / "sessions").glob("*.json"):
        prior = json.loads(path.read_text())
        if prior["reviewer"] != reviewer:
            continue
        overlap = set(scenes) & {x["story_id"] for x in prior["items"]}
        if overlap and prior["blind"]:
            exclusions.append("prior_same_scene_test:" + prior["token"][:12])
        if overlap and prior["evidence_opened"]:
            exclusions.append("prior_same_scene_private_exposure:" + prior["token"][:12])
    token = secrets.token_hex(32)
    session = {"format": "socialflux_human_annotation_session_v1", "token": token, "created_at": now(),
               "reviewer": reviewer, "bank": bank, "bank_sha256": bank_sha, "modality": modality, "workflow": "scene-sequence-v1",
               "video_inputs": video_inputs,
               "items": selected, "blind": {}, "private_judgments": {}, "final_judgments": {},
               "evidence_opened": {}, "machine_opened": {}, "events": [],
               "baseline_eligible": not exclusions, "baseline_exclusions": exclusions,
               "prior_exposure_declaration": payload["prior_exposure"]}
    event(session, "start", scenes=scenes, modality=modality,
          item_hashes={x["instance_id"]: item_digest(x) for x in selected},
          media_hashes=media_hashes(session))
    save(session_path(token), session)
    return status(session)


def selected_item(session, identity):
    item = next((x for x in session["items"] if x["instance_id"] == identity), None)
    if item is None:
        raise ValueError("题目不在此次分配中")
    return item


def media_hashes(session):
    return {identity: [{'asset_id': a['asset_id'], 'sha256': a['sha256'], 'evidence_ids': a['evidence_ids']}
                       for a in value['media']]
            for identity, value in session.get('video_inputs', {}).items()}


def video_material(session, identity):
    if session['modality'] == 'text':
        return None
    material = session.get('video_inputs', {}).get(identity)
    if not material or not material['media'] or not all(frozen_media_available(a) for a in material['media']):
        raise ValueError('已分配视频缺失或内容发生变化，请恢复原视频后继续；本次保持文字＋视频条件。')
    return material


def judgment(payload, item, *, rationale_required):
    answer = payload.get("answer")
    decision = payload.get("decision", "usable")
    if decision not in ("usable", "revise", "reject"):
        raise ValueError("审核意见无效")
    if answer not in item["options"] and not (decision == "reject" and answer is None and rationale_required):
        raise ValueError("请选择有效答案")
    rationale = str(payload.get("rationale", "")).strip()
    if rationale_required and not rationale:
        raise ValueError("请填写独立判断依据")
    accepted = payload.get("acceptable_answers", [answer] if answer else [])
    if not isinstance(accepted, list) or not set(accepted) <= item["options"].keys() or len(accepted) != len(set(accepted)):
        raise ValueError("可接受选项无效")
    if answer and answer not in accepted:
        raise ValueError("可接受选项须包含主答案")
    if decision == "usable" and rationale_required and len(accepted) != 1:
        raise ValueError("新版题目需要唯一最佳答案；存在多个可接受项时应标记修改")
    return {"answer": answer, "acceptable_answers": accepted, "rationale": rationale[:20000],
            "decision": decision, "submitted_at": now(), "item_sha256": item_digest(item)}


def private_evidence(item, bank_sha):
    """All relevant dialogue/state, without any machine answer or suggestion."""
    reference = author_reference(item, bank_sha)
    packet = item["authoring"].get("oracle_reference", {})
    oracle = checked_source(packet["packet_path"], packet.get("packet_sha256")) if packet.get("packet_path") else None
    result = {k: reference[k] for k in ("instance_id", "item_sha256", "target_spec", "scenario",
                                        "state_semantics", "source_checks", "source_turns", "replays")}
    if oracle:
        # No author proposal/check results in the evidence packet.
        result["omniscient_evidence"] = {k: oracle[k] for k in (
            "private_character", "initial_state", "prefix", "allowed_state_paths",
            "state_definitions", "evidence_ids", "replays", "branches", "caveat") if k in oracle}
        result["source_checks"]["oracle_packet"] = True
    else:
        result["source_checks"]["oracle_packet"] = False
    result["scope_note"] = ("T1 只使用题目截止点之前的全部历史；T2 使用 A/B 及同一结尾；"
                            "T3 使用共同前史及对应预测窗口的分支。其他未来不作为当前判断证据。")
    return result


def export_session(session):
    items = {x["instance_id"]: x for x in session["items"]}
    return {"format": "socialflux_human_annotation_export_v1", "reviewer": session["reviewer"],
            "bank": session["bank"], "bank_sha256": session["bank_sha256"], "modality": session["modality"],
            "baseline_eligible": session["baseline_eligible"], "baseline_exclusions": session["baseline_exclusions"],
            "blind_responses": deepcopy(session["blind"]),
            "independent_private_judgments": deepcopy(session["private_judgments"]),
            "machine_assisted_final_judgments": deepcopy(session["final_judgments"]),
            "item_hashes": {key: item_digest(value) for key, value in items.items()},
            "media_hashes": media_hashes(session),
            "public_input_hashes": {key: item_digest(value['public']) for key,value in session.get('video_inputs',{}).items()},
            "events": deepcopy(session["events"]),
            "workflow": session.get("workflow", "assignment-stages-v1"), "scene_progress": scene_progress(session),
            "formal_ground_truth": False,
            "scoring_rule": "Exclude this participant's GT and require two other independent agreeing reviewers; unresolved accuracy is null."}


def dispatch(action, payload):
    with LOCK:
        if action == "catalog":
            return catalog(payload.get("bank", "scenarios-v2"))
        if action == "start":
            return start(payload)
        session = load_session(payload.get("token"))
        if action == "status":
            return status(session)
        if action == "export":
            return export_session(session)
        item = selected_item(session, payload.get("instance_id"))
        identity = item["instance_id"]
        sequential = session.get("workflow") == "scene-sequence-v1"
        if sequential:
            active = status(session)["active_scene"]
            if active and item["story_id"] != active:
                raise ValueError("请先完成当前场景，不能跳转到其他场景")
        scoped = [x for x in session["items"] if not sequential or x["story_id"] == item["story_id"]]
        scope_ids = {x["instance_id"] for x in scoped}
        if action == "item":
            # Exact evaluated input: no capability, difficulty, author or source ratings.
            material = video_material(session, identity)
            return {"public": deepcopy(material['public']) if material else public_instance(item),
                    "media": deepcopy(material['media']) if material else [],
                    "media_coverage": deepcopy(material['media_coverage']) if material else None,
                    "blind_response": session["blind"].get(identity),
                    "private_judgment": session["private_judgments"].get(identity),
                    "final_judgment": session["final_judgments"].get(identity)}
        if action == "blind":
            if identity in session["blind"]:
                raise ValueError("盲答已提交并锁定，不能覆盖")
            if scope_ids.intersection(session["evidence_opened"]):
                raise ValueError("已查看私有证据，不能再提交盲答")
            video_material(session, identity)
            row = judgment(payload, item, rationale_required=False)
            row.update(modality=session["modality"], reviewer=session["reviewer"],
                       media_hashes=media_hashes(session).get(identity, []))
            session["blind"][identity] = row
            event(session, "blind_submitted", instance_id=identity)
        elif action == "evidence":
            if not scope_ids <= session["blind"].keys():
                raise ValueError("须先完成本场景的全部盲答，防止同场景泄漏" if sequential else "须先完成本次分配的全部盲答，防止同场景泄漏")
            session["evidence_opened"].setdefault(identity, now())
            event(session, "private_evidence_opened", instance_id=identity)
            result = private_evidence(item, session["bank_sha256"])
            save(session_path(session["token"]), session)
            return result
        elif action == "private":
            if identity not in session["evidence_opened"]:
                raise ValueError("请先查看私有证据")
            if identity in session["private_judgments"]:
                raise ValueError("独立 GT 初判已锁定；修改请记入最终审核")
            if scope_ids.intersection(session["machine_opened"]):
                raise ValueError("已查看机器建议，不能再补写独立 GT 初判")
            session["private_judgments"][identity] = judgment(payload, item, rationale_required=True)
            event(session, "private_judgment_submitted", instance_id=identity)
        elif action == "machine":
            if not scope_ids <= session["private_judgments"].keys():
                raise ValueError("须先完成全部私有证据独立初判，再开放机器建议")
            session["machine_opened"].setdefault(identity, now())
            event(session, "machine_suggestion_opened", instance_id=identity)
            save(session_path(session["token"]), session)
            return {"authoring": deepcopy(item["authoring"]), "ground_truth": deepcopy(item.get("ground_truth"))}
        elif action == "final":
            if not scope_ids <= session["private_judgments"].keys():
                raise ValueError("请先完成全部独立 GT 初判")
            if identity in session["final_judgments"]:
                raise ValueError("最终审核已提交；如需更正，请保留原记录并另行复核")
            if payload.get("human_attestation") is not True:
                raise ValueError("请确认这是你本人完成的人工审核")
            row = judgment(payload, item, rationale_required=True)
            row.update(reviewer=session["reviewer"], human_attestation=True,
                       machine_viewed=identity in session["machine_opened"])
            session["final_judgments"][identity] = row
            event(session, "final_judgment_submitted", instance_id=identity)
        else:
            raise ValueError("未知标注操作")
        save(session_path(session["token"]), session)
        return status(session)


def human_results():
    """Independent consensus and leave-participant-out baseline scoring."""
    with LOCK:
        sessions = [json.loads(p.read_text()) for p in sorted((STORE / "sessions").glob("*.json"))]
    labels = defaultdict(dict)
    for session in sessions:
        for identity, row in session["final_judgments"].items():
            if row.get("human_attestation"):
                labels[(identity, row["item_sha256"])][session["reviewer"]] = row
    def consensus(rows):
        rows = list(rows)
        if len(rows) < 2:
            return None, "pending_independent_review"
        # Any explicit disagreement/quality concern requires adjudication.
        if any(row["decision"] != "usable" for row in rows) or len({row["answer"] for row in rows}) != 1:
            return None, "needs_adjudication"
        return rows[0]["answer"], "independent_human_consensus"
    gt = []
    for (identity, item_sha), by_reviewer in sorted(labels.items()):
        answer, state = consensus(by_reviewer.values())
        gt.append({"instance_id": identity, "item_sha256": item_sha, "answer": answer,
                   "status": state, "reviewer_count": len(by_reviewer), "formal_admitted": False})
    scores = []
    for session in sessions:
        eligible = session["baseline_eligible"]
        resolved, correct = 0, 0
        for identity, row in session["blind"].items():
            other = [label for reviewer, label in labels[(identity, row["item_sha256"])].items()
                     if reviewer != session["reviewer"]]
            answer, _ = consensus(other)
            if eligible and answer:
                resolved += 1
                correct += row["answer"] == answer
        scores.append({"reviewer": session["reviewer"], "baseline_eligible": eligible,
                       "modality": session['modality'], "media_hashes": media_hashes(session),
                       "blind_submitted": len(session["blind"]), "independently_scored": resolved,
                       "correct": correct if resolved else None, "accuracy": correct / resolved if resolved else None})
    return {"ground_truth_candidates": gt, "human_baselines": scores, "identity_basis": "self_reported_reviewer_id"}
