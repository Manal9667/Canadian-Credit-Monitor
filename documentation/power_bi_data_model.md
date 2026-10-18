# Power BI Semantic Data Model

## Overview

This document describes the Power BI star schema used for the Canadian Banking & Credit Intelligence Platform dashboard.

**Design Pattern:** Star Schema with conformed dimensions

**Purpose:** Enable efficient, intuitive filtering and measure calculations across financial time series

---

## Schema Architecture

```
                        ┌─────────────────┐
                        │   DIM_DATE      │
                        ├─────────────────┤
                        │ date_key (PK)   │
                        │ date            │
                        │ year            │
                        │ quarter         │
                        │ month           │
                        │ month_name      │
                        │ day_of_week     │
                        │ is_month_end    │
                        │ is_quarter_end  │
                        │ is_year_end     │
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
        ┌───────────▼────────────┐  ┌────────▼───────────────┐
        │  FACT_OBSERVATIONS     │  │   DIM_SERIES           │
        ├────────────────────────┤  ├────────────────────────┤
        │ observation_key (PK)   │  │ series_id (PK)         │
        │ date_key (FK)          │  │ series_name            │
        │ series_id (FK)         │  │ category               │
        │ source_key (FK)        │  │ unit                   │
        │ value                  │  │ frequency              │
        │ observation_date       │  │ description            │
        │ retrieval_date         │  │ source_id              │
        │ data_quality_flag      │  │ start_date             │
        └────────────────────────┘  │ end_date               │
                    ▲                │ methodology            │
                    │                └────────────────────────┘
        ┌───────────┴──────────┐
        │   DIM_SOURCE         │
        ├──────────────────────┤
        │ source_key (PK)      │
        │ source_id            │
        │ source_name          │
        │ source_url           │
        │ source_frequency     │
        │ data_owner           │
        │ access_type          │
        └──────────────────────┘
```

---

## Dimension Tables

### DIM_DATE (Date Dimension)

**Purpose:** Provides time context for all observations. Enables time-based filtering and grouping.

| Column | Type | Description |
|--------|------|-------------|
| date_key | Integer (PK) | YYYYMMDD format |
| date | Date | Full date |
| year | Integer | Calendar year |
| quarter | Integer | 1-4 |
| month | Integer | 1-12 |
| month_name | Text | January-December |
| day_of_week | Integer | 1-7 |
| day_name | Text | Monday-Sunday |
| is_month_end | Boolean | TRUE if last day of month |
| is_quarter_end | Boolean | TRUE if last day of quarter |
| is_year_end | Boolean | TRUE if Dec 31 |
| year_month | Text | YYYY-MM |

**Key Features:**
- Covers entire historical range of financial data (2010-present)
- Enables monthly, quarterly, and annual aggregations
- Supports fiscal period analysis

**Relationships:**
- FK to FACT_OBSERVATIONS.date_key (Many-to-One)

---

### DIM_SERIES (Financial Series Dimension)

**Purpose:** Defines each financial indicator being tracked. Provides metadata and context.

| Column | Type | Description |
|--------|------|-------------|
| series_id | Text (PK) | Bank of Canada or Stats Canada ID |
| series_name | Text | Display name (e.g., "Household Credit") |
| category | Text | Credit / Rate / Economic |
| unit | Text | Currency, %, basis points, count |
| frequency | Text | Monthly, Quarterly, Annual |
| description | Text | Plain-language description |
| source_id | Integer (FK) | Reference to DIM_SOURCE |
| start_date | Date | Data availability start |
| end_date | Date | Data availability end (NULL if current) |
| methodology | Text | How the metric is calculated |
| data_quality_notes | Text | Known limitations |

**Key Features:**
- Uniquely identifies each financial series
- Stores descriptive metadata for context
- Links to source information
- Supports drill-down explanations

**Categories:**
- **Credit:** Household credit, business loans, mortgages, credit cards
- **Rate:** Policy rate, mortgage rates, lending rates, spreads
- **Economic:** GDP, employment, inflation, exchange rate

**Relationships:**
- FK to DIM_SOURCE.source_key (Many-to-One)
- Referenced by FACT_OBSERVATIONS.series_id (One-to-Many)

---

### DIM_SOURCE (Data Source Dimension)

**Purpose:** Tracks data lineage and source governance.

| Column | Type | Description |
|--------|------|-------------|
| source_key | Integer (PK) | Surrogate key |
| source_id | Text | Bank of Canada / Stats Canada |
| source_name | Text | Full name |
| source_url | Text | Official URL |
| source_frequency | Text | Update cadence |
| data_owner | Text | Organization |
| access_type | Text | Public / API / Download |
| refresh_protocol | Text | Manual / Automated |

**Relationships:**
- Referenced by DIM_SERIES.source_id (One-to-Many)

---

## Fact Table

### FACT_OBSERVATIONS (Core Fact Table)

**Purpose:** Stores every financial observation across all series and time periods.

| Column | Type | Description |
|--------|------|-------------|
| observation_key | Integer (PK) | Surrogate key |
| date_key | Integer (FK) | Links to DIM_DATE |
| series_id | Text (FK) | Links to DIM_SERIES |
| source_key | Integer (FK) | Links to DIM_SOURCE |
| value | Decimal | The financial metric value |
| observation_date | Date | The date the metric represents |
| retrieval_date | Date | When the data was fetched |
| data_quality_flag | Text | OK / WARNING / ERROR |

**Granularity:** One row per series per observation date

**Data Quality Flags:**
- OK: Passed all validation checks
- WARNING: Minor issue (e.g., revised value)
- ERROR: Data quality concern requiring investigation

**Relationships:**
- date_key → DIM_DATE.date_key (Many-to-One)
- series_id → DIM_SERIES.series_id (Many-to-One)
- source_key → DIM_SOURCE.source_key (Many-to-One)

**Indexes:**
- Primary: (date_key, series_id)
- Secondary: (series_id, observation_date)
- Secondary: (data_quality_flag)

---

## Conformed Dimensions

All dimensions are **conformed** — no duplicate entities across tables.

**DIM_DATE:** Conformed across all fact tables. Single calendar.

**DIM_SERIES:** Conformed across all fact tables. Each series defined once.

**DIM_SOURCE:** Conformed across all fact tables. Single source of truth.

---

## Cardinality

| Relationship | Cardinality | Filter Direction |
|--------------|-------------|------------------|
| FACT_OBSERVATIONS (date_key) → DIM_DATE | Many-to-One | Single |
| FACT_OBSERVATIONS (series_id) → DIM_SERIES | Many-to-One | Single |
| FACT_OBSERVATIONS (source_key) → DIM_SOURCE | Many-to-One | Single |
| DIM_SERIES (source_id) → DIM_SOURCE | Many-to-One | Single |

**Filter Direction:** All relationships filter from dimensions to fact table (standard star schema pattern).

---

## Date Table Characteristics

- Granularity: Daily (one row per calendar day)
- Range: 2010-01-01 to 2026-12-31
- Row count: ~6,200 rows
- Used for time-based filtering and bucketing
- Enables month-end, quarter-end, year-end analysis
- Supports year-over-year and period-over-period comparisons

---

## Data Refresh Strategy

| Component | Refresh Cadence | Method |
|-----------|-----------------|--------|
| FACT_OBSERVATIONS | Weekly | Automated ingestion pipeline |
| DIM_SERIES | As-needed | Manual or semi-automated |
| DIM_DATE | Annual | Automatic (pre-built) |
| DIM_SOURCE | As-needed | Manual |

---

## Hierarchy Examples

### Time Hierarchy (DIM_DATE)
```
Year
  └─ Quarter
      └─ Month
          └─ Day
```

### Credit Hierarchy (DIM_SERIES)
```
Category: Credit
  └─ Household Credit
      └─ Mortgages
      └─ Credit Cards
      └─ Other Personal
  └─ Business Credit
```

---

## Handling Multi-Frequency Data

Power BI model includes series at different frequencies (monthly, quarterly, annual).

**Approach:**
- All observations stored at their native frequency
- DIM_SERIES.frequency specifies each series' cadence
- Measures handle aggregation/interpolation as needed
- Dashboard filters allow frequency-specific views

**Example:**
- Bank of Canada policy rate: Daily
- Household credit: Quarterly
- Employment: Monthly
- GDP: Quarterly

---

## DAX Measure Context

Measures operate within this model structure:

```dax
Year-over-Year Change % = 
DIVIDE(
    [Current Value] - [Prior Year Value],
    [Prior Year Value]
)
```

Filters automatically propagate through relationships.

---

## Performance Considerations

1. **Fact Table Size:** ~50,000-100,000 rows (16+ years × ~52 series)
2. **Dimension Sizes:** Small (< 5,000 rows each)
3. **Indexes:** Clustered on (date_key, series_id)
4. **Query Folding:** Power Query handles filtering before loading
5. **Aggregations:** DAX measures use efficient SUMX/CALCULATE patterns

---

## Security

- **Data-level:** Model is public financial data. No row-level security (RLS) applied.
- **Licensing:** Data from Bank of Canada and Statistics Canada under public-use licenses.
- **Credentials:** No sensitive credentials stored in model.

---

## Future Enhancements

1. Add explicit rate-of-change dimension
2. Implement rolling-average fact table
3. Add forecast/scenario dimension
4. Create linked entity for correlated series
5. Implement SCD Type 2 for DIM_SERIES historical changes

---

## Model Validation Checklist

- [ ] All foreign keys exist in dimension tables
- [ ] No orphaned fact records
- [ ] Date relationships use proper date columns
- [ ] Hierarchies are properly defined
- [ ] Measure calculations verified against SQL
- [ ] No circular dependencies in relationships
- [ ] Filters flow correctly through dimensions
- [ ] Performance queries execute < 2 seconds
