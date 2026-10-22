"""Scene coverage, source separation and controlled material reuse."""
from collections import Counter,defaultdict
from copy import deepcopy
import json
from pathlib import Path
import unittest

from tasks.offline_choice import validate_item,public_instance,answer_prompt
from tasks.offline_design import grouped_record
from web.offline_review import load_review
from offline.scenario_v2_review import payload

ROOT=Path(__file__).resolve().parents[1]
BANK=ROOT/'tasks/examples/offline_scenarios_v2'


class ScenarioV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items=list(map(json.loads,(BANK/'items.jsonl').read_text().splitlines()))

    def test_every_scene_has_two_per_task_and_all_required_forms_exist(self):
        counts=Counter((i['story_id'],i['task']) for i in self.items)
        self.assertEqual(len(self.items),300)
        for n in range(1,51):
            for task in ('T1','T2','T3'):self.assertEqual(counts[f'GPT50_{n:03d}',task],2)
        self.assertEqual(Counter(i['authoring']['answer'] for i in self.items),dict.fromkeys('ABCD',75))
        from tasks.offline_design import SUBTYPES_V2
        for task,forms in SUBTYPES_V2.items():
            self.assertEqual({i['subtype'] for i in self.items if i['task']==task},forms)
        self.assertEqual({s.split('.')[0] for i in self.items for s in i['target_spec']['target_state_ids']},
            {'emotion','behavioral_disposition','relationship','consequence_risk'})

    def test_all_items_obey_v2_and_do_not_mint_human_truth(self):
        import jsonschema
        validator=jsonschema.Draft202012Validator(json.loads((ROOT/'schemas/offline_choice_item_v2.schema.json').read_text()))
        for x in self.items:
            validate_item(x);validator.validate(x)
            self.assertIsNone(x['ground_truth']);self.assertFalse(x['authoring']['source_admission']['formal_admitted'])
            self.assertEqual(grouped_record(x)['evaluated_input'],public_instance(x))
            self.assertNotIn('api_screening',answer_prompt(x))
            self.assertNotIn('history_control',answer_prompt(x))

    def test_all_t2_have_bound_replay_and_controlled_historical_action(self):
        from offline.oracle import bound_source, validate_t2_replay
        from offline.oracle_release import RUN, verify_amendment
        source={x['instance_id']:x for x in map(json.loads,(RUN/'source.items.jsonl').read_text().splitlines())}
        fresh=[i for i in self.items if i['task']=='T2']
        self.assertEqual(len(fresh),100)
        for x in fresh:
            inp=x['input'];control=x['authoring']['history_control']
            self.assertEqual(x['authoring']['replay_status'],'validated')
            verify_amendment(source[x['instance_id']], x)
            if source[x['instance_id']]['authoring']['replay_status']=='pending':
                self.assertEqual(len(control['edits']),1)
                self.assertEqual(control['edits'][0]['field'],'evaluated_agent')
            self.assertEqual(inp['shared_ending']['turn_id'],'ending')
            self.assertEqual(control['state_check']['status'],'controlled_replay_verified')
            construction=x['authoring']['construction_source']
            validate_t2_replay(x,bound_source(construction,'trajectory'),bound_source(construction,'replay'))
            self.assertTrue(x['authoring']['oracle_reference']['independent_check'])
            self.assertTrue(x['authoring']['api_screening'])

    def test_t3_uses_real_common_branches_and_both_question_forms(self):
        for x in self.items:
            if x['task']!='T3':continue
            evidence=x['authoring']['branch_evidence']
            self.assertEqual(evidence['status'],'validated');self.assertEqual(evidence['observed_responses'],5)
            self.assertEqual([a['label'] for a in x['input']['candidate_actions']],['行动 1','行动 2'])
            self.assertTrue(evidence['external_conditions_sha256'])
            self.assertEqual(evidence['external_plan_mode'],'none')
            self.assertIsNone(evidence['external_event_plan_hash'])
            if x['subtype']=='action_selection':self.assertTrue(x['target_spec']['goal'])

    def test_blind_review_payload_omits_all_author_information(self):
        scene=[deepcopy(i) for i in self.items if i['story_id']=='GPT50_001']
        for x in scene:x['authoring']['secret']='PRIVATE_TEST_SENTINEL'
        out=json.dumps(payload(scene))
        for token in ('PRIVATE_TEST_SENTINEL','ground_truth','api_screening','construction_source','"answer"'):
            self.assertNotIn(token,out)

    def test_combination_diagnostics_preserve_partly_correct_judgments(self):
        from evaluation.offline_choice import score_items
        # Freeze diagnostic semantics locally: one correct coordinate and one
        # wrong coordinate must not become a whole-item success.
        x=deepcopy(next(i for i in self.items if i['subtype']=='state_combination'))
        first,second=x['target_spec']['target_state_ids']
        x['authoring'].update(answer='B',option_errors={k:'state_dimension_confusion' for k in 'ACD'},
            option_variable_map={
                'A':{first:'up',second:'down'},'B':{first:'up',second:'up'},
                'C':{first:'down',second:'up'},'D':{first:'down',second:'down'}})
        x['authoring'].pop('acceptable_answers',None)
        result=score_items([x],[{'instance_id':x['instance_id'],'raw_output':'{"answer":"A"}'}])
        self.assertFalse(result['rows'][0]['correct'])
        diagnostics=result['combination_diagnostics']
        self.assertEqual(diagnostics[first]['accuracy'],1)
        self.assertEqual(diagnostics[second]['accuracy'],0)

    def test_web_all_scenes_and_media_pair_answers(self):
        catalog=load_review(bank_id='scenarios-v2');self.assertEqual(catalog['summary']['item_count'],300)
        self.assertEqual(len(catalog['summary']['scene_coverage']),50)
        pairs=list(map(json.loads,(BANK/'paired.items.jsonl').read_text().splitlines()))
        self.assertTrue(pairs)
        for t,v in zip(pairs[::2],pairs[1::2]):
            self.assertEqual(t['input'],v['input']);self.assertEqual(t['options'],v['options']);self.assertEqual(t['authoring']['answer'],v['authoring']['answer'])
        data=load_review(self.items[0]['instance_id'],bank_id='scenarios-v2')
        self.assertNotIn('api_screening',json.dumps(data));self.assertTrue(data['media'])


if __name__=='__main__':unittest.main()
