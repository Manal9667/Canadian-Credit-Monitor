-- =============================================================================
-- tables.sql - dimensional model (star schema)
-- =============================================================================
SET search_path TO credit, public;

-- -----------------------------------------------------------------------------
-- dim_source : one row per data source
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS credit.dim_source (
    source_key   TEXT PRIMARY KEY,               -- e.g. 'bank_of_canada'
    source_name  TEXT NOT NULL,                  -- e.g. 'Bank of Canada'
    service      TEXT NOT NULL,                  -- e.g. 'Valet API'
    licence      TEXT NOT NULL
);

COMMENT ON TABLE credit.dim_source IS 'Data source dimension.';

-- -----------------------------------------------------------------------------
-- dim_series : one row per financial series (the series dimension)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS credit.dim_series (
    series_key    INTEGER PRIMARY KEY,           -- surrogate key
    series_id     TEXT NOT NULL UNIQUE,          -- natural key (Valet/StatCan id)
    series_name   TEXT NOT NULL,
    category      TEXT NOT NULL,                 -- Policy Rate / Posted Rate / Household Credit / ...
    subcategory   TEXT,
    unit          TEXT NOT NULL,                 -- percent / millions_cad / ratio
    frequency     TEXT NOT NULL
                  CHECK (frequency IN ('daily','weekly','monthly','quarterly')),
    measure_type  TEXT NOT NULL
                  CHECK (measure_type IN ('rate','balance','ratio')),
    source_key    TEXT NOT NULL REFERENCES credit.dim_source(source_key)
);

COMMENT ON TABLE credit.dim_series IS 'Series dimension: describes each time series.';

-- -----------------------------------------------------------------------------
-- dim_date : daily calendar dimension
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS credit.dim_date (
    date_key        INTEGER PRIMARY KEY,         -- YYYYMMDD
    date            DATE NOT NULL UNIQUE,
    year            SMALLINT NOT NULL,
    quarter         SMALLINT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month           SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name      TEXT NOT NULL,
    year_month      TEXT NOT NULL,               -- 'YYYY-MM'
    year_quarter    TEXT NOT NULL,               -- 'YYYY-Q#'
    day_of_month    SMALLINT NOT NULL,
    is_month_end    BOOLEAN NOT NULL,
    is_quarter_end  BOOLEAN NOT NULL
);

COMMENT ON TABLE credit.dim_date IS 'Daily calendar dimension spanning the data range.';

-- -----------------------------------------------------------------------------
-- fact_observations : one row per series per observation date
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS credit.fact_observations (
    observation_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    series_key        INTEGER NOT NULL REFERENCES credit.dim_series(series_key),
    date_key          INTEGER NOT NULL REFERENCES credit.dim_date(date_key),
    observation_date  DATE NOT NULL,
    value             NUMERIC(18,4),             -- nullable: source suppressions allowed
    CONSTRAINT uq_fact_series_date UNIQUE (series_key, date_key)
);

COMMENT ON TABLE credit.fact_observations IS
  'Fact table: numeric observation per series per date. value may be NULL when the source suppresses a point.';
