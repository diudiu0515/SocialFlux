import {DatabaseSync, backup} from 'node:sqlite';
import {chmodSync, mkdirSync, renameSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {drizzle} from 'drizzle-orm/d1';
import * as schema from './schema';

const filename = process.env.ANNOTATION_DATABASE;
if (!filename) throw new Error('ANNOTATION_DATABASE must point to persistent storage');
mkdirSync(dirname(filename), {recursive:true, mode:0o700});
export const sqlite = new DatabaseSync(filename);
chmodSync(filename, 0o600);
sqlite.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=10000;
CREATE TABLE IF NOT EXISTS demo_sessions (
 id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, user_id TEXT NOT NULL,
 dataset_sha256 TEXT NOT NULL, release TEXT NOT NULL, reviewer_alias TEXT NOT NULL,
 prior_exposure INTEGER NOT NULL, draft_json TEXT NOT NULL DEFAULT '{}',
 item_hashes_json TEXT NOT NULL, media_reviews_json TEXT NOT NULL DEFAULT '{}',
 media_hashes_json TEXT NOT NULL DEFAULT '{}', assignment_json TEXT NOT NULL DEFAULT '{}',
 workflow_json TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'in_progress', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 submitted_at TEXT, UNIQUE(user_id, dataset_sha256));
CREATE TABLE IF NOT EXISTS annotation_history (
 sequence INTEGER PRIMARY KEY, session_id TEXT NOT NULL, revision INTEGER NOT NULL,
 saved_at TEXT NOT NULL, row_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS migration_sources (source_key TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, imported_at TEXT NOT NULL);
`);
const columns = (sqlite.prepare('PRAGMA table_info(demo_sessions)').all() as any[]).map(x=>x.name);
const snapshot = 'json_object(' + columns.map(k=>`'${k}',new.${k}`).join(',') + ')';
for (const action of ['INSERT', 'UPDATE']) sqlite.exec(`CREATE TRIGGER IF NOT EXISTS annotation_history_${action.toLowerCase()}
 AFTER ${action} ON demo_sessions BEGIN
 INSERT INTO annotation_history(session_id,revision,saved_at,row_json) VALUES(new.id,new.revision,strftime('%Y-%m-%dT%H:%M:%fZ','now'),${snapshot}); END;`);

// The shared annotation store uses Drizzle's D1 interface. This local adapter
// changes storage only; validation, frozen material selection and locks stay shared.
class Statement {
 constructor(private sql:string, private values:any[] = []) {}
 bind(...values:any[]) {return new Statement(this.sql, values);}
 async raw() {const stmt=sqlite.prepare(this.sql);stmt.setReturnArrays(true);return stmt.all(...this.values);}
 async all() {return {results:sqlite.prepare(this.sql).all(...this.values),success:true,meta:{}};}
 async run() {const result=sqlite.prepare(this.sql).run(...this.values);return {results:[],success:true,meta:{changes:Number(result.changes),last_row_id:Number(result.lastInsertRowid)}};}
}
const db = drizzle({prepare:(sql:string)=>new Statement(sql)} as any, {schema});
export const getDb = () => db;
export async function checkpointBackup() {
 const folder=resolve(dirname(filename!), 'snapshots');mkdirSync(folder,{recursive:true,mode:0o700});
 const target=resolve(folder,new Date().toISOString().replaceAll(':','-')+'-'+crypto.randomUUID()+'.sqlite3');
 await backup(sqlite,target+'.tmp');chmodSync(target+'.tmp',0o600);renameSync(target+'.tmp',target);
 return target;
}
