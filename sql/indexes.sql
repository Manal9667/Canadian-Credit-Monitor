-- =============================================================================
-- indexes.sql - supporting indexes for analytical query patterns
-- =============================================================================
SET search_path TO credit, public;

-- Fact table is queried predominantly by series over time, so a composite
-- (series_key, observation_date) index supports window functions ordered by
-- date within each series (LAG, rolling frames, YoY self-joins).
CREATE INDEX IF NOT EXISTS ix_fact_series_date
    ON credit.fact_observations (series_key, observation_date);

-- Date-key joins to the calendar dimension.
CREATE INDEX IF NOT EXISTS ix_fact_date_key
    ON credit.fact_observations (date_key);

-- Filtering series by analytical category (e.g. all Household Credit balances).
CREATE INDEX IF NOT EXISTS ix_series_category
    ON credit.dim_series (category);

-- Filtering the calendar by month-end / quarter-end for period-end reporting.
CREATE INDEX IF NOT EXISTS ix_date_month_end
    ON credit.dim_date (is_month_end) WHERE is_month_end;
