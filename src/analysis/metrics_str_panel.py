from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DailyStrAggregate:
    """Daily ecosystem-level STR aggregate computed from rollup-day rows."""

    date_utc: str
    rent_paid_eth_sum: float
    l2_fees_eth_sum: float
    str_value: float
    included_rollup_days: int
    skipped_rows: int


@dataclass(frozen=True)
class RollupStrContribution:
    """Per-rollup diagnostics for understanding daily STR composition."""

    date_utc: str
    rollup_id: str
    rent_paid_eth: float
    l2_fees_eth: float
    rollup_str_value: float
    rent_share_of_day: float
    fees_share_of_day: float
    contribution_to_ecosystem_str: float


def load_panel_csv(path: Path) -> list[dict[str, str]]:
    """Load a CSV panel file into a list of dictionary rows."""
    with path.open("r", encoding="utf-8", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        if reader.fieldnames is None:
            raise ValueError(f"Missing CSV header: {path}")
        return [dict(row) for row in reader]


def parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("Boolean is not a valid numeric value")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        if text.lower() in {"nan", "na", "null", "none"}:
            return None
        return float(text)
    raise TypeError(f"Unsupported numeric type: {type(value)}")


def _require_nonempty_str(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"Missing/invalid required field {key!r}: {value!r}")
    return value


def _parse_panel_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    date_key: str,
    rollup_key: str,
    fees_key: str,
    rent_key: str,
) -> tuple[list[tuple[str, str, float, float]], dict[str, int]]:
    parsed_rows: list[tuple[str, str, float, float]] = []
    skipped_by_date: dict[str, int] = {}

    for row in rows:
        date_utc = _require_nonempty_str(row, date_key)
        rollup_id = _require_nonempty_str(row, rollup_key)
        fees = parse_optional_float(row.get(fees_key))
        rent = parse_optional_float(row.get(rent_key))

        if fees is None or rent is None:
            skipped_by_date[date_utc] = skipped_by_date.get(date_utc, 0) + 1
            continue
        if fees < 0 or rent < 0:
            raise ValueError(
                f"Negative values not allowed: {date_utc=} {rollup_id=} {fees=} {rent=}"
            )
        parsed_rows.append((date_utc, rollup_id, fees, rent))

    return parsed_rows, skipped_by_date


def compute_daily_str_series(
    rows: Iterable[Mapping[str, Any]],
    *,
    date_key: str = "date_utc",
    rollup_key: str = "rollup_id",
    fees_key: str = "l2_fees_eth",
    rent_key: str = "rent_paid_eth",
) -> list[DailyStrAggregate]:
    """Compute daily ecosystem STR using protocol missingness and denominator rules."""
    parsed_rows, skipped_by_date = _parse_panel_rows(
        rows, date_key=date_key, rollup_key=rollup_key, fees_key=fees_key, rent_key=rent_key
    )

    buckets: dict[str, dict[str, float | int]] = {}
    for date_utc in skipped_by_date:
        buckets[date_utc] = {"fees_sum": 0.0, "rent_sum": 0.0, "included": 0, "skipped": skipped_by_date[date_utc]}

    for date_utc, _rollup_id, fees, rent in parsed_rows:
        bucket = buckets.get(date_utc)
        if bucket is None:
            bucket = {"fees_sum": 0.0, "rent_sum": 0.0, "included": 0, "skipped": 0}
            buckets[date_utc] = bucket
        bucket["fees_sum"] = float(bucket["fees_sum"]) + fees
        bucket["rent_sum"] = float(bucket["rent_sum"]) + rent
        bucket["included"] = int(bucket["included"]) + 1

    output: list[DailyStrAggregate] = []
    for date_utc, bucket in buckets.items():
        fees_sum = float(bucket["fees_sum"])
        rent_sum = float(bucket["rent_sum"])
        str_value = math.nan if fees_sum == 0 else (rent_sum / fees_sum)
        output.append(
            DailyStrAggregate(
                date_utc=date_utc,
                rent_paid_eth_sum=rent_sum,
                l2_fees_eth_sum=fees_sum,
                str_value=str_value,
                included_rollup_days=int(bucket["included"]),
                skipped_rows=int(bucket["skipped"]),
            )
        )

    output.sort(key=lambda row: row.date_utc)
    return output


def compute_rollup_str_contributions(
    rows: Iterable[Mapping[str, Any]],
    *,
    date_key: str = "date_utc",
    rollup_key: str = "rollup_id",
    fees_key: str = "l2_fees_eth",
    rent_key: str = "rent_paid_eth",
) -> list[RollupStrContribution]:
    """Compute per-rollup diagnostics for each date in the panel."""
    parsed_rows, _skipped_by_date = _parse_panel_rows(
        rows, date_key=date_key, rollup_key=rollup_key, fees_key=fees_key, rent_key=rent_key
    )

    daily_totals: dict[str, tuple[float, float]] = {}
    for date_utc, _rollup_id, fees, rent in parsed_rows:
        fees_sum, rent_sum = daily_totals.get(date_utc, (0.0, 0.0))
        daily_totals[date_utc] = (fees_sum + fees, rent_sum + rent)

    output: list[RollupStrContribution] = []
    for date_utc, rollup_id, fees, rent in parsed_rows:
        fees_sum, rent_sum = daily_totals[date_utc]
        rollup_str_value = math.nan if fees == 0 else (rent / fees)
        rent_share_of_day = math.nan if rent_sum == 0 else (rent / rent_sum)
        fees_share_of_day = math.nan if fees_sum == 0 else (fees / fees_sum)
        contribution_to_ecosystem_str = math.nan if fees_sum == 0 else (rent / fees_sum)
        output.append(
            RollupStrContribution(
                date_utc=date_utc,
                rollup_id=rollup_id,
                rent_paid_eth=rent,
                l2_fees_eth=fees,
                rollup_str_value=rollup_str_value,
                rent_share_of_day=rent_share_of_day,
                fees_share_of_day=fees_share_of_day,
                contribution_to_ecosystem_str=contribution_to_ecosystem_str,
            )
        )

    output.sort(key=lambda row: (row.date_utc, row.rollup_id))
    return output
