# Static Dashboard Deployment Preparation

## Architecture

The dashboard is a static HTML, CSS, and JavaScript page. It reads five generated CSV/JSON files with same-origin `fetch` requests and has no runtime Python service, database, API key, or server-side feature. The local builder creates `frontend/site/` with the dashboard entry point and its data bundle. Relative URLs keep the same bundle working at a domain root or beneath a repository/project path.

## Refresh and Validate Data

Run commands from the repository root. Live ingestion is optional and was not run as part of deployment preparation:

```powershell
python -m python.ingestion.bank_of_canada
python -m python.ingestion.statistics_canada
```

Then run validation and regenerate every offline output:

```powershell
python -m python.validation.engine
python -m python.transformation.transform
python -m python.analytics.metrics
python -m python.analytics.anomaly_detection
python -m python.reporting.reporting_summary
python -m python.db.duckdb_runner
python -m python.analysis.household_credit_research
python -m python.reporting.prepare_dashboard
```

Before using or publishing an update, inspect `data/processed/pipeline_metadata.json`, `data/processed/series_freshness.csv`, `documentation/validation_report.md`, both source `latest.json` pointers, and the selected snapshot manifests. Confirm snapshot IDs, retrieval timestamps, latest observation dates by frequency, row/series counts, candidate validation, expected next-publication dates, overdue statuses, and any warnings. Retrieval and processing times are not observation dates.

As of the successful 2026-10-13 refresh, Bank of Canada supplied 16/16 series (11,465 observations; latest daily/weekly/monthly observations 2026-10-12/2026-10-07/2026-07-01). Statistics Canada supplied all four configured series (584 observations through 2026-04-01). WDS cube metadata reported frequency code 9 (quarterly), release time 2026-09-11, and a current cube; all four values parsed without schema warnings. The prior 2026-10-12 WDS request returned HTTP 403, but the failure was not reproduced the next day. On 2026-10-13 both the configured WDS `getFullTableDownloadCSV` integration and the official CSV ZIP URL returned HTTP 200. The cause of the one-off 403 is unknown. Official alternatives are WDS full-table SDMX (`https://www.statcan.gc.ca/en/developers/wds/user-guide`), the SDMX REST service (`https://www.statcan.gc.ca/en/developers/sdmx/user-guide`), and the bulk Delta File (`https://www.statcan.gc.ca/en/developers/df`). The SDMX and Delta File routes were not tested because the configured WDS/CSV flow recovered. No access controls were bypassed.

Ingestion now validates completeness and data quality before atomically promoting a snapshot pointer. Partial series/table results, schema warnings, future dates, or validation failures leave the previous `latest.json` untouched; no old data are silently substituted. Transformation also rejects an incomplete selected manifest. Review every snapshot and pointer after failures.

Freshness is schedule-based, with expected release and grace rules documented in `documentation/methodology.md`. As of 2026-10-13 the previous fixed 75-day rule's 11 Bank monthly warnings were false positives; all 20 series are within their expected release windows. The quarterly next-release date is an estimate based on observed WDS release timing, not a provider commitment.

The pipeline does not schedule refreshes or publish automatically. Future data updates require a manual ingestion, validation, regeneration, review, and site-build cycle unless separate automation is designed and reviewed later.

## Files to Publish

Build with `python -m python.reporting.prepare_dashboard`. Publish only the **contents** of `frontend/site/`:

- `index.html`
- `data/processed/metrics_summary.csv`
- `data/processed/metrics_timeseries.csv`
- `data/processed/monitoring_alerts.csv`
- `data/processed/validation_results.csv`
- `data/processed/pipeline_metadata.json`

The dashboard does not use raw snapshots, Python files, research reports, or PostgreSQL. Those remain in the repository for reproducibility and analysis, not as web assets. `frontend/site/` is generated locally and ignored by Git; the source page and builder are reviewable.

## Local Preview

```powershell
python -m python.reporting.prepare_dashboard
python -m http.server 8000 --directory frontend/site
```

Open `http://localhost:8000/`. A static HTTP server is needed because browsers block local-file `fetch` requests. Stop the server with Ctrl+C when finished.

## Future Manual Publication

Cloudflare Pages Direct Upload is the recommended simplest host for this bundle; GitHub Pages and Netlify are also suitable static hosts. No hosting account, project, workflow, DNS, secret, or provider configuration has been created.

When ready to publish:

1. Run the refresh/rebuild checks above, inspect warnings and source dates, and review the generated changes.
2. Build `frontend/site/` and preview it locally at desktop and mobile sizes.
3. In the chosen host's dashboard, create a static site using its manual/direct-upload flow and upload the **contents** of `frontend/site/` as the site root. Do not configure a build command or server-side runtime for this prebuilt bundle.
4. After the host provides a preview URL, test all dashboard data requests, freshness notices, navigation, series filters, time-range controls, and mobile layout before sharing the URL.

The project is prepared for that future manual process but is not deployed. No public URL is available.