# Analytical Methodology

This document defines every metric and monitoring rule the platform computes, so
the numbers on the dashboard are fully traceable and reproducible. The same
definitions are implemented in the Python analytics layer (`python/analytics`)
and in the SQL analytical views (`sql/views.sql`); the reconciliation report
(`python/analytics/reconciliation.py`) confirms the two agree.

## Notation

- `value_t` — the observation at period _t_ for a series.
- A "period" is one observation step of the series (day, week, month, quarter).
- Metrics that are not statistically appropriate for a series are left **null**
  rather than forced.

## Change metrics

| Metric | Definition | Applied to |
|---|---|---|
| Previous value | `value_{t-1}` | all series |
| Absolute change | `value_t - value_{t-1}` | all series |
| Percentage change | `100 * (value_t - value_{t-1}) / |value_{t-1}|` | all series |
| Year-over-year absolute | `value_t - value_{t-k}` where _k_ = periods/year | monthly (k=12), quarterly (k=4) |
| Year-over-year percentage | `100 * (value_t - value_{t-k}) / |value_{t-k}|` | monthly, quarterly |

Percentage changes guard against division by zero (a zero base yields null).
Year-over-year is **not** computed for daily/weekly rate series because their
observation dates do not align cleanly one year apart; showing a YoY there would
be misleading, so it is intentionally omitted.

## Level / distribution metrics

| Metric | Definition |
|---|---|
| Rolling 3-period average | mean of the trailing 3 observations (min 1) |
| Rolling 12-period average | mean of the trailing 12 observations (min 1) |
| Historical average | mean over the full available history of the series |
| Historical standard deviation | sample standard deviation (ddof = 1) over full history |
| Historical min / max | extremes over full history |
| Deviation from average | `latest_value - historical_average` |
| Latest z-score | `(latest_value - historical_average) / historical_stddev` |
| Percentile rank | share of historical observations `<= latest_value`, in percent |

For monthly series the 3- and 12-period rolling averages are the 3-month and
12-month moving averages. For weekly series they are 3-week and 12-week averages;
the column names say "period" to stay honest about this.

## Monitoring / anomaly rules

The monitor is a transparent statistical screen, not a predictive model. Three
independent rules run; any one can raise a flag, and every flag states its reason.

1. **Rolling z-score** (primary). For each observation, compute the mean and
   standard deviation of the **trailing 12 observations that precede it** (so a
   point never influences its own baseline). The z-score is
   `(value_t - trailing_mean) / trailing_std`.
   - `|z| >= 3` → severity **HIGH**
   - `2 <= |z| < 3` → severity **MEDIUM**
   - otherwise → **NORMAL**
   Requires at least 8 prior observations, else the point is not scored.

2. **Percentage-change screen.** Flags a period whose percentage change exceeds
   3 standard deviations of that series' own historical percentage changes. This
   catches abrupt single-period jumps even when the level is not yet extreme.

3. **Historical-range (tail) screen.** Flags values in the top or bottom 2.5% of
   the series' full historical distribution.

The dashboard's "requires investigation" list is the **latest** observation of
each series that trips at least one rule, ranked by absolute z-score. The full
history of flagged points is also retained (`monitoring_history.csv`) for the
monitoring timeline visual.

### Language and scope

Flags use neutral language — "monitoring alert", "unusual movement", "historical
deviation", "requires investigation". The system never labels an observation as
fraud, never asserts a real-world risk event, and never claims a cause. A flag
means only that a value is statistically unusual relative to its own history and
merits an analyst's review.
