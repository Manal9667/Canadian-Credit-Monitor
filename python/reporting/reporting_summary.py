"""Automated Reporting System.

Purpose: Generate concise management summaries highlighting:
  - Largest recent changes
  - Unusual movements
  - Important rate changes
  - Monitoring alerts
  - Historical context
  - Suggested areas for investigation

Output: Structured reports saved as CSV and markdown for dashboard/email.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from ..common.config import PROCESSED_DIR
from ..common.logging_utils import get_logger

logger = get_logger("reporting.reporting_summary")

FACT_CSV = PROCESSED_DIR / "fact_observations.csv"
SERIES_CSV = PROCESSED_DIR / "dim_series.csv"
ALERTS_CSV = PROCESSED_DIR / "monitoring_alerts.csv"
METRICS_CSV = PROCESSED_DIR / "metrics_timeseries.csv"
SUMMARY_CSV = PROCESSED_DIR / "metrics_summary.csv"
PIPELINE_METADATA = PROCESSED_DIR / "pipeline_metadata.json"
VALIDATION_CSV = PROCESSED_DIR / "validation_results.csv"

REPORT_DIR = PROCESSED_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_MARKDOWN = REPORT_DIR / "automated_summary.md"
REPORT_CSV = REPORT_DIR / "automated_summary.csv"


class ReportingEngine:
    """Generate automated management reports from verified metrics."""

    def __init__(self):
        """Initialize reporting engine with metric data."""
        self.fact = None
        self.series = None
        self.alerts = None
        self.metrics = None
        self.summary = None
        self.pipeline_metadata = None
        self.validation = None
        self.report_date = datetime.now(timezone.utc)

    def load_data(self) -> bool:
        """Load all required data files. Return True if successful."""
        try:
            self.fact = pd.read_csv(FACT_CSV, parse_dates=["observation_date"])
            self.series = pd.read_csv(SERIES_CSV)
            self.alerts = pd.read_csv(ALERTS_CSV, parse_dates=["observation_date"])
            self.metrics = pd.read_csv(METRICS_CSV, parse_dates=["observation_date"])
            self.summary = pd.read_csv(SUMMARY_CSV, parse_dates=["latest_date"])
            self.pipeline_metadata = json.loads(
                PIPELINE_METADATA.read_text(encoding="utf-8")
            )
            self.validation = pd.read_csv(VALIDATION_CSV)
            logger.info("Reporting engine: data loaded successfully")
            return True
        except Exception as e:
            logger.error("Failed to load reporting data: %s", e)
            return False

    def get_largest_changes(self, top_n: int = 5) -> list[dict[str, Any]]:
        """Identify largest absolute changes from each series' prior observation."""
        if self.metrics is None or len(self.metrics) == 0:
            return []

        latest = self.metrics.sort_values("observation_date").groupby("series_id").tail(1)
        latest = latest[latest["abs_change"].notna()].copy()
        latest["abs_change_rank"] = latest["abs_change"].abs()
        largest = latest.nlargest(top_n, "abs_change_rank")

        results = []
        for _, row in largest.iterrows():
            results.append({
                "series_name": row.get("series_name", "Unknown"),
                "category": row.get("category", ""),
                "absolute_change": float(row["abs_change"]),
                "pct_change": float(row["pct_change"]) if pd.notna(row["pct_change"]) else None,
                "current_value": float(row["value"]),
                "unit": row.get("unit", ""),
                "observation_date": row.get("observation_date", ""),
            })
        return results

    def get_active_alerts(self, top_n: int = 10) -> list[dict[str, Any]]:
        """Get current monitoring alerts ranked by severity."""
        if self.alerts is None or len(self.alerts) == 0:
            return []

        active = self.alerts.loc[self.alerts["is_alert"].fillna(False)].copy()
        active["severity_rank"] = active["severity"].map(
            {"HIGH": 1, "MEDIUM": 2, "LOW": 3}
        )
        active = active.sort_values("severity_rank").head(top_n)

        results = []
        for _, row in active.iterrows():
            results.append({
                "series_name": row.get("series_name", "Unknown"),
                "category": row.get("category", ""),
                "severity": row.get("severity", "MEDIUM"),
                "current_value": float(row.get("value", 0)),
                "zscore": float(row.get("zscore", 0)) if pd.notna(row.get("zscore")) else None,
                "reason": row.get("reason", "No explanation"),
                "observation_date": row.get("observation_date", ""),
            })
        return results

    def get_rate_movements(self, top_n: int = 5) -> list[dict[str, Any]]:
        """Highlight important rate changes."""
        if self.metrics is None or len(self.metrics) == 0:
            return []

        rates = self.metrics[self.metrics["measure_type"] == "rate"].copy()
        if len(rates) == 0:
            return []

        latest = rates.sort_values("observation_date").groupby("series_id").tail(1)
        latest = latest[latest["abs_change"].notna()].copy()
        latest["abs_change_rank"] = latest["abs_change"].abs()
        largest = latest.nlargest(top_n, "abs_change_rank")

        results = []
        for _, row in largest.iterrows():
            results.append({
                "series_name": row.get("series_name", "Unknown"),
                "current_rate": float(row["value"]),
                "period_change": float(row["abs_change"]),
                "change_yoy": float(row["yoy_abs_change"])
                if pd.notna(row.get("yoy_abs_change"))
                else None,
                "unit": row.get("unit", "%"),
                "observation_date": row.get("observation_date", ""),
            })
        return results

    def get_credit_trends(self) -> dict[str, dict[str, Any]]:
        """Summarize credit category trends."""
        if self.metrics is None or len(self.metrics) == 0:
            return {}

        credit = self.metrics[
            self.metrics["category"].str.contains("Credit", case=False, na=False)
        ].copy()
        if len(credit) == 0:
            return {}

        credit = credit[credit["measure_type"].isin(["balance", "ratio"])]
        latest = credit.sort_values("observation_date").groupby("series_id").tail(1)

        results = {}
        for _, row in latest.iterrows():
            series_name = row.get("series_name", "Unknown")
            results[series_name] = {
                "current_value": float(row["value"]),
                "pct_change_yoy": float(row["yoy_pct_change"])
                if pd.notna(row.get("yoy_pct_change"))
                else None,
                "unit": row.get("unit", "$M"),
                "observation_date": row.get("observation_date", ""),
            }
        return results

    def get_historical_context(self, series_id: str) -> dict[str, Any]:
        """Get statistical context for a series."""
        if self.summary is None:
            return {}

        series_data = self.summary[self.summary["series_id"] == series_id].copy()
        if len(series_data) == 0:
            return {}

        latest = series_data.iloc[-1]
        return {
            "current_value": float(latest.get("current_value", 0)),
            "historical_average": float(latest.get("hist_avg", 0))
            if pd.notna(latest.get("hist_avg"))
            else None,
            "historical_std_dev": float(latest.get("hist_stddev", 0))
            if pd.notna(latest.get("hist_stddev"))
            else None,
            "zscore": float(latest.get("latest_zscore", 0))
            if pd.notna(latest.get("latest_zscore"))
            else None,
            "percentile_rank": float(latest.get("percentile_rank", 0))
            if pd.notna(latest.get("percentile_rank"))
            else None,
        }

    def generate_insights(self) -> dict[str, Any]:
        """Synthesize all insights into structured report."""
        insights = {
            "report_date": self.report_date.strftime("%Y-%m-%d"),
            "report_timestamp": self.report_date.isoformat(),
            "largest_changes": self.get_largest_changes(top_n=5),
            "active_alerts": self.get_active_alerts(top_n=10),
            "rate_movements": self.get_rate_movements(top_n=5),
            "credit_trends": self.get_credit_trends(),
            "source_provenance": self.pipeline_metadata.get("source_provenance", []),
            "data_quality_issues": self.validation[
                self.validation["status"].isin(["WARN", "FAIL"])
            ].to_dict("records"),
        }
        return insights

    def format_markdown(self, insights: dict[str, Any]) -> str:
        """Format insights as markdown for email/dashboard."""
        md = []
        md.append("# Canadian Banking Intelligence - Automated Report")
        md.append(f"\n**Report Date:** {insights['report_date']}")
        md.append(f"**Generated:** {insights['report_timestamp']}\n")
        md.append("**Source snapshots:**\n")
        for source in insights["source_provenance"]:
            md.append(
                f"- {source['source']}: `{source['snapshot']}`, retrieved "
                f"{source['retrieved_utc']}\n"
            )
        md.append("\n**Validation warnings and failures:**\n")
        if insights["data_quality_issues"]:
            for issue in insights["data_quality_issues"]:
                md.append(
                    f"- {issue['source']}: {issue['rule']} "
                    f"({issue['severity']}, {issue['records_affected']} affected)\n"
                )
        else:
            md.append("- None reported by the latest validation run.\n")

        md.append("---\n")

        # Executive Summary
        md.append("## Executive Summary\n")
        md.append(
            "This report highlights the largest recent movements, active monitoring alerts, "
            "and areas requiring analyst investigation across Canadian financial indicators.\n"
        )

        # Largest Changes
        md.append("\n## Largest Recent Changes\n")
        if insights["largest_changes"]:
            md.append(
                "| Series | Change | % Change | Unit | Date |\n"
                "| --- | --- | --- | --- | --- |"
            )
            for item in insights["largest_changes"]:
                pct_change = (
                    f"{item['pct_change']:.2f}%"
                    if item["pct_change"] is not None
                    else "N/A"
                )
                md.append(
                    f"| {item['series_name']} | "
                    f"{item['absolute_change']:.2f} | "
                    f"{pct_change} | "
                    f"{item['unit']} | "
                    f"{item['observation_date']} |"
                )
        else:
            md.append("No recent changes detected.\n")

        # Active Alerts
        md.append("\n## Active Monitoring Alerts\n")
        if insights["active_alerts"]:
            md.append(
                "**Important:** These are statistical anomalies flagged for investigation. "
                "They do NOT indicate a financial risk or constitute advice.\n\n"
            )
            for item in insights["active_alerts"]:
                md.append(f"### {item['series_name']}\n")
                md.append(f"- **Severity:** {item['severity']}\n")
                md.append(f"- **Current Value:** {item['current_value']:.2f}\n")
                if item["zscore"] is not None:
                    md.append(f"- **Z-Score:** {item['zscore']:.2f}\n")
                md.append(f"- **Reason:** {item['reason']}\n")
                md.append(f"- **Date:** {item['observation_date']}\n\n")
        else:
            md.append("No active alerts.\n")

        # Rate Movements
        md.append("\n## Rate Environment\n")
        if insights["rate_movements"]:
            md.append(
                "| Rate | Current | Period Δ (pp) | YoY Δ (pp) | Date |\n"
                "| --- | --- | --- | --- | --- |"
            )
            for item in insights["rate_movements"]:
                yoy = f"{item['change_yoy']:.2f}" if item["change_yoy"] is not None else "N/A"
                md.append(
                    f"| {item['series_name']} | "
                    f"{item['current_rate']:.2f}% | "
                    f"{item['period_change']:.2f} | "
                    f"{yoy} | "
                    f"{item['observation_date']} |"
                )
        else:
            md.append("No rate data available.\n")

        # Credit Trends
        md.append("\n## Credit Trends\n")
        if insights["credit_trends"]:
            md.append(
                "| Credit Category | Current | YoY Growth | Date |\n"
                "| --- | --- | --- | --- |"
            )
            for name, item in insights["credit_trends"].items():
                yoy = (
                    f"{item['pct_change_yoy']:.2f}%"
                    if item["pct_change_yoy"] is not None
                    else "N/A"
                )
                md.append(
                    f"| {name} | "
                    f"{item['current_value']:,.0f} {item['unit']} | "
                    f"{yoy} | "
                    f"{item['observation_date']} |"
                )
        else:
            md.append("No credit data available.\n")

        # Disclaimers
        md.append("\n---\n")
        md.append("## Methodology & Disclaimers\n")
        md.append(
            "- **Data Source:** Public data from Bank of Canada and Statistics Canada\n"
            "- **Methodology:** Statistical monitoring using rolling z-scores and historical ranges\n"
            "- **Interpretation:** Changes are observations, not causal claims\n"
            "- **Not Advice:** This report does not constitute investment or policy advice\n"
            "- **Refresh:** Generated on demand from the latest available local snapshots\n"
        )

        return "\n".join(md)

    def save_report(self, insights: dict[str, Any], markdown: str) -> dict[str, Any]:
        """Persist report to markdown and CSV files."""
        try:
            # Save markdown
            with open(REPORT_MARKDOWN, "w", encoding="utf-8") as f:
                f.write(markdown)
            logger.info("Markdown report saved: %s", REPORT_MARKDOWN)

            # Save structured insights as CSV
            rows = [
                {"record_type": "active_alert", **item}
                for item in insights.get("active_alerts", [])
            ] + [
                {"record_type": "largest_change", **item}
                for item in insights.get("largest_changes", [])
            ]
            pd.DataFrame(rows).to_csv(REPORT_CSV, index=False)
            logger.info("Structured report saved: %s", REPORT_CSV)

            return {
                "status": "success",
                "markdown_path": str(REPORT_MARKDOWN),
                "csv_path": str(REPORT_CSV),
                "num_alerts": len(insights.get("active_alerts", [])),
                "num_changes": len(insights.get("largest_changes", [])),
            }
        except Exception as e:
            logger.error("Failed to save report: %s", e)
            return {"status": "error", "message": str(e)}

    def run(self) -> dict[str, Any]:
        """Execute full reporting workflow."""
        if not self.load_data():
            return {"status": "error", "message": "Failed to load reporting data"}

        insights = self.generate_insights()
        markdown = self.format_markdown(insights)
        save_result = self.save_report(insights, markdown)

        return {
            "status": save_result.get("status"),
            "report_date": insights["report_date"],
            "num_alerts": len(insights.get("active_alerts", [])),
            "num_changes": len(insights.get("largest_changes", [])),
            "outputs": [
                save_result.get("markdown_path"),
                save_result.get("csv_path"),
            ],
        }


def run() -> dict[str, Any]:
    """Public entry point for automated reporting."""
    engine = ReportingEngine()
    return engine.run()


if __name__ == "__main__":
    result = run()
    print(result)
