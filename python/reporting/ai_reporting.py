"""AI-Assisted Reporting Module.

Purpose: Convert verified analytical metrics into natural-language reporting.

Critical Principle: AI does NOT calculate metrics. Python/SQL calculates.
                   AI ONLY converts verified numbers into prose.

The AI input is a structured record of verified metrics:

{
  "series_name": "Household Credit",
  "current_value": 1234567,
  "previous_value": 1230000,
  "absolute_change": 4567,
  "pct_change": 0.37,
  "yoy_change": 15000,
  "yoy_pct": 1.23,
  "zscore": 0.85,
  "historical_average": 1200000,
  "historical_std_dev": 50000,
  "unit": "$M"
}

AI Task: Convert this INTO natural language using ONLY these verified values.
         NO hallucination. NO invented trends. NO made-up sources.

Output: Natural-language report fragment suitable for dashboard/email.
"""
from __future__ import annotations

import os
from typing import Any

from ..common.logging_utils import get_logger

logger = get_logger("reporting.ai_reporting")

# Optional: Try to import Claude API client
try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    logger.warning("Claude SDK not installed. AI reporting disabled. Using fallback.")


class AIReportingEngine:
    """Convert verified metrics to natural-language insights using LLM."""

    def __init__(self):
        """Initialize AI reporting engine."""
        self.client = None
        self.use_ai = False

        # Check if API key is available
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if CLAUDE_AVAILABLE and api_key:
            try:
                self.client = anthropic.Anthropic(api_key=api_key)
                self.use_ai = True
                logger.info("AI Reporting: Claude client initialized")
            except Exception as e:
                logger.warning("Failed to initialize Claude client: %s. Using fallback.", e)
                self.use_ai = False
        else:
            logger.info(
                "AI Reporting disabled: ANTHROPIC_API_KEY not set or Claude SDK unavailable. "
                "Using deterministic fallback."
            )

    def generate_series_narrative(self, metric_dict: dict[str, Any]) -> str:
        """
        Generate natural-language narrative for a single metric.

        Input: Dictionary of verified metrics
        Output: Plain-text narrative (1-2 sentences)

        CRITICAL: Do not fabricate numbers or data sources.
        """
        if self.use_ai and self.client:
            return self._ai_narrative(metric_dict)
        else:
            return self._fallback_narrative(metric_dict)

    def _ai_narrative(self, metric_dict: dict[str, Any]) -> str:
        """Generate narrative using Claude API."""
        prompt = self._build_prompt(metric_dict)

        try:
            message = self.client.messages.create(
                model="claude-opus-4-1",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            narrative = message.content[0].text
            logger.debug("AI narrative generated successfully")
            return narrative
        except Exception as e:
            logger.error("AI narrative generation failed: %s. Using fallback.", e)
            return self._fallback_narrative(metric_dict)

    def _build_prompt(self, metric_dict: dict[str, Any]) -> str:
        """Build system-constrained prompt for metric narrative."""
        series_name = metric_dict.get("series_name", "Metric")
        current_value = metric_dict.get("current_value", 0)
        pct_change = metric_dict.get("pct_change", 0)
        yoy_pct = metric_dict.get("yoy_pct", 0)
        zscore = metric_dict.get("zscore", 0)
        unit = metric_dict.get("unit", "")

        prompt = f"""You are a financial analyst writing for a professional banking report.

VERIFIED METRICS (DO NOT FABRICATE):
- Series: {series_name}
- Current Value: {current_value:,.0f} {unit}
- Period Change: {pct_change:+.2f}%
- Year-over-Year Change: {yoy_pct:+.2f}%
- Statistical Deviation (Z-score): {zscore:.2f}

INSTRUCTIONS (STRICT):
1. Use ONLY the values above. Do not invent numbers.
2. Do not claim causality without evidence.
3. Do not provide investment recommendations.
4. Use neutral language: "observed," "noted," "appears," "moved to"
5. Write 1-2 sentences, maximum.
6. Include the unit in your description.

TASK: Write a single natural-language sentence describing this observation."""

        return prompt

    def _fallback_narrative(self, metric_dict: dict[str, Any]) -> str:
        """Deterministic fallback: Generate narrative without AI."""
        series_name = metric_dict.get("series_name", "Metric")
        current_value = metric_dict.get("current_value", 0)
        pct_change = metric_dict.get("pct_change", 0)
        yoy_pct = metric_dict.get("yoy_pct", 0)
        zscore = metric_dict.get("zscore", 0)
        unit = metric_dict.get("unit", "")

        # Determine direction
        direction_short = "increased" if pct_change > 0 else "decreased" if pct_change < 0 else "remained stable"
        # Build deterministic narrative
        narrative = f"{series_name} {direction_short} to {current_value:,.0f} {unit} "
        narrative += f"({pct_change:+.2f}% period-over-period, {yoy_pct:+.2f}% year-over-year)."

        # Add deviation note if significant
        if abs(zscore) > 2:
            deviation_type = "above" if zscore > 0 else "below"
            narrative += f" Value is {abs(zscore):.1f} standard deviations {deviation_type} historical average."

        return narrative

    def generate_alert_narrative(self, alert_dict: dict[str, Any]) -> str:
        """Generate narrative for a monitoring alert."""
        if self.use_ai and self.client:
            return self._ai_alert_narrative(alert_dict)
        else:
            return self._fallback_alert_narrative(alert_dict)

    def _ai_alert_narrative(self, alert_dict: dict[str, Any]) -> str:
        """Use AI to describe alert in natural language."""
        prompt = self._build_alert_prompt(alert_dict)

        try:
            message = self.client.messages.create(
                model="claude-opus-4-1",
                max_tokens=250,
                messages=[{"role": "user", "content": prompt}],
            )
            narrative = message.content[0].text
            return narrative
        except Exception as e:
            logger.error("AI alert narrative generation failed: %s. Using fallback.", e)
            return self._fallback_alert_narrative(alert_dict)

    def _build_alert_prompt(self, alert_dict: dict[str, Any]) -> str:
        """Build prompt for alert narrative."""
        series_name = alert_dict.get("series_name", "Metric")
        severity = alert_dict.get("severity", "MEDIUM")
        current_value = alert_dict.get("current_value", 0)
        reason = alert_dict.get("reason", "Unusual movement detected")
        zscore = alert_dict.get("zscore", 0)
        unit = alert_dict.get("unit", "")

        prompt = f"""You are a financial analyst writing for a professional banking report.

ALERT INFORMATION (VERIFIED):
- Series: {series_name}
- Severity: {severity}
- Current Value: {current_value:,.0f} {unit}
- Z-Score: {zscore:.2f}
- Flag Reason: {reason}

INSTRUCTIONS (STRICT):
1. Use ONLY the information above.
2. Do NOT claim this is a risk or problem. Use "alert," "flagged," "monitoring"
3. Do NOT recommend action. Suggest "investigation" or "review"
4. Do NOT invent data or causes.
5. Write 2-3 sentences, maximum.

TASK: Explain this alert in plain language."""

        return prompt

    def _fallback_alert_narrative(self, alert_dict: dict[str, Any]) -> str:
        """Deterministic fallback for alert narrative."""
        series_name = alert_dict.get("series_name", "Metric")
        severity = alert_dict.get("severity", "MEDIUM")
        reason = alert_dict.get("reason", "Unusual movement")

        severity_text = {
            "HIGH": "significant",
            "MEDIUM": "notable",
            "LOW": "minor",
        }.get(severity, "notable")

        narrative = (
            f"{series_name} has been flagged for {severity_text} movement. "
            f"Reason: {reason}. "
            f"This observation warrants analyst investigation."
        )
        return narrative

    def generate_management_summary(self, insights: dict[str, Any]) -> str:
        """Generate full management summary with AI enhancement."""
        summary_parts = []

        summary_parts.append("# Financial Intelligence Summary\n")
        summary_parts.append(f"Report Date: {insights.get('report_date', 'Unknown')}\n\n")

        # Largest Changes
        summary_parts.append("## Recent Notable Changes\n\n")
        changes = insights.get("largest_changes", [])
        if changes:
            for change_item in changes[:3]:
                narrative = self.generate_series_narrative(change_item)
                summary_parts.append(f"- {narrative}\n")
        else:
            summary_parts.append("- No significant changes detected in recent period.\n")

        # Active Alerts
        summary_parts.append("\n## Monitoring Alerts\n\n")
        alerts = insights.get("active_alerts", [])
        if alerts:
            summary_parts.append(
                "The following series require analyst attention:\n\n"
            )
            for alert_item in alerts[:3]:
                narrative = self.generate_alert_narrative(alert_item)
                summary_parts.append(f"- {narrative}\n")
        else:
            summary_parts.append("- No active alerts.\n")

        # Rate Environment
        summary_parts.append("\n## Rate Environment\n\n")
        rates = insights.get("rate_movements", [])
        if rates:
            for rate_item in rates[:2]:
                narrative = self.generate_series_narrative(rate_item)
                summary_parts.append(f"- {narrative}\n")
        else:
            summary_parts.append("- No significant rate changes.\n")

        # Disclaimer
        summary_parts.append("\n---\n")
        summary_parts.append(
            "**Disclaimer:** This report presents observations derived from public data. "
            "It does not constitute advice. "
            "All metrics are calculated by verified analytical systems. "
            "Natural-language descriptions are automated summaries of verified data.\n"
        )

        return "".join(summary_parts)


def run(insights: dict[str, Any]) -> dict[str, Any]:
    """Public entry point for AI-assisted reporting."""
    engine = AIReportingEngine()
    summary = engine.generate_management_summary(insights)

    return {
        "status": "success",
        "ai_enabled": engine.use_ai,
        "summary": summary,
    }


if __name__ == "__main__":
    # Test with sample data
    sample_insight = {
        "report_date": "2024-09-01",
        "largest_changes": [
            {
                "series_name": "Household Credit",
                "current_value": 1234567,
                "pct_change": 1.23,
                "yoy_pct": 3.45,
                "zscore": 0.85,
                "unit": "$M",
            }
        ],
        "active_alerts": [
            {
                "series_name": "Credit Card Balances",
                "severity": "MEDIUM",
                "current_value": 50000,
                "zscore": 2.5,
                "reason": "Value is 2.5 standard deviations above historical average",
                "unit": "$M",
            }
        ],
        "rate_movements": [],
    }

    result = run(sample_insight)
    print(result["summary"])
