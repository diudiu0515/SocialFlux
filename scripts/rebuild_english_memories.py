"""Rebuild translated dialogue summaries from their exact constituent utterances."""
import re
from scripts.localize_current_data import *


def main():
    items = [json.loads(s) for s in (BANK / 'items.jsonl').read_text().splitlines() if s]
    changes, missing, inventory = {}, [], {}
    staged = {}
    for p in sorted((STAGE / 'scenes').glob('GPT50_*/status.json')):
        scene = p.parent.name
        rows = [item for item in items if item['story_id'] == scene]
        cache = load(p.parent / 'cache.json')
        documents = {relative: clean(load(ROOT / relative)) for relative in load(p)['source_files']}
        mapping = {}
        for source in dict.fromkeys(strings({'items': rows, 'documents': documents})):
            if not CJK.search(source) or not source.startswith(('evaluated_agent: ', 'environment_agent: ')):
                continue
            inventory.setdefault(scene, []).append(digest(source))
            parts = re.split(r'(evaluated_agent: |environment_agent: )', source)
            assert parts[0] == '' and len(parts) % 2 == 1
            result = []
            for i in range(1, len(parts), 2):
                utterance = parts[i + 1].strip()
                if CJK.search(utterance) and digest(utterance) not in cache:
                    missing.append({'scene': scene, 'hash': digest(utterance), 'characters': len(utterance)})
                    break
                result.append(parts[i] + (cache[digest(utterance)] if CJK.search(utterance) else utterance))
            else:
                target = ' '.join(result)
                same_structure(source, target)
                if cache.get(digest(source)) != target:
                    mapping[digest(source)] = target
        staged[scene] = (rows, documents, cache, mapping)
    if missing:
        atomic_json(STAGE / 'memory_missing_strings.json', missing)
        raise ValueError('Constituent translations missing: ' + str(len(missing)))
    for scene, (rows, documents, cache, mapping) in staged.items():
        directory = STAGE / 'scenes' / scene
        if not mapping:
            continue
        def patch(before, after):
            if isinstance(before, str):
                return mapping.get(digest(before), after)
            if isinstance(before, dict):
                return {k: patch(v, after[k]) for k, v in before.items()}
            if isinstance(before, list):
                return [patch(a, b) for a, b in zip(before, after)]
            return after
        cache.update(mapping)
        localized = patch(rows, load(directory / 'items.json'))
        same_structure(rows, localized)
        atomic_json(directory / 'items.json', localized)
        for relative, original in documents.items():
            path = STAGE / 'files' / relative
            localized = patch(original, clean(load(path)))
            same_structure(original, localized)
            atomic_json(path, localized)
        atomic_json(directory / 'cache.json', cache)
        changes[scene] = list(mapping)
    atomic_json(STAGE / 'memory_reconstruction.json', {
        'method': 'Compose exact source-role order using the existing per-utterance English translations.',
        'source_hashes': inventory, 'summaries_rebuilt': sum(map(len, inventory.values())),
        'changed_in_final_pass': sum(map(len, changes.values())),
        'no_new_dialogue_generated': True, 'semantic_equivalence_review': 'pending',
    })
    print(json.dumps({'scenes': len(changes), 'summaries_rebuilt': sum(map(len, changes.values()))}))


if __name__ == '__main__':
    main()
