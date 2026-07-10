"""CSV upload parsing for forecast requests."""

from __future__ import annotations

import csv
import io
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class CsvInputError(ValueError):
    """Raised when an uploaded CSV cannot be converted into a forecast request."""


@dataclass(frozen=True)
class CsvObservedRow:
    timestamp: str
    value: float
    covariates: Dict[str, str]
    source_row_number: int
    sort_key: datetime


@dataclass(frozen=True)
class CsvForecastData:
    filename: Optional[str]
    date_column: str
    target_column: str
    covariate_columns: List[str]
    observed_rows: List[CsvObservedRow]
    skipped_missing_target_rows: int
    warnings: List[str]
    covariate_summary: Dict[str, Dict[str, Any]]

    @property
    def timestamps(self) -> List[str]:
        return [row.timestamp for row in self.observed_rows]

    @property
    def values(self) -> List[float]:
        return [row.value for row in self.observed_rows]

    def metadata(self) -> Dict[str, Any]:
        return {
            "source": "csv_upload",
            "filename": self.filename,
            "date_column": self.date_column,
            "target_column": self.target_column,
            "covariate_columns": self.covariate_columns,
            "observed_row_count": len(self.observed_rows),
            "skipped_missing_target_rows": self.skipped_missing_target_rows,
            "covariate_summary": self.covariate_summary,
            "warnings": self.warnings,
        }


def parse_csv_forecast_upload(
    content: bytes,
    *,
    filename: Optional[str],
    date_column: str,
    target_column: str,
) -> CsvForecastData:
    """Parse uploaded CSV bytes into sorted forecast inputs and covariate metadata."""

    if not content:
        raise CsvInputError("Uploaded CSV is empty.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvInputError("Uploaded CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CsvInputError("Uploaded CSV must include a header row.")

    headers = [_clean_header(value) for value in reader.fieldnames]
    if len(headers) != len(set(headers)):
        raise CsvInputError("CSV headers must be unique after trimming whitespace.")

    date_column = _clean_header(date_column)
    target_column = _clean_header(target_column)
    if date_column not in headers:
        raise CsvInputError(f"CSV is missing date column '{date_column}'.")
    if target_column not in headers:
        raise CsvInputError(f"CSV is missing target column '{target_column}'.")

    covariate_columns = [column for column in headers if column not in {date_column, target_column}]
    observed_rows: List[CsvObservedRow] = []
    skipped_missing_target_rows = 0
    seen_timestamps: Dict[str, int] = {}

    for row_index, raw_row in enumerate(reader, start=2):
        row = {_clean_header(key): _clean_cell(value) for key, value in raw_row.items() if key is not None}
        raw_timestamp = row.get(date_column, "")
        raw_target = row.get(target_column, "")

        if not raw_timestamp:
            raise CsvInputError(f"Row {row_index} is missing '{date_column}'.")
        timestamp, sort_key = _normalize_timestamp(raw_timestamp, row_index)

        if not raw_target:
            skipped_missing_target_rows += 1
            continue

        if timestamp in seen_timestamps:
            raise CsvInputError(
                f"Duplicate timestamp '{timestamp}' in rows {seen_timestamps[timestamp]} and {row_index}."
            )
        seen_timestamps[timestamp] = row_index

        observed_rows.append(
            CsvObservedRow(
                timestamp=timestamp,
                value=_parse_float(raw_target, row_index, target_column),
                covariates={column: row.get(column, "") for column in covariate_columns},
                source_row_number=row_index,
                sort_key=sort_key,
            )
        )

    observed_rows.sort(key=lambda item: item.sort_key)
    if len(observed_rows) < 2:
        raise CsvInputError("CSV must include at least two rows with non-empty target values.")

    warnings: List[str] = []
    if skipped_missing_target_rows:
        warnings.append(f"Skipped {skipped_missing_target_rows} row(s) with blank target values.")

    return CsvForecastData(
        filename=filename,
        date_column=date_column,
        target_column=target_column,
        covariate_columns=covariate_columns,
        observed_rows=observed_rows,
        skipped_missing_target_rows=skipped_missing_target_rows,
        warnings=warnings,
        covariate_summary=_summarize_covariates(observed_rows, covariate_columns),
    )


def parse_quantile_levels(value: str) -> List[float]:
    levels = []
    for part in value.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        try:
            levels.append(float(cleaned))
        except ValueError as exc:
            raise CsvInputError(f"Invalid quantile level '{cleaned}'.") from exc
    if not levels:
        raise CsvInputError("At least one quantile level is required.")
    return levels


def csv_context_notes(notes: Optional[str], csv_data: CsvForecastData) -> str:
    context_parts = []
    for column, summary in csv_data.covariate_summary.items():
        if summary.get("numeric"):
            context_parts.append(
                f"{column}: latest={summary.get('latest')}, "
                f"min={summary.get('min')}, max={summary.get('max')}, mean={summary.get('mean')}"
            )
        else:
            context_parts.append(f"{column}: latest={summary.get('latest')}, non_empty={summary.get('non_empty')}")

    csv_context = (
        f"CSV upload context: {len(csv_data.observed_rows)} observed rows from "
        f"{csv_data.timestamps[0]} to {csv_data.timestamps[-1]}."
    )
    if context_parts:
        csv_context += " Covariate summary: " + "; ".join(context_parts[:12]) + "."

    return "\n\n".join(part for part in [notes, csv_context] if part)


def _clean_header(value: Optional[str]) -> str:
    return (value or "").strip()


def _clean_cell(value: Optional[str]) -> str:
    return (value or "").strip()


def _normalize_timestamp(value: str, row_index: int) -> Tuple[str, datetime]:
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%m-%d-%Y"]
    for parser in [_parse_iso_timestamp, *(_format_parser(fmt) for fmt in formats)]:
        parsed = parser(value)
        if parsed is not None:
            return parsed.date().isoformat(), parsed
    raise CsvInputError(f"Row {row_index} has invalid date value '{value}'. Use ISO date format like 2026-07-01.")


def _parse_iso_timestamp(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _format_parser(fmt: str):
    def parse(value: str) -> Optional[datetime]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            return None

    return parse


def _parse_float(value: str, row_index: int, column: str) -> float:
    try:
        parsed = float(value.replace(",", ""))
    except ValueError as exc:
        raise CsvInputError(f"Row {row_index} has non-numeric target value '{value}' in '{column}'.") from exc
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        raise CsvInputError(f"Row {row_index} has non-finite target value in '{column}'.")
    return parsed


def _summarize_covariates(
    observed_rows: List[CsvObservedRow],
    covariate_columns: List[str],
) -> Dict[str, Dict[str, Any]]:
    summaries: Dict[str, Dict[str, Any]] = {}
    for column in covariate_columns:
        values = [row.covariates.get(column, "") for row in observed_rows]
        non_empty = [value for value in values if value != ""]
        if not non_empty:
            summaries[column] = {"non_empty": 0, "latest": None, "numeric": False}
            continue

        numeric_values = [_try_float(value) for value in non_empty]
        numeric_complete = all(value is not None for value in numeric_values)
        latest = non_empty[-1]
        if numeric_complete:
            numbers = [value for value in numeric_values if value is not None]
            summaries[column] = {
                "non_empty": len(non_empty),
                "latest": numbers[-1],
                "numeric": True,
                "min": min(numbers),
                "max": max(numbers),
                "mean": round(float(statistics.fmean(numbers)), 6),
            }
        else:
            top_values = sorted({value for value in non_empty})[:10]
            summaries[column] = {
                "non_empty": len(non_empty),
                "latest": latest,
                "numeric": False,
                "unique_values_sample": top_values,
            }
    return summaries


def _try_float(value: str) -> Optional[float]:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None
