# Dataset and provenance audit

No external dataset is included or required. LockLens uses two evidence sources:

1. Reproducible built-in scenario definitions in `backend/app/lab/library.py`. They seed synthetic tables and execute real PostgreSQL sessions; they are test fixtures, not observations from a public publisher.
2. Runtime PostgreSQL evidence: execution events, SQLSTATE errors, final-state/invariant probes, and sampled `pg_locks` data. These records are created during each experiment and stored in the metadata database.

Runtime evidence can be incomplete: lock data is sampled at `LOCK_POLL_INTERVAL_MS`, and cancellation/connection loss can truncate observation. No missing evidence is interpreted as proof that an anomaly did not occur. There are no data downloads, licenses, preprocessing pipelines, or ML training datasets to document.
