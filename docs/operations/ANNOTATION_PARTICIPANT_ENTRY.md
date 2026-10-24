# Participant entry without a researcher account

Participants open `/annotation/` directly. The browser generates a stable random anonymous alias and a cryptographically random recovery code for each session. The recovery code is stored before sending the start request, so a lost response does not lose the ability to recover a committed session. Existing aliases and recovery codes still work.

The Python gateway permits only the named participant routes. SQLite session lookup still uses the hash of the recovery code. Research `/api/lab` remains authenticated. Media requires a recovery code for an existing session. No cross-person listing or export endpoint is added. Public static catalog metadata contains no answers or recovery codes.

Validation: isolated copy of the database, start/draft/recover/export without Basic authentication; wrong recovery codes cannot access the session; wrong alias recovery is rejected; admin API returns 401; media requires a valid session. Chromium completed the start flow with an automatically generated alias and displayed the recovery code without a Lab login. Production session count remained 5 and SQLite integrity was OK. Public AutoDL connectivity remains a separate dependency: no client reports successful saving without a server response.
