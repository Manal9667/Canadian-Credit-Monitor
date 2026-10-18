-- =============================================================================
-- views.sql - analytical views
-- These are the decision-ready views Power BI (or any BI tool) connects to.
-- They demonstrate JOINs, CTEs, CASE, conditional aggregation, date functions
-- and window functions (LAG, rolling frames, ranking, partitioned aggregates).
-- =============================================================================
SET search_path TO credit, public;

-- -----------------------------------------------------------------------------
-- 1. Enriched observations: the analytical base (fact + both dimensions)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW credit.vw_observations_enriched AS
SELECT
    f.observation_id,
    f.series_key,
    s.series_id,
    s.series_name,
    s.category,
    s.subcategory,
    s.unit,
    s.frequency,
    s.measure_type,
    s.source_key,
    f.date_key,
    f.observation_date,
    d.year,
    d.quarter,
    d.month,
    d.year_month,
    d.year_quarter,
    f.value
FROM credit.fact_observations f
JOIN credit.dim_series s ON s.series_key = f.series_key
JOIN credit.dim_date   d ON d.date_key   = f.date_key
WHERE f.value IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 2. Latest observation per series
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW credit.vw_latest_observation AS
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (PARTITION BY e.series_key
                           ORDER BY e.observation_date DESC) AS rn
    FROM credit.vw_observations_enriched e
)
SELECT series_key, series_id, series_name, category, subcategory,
       unit, frequency, measure_type, source_key,
       observation_date AS latest_date,
       value            AS latest_value
FROM ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- 3. Period-over-period change (previous observation of the same series)
--    For monthly series this is month-over-month; generically "previous period".
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW credit.vw_period_changes AS
WITH lagged AS (
    SELECT
        e.series_key, e.series_id, e.series_name, e.category,
        e.frequency, e.measure_type, e.unit,
        e.observation_date,
        e.value,
        LAG(e.value)            OVER w AS prev_value,
        LAG(e.observation_date) OVER w AS prev_date
    FROM credit.vw_observations_enriched e
    WINDOW w AS (PARTITION BY e.series_key ORDER BY e.observation_date)
)
SELECT
    series_key, series_id, series_name, category, frequency, measure_type, unit,
    observation_date, value, prev_value, prev_date,
    (value - prev_value) AS abs_change,
    CASE WHEN prev_value IS NULL OR prev_value = 0 THEN NULL
         ELSE ROUND(100.0 * (value - prev_value) / ABS(prev_value), 4)
    END AS pct_change
FROM lagged;

-- -----------------------------------------------------------------------------
-- 4. Year-over-year change (self-join to the observation ~1 year earlier).
--    Restricted to monthly/quarterly series whose dates align 1 year apart.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW credit.vw_yoy_change AS
SELECT
    cur.series_key, cur.series_id, cur.series_name, cur.category,
    cur.measure_type, cur.unit,
    cur.observation_date,
    cur.value                          AS value,
    prior.value                        AS value_year_ago,
    (cur.value - prior.value)          AS yoy_abs_change,
    CASE WHEN prior.value IS NULL OR prior.value = 0 THEN NULL
         ELSE ROUND(100.0 * (cur.value - prior.value) / ABS(prior.value), 4)
    END                                AS yoy_pct_change
FROM credit.vw_observations_enriched cur
JOIN credit.dim_series s ON s.series_key = cur.series_key
                        AND s.frequency IN ('monthly','quarterly')
JOIN credit.vw_observations_enriched prior
     ON prior.series_key = cur.series_key
    AND prior.observation_date = (cur.observation_date - INTERVAL '1 year')::date;

-- -----------------------------------------------------------------------------
-- 5. Rolling averages over the trailing 3 and 12 observations of each series.
--    For monthly series these are the 3-month and 12-month moving averages.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW credit.vw_rolling_averages AS
SELECT
    e.series_key, e.series_id, e.series_name, e.category, e.frequency, e.unit,
    e.observation_date,
    e.value,
    ROUND(AVG(e.value) OVER (PARTITION BY e.series_key ORDER BY e.observation_date
          ROWS BETWEEN 2  PRECEDING AND CURRENT ROW), 4) AS rolling_3_period_avg,
    ROUND(AVG(e.value) OVER (PARTITION BY e.series_key ORDER BY e.observation_date
          ROWS BETWEEN 11 PRECEDING AND CURRENT ROW), 4) AS rolling_12_period_avg
FROM credit.vw_observations_enriched e;

-- -----------------------------------------------------------------------------
-- 6. Full-history statistics + deviation of the latest point from history.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW credit.vw_historical_stats AS
WITH stats AS (
    SELECT
        series_key,
        COUNT(*)                       AS n_obs,
        MIN(value)                     AS hist_min,
        MAX(value)                     AS hist_max,
        ROUND(AVG(value), 4)           AS hist_avg,
        ROUND(STDDEV_SAMP(value), 4)   AS hist_stddev
    FROM credit.vw_observations_enriched
    GROUP BY series_key
)
SELECT
    l.series_key, l.series_id, l.series_name, l.category, l.unit, l.frequency,
    l.latest_date, l.latest_value,
    st.n_obs, st.hist_min, st.hist_max, st.hist_avg, st.hist_stddev,
    (l.latest_value - st.hist_avg) AS deviation_from_avg,
    CASE WHEN st.hist_stddev IS NULL OR st.hist_stddev = 0 THEN NULL
         ELSE ROUND((l.latest_value - st.hist_avg) / st.hist_stddev, 3)
    END AS latest_zscore
FROM credit.vw_latest_observation l
JOIN stats st ON st.series_key = l.series_key;

-- -----------------------------------------------------------------------------
-- 7. Rate spreads: prime and 5-year mortgage relative to the policy rate.
--    Posted rates are weekly (Wednesday); the policy rate is business-daily,
--    so a LEFT JOIN on date matches each weekly point to that day's policy rate.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW credit.vw_rate_spreads AS
WITH policy AS (
    SELECT observation_date, value AS policy_rate
    FROM credit.vw_observations_enriched WHERE series_id = 'V39079'
),
prime AS (
    SELECT observation_date, value AS prime_rate
    FROM credit.vw_observations_enriched WHERE series_id = 'V80691311'
),
mtg5 AS (
    SELECT observation_date, value AS mortgage_5yr_rate
    FROM credit.vw_observations_enriched WHERE series_id = 'V80691335'
)
SELECT
    p.observation_date,
    pol.policy_rate,
    p.prime_rate,
    m.mortgage_5yr_rate,
    (p.prime_rate - pol.policy_rate)        AS prime_minus_policy,
    (m.mortgage_5yr_rate - pol.policy_rate) AS mortgage5_minus_policy
FROM prime p
LEFT JOIN policy pol ON pol.observation_date = p.observation_date
LEFT JOIN mtg5  m   ON m.observation_date   = p.observation_date
ORDER BY p.observation_date;

-- -----------------------------------------------------------------------------
-- 8. Shares of tracked, non-aggregate Bank of Canada household credit
--    components. The consumer-credit total is excluded because its component
--    series are also present; this is not a measure of total household debt.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS credit.vw_category_share;
CREATE VIEW credit.vw_category_share AS
WITH hh AS (
    SELECT e.observation_date, e.series_id, e.series_name, e.subcategory, e.value
    FROM credit.vw_observations_enriched e
    WHERE e.category = 'Household Credit'
      AND e.measure_type = 'balance'
      AND e.source_key = 'bank_of_canada'
        AND e.subcategory <> 'Consumer credit total'
)
SELECT
    observation_date,
    series_id,
    series_name,
    subcategory,
    value,
        SUM(value) OVER (PARTITION BY observation_date) AS tracked_component_total,
    ROUND(100.0 * value
                    / NULLIF(SUM(value) OVER (PARTITION BY observation_date), 0), 3)
                    AS pct_of_tracked_components
FROM hh;

-- -----------------------------------------------------------------------------
-- 9. Monitoring alerts (SQL version): flag the latest point of each series when
--    it lies more than 2 standard deviations from its full-history mean.
--    Transparent, explainable, no black box. The Python engine adds a rolling
--    (recent-window) view; the reconciliation report compares the two.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW credit.vw_monitoring_alerts AS
SELECT
    series_id,
    series_name,
    category,
    unit,
    latest_date,
    latest_value,
    hist_avg,
    hist_stddev,
    latest_zscore,
    CASE
        WHEN latest_zscore IS NULL THEN 'INSUFFICIENT_DATA'
        WHEN ABS(latest_zscore) >= 3 THEN 'HIGH'
        WHEN ABS(latest_zscore) >= 2 THEN 'MEDIUM'
        ELSE 'NORMAL'
    END AS alert_level,
    CASE
        WHEN latest_zscore IS NULL THEN 'Not enough history to assess.'
        WHEN ABS(latest_zscore) >= 2 THEN
            'Latest value is ' || ROUND(ABS(latest_zscore),2)
            || ' standard deviations from its full-history average; review.'
        ELSE 'Latest value within normal historical range.'
    END AS alert_reason
FROM credit.vw_historical_stats;
