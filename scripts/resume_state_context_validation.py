#!/usr/bin/env python3
"""One bounded transport recovery of frozen, previously unanswered samples."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import validate_state_context_samples as v
from providers.factory import build_provider, public_provider_config
from rollout.configuration import load_rollout_config

OLD = v.OUTPUT
OUT = OLD.parent / 'context_samples_v724_transport_recovery'

class DeadlineProvider:
    def __init__(self, config):
        self.provider = build_provider(config)
        self.deadline = time.monotonic() + 600

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def complete(self, messages, **generation):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('600-second logical-call deadline exceeded')
        self.provider.timeout = remaining
        return self.provider.complete(messages, **generation)

def route_config(env, slot):
    original = env.get('state_appraisal_provider', env['provider'])
    result = deepcopy(original['candidates'][slot])
    for key in ('model', 'stream', 'reasoning_effort', 'max_tokens'):
        if key in original:
            result[key] = original[key]
    result.update(timeout=600, max_transport_attempts=1)
    return result

def main():
    if (OUT / 'preregistration.json').exists():
        raise FileExistsError('This recovery may run only once; prior results are never overwritten')
    frozen = v.load(OLD / 'code_freeze.json')
    for path, digest in frozen['sha256'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    old_results = v.load(OLD / 'results.json')
    old_inputs = v.load(OLD / 'prepared_requests.json')
    env = load_rollout_config(v.CONFIG)['environment']
    phase_a = [2, 8, 9]
    phase_b = [0, 1, 3, 5, 6, 10, 11]
    assert set(phase_a + phase_b) == {int(i) for i,r in old_results['rows'].items() if r['status']=='call_failure'}
    prepared = {}
    for i in phase_a + phase_b:
        prepared[i] = v.prepare_case(old_inputs[i]['case'], env)
        assert prepared[i]['request'] == old_inputs[i]['request'], 'actual input changed'
    routes = {i: route_config(env, 0 if n % 2 == 0 else 4) for n,i in enumerate(phase_a + phase_b)}
    v.save(OUT / 'preregistration.json', {
        'prior_run': str(OLD.relative_to(ROOT)), 'phase_a': phase_a, 'phase_b': phase_b,
        'phase_b_gate': 'all three phase-a logical calls completed, regardless of semantic score',
        'inputs_identical_to_prior_run': True, 'semantic_changes': False,
        'transport_change': '600s logical-call deadline; 3 workers; pin previous successful chat credential routes 0 and 4; one transport attempt',
        'routes': {str(i):public_provider_config(c) for i,c in routes.items()},
        'full_scale_authorized': False,
    })
    v.OUTPUT = OUT
    v.build_provider = DeadlineProvider
    report = {'status':'running','rows':{},'not_attempted':[], 'full_scale_authorized':False}
    v.save(OUT / 'results.json', report)
    for phase, schedule in [('critical_boundaries',phase_a),('remaining_unanswered',phase_b)]:
        if phase == 'remaining_unanswered' and any(report['rows'][str(i)]['status']!='completed' for i in phase_a):
            report['not_attempted'] = phase_b
            report['stop_reason'] = 'predeclared transport-completeness gate failed; no semantic cherry-picking'
            break
        print('START '+phase+' '+str(schedule),flush=True)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(v.run_one,i,prepared[i],env,routes[i]):i for i in schedule}
            for future in as_completed(futures):
                report['rows'][str(futures[future])] = future.result()
                v.save(OUT / 'results.json',report)
    report['status']='completed'
    complete=[r for r in report['rows'].values() if r['status']=='completed']
    negatives=[r for r in complete if r['case']['expected_judgment'] not in v.NEW]
    report['summary']={
        'attempted':len(report['rows']), 'complete':len(complete),
        'call_failures':len(report['rows'])-len(complete),
        'recognition_correct':sum(r['recognition_correct'] for r in complete),
        'strength_correct':sum(r['strength_correct'] for r in complete),
        'direction_correct':sum(r['direction_correct'] for r in complete),
        'negative_observations_evaluable':len(negatives),
        'false_positives':sum(r['false_positive'] for r in negatives),
        'false_positive_rate':sum(r['false_positive'] for r in negatives)/len(negatives) if negatives else None,
    }
    v.save(OUT / 'results.json',report)
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2),flush=True)

if __name__ == '__main__':
    main()
