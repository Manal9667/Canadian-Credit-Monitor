# Role-Relevant Skills Mapping

This document maps implemented repository evidence to common banking technology operations and analytics responsibilities. It is not a claim that the project uses CIBC data, systems, or confidential information.

| Capability | Evidence in this repository | Boundary |
| --- | --- | --- |
| API and file ingestion | Bank of Canada Valet and Statistics Canada WDS modules | Live network ingestion was not run during the latest verification. |
| Data quality | Schema, null, duplicate, date, frequency, freshness, and value checks; strict transformation guards | Current checked-in data has 1 warning for 12 stale Bank of Canada series. |
| Python analytics | Period changes, exact-calendar YoY for eligible frequencies, rolling means, history statistics, anomaly flags | Statistical descriptions are not causal or borrower-risk conclusions. |
| SQL and modeling | Four-table star schema, indexes, and 9 analytical views | Views were executed through DuckDB; PostgreSQL integration remains unverified. |
| Reporting | On-demand Markdown and CSV output with source snapshot timestamps | No scheduler, mail delivery, deployed report service, or frontend. |
| BI | Power Query scripts and written semantic-model/DAX/dashboard specifications | No Power BI `.pbix` or implemented dashboard is present. |

## Public Data and Compliance

The project uses public Bank of Canada and Statistics Canada data only. It contains no CIBC data, customer records, internal systems, or proprietary information. Do not describe aggregate macroeconomic observations as individual loan, delinquency, or credit-bureau data.

## Interview Notes

Use the verified resume notes in `resume_metrics.md` and the actual results in the root `README.md`. Do not claim implementation of a Power BI dashboard, production deployment, scheduling, query-performance benchmarks, or broad test coverage.
