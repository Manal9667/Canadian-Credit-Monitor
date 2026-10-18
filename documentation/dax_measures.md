# DAX Measures Specification

## Overview

This document defines all DAX measures used in the Power BI semantic model. Each measure is accompanied by its formula, calculation logic, and appropriate usage context.

**Measure Naming Convention:** [Measure Category]_[Metric Name]

**Update Method:** Automatic through Power Query refresh

---

## Core Value Measures

### VALUE_Current

**Purpose:** Latest observation value for the selected series.

```dax
VALUE_Current = 
CALCULATE(
    MAX(FACT_OBSERVATIONS[value]),
    FILTER(
        FACT_OBSERVATIONS,
        FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
    )
)
```

**Usage:** KPI cards, gauge visuals, drill-down current values

**Context:** Filters on Series, Date, Source

---

### VALUE_PriorPeriod

**Purpose:** Value from the immediately preceding period (month/quarter/year).

```dax
VALUE_PriorPeriod = 
VAR CurrentDate = MAX(FACT_OBSERVATIONS[observation_date])
VAR SeriesKey = MAX(FACT_OBSERVATIONS[series_id])
VAR Frequency = MAX(DIM_SERIES[frequency])
VAR PriorMonthDate = DATE(YEAR(CurrentDate), MONTH(CurrentDate) - 1, DAY(CurrentDate))
RETURN
CALCULATE(
    MAX(FACT_OBSERVATIONS[value]),
    FACT_OBSERVATIONS[series_id] = SeriesKey,
    FACT_OBSERVATIONS[observation_date] = PriorMonthDate,
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
```

**Usage:** Period-over-period comparison, change calculations

**Notes:** Handles month-end edge cases

---

### VALUE_PriorYear

**Purpose:** Observation value from one year prior (same date).

```dax
VALUE_PriorYear = 
VAR CurrentDate = MAX(FACT_OBSERVATIONS[observation_date])
VAR SeriesKey = MAX(FACT_OBSERVATIONS[series_id])
VAR PriorYearDate = DATE(YEAR(CurrentDate) - 1, MONTH(CurrentDate), DAY(CurrentDate))
RETURN
CALCULATE(
    MAX(FACT_OBSERVATIONS[value]),
    FACT_OBSERVATIONS[series_id] = SeriesKey,
    FACT_OBSERVATIONS[observation_date] = PriorYearDate,
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
```

**Usage:** Year-over-year analysis, annual comparison charts

---

## Change Measures

### CHANGE_AbsoluteMonthly

**Purpose:** Absolute change in value from prior month.

```dax
CHANGE_AbsoluteMonthly = 
[VALUE_Current] - [VALUE_PriorPeriod]
```

**Usage:** Change visualization, trend tables

**Format:** Same unit as underlying series

---

### CHANGE_PercentageMonthly

**Purpose:** Percentage change from prior month.

```dax
CHANGE_PercentageMonthly = 
DIVIDE(
    [CHANGE_AbsoluteMonthly],
    [VALUE_PriorPeriod],
    BLANK()
) * 100
```

**Usage:** Growth rate visualization, comparative analysis

**Format:** Percentage (%)

---

### CHANGE_AbsoluteYoY

**Purpose:** Absolute change from year-ago value.

```dax
CHANGE_AbsoluteYoY = 
[VALUE_Current] - [VALUE_PriorYear]
```

**Usage:** Long-term trend analysis

---

### CHANGE_PercentageYoY

**Purpose:** Year-over-year percentage change.

```dax
CHANGE_PercentageYoY = 
DIVIDE(
    [CHANGE_AbsoluteYoY],
    [VALUE_PriorYear],
    BLANK()
) * 100
```

**Usage:** Annual growth rates, YoY dashboards

**Format:** Percentage (%)

---

## Trend Measures

### TREND_Rolling3MonthAverage

**Purpose:** Average value over the last 3 months (or applicable period).

```dax
TREND_Rolling3MonthAverage = 
VAR CurrentDate = MAX(FACT_OBSERVATIONS[observation_date])
VAR SeriesKey = MAX(FACT_OBSERVATIONS[series_id])
VAR StartDate = DATE(YEAR(CurrentDate), MONTH(CurrentDate) - 2, 1)
RETURN
CALCULATE(
    AVERAGE(FACT_OBSERVATIONS[value]),
    FACT_OBSERVATIONS[series_id] = SeriesKey,
    FACT_OBSERVATIONS[observation_date] >= StartDate,
    FACT_OBSERVATIONS[observation_date] <= CurrentDate,
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
```

**Usage:** Smoothed trend visualization, noise reduction

---

### TREND_Rolling12MonthAverage

**Purpose:** Average value over the last 12 months (annual average).

```dax
TREND_Rolling12MonthAverage = 
VAR CurrentDate = MAX(FACT_OBSERVATIONS[observation_date])
VAR SeriesKey = MAX(FACT_OBSERVATIONS[series_id])
VAR StartDate = DATE(YEAR(CurrentDate) - 1, MONTH(CurrentDate), DAY(CurrentDate))
RETURN
CALCULATE(
    AVERAGE(FACT_OBSERVATIONS[value]),
    FACT_OBSERVATIONS[series_id] = SeriesKey,
    FACT_OBSERVATIONS[observation_date] >= StartDate,
    FACT_OBSERVATIONS[observation_date] <= CurrentDate,
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
```

**Usage:** Annual trend analysis, long-term patterns

---

## Statistical Measures

### STAT_HistoricalAverage

**Purpose:** Average across all available history (full dataset).

```dax
STAT_HistoricalAverage = 
VAR SeriesKey = MAX(FACT_OBSERVATIONS[series_id])
RETURN
CALCULATE(
    AVERAGE(FACT_OBSERVATIONS[value]),
    FACT_OBSERVATIONS[series_id] = SeriesKey,
    ALL(DIM_DATE),
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
```

**Usage:** Historical baseline, deviation calculations

---

### STAT_HistoricalStdDev

**Purpose:** Standard deviation across full history.

```dax
STAT_HistoricalStdDev = 
VAR SeriesKey = MAX(FACT_OBSERVATIONS[series_id])
RETURN
CALCULATE(
    STDEV.P(FACT_OBSERVATIONS[value]),
    FACT_OBSERVATIONS[series_id] = SeriesKey,
    ALL(DIM_DATE),
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
```

**Usage:** Volatility assessment, z-score calculation

---

### STAT_HistoricalMin

**Purpose:** Minimum value in full history.

```dax
STAT_HistoricalMin = 
VAR SeriesKey = MAX(FACT_OBSERVATIONS[series_id])
RETURN
CALCULATE(
    MIN(FACT_OBSERVATIONS[value]),
    FACT_OBSERVATIONS[series_id] = SeriesKey,
    ALL(DIM_DATE),
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
```

**Usage:** Range context, extreme value identification

---

### STAT_HistoricalMax

**Purpose:** Maximum value in full history.

```dax
STAT_HistoricalMax = 
VAR SeriesKey = MAX(FACT_OBSERVATIONS[series_id])
RETURN
CALCULATE(
    MAX(FACT_OBSERVATIONS[value]),
    FACT_OBSERVATIONS[series_id] = SeriesKey,
    ALL(DIM_DATE),
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
```

**Usage:** Range context, peak value reference

---

## Deviation Measures

### DEVIATION_FromHistoricalAverage

**Purpose:** Current value expressed as deviation from historical mean.

```dax
DEVIATION_FromHistoricalAverage = 
[VALUE_Current] - [STAT_HistoricalAverage]
```

**Usage:** Anomaly detection, monitoring dashboard

---

### DEVIATION_ZScore

**Purpose:** Z-score: how many standard deviations from historical mean?

```dax
DEVIATION_ZScore = 
DIVIDE(
    [DEVIATION_FromHistoricalAverage],
    [STAT_HistoricalStdDev],
    BLANK()
)
```

**Usage:** Outlier identification, statistical alerts

**Interpretation:**
- |z| < 1: Within 1 standard deviation (68% of values)
- |z| 1-2: Between 1-2 standard deviations (95% of values)
- |z| > 2: Unusual movement (< 5% of values)
- |z| > 3: Extreme movement (< 0.3% of values)

---

### DEVIATION_PercentageFromAverage

**Purpose:** Current value as % deviation from historical mean.

```dax
DEVIATION_PercentageFromAverage = 
DIVIDE(
    [DEVIATION_FromHistoricalAverage],
    [STAT_HistoricalAverage],
    BLANK()
) * 100
```

**Usage:** Relative context, percentage-based alerts

---

## Rate-Specific Measures

### RATE_Spread

**Purpose:** Difference between two related rates (e.g., lending rate - policy rate).

```dax
RATE_Spread = 
VAR RateName = MAX(DIM_SERIES[series_name])
VAR BaseRate = CALCULATE(
    [VALUE_Current],
    FILTER(DIM_SERIES, DIM_SERIES[series_name] = "Policy Rate")
)
RETURN
[VALUE_Current] - BaseRate
```

**Usage:** Lending margin analysis, rate environment

**Notes:** Requires custom logic per rate pair

---

### RATE_ChangeFromPrior

**Purpose:** Change in rate from prior period (basis points).

```dax
RATE_ChangeFromPrior = 
VAR Change = [CHANGE_AbsoluteMonthly]
RETURN
IF(
    SEARCH("Rate", MAX(DIM_SERIES[series_name])),,
    Change * 100,  // Convert to basis points if rate is in %
    Change
)
```

**Usage:** Rate-change highlighting, monetary policy tracking

---

## Monitoring/Alert Measures

### ALERT_IsUnusualMovement

**Purpose:** Flag if current observation is statistically unusual (z-score > 2).

```dax
ALERT_IsUnusualMovement = 
IF(
    ABS([DEVIATION_ZScore]) > 2,
    TRUE,
    FALSE
)
```

**Usage:** Monitoring dashboard, alert row highlighting

---

### ALERT_ExtremeChange

**Purpose:** Flag if period change is extreme (> 3 standard deviations of historical changes).

```dax
ALERT_ExtremeChange = 
VAR HistoricalPctChangeStdDev = CALCULATE(
    STDEV.P(FACT_OBSERVATIONS[pct_change]),
    ALL(DIM_DATE),
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
RETURN
IF(
    ABS([CHANGE_PercentageMonthly] / HistoricalPctChangeStdDev) > 3,
    TRUE,
    FALSE
)
```

**Usage:** Alert flagging, threshold-based monitoring

---

## Count Measures

### COUNT_ObservationsInSelection

**Purpose:** Number of valid observations in the current filter context.

```dax
COUNT_ObservationsInSelection = 
CALCULATE(
    COUNTA(FACT_OBSERVATIONS[observation_key]),
    FACT_OBSERVATIONS[data_quality_flag] <> "ERROR"
)
```

**Usage:** Data completeness, audit view

---

### COUNT_SeriesInScope

**Purpose:** Number of unique series in current filter.

```dax
COUNT_SeriesInScope = 
DISTINCTCOUNT(FACT_OBSERVATIONS[series_id])
```

**Usage:** Dashboard status, series coverage

---

### COUNT_ActiveAlerts

**Purpose:** Number of current monitoring alerts.

```dax
COUNT_ActiveAlerts = 
CALCULATE(
    COUNTX(
        FILTER(
            VALUES(FACT_OBSERVATIONS[series_id]),
            [ALERT_IsUnusualMovement]
        ),
        1
    )
)
```

**Usage:** Alert summary, dashboard KPI

---

## Format Strings

Recommended Power BI format strings for measures:

| Measure Type | Format | Example |
|--------------|--------|---------|
| VALUE_* | Depends on series unit | Millions: #,##0 |
| CHANGE_Percentage* | Percentage | 0.00% |
| CHANGE_Absolute* | Same as VALUE | Millions: #,##0 |
| STAT_* | Same as VALUE | Millions: #,##0 |
| DEVIATION_ZScore | Number | 0.00 |
| DEVIATION_Percentage* | Percentage | 0.00% |
| RATE_Spread | Number (basis pts) | 0.00 |
| ALERT_* | True/False | Boolean |
| COUNT_* | Whole number | 0 |

---

## Measure Calculation Order

When building Power BI visuals, apply measures in this order:

1. **Base Values:** VALUE_Current, VALUE_PriorPeriod
2. **Derived Changes:** CHANGE_*, DEVIATION_*
3. **Trends:** TREND_*
4. **Alerts:** ALERT_*
5. **Formatting:** Apply conditional formatting based on thresholds

---

## Performance Notes

- Measures using ALL() may be slow on large datasets; test before deploying
- Avoid nesting multiple measures in complex calculations
- Consider separate summary tables for heavily-used aggregations
- Cache calculations using SUMMARIZE() when appropriate
- Use KEEPFILTERS vs CALCULATE judiciously

---

## Testing & Validation

Every measure should be tested against:

1. **Raw SQL equivalent** from PostgreSQL analytical views
2. **Python calculation** from analytics layer
3. **Manual spot-check** for known data points
4. **Edge cases:** Month-end, year-end, data gaps, null values

Reconciliation report in `documentation/measure_reconciliation.md`

---

## Future Enhancements

- Add forecasting measures (linear regression, exponential smoothing)
- Create scenario/what-if measures
- Implement correlation measures between series
- Add contribution-to-total measures for credit category breakdown
