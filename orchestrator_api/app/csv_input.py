"""CSV upload parsing for forecast requests."""

from __future__ import annotations

import csv
import io
import math
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
class CsvFutureRow:
    timestamp: str
    covariates: Dict[str, str]
    source_row_number: int
    sort_key: datetime


@dataclass(frozen=True)
class _CsvParsedRow:
    timestamp: str
    value: Optional[float]
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
    future_rows: List[CsvFutureRow]
    skipped_missing_target_rows: int
    warnings: List[str]
    covariate_summary: Dict[str, Dict[str, Any]]
    future_covariate_summary: Dict[str, Dict[str, Any]]
    past_covariates: Dict[str, List[Any]]
    future_covariates: Dict[str, List[Any]]
    excluded_covariate_columns: List[str]

    @property
    def timestamps(self) -> List[str]:
        return [row.timestamp for row in self.observed_rows]

    @property
    def values(self) -> List[float]:
        return [row.value for row in self.observed_rows]

    @property
    def future_timestamps(self) -> List[str]:
        return [row.timestamp for row in self.future_rows]

    def metadata(self) -> Dict[str, Any]:
        return {
            "source": "csv_upload",
            "filename": self.filename,
            "date_column": self.date_column,
            "target_column": self.target_column,
            "covariate_columns": self.covariate_columns,
            "observed_row_count": len(self.observed_rows),
            "future_row_count": len(self.future_rows),
            "skipped_missing_target_rows": self.skipped_missing_target_rows,
            "covariate_summary": self.covariate_summary,
            "future_covariate_summary": self.future_covariate_summary,
            "model_past_covariates": sorted(self.past_covariates),
            "model_future_covariates": sorted(self.future_covariates),
            "excluded_covariate_columns": self.excluded_covariate_columns,
            "warnings": self.warnings,
        }


def parse_csv_forecast_upload(
    content: bytes,
    *,
    filename: Optional[str],
    date_column: str,
    target_column: str,
    prediction_length: Optional[int] = None,
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
    parsed_rows: List[_CsvParsedRow] = []

    for row_index, raw_row in enumerate(reader, start=2):
        row = {_clean_header(key): _clean_cell(value) for key, value in raw_row.items() if key is not None}
        raw_timestamp = row.get(date_column, "")
        raw_target = row.get(target_column, "")

        if not raw_timestamp:
            raise CsvInputError(f"Row {row_index} is missing '{date_column}'.")
        timestamp, sort_key = _normalize_timestamp(raw_timestamp, row_index)

        parsed_rows.append(
            _CsvParsedRow(
                timestamp=timestamp,
                value=_parse_float(raw_target, row_index, target_column) if raw_target else None,
                covariates={column: row.get(column, "") for column in covariate_columns},
                source_row_number=row_index,
                sort_key=sort_key,
            )
        )

    future_start = len(parsed_rows)
    while future_start > 0 and parsed_rows[future_start - 1].value is None:
        future_start -= 1

    historical_parsed = parsed_rows[:future_start]
    future_parsed = parsed_rows[future_start:]
    if future_parsed:
        if prediction_length is None:
            raise CsvInputError("prediction_length is required when CSV has trailing blank-target rows.")
        if len(future_parsed) != prediction_length:
            raise CsvInputError(
                f"Trailing blank-target row count ({len(future_parsed)}) must equal "
                f"prediction_length ({prediction_length})."
            )

    skipped_missing_target_rows = sum(row.value is None for row in historical_parsed)
    observed_rows = [
        CsvObservedRow(
            timestamp=row.timestamp,
            value=row.value,
            covariates=row.covariates,
            source_row_number=row.source_row_number,
            sort_key=row.sort_key,
        )
        for row in historical_parsed
        if row.value is not None
    ]
    future_rows = [
        CsvFutureRow(
            timestamp=row.timestamp,
            covariates=row.covariates,
            source_row_number=row.source_row_number,
            sort_key=row.sort_key,
        )
        for row in future_parsed
    ]

    observed_rows.sort(key=lambda item: item.sort_key)
    future_rows.sort(key=lambda item: item.sort_key)
    if len(observed_rows) < 2:
        raise CsvInputError("CSV must include at least two rows with non-empty target values.")

    seen_timestamps: Dict[str, int] = {}
    for row in [*observed_rows, *future_rows]:
        if row.timestamp in seen_timestamps:
            raise CsvInputError(
                f"Duplicate timestamp '{row.timestamp}' in rows "
                f"{seen_timestamps[row.timestamp]} and {row.source_row_number}."
            )
        seen_timestamps[row.timestamp] = row.source_row_number

    warnings: List[str] = []
    if skipped_missing_target_rows:
        warnings.append(f"Skipped {skipped_missing_target_rows} row(s) with blank target values.")
    if future_rows:
        warnings.append(
            f"Interpreted {len(future_rows)} trailing row(s) with blank target values as known-future rows."
        )

    past_covariates, future_covariates, excluded_covariates = _build_model_covariates(
        observed_rows=observed_rows,
        future_rows=future_rows,
        covariate_columns=covariate_columns,
        warnings=warnings,
    )

    return CsvForecastData(
        filename=filename,
        date_column=date_column,
        target_column=target_column,
        covariate_columns=covariate_columns,
        observed_rows=observed_rows,
        future_rows=future_rows,
        skipped_missing_target_rows=skipped_missing_target_rows,
        warnings=warnings,
        covariate_summary=_summarize_covariates(observed_rows, covariate_columns),
        future_covariate_summary=_summarize_covariates(future_rows, covariate_columns),
        past_covariates=past_covariates,
        future_covariates=future_covariates,
        excluded_covariate_columns=excluded_covariates,
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
    context_parts = _covariate_context_parts(csv_data.covariate_summary)

    csv_context = (
        f"CSV upload context: {len(csv_data.observed_rows)} observed rows from "
        f"{csv_data.timestamps[0]} to {csv_data.timestamps[-1]}."
    )
    if context_parts:
        csv_context += " Covariate summary: " + "; ".join(context_parts[:12]) + "."
    if csv_data.future_rows:
        future_context_parts = _covariate_context_parts(csv_data.future_covariate_summary)
        csv_context += (
            f" The upload includes {len(csv_data.future_rows)} known-future row(s) through "
            f"{csv_data.future_timestamps[-1]}; model future covariates: "
            f"{', '.join(sorted(csv_data.future_covariates)) or 'none'}."
        )
        if future_context_parts:
            csv_context += " Future covariate summary: " + "; ".join(future_context_parts[:12]) + "."

    return "\n\n".join(part for part in [notes, csv_context] if part)


def _covariate_context_parts(summaries: Dict[str, Dict[str, Any]]) -> List[str]:
    context_parts: List[str] = []
    for column, summary in summaries.items():
        if summary.get("numeric"):
            context_parts.append(
                f"{column}: latest={summary.get('latest')}, "
                f"min={summary.get('min')}, max={summary.get('max')}, mean={summary.get('mean')}"
            )
        else:
            sample = summary.get("unique_values_sample") or []
            sample_text = f", values={sample}" if sample else ""
            context_parts.append(
                f"{column}: latest={summary.get('latest')}, non_empty={summary.get('non_empty')}{sample_text}"
            )
    return context_parts


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
    observed_rows: List[Any],
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
        parsed = float(value.replace(",", ""))
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _build_model_covariates(
    *,
    observed_rows: List[CsvObservedRow],
    future_rows: List[CsvFutureRow],
    covariate_columns: List[str],
    warnings: List[str],
) -> Tuple[Dict[str, List[Any]], Dict[str, List[Any]], List[str]]:
    past_covariates: Dict[str, List[Any]] = {}
    future_covariates: Dict[str, List[Any]] = {}
    excluded: List[str] = []

    for column in covariate_columns:
        historical_values = [row.covariates.get(column, "") for row in observed_rows]
        missing_historical = sum(value == "" for value in historical_values)
        if missing_historical:
            excluded.append(column)
            warnings.append(
                f"Excluded covariate '{column}' from model input because "
                f"{missing_historical} historical value(s) are blank."
            )
            continue

        raw_future_values = [row.covariates.get(column, "") for row in future_rows]
        future_is_complete = bool(future_rows) and all(value != "" for value in raw_future_values)
        if future_is_complete:
            converted = _coerce_covariate_values([*historical_values, *raw_future_values])
            past_covariates[column] = converted[: len(historical_values)]
            future_covariates[column] = converted[len(historical_values) :]
        else:
            past_covariates[column] = _coerce_covariate_values(historical_values)
            if future_rows:
                missing_future = sum(value == "" for value in raw_future_values)
                warnings.append(
                    f"Covariate '{column}' has {missing_future} blank future value(s) and is used as past-only."
                )

    return past_covariates, future_covariates, excluded


def _coerce_covariate_values(values: List[str]) -> List[Any]:
    numeric_values = [_try_float(value) for value in values]
    if all(value is not None for value in numeric_values):
        return [value for value in numeric_values if value is not None]
    return list(values)
