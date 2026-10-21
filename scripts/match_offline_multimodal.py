"""Refresh only derived offline media pairs against the currently published bank."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from offline.choice_builder import load, save, sha
from offline.choice_media import ROOT, pair_assets

DERIVED = ('paired.items.jsonl', 'paired.public.jsonl', 'media.json', 'pairing_report.json')


def refresh(bank, manifest, frame_root):
    bank = Path(bank)
    raw = (bank / 'items.jsonl').read_bytes()
    items = [json.loads(line) for line in raw.splitlines() if line.strip()]
    with tempfile.TemporaryDirectory(prefix='offline-media-') as directory:
        stage = Path(directory)
        report = pair_assets(items, manifest, stage, frame_root=frame_root)
        report['items_sha256'] = sha(bank / 'items.jsonl')
        save(stage / 'pairing_report.json', report)
        previous_manifest = load(bank / 'manifest.json')
        previous_manifest.update(modality_pairs=report['logical_pairs'],
                                 media_missing=len(items) - report['logical_pairs'],
                                 media_pairing_report_sha256=sha(stage / 'pairing_report.json'))
        save(stage / 'manifest.json', previous_manifest)
        if (bank / 'items.jsonl').read_bytes() != raw:
            raise ValueError('question bank changed during media matching; retry against the new release')
        # Preserve the previous derived bundle; never regenerate questions or oracle references.
        previous = bank / 'media.json'
        if previous.exists():
            backup = ROOT / 'data/offline_media_backups' / (bank.name + '-' + sha(previous))
            backup.mkdir(parents=True, exist_ok=True)
            for name in (*DERIVED, 'manifest.json'):
                if (bank / name).exists() and not (backup / name).exists():
                    shutil.copyfile(bank / name, backup / name)
        for name in (*DERIVED, 'manifest.json'):
            target = bank / (name + '.matching')
            shutil.copyfile(stage / name, target)
            target.replace(bank / name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', type=Path, default=ROOT / 'tasks/examples/offline_scenarios_v2')
    parser.add_argument('--manifest', type=Path, default=ROOT /
                        'data/gpt50/experiment/multimodal_delivery_v1/online_multimodal/manifest.json')
    parser.add_argument('--frame-root', type=Path, default=ROOT / 'data/offline_multimodal_frames')
    args = parser.parse_args()
    report = refresh(args.bank, args.manifest, args.frame_root)
    print(json.dumps({k: report[k] for k in ('input_item_count', 'logical_pairs', 'variants',
                                            'unique_videos', 'paired_by_task', 'coverage_counts')},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
