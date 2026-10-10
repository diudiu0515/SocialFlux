#!/usr/bin/env python3
"""One rollout per scenario; transport recovery cannot block unrelated scenarios."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from copy import deepcopy
from pathlib import Path
import json
import sys
import time
from urllib.error import URLError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import continue_unified_gpt50_corrected as previous
from scripts import run_unified_three_pilot as pilot
from scripts import run_unified_gpt50 as batch
from scripts.recover_exploratory_response_budget import ReplayPrefixProvider
from scripts.validate_state_context_samples import load,save
from providers.factory import build_provider,public_provider_config
from rollout.configuration import load_rollout_config
from pipeline.localization import EnglishOutputProvider, atomic_json, digest, ENGLISH_INSTRUCTION

SOURCE=previous.OUT
OUT=SOURCE.with_name('unified_current_trust_v1_gpt50_active')
WORKERS=3
RETRYABLE={408,409,425,429,500,502,503,504}


def transient(error):
    return isinstance(error,(TimeoutError,ConnectionError,URLError)) or getattr(error,'status',None) in RETRYABLE


def saved_transport_error(record):
    error=record.get('error',{})
    if error.get('type') in ('TimeoutError','ConnectionError','URLError'):return True
    return error.get('type')=='ProviderHTTPError' and any(f'HTTP {code}:' in error.get('message','') for code in RETRYABLE)


def next_call_index(rows):
    for row in reversed(rows):
        base=row.get('generation',{}).get('seed')
        if not isinstance(base,int):continue
        for audit in reversed(row.get('provider_audit_records',[])):
            actual=audit.get('request',{}).get('seed')
            if isinstance(actual,int):return max(0,actual-base+1)
    return len(rows)


class TransportRoutes:
    """Retry only transport failures; preserve effective seed across route attempts."""
    def __init__(self,configs,path,*,call_index=0,providers=None,sleeper=time.sleep):
        self.configs=deepcopy(configs)
        self.providers=providers if providers is not None else [build_provider(c) for c in configs]
        self.path=Path(path);self.call_index=call_index;self.sleeper=sleeper
        self.attempts=[];self._audits=[]
    @property
    def provenance(self):return {'provider':'bounded_transport_routes','model':self.configs[0]['model'],'max_transport_attempts':len(self.providers)}
    @property
    def audit_records(self):return deepcopy(self._audits)
    @property
    def metrics(self):return {'request_count':len(self.attempts),'failed_request_count':sum('error' in a for a in self.attempts)}
    def complete(self,messages,**generation):
        for index,provider in enumerate(self.providers):
            if hasattr(provider,'_call_index'):provider._call_index=self.call_index
            start=len(getattr(provider,'audit_records',[]))
            record={'logical_call_index':self.call_index,'route':index,'messages':deepcopy(messages),
                    'generation':deepcopy(generation),'effective_seed':generation.get('seed',0)+self.call_index if isinstance(generation.get('seed'),int) else None,
                    'provider':public_provider_config(self.configs[index]),'started_at':time.time()}
            self.attempts.append(record);save(self.path,self.attempts)
            try:
                result=provider.complete(messages,**generation)
                record['raw_output']=result
                self.call_index+=1
                return result
            except Exception as exc:
                record['error']={'type':type(exc).__name__,'message':str(exc),'status':getattr(exc,'status',None)}
                if not transient(exc) or index==len(self.providers)-1:
                    self.call_index+=1
                    raise
            finally:
                record['finished_at']=time.time()
                audits=deepcopy(getattr(provider,'audit_records',[])[start:])
                record['provider_audit_records']=audits
                self._audits.extend(audits);save(self.path,self.attempts)
            self.sleeper(min(2**(index+1),8))


def route_configs(plan,role):
    env=plan['environment']
    if role=='policy':primary=plan['policy']['provider']
    elif role=='response':
        wrapper=env['response_provider']
        primary={k:v for k,v in wrapper.items() if k in ('model','stream','timeout','max_tokens','reasoning_effort')}
        primary.update(wrapper['candidates'][0])
    else:primary=env[role+'_provider']
    original=load_rollout_config(batch.CONFIG)['environment']
    if role=='response':alternatives=[original['response_provider']['candidates'][i] for i in (0,2)]
    else:alternatives=[original['provider']['candidates'][i] for i in (0,2,4)]
    result=[deepcopy(primary)]
    identity=lambda c:(c.get('provider'),c.get('endpoint'),c.get('api_key_file'),c.get('api_key_env'))
    for alternate in alternatives:
        candidate=deepcopy(primary)
        for key in ('provider','endpoint','api_key_file','api_key_env','auth_scheme','use_proxy'):
            candidate.pop(key,None)
            if key in alternate:candidate[key]=alternate[key]
        if identity(candidate) not in {identity(c) for c in result}:result.append(candidate)
    # Up to three requests, allowing one final transport retry when only two Fable keys exist.
    if len(result)<3:result.append(deepcopy(result[0]))
    for config in result:
        config.update(max_transport_attempts=1,timeout=600)
    return result[:3]


def prepare():
    plans,prior=previous.prepare()
    status=load(SOURCE/'results.json')
    if status['status']!='stopped_verification_failed':raise ValueError('Unexpected recovery source')
    prereg=deepcopy(prior)
    prereg.update(workers=WORKERS,scenario_failure_blocks_batch=False,verification_first_scenario=None,
                  recovery_source=str(SOURCE.relative_to(ROOT)),max_transport_attempts_per_request=3,
                  semantic_resampling=False,rollouts_per_scenario=1,
                  source_call_sha256={str(p.relative_to(SOURCE)):pilot.sha(p) for p in SOURCE.glob('*/calls/*/requests.json')})
    prereg['code_sha256'][str(Path(__file__).relative_to(ROOT))]=pilot.sha(__file__)
    target=OUT/'preregistration.json'
    if target.exists():
        if load(target)!=prereg:raise ValueError('Run configuration changed')
    else:save(target,prereg)
    return plans,prereg


def install_logging(plans, *, replay_root=None, language=None):
    original=pilot.RoleLogProvider
    by_case={f"{i:02d}_{p['case']['scenario_id']}_gpt":p for i,p in enumerate(plans)}
    def logger(unused_provider,directory,expected):
        relative=directory.relative_to(OUT)
        plan=by_case[relative.parts[0]];role=relative.parts[-1]
        old=(replay_root or SOURCE)/relative/'requests.json'
        rows=load(old) if old.exists() else []
        completed=[];failed=None
        for i,row in enumerate(rows):
            if 'error' in row or 'raw_output' not in row:
                interrupted = replay_root is not None and 'finished_at' not in row and 'error' not in row
                if i!=len(rows)-1 or not (interrupted or saved_transport_error(row)):
                    raise ValueError('Refusing to resample a semantic or validation failure')
                failed=row
            else:completed.append(row)
        provider=TransportRoutes(route_configs(plan,role),directory/'transport_attempts.json',call_index=next_call_index(completed))
        if language == 'en':provider=EnglishOutputProvider(provider)
        if rows:provider=ReplayPrefixProvider(provider,completed,old,failed=failed)
        return original(provider,directory,expected)
    pilot.RoleLogProvider=logger


def schedule(plans,run_one,on_result,workers=WORKERS,indices=None):
    # The resumed scenario is prioritized, but no scenario is a prerequisite.
    order=[1]+[i for i in range(len(plans)) if i!=1]
    if indices is not None:order=[i for i in order if i in indices]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(run_one,i,plans[i]):i for i in order}
        for future in as_completed(futures):
            i=futures[future]
            try:row=future.result()
            except Exception as exc:
                row={'scenario_id':plans[i]['case']['scenario_id'],'policy':'gpt','status':'runner_failure',
                     'error_type':type(exc).__name__,'error':str(exc),'formal_admission':False}
            on_result(i,row)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true')
    parser.add_argument('--resume',action='store_true',help='Continue saved calls, skipping every finished scenario')
    parser.add_argument('--language',choices=['en'],default='en')
    args=parser.parse_args()
    if args.resume:
        plans,_=previous.prepare()
        prereg=load(OUT/'preregistration.json')
        snapshot=OUT/'language_migration'
        if not (snapshot/'snapshot.json').exists():raise ValueError('Missing immutable language migration snapshot')
        resume_source=load(snapshot/'resume_source.json') if (snapshot/'resume_source.json').exists() else {}
        replay_root=OUT/resume_source['replay_root'] if resume_source else snapshot/'original_zh'
        report=load(OUT/'results.json')
        indices=[i for i in range(len(plans)) if str(i) not in report['rows']]
        amendment={'output_language':args.language,'scope':'fresh calls only; replay every saved response verbatim',
                   'instruction_sha256':digest(ENGLISH_INSTRUCTION),
                   'resume_scenario_indices':indices,'original_preregistration_sha256':pilot.sha(OUT/'preregistration.json'),
                   'code_sha256':{str(Path(__file__).relative_to(ROOT)):pilot.sha(__file__),
                                  'pipeline/localization.py':pilot.sha(ROOT/'pipeline/localization.py')},
                   'human_review_status':'pending'}
        target=snapshot/(f"amendment_{resume_source['revision']}.json" if resume_source else 'amendment.json')
        if target.exists() and load(target)!=amendment:raise ValueError('Language continuation already registered differently')
        atomic_json(target,amendment)
    else:
        plans,prereg=prepare()
        indices=None
    if not args.run:print('Prepared 50 independent slots, 3 workers, bounded transport retries, no prerequisite scenario.');return
    if not args.resume and (OUT/'results.json').exists():raise FileExistsError('Batch already started; preserve existing evidence')
    pilot.OUT=OUT;batch.OUT=OUT
    install_logging(plans,replay_root=replay_root if args.resume else None,language=args.language)
    if not args.resume:report={'status':'running','scheduled_scenarios':50,'rollouts_per_scenario':1,'workers':WORKERS,'rows':{},
            'scenario_failure_blocks_batch':False,'state_updates':'current_unified_candidate_every_turn',
            'formal_admission':False,'quality_review_status':'pending'}
    report.update(status='running',output_language=args.language,language_migration=str(target.relative_to(OUT)) if args.resume else None)
    save(OUT/'results.json',report)
    (OUT/'runner.pid').write_text(str(__import__('os').getpid())+'\n')
    print('START: 50 scenarios x 1 rollout; 3 concurrent scenarios; school prefix reused; per-request transport retry <=3.',flush=True)
    def finished(i,row):
        report['rows'][str(i)]=row
        save(OUT/f"{i:02d}_{plans[i]['case']['scenario_id']}_gpt"/'result.json',row)
        save(OUT/'results.json',report)
        try:batch.refresh()
        except Exception as exc:print('Export error: '+repr(exc),flush=True)
    schedule(plans,pilot.run_one,finished,indices=indices)
    report.update(status='completed',completed_scenarios=sum(x['status']=='completed' for x in report['rows'].values()))
    report['failed_scenarios']=50-report['completed_scenarios']
    report['code_freeze_unchanged']=all(pilot.sha(ROOT/p)==h for p,h in prereg['code_sha256'].items())
    if args.resume:
        expected={**prereg['code_sha256'],**amendment['code_sha256']}
        report['authorized_language_amendment_unchanged']=all(pilot.sha(ROOT/p)==h for p,h in expected.items())
    save(OUT/'results.json',report);batch.refresh()
    print('FINISHED: '+str(report['completed_scenarios'])+' completed; '+str(report['failed_scenarios'])+' retained failures.',flush=True)

if __name__=='__main__':main()
