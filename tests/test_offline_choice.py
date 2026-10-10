import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tasks.offline_choice import VERSION, answer_prompt, parse_answer, public_instance, validate_item
from evaluation.offline_choice import score_items
from rollout.counterfactual import branch_counterfactuals


def item():
    return {'instance_id':'q1', 'benchmark_version':VERSION, 'task':'T1', 'subtype':'interval_change',
            'story_id':'s1', 'pair_id':None, 'modality':'text',
            'input':{'context':{'background':'同事交接。'},'role':{'character_id':'agent','name':'乙'},
                     'target_character':{'character_id':'owner','name':'甲'},
                     'history':[{'turn_id':'t1','evaluated_agent':'已核对','environment_character':'好'}]},
            'question':'甲对乙的信任在t0到t1如何变化？',
            'options':{'A':'上升','B':'基本不变','C':'下降'},
            'target_spec':{'target_state_ids':['relationship.trust'],'state_owner':'owner','state_target':'agent','time_scope':'t0到t1'},
            'ground_truth':None, 'metadata':{'source_trajectory_id':'private-trajectory'},
            'authoring':{'answer':'A','evidence_ids':['t1'],'rationale':'已核验履约',
                         'option_errors':{'B':'history_ignored','C':'unsupported_inference'},
                         'option_variable_map':{'A':{'relationship.trust':'increase'},'B':{'relationship.trust':'similar'},'C':{'relationship.trust':'decrease'}},
                         'review_status':'pending_human_review'}}


class OfflineChoiceTest(unittest.TestCase):
    def test_protocol_accepts_only_unique_unambiguous_choice(self):
        options=item()['options']
        for raw in ['B',' b ','{"answer":"B"}']:
            self.assertEqual(parse_answer(raw,options)['answer'],'B')
        for raw in ['B or C','答案是 B','{"answer":"B","answer":"C"}','["B"]','{"answer":"Z"}',
                    '{"answer":["B"]}','```json\n{"answer":"B"}\n```','{"answer":"B","rationale":"x"}']:
            self.assertIsNotNone(parse_answer(raw,options)['format_error'],raw)

    def test_answer_and_evidence_are_scored_independently(self):
        x=item()
        good_answer=score_items([x],[{'instance_id':'q1','raw_output':'{"answer":"A","evidence_ids":["invisible"]}'}],diagnostic=True)
        row=good_answer['rows'][0]
        self.assertTrue(row['correct']);self.assertEqual(row['evidence']['f1'],0)
        wrong=score_items([x],[{'instance_id':'q1','raw_output':'{"answer":"B","evidence_ids":["t1"]}'}],diagnostic=True)
        self.assertFalse(wrong['rows'][0]['correct']);self.assertEqual(wrong['rows'][0]['evidence']['f1'],1)
        missing=score_items([x],[{'instance_id':'q1','raw_output':'A'}],diagnostic=True)
        self.assertTrue(missing['rows'][0]['correct']);self.assertTrue(missing['rows'][0]['evidence_format_error'])
        absent=score_items([x],[{'instance_id':'q1','raw_output':'{"evidence_ids":["t1"]}'}],diagnostic=True)
        self.assertFalse(absent['rows'][0]['correct']);self.assertEqual(absent['rows'][0]['evidence']['f1'],1)
        extra=score_items([x],[{'instance_id':'q1','raw_output':'{"answer":"A","reason":"extra"}'}])
        self.assertTrue(extra['rows'][0]['correct']);self.assertEqual(extra['rows'][0]['format_error'],'unexpected_fields')

    def test_failure_denominator_and_types(self):
        xs=[item() for _ in range(4)]
        for i,x in enumerate(xs):x['instance_id']=str(i)
        report=score_items(xs,[{'instance_id':'0','raw_output':'A'}, {'instance_id':'1','raw_output':'C'},
                              {'instance_id':'2','raw_output':'A or B'}, {'instance_id':'3','call_error':'timeout'}])
        self.assertEqual(report['groups']['overall'],{'n':4,'correct':1,'accuracy':.25,'semantic_errors':1,'format_failures':1,'call_failures':1})
        self.assertEqual(report['wrong_option_types'],{'unsupported_inference':1})

    def test_no_author_metadata_or_future_in_prompt(self):
        x=item();x['authoring']['secret_future']='future sentinel'
        prompt=answer_prompt(x)
        for secret in ['private-trajectory','future sentinel','option_variable_map','target_state_ids','pending_human_review']:
            self.assertNotIn(secret,prompt)
        x['input']['history'][0]['state_after']={'relationship':{'trust':8}}
        with self.assertRaises(ValueError):answer_prompt(x)
        x=item();x['input']['role']['persona']={'hidden':'x'}
        with self.assertRaises(ValueError):answer_prompt(x)

    def test_combination_results_never_inflate_whole_item(self):
        x=item();x['subtype']='joint_change';x['options']['D']='均下降';x['authoring']['option_errors']['D']='unsupported_inference';x['authoring']['option_variable_map']['D']={'relationship.trust':'decrease','emotion.anger':'decrease'};x['target_spec']['target_state_ids'].append('emotion.anger')
        for k,judgment in [('A','decrease'),('B','decrease'),('C','increase')]:
            x['authoring']['option_variable_map'][k]['emotion.anger']=judgment
        report=score_items([x],[{'instance_id':'q1','raw_output':'B'}])
        self.assertEqual(report['groups']['overall']['accuracy'],0)
        self.assertEqual(report['combination_diagnostics']['emotion.anger']['accuracy'],1)
        self.assertEqual(report['combination_diagnostics']['relationship.trust']['accuracy'],0)
        self.assertEqual(report['groups']['task_state/T1/Emotion']['n'],1)

    def test_formal_admission_and_unknown_responses_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'human ground truth'):validate_item(item(),formal=True)
        x=item();x['ground_truth']={'acceptable_answers':['A']}
        with self.assertRaisesRegex(ValueError,'unreviewed'):validate_item(x)
        with self.assertRaisesRegex(ValueError,'unknown response'):
            score_items([item()],[{'instance_id':'q2','raw_output':'A'}])

    def test_accepted_neighbor_and_formal_scoring(self):
        x=item();x['authoring']['acceptable_answers']=['A','B']
        del x['authoring']['option_errors']['B']
        x['ground_truth']={'acceptable_answers':['A','B']}
        x['authoring'].update(review_status='human_approved',source_admission={'formal_admitted':True})
        result=score_items([x],[{'instance_id':'q1','raw_output':'B'}],formal=True)
        self.assertEqual(result['label_basis'],'human_ground_truth')
        self.assertTrue(result['rows'][0]['correct'])
        self.assertEqual(result['wrong_option_types'],{})

    def test_legacy_path_never_silently_drops_video(self):
        from tasks.offline_choice import generate_answer
        x=item();x['modality']='text+video'
        with self.assertRaisesRegex(ValueError,'explicit media manifest'):
            generate_answer(None,x,1)

    def test_legacy_answer_module_dispatch(self):
        from tasks.T1.answering import generate_answer
        class Provider:
            def complete(self,messages,**kwargs):
                self.messages=messages;return '{"answer":"A"}'
        provider=Provider();answer,calls=generate_answer(provider,item(),1,private_persona={'secret':'x'})
        self.assertEqual(answer['answer'],'A');self.assertEqual(calls,1)
        self.assertNotIn('secret',json.dumps(provider.messages))

    def test_t3_window_and_same_snapshot(self):
        class Environment:
            def restore(self,snapshot,episode_id):
                self.session=deepcopy(snapshot);self.session.update(turns=[],status='active')
            def step(self,action):
                self.session['state']['x']+=1
                log={'state_after':deepcopy(self.session['state']),'dynamics_after':{},'response':'observed'}
                self.session['turns'].append(log);return {},log
            def observe(self):return {}
        class Policy:
            def generate(self,observation):return {'text':'continue'}
        checkpoint={'turn_id':'t3','environment_snapshot_before':{'state':{'x':0},'dynamics':{},'event_plan':{'plan_hash':'frozen'}}}
        rows=branch_counterfactuals(Environment,checkpoint,[{'text':'one'},{'text':'two'}],Policy,5)
        self.assertEqual(rows[0]['snapshot_sha256'],rows[1]['snapshot_sha256'])
        self.assertTrue(all(r['actual_turns_observed']==5 and r['window_complete'] for r in rows))
        self.assertTrue(all(r['state_after_immediate']['x']==1 and r['state_after_delayed']['x']==5 for r in rows))

    def test_parallel_branch_resume_replays_only_real_snapshot(self):
        class Environment:
            calls=0
            def restore(self,snapshot,episode_id):
                self.session=deepcopy(snapshot);self.session.update(turns=[],status='active')
            def step(self,action):
                Environment.calls+=1
                before={k:deepcopy(v) for k,v in self.session.items() if k not in {'turns','status'}}
                old=deepcopy(self.session['state']);self.session['state']['x']+=1
                log={'state_before':old,'state_after':deepcopy(self.session['state']),
                     'dynamics_before':{},'dynamics_after':{},'policy_action':deepcopy(action),
                     'environment_snapshot_before':before}
                self.session['turns'].append(log);return {},log
            def observe(self):return {}
        class Policy:
            def generate(self,observation):return {'text':'continue'}
        checkpoint={'turn_id':'t3','environment_snapshot_before':{'state':{'x':0},'dynamics':{},'event_plan':{'plan_hash':'frozen'}}}
        actions=[{'text':'one'},{'text':'two'}]
        original=branch_counterfactuals(Environment,checkpoint,actions,Policy)
        Environment.calls=0
        resumed=branch_counterfactuals(Environment,checkpoint,actions,Policy,branch_workers=2,
                                      resume_logs={0:original[0]['future_turns'][:3]})
        self.assertEqual(Environment.calls,8)
        self.assertEqual(resumed[0]['resumed_prefix_turns'],2)
        self.assertTrue(all(r['state_before']=={'x':0} and r['state_after_delayed']=={'x':5} for r in resumed))
        self.assertTrue(all(len(r['future_turns'])==5 and r['window_complete'] for r in resumed))
        invalid=deepcopy(original[0]['future_turns'][:3]);invalid[0]['policy_action']={'text':'different'}
        with self.assertRaisesRegex(ValueError,'snapshot/action'):
            branch_counterfactuals(Environment,checkpoint,actions,Policy,resume_logs={0:invalid})
        Environment.calls=0;completed=[]
        selected=branch_counterfactuals(Environment,checkpoint,actions,Policy,
            branch_indices=[1],branch_workers=2,branch_callback=lambda i,row:completed.append(i))
        self.assertEqual(Environment.calls,5)
        self.assertEqual(completed,[1])
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]['candidate_action'],actions[1])
        for bad in [[],[0,0],[2],[True]]:
            with self.assertRaisesRegex(ValueError,'selected branch'):
                branch_counterfactuals(Environment,checkpoint,actions,Policy,branch_indices=bad)


class OfflineMediaBoundaryTest(unittest.TestCase):
    def test_video_transport_failure_is_recorded_without_text_fallback(self):
        from scripts.evaluate_offline_choice import call_item
        x=item();x['modality']='text+video'
        with patch('scripts.evaluate_offline_choice.build_provider') as build:
            result=call_item(x,{'provider':'openai_compatible','model':'test'},media=None)
        self.assertIn('call_error',result);build.assert_not_called()

    def test_actor_binding_and_intensity_are_not_relaxed(self):
        x=item();x['target_spec']['state_owner']='agent'
        with self.assertRaisesRegex(ValueError,'owner/target'):validate_item(x)
        x=item();x['subtype']='current_intensity'
        with self.assertRaisesRegex(ValueError,'option count'):validate_item(x)

    def test_canonical_cli_routes_both_new_commands(self):
        from pipeline.cli import main
        with patch('scripts.build_offline_choice_dev.main') as build:
            main(['offline-build','--export-only']);build.assert_called_once_with(['--export-only'])
        with patch('scripts.build_offline_choice_dev.main') as build:
            main(['tasks','--protocol','choice','--export-only']);build.assert_called_once_with(['--export-only'])
        with patch('scripts.evaluate_offline_choice.main') as evaluate:
            main(['offline-eval','--check-only']);evaluate.assert_called_once_with(['--check-only'])


class OfflinePairTest(unittest.TestCase):
    def test_paired_answers_and_semantics_must_match(self):
        a=item();b=deepcopy(a)
        a['metadata']['modality_pair_id']='logical1';b['metadata']['modality_pair_id']='logical1'
        b['instance_id']='q1-video';b['modality']='text+video'
        result=score_items([a,b],[{'instance_id':'q1','raw_output':'A'},{'instance_id':'q1-video','raw_output':'B'}])
        self.assertFalse(result['paired_diagnostics'][0]['answer_agreement'])
        b['authoring']['answer']='B'
        with self.assertRaisesRegex(ValueError,'paired inputs or labels differ'):
            score_items([a,b],[])



class OfflineSamplingTest(unittest.TestCase):
    def test_unsupported_top_p_is_omitted_even_for_semantic_repair(self):
        from offline.provider_compat import OfflineSamplingProvider
        class Provider:
            provenance={'model':'existing-gpt-route'}
            def complete(self,messages,**generation):
                self.received=generation;return '{}'
        raw=Provider();provider=OfflineSamplingProvider(raw)
        provider.complete([],temperature=.7,top_p=.9,seed=9)
        self.assertEqual(raw.received,{'temperature':.7,'seed':9})
        self.assertEqual(provider.omitted_sampling,[{'top_p':.9}])

if __name__=='__main__':unittest.main()
