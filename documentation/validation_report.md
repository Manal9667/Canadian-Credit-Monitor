# Data Quality Validation Report

_Generated: 2026-09-27T01:14:20.845186+00:00_

This report is produced automatically by the validation framework (`python/validation`). Each rule records its status, the number of records affected, a severity grade, and a recommended action.

**Overall gate:** PASS - safe to load

---
## Source: bank_of_canada

- Observations checked: 11434
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
Records affected: 11
Severity: MEDIUM
Recommended action: Confirm source has not paused publication.
Details: stale_series: 11


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
