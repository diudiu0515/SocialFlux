"""Experiment notebook: live evidence, indexed reports, durable planning records.

The notebook never executes experiments or changes source Gate/GT artifacts.
SQLite transactions and revision checks protect concurrent edits across browsers.
"""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

from web.experiment_status import load_experiment_status
from web.experiment_catalog import load_matrix, planned_records
from web.experiment_tables import build_paper_tables
from web.human_gt import load_human_gt

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data/experiment_hub"
STATUSES = ("planned", "running", "blocked", "review", "completed", "archived")
CATEGORIES = ("Gate 1", "Gate 2", "Gate 3", "Gate 4", "T1–T3", "T4", "环境消融", "多模态", "其他")
FIELDS = ("title", "category", "status", "priority", "owner", "due_date",
          "hypothesis", "method", "acceptance", "notes", "sources", "metrics")

# Report-derived proposals, not claims that these jobs are running or approved.
SEEDS = (
    ("t2-replay", "补齐新版 T2 受控历史的状态回放", "T1–T3", "P0",
     "核验受控历史编辑经过环境回放后，是否支持题目中的状态差异。",
     "绑定原始 checkpoint、配置与内容哈希，按正式环境路径分别回放 A/B。",
     "逐场景保存回放记录与失败原因；共享 ending 和来源核对通过后进入人工审核。",
     "reports/experiments/2026-10-20_scenarios_v2.md"),
    ("human-gt", "完成新版题库独立人工标注与 GT 审核", "Gate 4", "P0",
     "确认题目可回答性、证据支持和参考答案；区分机器候选与人工标签。",
     "先独立盲答，再核验私有证据；按 Gate 4 固定样本开展双人独立复核及分歧仲裁。",
     "保存绑定题目版本的人工记录、分歧处置和来源准入证据。",
     "DESIGN_CONTRACT.md"),
    ("gate1-freeze", "补齐场景与初始状态的人工冻结证据", "Gate 1", "P0",
     "确认来源、社会合理性和初始状态符合当前批次合同。",
     "逐场景核对原文、初始 state、runtime seed 与来源哈希。",
     "人工签署与最终来源版本一致；机器检查单独记录。",
     "DESIGN_CONTRACT.md"),
    ("gate2-human", "完成 E1–E9 环境有效性的人工核验", "Gate 2", "P0",
     "检查机器干预结果是否支持环境有效性结论。",
     "按每项实验的当前证据包核对样本、分母、失败和规定的人工判断。",
     "逐项保留证据与人工结论；缺失项保持 pending。",
     "DESIGN_CONTRACT.md"),
    ("gate3-review", "复核轨迹质量与独立审核分歧", "Gate 3", "P0",
     "确认唯一自然轨迹的六维质量及 hard reject 判断。",
     "核对主审核、独立审计、history evidence 和不可用来源。",
     "完成对应批次的必要人工要求；失败留在原始分母中。",
     "DESIGN_CONTRACT.md"),
    ("t4-calibration", "校准 T4「对话承诺」与「外部完成」评分", "T4", "P1",
     "核验不同裁判对目标完成的判准是否一致。",
     "复核报告中 GPT50_002 的评分依据，建立固定样本和明确评分锚点。",
     "保留原分数，单列人工校准和判准差异，不覆盖既有结果。",
     "reports/experiments/2026-10-20_t4_checkpoint_findings.md"),
    ("media-quality", "复核视频动作自然度、情绪适配与音频", "多模态", "P1",
     "确认媒体具有目标线索且没有额外事实或信息泄漏。",
     "先复核 GPT50_024 及当前素材，再按来源一致的样本计划检查视听质量。",
     "记录人工质量判断；区分视频帧接收、原生视频和音频验证。",
     "reports/experiments/2026-10-20_t4_checkpoint_findings.md"),
    ("t4-semantics", "复核固定节点中的角色脱离与无依据事实", "T4", "P1",
     "确认格式校验通过的回应是否仍存在语义无效问题。",
     "检查 Claude 与 DeepSeek 在 GPT50_024 的原始回应和公开输入。",
     "逐项记录人工判断与证据；保留原始调用，不把异常重试成成功。",
     "reports/experiments/2026-10-20_t4_checkpoint_findings.md"),
    ("legacy-audit", "确认旧题迁移中未完成的适配复核", "T1–T3", "P2",
     "核对历史 460 题尚未完成的 API 复核与来源问题。",
     "以最新迁移结果及逐题 SHA 为准，先判断是否仍需迁移，再安排补查。",
     "已核验、失败、超时及不迁移项分别留痕。",
     "reports/experiments/2026-10-20_legacy_task_migration.md"),
)


class ConflictError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    STORE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STORE / "notebook.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
    db.execute("""CREATE TABLE IF NOT EXISTS events
                  (sequence INTEGER PRIMARY KEY, record_id TEXT NOT NULL,
                   at TEXT NOT NULL, body TEXT NOT NULL)""")
    db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    with db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM meta WHERE key='seed_v1'").fetchone():
            for key, title, category, priority, hypothesis, method, acceptance, source in SEEDS:
                record = dict(id="plan-" + key, title=title, category=category,
                              priority=priority, status="planned", owner="", due_date="",
                              hypothesis=hypothesis, method=method, acceptance=acceptance,
                              notes="根据项目文档整理的初始待办，执行前请核对最新证据。",
                              sources=[source], metrics=[], origin="report_proposal",
                              created_at=now(), updated_at=now(), revision=1)
                db.execute("INSERT OR IGNORE INTO records VALUES (?, ?)",
                           (record["id"], json.dumps(record, ensure_ascii=False)))
            db.execute("INSERT OR IGNORE INTO meta VALUES ('seed_v1', '1')")
        # Add the requested matrix to existing notebooks too, without replacing edits.
        if not db.execute("SELECT 1 FROM meta WHERE key='research_matrix_20261021'").fetchone():
            for record in planned_records(now()):
                inserted = db.execute("INSERT OR IGNORE INTO records VALUES (?, ?)",
                                      (record["id"], json.dumps(record, ensure_ascii=False)))
                if inserted.rowcount:
                    event = dict(at=record["created_at"], action="created", before=None, after=record)
                    db.execute("INSERT INTO events (record_id, at, body) VALUES (?, ?, ?)",
                               (record["id"], record["created_at"], json.dumps(event, ensure_ascii=False)))
            db.execute("INSERT OR IGNORE INTO meta VALUES ('research_matrix_20261021', '1')")
        if not db.execute("SELECT 1 FROM meta WHERE key='gate_protocols_v2'").fetchone():
            for proposed in planned_records(now()):
                stored = db.execute("SELECT body FROM records WHERE id=?", (proposed["id"],)).fetchone()
                event = db.execute("SELECT body FROM events WHERE record_id=? ORDER BY sequence LIMIT 1",
                                   (proposed["id"],)).fetchone()
                if not stored or not event:
                    continue
                before = json.loads(stored["body"])
                baseline = json.loads(event["body"]).get("after", {})
                if before.get("origin") != "research_matrix_20261021":
                    continue
                updated = dict(before)
                for field in ("title", "category", "hypothesis", "method", "acceptance", "notes", "sources"):
                    if before.get(field) == baseline.get(field):
                        updated[field] = proposed[field]
                if updated != before:
                    updated.update(revision=before["revision"] + 1, updated_at=now())
                    db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(updated, ensure_ascii=False), updated["id"]))
                    event = dict(at=updated["updated_at"], action="updated", before=before, after=updated,
                                 reason="补齐 Gate 方法与归属；只更新未被手动修改的字段")
                    db.execute("INSERT INTO events (record_id, at, body) VALUES (?, ?, ?)",
                               (updated["id"], updated["updated_at"], json.dumps(event, ensure_ascii=False)))
            db.execute("INSERT INTO meta VALUES ('gate_protocols_v2', '1')")
        if not db.execute("SELECT 1 FROM meta WHERE key='gate_scope_v3'").fetchone():
            automatic_reason = "补齐 Gate 方法与归属；只更新未被手动修改的字段"
            for proposed in planned_records(now()):
                stored = db.execute("SELECT body FROM records WHERE id=?", (proposed['id'],)).fetchone()
                if not stored:
                    continue
                before = json.loads(stored['body'])
                if before.get('origin') != 'research_matrix_20261021':
                    continue
                events = [json.loads(r['body']) for r in db.execute(
                    'SELECT body FROM events WHERE record_id=? ORDER BY sequence', (proposed['id'],))]
                updated = dict(before)
                for field in ('title','category','hypothesis','method','acceptance','notes','sources'):
                    changes = [e for e in events if (e.get('before') or {}).get(field) != (e.get('after') or {}).get(field)]
                    if not changes:
                        continue
                    latest = changes[-1]
                    automatic = latest.get('before') is None or latest.get('reason') == automatic_reason
                    if automatic and before.get(field) == latest['after'].get(field):
                        updated[field] = proposed[field]
                if updated != before:
                    updated.update(revision=before['revision']+1, updated_at=now())
                    db.execute('UPDATE records SET body=? WHERE id=?', (json.dumps(updated,ensure_ascii=False),updated['id']))
                    event = dict(at=updated['updated_at'], action='updated', before=before, after=updated,
                                 reason='校正 E7/S0 及实际测试覆盖范围；保留手动编辑字段')
                    db.execute('INSERT INTO events (record_id,at,body) VALUES (?,?,?)',
                               (updated['id'],updated['updated_at'],json.dumps(event,ensure_ascii=False)))
            db.execute("INSERT INTO meta VALUES ('gate_scope_v3','1')")
    return db


def records():
    db = connect()
    try:
        return sorted((json.loads(row["body"]) for row in db.execute("SELECT body FROM records")),
                      key=lambda x: (x["priority"], x["created_at"], x["id"]))
    finally:
        db.close()


def history(identity):
    db = connect()
    try:
        return [json.loads(row["body"]) for row in db.execute(
            "SELECT body FROM events WHERE record_id=? ORDER BY sequence DESC LIMIT 100",
            (identity,))]
    finally:
        db.close()


def validate(payload):
    result = {}
    for field in FIELDS:
        if field in ("sources", "metrics"):
            continue
        value = payload.get(field, "")
        limit = 160 if field == "title" else 100 if field == "owner" else 12000
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"{field} 格式无效或内容过长")
        result[field] = value.strip()
    if not result["title"]:
        raise ValueError("请填写实验名称")
    if result["status"] not in STATUSES or result["category"] not in CATEGORIES:
        raise ValueError("实验状态或分类无效")
    if result["priority"] not in ("P0", "P1", "P2"):
        raise ValueError("优先级无效")
    if result["due_date"]:
        try:
            date.fromisoformat(result["due_date"])
        except ValueError:
            raise ValueError("计划日期格式应为 YYYY-MM-DD") from None
    sources = payload.get("sources", [])
    if not isinstance(sources, list) or len(sources) > 40:
        raise ValueError("来源列表无效")
    if any(not isinstance(s, str) or len(s) > 500 for s in sources):
        raise ValueError("来源路径过长或无效")
    result["sources"] = list(dict.fromkeys(s.strip() for s in sources if s.strip()))
    metrics = payload.get("metrics", [])
    if not isinstance(metrics, list) or len(metrics) > 100:
        raise ValueError("指标列表无效")
    result["metrics"] = []
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ValueError("每个指标必须包含 name、value，可选 unit、n")
        clean = {}
        for field in ("name", "value", "unit", "n"):
            value = metric.get(field, "")
            if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 200:
                raise ValueError("指标字段无效")
            clean[field] = str(value).strip()
        if not clean["name"]:
            raise ValueError("指标名称不能为空")
        result["metrics"].append(clean)
    return result


def save_record(payload):
    clean = validate(payload)
    identity = payload.get("id")
    if identity is not None and (not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,80}", identity)):
        raise ValueError("实验 ID 无效")
    db = connect()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            before = None
            if identity:
                row = db.execute("SELECT body FROM records WHERE id=?", (identity,)).fetchone()
                if not row:
                    raise ValueError("实验不存在")
                before = json.loads(row["body"])
                if type(payload.get("revision")) is not int or payload["revision"] != before["revision"]:
                    raise ConflictError("此实验已被其他页面更新。请保留输入，刷新记录后再保存。")
            stamp = now()
            clean.update(id=identity or "exp-" + uuid.uuid4().hex[:16],
                         revision=(before["revision"] + 1) if before else 1,
                         created_at=before["created_at"] if before else stamp,
                         updated_at=stamp, origin=before["origin"] if before else "manual")
            event = {"at": stamp, "action": "updated" if before else "created",
                     "before": before, "after": clean}
            db.execute("INSERT OR REPLACE INTO records VALUES (?, ?)",
                       (clean["id"], json.dumps(clean, ensure_ascii=False)))
            db.execute("INSERT INTO events (record_id, at, body) VALUES (?, ?, ?)",
                       (clean["id"], stamp, json.dumps(event, ensure_ascii=False)))
        return clean
    finally:
        db.close()


def category_for(path):
    name = path.name.lower()
    for needle, label in (("t4", "T4"), ("gate2", "Gate 2"), ("gate3", "Gate 3"),
                          ("offline", "T1–T3"), ("scenarios_v2", "T1–T3"),
                          ("legacy_task", "T1–T3"), ("multimodal", "多模态"),
                          ("video", "多模态"), ("state", "Gate 2")):
        if needle in name:
            return label
    return "其他"


def source_path(relative):
    """Expose only indexed reports and explicitly listed public project documents."""
    if not isinstance(relative, str) or len(relative) > 500:
        return None
    path = ROOT / relative
    # Reject symlinks at every level (including in the report tree).
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != ROOT.parent):
        return None
    target = path.resolve()
    report_root = (ROOT / "reports/experiments").resolve()
    allowed = target.is_relative_to(report_root) or relative in {
        "DESIGN_CONTRACT.md", "PROJECT_PROGRESS.md", "self_check.md",
        "docs/protocols/OFFLINE_T1_T3_CHOICE_V2.md",
    }
    if not allowed or not target.is_file() or target.suffix.lower() not in {
        ".md", ".txt", ".json", ".jsonl", ".csv", ".tex"
    }:
        return None
    return target


def source_document(relative):
    path = source_path(relative)
    if path is None:
        return None
    if path.stat().st_size > 8_000_000:
        return {"path": relative, "error": "文件超过 8 MB，请从原始实验目录查看"}
    raw = path.read_bytes()
    return {"path": relative, "content": raw.decode("utf-8", errors="replace"),
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def report_catalog():
    result, errors = [], []
    for path in sorted((ROOT / "reports/experiments").rglob("*"), reverse=True):
        relative = str(path.relative_to(ROOT))
        if source_path(relative) is None:
            continue
        try:
            stat = path.stat()
            title, excerpt = path.stem, ""
            if path.suffix in (".md", ".txt"):
                with path.open(encoding="utf-8", errors="replace") as stream:
                    head = stream.read(6000)
                lines = [s.strip() for s in head.splitlines() if s.strip()]
                title = next((s.lstrip("# ").strip() for s in lines if s.startswith("# ")),
                             lines[0][:160] if lines else path.stem)
                excerpt = " ".join(s for s in lines[1:] if not s.startswith(("#", "|", "```")))[:200]
            match = re.search(r"\d{4}-\d{2}-\d{2}", path.name)
            result.append({"id": hashlib.sha256(relative.encode()).hexdigest()[:20],
                           "path": relative, "title": title, "excerpt": excerpt,
                           "date": match.group() if match else "",
                           "category": category_for(path), "format": path.suffix[1:].upper(),
                           "archived": "archive" in path.parts, "bytes": stat.st_size,
                           "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()})
        except OSError:
            errors.append(relative)
    return result, errors


def load_hub():
    reports, errors = report_catalog()
    live_error = None
    try:
        live = load_experiment_status()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        live = None
        live_error = f"当前实验文件暂不可读（{type(exc).__name__}），请稍后刷新。"
    notebook = records()
    matrix = load_matrix(ROOT, live, notebook)
    human = load_human_gt()
    return {"schema": "socialflux_experiment_hub_v2", "generated_at": now(),
            "records": notebook, "reports": reports, "live": live,
            "matrix": matrix, "human_annotation": human,
            "paper_tables": build_paper_tables(live, matrix) + human['tables'],
            "live_error": live_error, "catalog_errors": errors,
            "scope": "收录 reports/experiments 下全部文本、JSON、JSONL、CSV；实时摘要覆盖已登记批次。原始轨迹、视频和调用日志保留在原目录。",
            "storage": "data/experiment_hub/notebook.sqlite3",
            "categories": CATEGORIES, "statuses": STATUSES}
