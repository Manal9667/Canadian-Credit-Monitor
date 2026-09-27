# Power Query Workflow

Power Query (the M engine behind Power BI's "Transform Data") performs the
**last-mile shaping** the semantic model needs. The `.pq` scripts in
`powerquery/` are the M code for each query; they can be pasted into the Power BI
Advanced Editor or referenced when rebuilding the model.

## Source parameter

All queries read from a single Power BI parameter, `SourceFolder`, that points at
`data/processed`. Repointing this one parameter (or swapping the source step for
a PostgreSQL connector against the `credit` views) moves the whole model between
the CSV serving layer and the database with no other changes.

## Queries

| Query | File | Transformations demonstrated |
|---|---|---|
| dim_series | `dim_series.pq` | promote headers, type normalisation, text trim/clean, derived `unit_label` |
| dim_date | `dim_date.pq` | typing, derived `year_month_sort` for chronological sorting |
| fact_observations | `fact_observations.pq` | typing, missing-value tagging, row filtering, **reference merge** to `dim_series`, derived display value |
| monitoring_alerts | `monitoring_alerts.pq` | typing, filtering to active alerts, derived severity sort order |

Together these cover the transformation types called for: data-type
normalisation, column standardisation, filtering, merging (nested join),
missing-value handling, date transformation, reference-data joins, and derived
fields. (Appending is illustrated conceptually below; the pipeline conforms the
two sources upstream, so an append is not required in the model.)

## Why each layer does what it does

This project deliberately uses four distinct transformation layers. Keeping their
responsibilities separate is the point — it mirrors how a governed reporting
stack actually works.

| Layer | Owns | Why here |
|---|---|---|
| **Python ETL** (`python/`) | Retrieval, raw snapshotting, validation, source conforming, heavy/statistical computation (metrics, monitoring) | Reproducible, testable, version-controlled, runs on a schedule independent of any BI tool. Statistics belong in tested code, not in a report. |
| **SQL / PostgreSQL** (`sql/`) | The governed relational model and set-based analytical views (changes, rolling, spreads, shares, alerts) | A single source of truth that any tool can query; set-based logic is efficient and centrally governed. |
| **Power Query** (`powerquery/`) | Last-mile shaping for the model: typing, filtering, merges, model-friendly derived columns | Analyst-editable, close to the report, ideal for shaping that varies with the visual layer without redeploying the pipeline. |
| **Power BI model + DAX** | Relationships and *dynamic, filter-context* measures | Aggregations that must respond to slicers and cross-filtering belong in DAX, not baked into the data. |

### Rule of thumb used here
- If a calculation is **fixed and row-level** and should be identical everywhere
  → do it once in Python/SQL (e.g. year-over-year change, z-scores).
- If a calculation must **react to what the user filters** on the page
  → do it in DAX (e.g. "current value" for the selected series and date range).
- If it is **structural shaping** for the model → do it in Power Query.

## Appending (conceptual example)

If the two sources were **not** pre-conformed in Python, the Power Query pattern
would be:

```m
let
    boc     = #"raw_bank_of_canada",     // long: source, series_id, date, value
    statcan = #"raw_statistics_canada",  // same shape
    Combined = Table.Combine({boc, statcan})   // append
in
    Combined
```

In this project that conforming already happens in `transformation/transform.py`,
which is why the model reads a single `fact_observations` query instead. The
example is retained to document the decision.
