import tempfile
from pathlib import Path
import unittest
from scripts.run_unified_gpt50_resilient import TransportRoutes,schedule,next_call_index,saved_transport_error
from providers.openai_compatible import ProviderHTTPError

class Stub:
    def __init__(self,outcome):self.outcome=outcome;self._call_index=0;self.audit_records=[];self.seeds=[]
    def complete(self,messages,**generation):
        self.seeds.append(generation['seed']+self._call_index);self._call_index+=1
        if isinstance(self.outcome,Exception):raise self.outcome
        self.audit_records.append({'request':{'seed':self.seeds[-1]},'complete':True});return self.outcome

class ResilientTests(unittest.TestCase):
    def test_transient_failover_preserves_effective_seed(self):
        providers=[Stub(ProviderHTTPError(500,'upstream')),Stub('saved-result')]
        with tempfile.TemporaryDirectory() as directory:
            p=TransportRoutes([{'model':'model'}]*2,Path(directory)/'attempts.json',call_index=8,providers=providers,sleeper=lambda _:None)
            self.assertEqual(p.complete([],seed=100),'saved-result')
            self.assertEqual([x.seeds for x in providers],[[108],[108]])
            self.assertEqual(len(p.attempts),2)
            self.assertEqual(p.call_index,9)

    def test_semantic_failure_is_not_retried(self):
        providers=[Stub(ValueError('invalid output')),Stub('should-not-run')]
        with tempfile.TemporaryDirectory() as directory:
            p=TransportRoutes([{'model':'model'}]*2,Path(directory)/'attempts.json',providers=providers,sleeper=lambda _:None)
            with self.assertRaises(ValueError):p.complete([],seed=100)
            self.assertEqual(providers[1].seeds,[])

    def test_one_failed_scenario_does_not_block_others(self):
        plans=[{'case':{'scenario_id':str(i)}} for i in range(5)];called=[];results={}
        def run(i,p):
            called.append(i)
            if i==1:raise ProviderHTTPError(500,'upstream')
            return {'status':'completed'}
        schedule(plans,run,lambda i,row:results.update({i:row}),workers=2)
        self.assertEqual(sorted(called),list(range(5)))
        self.assertEqual(len(results),5)
        self.assertEqual(results[1]['status'],'runner_failure')

    def test_saved_transport_and_call_index(self):
        self.assertTrue(saved_transport_error({'error':{'type':'ProviderHTTPError','message':'provider HTTP 500: failed'}}))
        self.assertFalse(saved_transport_error({'error':{'type':'ValueError','message':'bad semantic answer'}}))
        self.assertEqual(next_call_index([{'generation':{'seed':100},'provider_audit_records':[{'request':{'seed':105}}]}]),6)

if __name__=='__main__':unittest.main()
