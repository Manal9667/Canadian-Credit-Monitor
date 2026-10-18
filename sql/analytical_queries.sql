-- =============================================================================
-- analytical_queries.sql - example queries answering the analytical questions.
-- These are illustrative, ad-hoc queries (not persisted views). Each maps to a
-- question in documentation/analytical_questions.md.
-- =============================================================================
SET search_path TO credit, public;

-- Q2. Which credit categories have grown the most year-over-year? (latest month)
--     Demonstrates: CTE, window MAX, ranking, JOIN.
WITH latest_yoy AS (
    SELECT y.*,
           ROW_NUMBER() OVER (PARTITION BY series_key ORDER BY observation_date DESC) AS rn
    FROM credit.vw_yoy_change y
    WHERE measure_type = 'balance'
)
SELECT series_name, observation_date, value, yoy_abs_change, yoy_pct_change
FROM latest_yoy
WHERE rn = 1
ORDER BY yoy_pct_change DESC NULLS LAST;

-- Q3. Shares of tracked non-aggregate BoC household-credit components at the
--     latest month; this is not a total household-debt composition.
--     Demonstrates: subquery for MAX date, partitioned share, ORDER BY.
SELECT series_name, subcategory, value, pct_of_total
FROM credit.vw_category_share
WHERE observation_date = (SELECT MAX(observation_date) FROM credit.vw_category_share)
ORDER BY pct_of_total DESC;

-- Q4/Q5. Latest rate environment and spreads to the policy rate.
--     Demonstrates: filtering to the latest weekly posting.
SELECT observation_date, policy_rate, prime_rate, mortgage_5yr_rate,
       prime_minus_policy, mortgage5_minus_policy
FROM credit.vw_rate_spreads
WHERE observation_date = (SELECT MAX(observation_date) FROM credit.vw_rate_spreads);

-- Q6. Co-movement: align monthly credit-card balances with the month-end policy
--     rate to inspect their relationship (observation only, no causal claim).
--     Demonstrates: date_trunc, conditional aggregation, JOIN on month.
WITH cc AS (
    SELECT date_trunc('month', observation_date)::date AS m, value AS card_balance
    FROM credit.vw_observations_enriched WHERE series_id = 'V122667761'
),
pol AS (
    SELECT date_trunc('month', observation_date)::date AS m, AVG(value) AS avg_policy_rate
    FROM credit.vw_observations_enriched WHERE series_id = 'V39079'
    GROUP BY 1
)
SELECT cc.m AS month, cc.card_balance, pol.avg_policy_rate
FROM cc JOIN pol ON pol.m = cc.m
ORDER BY cc.m;

-- Q7. Latest value versus history for every series, most-deviant first.
--     Demonstrates: reuse of the historical-stats view.
SELECT series_name, category, latest_date, latest_value,
       hist_avg, hist_stddev, latest_zscore
FROM credit.vw_historical_stats
ORDER BY ABS(latest_zscore) DESC NULLS LAST;

-- Q8/Q9. Which indicators should an analyst investigate? (active alerts)
SELECT series_name, category, latest_date, latest_value, latest_zscore,
       alert_level, alert_reason
FROM credit.vw_monitoring_alerts
WHERE alert_level IN ('MEDIUM','HIGH')
ORDER BY ABS(latest_zscore) DESC;

-- Q1. Long-run household credit market debt (StatCan) with year-over-year growth.
--     Demonstrates: window LAG over quarterly data, CASE guard against divide-by-zero.
SELECT observation_date,
       value AS household_credit_market_debt_millions,
       ROUND(100.0 * (value - LAG(value, 4) OVER (ORDER BY observation_date))
             / NULLIF(LAG(value, 4) OVER (ORDER BY observation_date), 0), 2) AS yoy_pct_change
FROM credit.vw_observations_enriched
WHERE series_id = 'STATCAN_v1038036700'
ORDER BY observation_date;
