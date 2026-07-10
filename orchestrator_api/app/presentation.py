"""Human-readable forecast presentation helpers."""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, Optional

from .csv_input import CsvForecastData


def build_presentation(
    *,
    ml_output: Dict[str, Any],
    explanation: Dict[str, Any],
    recommendations: Dict[str, Any],
    csv_data: Optional[CsvForecastData] = None,
) -> Dict[str, Any]:
    explanation_text = _paragraph(explanation.get("text", ""))
    recommendations_text = recommendations.get("text", "").strip()
    presentation = {
        "predictions_text": _prediction_bullets(ml_output),
        "explanation_paragraph": explanation_text,
        "recommendations_text": recommendations_text,
        "enriched_csv": None,
    }
    if csv_data is not None:
        presentation["enriched_csv"] = _build_enriched_csv(
            csv_data=csv_data,
            ml_output=ml_output,
            explanation_text=explanation_text,
            recommendations_text=recommendations_text,
        )
    return presentation


def build_markdown_report(*, ml_output: Dict[str, Any], presentation: Dict[str, Any]) -> str:
    """Build a curl-friendly Markdown report from the forecast presentation."""
    lines = ["# Forecast Report", "", presentation.get("predictions_text", "").strip()]

    summary = ml_output.get("summary") or {}
    if summary:
        lines.extend(
            [
                "",
                "Summary",
                "",
                f"* Trend: {summary.get('trend_direction', 'unknown')}",
                f"* Risk band: {summary.get('risk_band', 'unknown')}",
                f"* Confidence: {_fmt_number(summary.get('confidence'))}",
                f"* Final median: {_fmt_number(summary.get('final_median'))}",
                f"* Baseline: {_fmt_number(summary.get('baseline'))}",
            ]
        )

    explanation = presentation.get("explanation_paragraph")
    if explanation:
        lines.extend(["", "Explanation", "", explanation.strip()])

    recommendations = presentation.get("recommendations_text")
    if recommendations:
        lines.extend(["", "Recommendations", "", recommendations.strip()])

    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def _prediction_bullets(ml_output: Dict[str, Any]) -> str:
    horizon = ml_output.get("horizon") or []
    if not horizon:
        return "Predictions\n\n* No forecast horizon returned."

    lines = ["Predictions", ""]
    for point in horizon:
        timestamp = point.get("timestamp") or f"step {point.get('step')}"
        median = _fmt_number(point.get("median"))
        lower = _fmt_number(point.get("lower"))
        upper = _fmt_number(point.get("upper"))
        lines.append(f"* {timestamp}: {median} (range {lower} to {upper})")
    return "\n".join(lines)


def _build_enriched_csv(
    *,
    csv_data: CsvForecastData,
    ml_output: Dict[str, Any],
    explanation_text: str,
    recommendations_text: str,
) -> str:
    fieldnames = [
        "row_type",
        "timestamp",
        "actual_value",
        "predicted_median",
        "predicted_lower",
        "predicted_upper",
        "explanation",
        "recommendations",
        *csv_data.covariate_columns,
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for row in csv_data.observed_rows:
        writer.writerow(
            {
                "row_type": "actual",
                "timestamp": row.timestamp,
                "actual_value": _fmt_number(row.value),
                "predicted_median": "",
                "predicted_lower": "",
                "predicted_upper": "",
                "explanation": "",
                "recommendations": "",
                **row.covariates,
            }
        )

    for index, point in enumerate(ml_output.get("horizon") or []):
        writer.writerow(
            {
                "row_type": "forecast",
                "timestamp": point.get("timestamp") or f"step {point.get('step')}",
                "actual_value": "",
                "predicted_median": _fmt_number(point.get("median")),
                "predicted_lower": _fmt_number(point.get("lower")),
                "predicted_upper": _fmt_number(point.get("upper")),
                "explanation": explanation_text if index == 0 else "",
                "recommendations": recommendations_text if index == 0 else "",
                **{column: "" for column in csv_data.covariate_columns},
            }
        )

    return output.getvalue()


def _paragraph(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return " ".join(lines)


def _fmt_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)
