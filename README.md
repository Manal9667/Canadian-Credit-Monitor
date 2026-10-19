# Canadian Household Credit & Interest-Rate Analysis

An end-to-end financial data analytics platform that transforms public Canadian interest-rate and household-credit data into reproducible research, interactive visualizations, and interest-cost sensitivity scenarios.

**[Live Dashboard](https://canadian-credit-monitor.vercel.app/)** · **[Research Memo](reports/research_memo.md)** · **[Methodology](documentation/methodology.md)**

<img width="1886" height="952" alt="Screenshot (83)" src="https://github.com/user-attachments/assets/ea4df03f-0376-4968-bc5a-bd60967291b5" />

## Project Highlights

- **Financial data engineering:** Integrated 20 Bank of Canada and Statistics Canada series into a reproducible pipeline containing 12,049 observations, with timestamped source snapshots, validation checks, and data-quality monitoring.
- **Interest-rate analysis:** Calculated lending-policy rate spreads and compared household credit growth across hiking, stable, and easing monetary-policy regimes, incorporating Newey–West HAC standard errors and block-bootstrap confidence intervals.
- **Interest-cost scenario modeling:** Developed a Python and JavaScript calculation engine to quantify annualized borrowing-cost sensitivity under configurable rate shocks, pass-through assumptions, exposure shares, and repricing horizons.
- **SQL analytics:** Built nine DuckDB analytical views for year-over-year changes, credit metrics, and other derived indicators.
- **Testing and reproducibility:** Implemented automated unit tests and GitHub Actions checks, with an offline pipeline that reproduces results from selected historical source snapshots.

## Selected Findings

*Results from the selected data snapshot retrieved October 13, 2026; processed observations extend through October 12, 2026.*

| Analysis | Finding |
|---|---|
| Lending-policy spread | Prime rate of 4.45% versus a 2.25% policy rate: a 2.20 percentage-point spread on October 7, 2026 |
| Consumer-credit growth | Mean year-over-year growth ranged from 3.23% in the stable regime to 5.81% in the hiking regime |
| Interest-cost sensitivity | A hypothetical 100 bp increase applied immediately to the full CAD 704.582 billion consumer-credit balance implies CAD 7.046 billion in additional annualized interest costs |

These are descriptive results and mechanical scenario calculations, not causal estimates or forecasts. Regime comparisons include uncertainty analysis, and the full-balance sensitivity assumes immediate, one-for-one repricing.

## Tech Stack

**Languages:** Python, SQL, JavaScript  
**Data & Analytics:** DuckDB, pandas, NumPy, statistical analysis, financial scenario modeling  
**Engineering:** REST APIs, data validation, automated testing, GitHub Actions, reproducible ETL pipelines  
**Visualization:** Interactive web dashboard, generated charts, static-site deployment

## Key Engineering Decisions

- **Reproducible inputs:** Preserve timestamped source snapshots, retrieval metadata, row counts, and checksums.
- **Data-quality controls:** Validate incoming observations before publishing derived analytical outputs.
- **Offline-first research:** Separate live data ingestion from historical analysis so results can be reproduced without provider access.
- **Consistent calculations:** Mirror the interest-cost scenario engine in Python and JavaScript.
- **Explicit assumptions:** Distinguish observed data from user-defined scenario inputs and disclose the limitations of aggregate credit data.



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
