# Canadian Household Credit & Interest-Rate Analysis

This project turns public Canadian interest-rate and household-credit data into reproducible financial indicators, regime comparisons, and an auditable interest-cost scenario. It is designed to answer three analyst questions: **What is happening? What changed across rate regimes? What could a rate shock mean under explicit repricing assumptions?**

<img width="1886" height="952" alt="Screenshot (83)" src="https://github.com/user-attachments/assets/ea4df03f-0376-4968-bc5a-bd60967291b5" />

**Live Dashboard:** https://canadian-credit-monitor.vercel.app/

## Verified findings in the current data snapshot

The selected source snapshots were retrieved on 2026-10-13; the current processed run contains **20 series and 12,049 observations** through 2026-10-12. Research outputs and provenance are under `reports/` and `data/processed/`.

- The prime lending rate was **4.45%** and the policy rate **2.25%** on 2026-10-07, a **2.20 percentage-point spread** across 912 exact-date weekly observations.
- The effective consumer-credit rate was **7.92%** on 2026-07-01. Its spread over the same-month average policy rate was **5.67 percentage points** (`N=121`).
- Mean consumer-credit year-over-year growth was **5.81% hiking** (`N=52`, Aug 2017–May 2024), **3.23% stable** (`N=20`, Jul 2017–Jul 2024), and **3.53% easing** (`N=37`, Mar 2020–Jul 2026). The easing HAC and 12-month block-bootstrap 95% intervals both span zero; these descriptive comparisons do not establish a policy effect.
- The observed chartered-bank consumer-credit balance was **CAD 704,582 million** on 2026-07-01. A +100 bp full-balance, immediate-repricing mechanical sensitivity is **CAD 7,045.82 million per year**. This is an arithmetic scenario, not a forecast.

These numbers are reproducible from the selected raw snapshots and generated analysis files. Providers can revise observations, and later snapshots can change the results. The data freshness section below records a warning in the current validation run.

## How the project works

```text
Bank of Canada Valet API ─┐
                          ├─> timestamped source snapshots ─> validation
Statistics Canada WDS ────┘                                      │
                                               dimensional CSV model
                                                        │
                              ┌─────────────────────────┼──────────────────────┐
                              v                         v                      v
                      Python metrics            DuckDB SQL views       research outputs
                              └─────────────────────────┼──────────────────────┘
                                                        v
                                              static dashboard bundle
```

The Bank of Canada client reads configured Valet series; the Statistics Canada client reads table 38-10-0238-01 through WDS. Snapshot manifests retain source identifiers, retrieval times, row counts, and checksums. Preflight and transformation checks reject incomplete snapshots and malformed or duplicate observations before derived outputs are published. Python and the shared `sql/views.sql` definitions produce nine analytical DuckDB views. Live ingestion is separate from offline processing.

The interest-cost engine is implemented in `python/analysis/interest_cost_scenarios.py` and mirrored in `frontend/interest_cost_engine.js`. The dashboard calls the calculation layer; it does not upload or save user inputs.

## Reproduce the results

### Environment

The repository supports **CPython 3.12–3.14**. `.python-version` selects 3.14 as the default. Runtime dependencies are pinned in `requirements.txt`; `requirements-dev.txt` adds Ruff. No database server or API key is needed for the offline pipeline, DuckDB models, tests, or dashboard.

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

macOS/Linux (install Python 3.14 first):

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

PostgreSQL loading is optional. To load values from a local `.env` file, install `requirements-postgres.txt`, copy `.env.example` to `.env`, and set `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`. Process environment variables take precedence. Do not commit real credentials. A running PostgreSQL server is required only for `python -m python.db.load_postgres`.

### Tests and lint

```bash
python -m ruff check python tests
python -m unittest discover -v
```

The 38 unit tests use small in-memory or temporary-directory fixtures and mocked HTTP responses; they do not call live providers or require the full historical data. GitHub Actions runs these checks and the offline data pipeline on Python 3.12 and 3.14 for pull requests.

### Offline data and SQL reproduction

Run from the repository root. These steps use the selected raw snapshots, not live services:

```bash
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

The headline rate spreads and regime results are written to `reports/key_findings.csv`, `reports/rate_pass_through.csv`, `reports/credit_regime_uncertainty.csv`, and `reports/credit_regime_sensitivity.csv`. The SQL runner loads the four processed dimensional CSVs into an in-memory DuckDB database and executes the nine views in `sql/views.sql`. A reproduced credit-card balance YoY result is available from `credit.vw_yoy_change` for series `V122667761`; the selected snapshot returns 2026-07-01, CAD 107,880 million, versus CAD 102,497 million a year earlier (5.2519%).

To reproduce that credit-card result directly after the offline pipeline:

```powershell
@'
from python.db.duckdb_runner import build_connection, query

connection = build_connection()
try:
    result = query(connection, """
        SELECT observation_date, value, value_year_ago, yoy_pct_change
        FROM credit.vw_yoy_change
        WHERE series_id = 'V122667761'
        ORDER BY observation_date DESC
        LIMIT 1
    """)
    print(result.to_string(index=False))
finally:
    connection.close()
'@ | python -
```

### Refresh public data

Refresh is not needed to run tests or reproduce the selected snapshot. These commands make live requests and write new timestamped raw snapshots:

```bash
python -m python.ingestion.bank_of_canada
python -m python.ingestion.statistics_canada
```

After refresh, run validation and the offline pipeline above. A failed or partial refresh leaves the last selected valid snapshot pointer intact. Network errors, provider rate limits, schema changes, and source outages can stop acquisition; inspect `data/raw/<source>/last_refresh.json` and `documentation/validation_report.md` for status.

## Dashboard

Build and serve the generated static site from the repository root:

```bash
python -m python.reporting.prepare_dashboard
python -m http.server 8000 --directory frontend/site
```

Open `http://localhost:8000/`. The first three views are **What is happening?**, **What changed?**, and **What could happen?** Detailed credit, rate, and monitoring views remain available. The bundle reads generated CSV/JSON files under `frontend/site/data/processed/`; `frontend/site/` is disposable build output and ignored by Git. No API server, cloud account, or database is involved.

## Data coverage and limitations

The latest processed run spans 1990-01-01 to 2026-10-12. The Bank snapshot contains 16 series (11,465 observations), retrieved 2026-10-13; the Statistics Canada snapshot contains four series (584 observations), retrieved 2026-10-13, with quarterly observations through 2026-04. In the 2026-10-18 validation run, Bank of Canada had **9 PASS, 1 WARN, 0 FAIL**: five series were overdue under configured release schedules. Statistics Canada had **10 PASS, 0 WARN, 0 FAIL**. These are stored-snapshot statuses, not live source checks; expected release dates are schedule estimates.

The research outcomes are aggregate and descriptive. Regimes use the trailing 12-month change in the monthly average policy rate: hiking at or above +0.25 percentage points, easing at or below −0.25, and stable between. The baseline labels a completed month with that month’s policy average. Outcomes are monthly chartered-bank consumer-credit YoY growth. Monthly observations are serially dependent, so research outputs include Newey–West HAC(12) and 12-month block-bootstrap intervals as well as conventional intervals for comparison. No configured monthly unemployment, inflation, or household-income control series is available in this analysis. The regression is not causal.

Scenario inputs are user assumptions except the observed balance default. The model applies:

```text
borrowing-rate change = policy shock (bp) × pass-through ÷ 10,000
affected balance = eligible balance × exposure share × repriced share
annualized sensitivity = affected balance × borrowing-rate change
```

The partial case separates exposure, pass-through, and the share repriced by the selected horizon. Uniform repricing uses half the horizon’s full run-rate to calculate cumulative interest; start-of-horizon repricing applies it for the full horizon. The mechanical comparator assumes the entire balance reprices immediately with one-for-one pass-through. Balances are static; repayments, defaults, new borrowing, contract terms, taxes, and compounding are not modeled.

## Outputs and deeper documentation

- `data/raw/`: timestamped public source snapshots and selected `latest.json` pointers.
- `data/processed/`: conformed CSV dimensions/facts, metrics, validation, freshness, and source-health outputs.
- `reports/`: research CSVs, six generated figures, scenario examples, and the research memo.
- `documentation/`: source definitions, validation results, pipeline limits, and methodology.
- `frontend/index.html`: dashboard source; `frontend/site/` is generated at build time.

See [the research memo](reports/research_memo.md), [methodology](documentation/methodology.md), [data sources](documentation/data_sources.md), [pipeline hardening notes](documentation/pipeline_hardening.md), and the [extended technical reference](documentation/technical_reference.md).

The project has no borrower-level data, default or delinquency outcome, forecasts, causal estimates, scheduled refresh, or deployed public dashboard. PostgreSQL loading is optional and its integration path was not exercised in this audit.
