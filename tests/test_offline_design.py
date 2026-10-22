"""Regression coverage for evidence boundaries, controlled edits and v2 analysis."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import unittest

from evaluation.offline_choice import score_items
from tasks.offline_choice import answer_prompt, public_instance, validate_item
from tasks.offline_design import CAPABILITIES, generation_request, grouped_record, author_item
from prompts.loader import get_prompt
from web.offline_review import load_review, item_digest

BANK = Path(__file__).resolve().parents[1] / 'tasks/examples/offline_design_v2'


class OfflineDesignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = [json.loads(s) for s in (BANK / 'items.jsonl').read_text().splitlines()]

    def test_all_examples_schema_balance_and_coverage(self):
        import jsonschema
        schema=json.loads((BANK.parents[2]/'schemas/offline_choice_item_v2.schema.json').read_text())
        for x in self.items:
            validate_item(x);jsonschema.validate(x,schema)
        self.assertEqual(Counter(x['task'] for x in self.items), {'T1':8,'T2':8,'T3':8})
        self.assertEqual(Counter(x['authoring']['answer'] for x in self.items),dict.fromkeys('ABCD',6))
        for task in ['T1','T2','T3']:
            self.assertEqual({p.split('.')[0] for x in self.items if x['task']==task for p in x['target_spec']['target_state_ids']},
                             {'emotion','behavioral_disposition','relationship','consequence_risk'})

    def test_legacy_snapshots_still_validate(self):
        for bank in ['offline_t1_t3_dev60','offline_gpt50_t1_t3']:
            for line in (BANK.parent/bank/'items.jsonl').read_text().splitlines():
                validate_item(json.loads(line))

    def test_analysis_and_hidden_references_do_not_enter_model_input(self):
        for x in self.items:
            obj=deepcopy(x);obj['authoring']['secret_future']='HIDDEN_BRANCH_SENTINEL'
            prompt=answer_prompt(obj)
            for term in ['HIDDEN_BRANCH_SENTINEL','primary_capability','difficulty_reason','branch_evidence','state_check','ground_truth']:
                self.assertNotIn(term,prompt)
            self.assertEqual(grouped_record(x)['evaluated_input'],public_instance(x))
        obj=deepcopy(self.items[0]);obj['input']['history'][0]['analysis']={'answer':'A'}
        with self.assertRaises(ValueError):public_instance(obj)

    def test_hard_needs_reason_and_measured_difficulty_is_separate(self):
        x=deepcopy(next(i for i in self.items if i['analysis']['design_difficulty']=='hard'))
        x['analysis']['difficulty_reason']=''
        with self.assertRaisesRegex(ValueError,'Hard'):validate_item(x)
        x=deepcopy(self.items[0]);x['analysis']['empirical_difficulty']={'accuracy':0.9}
        with self.assertRaisesRegex(ValueError,'run provenance'):validate_item(x)

    def test_t1_cutoff_and_comparison_start(self):
        x=deepcopy(self.items[0]);x['input']['history'].append(deepcopy(x['input']['history'][-1]));x['input']['history'][-1]['turn_id']='future'
        with self.assertRaisesRegex(ValueError,'checkpoint'):validate_item(x)
        x=deepcopy(self.items[1]);x['target_spec']['comparison_interval']['start']='missing'
        with self.assertRaisesRegex(ValueError,'visible start'):validate_item(x)

    def test_t2_every_edit_must_be_recoverable_and_expression_shared(self):
        x=deepcopy(self.items[16]);x['input']['history_b'][0]['evaluated_agent']+='未记录的编辑'
        with self.assertRaisesRegex(ValueError,'edit log'):validate_item(x)
        x=deepcopy(self.items[16]);x['authoring']['history_control']['shared_expression']='two_clips'
        with self.assertRaisesRegex(ValueError,'stored only once'):validate_item(x)

    def test_t3_immediate_can_use_short_branch_but_delayed_cannot(self):
        x=deepcopy(self.items[8]);x['authoring']['branch_evidence']['observed_responses']=1
        x['target_spec'].pop('delayed_horizon');validate_item(x)
        x['target_spec'].update(horizon='delayed',delayed_horizon=5)
        with self.assertRaisesRegex(ValueError,'window too short'):validate_item(x)
        x=deepcopy(self.items[20]);x['input']['candidate_actions'][0]['label']='A'
        with self.assertRaisesRegex(ValueError,'numbered'):validate_item(x)

    def test_scoring_groups_and_pair_answers(self):
        responses=[{'instance_id':x['instance_id'],'raw_output':json.dumps({'answer':x['authoring']['answer']})} for x in self.items]
        scores=score_items(self.items,responses)
        self.assertEqual(scores['groups']['overall']['n'],24)
        self.assertEqual(sum(scores['groups']['capability/'+k]['n'] for k in CAPABILITIES),24)
        self.assertEqual(scores['groups']['difficulty/hard']['n'],15)
        pairs=[json.loads(s) for s in (BANK/'paired.items.jsonl').read_text().splitlines()]
        score_items(pairs,[])
        if pairs:
            pairs[1]['authoring']['answer']='D' if pairs[0]['authoring']['answer']!='D' else 'A'
            with self.assertRaisesRegex(ValueError,'paired inputs or labels'):score_items(pairs,[])

    def test_formal_admission_stays_closed(self):
        for x in self.items:
            with self.assertRaisesRegex(ValueError,'human ground truth'):validate_item(x,formal=True)

    def test_demo_bank_reference_is_opt_in_for_every_example(self):
        catalog=load_review(bank_id='design-v2');self.assertEqual(catalog['summary']['item_count'],24)
        for x in self.items:
            detail=load_review(x['instance_id'],bank_id='design-v2')
            self.assertNotIn('authoring',json.dumps(detail));self.assertEqual(detail['metadata']['item_sha256'],item_digest(x))
            reference=load_review(x['instance_id'],True,bank_id='design-v2')
            self.assertEqual(reference['authoring']['answer'],x['authoring']['answer'])
            self.assertIn('difficulty_reason',reference['analysis'])

    def test_template_registration_and_fixed_input(self):
        x=self.items[0]
        req=generation_request(x['task'],x['subtype'],x['input'],primary_capability=x['analysis']['primary_capability'])
        with self.assertRaisesRegex(ValueError, 'frozen construction'):
            author_item(object(), req)
        req['public_input']['history'].clear()
        self.assertTrue(x['input']['history'])
        self.assertIn('动态社会理解与适应',get_prompt('offline_choice_author_v2'))


if __name__=='__main__':unittest.main()
