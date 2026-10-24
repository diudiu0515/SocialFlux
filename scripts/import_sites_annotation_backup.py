"""Import verified private Sites records without replacing any saved session."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def import_backup(source, database):
    source, database = Path(source), Path(database)
    value = json.loads(source.read_text())
    if value.get('format') != 'socialflux_sites_migration_v1':
        raise ValueError('Unsupported backup')
    if not database.is_file():
        raise ValueError('Initialize the annotation database before importing')
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    with sqlite3.connect(database, timeout=30) as db:
        db.row_factory = sqlite3.Row
        columns = [r['name'] for r in db.execute('PRAGMA table_info(demo_sessions)')]
        db.execute('BEGIN IMMEDIATE')
        inserted = 0
        for entry in value['records']:
            row = dict(entry['row'])
            row.setdefault('owner_user_id', 'migrated:' + entry['project_id'])
            if set(row) != set(columns):
                raise ValueError('Schema mismatch')
            previous = db.execute('SELECT * FROM demo_sessions WHERE id=?', (row['id'],)).fetchone()
            if previous:
                if dict(previous) != row:
                    raise ValueError('Existing record differs; refusing overwrite')
            else:
                db.execute('INSERT INTO demo_sessions (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', [row[c] for c in columns])
                inserted += 1
            key = entry['project_id'] + ':' + row['id']
            old = db.execute('SELECT source_sha256 FROM migration_sources WHERE source_key=?', (key,)).fetchone()
            if old and old[0] != sha:
                raise ValueError('Source changed after migration')
            db.execute('INSERT OR IGNORE INTO migration_sources VALUES (?,?,?)', (key, sha, datetime.now(timezone.utc).isoformat()))
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed')
        backup = database.with_name('migration-verified.sqlite3')
        if backup.exists():
            raise ValueError('Migration backup already exists; do not overwrite')
        with sqlite3.connect(backup) as dst:
            db.backup(dst)
        backup.chmod(0o600)
    return {'records': len(value['records']), 'inserted': inserted, 'source_sha256': sha,
            'database_integrity': 'ok', 'backup': str(backup)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(import_backup(args.source, args.database)))
