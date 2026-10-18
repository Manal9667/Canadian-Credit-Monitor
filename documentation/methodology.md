# Analytical Methodology

This document defines the metrics and monitoring rules currently computed by
the CSV, Python, and SQL layers. Python metrics are implemented in
`python/analytics/metrics.py`; SQL equivalents are implemented in
`sql/views.sql`. Regression tests compare selected SQL and Python results on
deterministic fixtures; not every metric is reconciled for every series.

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
| Year-over-year absolute | `value_t - value_{t-1 year}` matched by exact calendar date | monthly, quarterly |
| Year-over-year percentage | `100 * (value_t - value_{t-1 year}) / |value_{t-1 year}|` | monthly, quarterly |

Percentage changes guard against division by zero (a zero base yields null).
Year-over-year requires an observation on the exact same calendar date one year
earlier. If that date is absent, the result is null; rows are never substituted
by a fixed offset. It is intentionally omitted for daily and weekly series.

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

## Source freshness monitoring

Freshness is based on each source's publication schedule, not a shared maximum
observation age. Bank of Canada Valet labels the policy series business-daily
and the posted-rate series weekly; its A4 credit and effective-rate series are
monthly. Statistics Canada table 38-10-0238-01 has quarterly frequency in WDS
metadata (frequency code 9).

| Source frequency | Next expected publication | Grace after expected date | Basis |
|---|---|---|---|
| Bank of Canada business-daily | Next weekday after latest observation | 2 business days | Valet label and observed business-day cadence; public API processing may lag release. Holidays are not modeled in the weekday projection. |
| Bank of Canada weekly | Latest observation + 7 days | 2 business days | Weekly Valet series; observed Wednesday cadence. |
| Bank of Canada monthly | End of the next reference month + 60 calendar days | 7 calendar days | Operational publication-lag allowance based on the A4 monthly release cycle; it is a monitoring rule, not a Bank-guaranteed release date. |
| Statistics Canada quarterly | End of the next quarter + 73 calendar days, moved back to Friday if it falls on a weekend | 7 calendar days | WDS table metadata reports the 2026-09-11 release for data through 2026-Q2, 73 days after 2026-06-30. This is an observed-lag projection, not an official future release commitment. |

A series is `OVERDUE` only when the current date is strictly later than its
expected publication date plus grace. Unknown source/frequency combinations are
reported as `UNKNOWN`, not silently treated as current or overdue. The generated
`data/processed/series_freshness.csv` records publication frequency, source
observation date, snapshot ID, retrieval timestamp, processing timestamp,
expected next publication, overdue-after date, rule text, and status. A source
observation date is never replaced by its retrieval or processing timestamp.

On the 2026-10-13 refresh, all 20 series were inside these windows. The previous
75-day threshold incorrectly warned on all 11 Bank of Canada monthly series;
they had not passed their expected release windows. This rule prevents those
false positives while retaining an explicit `OVERDUE` status once a scheduled
publication and grace period have actually elapsed.

## Consumer-credit regime research extension

The reproducible extension is implemented in
`python/analysis/credit_regime_extensions.py` and run with
`python -m python.analysis.run_credit_extensions`. It writes the monthly
analysis panel, regime uncertainty summaries, lag correlations, specification
sensitivity, and dynamic OLS estimates to `reports/credit_*.csv`. The original
`regime_comparisons.csv` and baseline definition remain the descriptive anchor.

The outcome is chartered-bank total consumer-credit balance YoY percentage
growth. It is computed from the exact calendar month 12 months earlier. The
monthly panel is reindexed before calculating growth, so a missing month is not
silently skipped/bridged. Regime input is the average daily policy rate for a
calendar month minus its value 12 calendar months earlier. The baseline uses
the same completed reference month (first-of-month stamp is a display label).
The timing sensitivity shifts that completed regime label forward one month
before joining it to credit growth. Alternative thresholds are ±0.10 and
±0.50 percentage points; window sensitivities are pre-2020-03 and post-2020.

Regime tables report N, sample dates, mean, median, sample SD, iid normal-
approximation mean interval, Newey-West HAC(12) mean interval, and a circular moving-block
bootstrap interval. HAC scores retain all monthly dates, assigning zero scores
outside the regime, rather than treating separated regime observations as
adjacent. The bootstrap uses 12-month blocks, 2,000 draws, and seed 20261018;
draws with no observations for a regime are omitted from that regime's interval.
These intervals quantify uncertainty under their respective assumptions; they
do not account for regime classification uncertainty, source revisions, or
selection of policy episodes.

Lag k means the trailing 12-month policy change in month t paired with credit
YoY growth in month t+k; output dates refer to t. The dynamic sensitivity model
is OLS of monthly YoY growth on policy-change lags 0-3, lagged YoY growth, and a
linear trend, with Newey-West HAC(12) standard errors. It is descriptive and
does not identify a causal policy effect. No monthly unemployment, inflation,
or household-income series exists in the configured snapshot. Quarterly debt-
to-income is not used as a control because of frequency mismatch and potential
post-treatment status. The analysis does not formally test structural breaks;
the 2020 pandemic/rebound and 2022-23 tightening are interpreted as periods
that may affect these short aggregate time series. The selected consumer-credit
balance sample is 2016-07 through 2026-07 and has no missing monthly dates or
null values; outliers are retained and reported in the research memo.

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

## Finance Research Layer

The research layer is implemented in `python/analysis/household_credit_research.py`
and writes reproducible outputs to `reports/`. It uses only processed aggregate
observations and does not interpolate across mismatched frequencies.

### Rate pass-through

The mechanical pass-through comparison is the chartered-bank prime lending rate
against the Bank of Canada policy rate. Posted rates are weekly, while the
policy rate is business-daily, so posted-rate analysis uses exact observation
date joins and starts only after the policy-rate series begins in April 2009.

Effective lending rates are monthly. For those comparisons, the daily policy
rate is averaged within the same calendar month and joined to the monthly
effective-rate observation. This is an explicit frequency aggregation, not a
forward-fill or interpolation. Posted mortgage rates are reported as informative
spreads because they also reflect funding costs and bond yields.

### Lead/lag correlations

Lead/lag analysis uses changes rather than levels. The policy variable is the
trailing 12-month change in the monthly average policy rate, in percentage
points. The credit variable is year-over-year balance growth, using the same
exact-date rule as the standard metrics layer. Correlations are reported for
every lag from 0 to 12 months, where a lag of `L` compares the policy-rate
change at month `t` with credit growth at month `t + L`. No "best lag" is
selected.

Each correlation reports `N`, the number of aligned observations used.
Correlations are descriptive timing evidence, not causal estimates or forecasts.

### Rate regimes

Regimes are defined before computation using the trailing 12-month change in the
monthly average policy rate:

| Regime | Rule |
|---|---|
| Hiking | 12-month policy-rate change `>= +0.25` percentage points |
| Easing | 12-month policy-rate change `<= -0.25` percentage points |
| Stable | Between `-0.25` and `+0.25` percentage points |

Monthly credit growth is joined to the regime for the same calendar month.
Quarterly Statistics Canada observations are joined only when their observation
date exactly matches an available monthly regime date. Results are labelled as
associations that coincided with regimes, not as policy effects.

### Tracked component shares

The component-share output uses the Bank of Canada household-credit components
available in this project and excludes the consumer-credit aggregate to avoid
double counting. Shares are therefore named "share of tracked components" and
are not presented as total household-debt composition.

### Illustrative rate sensitivity

The sensitivity table applies +100 bp and +200 bp shocks mechanically to the
latest observed balances for products that also have effective lending-rate
series. The calculation is:

`incremental annual interest = balance_millions_cad * rate_shock_percentage / 100`

The result is shown in millions of Canadian dollars and as a percentage of the
balance. It ignores repricing schedules, defaults, credit mix, balances paid in
full, and borrower behaviour. Mortgages are excluded because this dataset does
not include an effective mortgage lending rate.

## Auditable interest-cost scenario engine

The validated calculation layer is `python/analysis/interest_cost_scenarios.py`;
the static dashboard counterpart is `frontend/interest_cost_engine.js`. The
Python example generator is `python -m python.analysis.run_interest_cost_scenarios`
and writes `reports/interest_cost_scenario_examples.csv`. Dashboard inputs are
client-side and are never saved or uploaded.

Inputs and units: eligible balance **B** in CAD millions (observed V122667758
balance by default, editable as a user-defined amount); policy shock **S** in
basis points; exposure share **E** between 0 and 1; pass-through multiple **P**
between 0 and 5; repriced share **R** between 0 and 1, conditional on the
exposed balance; horizon **H** in whole months (1 to 120); and timing, either
repricing uniformly across the horizon or at its start. The borrowing-rate
change is `S × P / 10,000` as a decimal rate (equivalently S×P basis points).
Partial affected balance is `B × E × R`. Annualized incremental run-rate at
horizon is `B × E × R × S × P / 10,000` in CAD millions per year.

For repricing at horizon start, cumulative incremental cost is annualized
run-rate × H/12. For uniform repricing across the horizon, the average repriced
share is R/2, so cumulative cost is annualized run-rate × H/24. This assumes
even timing and a static balance/rate shock. The separately displayed full
mechanical comparator sets E=1, P=1, R=1, and timing to horizon start; it does
not modify or multiply the partial case. This separation prevents double
counting balances, pass-through, exposure, and repricing.

The example defaults use observed balance CAD 704,582 million, but use
illustrative assumptions of +100 bp policy shock, 60% exposed, 0.50x
pass-through, 50% of exposed balance repriced, and uniform repricing over 12
months. Those assumptions are not estimated by the project. As an arithmetic
check, the verified full mechanical +100 bp comparator is CAD 7,045.82 million
per year if all eligible balances reprice immediately with one-for-one pass-
through; the dashboard calculates this rather than hardcoding it. The observed
7.92% effective rate is shown for context only and is not added to the
incremental-rate formula.

Negative shocks represent cost reductions. Zero balances and zero shocks yield
zero incremental costs. Inputs are bounded to catch invalid/extreme values.
The model excludes repayments, defaults, new borrowing, balance migration,
taxes, compounding, caps/floors, and borrower-specific contract terms. The
finite-horizon amount is a simple undiscounted cumulative sum, not a forecast,
causal estimate, or precision claim. Source date, retrieval time, and last
validation freshness status are shown separately; freshness refers to the
stored validation run, not a live source check.
