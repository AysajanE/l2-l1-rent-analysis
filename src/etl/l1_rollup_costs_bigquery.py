from __future__ import annotations

"""On-chain (BigQuery): compute rollup-attributed daily L1 rent + decomposition (contract v1).

This is the preferred on-chain route for full-scale unattended runs when you have BigQuery access.
It queries the public Ethereum dataset (`bigquery-public-data.crypto_ethereum`) and attributes txs
to rollups via `registry/rollup_registry_v1.csv` sender allowlist (batcher/poster addresses).

Raw snapshots are append-only under:
  `data/raw/bq_ethereum_rollup_costs/<as-of>/...`
and are tracked via `data/raw_manifest/bq_ethereum_rollup_costs_<as-of>.json`.

Processed outputs are rebuildable under `data/processed/onchain/` (gitignored) and tracked via
`data/processed_manifest/onchain_rollup_costs_<as-of>.json` when `--write-manifest` is used.
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.offchain.files import ensure_dir, write_text_append_only  # noqa: E402


RAW_SOURCE_NAME = "bq_ethereum_rollup_costs"
BQ_BLOCKS_TABLE = "bigquery-public-data.crypto_ethereum.blocks"
BQ_TXS_TABLE = "bigquery-public-data.crypto_ethereum.transactions"


def _repo_root() -> Path:
    return REPO_ROOT


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_within_repo(root: Path, target: Path) -> Path:
    try:
        return target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"path must be inside repo root: {root} (got {target})") from exc


def _parse_date(value: str, *, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {label} date (expected YYYY-MM-DD): {value!r}") from exc


def _parse_optional_date(value: str) -> date | None:
    v = (value or "").strip()
    if v == "":
        return None
    return _parse_date(v, label="registry")


def _parse_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in {"true", "1", "yes", "y"}:
        return True
    if v in {"false", "0", "no", "n", ""}:
        return False
    raise SystemExit(f"Invalid boolean value: {value!r}")


def _unquote_yaml_scalar(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    return v


def _load_schema_fields(schema_path: Path) -> tuple[tuple[str, ...], dict[str, bool]]:
    """Parse a minimal subset of YAML schemas (stdlib-only)."""
    if not schema_path.exists():
        raise SystemExit(f"schema not found: {schema_path}")

    text = schema_path.read_text(encoding="utf-8")
    fields: list[str] = []
    seen: set[str] = set()
    nullable: dict[str, bool] = {}
    in_fields = False
    current_field: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        if not in_fields:
            if line.strip() == "fields:":
                in_fields = True
            continue

        if not line.startswith(" ") and re.match(r"^[A-Za-z0-9_-]+\s*:", line.strip()):
            break

        m_name = re.match(r"^\s*-\s*name:\s*(.+?)\s*$", line)
        if m_name:
            name = _unquote_yaml_scalar(m_name.group(1))
            if name == "":
                raise SystemExit(f"schema field name is empty: {schema_path}")
            if name in seen:
                raise SystemExit(f"schema has duplicate field name {name!r}: {schema_path}")
            seen.add(name)
            fields.append(name)
            current_field = name
            continue

        m_nullable = re.match(r"^\s*nullable:\s*(true|false)\s*$", line.strip(), flags=re.IGNORECASE)
        if m_nullable and current_field is not None:
            nullable[current_field] = m_nullable.group(1).lower() == "true"

    if not fields:
        raise SystemExit(f"schema has no fields (expected fields: ...): {schema_path}")
    missing_nullable = [f for f in fields if f not in nullable]
    if missing_nullable:
        raise SystemExit(f"schema fields missing `nullable` flag: {missing_nullable} ({schema_path})")

    return tuple(fields), nullable


def _assert_contract(*, schema_path: Path, expected_fields: tuple[str, ...]) -> dict[str, object]:
    schema_fields, schema_nullable = _load_schema_fields(schema_path)
    if schema_fields != expected_fields:
        raise SystemExit(
            "Contract mismatch: schema field order differs from BigQuery output.\n"
            f"- schema_path: {schema_path}\n"
            f"- schema_fields: {list(schema_fields)}\n"
            f"- expected_fields: {list(expected_fields)}\n"
            "Update the query to match the locked schema, or update the schema with a W0 decision."
        )
    required_fields = tuple([f for f in schema_fields if not schema_nullable[f]])
    return {"schema_fields": list(schema_fields), "schema_required_fields": list(required_fields)}


@dataclass(frozen=True)
class RegistryRollup:
    rollup_id: str
    in_scope: bool
    status: str
    start_date_utc: date | None
    end_date_utc: date | None

    def includes(self, d: date) -> bool:
        if self.status == "deprecated":
            return False
        if not self.in_scope:
            return False
        if self.start_date_utc is not None and d < self.start_date_utc:
            return False
        if self.end_date_utc is not None and d > self.end_date_utc:
            return False
        if self.status == "inactive" and self.end_date_utc is None:
            raise SystemExit(f"Registry row {self.rollup_id!r} has status=inactive but missing end_date_utc")
        return True


@dataclass(frozen=True)
class SenderMapping:
    rollup_id: str
    from_address_lc: str
    addr_start_date_utc: date | None
    addr_end_date_utc: date | None
    rollup_start_date_utc: date | None
    rollup_end_date_utc: date | None


def _load_registry_sender_mappings(path: Path) -> tuple[list[SenderMapping], dict[str, object]]:
    if not path.exists():
        raise SystemExit(f"registry not found: {path}")

    rollups: dict[str, RegistryRollup] = {}
    mappings: list[SenderMapping] = []
    seen_addr: dict[str, str] = {}

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("registry CSV missing header row")
        required = {"rollup_id", "in_scope", "status", "start_date_utc", "end_date_utc", "batcher_addresses_json"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise SystemExit(f"registry CSV missing required columns: {missing}")

        for i, row in enumerate(reader, start=2):
            rollup_id = (row.get("rollup_id") or "").strip()
            if rollup_id == "":
                raise SystemExit(f"registry row {i}: missing rollup_id")
            if rollup_id in rollups:
                raise SystemExit(f"registry row {i}: duplicate rollup_id: {rollup_id!r}")

            in_scope = _parse_bool(row.get("in_scope", ""))
            status = (row.get("status") or "").strip().lower() or "active"
            start = _parse_optional_date(row.get("start_date_utc", ""))
            end = _parse_optional_date(row.get("end_date_utc", ""))
            rollups[rollup_id] = RegistryRollup(
                rollup_id=rollup_id,
                in_scope=in_scope,
                status=status,
                start_date_utc=start,
                end_date_utc=end,
            )

            if not in_scope or status == "deprecated":
                continue

            raw_json = (row.get("batcher_addresses_json") or "").strip()
            if raw_json == "":
                continue
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"registry row {i}: invalid batcher_addresses_json: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise SystemExit(f"registry row {i}: batcher_addresses_json must be an object")
            addresses = payload.get("addresses")
            if not isinstance(addresses, list):
                continue
            for a in addresses:
                if not isinstance(a, dict):
                    continue
                addr = a.get("address")
                if not isinstance(addr, str) or addr.strip() == "":
                    continue
                addr_lc = addr.strip().lower()
                if addr_lc in seen_addr and seen_addr[addr_lc] != rollup_id:
                    raise SystemExit(
                        "Registry address maps to multiple rollups (ambiguous attribution).\n"
                        f"- address: {addr_lc}\n"
                        f"- rollup_ids: {sorted({seen_addr[addr_lc], rollup_id})}\n"
                        "Fix registry (T082) before running BigQuery attribution."
                    )
                seen_addr[addr_lc] = rollup_id

                addr_start = _parse_optional_date(str(a.get("start_date_utc") or ""))
                addr_end = _parse_optional_date(str(a.get("end_date_utc") or ""))
                mappings.append(
                    SenderMapping(
                        rollup_id=rollup_id,
                        from_address_lc=addr_lc,
                        addr_start_date_utc=addr_start,
                        addr_end_date_utc=addr_end,
                        rollup_start_date_utc=start,
                        rollup_end_date_utc=end,
                    )
                )

    if not mappings:
        raise SystemExit("registry sender allowlist is empty (batcher_addresses_json missing?)")

    meta = {
        "in_scope_rollups": sorted([k for k, v in rollups.items() if v.in_scope and v.status != "deprecated"]),
        "addresses": len(seen_addr),
    }
    return mappings, meta


def _sql_literal_date(d: date | None) -> str:
    # BigQuery can infer `NULL` as INT64 when used inside STRUCT literals if all
    # values are NULL. Cast explicitly to keep sender_map fields typed as DATE.
    return "CAST(NULL AS DATE)" if d is None else f"DATE '{d.isoformat()}'"


def _render_sender_cte(mappings: list[SenderMapping]) -> str:
    parts: list[str] = []
    for m in mappings:
        parts.append(
            "STRUCT("
            + f"'{m.rollup_id}' AS rollup_id, "
            + f"'{m.from_address_lc}' AS from_address_lc, "
            + f"{_sql_literal_date(m.addr_start_date_utc)} AS addr_start_date_utc, "
            + f"{_sql_literal_date(m.addr_end_date_utc)} AS addr_end_date_utc, "
            + f"{_sql_literal_date(m.rollup_start_date_utc)} AS rollup_start_date_utc, "
            + f"{_sql_literal_date(m.rollup_end_date_utc)} AS rollup_end_date_utc"
            + ")"
        )
    inner = ",\n    ".join(parts)
    return "SELECT * FROM UNNEST([\n    " + inner + "\n  ])"


def _build_costs_sql(*, sender_cte: str, start_date: date, end_date: date) -> str:
    return f"""
WITH sender_map AS (
  {sender_cte}
),
txs AS (
  SELECT
    DATE(t.block_timestamp) AS date_utc,
    LOWER(t.from_address) AS from_address_lc,
    t.receipt_gas_used AS gas_used,
    t.receipt_effective_gas_price AS effective_gas_price_wei,
    t.transaction_type AS tx_type,
    t.receipt_blob_gas_used AS receipt_blob_gas_used,
    t.receipt_blob_gas_price AS receipt_blob_gas_price_wei,
    t.block_number AS block_number
  FROM `{BQ_TXS_TABLE}` t
  WHERE DATE(t.block_timestamp) BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
    AND LOWER(t.from_address) IN (SELECT from_address_lc FROM sender_map)
),
joined AS (
  SELECT
    txs.date_utc,
    m.rollup_id,
    CAST(txs.gas_used AS NUMERIC) AS gas_used,
    CAST(txs.effective_gas_price_wei AS NUMERIC) AS effective_gas_price_wei,
    CAST(b.base_fee_per_gas AS NUMERIC) AS base_fee_per_gas_wei,
    txs.tx_type AS tx_type,
    CAST(txs.receipt_blob_gas_used AS NUMERIC) AS receipt_blob_gas_used,
    CAST(txs.receipt_blob_gas_price_wei AS NUMERIC) AS receipt_blob_gas_price_wei
  FROM txs
  JOIN sender_map m
    ON txs.from_address_lc = m.from_address_lc
  JOIN `{BQ_BLOCKS_TABLE}` b
    ON txs.block_number = b.number
  WHERE (m.addr_start_date_utc IS NULL OR txs.date_utc >= m.addr_start_date_utc)
    AND (m.addr_end_date_utc IS NULL OR txs.date_utc <= m.addr_end_date_utc)
    AND (m.rollup_start_date_utc IS NULL OR txs.date_utc >= m.rollup_start_date_utc)
    AND (m.rollup_end_date_utc IS NULL OR txs.date_utc <= m.rollup_end_date_utc)
)
SELECT
  date_utc,
  rollup_id,
  CAST(SUM(
    (gas_used * base_fee_per_gas_wei) +
    (gas_used * (effective_gas_price_wei - base_fee_per_gas_wei)) +
    IF(tx_type = 3, (receipt_blob_gas_used * receipt_blob_gas_price_wei), 0)
  ) / 1e18 AS STRING) AS rent_paid_eth,
  CAST(SUM(
    (gas_used * base_fee_per_gas_wei) +
    (gas_used * (effective_gas_price_wei - base_fee_per_gas_wei)) +
    IF(tx_type = 3, (receipt_blob_gas_used * receipt_blob_gas_price_wei), 0)
  ) AS STRING) AS rent_paid_wei
FROM joined
GROUP BY date_utc, rollup_id
ORDER BY date_utc, rollup_id
""".strip()


def _build_decomp_sql(*, sender_cte: str, start_date: date, end_date: date) -> str:
    return f"""
WITH sender_map AS (
  {sender_cte}
),
txs AS (
  SELECT
    DATE(t.block_timestamp) AS date_utc,
    LOWER(t.from_address) AS from_address_lc,
    t.receipt_gas_used AS gas_used,
    t.receipt_effective_gas_price AS effective_gas_price_wei,
    t.transaction_type AS tx_type,
    t.receipt_blob_gas_used AS receipt_blob_gas_used,
    t.receipt_blob_gas_price AS receipt_blob_gas_price_wei,
    t.block_number AS block_number
  FROM `{BQ_TXS_TABLE}` t
  WHERE DATE(t.block_timestamp) BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
    AND LOWER(t.from_address) IN (SELECT from_address_lc FROM sender_map)
),
joined AS (
  SELECT
    txs.date_utc,
    m.rollup_id,
    CAST(txs.gas_used AS NUMERIC) AS gas_used,
    CAST(txs.effective_gas_price_wei AS NUMERIC) AS effective_gas_price_wei,
    CAST(b.base_fee_per_gas AS NUMERIC) AS base_fee_per_gas_wei,
    txs.tx_type AS tx_type,
    CAST(txs.receipt_blob_gas_used AS NUMERIC) AS receipt_blob_gas_used,
    CAST(txs.receipt_blob_gas_price_wei AS NUMERIC) AS receipt_blob_gas_price_wei
  FROM txs
  JOIN sender_map m
    ON txs.from_address_lc = m.from_address_lc
  JOIN `{BQ_BLOCKS_TABLE}` b
    ON txs.block_number = b.number
  WHERE (m.addr_start_date_utc IS NULL OR txs.date_utc >= m.addr_start_date_utc)
    AND (m.addr_end_date_utc IS NULL OR txs.date_utc <= m.addr_end_date_utc)
    AND (m.rollup_start_date_utc IS NULL OR txs.date_utc >= m.rollup_start_date_utc)
    AND (m.rollup_end_date_utc IS NULL OR txs.date_utc <= m.rollup_end_date_utc)
),
per_tx AS (
  SELECT
    date_utc,
    rollup_id,
    (gas_used * base_fee_per_gas_wei) AS burn_base_wei,
    (gas_used * (effective_gas_price_wei - base_fee_per_gas_wei)) AS tips_wei,
    IF(tx_type = 3, (receipt_blob_gas_used * receipt_blob_gas_price_wei), 0) AS burn_blob_wei,
    IF(tx_type = 3, receipt_blob_gas_used, 0) AS blob_gas_used
  FROM joined
)
SELECT
  date_utc,
  rollup_id,
  CAST(SUM(burn_base_wei + tips_wei + burn_blob_wei) / 1e18 AS STRING) AS rent_paid_eth,
  CAST(SUM(burn_base_wei) / 1e18 AS STRING) AS rent_base_fee_burn_eth,
  CAST(SUM(burn_blob_wei) / 1e18 AS STRING) AS rent_blob_fee_burn_eth,
  CAST(SUM(tips_wei) / 1e18 AS STRING) AS rent_priority_fee_eth,
  CAST(SUM(blob_gas_used) AS STRING) AS rollup_blob_gas_used,
  CAST(SUM(burn_base_wei + tips_wei + burn_blob_wei) AS STRING) AS rent_paid_wei,
  CAST(SUM(burn_blob_wei) AS STRING) AS rent_blob_fee_burn_wei,
  CAST(SUM(burn_base_wei) AS STRING) AS rent_base_fee_burn_wei,
  CAST(SUM(tips_wei) AS STRING) AS rent_priority_fee_wei,
  CAST(NULL AS STRING) AS unattributed_rent_eth
FROM per_tx
GROUP BY date_utc, rollup_id
ORDER BY date_utc, rollup_id
""".strip()


def _run_bq_query(*, sql: str, project_id: str | None, location: str | None) -> tuple[str, str]:
    cmd = ["bq", "--quiet", "query", "--use_legacy_sql=false", "--format=csv"]
    if project_id:
        cmd.extend(["--project_id", project_id])
    if location:
        cmd.extend(["--location", location])
    cmd.append(sql)
    try:
        r = subprocess.run(cmd, cwd=_repo_root(), capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise SystemExit("Missing `bq` CLI. Install Google Cloud SDK (bq) and authenticate before running.") from exc
    if r.returncode != 0:
        stderr = (r.stderr or "").strip()
        stdout = (r.stdout or "").strip()
        msg = f"bq query failed (code={r.returncode})."
        if stderr:
            msg += f"\n--- stderr ---\n{stderr}"
        if stdout:
            msg += f"\n--- stdout ---\n{stdout}"
        raise SystemExit(msg)
    return r.stdout, r.stderr or ""


def _run_bq_query_prettyjson(*, sql: str, project_id: str | None, location: str | None) -> list[dict[str, Any]]:
    cmd = ["bq", "--quiet", "query", "--use_legacy_sql=false", "--format=prettyjson"]
    if project_id:
        cmd.extend(["--project_id", project_id])
    if location:
        cmd.extend(["--location", location])
    cmd.append(sql)
    try:
        r = subprocess.run(cmd, cwd=_repo_root(), capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise SystemExit("Missing `bq` CLI. Install Google Cloud SDK (bq) and authenticate before running.") from exc
    if r.returncode != 0:
        stderr = (r.stderr or "").strip()
        stdout = (r.stdout or "").strip()
        msg = f"bq query failed (code={r.returncode})."
        if stderr:
            msg += f"\n--- stderr ---\n{stderr}"
        if stdout:
            msg += f"\n--- stdout ---\n{stdout}"
        raise SystemExit(msg)
    try:
        payload = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"bq prettyjson output is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, list):
        raise SystemExit("bq prettyjson output must be a JSON list")
    out: list[dict[str, Any]] = []
    for row in payload:
        if isinstance(row, dict):
            out.append(row)
    return out


def _probe_type3_blob_receipt_fields(
    *,
    sender_cte: str,
    start_date: date,
    end_date: date,
    project_id: str | None,
    location: str | None,
) -> dict[str, int]:
    sql = f"""
WITH sender_map AS (
  {sender_cte}
),
txs AS (
  SELECT
    t.transaction_type AS tx_type,
    t.receipt_blob_gas_used AS receipt_blob_gas_used,
    t.receipt_blob_gas_price AS receipt_blob_gas_price
  FROM `{BQ_TXS_TABLE}` t
  WHERE DATE(t.block_timestamp) BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
    AND t.transaction_type = 3
    AND LOWER(t.from_address) IN (SELECT from_address_lc FROM sender_map)
)
SELECT
  COUNT(*) AS type3_txs,
  SUM(CASE WHEN receipt_blob_gas_used IS NULL OR receipt_blob_gas_price IS NULL THEN 1 ELSE 0 END) AS missing_blob_receipt_fields
FROM txs
""".strip()

    rows = _run_bq_query_prettyjson(sql=sql, project_id=project_id, location=location)
    if not rows:
        return {"type3_txs": 0, "missing_blob_receipt_fields": 0}
    r0 = rows[0]
    type3 = int(r0.get("type3_txs") or 0)
    missing = int(r0.get("missing_blob_receipt_fields") or 0)
    return {"type3_txs": type3, "missing_blob_receipt_fields": missing}


def _write_raw_dir(*, raw_dir: Path, filename: str, text: str) -> Path:
    ensure_dir(raw_dir)
    path = raw_dir / filename
    write_text_append_only(path, text if text.endswith("\n") else (text + "\n"), encoding="utf-8")
    return path


def _validate_csv_contract(*, csv_path: Path, expected_fields: tuple[str, ...], required_fields: list[str]) -> dict[str, int]:
    counts = {"rows": 0, "missing_required": 0}
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit(f"CSV missing header row: {csv_path}")
        if tuple(reader.fieldnames) != expected_fields:
            raise SystemExit(
                "CSV header does not match locked contract field order.\n"
                f"- path: {csv_path}\n"
                f"- got: {reader.fieldnames}\n"
                f"- expected: {list(expected_fields)}"
            )
        for row in reader:
            counts["rows"] += 1
            for k in required_fields:
                if (row.get(k) or "").strip() == "":
                    counts["missing_required"] += 1
                    raise SystemExit(f"Found null/empty required field {k!r} in {csv_path}")
    return counts


def _copy_csv(*, src: Path, dst: Path, fieldnames: tuple[str, ...]) -> None:
    ensure_dir(dst.parent)
    with src.open("r", encoding="utf-8", newline="") as rf, dst.open("w", encoding="utf-8", newline="") as wf:
        reader = csv.DictReader(rf)
        if reader.fieldnames is None:
            raise SystemExit(f"CSV missing header row: {src}")
        w = csv.DictWriter(wf, fieldnames=list(fieldnames), lineterminator="\n")
        w.writeheader()
        for row in reader:
            w.writerow({k: (row.get(k) or "") for k in fieldnames})


def _render_command_tokens_for_manifest(root: Path) -> list[str]:
    argv0 = Path(sys.argv[0])
    try:
        script_token = str(argv0.resolve().relative_to(root.resolve()))
    except Exception:
        script_token = sys.argv[0]
    return ["python", script_token, *sys.argv[1:]]


def _write_raw_manifest(*, snapshot_dir: Path, as_of: date) -> Path:
    root = _repo_root()
    helper = root / "scripts/make_raw_manifest.py"
    if not helper.exists():
        raise SystemExit(f"missing helper script (expected): {helper}")

    rel_snapshot_dir = snapshot_dir.resolve().relative_to(root.resolve())
    cmd = [
        sys.executable,
        str(helper),
        RAW_SOURCE_NAME,
        str(rel_snapshot_dir),
        "--as-of",
        as_of.isoformat(),
        "--",
        *_render_command_tokens_for_manifest(root),
    ]
    subprocess.run(cmd, cwd=root, check=True)
    return root / "data" / "raw_manifest" / f"{RAW_SOURCE_NAME}_{as_of.isoformat()}.json"


def _write_processed_manifest(
    *,
    as_of: date,
    inputs: list[Path],
    outputs: list[Path],
    meta: dict[str, object],
    out_path: Path,
) -> None:
    root = _repo_root()
    helper = root / "scripts/make_processed_manifest.py"
    if not helper.exists():
        raise SystemExit(f"missing helper script (expected): {helper}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tf:
        json.dump(meta, tf, indent=2, sort_keys=True)
        tf.write("\n")
        meta_path = Path(tf.name)

    try:
        cmd: list[str] = [
            sys.executable,
            str(helper),
            "onchain_rollup_costs",
            "--as-of",
            as_of.isoformat(),
            "--inputs",
            *[str(p.resolve().relative_to(root.resolve())) for p in inputs],
            "--outputs",
            *[str(p.resolve().relative_to(root.resolve())) for p in outputs],
            "--meta-json",
            str(meta_path),
            "--out",
            str(out_path.resolve().relative_to(root.resolve())),
            "--",
            *_render_command_tokens_for_manifest(root),
        ]
        subprocess.run(cmd, cwd=root, check=True)
    finally:
        try:
            meta_path.unlink()
        except OSError:
            pass


def main(argv: list[str]) -> int:
    root = _repo_root()

    p = argparse.ArgumentParser(prog="l1_rollup_costs_bigquery.py")
    p.add_argument("--as-of", required=True, help="UTC as-of date for snapshot/manifests (YYYY-MM-DD)")
    p.add_argument("--start-date", default="2022-01-01", help="UTC start date (YYYY-MM-DD)")
    p.add_argument("--end-date", default=None, help="UTC end date (YYYY-MM-DD; default=as-of)")

    p.add_argument("--registry", default="registry/rollup_registry_v1.csv")
    p.add_argument("--schema-costs", default="contracts/schemas/rollup_costs_daily_v1.yaml")
    p.add_argument("--schema-decomp", default="contracts/schemas/rollup_costs_decomposition_daily_v1.yaml")

    p.add_argument("--project-id", default=None, help="Optional BigQuery billing project id (else use gcloud default)")
    p.add_argument("--location", default="US", help="BigQuery location (default=US)")

    p.add_argument("--raw-dir", default=None, help="Optional raw snapshot dir (inside repo); default=data/raw/bq_ethereum_rollup_costs/<as-of>")
    p.add_argument("--out-costs", default="data/processed/onchain/rollup_costs_daily.csv")
    p.add_argument("--out-decomp", default="data/processed/onchain/rollup_costs_decomposition_daily.csv")

    p.add_argument("--write-manifest", action="store_true", help="Write raw + processed manifests (append-only)")
    args = p.parse_args(argv[1:])

    as_of = _parse_date(str(args.as_of), label="as_of")
    start_date = _parse_date(str(args.start_date), label="start_date")
    end_date = _parse_date(str(args.end_date), label="end_date") if args.end_date else as_of
    if end_date < start_date:
        raise SystemExit(f"end_date must be >= start_date (got {end_date} < {start_date})")

    registry_path = Path(args.registry)
    registry_abs = registry_path if registry_path.is_absolute() else (root / registry_path)
    mappings, registry_meta = _load_registry_sender_mappings(registry_abs)

    raw_dir = Path(args.raw_dir) if args.raw_dir else (root / "data" / "raw" / RAW_SOURCE_NAME / as_of.isoformat())
    raw_dir_abs = raw_dir if raw_dir.is_absolute() else (root / raw_dir)
    _ensure_within_repo(root, raw_dir_abs)

    sender_cte = _render_sender_cte(mappings)
    probe = _probe_type3_blob_receipt_fields(
        sender_cte=sender_cte,
        start_date=start_date,
        end_date=end_date,
        project_id=(str(args.project_id) if args.project_id else None),
        location=(str(args.location) if args.location else None),
    )
    if probe["missing_blob_receipt_fields"] > 0:
        raise SystemExit(
            "BigQuery dataset is missing required blob receipt fields for some type-3 txs in the selected window.\n"
            f"- type3_txs: {probe['type3_txs']}\n"
            f"- missing_blob_receipt_fields: {probe['missing_blob_receipt_fields']}\n"
            "This pipeline relies on receipt_blob_gas_used and receipt_blob_gas_price to compute blob burn.\n"
            "If this persists, fall back to RPC extraction with header-based blob base fee computation."
        )
    sql_costs = _build_costs_sql(sender_cte=sender_cte, start_date=start_date, end_date=end_date)
    sql_decomp = _build_decomp_sql(sender_cte=sender_cte, start_date=start_date, end_date=end_date)

    sql_costs_path = _write_raw_dir(raw_dir=raw_dir_abs, filename="rollup_costs_daily.sql", text=sql_costs)
    sql_decomp_path = _write_raw_dir(raw_dir=raw_dir_abs, filename="rollup_costs_decomposition_daily.sql", text=sql_decomp)
    mapping_path = _write_raw_dir(raw_dir=raw_dir_abs, filename="sender_map_meta.json", text=json.dumps(registry_meta, indent=2, sort_keys=True))

    costs_csv_text, costs_stderr = _run_bq_query(sql=sql_costs, project_id=str(args.project_id) if args.project_id else None, location=str(args.location) if args.location else None)
    decomp_csv_text, decomp_stderr = _run_bq_query(sql=sql_decomp, project_id=str(args.project_id) if args.project_id else None, location=str(args.location) if args.location else None)

    raw_costs_csv = _write_raw_dir(raw_dir=raw_dir_abs, filename="rollup_costs_daily.csv", text=costs_csv_text)
    raw_decomp_csv = _write_raw_dir(raw_dir=raw_dir_abs, filename="rollup_costs_decomposition_daily.csv", text=decomp_csv_text)
    _write_raw_dir(raw_dir=raw_dir_abs, filename="bq_stderr_daily.log", text=costs_stderr)
    _write_raw_dir(raw_dir=raw_dir_abs, filename="bq_stderr_decomposition.log", text=decomp_stderr)

    schema_costs = Path(args.schema_costs)
    schema_decomp = Path(args.schema_decomp)
    schema_costs_abs = schema_costs if schema_costs.is_absolute() else (root / schema_costs)
    schema_decomp_abs = schema_decomp if schema_decomp.is_absolute() else (root / schema_decomp)

    costs_fields, costs_nullable = _load_schema_fields(schema_costs_abs)
    decomp_fields, decomp_nullable = _load_schema_fields(schema_decomp_abs)
    contract_costs = _assert_contract(schema_path=schema_costs_abs, expected_fields=costs_fields)
    contract_decomp = _assert_contract(schema_path=schema_decomp_abs, expected_fields=decomp_fields)

    required_costs = [f for f in costs_fields if not costs_nullable[f]]
    required_decomp = [f for f in decomp_fields if not decomp_nullable[f]]

    counts_costs = _validate_csv_contract(csv_path=raw_costs_csv, expected_fields=costs_fields, required_fields=required_costs)
    counts_decomp = _validate_csv_contract(csv_path=raw_decomp_csv, expected_fields=decomp_fields, required_fields=required_decomp)

    out_costs = Path(args.out_costs)
    out_decomp = Path(args.out_decomp)
    out_costs_abs = out_costs if out_costs.is_absolute() else (root / out_costs)
    out_decomp_abs = out_decomp if out_decomp.is_absolute() else (root / out_decomp)
    _ensure_within_repo(root, out_costs_abs)
    _ensure_within_repo(root, out_decomp_abs)

    _copy_csv(src=raw_costs_csv, dst=out_costs_abs, fieldnames=costs_fields)
    _copy_csv(src=raw_decomp_csv, dst=out_decomp_abs, fieldnames=decomp_fields)

    raw_manifest_path: Path | None = None
    if args.write_manifest:
        raw_manifest_path = _write_raw_manifest(snapshot_dir=raw_dir_abs, as_of=as_of)
        processed_out = root / "data" / "processed_manifest" / f"onchain_rollup_costs_{as_of.isoformat()}.json"
        meta = {
            "source": {
                "type": "bigquery",
                "blocks_table": BQ_BLOCKS_TABLE,
                "txs_table": BQ_TXS_TABLE,
                "project_id": (str(args.project_id) if args.project_id else None),
                "location": (str(args.location) if args.location else None),
            },
            "date_range_utc": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "probe": probe,
            "registry": {
                "path": str(_ensure_within_repo(root, registry_abs.resolve())),
                "sha256": _sha256_file(registry_abs),
                "universe": registry_meta,
            },
            "raw_snapshot": {
                "dir": str(_ensure_within_repo(root, raw_dir_abs.resolve())),
                "sql_sha256": {"costs": _sha256_text(sql_costs), "decomposition": _sha256_text(sql_decomp)},
                "sql_paths": {
                    "costs": str(_ensure_within_repo(root, sql_costs_path.resolve())),
                    "decomposition": str(_ensure_within_repo(root, sql_decomp_path.resolve())),
                    "sender_meta": str(_ensure_within_repo(root, mapping_path.resolve())),
                },
            },
            "contracts": {
                "rollup_costs_daily_v1": {
                    "schema_path": str(_ensure_within_repo(root, schema_costs_abs.resolve())),
                    "sha256": _sha256_file(schema_costs_abs),
                    "contract_assertions": contract_costs,
                    "required_fields": required_costs,
                },
                "rollup_costs_decomposition_daily_v1": {
                    "schema_path": str(_ensure_within_repo(root, schema_decomp_abs.resolve())),
                    "sha256": _sha256_file(schema_decomp_abs),
                    "contract_assertions": contract_decomp,
                    "required_fields": required_decomp,
                },
            },
            "counts": {"costs": counts_costs, "decomposition": counts_decomp},
            "notes": [
                "Attribution uses sender allowlist from registry batcher_addresses_json (from_address match only).",
                "Blob burn uses receipt_blob_gas_used * receipt_blob_gas_price (wei).",
                "Row omission encodes missingness: rollup-days appear only when at least one attributed tx exists.",
            ],
        }

        processed_inputs = [raw_manifest_path, registry_abs, schema_costs_abs, schema_decomp_abs]
        processed_outputs = [out_costs_abs, out_decomp_abs]
        _write_processed_manifest(
            as_of=as_of,
            inputs=processed_inputs,
            outputs=processed_outputs,
            meta=meta,
            out_path=processed_out,
        )

    print(
        json.dumps(
            {
                "ok": True,
                "as_of_utc_date": as_of.isoformat(),
                "date_range_utc": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "raw_dir": str(raw_dir_abs),
                "out_costs": str(out_costs_abs),
                "out_decomposition": str(out_decomp_abs),
                "manifests": {
                    "raw": str(raw_manifest_path) if raw_manifest_path is not None else None,
                    "processed": (str(root / "data" / "processed_manifest" / f"onchain_rollup_costs_{as_of.isoformat()}.json") if args.write_manifest else None),
                },
                "counts": {"costs": counts_costs, "decomposition": counts_decomp},
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
