import csv
import io
import unittest

from web.experiment_tables import build_paper_tables, make_table


class ExperimentTablesTests(unittest.TestCase):
    def test_diagnostic_counts_and_prefixes_do_not_become_completed_pairs(self):
        live = {'s0_ablation': {'run_id':'run','status':'stopped_diagnostics',
            'diagnostics': {'execution_counts': {'dynamic_state': {'completed':0,'failed':9,
                'interrupted':2,'not_started':19,'saved_turns':18}},
                'bounds_preflight':{'passed':30,'total':30,'changed_scenarios':12},
                'provider_probe':{'returned_text':3,'diagnostic_only':True}},
            'pairs':{'dynamic_repeat':{'n':0,'metrics':{}}}}}
        tables = {t['id']:t for t in build_paper_tables(live, {'experiments':[]})}
        self.assertEqual(tables['s0-execution-coverage']['rows'][0][1:], [30,0,9,2,19,18])
        self.assertEqual(tables['supplementary-results']['rows'][-1][4], 0)
        self.assertIn('诊断输出不计入', tables['s0-execution-coverage']['exports']['markdown'])

    def test_s0_saved_turns_are_not_reported_as_completed_pairs(self):
        from web.experiment_catalog import definitions
        live = {'s0_ablation': {'run_id':'gate2_s0_mechanism_20261021', 'status':'waiting_provider_authorization',
            'conditions':{'replaced_s0':{'saved_turns':12,'completed':0,'failed':1}},
            'pairs':{'replaced_s0':{'n':0,'metrics':{'state_delta_mae':None}}}}}
        tables = build_paper_tables(live, {'experiments':[dict(r, evidence={}) for r in definitions()]})
        table = next(t for t in tables if t['id']=='supplementary-results')
        row = next(r for r in table['rows'] if '初始状态敏感性' in r[0])
        self.assertEqual(row[4], 0)
        self.assertIn('已存 12 轮', row[5])
        self.assertIn('MAE=N/A', row[5])
        self.assertIn('待外发授权', row[5])

    def test_gate_metrics_keep_distinct_denominators_and_human_pending(self):
        live = dict(gates=[dict(id="Gate 2", raw_intervention_records=46, experiments=[
            dict(id="E1", evidence_present=True, status="pending", human_attestation=False, review_items=40,
                 report_metrics=dict(agreement=None), machine_record={}),
            dict(id="E4", evidence_present=True, status="pending", human_attestation=False,
                 raw_partial=dict(records=31, screen_passed=10),
                 machine_record=dict(active_union_direction_agreement=.4884),
                 report_metrics=dict(active_union_dimension_count=172)),
            dict(id="E6", evidence_present=True, status="fail", machine_record=dict(matched_checkpoint_count=46,
                 successful_matched_checkpoint_count=43, mean_active_union_direction_agreement=.4987,
                 replay_failure_count=3, mean_true_sign_reversal_rate=.0353), report_metrics=dict(record_pass_fraction=.6512)),
        ])])
        tables = {t["id"]: t for t in build_paper_tables(live, dict(experiments=[]))}
        rows = {r[0].split()[0]: r for r in tables["gate2-results"]["rows"]}
        self.assertEqual(rows["E1"][2:4], [40, "N/A"])
        self.assertEqual(rows["E1"][5], "人工方向一致率 N/A")
        self.assertEqual(rows["E4"][2:5], [46, 31, "10/31 (32.26%)"])
        self.assertIn("48.84%", rows["E4"][5])
        self.assertIn("15", rows["E4"][6])
        self.assertEqual(rows["E6"][3], 43)
        self.assertIn("49.87%", rows["E6"][5])
        self.assertIn("失败 3", rows["E6"][6])
        self.assertEqual(rows["E6"][-2:], ["协议不要求人工签署", "未通过"])

    def test_t4_runs_na_negative_deltas_and_intervals_are_preserved(self):
        model = dict(conditions=dict(text_only=dict(metrics=dict(goal_achievement=dict(n=4, mean=8, sd=1)))),
                     matched_scenarios=2, paired_differences=dict(goal_achievement=dict(n=2, mean=-.5, bootstrap_ci95=[-1, 0])),
                     status_counts=dict(completed=4, failed=2, delegated_to_run=3))
        live = dict(t4_runs=[dict(id="run-a", title="A", models=dict(gpt=model)), dict(id="run-b", title="B", models=dict(gpt=model))])
        tables = {t["id"]: t for t in build_paper_tables(live, dict(experiments=[]))}
        self.assertIn("run-a-scores", tables)
        self.assertIn("run-b-scores", tables)
        self.assertEqual(tables["run-a-scores"]["rows"][0][2], "8.00 (n=4); SD=1.00")
        self.assertEqual(tables["run-a-paired"]["rows"][0][2], "-0.50 (n=2); 95% CI [-1.00, 0.00]")
        self.assertEqual(tables["run-a-scores"]["rows"][0][5], "N/A (n=0)")
        self.assertEqual(tables["run-a-coverage"]["rows"][0][1:3], [4, 2])
        self.assertEqual(tables["run-a-coverage"]["rows"][0][5], 3)

    def test_exports_escape_special_characters_and_keep_notes(self):
        table = make_table("demo", "例子 & 对照", ["名称", "结果"], [["a_b | test", "50%"], ["=1+1", "x\ny"]], ["未经人工校准"], ["data/summary.json"])
        self.assertIn(r"a\_b", table["exports"]["latex"])
        self.assertIn(r"50\%", table["exports"]["latex"])
        self.assertIn(r"\begin{longtable}", table["exports"]["latex"])
        self.assertIn("未经人工校准", table["exports"]["latex"])
        self.assertIn(r"\|", table["exports"]["markdown"])
        rows = list(csv.reader(io.StringIO(table["exports"]["csv"].lstrip("\ufeff"))))
        self.assertEqual(rows[-1], ["'=1+1", "x\ny"])


if __name__ == "__main__":
    unittest.main()
