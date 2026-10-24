# Portable annotation for the GitHub Pages Lab

The frontend runs on GitHub Pages. Research APIs and this annotation service run
on the owner's existing AutoDL server. No ChatGPT Sites requests or login are
required. The server must remain online to read or save records.

The implementation carries forward the annotation components, versioned
materials and workflow checks from Lab source commit
`8d1f5ebbd80e1fcc9aac0d7213c774c6ae613e4b`. Private frozen bundles in `data/`,
the server build, database, recovery codes and media never enter the public
Pages artifact or public Git repository.

## Storage and recovery

- Persistent database: `data/sites_annotation/annotation.sqlite3`.
- SQLite uses WAL, full synchronous commits, revision checks and transactional
  history triggers. A saved response is returned after the database write,
  immutable JSON receipt and consistent SQLite snapshot complete.
- Receipts: `data/sites_annotation/receipts/<session>/<revision>.json`.
- Database snapshots: `data/sites_annotation/snapshots/`.
- Original cloud row projections, verified material bindings, and pre-migration
  server backups: `data/migrations/20261024-pages-sites/`.
- Recovery uses the original anonymous alias and recovery code. The hashed code
  and frozen dataset binding are preserved. New browser credentials are never
  written to a URL or to the GitHub repository.
- Existing Python human-summary validation imports compatible saved receipts;
  individual proposals remain distinct from agreed ground truth.

Snapshots protect against accidental overwrites and permit restore testing. They
are on the same server disk; they are not an independent off-server disaster
backup. Keep a separate downloaded copy before deleting the server or disk.

## Build and run

Use Node 22.13 or later. Install the dependencies from `package.json`, restore
the private frozen `data/` bundle and font assets, then run `node build.mjs`.
The static client appears in `dist/client`; `scripts/build_lab_pages.py`
adds the backend origin and shared login adapter. Only that client is published.

`configs/lab.supervisord.conf` starts the private annotation service on loopback
port 6067 and the authenticated Pages-compatible Lab API on port 6006.
`scripts/serve_pages_lab.py` accepts only the configured Pages origin and
forwards authenticated annotation calls using an internal proxy secret.
The ordinary 8000 research service remains separate.

To restore, stop only `socialflux-annotation-storage`, restore a verified
snapshot to a new database path, run `PRAGMA integrity_check` and compare saved
session revisions, then update the configured database path and restart.
Do not overwrite the only copy of a live database or discard WAL files.

## GitHub Pages deployment

The `lab-independent-hosting-20261022` branch publishes the checked-in `pages/`
artifact through GitHub Actions. GitHub repository **Settings → Pages → Source**
must be **GitHub Actions**. The GitHub connector used in this migration can push
source but cannot change that repository setting.

The artifact contains Lab's seven views and `/annotation/`. The expected address
is `https://diudiu0515.github.io/SocialFlux/lab/`; it is live only after the Pages
deployment succeeds. The server API address is public configuration, while the
Lab password and all annotation records remain private.
