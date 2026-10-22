"""Audited transfer of untouched T4 episodes to a separate frozen worker run."""

import json
import os
from pathlib import Path
from uuid import uuid4

from evaluation.t4_batch import save


def delegate_unstarted_scenarios(source_run, target_run, scenario_ids, model_ids):
    """Use explicit non-success records so the existing runner skips transferred jobs.

    Call only for later blocks separated from the live block by an untouched
    buffer block. The old runner already checks result.json before each job.
    No completed/failed/partial episode is eligible for transfer.
    """
    source_run, target_run = Path(source_run).resolve(), Path(target_run).resolve()
    plan = json.loads((source_run / "plan.json").read_text())
    if not set(scenario_ids) <= set(plan["config"]["scenario_ids"]):
        raise ValueError("delegation includes scenarios outside the source plan")
    if set(model_ids) != set(plan["providers"]):
        raise ValueError("delegation must retain every source model")
    if source_run == target_run or not scenario_ids:
        raise ValueError("delegation needs a distinct target and nonempty scope")
    for sid in scenario_ids:
        if (source_run / "episodes" / sid).exists() or (target_run / "episodes" / sid).exists():
            raise ValueError("scenario already has episode artifacts: " + sid)
    records = []
    for sid in scenario_ids:
        for model in model_ids:
            for condition in ("text_only", "text_video"):
                relative = Path("episodes") / sid / model / condition / "result.json"
                path = source_run / relative
                row = {"scenario_id": sid, "model_id": model, "condition": condition,
                       "modality": {"policy_condition": condition},
                       "status": "delegated_to_run", "is_measurement": False,
                       "destination_result": str(target_run / relative),
                       "reason": "User requested parallel acceleration; source has made no calls for this episode."}
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(".delegation-" + uuid4().hex)
                temporary.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n")
                try:
                    os.link(temporary, path)  # Atomic create; never overwrite a result.
                finally:
                    temporary.unlink()
                records.append(str(relative))
    record = {"source_run": str(source_run), "target_run": str(target_run),
              "scenario_ids": scenario_ids, "model_ids": model_ids,
              "episode_count": len(records), "records": records,
              "status_semantics": "delegated_to_run is a scheduling record, never a score or successful episode"}
    save(source_run / "delegation.json", record)
    save(target_run / "delegation_source.json", record)
    return record
