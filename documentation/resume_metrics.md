# Verified Project Resume Notes

Use only claims supported by the current implementation and rerun outputs. Dataset counts below describe the selected Bank of Canada and Statistics Canada snapshots retrieved 2026-10-13; they can change after ingestion.

## Defensible Resume Bullets

- Built a reproducible Python data pipeline that ingests public Bank of Canada Valet and Statistics Canada WDS data into timestamped raw snapshots, validates source schemas and observation keys, and transforms observations into a dimensional CSV model with refresh provenance.
- Implemented Python time-series metrics and explainable anomaly monitoring for public Canadian banking and household-credit indicators; the selected snapshots transform to 20 series and 12,049 observations, with all nine SQL analytical views queried locally using DuckDB.
- Added 18 deterministic tests for calendar-aligned year-over-year metrics, source parsing, duplicate/malformed input rejection, failure-safe snapshot promotion, freshness schedules, research calculations, and SQL share calculations; generated source-aware Markdown, CSV, and chart outputs from the pipeline.

## Evidence and Limits

- Last local validation: 20 PASS, 0 WARN, 0 FAIL. All 20 series are inside documented frequency-aware freshness windows. The prior fixed-age rule's 11 monthly flags were false positives. A Statistics Canada HTTP 403 on 2026-10-12 was not reproduced on 2026-10-13; its root cause remains unknown.
- The SQL file defines 9 analytical views, all queried locally. Selected behavior is covered by 18 tests; broad coverage is not measured.
- The loader has transactional PostgreSQL logic, but no PostgreSQL server was available for integration verification.
- Power BI assets are specifications and Power Query scripts only. There is no `.pbix`, deployed dashboard, or implemented DAX measure library. The static dashboard is locally prepared for later deployment but has not been published.
- Do not claim dashboard delivery, query latency, throughput, automated schedules, database load success, or 50,000+ records based on this repository's current checked-in data.

## Interview Framing

Describe this as an in-progress engineering portfolio project using public macro/financial indicators. Be explicit that the observations are aggregate and are not individual borrower or loan records. Distinguish source refresh time from observation dates, and explain that a statistical alert is a prompt for review rather than a risk classification or causal conclusion.
