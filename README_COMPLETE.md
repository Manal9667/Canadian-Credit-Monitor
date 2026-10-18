# Canadian Household Credit and Interest-Rate Analysis

A finance research project on Canadian household credit, lending-rate pass-through, and rate-regime context, built on a reproducible data pipeline from public Bank of Canada and Statistics Canada indicators. The project demonstrates a clear research question, quantitative analysis, charts, a written memo, ingestion, data quality checks, dimensional modeling, time-series metrics, SQL analytics, monitoring, and generated reports.

> Scope: these are aggregate economic and banking indicators, not individual loans, borrowers, credit bureau records, delinquency rates, or bank-level customer portfolios. The project makes no causal or credit-risk claims.

## Research Question and Findings

The headline question is how Bank of Canada policy-rate changes showed up in posted and effective lending rates, and how those rate regimes coincided with household-credit growth and debt indicators. The finance memo is in `reports/research_memo.md`; reproducible research outputs are in `reports/*.csv`, with charts in `reports/figures/`.

Selected verified findings from the current processed run:

- Latest prime-policy spread: `2.20` percentage points over 2009-04-22 to 2026-10-07 (`N=912`), using `V80691311` and `V39079`.
- Latest consumer effective-rate spread over policy: `5.67` percentage points over 2016-07-01 to 2026-07-01 (`N=121`), using `V122667809` and `V39079`.
- Average consumer-credit YoY growth during hiking regimes: `5.8099%` over 2017-08-01 to 2024-05-01 (`N=52`), using `V122667758` and `V39079`.
- Average consumer-credit YoY growth during stable regimes: `3.2329%` (`N=20`); during easing regimes: `3.5333%` (`N=37`). These are descriptive associations, not policy effects.
- Largest tracked household-credit component: uninsured mortgages at `54.4947%` of tracked components on 2026-07-01. This is not total household-debt composition.
- Mechanical +100 bp consumer-credit sensitivity: `7,045.82` million CAD of annual interest as of 2026-07-01, using `V122667758` and `V122667809`. This ignores repricing schedules, defaults, credit mix, balances paid in full, and borrower behaviour.

## Verified Status

The repository contains Python ingestion and analytics code, raw source snapshots, processed CSV outputs, SQL schemas and views, Power Query scripts, a static browser dashboard in `frontend/index.html`, and Markdown design notes. It does **not** contain a Power BI `.pbix`, API, database migration framework, or deployed service. Power BI dashboard descriptions in older project notes are specifications, not implemented `.pbix` deliverables.

The snapshots selected by `latest.json` were retrieved on 2026-10-13 by both sources. `data/processed/pipeline_metadata.json` records the selected snapshot identifiers and retrieval times.

- Bank of Canada: 16 of 16 configured series succeeded; 11,465 observations.
- Statistics Canada: four series from table `38-10-0238-01` (WDS product ID `38100238`); 584 observations.
- Latest transformed output: 20 series and 12,049 observations, spanning 1990-01-01 to 2026-10-12.
- Most recent Bank of Canada observations are 2026-10-12 daily, 2026-10-07 weekly, and 2026-07-01 monthly. Statistics Canada quarterly observations end at 2026-04-01; the official table release metadata is 2026-09-11.
- The 2026-10-12 Statistics Canada HTTP 403 was not reproduced on 2026-10-13. Both the configured WDS integration and official static CSV ZIP succeeded, and all four configured series passed preflight. The earlier failure's root cause is not known.
- Validation from the 2026-10-18 offline run: Bank of Canada 9 PASS / 1 WARN / 0 FAIL, with five schedule-stale series; Statistics Canada 10 PASS / 0 WARN / 0 FAIL. Freshness is schedule-based and recorded per series in `data/processed/series_freshness.csv`.

These figures describe the checked-in snapshot, not a promise that public sources remain current. The pipeline records refresh provenance in `data/processed/pipeline_metadata.json` after transformation.

## Architecture

```text
Bank of Canada Valet API       Statistics Canada WDS
            |                            |
            +---- immutable timestamped raw snapshots ----+
                         latest.json pointer              |
                                  |                        |
                     validation.engine + validators       |
                                  |                        |
                strict schema/date/key/value checks        |
                                  |                        |
             transform -> dimensions + observation fact   |
                       + pipeline provenance JSON         |
                                  |
                  +---------------+----------------+
                  |               |                |
             Python metrics   monitoring      PostgreSQL load
                  |               |                |
                  +---------- CSV reports --------+
                                  |
              DuckDB executes shared SQL views locally
                                       |
                  Static dashboard reads processed CSV/JSON
```

The observation fact grain is one row per `(series_id, observation_date)`. The dimensions are one row per source, series, or calendar date. Raw snapshots are immutable; ingestion promotes `latest.json` only after complete-series and candidate validation checks pass, using an atomic pointer replacement. Transformation independently rejects snapshots whose manifest reports failures or schema warnings, malformed dates/numbers, future dates, duplicate keys, or missing series metadata. Metrics preserve genuine missing values rather than replacing them with zero.

## Sources and Access

| Source | Data used | Access and notes |
| --- | --- | --- |
| Bank of Canada Valet API | Policy and posted rates, selected chartered-bank credit balances and effective rates | Public JSON API; no key required. Source terms: [Bank of Canada terms](https://www.bankofcanada.ca/terms/). |
| Statistics Canada WDS | Household credit market debt, consumer credit, mortgage liabilities, and debt-to-income indicator from product `38100238` | Public table download through WDS; no key required. Statistics Canada Open Licence applies. Product IDs and category filters are in `config/series_config.json`. |

The curated Bank of Canada series IDs, units, declared frequencies, and categories are in `config/series_config.json`. Statistics Canada row filters are descriptor-based and the source vector IDs returned with the snapshot are preserved in series metadata. Review that metadata when the upstream table changes.

## Data Model and Metrics

PostgreSQL DDL is under `sql/`. The `credit` schema contains:

- `dim_source`: one row per data provider.
- `dim_series`: one row per source series, including category, unit, measure type, and frequency.
- `dim_date`: one row per calendar date in the transformed range; `date_key` is `YYYYMMDD`.
- `fact_observations`: one numeric observation per series/date; unique `(series_key, date_key)`. `value` may be null for a source-suppressed observation.

Python outputs and definitions:

- `metrics_timeseries.csv`: previous-observation change, percentage change, trailing 3/12 observation means, and eligible YoY comparisons.
- `metrics_summary.csv`: latest value and date, changes, full-history min/max/mean/sample standard deviation, z-score, percentile rank, and observation count per series.
- `monitoring_alerts.csv` and `monitoring_history.csv`: transparent rolling z-score, percentage-change, and historical-tail flags. Alerts are investigation prompts, not predictions or risk classifications.
- `reports/automated_summary.md` and `.csv`: on-demand summary of latest changes and current alerts.

Percent change is `100 * (current - prior) / abs(prior)`; a zero prior value yields null. YoY is matched to the **exact calendar date one year earlier** for monthly and quarterly series; absent dates remain null. Daily and weekly YoY is not produced. Rolling windows count observations, not elapsed months. The SQL `vw_yoy_change` uses the same exact-date rule.

The SQL `vw_category_share` excludes the consumer-credit aggregate because its component balances are also present. Its denominator is explicitly named `tracked_component_total`; the resulting shares are not total household-debt composition. The rate-spread view joins series on exact observation dates and does not interpolate or carry values forward.

More detailed calculation and alert thresholds are in [documentation/methodology.md](documentation/methodology.md).

## Setup (Windows PowerShell)

Use CPython 3.12-3.14. The repository defaults to 3.14 in `.python-version`. Runtime and development dependencies are pinned in `requirements.txt` and `requirements-dev.txt`.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

PostgreSQL is optional. For `.env` file support and the database driver, install `requirements-postgres.txt`; set `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`. Process environment variables take precedence. Never commit real credentials. CSV ingestion, transformation, metrics, reports, tests, and DuckDB do not require database credentials.

### Browser Dashboard

Build a self-contained static dashboard bundle, then serve that folder locally:

```powershell
python -m python.reporting.prepare_dashboard
python -m http.server 8000 --directory frontend/site
```

Open `http://localhost:8000/`. The dashboard reads generated data under `frontend/site/data/processed/`. Its primary views are “What is happening?”, “What changed?”, and “What could happen?”, with detailed credit, rates, and monitoring views. It is a local static reporting UI, not a Power BI report or deployed service.

## Reproduce the Pipeline

Run from the repository root. Ingestion makes live public network requests and writes new immutable raw snapshots.

```powershell
python -m python.ingestion.bank_of_canada
python -m python.ingestion.statistics_canada
python -m python.validation.engine
python -m python.transformation.transform
python -m python.analytics.metrics
python -m python.analytics.anomaly_detection
python -m python.reporting.reporting_summary
python -m python.db.duckdb_runner
python -m python.analysis.household_credit_research
python -m python.analysis.run_credit_extensions
python -m python.analysis.run_interest_cost_scenarios
python -m python.reporting.prepare_dashboard
```

The aggregate validation command writes `data/processed/validation_results.csv` and `documentation/validation_report.md`; hard validation failures return a nonzero exit code. Warnings, including staleness, are reported but do not fail that gate. Transformation independently blocks a latest snapshot marked incomplete; it does not silently fall back to an older snapshot.

For an offline rerun using the selected raw snapshots, start at validation and skip both ingestion commands. Tests and CI use mocked or deterministic data and do not call live sources.

### Reproducible Metric Query

After the steps above, run this from the project root to inspect the latest credit-card balance and its exact-year comparison using the SQL view:

```powershell
@'
from python.db.duckdb_runner import build_connection, query

connection = build_connection()
sql = """
SELECT observation_date, value, value_year_ago, yoy_pct_change
FROM credit.vw_yoy_change
WHERE series_id = 'V122667761'
ORDER BY observation_date DESC
LIMIT 1
"""
print(query(connection, sql).to_string(index=False))
connection.close()
'@ | python -
```

The query uses the Bank of Canada credit-card balance series. Against the currently selected snapshot it returned 2026-07-01, value `107880.0`, prior-year value `102497.0`, and YoY change `5.2519%`. Its result is computed from the selected raw snapshot and will change as the data refreshes.

## PostgreSQL (Optional)

Create the database and user outside this project, configure the `PG*` variables, then run:

```powershell
python -m python.db.load_postgres
```

The loader creates the `credit` schema, creates tables and indexes if absent, truncates and reloads all processed tables inside one transaction, then creates the views. A failed load rolls back. The table definitions are initialization DDL, not versioned migrations; for a new schema or changed columns, use a new database and reload. PostgreSQL was not available/configured during the local verification described below, so this integration path remains unverified here.

DuckDB is the local SQL verification path. It loads processed CSVs into an in-memory database and executes the shared `sql/views.sql`; it is not a substitute for PostgreSQL integration testing.

## Tests and Checks

```powershell
python -m ruff check python tests
python -m unittest discover -v
python -m compileall -q python tests
python -m python.validation.engine
python -m python.db.duckdb_runner
```

The 38 tests cover calendar alignment, duplicate keys, malformed dates and values, zero-versus-missing source values, mocked ingestion failures, snapshot preservation, freshness boundaries, SQL views, regime and lag calculations, interest-cost formulas, and local README links. The fixtures are in-memory or temporary files; no full-history download or live endpoint is needed. GitHub Actions runs Ruff, the unit suite, validation, transformation, DuckDB, research outputs, and dashboard build on Python 3.12 and 3.14 for pull requests.

## Prioritized Audit Checklist

- **P0, presentation claims:** A static browser dashboard now exists, but no Power BI file, API, or deployed service exists. Dashboard pages and DAX counts in older notes remain design claims, not executable Power BI artifacts.
- **P1, metric correctness (fixed):** Python YoY previously used row offsets and could compare mismatched periods across gaps. It now matches exact calendar dates and has a missing-period regression test.
- **P1, data integrity (fixed):** Transformation previously dropped invalid dates and coerced malformed values to null. It now rejects malformed schema/data, duplicate keys, future dates, and incomplete latest manifests; null source values remain null.
- **P1, SQL metric correctness (fixed):** The category-share denominator previously included both a consumer-credit total and its components. The aggregate is excluded and the output is named as a tracked-component share.
- **P1, reporting workflow (fixed):** Reporting referenced a nonexistent metrics filename and obsolete column names; it now consumes actual outputs and writes UTF-8 on Windows.
- **P1, database safety (improved):** PostgreSQL DDL previously dropped all tables on every load. Reload now truncates and reloads transactionally. There is no migration framework, and PostgreSQL integration has not been exercised here.
- **P2, execution reproducibility (fixed):** The documented aggregate validator was a no-op, DuckDB was missing from requirements, and `.env.example` advertised unsupported settings. The CLI, dependency, and supported PostgreSQL environment template now match the implementation.
- **P2, freshness (corrected):** Freshness is evaluated against expected source release schedules and grace windows, with per-series provenance output. In the 2026-10-18 validation run, five Bank of Canada series were stale; Statistics Canada passed its configured schedule check.

## Verification Performed

On Windows with a newly created temporary Python 3.14.4 virtual environment:

- `python -m pip install -r requirements-dev.txt`: passed in the fresh environment.
- `python -m ruff check python tests`: passed.
- `python -m unittest discover -v`: 38 tests passed.
- `python -m compileall -q python tests`: passed.
- No live ingestion was run during this audit; the selected snapshots were retrieved on 2026-10-13.
- Transform: 20 series, 12,049 observations through 2026-10-12.
- Metrics: 12,049 timeseries rows and 20 summary rows.
- Monitoring: 20 series scanned; 10 latest-period alerts.
- Reporting: generated Markdown and CSV successfully after explicit UTF-8 handling.
- DuckDB runner: all 9 SQL views queried against processed outputs.
- Browser UI: locally served and checked at desktop/mobile widths; navigation, series filtering, period controls, chart rendering, KPIs, and freshness warning verified.
- Aggregate validation: Bank of Canada 9 PASS / 1 WARN / 0 FAIL; Statistics Canada 10 PASS / 0 WARN / 0 FAIL.
- Freshness metadata: five Bank of Canada series are stale in the 2026-10-18 validation, while Statistics Canada is current. Observation date, snapshot retrieval, processing time, and expected next publication are separate fields.
- Research outputs were regenerated. Prime-policy spread was 2.20 pp (N=912); consumer effective-rate spread was 5.67 pp (N=121); the +100 bp consumer-credit scenario was CA$7,045.82 million.
- The documented Python 3.12 install could not be run locally because Python 3.12 was not installed and provisioning it failed TLS certificate validation. Python 3.14.4 was installed and tested in a fresh virtual environment. CI is configured to exercise both versions but was not run on GitHub during this audit.

The PostgreSQL driver/database integration remains untested; local SQL verification uses DuckDB. No public dashboard has been deployed.

## Limitations and Next Steps

- Data is aggregate, public, and revised by providers; no revision history is modeled beyond immutable retrieval snapshots.
- Source frequencies differ. A comparison is valid only where series definitions, units, periods, and exact dates align.
- Current monitoring thresholds are simple statistical screens and can flag ordinary structural changes.
- PostgreSQL DDL has no migration history; database integration needs testing on a configured server.
- The static browser dashboard is available locally; Power BI remains a presentation design only. The `.pq` files and documentation do not constitute a `.pbix` dashboard.
- There is no scheduler, email delivery, deployed service, or real-time pipeline.
- Before publishing recruiter-facing quantitative claims, refresh the snapshots, run validation, and quote only the resulting metrics and dates.
