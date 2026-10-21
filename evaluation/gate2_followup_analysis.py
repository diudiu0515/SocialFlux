"""Matched triplet diagnostic for wording effects versus repeat variability.

This secondary diagnostic uses one shared active-variable denominator across
original, repeat and paraphrase; it does not replace the registered pair metric.
"""
import json
import random
from pathlib import Path

from evaluation.transition_metrics import sign

ROOT = Path(__file__).resolve().parents[1]


def audit_repeat_inputs(directory, records):
    checked, mismatches, missing = 0, [], []
    for record in records:
        if 'repeat' not in record.get('comparisons', {}):
            continue
        sid = record['scenario_id']
        for stage in ('state', 'interaction'):
            first = []
            for condition in ('original', 'repeat'):
                reused = record.get('reused_outputs', {}).get(condition)
                source = (ROOT / reused['path']).parents[2] if reused else directory
                logs = [json.loads(p.read_text()) for p in (source / 'calls' / sid / condition / stage).glob('*.json')]
                if not logs:
                    first.append(None)
                else:
                    call = min(logs, key=lambda x: x['started_at_unix'])
                    first.append(dict(messages=call['messages'], generation=call['generation']))
            if any(x is None for x in first):
                missing.append(dict(scenario_id=sid, stage=stage)); continue
            checked += 1
            if first[0] != first[1]:
                mismatches.append(dict(scenario_id=sid, stage=stage))
    return dict(compared_stage_pairs=checked, matched_stage_pairs=checked-len(mismatches), mismatches=mismatches,
                missing=missing, all_checked_inputs_identical=bool(checked) and not mismatches and not missing)


def matched_controls(records):
    scenes = []
    for row in records:
        comparisons = row.get('comparisons', {})
        if 'repeat' not in comparisons or 'paraphrase' not in comparisons:
            continue
        repeat, paraphrase = (comparisons[k]['overall'] for k in ('repeat', 'paraphrase'))
        original = repeat['left_numeric_delta']
        if original != paraphrase['left_numeric_delta']:
            raise ValueError('Triplet does not share one original output')
        r, p = repeat['right_numeric_delta'], paraphrase['right_numeric_delta']
        keys = [k for k in sorted(original.keys() & r.keys() & p.keys()) if original[k] or r[k] or p[k]]
        if not keys:
            continue
        scenes.append(dict(scenario_id=row['scenario_id'], active_dimensions=len(keys),
            repeat_matches=sum(sign(original[k]) == sign(r[k]) for k in keys),
            paraphrase_matches=sum(sign(original[k]) == sign(p[k]) for k in keys),
            repeat_reversals=sum(sign(original[k])*sign(r[k]) == -1 for k in keys),
            paraphrase_reversals=sum(sign(original[k])*sign(p[k]) == -1 for k in keys)))
    active = sum(x['active_dimensions'] for x in scenes)
    rate = lambda key: sum(x[key] for x in scenes) / active if active else None
    repeat, paraphrase = rate('repeat_matches'), rate('paraphrase_matches')
    interval = None
    if len(scenes) >= 2:
        rng = random.Random(20261022)
        samples = []
        for _ in range(2000):
            sample = rng.choices(scenes, k=len(scenes))
            samples.append(sum(x['paraphrase_matches']-x['repeat_matches'] for x in sample) / sum(x['active_dimensions'] for x in sample))
        samples.sort(); interval = [samples[49], samples[1949]]
    return dict(matched_scenarios=len(scenes), active_dimensions=active, repeat_direction_agreement=repeat,
                paraphrase_direction_agreement=paraphrase, paraphrase_minus_repeat=paraphrase-repeat if active else None,
                paired_scene_bootstrap_ci95=interval, bootstrap_samples=2000, bootstrap_seed=20261022,
                repeat_reversal_rate=rate('repeat_reversals'), paraphrase_reversal_rate=rate('paraphrase_reversals'),
                scenes=scenes, primary_threshold_unchanged=.8,
                note='Secondary diagnostic: same scenes and union of variables active in any of the three conditions. Machine equivalence screening only; independent human equivalence pending.')


def report(directory):
    records = [json.loads(p.read_text()) for p in sorted(directory.glob('results/*.json'))]
    result = matched_controls(records)
    result['repeat_input_audit'] = audit_repeat_inputs(directory, records)
    result['recorded_sources'] = len(records)
    from offline.choice_builder import save
    save(directory / 'matched_controls.json', result)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('directory', type=Path)
    print(json.dumps(report(parser.parse_args().directory)))
