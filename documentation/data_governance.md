# Data Governance Framework

## Canadian Banking & Credit Intelligence Platform

**Version:** 1.0  
**Last Updated:** 2024-09-26  
**Classification:** Public Documentation

---

## 1. Governance Overview

This document establishes the data governance framework for the Canadian Banking & Credit Intelligence Platform.

**Scope:** Data ingestion, quality, transformation, storage, analytics, and reporting

**Objectives:**
- Ensure data quality and reliability
- Maintain reproducible, auditable processes
- Comply with data policies and regulations
- Document data lineage and ownership
- Support decision-making with trusted data

---

## 2. Critical Compliance Statement

**⚠️ IMPORTANT COMPLIANCE NOTE:**

This project uses **publicly available data only** from:
- Bank of Canada (public APIs and public data)
- Statistics Canada (public tables and downloads)
- Government of Canada (public datasets)

**This project does NOT contain, use, or reference:**
- CIBC confidential data
- CIBC customer data
- CIBC proprietary systems or internal data
- Any confidential banking information
- Any non-public financial data

**Data Source Licensing:**
- Bank of Canada data: Public domain
- Statistics Canada data: Government of Canada Open Government License
- All data is publicly available without restrictions

**Reproducibility:**
All data can be obtained independently by anyone using the same public sources and same methodology documented in this framework.

---

## 3. Data Sources

### Source 1: Bank of Canada Valet API

**Official Name:** Bank of Canada Valet API  
**URL:** https://www.bankofcanada.ca/rates/  
**Access Method:** REST API (no key required)  
**Data Type:** Financial time series  
**Frequency:** Daily for rates, as released by BoC

**Data Covered:**
- Policy (overnight) rate
- Mortgage lending rates
- Commercial lending rates
- Consumer lending rates
- Exchange rates

**Series Identifiers:**
- `FXUSDCAD` - USD/CAD exchange rate
- `LOOKPD` - Bank of Canada policy rate (overnight)
- Various lending rate series

**Update Frequency:** Daily (subject to BoC release schedule)

**Historical Coverage:** 1990s - Present

**Data Quality:** High (official government agency)

**Access Restrictions:** None (public data)

**Terms of Use:** Public domain (attribute Bank of Canada)

**Contact:** Bank of Canada - Data Services

---

### Source 2: Statistics Canada - Household Credit

**Official Name:** Statistics Canada - Household Credit (Table 11-10-0140-01)  
**URL:** https://www150.statcan.gc.ca/  
**Access Method:** Data Download Center / API  
**Data Type:** Quarterly household credit balances  
**Frequency:** Quarterly

**Data Covered:**
- Total household credit
- Mortgage credit
- Credit card credit
- Personal loans
- Other consumer credit

**Table ID:** 11-10-0140-01  
**Frequency:** Quarterly  
**Update Frequency:** ~60 days after quarter end  
**Historical Coverage:** 1990 - Present  

**Data Quality:** High (official government agency)

**Access Restrictions:** None (public data)

**Terms of Use:** Government of Canada Open Government License

**Contact:** Statistics Canada - Data Dissemination Services

---

### Source 3: Statistics Canada - Credit Card Balances

**Official Name:** Statistics Canada - Credit Card Balances (Table 11-10-0015-01)  
**URL:** https://www150.statcan.gc.ca/  
**Access Method:** Data Download Center  
**Data Type:** Monthly credit card balances  
**Frequency:** Monthly

**Data Covered:**
- Personal credit card balances
- Revolving credit limits
- Utilization rates

**Table ID:** 11-10-0015-01  
**Frequency:** Monthly  
**Update Frequency:** ~35 days after month end  
**Historical Coverage:** 2000 - Present  

**Data Quality:** High (official government agency)

**Access Restrictions:** None (public data)

**Terms of Use:** Government of Canada Open Government License

---

## 4. Data Ownership & Responsibility

| Component | Owner | Contact | Responsibility |
|-----------|-------|---------|-----------------|
| Data Ingestion | Data Engineer | Team Lead | Reliable retrieval, error handling |
| Data Validation | QA Analyst | Team Lead | Quality rules, monitoring |
| Data Transformation | Analytics Engineer | Analytics Lead | Logic, testing, documentation |
| Database (PostgreSQL) | Database Admin | DBA | Schema, maintenance, backups |
| Power BI Model | BI Developer | BI Lead | Design, relationships, performance |
| Reports & Analytics | Business Analyst | Analytics Lead | Accuracy, relevance, delivery |
| Governance Compliance | Compliance Officer | Compliance | Policy adherence, audit |

---

## 5. Data Quality Framework

### 5.1 Data Quality Dimensions

**Completeness:** All expected observations present?
- Check: No missing dates for active series
- Check: No null values in key columns
- Threshold: 99% completeness required

**Accuracy:** Values correct and aligned with source?
- Check: Spot-check 5% of loaded values against source
- Check: Schema validation (data types, formats)
- Threshold: 100% accuracy required

**Consistency:** Values consistent with other sources?
- Check: Cross-source correlation analysis
- Check: Historical trends logical
- Threshold: Explained deviations only

**Timeliness:** Data current and fresh?
- Check: Retrieval date vs. latest available
- Check: Lag from source publication
- Threshold: Source-specific expected publication date plus the documented frequency-specific grace window in `documentation/methodology.md`; retrieval and processing timestamps do not substitute for observation dates.

**Validity:** Values within expected ranges?
- Check: Numeric ranges (no negative household credit, etc.)
- Check: Date ordering (chronological)
- Threshold: 100% valid required

---

### 5.2 Validation Rules

**VR-001: No Duplicate Observations**
- **Test:** SELECT series_id, observation_date, COUNT(*) ... GROUP BY series_id, observation_date HAVING COUNT(*) > 1
- **Action:** Reject and log duplicates
- **Severity:** CRITICAL

**VR-002: Chronological Ordering**
- **Test:** Verify no observation_date out of order
- **Action:** Log and investigate
- **Severity:** ERROR

**VR-003: Date Format Valid**
- **Test:** All dates parse as YYYY-MM-DD
- **Action:** Reject invalid dates
- **Severity:** CRITICAL

**VR-004: Numeric Values Valid**
- **Test:** Values are numeric and finite (not NaN/Inf)
- **Action:** Log as ERROR or null if applicable
- **Severity:** ERROR

**VR-005: Frequency Consistency**
- **Test:** Observations match series frequency (monthly, quarterly, etc.)
- **Action:** Log gaps and investigate
- **Severity:** WARNING

**VR-006: Value Range Validation**
- **Test:** Series-specific reasonable ranges
  - Household credit: $100B - $1.5T (CAD)
  - Policy rate: -2% to 10%
  - Exchange rate: 1.0 - 1.5
- **Action:** Extreme values logged for investigation
- **Severity:** WARNING

**VR-007: Foreign Key Integrity**
- **Test:** All series_id, source_id exist in dimension tables
- **Action:** Reject rows with invalid FKs
- **Severity:** CRITICAL

**VR-008: Schema Validation**
- **Test:** Columns match expected schema
- **Action:** Alert if schema changes detected
- **Severity:** CRITICAL

---

### 5.3 Data Quality Acceptance Criteria

A data load is acceptable if:
- [ ] VR-001 through VR-004 (CRITICAL) pass 100%
- [ ] VR-007 (Foreign Key) passes 100%
- [ ] VR-005, VR-006 (WARNING) pass with documented exceptions
- [ ] < 1% of observations flagged for quality issues
- [ ] All anomalies are explained or investigated
- [ ] Validation report generated and reviewed

---

## 6. Data Transformation & Lineage

### 6.1 Transformation Stages

**Stage 1: Raw Ingestion**
- **Input:** API/download from public sources
- **Processing:** Minimal - preserve source format
- **Output:** `data/raw/` (immutable)
- **Owner:** Data Engineer

**Stage 2: Validation & Cleaning**
- **Input:** Raw data
- **Processing:** Validation rules applied, cleaning where appropriate
- **Output:** `data/processed/fact_observations.csv`
- **Owner:** QA / Data Engineer

**Stage 3: Transformation**
- **Input:** Validated data
- **Processing:** Business logic (derived metrics, aggregations)
- **Output:** `data/processed/analytical_metrics.csv`
- **Owner:** Analytics Engineer

**Stage 4: Database Loading**
- **Input:** Transformed data
- **Processing:** PostgreSQL load with constraints
- **Output:** PostgreSQL tables (FACT, DIMENSIONS)
- **Owner:** Database Admin

**Stage 5: Analytics Layer**
- **Input:** PostgreSQL tables
- **Processing:** SQL views (analytical queries)
- **Output:** SQL views for Power BI
- **Owner:** Analytics Engineer

**Stage 6: Business Intelligence**
- **Input:** SQL views / PostgreSQL
- **Processing:** Power BI model (relationships, measures)
- **Output:** Power BI dashboard
- **Owner:** BI Developer

---

### 6.2 Data Lineage Diagram

```
Bank of Canada API ─┐
                    ├─→ Python Ingestion ─→ Raw CSV ─→ Validation ─→ Processed CSV
Statistics Canada   ┤                                      ↓
                    │                                    Testing
Government Canada ──┘                                      ↓
                                          PostgreSQL Tables (FACT + DIM)
                                                      ↓
                                          SQL Analytical Views
                                                      ↓
                                          Power Query (Transform)
                                                      ↓
                                          Power BI Model (Star Schema)
                                                      ↓
                                          DAX Measures + Calculated Columns
                                                      ↓
                                          Dashboards + Automated Reports
```

---

## 7. Data Refresh Process

### 7.1 Refresh Cadence

| Component | Frequency | Time | Owner | SLA |
|-----------|-----------|------|-------|-----|
| BoC Rates | Daily | 9:00 AM ET | Data Eng | < 2 hours after release |
| Stats Canada Data | Quarterly | Week of release | Data Eng | < 3 days after release |
| Validation Checks | Per load | Automatic | QA | Immediate |
| SQL Views | Per load | Automatic | Analytics | Immediate |
| Power BI | Per load | 11:00 AM ET | BI Dev | < 30 min after DB update |
| Automated Reports | Weekly | Monday 8:00 AM | Reporting | Automatic |

### 7.2 Refresh Process Steps

1. **Ingestion** (Automated)
   - Retrieve latest data from sources
   - Log retrieval timestamp and status
   - Save to `data/raw/`

2. **Validation** (Automated)
   - Run all validation rules
   - Generate validation report
   - Alert if critical failures

3. **Transformation** (Automated)
   - Apply business logic
   - Calculate derived metrics
   - Save to `data/processed/`

4. **Database Load** (Automated)
   - Verify schema and constraints
   - Load into PostgreSQL
   - Reconcile with previous load

5. **Analytics** (Automated)
   - Refresh SQL views
   - Update analytical metrics
   - Generate monitoring alerts

6. **BI Refresh** (Automated)
   - Power BI connects to PostgreSQL
   - Auto-refresh on schedule
   - Alert on failures

7. **Reporting** (Scheduled)
   - Generate automated reports
   - Send to stakeholders
   - Archive for audit

### 7.3 Failure Handling

**If ingestion fails:**
- Alert DBA/Data Engineer immediately
- Do NOT load partial data
- Retain previous day's load
- Investigate and retry within SLA

**If validation fails:**
- Hold data for review
- Generate exception report
- Do NOT promote to analytics
- Escalate to QA lead

**If Power BI refresh fails:**
- Alert BI Developer
- Dashboard shows last successful load date
- Do NOT publish stale data
- Retry on next scheduled cycle

---

## 8. Data Assumptions & Limitations

### 8.1 Key Assumptions

1. **Public Data Stability:** Bank of Canada and Statistics Canada data remain publicly available and unchanged in format
2. **No Real-Time Updates:** Data is batch-based, not real-time
3. **Canadian Scope Only:** No international data
4. **Historical Accuracy:** No retroactive corrections to published data are incorporated
5. **API Availability:** Bank of Canada API available 99% of the time

### 8.2 Known Limitations

1. **Data Lag:** Statistics Canada data lags release by ~60 days (quarterly data published ~2 months after quarter end)
2. **Frequency Mismatch:** Different metrics at different frequencies (daily rates vs. quarterly credit)
3. **Revisions:** Statistics Canada may revise historical data; current system does not track revisions
4. **Definitions:** Series definitions may change over time; not tracked in current system
5. **Missing Data:** Some historical periods may have missing observations for certain series
6. **Scope:** Household credit focus; business credit and government lending not included
7. **Drill-Down Limited:** Cannot drill below published series level (no transaction data)

### 8.3 Scope Not Covered

This project does NOT include:
- Real-time intraday updates
- Granular transaction data
- Customer-level data
- Confidential CIBC data
- Proprietary financial models
- Forecasting or predictions (data-only)
- Non-Canadian geographies
- Cross-border transaction detail

---

## 9. Security & Data Protection

### 9.1 Data Classification

**Classification Level:** PUBLIC

All data in this project is publicly available and does not require special security handling beyond standard practices.

**Public Attribute:** All data from public sources (Bank of Canada, Statistics Canada)

**No Special Handling Required:**
- No encryption at rest required
- No special access controls
- Standard backups sufficient
- No audit logging required for access

### 9.2 Credential Management

**No Credentials Required:**
- Bank of Canada API: No key needed
- Statistics Canada: Public download
- PostgreSQL: Standard credentials (not committed to repo)

**GitHub Security:**
- No API keys in code
- No database credentials
- `.env.example` provided as template
- `.gitignore` excludes credential files

### 9.3 Access Control

**Public Repository:** Project can be public (no confidential data)

**Data Access:**
- PostgreSQL: Local connection only (development)
- Production: Standard database access controls
- Power BI: Team members only (standard AAD/organizational controls)

---

## 10. Reproducibility

### 10.1 Reproducibility Standards

The project is designed to be fully reproducible:

1. **Source Data:** All from public, downloadable sources
2. **Ingestion Logic:** Documented in Python code with comments
3. **Transformations:** SQL + Python transformations documented
4. **Database Schema:** SQL scripts version-controlled
5. **Analytics:** SQL views documented
6. **BI Model:** Power BI model documented
7. **Configuration:** Environment variables documented

### 10.2 Reproduction Instructions

**Anyone can reproduce the analysis:**

1. Clone repository: `git clone <repo>`
2. Install dependencies: `pip install -r requirements.txt`
3. Configure environment: Copy `.env.example` to `.env`
4. Run ingestion: `python -m python.ingestion.bank_of_canada`
5. Run validation: `python -m python.validation.engine`
6. Load database: `python -m python.db.load_postgres`
7. View results in Power BI or SQL queries

**Expected Result:** Identical metrics and visualizations

**Time Estimate:** < 1 hour for full reproducibility

---

## 11. Audit & Compliance

### 11.1 Audit Trail

**Logging:**
- Ingestion: Source, retrieval date, status
- Validation: Rule run, pass/fail, count
- Database: Load timestamp, row count, status
- Reports: Generation timestamp, data freshness

**Retention:**
- Logs retained for 12 months
- Validation reports retained for 12 months
- Data files retained indefinitely (immutable)

### 11.2 Compliance Checklist

**Data Governance:**
- [x] Data sources documented
- [x] Ownership defined
- [x] Quality rules documented
- [x] Refresh process documented
- [x] Assumptions documented
- [x] Limitations documented

**Technical Controls:**
- [x] Validation rules automated
- [x] Schema constraints enforced
- [x] Error handling implemented
- [x] Logging implemented
- [x] Code version-controlled

**Security:**
- [x] No credentials in code
- [x] Public data only
- [x] Access controls defined
- [x] Data lineage documented

**Reproducibility:**
- [x] Configuration externalized
- [x] Dependencies specified
- [x] Process documented
- [x] Scripts automated
- [x] Version control

---

## 12. Future Governance Enhancements

1. **Data Catalog:** Central registry of all data assets
2. **Lineage Tracking:** Automated impact analysis
3. **Change Management:** Formal process for schema/logic changes
4. **Reconciliation Framework:** Automated data reconciliation
5. **Compliance Automation:** Continuous compliance monitoring
6. **Incident Management:** Formal incident tracking and resolution
7. **SLA Monitoring:** Automated SLA tracking and alerts

---

## 13. Governance Contact

**Data Governance Officer:** [Project Lead]  
**Escalation:** [Compliance Officer]  
**Questions:** [Data Governance Email]

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-09-26 | Project Team | Initial framework |
