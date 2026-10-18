# Data Quality Validation Report

_Generated: 2026-10-18T16:38:11.093449+00:00_

This report is produced automatically by the validation framework (`python/validation`). Each rule records its status, the number of records affected, a severity grade, and a recommended action.

Per-series source observation, snapshot retrieval, validation processing, and next expected publication dates are recorded in `data/processed/series_freshness.csv`. Expected dates are schedule projections, not guarantees.

**Overall gate:** PASS - safe to load

---
## Source: bank_of_canada

- Observations checked: 11465
- Series checked: 16
- Result: 9 PASS / 1 WARN / 0 FAIL
- Worst severity: MEDIUM

### DATA QUALITY CHECK

Check: Schema: required columns present
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None
Details: columns_checked: 4

### DATA QUALITY CHECK

Check: Missing observations (null values)
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None
Details: pct_missing: 0.0

### DATA QUALITY CHECK

Check: Duplicate series/date combinations
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Invalid / unparseable dates
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Observation dates in the future
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Negative values in balance/rate series
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None
Details: affected_series: 0

### DATA QUALITY CHECK

Check: Unit consistency per series
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Unexpected frequency gaps
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Extreme values (|z| > 6.0)
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Stale data (latest observation older than expected)
Status: WARN
Records affected: 5
Severity: MEDIUM
Recommended action: Confirm source has not paused publication.
Details: stale_series: {'V39079': {'age_days': 6, 'expected_next_publication_date': '2026-10-13', 'overdue_after_date': '2026-10-15'}, 'V80691311': {'age_days': 11, 'expected_next_publication_date': '2026-10-14', 'overdue_after_date': '2026-10-16'}, 'V80691333': {'age_days': 11, 'expected_next_publication_date': '2026-10-14', 'overdue_after_date': '2026-10-16'}, 'V80691334': {'age_days': 11, 'expected_next_publication_date': '2026-10-14', 'overdue_after_date': '2026-10-16'}, 'V80691335': {'age_days': 11, 'expected_next_publication_date': '2026-10-14', 'overdue_after_date': '2026-10-16'}}


## Source: statistics_canada

- Observations checked: 584
- Series checked: 4
- Result: 10 PASS / 0 WARN / 0 FAIL
- Worst severity: INFO

### DATA QUALITY CHECK

Check: Schema: required columns present
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None
Details: columns_checked: 4

### DATA QUALITY CHECK

Check: Missing observations (null values)
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None
Details: pct_missing: 0.0

### DATA QUALITY CHECK

Check: Duplicate series/date combinations
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Invalid / unparseable dates
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Observation dates in the future
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Negative values in balance/rate series
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None
Details: affected_series: 0

### DATA QUALITY CHECK

Check: Unit consistency per series
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Unexpected frequency gaps
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Extreme values (|z| > 6.0)
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None

### DATA QUALITY CHECK

Check: Stale data (latest observation older than expected)
Status: PASS
Records affected: 0
Severity: INFO
Recommended action: None
