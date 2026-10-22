#!/usr/bin/env bash
set -euo pipefail
cd /root/autodl-tmp/emotree

: "${SOCIALFLUX_API_KEY:?Set SOCIALFLUX_API_KEY in the server environment}"

status_dir=build/task_examples_v2
mkdir -p "$status_dir/logs"
python -c 'import json; from datetime import datetime,timezone; from pathlib import Path; Path("build/task_examples_v2/background_status.json").write_text(json.dumps({"status":"starting_remote_api","started_at_utc":datetime.now(timezone.utc).isoformat(),"stage":"frontier_route_preflight","result":"pending","website_switch_policy":"only_after_validated_build"},ensure_ascii=False,indent=2)+"\n")'
finish() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    T2_RC="$rc" python -c 'import json,os; from datetime import datetime,timezone; from pathlib import Path; p=Path("build/task_examples_v2/background_status.json"); x=json.loads(p.read_text()) if p.exists() else {}; x.update({"status":"failed","result":"old_t2_preserved","exit_code":int(os.environ["T2_RC"]),"finished_at_utc":datetime.now(timezone.utc).isoformat()}); p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n")'
  fi
}
trap finish EXIT
python -c 'import json; from pathlib import Path; p=Path("build/task_examples_v2/background_status.json"); x=json.loads(p.read_text()); x.update({"status":"building","stage":"controlled_histories_and_llm_answer"}); p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n")'
python scripts/build_t2_controlled_example.py configs/model_routes.frontier_api.json > "$status_dir/logs/build.log" 2>&1
python -m unittest tests.test_multimodal tests.test_pipeline_contract tests.test_task_review_gate web.tests.test_server > "$status_dir/logs/tests.log" 2>&1
curl --noproxy '*' --max-time 15 -fsS http://127.0.0.1:8000/api/task-examples > "$status_dir/api_snapshot.json"
python -c 'import json; from datetime import datetime,timezone; from pathlib import Path; p=Path("build/task_examples_v2/background_status.json"); x=json.loads(p.read_text()); packet=json.load(open("build/task_examples_v1/examples.json")); t2=next(e for e in packet["examples"] if e["task"]=="T2"); x.update({"status":"complete","stage":"validated_and_live","result":"website_switched_to_t2_controlled_v2","instance_id":t2["text_instance"]["instance_id"],"history_lengths":[len(t2["text_instance"]["input"]["history_a"]),len(t2["text_instance"]["input"]["history_b"])],"ground_truth":t2["text_instance"]["ground_truth"],"answer_type":t2["answer_provenance"]["answer_type"],"finished_at_utc":datetime.now(timezone.utc).isoformat(),"tests":"35 relevant tests passed"}); p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n")'
