# Pages and annotation persistence

The public Lab and annotation entry must render without a reachable AutoDL backend. The Lab reads a dated aggregate snapshot until the researcher logs in. Individual answers, recovery codes and private plan records are excluded from the public artifact.

`python -m scripts.build_lab_pages` now generates the aggregate snapshot as part of a rebuild. `scripts/build_lab_public_snapshot.py` uses explicit field and table allowlists. The checked-in annotation catalog contains only assignment metadata.

The backend URL must include the AutoDL HTTPS port **8443**. On 2026-10-24, a GitHub-hosted runner received HTTP 401 from that port (expected without credentials); standard port 443 timed out. The deployment workflow also checks Pages CORS preflight without sending credentials.

Login credentials stay in browser memory. Successful login refreshes the Lab and annotation entry. Writes require authentication and a real server response. An unreachable backend is never reported as a successful save. Existing per-session local drafts remain in the browser; server SQLite records, revision receipts and snapshots remain on AutoDL. Migration archives are private and must not be copied into Pages or the public repository.

Verification: all seven Lab views and the annotation entry opened in Chromium with the backend blocked, both in a local preview and on the published Pages URL. This test establishes frontend availability, not end-to-end authenticated save availability for every user network.
