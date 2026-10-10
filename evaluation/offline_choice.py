"""Whole-item accuracy with separate evidence and combination diagnostics."""
from collections import Counter, defaultdict
from tasks.offline_choice import FAMILIES, parse_answer, validate_item, visible_evidence


def score_items(items, responses, *, diagnostic=False, formal=False):
    by_id = {}
    for response in responses:
        if response['instance_id'] in by_id:
            raise ValueError('duplicate response id')
        by_id[response['instance_id']] = response
    ids = [x['instance_id'] for x in items]
    if len(set(ids)) != len(ids) or set(by_id) - set(ids):
        raise ValueError('duplicate items or unknown response ids')
    pairs = defaultdict(dict)
    for item in items:
        pair_id = item.get('metadata', {}).get('modality_pair_id')
        if pair_id:
            if item['modality'] in pairs[pair_id]:
                raise ValueError('duplicate modality within a logical pair')
            pairs[pair_id][item['modality']] = item
    for pair in pairs.values():
        if set(pair) == {'text','text+video'}:
            text, video = pair['text'], pair['text+video']
            if any(text[k] != video[k] for k in ('input','question','options','target_spec','ground_truth')) or any(text['authoring'].get(k) != video['authoring'].get(k) for k in ('answer','acceptable_answers')):
                raise ValueError('paired inputs or labels differ')
    groups = defaultdict(list)
    errors, rows, component = Counter(), [], defaultdict(list)
    for item in items:
        validate_item(item, formal=formal)
        record = by_id.get(item['instance_id'], {})
        call_error = record.get('call_error') or ('missing_response' if not record else None)
        parsed = parse_answer(record.get('raw_output', ''), item['options'], diagnostic)
        if call_error:
            parsed['format_error'] = None
            parsed['answer'] = None
        author = item['authoring']
        accepted = (item['ground_truth']['acceptable_answers'] if formal else
                    author.get('acceptable_answers', [author['answer']]))
        correct = parsed['answer'] in accepted
        semantic_error = parsed['answer'] is not None and not correct
        row = {'instance_id': item['instance_id'], 'correct': correct, 'call_error': call_error,
               'semantic_error': semantic_error, **parsed}
        error = author['option_errors'].get(parsed['answer']) if semantic_error else None
        row['option_error_type'] = error
        if error:
            errors[error] += 1
        variables = item['target_spec']['target_state_ids']
        maps = author['option_variable_map']
        combo = len(next(iter(maps.values()))) > 1
        for key in ['overall', 'task/' + item['task'], 'subtype/' + item['task'] + '/' + item['subtype'],
                    'structure/' + ('combination' if combo else 'single'), 'modality/' + item['modality']]:
            groups[key].append(row)
        for family in sorted({p.split('.')[0] for p in variables}):
            groups['task_state/' + item['task'] + '/' + FAMILIES[family]].append(row)
        if combo and parsed['answer']:
            selected = maps[parsed['answer']]
            for coordinate, judgment in selected.items():
                component[coordinate].append(any(maps[a][coordinate] == judgment for a in accepted))
        if diagnostic and not call_error:
            predicted = set(parsed['evidence_ids'] or [])
            gold = set(author['evidence_ids'])
            hits = len(predicted & gold)
            precision = hits / len(predicted) if predicted else 0.0
            recall = hits / len(gold)
            row['evidence'] = {'precision': precision, 'recall': recall,
                               'f1': 2*precision*recall/(precision+recall) if precision+recall else 0.0,
                               'unknown_ids': sorted(predicted - visible_evidence(item)),
                               'exact_match': predicted == gold}
        rows.append(row)
    def summarize(values):
        n = len(values)
        return {'n': n, 'correct': sum(v['correct'] for v in values),
                'accuracy': sum(v['correct'] for v in values)/n if n else None,
                'semantic_errors': sum(v['semantic_error'] for v in values),
                'format_failures': sum(bool(v['format_error']) for v in values),
                'call_failures': sum(bool(v['call_error']) for v in values)}
    evidence = [r['evidence'] for r in rows if 'evidence' in r]
    row_by_id = {r['instance_id']:r for r in rows}
    paired_rows = []
    for pair_id, pair in pairs.items():
        if set(pair) == {'text','text+video'}:
            left, right = [row_by_id[pair[m]['instance_id']] for m in ('text','text+video')]
            paired_rows.append({'pair_id':pair_id,'text_correct':left['correct'],'video_correct':right['correct'],
                                'answer_agreement':left['answer'] == right['answer'] if left['answer'] and right['answer'] else None})
    return {'paired_diagnostics': paired_rows, 'label_basis': 'human_ground_truth' if formal else 'provisional_author_answers',
            'groups': {k: summarize(v) for k, v in sorted(groups.items())},
            'wrong_option_types': dict(errors),
            'combination_diagnostics': {k: {'n_parsed': len(v), 'accuracy': sum(v)/len(v)} for k, v in component.items()},
            'evidence_diagnostics': {'n': len(evidence), 'macro_f1': sum(v['f1'] for v in evidence)/len(evidence) if evidence else None,
                                     'format_failures': sum(bool(r['evidence_format_error']) for r in rows)},
            'rows': rows}
