"""Audit isolation, frozen-version caching and migration conclusions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from offline.reuse_audit import BLIND, REVIEW, call, digest, groups, validate, export
from providers.factory import public_provider_config
from tasks.offline_choice import visible_evidence
import web.offline_review as web_review


class FakeProvider:
    def __init__(self,result):self.result=result;self.requests=[];self.metrics={}
    def complete(self,messages,**generation):self.requests.append(deepcopy(messages));return json.dumps(self.result,ensure_ascii=False)


class ReuseAuditTest(unittest.TestCase):
    def setUp(self):
        self.group=groups()[0]
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.run=Path(self.temp.name)
        self.config={'provider':'test','model':'fixture'}
        (self.run/'manifest.json').write_text(json.dumps({'provider':public_provider_config(self.config)}))

    def cache(self,phase,result,blind=None):
        path=self.run/'groups'/self.group['group_id'];path.mkdir(parents=True,exist_ok=True)
        value={'result':result,'binding':digest({'items':self.group['items'],'prompt':BLIND if phase=='blind' else REVIEW,'config':public_provider_config(self.config)}),'blind_sha256':digest(blind) if blind else None}
        (path/(phase+'.json')).write_text(json.dumps(value))

    def blind(self):
        return {'answers':[{'instance_id':x['instance_id'],'answer':x['authoring']['answer'],
                  'plausible_answers':[x['authoring']['answer']],'evidence_ids':x['authoring']['evidence_ids'],'rationale':'fixture'} for x in self.group['items']]}

    def review(self):
        return {'reviews':[{'instance_id':x['instance_id'],'migration_level':'metadata_only','new_form':'T1/current_state',
            'best_answer':x['authoring']['answer'],'acceptable_answers':[x['authoring']['answer']],
            'public_evidence_sufficient':True,'evidence_ids':x['authoring']['evidence_ids'],'counterevidence_ids':[],
            'issues':[],'rationale':'fixture','revision':'','primary_capability':'situational_evidence_integration',
            'design_difficulty':'ordinary','difficulty_reason':''} for x in self.group['items']]}

    def test_blind_api_payload_omits_author_and_future_and_cache_is_bound(self):
        self.group['items'][0]['authoring']['hidden_future']='PRIVATE_SENTINEL'
        fake=FakeProvider(self.blind())
        with patch('offline.reuse_audit.build_provider',return_value=fake):
            result=call(self.group,'blind',self.config,self.run)
            self.assertEqual(call(self.group,'blind',self.config,self.run),result)
            self.assertEqual(len(fake.requests),1)
            payload=json.loads(fake.requests[0][1]['content'])
            self.assertEqual(set(payload),{'shared_input','questions'})
            for token in ['PRIVATE_SENTINEL','old_labels','target_spec','ground_truth','authoring']:
                self.assertNotIn(token,json.dumps(payload))
            self.group['items'][0]['question']+='edited'
            with self.assertRaisesRegex(ValueError,'cached input mismatch'):call(self.group,'blind',self.config,self.run)
            self.assertEqual(len(fake.requests),1)

    def test_review_sends_only_authorized_label_subset(self):
        self.group['items'][0]['authoring']['secret_future']='PRIVATE_SENTINEL'
        fake=FakeProvider(self.review())
        with patch('offline.reuse_audit.build_provider',return_value=fake):call(self.group,'review',self.config,self.run,self.blind())
        payload=json.loads(fake.requests[0][1]['content'])
        self.assertEqual(set(payload['old_labels'][0]),{'instance_id','answer','acceptable_answers','target_spec'})
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(payload))

    def test_missing_items_and_invisible_evidence_rejected(self):
        result=self.blind();result['answers'].pop()
        with self.assertRaises(ValueError):validate(json.dumps(result),self.group,'blind')
        result=self.review();result['reviews'][0]['evidence_ids']=['future:t9']
        with self.assertRaisesRegex(ValueError,'invisible evidence'):validate(json.dumps(result),self.group,'review')

    def test_metadata_only_requires_unique_supported_answer(self):
        result=self.review();result['reviews'][0]['public_evidence_sufficient']=False
        with self.assertRaisesRegex(ValueError,'unambiguous'):validate(json.dumps(result),self.group,'review')

    def test_changed_answer_requires_substantive_revision_and_gt_is_not_minted(self):
        result=self.review();r=result['reviews'][1];x=self.group['items'][1]
        r['best_answer']=next(k for k in x['options'] if k!=x['authoring']['answer']);r['acceptable_answers']=[r['best_answer']]
        self.cache('blind',self.blind());self.cache('review',result,self.blind())
        export(self.run,[self.group]);rows=json.loads((self.run/'results.json').read_text())['items']
        self.assertEqual(rows[1]['migration_level'],'substantive');self.assertTrue(all(r['formal_usable'] is False for r in rows))
        self.assertTrue(all(i['ground_truth'] is None for i in self.group['items']))

    def test_web_audit_invalidated_by_source_edit(self):
        x=deepcopy(self.group['items'][0]);directory=self.run/'tasks/examples/offline_legacy_api_audit';directory.mkdir(parents=True)
        (directory/'results.json').write_text(json.dumps({'items':[{'instance_id':x['instance_id'],'item_sha256':web_review.item_digest(x),'migration_level':'editorial'}]}))
        with patch.object(web_review,'ROOT',self.run):
            self.assertEqual(web_review.migration_review(x)['migration_level'],'editorial')
            x['question']+='edited';self.assertIsNone(web_review.migration_review(x))

    def test_failed_phase_is_pending_not_a_quality_verdict(self):
        self.cache('blind',self.blind())
        calls=self.run/'calls'/self.group['group_id']/'review';calls.mkdir(parents=True)
        (calls/'failed.json').write_text(json.dumps({'started_at_unix':1,'status':'failed','error':{'type':'TimeoutError','message':'PRIVATE_SENTINEL'}}))
        summary=export(self.run,[self.group]);data=json.loads((self.run/'results.json').read_text())
        self.assertEqual(summary['reviewed_items'],0)
        self.assertEqual(summary['blind_completed_items'],len(self.group['items']))
        self.assertEqual(summary['pending_reasons'],{'api_timeout':len(self.group['items'])})
        self.assertEqual(data['items'],[])
        self.assertTrue(all(x['migration_status']=='pending' and 'migration_level' not in x for x in data['pending_items']))
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(data))

    def test_exhausted_transport_budget_never_reissues_request(self):
        calls=self.run/'calls'/self.group['group_id']/'blind';calls.mkdir(parents=True)
        for i in range(2):(calls/f'{i}.json').write_text(json.dumps({'status':'failed'}))
        fake=FakeProvider(self.blind())
        with patch('offline.reuse_audit.build_provider',return_value=fake):
            with self.assertRaisesRegex(RuntimeError,'retry budget exhausted'):call(self.group,'blind',self.config,self.run)
        self.assertEqual(fake.requests,[])

    def test_export_cannot_rebind_old_review_to_changed_question(self):
        self.cache('blind',self.blind());self.cache('review',self.review(),self.blind())
        self.group['items'][0]['question']+='edited'
        summary=export(self.run,[self.group])
        self.assertEqual(summary['reviewed_items'],0)
        self.assertEqual(summary['blind_completed_items'],0)
        self.assertEqual(summary['pending_reasons'],{'cached_input_mismatch':len(self.group['items'])})


if __name__=='__main__':unittest.main()
