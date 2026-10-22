#!/usr/bin/env python3
"""One transport-only continuation, preserving every completed model output."""
from copy import deepcopy
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_unified_gpt50_corrected as corrected
from scripts import run_unified_three_pilot as pilot
from scripts.validate_state_context_samples import load,save
from scripts.recover_exploratory_response_budget import ReplayPrefixProvider
from pipeline.runtime import appraisal_route_config as route_config
from providers.factory import public_provider_config

SOURCE=corrected.OUT
OUT=SOURCE.with_name('unified_current_trust_v1_gpt50_corrected_transport')
original_prepare=corrected.prepare
original_logger=pilot.RoleLogProvider


def prepare():
    destination=corrected.OUT
    try:
        corrected.OUT=SOURCE
        plans,prereg=original_prepare()
    finally:
        corrected.OUT=destination
    result=load(SOURCE/'results.json')
    if result['status']!='stopped_verification_failed' or set(result['rows'])!={'1'} or result['rows']['1'].get('error_type')!='TimeoutError':
        raise ValueError('Only the recorded school timeout is eligible')
    env=plans[1]['environment']
    env['state_appraisal_provider']=route_config({k:v for k,v in env.items() if k!='state_appraisal_provider'},0)
    prereg=deepcopy(prereg)
    prereg['plans'][1]['environment']['state_appraisal_provider']=public_provider_config(env['state_appraisal_provider'])
    prereg.update(transport_continuation_source=str(SOURCE.relative_to(ROOT)),
                  reuse_completed_call_prefix=True,transport_change='Retry only the timed-out state call through existing GPT credential route 0; replay all completed calls.')
    prereg['code_sha256'][str(Path(__file__).relative_to(ROOT))]=pilot.sha(__file__)
    prereg['source_call_sha256']={str(p.relative_to(SOURCE)):pilot.sha(p) for p in SOURCE.glob('*/calls/*/requests.json')}
    path=OUT/'preregistration.json'
    if path.exists():
        if load(path)!=prereg:raise ValueError('Continuation changed')
    else:save(path,prereg)
    return plans,prereg


def replay_logger(provider,directory,expected):
    old=SOURCE/directory.relative_to(OUT)/'requests.json'
    if old.exists():
        rows=load(old);completed=[];failed=None
        for i,row in enumerate(rows):
            if 'error' in row or 'raw_output' not in row:
                if i!=len(rows)-1 or row.get('error',{}).get('type')!='TimeoutError':
                    raise ValueError('Cannot resample an existing semantic/validation failure')
                failed=row
            else:completed.append(row)
        provider=ReplayPrefixProvider(provider,completed,old,failed=failed)
    return original_logger(provider,directory,expected)

if __name__=='__main__':
    corrected.OUT=OUT;corrected.prepare=prepare;pilot.RoleLogProvider=replay_logger
    corrected.main()
