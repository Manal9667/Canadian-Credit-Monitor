# Data Sources

This project uses **only publicly available Canadian financial and economic data**.
It contains no CIBC data and no confidential, customer, proprietary, or internal
information from any financial institution. Every series listed below was verified
against the live public API before being added to the pipeline.

Coverage figures reflect the data actually retrieved by the ingestion pipeline
(see `data/raw/*/series_metadata.csv`).

---

## Source 1 — Bank of Canada (primary source)

| Attribute | Detail |
|---|---|
| Source name | Bank of Canada |
| Service | Valet API (public) |
| Official URL | https://www.bankofcanada.ca/valet/docs |
| Terms of use | https://www.bankofcanada.ca/terms/ |
| API key required | **No** |
| Access mechanism | REST/JSON: `GET /valet/observations/{seriesId}/json` |
| Update frequency | Policy rate: business-daily; posted rates: weekly (Wed); credit aggregates: monthly |
| Licensing | Public data, free to use with attribution to the Bank of Canada |

### Why this source
The Bank of Canada is the authoritative publisher of Canadian policy rates,
chartered-bank posted lending rates, and the chartered-bank credit aggregates
("A4" tables). A single, keyless, well-documented API covers **policy rates,
lending rates, and credit balances**, which is exactly the scope this platform
monitors. It is the backbone of the project.

### Series ingested (16)

**Rates**

| Series ID | Measures | Frequency | Unit | Coverage |
|---|---|---|---|---|
| V39079 | Target for the overnight rate (policy rate) | Daily | % | 2009-04-21 → 2026-09-24 |
| V80691311 | Chartered-bank prime lending rate | Weekly | % | 2000-01-05 → 2026-09-23 |
| V80691333 | Conventional mortgage rate, 1-year | Weekly | % | 2000-01-05 → 2026-09-23 |
| V80691334 | Conventional mortgage rate, 3-year | Weekly | % | 2000-01-05 → 2026-09-23 |
| V80691335 | Conventional mortgage rate, 5-year | Weekly | % | 2000-01-05 → 2026-09-23 |

**Credit balances (chartered banks, A4 — month-end, $ millions)**

| Series ID | Measures | Coverage |
|---|---|---|
| V122667758 | Consumer credit, total (outstanding) | 2016-07 → 2026-06 |
| V122667761 | Credit card loans (outstanding) | 2016-07 → 2026-06 |
| V122667762 | Personal lines of credit, secured (outstanding) | 2016-07 → 2026-06 |
| V122667763 | Personal lines of credit, unsecured (outstanding) | 2016-07 → 2026-06 |
| V122667760 | Auto loans (outstanding) | 2016-07 → 2026-06 |
| V122667736 | Residential mortgages, insured, total (outstanding) | 2016-07 → 2026-06 |
| V122667742 | Residential mortgages, uninsured, total (outstanding) | 2016-07 → 2026-06 |
| V122667770 | Business loans, total (outstanding) | 2016-07 → 2026-06 |

**Effective lending rates (chartered banks, A4 — month-end, %)**

| Series ID | Measures | Coverage |
|---|---|---|
| V122667809 | Consumer credit, total (effective rate) | 2016-07 → 2026-06 |
| V122667812 | Credit card loans (effective rate) | 2016-07 → 2026-06 |
| V122667821 | Business loans, total (effective rate) | 2016-07 → 2026-06 |

> Note on coverage: the Bank of Canada A4 chartered-bank credit dataset begins in
> July 2016, so all monthly credit/rate series share that start date. The posted
> rate series reach back to 2000 and the daily policy-rate series to 2009. The
> pipeline adapts to whatever history each series actually provides rather than
> assuming a common window.

---

## Source 2 — Statistics Canada (secondary source)

| Attribute | Detail |
|---|---|
| Source name | Statistics Canada |
| Service | Web Data Service (WDS) |
| Official URL | https://www.statcan.gc.ca/en/developers/wds |
| Table | 38-10-0238 — Household sector credit market summary table |
| Table URL | https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3810023801 |
| API key required | **No** |
| Access mechanism | `GET /getFullTableDownloadCSV/{productId}/en` → returns a URL to the official CSV zip, which the pipeline downloads and parses |
| Update frequency | Quarterly (national balance sheet accounts) |
| Licensing | [Statistics Canada Open Licence](https://www.statcan.gc.ca/en/reference/licence) |

### Why this source
The Bank of Canada A4 data measures credit **held on chartered-bank balance
sheets** from 2016 onward. Statistics Canada's household-sector credit summary
adds two things the A4 data cannot: (1) a long macro history back to **1990**,
and (2) the widely-watched **household-debt-to-disposable-income ratio**, a
headline indicator of household credit stress. Together the two sources let the
platform show both the recent bank-level detail and the long-run household
context.

### Series ingested (4)

| StatCan vector | Series | Frequency | Unit | Coverage |
|---|---|---|---|---|
| v1038036698 | Household credit market debt to disposable income | Quarterly | ratio | 1990-Q1 → 2026-Q2 |
| v1038036700 | Household credit market debt (level) | Quarterly | $ millions | 1990-Q1 → 2026-Q2 |
| v1038036701 | Household consumer credit liabilities (level) | Quarterly | $ millions | 1990-Q1 → 2026-Q2 |
| v1038036703 | Household mortgage liabilities (level) | Quarterly | $ millions | 1990-Q1 → 2026-Q2 |

> Vector IDs are **not** hard-coded in the request. The ingester downloads the
> official table and selects rows by the human-readable `Categories` descriptor
> (configured in `config/series_config.json`), then records whatever `VECTOR`
> StatCan assigns as metadata. If StatCan renames a category, the ingester logs a
> schema-change warning instead of silently dropping the series.

---

## Sources considered but not included

- **CMHC / housing-start data** — useful context, but overlaps with mortgage
  credit already covered and would add a third retrieval mechanism without a
  clear analytical gain. Excluded to keep the project focused (per the brief:
  do not add sources merely to increase technology count).
- **StatCan CPI (18-10-0004)** — the WDS mechanism was verified against this
  table during research, but inflation is out of scope for a credit/lending
  monitoring platform, so it is documented here only as a validated fallback
  example of the CSV-download mechanism.

---

## Data not available / not fabricated

The brief asked about several metrics that are **not** available as clean public
series and are therefore **not** included (rather than fabricated):

- Institution-level (e.g., single-bank) lending or deposit figures — not public.
- Delinquency / default / charge-off rates by product — not published as a clean
  public API series at the granularity implied.
- Any forward-looking or proprietary risk metric.

Where a desired metric was unavailable, the project adapts to the real data
instead of inventing values.
