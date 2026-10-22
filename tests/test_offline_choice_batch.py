"""Fixed-cohort provenance, task isolation, and source-preserving recovery."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from offline.choice_batch import source_for, run_batch, validate_branches, generate_with_recovery
from offline.choice_builder import save, sha, assemble
from tests.test_offline_choice import item


class OfflineBatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {'source_root':str(self.root/'original'),
                       'scenario_root':str(self.root/'scenarios'),
                       'output':str(self.root/'bank'), 'tasks':['T1','T3'],
                       'scenario_numbers':[1], 'bank_id':'SFG50'}
        save(self.root/'scenarios/gpt_001.json', {'scenario_id':'GPT50_001'})
        self.trajectory = {'scenario_id':'GPT50_001','trajectory_id':'source-one',
                           'turns':[{'turn_id':f't{n}'} for n in range(1,4)]}
        self.path = self.root/'original/run_GPT50_001_gpt/partial_trajectory.json'
        save(self.path,self.trajectory)
        self.review = {'candidates':[{'scenario_id':'GPT50_001',
            'latest_attempt':{'artifact_sha256':sha(self.path)},
            'model_semantic_review':{'decision':'reject'}}]}
        save(self.root/'original/gate3_followup/source_review.json',self.review)

    def test_partial_rejected_source_is_preserved_and_bound_by_hash(self):
        before = self.path.read_bytes()
        with patch('offline.choice_batch.runtime') as runtime:
            *_, source = source_for(self.config,1)
        runtime.assert_not_called()
        self.assertEqual(source['source_review_status'],'reject')
        self.assertEqual(source['origin'],'existing_partial_rollout')
        self.assertFalse(source['source_complete'])
        self.assertEqual(self.path.read_bytes(),before)
        changed = deepcopy(self.trajectory)
        changed['turns'][0]['extra'] = 'changed'
        save(self.path,changed)
        with self.assertRaisesRegex(ValueError,'review hash'):
            source_for(self.config,1)

    def test_missing_history_uses_separate_prefix_never_overwrites_failure(self):
        failed={**self.trajectory,'turns':[],'generation_error':{'error':'original failure'}}
        save(self.path,failed)
        before=self.path.read_bytes()
        policy=SimpleNamespace(policy_id='existing_policy')
        with patch('offline.choice_batch.runtime',return_value=(object(),lambda:policy)), \
             patch('offline.choice_batch.RolloutRunner') as runner:
            runner.return_value.run.return_value=deepcopy(self.trajectory)
            *_, source=source_for(self.config,1)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(source['source_review_status'],'not_reviewed')
        self.assertEqual(Path(source['trajectory_path']).name,'source_prefix.json')
        self.assertFalse(source['source_complete'])
        with patch('offline.choice_batch.runtime') as runtime:
            *_, repeated=source_for(self.config,1)
        runtime.assert_not_called()
        self.assertEqual(source,repeated)

    def test_t2_rejected_before_any_provider_or_source_access(self):
        with patch('offline.choice_batch.source_for') as source, \
             patch('offline.choice_batch.author_provider') as provider:
            with self.assertRaisesRegex(ValueError,'T2 is paused'):
                run_batch(self.config,SimpleNamespace(tasks=['T2']))
        source.assert_not_called()
        provider.assert_not_called()

    def test_pending_recorded_intervention_cannot_fall_back_to_unmodified_policy(self):
        save(self.path,{**self.trajectory,'turns':[]})
        save(Path(self.config['output'])/'sources/GPT50_001/source_intervention.json',
             {'review_status':'pending_human_review'})
        with patch('offline.choice_batch.runtime') as runtime:
            with self.assertRaisesRegex(ValueError,'prefix intervention is pending'):
                source_for(self.config,1)
        runtime.assert_not_called()

    def test_transport_recovery_preserves_failure_and_never_retries_semantics(self):
        with patch('offline.choice_batch.generate_case',side_effect=[TimeoutError('read timeout'),{'completed_tasks':['T3']}]) as generate, \
             patch('offline.choice_batch.sleep'):
            result=generate_with_recovery(self.config,1,['T3'],replay=True,run='retry-fixture',retries=2)
        self.assertEqual(generate.call_count,2)
        self.assertEqual(len(result['recovered_failures']),1)
        self.assertTrue((self.root/'bank/sources/GPT50_001/failures/retry-fixture_attempt_1.json').is_file())
        with patch('offline.choice_batch.generate_case',side_effect=ValueError('source hash differs')) as generate:
            with self.assertRaisesRegex(ValueError,'source hash'):
                generate_with_recovery(self.config,1,['T3'],replay=True,run='invalid-fixture',retries=2)
        self.assertEqual(generate.call_count,1)
        with patch('offline.choice_batch.generate_case',side_effect=[ValueError('provider returned empty content'),{'completed_tasks':['T3']}]) as generate, \
             patch('offline.choice_batch.sleep'):
            result=generate_with_recovery(self.config,1,['T3'],replay=True,run='empty-fixture',retries=1)
        self.assertEqual(generate.call_count,2)
        self.assertEqual(result['recovered_failures'][0]['type'],'ValueError')

    def test_local_export_does_not_replace_active_run_status(self):
        output=Path(self.config['output']);save(output/'run_status_T3.json',{'status':'running','pid':123})
        args=SimpleNamespace(tasks=['T3'],scenarios=None,export_only=True,pair_media=None)
        manifest={'complete':False,'expected_items':8}
        with patch('offline.choice_batch.export_batch',return_value=([],manifest)):
            run_batch(self.config,args)
        from offline.choice_builder import load
        self.assertEqual(load(output/'run_status_T3.json'),{'status':'running','pid':123})
        self.assertEqual(load(output/'export_status.json')['status'],'incomplete')

    def test_pair_report_identifies_exact_question_version(self):
        from offline.choice_media import pair_assets
        from offline.choice_builder import write_bundle,load
        question=item()
        question['authoring']['review_notes']='test fixture'
        question['authoring']['replay_status']='not_required'
        trajectory=self.root/'media_trajectory.json'
        save(trajectory,{'turns':[]})
        question['authoring']['construction_source']={'trajectory_path':str(trajectory)}
        media_manifest=self.root/'media_manifest.json'
        save(media_manifest,{'requests':[],'batch_root':str(self.root)})
        output=self.root/'paired'
        write_bundle([question],output)
        report=pair_assets([question],media_manifest,output,frames=False)
        self.assertEqual(report['items_sha256'],sha(output/'items.jsonl'))
        self.assertEqual(report['input_item_count'],1)
        self.assertEqual(report['logical_pairs'],0)
        self.assertEqual(len(report['gaps']),1)
        self.assertEqual(load(output/'pairing_report.json'),report)

    def test_stable_identity_and_independent_raw_author_cache(self):
        sample=item();raw={k:sample[k] for k in ['question','subtype','options','target_spec']}
        raw.update({k:sample['authoring'][k] for k in ['answer','evidence_ids','rationale','option_errors','option_variable_map']})
        raw['review_notes']='pending'
        original=deepcopy(raw)
        kwargs=dict(task='T1',source={'scenario_id':'GPT50_001','trajectory_id':'one'},
                    public_input=sample['input'],ordinal=0,index=0,instance_id='SFG50-001-T1-01')
        first=assemble(raw,**kwargs)
        second=assemble(raw,**kwargs)
        self.assertEqual(first,second)
        self.assertEqual(raw,original)
        self.assertEqual(first['instance_id'],'SFG50-001-T1-01')

    def test_chinese_action_names_bind_to_candidates_without_hiding_conflicts(self):
        sample=item();raw={k:sample[k] for k in ['question','subtype','options','target_spec']}
        raw.update({k:sample['authoring'][k] for k in ['answer','evidence_ids','rationale','option_errors','option_variable_map']})
        raw.update(subtype='immediate_effect',review_notes='pending')
        public=deepcopy(sample['input'])
        public['candidate_actions']=[{'action_id':'action_1','text':'核对交接记录'},
                                     {'action_id':'action_2','text':'直接交接'}]
        kwargs=dict(task='T3',source={'scenario_id':'GPT50_001','trajectory_id':'one'},
                    public_input=public,ordinal=0,index=0,instance_id='test-action')
        for name in ['行动一','行动 1','action_1']:
            raw['question']=f'采取{name}后，甲对乙的信任在下一次回应中如何变化？'
            raw['target_spec']['action_id']='action_1'
            self.assertEqual(assemble(raw,**kwargs)['target_spec']['action_id'],'action_1')
        raw['target_spec']['action_id']='action_2'
        with self.assertRaisesRegex(ValueError,'conflicts'):
            assemble(raw,**kwargs)
        raw['question']='采取行动一或行动二后，甲的信任如何变化？'
        with self.assertRaisesRegex(ValueError,'one candidate'):
            assemble(raw,**kwargs)

    def test_delayed_reference_rejects_source_action_and_window_drift(self):
        import hashlib,json
        snapshot={'state':{},'event_plan':{'plan_hash':'fixed'}}
        trajectory={'turns':[{}, {}, {'environment_snapshot_before':snapshot}]}
        actions=[{'text':'one'},{'text':'two'}]
        digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        rows=[{'snapshot_sha256':digest,'candidate_action':a,'delayed_horizon':5,
               'external_event_plan_hash':'fixed','window_complete':True,
               'actual_turns_observed':5,'future_turns':[{}]*5} for a in actions]
        self.assertEqual(validate_branches(rows,trajectory,actions,5),rows)
        for field,value in [('snapshot_sha256','different'),('external_event_plan_hash','different'),
                            ('actual_turns_observed',4),('candidate_action',{'text':'changed'})]:
            bad=deepcopy(rows);bad[0][field]=value
            with self.assertRaises(ValueError):validate_branches(bad,trajectory,actions,5)


class FactualReferenceTest(unittest.TestCase):
    def test_empty_provider_response_preserves_steps_for_outer_recovery(self):
        from rollout.counterfactual import branch_counterfactuals
        calls=[]
        class Environment:
            def restore(self,snapshot,episode_id):
                self.session=deepcopy(snapshot);self.session['turns']=[]
            def snapshot(self):
                return {k:deepcopy(v) for k,v in self.session.items() if k!='turns'}
            def observe(self):return {}
            def step(self,action):
                calls.append(action['text'])
                if len(calls)>1:raise ValueError('provider returned empty content')
                log={'state_after':{},'dynamics_after':{}}
                self.session['turns'].append(log)
                return {},log
        class Policy:
            def generate(self,observation):return {'text':'continue'}
        checkpoint={'turn_id':'t3','environment_snapshot_before':{
            'state':{},'dynamics':{},'status':'active','event_plan':{'plan_hash':'fixed'}}}
        saved=[]
        with self.assertRaisesRegex(ValueError,'provider returned empty content'):
            branch_counterfactuals(Environment,checkpoint,[{'text':'one'},{'text':'two'}],Policy,
                                   audit_callback=lambda *row:saved.append(row))
        self.assertEqual(calls,['one','continue'])
        self.assertEqual(len(saved),1)
        self.assertIn('environment_snapshot_after',saved[0][-1])

    def test_actual_after_snapshot_resumes_without_repeating_paid_step(self):
        from rollout.counterfactual import branch_counterfactuals
        class Environment:
            calls=0
            def restore(self,snapshot,episode_id):
                self.session=deepcopy(snapshot);self.session.update(turns=[],status='active')
            def snapshot(self):
                return {k:deepcopy(v) for k,v in self.session.items() if k!='turns'}
            def observe(self):return {}
            def step(self,action):
                Environment.calls+=1
                before=self.snapshot();self.session['state']['x']+=1
                log={'state_before':before['state'],'state_after':deepcopy(self.session['state']),
                     'dynamics_before':{},'dynamics_after':{},'policy_action':deepcopy(action),
                     'environment_snapshot_before':before}
                self.session['turns'].append(log);return {},log
        class Policy:
            def generate(self,observation):return {'text':'continue'}
        checkpoint={'turn_id':'t3','environment_snapshot_before':{
            'state':{'x':0},'dynamics':{},'status':'active','event_plan':{'plan_hash':'fixed'}}}
        actions=[{'text':'one'},{'text':'two'}]
        original=branch_counterfactuals(Environment,checkpoint,actions,Policy)
        Environment.calls=0
        prior=original[0]['future_turns'][:3]
        rows=branch_counterfactuals(Environment,checkpoint,actions,Policy,
                                   resume_logs={0:prior},completed_branches={1:original[1]})
        self.assertEqual(Environment.calls,2)
        self.assertEqual(rows[0]['resumed_prefix_turns'],3)
        self.assertEqual(rows[0]['state_after_delayed'],{'x':5})
        bad=deepcopy(prior);bad[-1]['environment_snapshot_after']['state']['x']=99
        with self.assertRaisesRegex(ValueError,'after-snapshot'):
            branch_counterfactuals(Environment,checkpoint,actions,Policy,resume_logs={0:bad})

    def trajectory(self):
        rows=[]
        for n in range(7):
            snapshot={'state':{'x':n},'dynamics':{},'event_plan':{'plan_hash':'fixed'},
                      'public_timeline':[],'segment_index':0,'elapsed_time':n}
            rows.append({'turn_id':f't{n+1}','environment_snapshot_before':snapshot,
                         'policy_action':{'text':f'action {n}'},'state_before':{'x':n},
                         'state_after':{'x':n+1},'dynamics_before':{},'dynamics_after':{},
                         'elapsed_time_after':n+1,'segment_transition_after':None})
        return {'turns':rows,'policy_provenance':{'model':'test'}}

    def test_factual_reuse_requires_complete_fixed_external_window(self):
        from offline.factual_reference import factual_reference,assert_same_policy
        trajectory=self.trajectory();source={'trajectory_path':'fixture','trajectory_sha256':'frozen'}
        ref=factual_reference(trajectory,5,source)
        self.assertEqual(ref['candidate_action'],{'text':'action 2'})
        self.assertEqual(ref['state_after_delayed'],{'x':7})
        assert_same_policy(ref,SimpleNamespace(provenance={'model':'test'}))
        with self.assertRaisesRegex(ValueError,'policy differs'):
            assert_same_policy(ref,SimpleNamespace(provenance={'model':'different'}))
        for change in ['short','transition','plan','state']:
            bad=deepcopy(trajectory)
            if change=='short':bad['turns'].pop()
            elif change=='transition':bad['turns'][4]['segment_transition_after']={'advanced':True}
            elif change=='plan':bad['turns'][4]['environment_snapshot_before']['event_plan']['plan_hash']='different'
            else:bad['turns'][4]['state_before']={'x':99}
            self.assertIsNone(factual_reference(bad,5,source))

    def test_completed_branches_skip_provider_and_reject_inconsistent_evidence(self):
        from offline.factual_reference import factual_reference
        from rollout.counterfactual import branch_counterfactuals
        trajectory=self.trajectory();source={'trajectory_path':'fixture','trajectory_sha256':'frozen'}
        first=factual_reference(trajectory,5,source);second=deepcopy(first)
        second['candidate_action']['text']='alternative'
        second['future_turns'][0]['policy_action']['text']='alternative'
        actions=[first['candidate_action'],second['candidate_action']]
        def forbidden():raise AssertionError('completed branch must not construct provider')
        rows=branch_counterfactuals(forbidden,trajectory['turns'][2],actions,forbidden,
                                   completed_branches={0:first,1:second})
        self.assertEqual(rows,[first,second])
        second['future_turns'][2]['state_before']={'x':900}
        with self.assertRaisesRegex(ValueError,'discontinuous'):
            branch_counterfactuals(forbidden,trajectory['turns'][2],actions,forbidden,
                                  completed_branches={0:first,1:second})


if __name__=='__main__':
    unittest.main()
