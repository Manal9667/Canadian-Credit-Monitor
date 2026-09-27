-- =============================================================================
-- Canadian Banking & Credit Intelligence Platform
-- schema.sql - schema creation and conventions
-- Target: PostgreSQL 13+
-- =============================================================================
-- Run order: schema.sql -> tables.sql -> indexes.sql -> views.sql
-- (analytical_queries.sql contains ad-hoc examples and is optional.)
--
-- This project uses ONLY public data (Bank of Canada, Statistics Canada).
-- It contains no confidential, customer, proprietary, or internal bank data.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS credit;

COMMENT ON SCHEMA credit IS
  'Public Canadian credit & rate indicators (Bank of Canada + Statistics Canada). Star schema.';

-- Make the schema the default target for the rest of the scripts in a session.
SET search_path TO credit, public;
