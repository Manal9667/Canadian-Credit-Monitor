# Analytical Questions

These are the practical questions the platform and its dashboard are built to
answer. They drive the SQL views, the analytical metrics, the monitoring engine,
and the four dashboard pages.

**Language discipline.** This project describes *observations* and *relationships*
in the data. It does not assert causation unless a specific analysis supports it.
Wording such as "co-movement", "observed change", "relationship", and "historical
deviation" is used deliberately in place of "X caused Y".

---

## A. Credit levels and growth

1. **How have Canadian household credit levels changed over time?**
   Measured by chartered-bank outstanding balances (consumer credit, credit
   cards, lines of credit, auto, mortgages) and by the long-run StatCan household
   credit market debt level.

2. **Which credit categories have experienced the largest growth?**
   Ranked by month-over-month, year-over-year, and multi-year change.

3. **How has the composition of household credit changed?**
   Each category's share of total household credit, and how those shares have
   shifted over time (e.g., secured vs. unsecured lines of credit; credit cards
   vs. mortgages).

## B. The rate environment

4. **How have lending rates changed relative to the Bank of Canada's policy rate?**
   Policy rate vs. prime vs. posted mortgage rates vs. effective lending rates,
   over time.

5. **What is the spread between key rates?**
   e.g., prime minus policy rate; posted 5-year mortgage minus policy rate; and
   how those spreads have widened or narrowed.

6. **Is there co-movement between the rate environment and credit growth?**
   Described as an observed relationship only — the dashboard shows the two side
   by side and quantifies correlation, without asserting that one caused the other.

## C. Recent change and historical context

7. **How does the latest period compare with historical averages?**
   Latest value vs. rolling 3-month / 12-month averages and vs. the full-history
   mean and standard deviation for each series.

8. **Which financial indicators have experienced unusually large recent movements?**
   Flagged by the monitoring engine using transparent z-score and
   percentage-change thresholds.

## D. Monitoring and reporting

9. **Which indicators should an analyst investigate further?**
   The monitoring engine produces a ranked list of series whose latest
   observation deviates materially from their recent historical range, each with
   a plain-language reason.

10. **What major changes should be highlighted in a management report?**
    The automated reporting layer summarizes the largest recent movements, the
    most notable rate changes, and any active monitoring alerts into a concise
    executive summary.

---

## Mapping questions to deliverables

| Question | SQL view / metric | Dashboard page |
|---|---|---|
| 1, 2 | `vw_period_changes`, `vw_yoy_change` | Credit Analytics |
| 3 | `vw_category_share` | Credit Analytics |
| 4, 5 | `vw_latest_observation`, `vw_rate_spreads` | Rate Environment |
| 6 | correlation in `metrics.py` + side-by-side visual | Rate Environment |
| 7 | `vw_historical_stats`, `vw_rolling_averages` | Executive Overview |
| 8, 9 | `anomaly_detection.py`, `vw_monitoring_alerts` | Monitoring & Insights |
| 10 | `reporting_summary.py`, `ai_report.py` | Monitoring & Insights |

## Explicitly out of scope

- Any claim of causality between rates and credit without a supporting model.
- Forecasting or forward-looking projections.
- Investment advice or recommendations of any kind.
- Institution-specific commentary (data is economy-wide / chartered-bank
  aggregate only).
