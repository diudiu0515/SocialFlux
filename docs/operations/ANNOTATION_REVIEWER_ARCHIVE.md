# Private annotation archives by reviewer

Run `python scripts/archive_annotation_by_reviewer.py --receipts data/sites_annotation/receipts --output data/sites_annotation/reviewer_archive` to derive a private archive from durable receipts. Supervisor runs this with `--watch` every 60 seconds. This task never writes to the annotation database or source receipts.

Open `data/sites_annotation/reviewer_archive/index.html` locally to browse saved answers and all archived revisions grouped by reviewer alias and session. `summary.csv` lists sessions, releases, statuses and revision counts. Each session also has `latest.json` and `versions/*.json`. Paths use hashes rather than user-supplied names. Same-alias sessions remain separate; aliases are labels, not verified identities. Assign each person a unique, stable alias.

These files contain private answers. They must not enter GitHub Pages or the public repository. The current web Human/GT view is an aggregate view, not this per-person archive. Downloaded copies are snapshots and do not update automatically. Only confirmed server saves appear here; browser-only drafts do not. This is a derived archive on the same server, not an off-server disaster-recovery backup.

Validation covers preservation of multiple sessions and revisions, HTML escaping, repeated execution, and refusal to overwrite conflicting archived versions. The live archive was opened in Chromium with no script errors; the archive watcher runs independently of the annotation API.
