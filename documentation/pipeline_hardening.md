# Pipeline reliability and source health

## Refresh behavior

The two source clients continue to write immutable raw snapshots and move the
existing `latest.json` pointer only after candidate validation succeeds. Snapshot
names now include microseconds. Each new manifest records the source series,
table or vector identifiers, UTC retrieval time, row counts, validation summary,
and SHA-256 checksums for the normalized observation and metadata CSV files.
The transform verifies a selected snapshot's source, row count, observation
keys, series identifiers and any recorded checksums before using it. Both
configured sources are required; a missing source stops the transform instead
of publishing incomplete replacement tables.

Bank of Canada and Statistics Canada HTTP clients use the configured timeout,
with hard bounds of 1–120 seconds. Retry attempts are capped at five and
backoff at 30 seconds per step. Network errors, HTTP 429/5xx, and a damaged
downloaded ZIP may retry. Permanent HTTP errors (including 4xx other than 429),
malformed JSON, bad WDS status, and schema/semantic failures do not retry.
Requests remain sequential, which keeps request volume modest; neither client
implements a provider-specific token bucket or adaptive rate limiter.

The latest ingestion attempt is separately recorded at
`data/raw/<source>/last_refresh.json`. A failed attempt leaves the last valid
snapshot pointer untouched, but sets source health to `FAILED` until a later
successful refresh. In `data/processed/source_health.csv`, `CURRENT` means all
series pass configured schedule windows and no validation warning exists;
`STALE` means at least one series is beyond its schedule plus grace window;
`PARTIAL` means validation emitted warnings or a manifest indicates an
incomplete source; `FAILED` means the most recent refresh failed or no selected
snapshot is available. `UNKNOWN` means there is no configured schedule. Source
freshness is cadence-based, not determined from retrieval age alone. Projection
dates remain estimates, not publication guarantees.

## Safe output publication

Transformation tables and metadata, validation reports, metrics, monitoring
outputs, management reports, and the static dashboard bundle are staged before
publication. Replacement errors roll back already replaced files to their
previous versions. This protects against writer errors and ordinary process
exceptions while preserving existing flat-file locations used by DuckDB and
the dashboard.

The flat-file layout cannot provide a single filesystem transaction across
multiple paths. A sudden power loss or forced process termination during the
brief multi-file replacement window may leave backup files or a mixed set of
published files. A versioned output directory with one atomic generation
pointer would be needed for crash-atomic publication; this was not introduced
because it would require changing existing CSV consumers and dashboard paths.
Raw snapshot directories can also contain an unselected partial folder after a
process interruption; the selected pointer still references the last validated
snapshot.

## Checks and known limits

The selected source observations are checked for required normalized columns,
unexpected columns, parseable dates, numeric values, expected series coverage,
duplicate series/date keys, missing values, cadence gaps, unit consistency,
plausible ranges, and schedule-based freshness. StatCan source-table downloads
preserve official table/vector identifiers and validate the required `REF_DATE`
and `VALUE` columns plus each configured descriptor match. Provider tables may
contain additional dimension columns, so these are not rejected wholesale.

Live ingestion was not run as part of local verification; the selected raw
snapshots are those already in the repository. The tests use deterministic
fixtures and mocked source failures. Source freshness and failed-refresh state
are visible in `source_health.csv` and the dashboard warning banner. A failure
does not rewrite the selected raw data, metrics or analytical reports. Validation
publishes a failed health record while retaining the prior validation report
when a required source snapshot is missing.

PostgreSQL loading remains a separate optional path. The DuckDB CSV-backed views
were exercised locally; PostgreSQL integration was not part of this hardening
check.
