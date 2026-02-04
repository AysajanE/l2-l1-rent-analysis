from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Iterable, Mapping


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
class RollupStrRow:
    """Per-rollup STR row (rollup-day)."""

    date_utc: str
    rollup_id: str
    rent_paid_eth: float
    l2_fees_eth: float
    str_value: float


def load_panel_csv(path: Path) -> list[dict[str, str]]:
    """Load a CSV panel file into a list of dict rows (string values).

    This helper is intentionally small and stdlib-only. Metric computation functions in this
    module accept any iterable of mapping-like rows, so callers can provide their own loaders.
    """
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
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
        s = value.strip()
        if s == "":
            return None
        if s.lower() in {"nan", "na", "null", "none"}:
            return None
        return float(s)
    raise TypeError(f"Unsupported numeric type: {type(value)}")


def _require_str(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"Missing/invalid required field {key!r}: {value!r}")
    return value


def compute_rollup_str_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    date_key: str = "date_utc",
    rollup_key: str = "rollup_id",
    fees_key: str = "l2_fees_eth",
    rent_key: str = "rent_paid_eth",
) -> list[RollupStrRow]:
    """Compute per-rollup STR rows.

    Missingness rule:
    - If either fees or rent is missing on a rollup-day row, the row is excluded (skipped).

    Denominator rule:
    - If fees == 0, STR is NaN for that rollup-day row.
    """
    out: list[RollupStrRow] = []
    for row in rows:
        date_utc = _require_str(row, date_key)
        rollup_id = _require_str(row, rollup_key)
        l2_fees = parse_optional_float(row.get(fees_key))
        rent_paid = parse_optional_float(row.get(rent_key))
        if l2_fees is None or rent_paid is None:
            continue
        if l2_fees < 0 or rent_paid < 0:
            raise ValueError(f"Negative values not allowed: {date_utc=} {rollup_id=} {l2_fees=} {rent_paid=}")
        str_value = math.nan if l2_fees == 0 else (rent_paid / l2_fees)
        out.append(
            RollupStrRow(
                date_utc=date_utc,
                rollup_id=rollup_id,
                rent_paid_eth=rent_paid,
                l2_fees_eth=l2_fees,
                str_value=str_value,
            )
        )

    out.sort(key=lambda r: (r.date_utc, r.rollup_id))
    return out


def compute_daily_ecosystem_str(
    rows: Iterable[Mapping[str, Any]],
    *,
    date_key: str = "date_utc",
    fees_key: str = "l2_fees_eth",
    rent_key: str = "rent_paid_eth",
) -> list[DailyStrAggregate]:
    """Compute daily ecosystem-level STR time series.

    Protocol rules implemented:
    - Missingness rule: if either fees or rent is missing for a rollup-day, exclude that rollup-day
      from both the numerator and denominator sums (by skipping it).
    - Denominator-zero rule: if Σ fees == 0 for day t, STR_t is NaN.
    """
    buckets: dict[str, dict[str, float | int]] = {}

    for row in rows:
        date_utc = _require_str(row, date_key)
        l2_fees = parse_optional_float(row.get(fees_key))
        rent_paid = parse_optional_float(row.get(rent_key))

        b = buckets.get(date_utc)
        if b is None:
            b = {"fees_sum": 0.0, "rent_sum": 0.0, "included": 0, "skipped": 0}
            buckets[date_utc] = b

        if l2_fees is None or rent_paid is None:
            b["skipped"] = int(b["skipped"]) + 1
            continue
        if l2_fees < 0 or rent_paid < 0:
            raise ValueError(f"Negative values not allowed: {date_utc=} {l2_fees=} {rent_paid=}")

        b["fees_sum"] = float(b["fees_sum"]) + float(l2_fees)
        b["rent_sum"] = float(b["rent_sum"]) + float(rent_paid)
        b["included"] = int(b["included"]) + 1

    out: list[DailyStrAggregate] = []
    for date_utc, b in buckets.items():
        fees_sum = float(b["fees_sum"])
        rent_sum = float(b["rent_sum"])
        included = int(b["included"])
        skipped = int(b["skipped"])
        str_value = math.nan if fees_sum == 0 else (rent_sum / fees_sum)
        out.append(
            DailyStrAggregate(
                date_utc=date_utc,
                rent_paid_eth_sum=rent_sum,
                l2_fees_eth_sum=fees_sum,
                str_value=str_value,
                included_rollup_days=included,
                skipped_rows=skipped,
            )
        )

    out.sort(key=lambda r: r.date_utc)
    return out

