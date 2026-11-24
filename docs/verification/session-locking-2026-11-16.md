# Session-locking integration verification — November 16, 2026

Refs #42. Verified against develop `2cbda83`, including merged generator #105 and completion #107.

## Results

- Disposable PostgreSQL 16 database: all **76 study tests pass**, including the two new API/generator lifecycle tests.
- SQLite: the two new lifecycle tests pass.
- Migration drift and Git diff checks pass; no application behavior changes or new migrations were needed.
- Both assignment and exam sessions were generated through the real endpoint, locked through PATCH, regenerated, manually rescheduled, regenerated again, unlocked, and regenerated again.
- A locked session retained its primary key, lock, and exact time through regeneration. A manual move kept the lock, and subsequent regeneration preserved the moved time. Calendar GET reflected the lock. Explicit unlock allowed regeneration to replace that session and schedule the workload afresh.
- Existing study tests also cover other-account isolation, conflicts/override, completion preservation, class-meeting conflicts, deadline ordering, and invalid generation rollback.

The new lifecycle checks run on SQLite CI and on PostgreSQL when the test database is configured for that backend. Running the full study suite on PostgreSQL exercised the actual `select_for_update(of=('self',))` query, including sessions backed by nullable assignment/exam joins.

## Remaining deployment check

An authenticated browser visit to staging on November 16 showed the older calendar without a Generate study plan control. Imported class meetings were visible and there were zero study sessions in the current week. The deployed generator lifecycle could therefore not be exercised. No staging or production account data was changed during this verification, and no deployment was performed.

Keep #42 open until the merged generator build is deployed to staging and a teammate verifies:

1. Using a disposable QA account/course, create an assignment or exam with future deadline/start and workload, plus availability.
2. Generate sessions, lock one, and record its time.
3. Generate again: verify that session remains locked at exactly the same time and other generated sessions avoid it.
4. Reschedule the locked session, handling warnings if needed; refresh and regenerate to confirm the new time and lock persist.
5. Unlock it; regenerate and verify it becomes replaceable. Refresh the calendar.
6. Record the staging build and result before closing #42. Do not use an account with an important existing study plan, since generation replaces unlocked upcoming sessions.

Prepared with Codex. Local verification used isolated test databases, not RDS.
