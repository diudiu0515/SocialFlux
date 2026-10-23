"""Publish-ready T1/T3 native-video overlay; T2 stays text-only.

All question hashes, private evidence and existing annotation records survive.
Old generated video files may be pruned only from the isolated new site package.
"""
from argparse import ArgumentParser
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.seedance_state_batch import OUT, BANK, load, save, sha
from scripts import build_gate2_annotation as gate2
from scripts.export_checkpoint_annotation import replace_media_reviews, media_snapshot
from scripts.prepare_human_gt_release import digest, packed
from offline.talking_head import public_nodes
from offline.revision_checks import audio_evidence_valid, sync_evidence_valid

RELEASE = 'annotation400-seedance-state-20261023-v3'


def replace_e8_video(task, original_by_sha, current_by_id, site):
    """New version of the same state/event audit; retain its frozen trajectory."""
    old = original_by_sha.get(task['video']['sha256'])
    if not old or old['scenario_id'] != task['scene_id']:
        raise ValueError('E8 original media binding missing or mismatched')
    row = current_by_id[old['media_asset_id']]
    if any(row[k] != old[k] for k in ('scenario_id', 'event_family', 'media_asset_id', 'scenario_profile_sha256')):
        raise ValueError('E8 event binding changed')
    revised = deepcopy(task)
    revised['video'] = gate2.copy_video(site, ROOT / 'data/gpt50/experiment' / row['video_file'],
        row['video_sha256'], '/media/'+row['video_sha256']+'.mp4')
    revised['evidence']['media_refresh'] = dict(media_asset_id=row['media_asset_id'],
        event_family=row['event_family'], previous_video_sha256=task['video']['sha256'],
        video_sha256=row['video_sha256'], prompt_sha256=row['prompt_sha256'],
        note='同一触发素材位的新视频；轨迹和触发语义保留，旧视频的质量结论不继承。')
    revised['id'] = 'E8:' + gate2.digest(dict(source_task=task['id'], video_sha256=row['video_sha256']))
    revised.pop('sha256', None)
    revised['sha256'] = gate2.digest(revised)
    return revised


def replace_online_reviews(registry, research, site):
    from scripts.refresh_online_state_videos import TARGET, OLD
    from evaluation.t4_asset_coverage import audit_asset_coverage, require_complete_assets
    path = TARGET / 'manifest.json'
    manifest = load(path)
    require_complete_assets(audit_asset_coverage(manifest, ROOT / 'data/gpt50/experiment'))
    if manifest.get('trigger_policy_unchanged') is not True or manifest.get('verified_at_utc') is None:
        raise ValueError('Online generation must be finalized before publication')
    # Publish every reusable slot, including ones absent from the historical T4 sample.
    for row in manifest['requests']:
        gate2.copy_video(site, ROOT / 'data/gpt50/experiment' / row['video_file'], row['video_sha256'],
                         '/media/'+row['video_sha256']+'.mp4')
    expanded = gate2.expand_registry(registry)
    current = next(v for v in expanded['versions'] if v['sha256'] == expanded['current'])
    original_by_sha = {r['video_sha256']: r for r in load(OLD)['requests'] if r.get('video_sha256')}
    current_by_id = {r['media_asset_id']: r for r in manifest['requests']}
    tasks = [replace_e8_video(t, original_by_sha, current_by_id, site) if t['kind'] == 'E8' else deepcopy(t)
             for t in current['tasks'] if t['kind'] not in ('T4-video', 'T4-trigger')]
    def add(ident, sid, kind, title, evidence, questions, stage='review', **extra):
        task = dict(id=ident, scene_id=sid, kind=kind, title=title, stage=stage,
                    evidence=evidence, questions=questions, **extra)
        task['sha256'] = gate2.digest(task)
        tasks.append(task)
        return task
    coverage = gate2.add_t4_reviews(research, site, add, manifest_path=path)
    bundle = {k: deepcopy(v) for k,v in current.items() if k not in ('sha256', 'tasks')}
    bundle['tasks'] = tasks
    bundle['sha256'] = gate2.digest(bundle)
    versions = deepcopy(expanded['versions'])
    if bundle['sha256'] not in {v['sha256'] for v in versions}:
        versions.append(bundle)
    return dict(current=bundle['sha256'], versions=versions), bundle, coverage, manifest


def bind_media(source, nodes, assets):
    result = deepcopy(source)
    by_id = {r['id']: r for r in result['items']}
    bindings = {}
    for node in nodes:
        if node['location'] == 'ending':
            continue
        asset = assets[node['node_id']]
        for binding in node['bindings']:
            item = by_id[binding['instance_id']]
            if item['item_sha256'] != binding['item_sha256'] or item['scene_id'] != node['scenario_id']:
                raise ValueError('Frozen question binding mismatch')
            if item['task'] == 'T2':
                continue
            if item['task'] not in ('T1', 'T3'):
                raise ValueError('Unexpected offline task')
            bindings.setdefault(item['id'], []).append(deepcopy(asset) | {'evidence_ids': binding['evidence_ids'][:]})
    for item in result['items']:
        if item['task'] == 'T2':
            item.update(public_video=None, media=[], coverage=dict(complete=False, mode='text_only', video_required=False,
                reason='Controlled-history task uses text only; no shared-ending video.'))
        else:
            media = bindings.get(item['id'], [])
            if not media:
                raise ValueError('T1/T3 question has no video: '+item['id'])
            wanted = {t['turn_id'] for t in item['public_text']['input']['history']}
            covered = {e for a in media for e in a['evidence_ids']}
            if wanted != covered:
                raise ValueError('Incomplete T1/T3 history-video coverage: '+item['id'])
            item.update(public_video={**item['public_text'], 'modality': 'text+video'}, media=media,
                coverage=dict(complete=True, covered_evidence_ids=sorted(covered), uncovered_evidence_ids=[],
                    spoken_scope='checkpoint_sentence', full_reply_text_preserved=True,
                    complete_spoken_response=False, state_conditioned=True, human_review='pending'))
    result.update(release=RELEASE, media_readiness=dict(
        required_nodes=len(assets), completed_nodes=len(assets), video_tasks=['T1', 'T3'],
        video_items=sum(i['task'] in ('T1', 'T3') for i in result['items']),
        complete_items=sum(i['task'] in ('T1', 'T3') for i in result['items']),
        text_only_items=sum(i['task'] == 'T2' for i in result['items']),
        scope_note='T1/T3 share short videos by history node; T2 is text only.',
        state_conditioned=True, full_reply_text_preserved=True, human_review='pending'))
    result.pop('dataset_sha256', None)
    result['dataset_sha256'] = digest(result)
    return result


def verified_asset(row):
    directory = ROOT / row['directory']
    state = load(directory / 'provider-state.json')
    receipt = load(directory / 'web-receipt.json')
    qa = directory / 'qa'
    audio = load(qa / 'audio_screen.json')
    sync = load(qa / 'lipsync_screen.json')
    if (state.get('status') != 'downloaded' or sha(directory / 'native.mp4') != state['video_sha256']
        or receipt['source_native_sha256'] != state['video_sha256']
        or sha(directory / 'web.mp4') != receipt['web_sha256'] or not receipt['structural_pass']
        or not audio_evidence_valid(audio) or not sync_evidence_valid(sync)
        or audio['sha256'] != sha(qa / 'speech.wav') or sync['video_sha256'] != sha(qa / 'video.mp4')
        or audio['request_sha256_after'] != sha(qa / 'request.json')
        or sync['request_sha256_after'] != sha(qa / 'request.json')):
        raise ValueError('Native-video checks missing, stale or failed: '+row['node_id'])
    provenance = load(directory / 'provenance.json')
    request_path = ROOT / provenance['baseline_request_path']
    if sha(request_path) != provenance['baseline_request_sha256']:
        raise ValueError('Frozen checkpoint changed')
    original = load(request_path)
    video_sha = receipt['web_sha256']
    return dict(asset_id='video-'+video_sha[:16], node_id=row['node_id'], sha256=video_sha,
        url='/media/'+video_sha+'.mp4', speech_language='en', audio_required=True,
        spoken_text=row['exact_line'], spoken_scope='checkpoint_sentence',
        full_public_response=original['full_public_response'], source_quote=original['checkpoint_line']['source_quote'],
        duration_seconds=receipt['duration_seconds'], media_kind='talking_head',
        human_review='approved_pilot' if row['node_id'].endswith('t1-e30dc6556d3865ac') else 'pending',
        speech_verified=True, provider='seedance', method='native_state_performance_v2',
        spec_sha256=load(qa / 'request.json')['spec_sha256'],
        native_video_sha256=state['video_sha256'], prompt_sha256=sha(directory / 'prompt.en.txt'))


def export(site, source_site, prune=False, online=False):
    site, source_site = Path(site).resolve(), Path(source_site).resolve()
    if site == source_site or not site.is_relative_to(ROOT / 'build'):
        raise ValueError('Use an isolated build checkout')
    manifest = load(OUT / 'manifest.json')
    if manifest['bank_sha256'] != sha(BANK) or len(manifest['nodes']) != 100:
        raise ValueError('Expected current 100-node T1/T3 revision')
    source = gate2.unpack(load(source_site / 'data/research-server.json')['gzip_base64'])
    if source['source_bank_sha256'] != sha(BANK):
        raise ValueError('Question bank mismatch')
    assets = {r['node_id']: verified_asset(r) for r in manifest['nodes']}
    nodes = public_nodes([json.loads(s) for s in BANK.read_text().splitlines() if s.strip()])
    research = bind_media(source, nodes, assets)
    for row in manifest['nodes']:
        asset = assets[row['node_id']]
        gate2.copy_video(site, ROOT / row['directory'] / 'web.mp4', asset['sha256'], asset['url'])
    registry = gate2.unpack(load(source_site / 'data/gate2-review-server.json')['gzip_base64'])
    revised_registry, bundle, coverage, retained = replace_media_reviews(registry, research, site)
    online_manifest = None
    if online:
        revised_registry, bundle, online_coverage, online_manifest = replace_online_reviews(revised_registry, research, site)
        save(OUT / 'online-review-coverage.json', online_coverage)
    history = load(source_site / 'data/research-media-history.json')
    if source['dataset_sha256'] not in {r['dataset_sha256'] for r in history}:
        history.append(media_snapshot(source))
    save(site / 'data/research-media-history.json', history)
    save(site / 'data/research-media-history-server.json', {'gzip_base64': packed(history)})
    save(site / 'data/research-server.json', {'gzip_base64': packed(research)})
    from scripts.build_research_storage import build as build_storage
    save(OUT / 'storage-roundtrip.json', build_storage(site))
    gate2.write_registry(site / 'data/gate2-review-server.json', revised_registry)
    save(OUT / 'gate2-release.json', bundle)
    retired = []
    if prune:
        # User approved deleting former videos. Preserve all research snapshots
        # and annotations; the UI explicitly marks retired historical media.
        keep = {a['sha256']+'.mp4' for a in assets.values()}
        if online_manifest:
            keep.update(r['video_sha256']+'.mp4' for r in online_manifest['requests'])
        # Current online review media remain until their separate replacement.
        for task in bundle['tasks']:
            if task['kind'] != 'media-quality' and task.get('video'):
                url = task['video'].get('url', '')
                if url.startswith('/media/'):
                    keep.add(Path(url).name)
        for path in (site / 'public/media').glob('*.mp4'):
            if path.name not in keep:
                retired.append(dict(file=path.name, sha256=sha(path), bytes=path.stat().st_size))
                path.unlink()
        prior = load(source_site / 'data/retired-media.json') if (source_site / 'data/retired-media.json').exists() else {'files': []}
        save(site / 'data/retired-media.json', dict(files=sorted(set(prior['files']) | {r['file'] for r in retired})))
    summary = dict(release=RELEASE, dataset_sha256=research['dataset_sha256'],
        video_count=len(assets), video_questions=300, text_only_t2=100,
        online_video_count=len(online_manifest['requests']) if online_manifest else 0,
        gate2_sha256=bundle['sha256'], question_hashes_unchanged=True,
        existing_annotation_records_untouched=True, retired_files=retired,
        retired_bytes=sum(r['bytes'] for r in retired), published=False)
    save(OUT / 'release.json', research)
    save(OUT / 'publication-candidate.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='retired_files'}))
    return summary


if __name__ == '__main__':
    p = ArgumentParser()
    p.add_argument('--site', required=True, type=Path)
    p.add_argument('--source-site', default=ROOT / 'web/participant_demo', type=Path)
    p.add_argument('--prune-old-media', action='store_true')
    p.add_argument('--online', action='store_true')
    args = p.parse_args()
    export(args.site, args.source_site, args.prune_old_media, args.online)
