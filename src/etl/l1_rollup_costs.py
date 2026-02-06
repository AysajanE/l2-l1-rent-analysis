from __future__ import annotations

"""On-chain: compute rollup-attributed daily L1 rent + decomposition (contract v1).

This module is deterministic and stdlib-only. It consumes the processed CSV outputs from:
- `src/etl/l1_extract_blocks.py`
- `src/etl/l1_extract_txs_receipts.py`
and attributes transactions to rollups using `registry/rollup_registry_v1.csv` batcher/poster addresses.

Outputs (defaults):
- `data/processed/onchain/rollup_costs_daily.csv`
- `data/processed/onchain/rollup_costs_decomposition_daily.csv`
- Optional processed manifest: `data/processed_manifest/onchain_rollup_costs_<YYYY-MM-DD>.json`

Design notes:
- Attribution is conservative: we only attribute by `from_address` matching the registry allowlist.
- Rollup-days are emitted iff at least one attributed transaction is observed for that rollup-day.
  (Row omission encodes missingness; do not coerce unknown spend to 0.)
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
from decimal import Decimal
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so `src.*` namespace imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.etl.l1_fee_components import compute_fee_components_wei  # noqa: E402


COSTS_DAILY_OUTPUT_COLUMNS = ("date_utc", "rollup_id", "rent_paid_eth", "rent_paid_wei")
DECOMP_OUTPUT_COLUMNS = (
    "date_utc",
    "rollup_id",
    "rent_paid_eth",
    "rent_base_fee_burn_eth",
    "rent_blob_fee_burn_eth",
    "rent_priority_fee_eth",
    "rollup_blob_gas_used",
    "rent_paid_wei",
    "rent_blob_fee_burn_wei",
    "rent_base_fee_burn_wei",
    "rent_priority_fee_wei",
    "unattributed_rent_eth",
)


def _repo_root() -> Path:
    return REPO_ROOT


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


def _parse_int_optional(value: Any, *, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return int(value)
    s = str(value).strip()
    if s == "":
        return None
    try:
        return int(s)
    except ValueError as exc:
        raise SystemExit(f"Invalid int for {label}: {value!r}") from exc


def _unquote_yaml_scalar(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    return v


def _load_schema_fields(schema_path: Path) -> tuple[tuple[str, ...], dict[str, bool]]:
    """Parse a minimal subset of YAML schemas (stdlib-only).

    Supports the structure used in `contracts/schemas/*_v1.yaml`:
      fields:
        - name: foo
          nullable: false
    """
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
            "Contract mismatch: schema field order differs from builder output.\n"
            f"- schema_path: {schema_path}\n"
            f"- schema_fields: {list(schema_fields)}\n"
            f"- expected_fields: {list(expected_fields)}\n"
            "Update the builder to match the locked schema, or update the schema with a W0 decision."
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
class RegistryAddress:
    rollup_id: str
    address_lc: str
    start_date_utc: date | None
    end_date_utc: date | None
    role: str
    evidence_url: str
    verified_utc: str

    def includes(self, d: date) -> bool:
        if self.start_date_utc is not None and d < self.start_date_utc:
            return False
        if self.end_date_utc is not None and d > self.end_date_utc:
            return False
        return True


def load_registry(path: Path) -> tuple[dict[str, RegistryRollup], dict[str, list[RegistryAddress]]]:
    if not path.exists():
        raise SystemExit(f"registry not found: {path}")

    rollups: dict[str, RegistryRollup] = {}
    by_address: dict[str, list[RegistryAddress]] = {}

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
                role = str(a.get("role") or "").strip()
                evidence_url = str(a.get("evidence_url") or "").strip()
                verified_utc = str(a.get("verified_utc") or "").strip()
                addr_start = _parse_optional_date(str(a.get("start_date_utc") or ""))
                addr_end = _parse_optional_date(str(a.get("end_date_utc") or ""))
                entry = RegistryAddress(
                    rollup_id=rollup_id,
                    address_lc=addr_lc,
                    start_date_utc=addr_start,
                    end_date_utc=addr_end,
                    role=role,
                    evidence_url=evidence_url,
                    verified_utc=verified_utc,
                )
                by_address.setdefault(addr_lc, []).append(entry)

    if not rollups:
        raise SystemExit(f"registry is empty: {path}")
    return rollups, by_address


def _resolve_rollup_id(
    *,
    rollups: dict[str, RegistryRollup],
    by_address: dict[str, list[RegistryAddress]],
    from_address_lc: str,
    date_utc: date,
) -> str | None:
    candidates = by_address.get(from_address_lc, [])
    if not candidates:
        return None
    matches = [c for c in candidates if c.includes(date_utc)]
    if not matches:
        return None
    rollup_ids = sorted({m.rollup_id for m in matches})
    if len(rollup_ids) != 1:
        raise SystemExit(
            "Attribution ambiguity: sender address maps to multiple rollups for this date.\n"
            f"- from_address: {from_address_lc}\n"
            f"- date_utc: {date_utc.isoformat()}\n"
            f"- rollup_ids: {rollup_ids}\n"
            "Resolve by adding validity windows in the registry (T082) or block with @human."
        )
    rid = rollup_ids[0]
    reg = rollups.get(rid)
    if reg is None:
        return None
    return rid if reg.includes(date_utc) else None


@dataclass(frozen=True)
class BlockInfo:
    date_utc: date
    base_fee_per_gas_wei: int
    excess_blob_gas: int | None


def _load_blocks(path: Path) -> dict[int, BlockInfo]:
    if not path.exists():
        raise SystemExit(f"blocks CSV not found: {path}")
    blocks: dict[int, BlockInfo] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("blocks CSV missing header row")
        required = {"block_number", "date_utc", "base_fee_per_gas_wei", "excess_blob_gas"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise SystemExit(f"blocks CSV missing required columns: {missing}")
        for i, row in enumerate(reader, start=2):
            bn = _parse_int_optional(row.get("block_number"), label="block_number")
            if bn is None:
                raise SystemExit(f"blocks row {i}: missing block_number")
            d = _parse_date(str(row.get("date_utc") or "").strip(), label="date_utc")
            base_fee = _parse_int_optional(row.get("base_fee_per_gas_wei"), label="base_fee_per_gas_wei")
            if base_fee is None:
                raise SystemExit(f"blocks row {i}: missing base_fee_per_gas_wei")
            excess_blob_gas = _parse_int_optional(row.get("excess_blob_gas"), label="excess_blob_gas")
            blocks[bn] = BlockInfo(date_utc=d, base_fee_per_gas_wei=int(base_fee), excess_blob_gas=excess_blob_gas)
    if not blocks:
        raise SystemExit(f"blocks CSV is empty: {path}")
    return blocks


@dataclass(frozen=True)
class TxInfo:
    tx_type: int | None
    from_address_lc: str
    blob_hashes_count: int | None
    tx_max_fee_per_blob_gas_wei: int | None


def _load_txs(path: Path) -> dict[str, TxInfo]:
    if not path.exists():
        raise SystemExit(f"txs CSV not found: {path}")
    out: dict[str, TxInfo] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("txs CSV missing header row")
        required = {"tx_hash", "from_address", "tx_type", "blobVersionedHashes_count", "max_fee_per_blob_gas_wei"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise SystemExit(f"txs CSV missing required columns: {missing}")
        for i, row in enumerate(reader, start=2):
            tx_hash = (row.get("tx_hash") or "").strip()
            if tx_hash == "":
                raise SystemExit(f"txs row {i}: missing tx_hash")
            if tx_hash in out:
                raise SystemExit(f"txs row {i}: duplicate tx_hash: {tx_hash}")
            tx_type = _parse_int_optional(row.get("tx_type"), label="tx_type")
            sender = (row.get("from_address") or "").strip().lower()
            if sender == "":
                raise SystemExit(f"txs row {i}: missing from_address")
            blob_count = _parse_int_optional(row.get("blobVersionedHashes_count"), label="blobVersionedHashes_count")
            max_fee_blob = _parse_int_optional(row.get("max_fee_per_blob_gas_wei"), label="max_fee_per_blob_gas_wei")
            out[tx_hash] = TxInfo(
                tx_type=tx_type,
                from_address_lc=sender,
                blob_hashes_count=blob_count,
                tx_max_fee_per_blob_gas_wei=max_fee_blob,
            )
    if not out:
        raise SystemExit(f"txs CSV is empty: {path}")
    return out


def _eth_from_wei_str(wei: int) -> str:
    d = Decimal(int(wei)) / Decimal(10**18)
    return format(d, "f")


@dataclass
class AggWei:
    rent_paid_wei: int = 0
    burn_base_wei: int = 0
    burn_blob_wei: int = 0
    tips_wei: int = 0
    blob_gas_used: int = 0
    txs: int = 0
    type3_txs: int = 0


def compute_rollup_costs(
    *,
    blocks: dict[int, BlockInfo],
    txs: dict[str, TxInfo],
    receipts_csv: Path,
    rollups: dict[str, RegistryRollup],
    by_address: dict[str, list[RegistryAddress]],
) -> tuple[dict[tuple[str, str], AggWei], dict[str, int]]:
    if not receipts_csv.exists():
        raise SystemExit(f"receipts CSV not found: {receipts_csv}")

    counts = {
        "receipts_rows": 0,
        "txs_joined": 0,
        "txs_attributed": 0,
        "type3_txs": 0,
        "type3_txs_blob_fields_missing": 0,
    }

    buckets: dict[tuple[str, str], AggWei] = {}

    with receipts_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("receipts CSV missing header row")
        required = {"tx_hash", "block_number", "gas_used", "effective_gas_price_wei", "blobGasUsed", "blobGasPrice"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise SystemExit(f"receipts CSV missing required columns: {missing}")

        for i, row in enumerate(reader, start=2):
            counts["receipts_rows"] += 1
            tx_hash = (row.get("tx_hash") or "").strip()
            if tx_hash == "":
                raise SystemExit(f"receipts row {i}: missing tx_hash")
            tx_info = txs.get(tx_hash)
            if tx_info is None:
                raise SystemExit(
                    f"receipts row {i}: tx_hash not found in txs CSV (inconsistent extract?): {tx_hash}"
                )

            bn = _parse_int_optional(row.get("block_number"), label="block_number")
            if bn is None:
                raise SystemExit(f"receipts row {i}: missing block_number")
            block = blocks.get(int(bn))
            if block is None:
                raise SystemExit(
                    f"receipts row {i}: block_number not found in blocks CSV (inconsistent extract?): {bn}"
                )

            d = block.date_utc
            rid = _resolve_rollup_id(rollups=rollups, by_address=by_address, from_address_lc=tx_info.from_address_lc, date_utc=d)
            if rid is None:
                raise SystemExit(
                    "Unattributed tx found (sender not in registry or outside validity window).\n"
                    f"- tx_hash: {tx_hash}\n"
                    f"- from_address: {tx_info.from_address_lc}\n"
                    f"- date_utc: {d.isoformat()}\n"
                    "Fix registry coverage/validity windows (T082) or rerun extraction with registry filtering."
                )
            counts["txs_attributed"] += 1

            gas_used = _parse_int_optional(row.get("gas_used"), label="gas_used")
            eff_price = _parse_int_optional(row.get("effective_gas_price_wei"), label="effective_gas_price_wei")
            if gas_used is None or eff_price is None:
                raise SystemExit(f"receipts row {i}: missing gas_used/effective_gas_price_wei for tx {tx_hash}")

            receipt_blob_gas_used = _parse_int_optional(row.get("blobGasUsed"), label="blobGasUsed")
            receipt_blob_gas_price = _parse_int_optional(row.get("blobGasPrice"), label="blobGasPrice")

            try:
                fee = compute_fee_components_wei(
                    gas_used=int(gas_used),
                    effective_gas_price_wei=int(eff_price),
                    base_fee_per_gas_wei=int(block.base_fee_per_gas_wei),
                    tx_type=tx_info.tx_type,
                    receipt_blob_gas_used=receipt_blob_gas_used,
                    receipt_blob_gas_price_wei=receipt_blob_gas_price,
                    tx_blob_versioned_hashes_count=tx_info.blob_hashes_count,
                    block_excess_blob_gas=block.excess_blob_gas,
                    tx_max_fee_per_blob_gas_wei=tx_info.tx_max_fee_per_blob_gas_wei,
                )
            except ValueError as exc:
                if tx_info.tx_type == 3:
                    counts["type3_txs_blob_fields_missing"] += 1
                raise SystemExit(f"fee component computation failed for tx {tx_hash}: {exc}") from exc

            if tx_info.tx_type == 3:
                counts["type3_txs"] += 1

            key = (d.isoformat(), rid)
            b = buckets.get(key)
            if b is None:
                b = AggWei()
                buckets[key] = b

            b.rent_paid_wei += int(fee.rent_paid_wei)
            b.burn_base_wei += int(fee.burn_base_wei)
            b.burn_blob_wei += int(fee.burn_blob_wei)
            b.tips_wei += int(fee.tips_wei)
            b.blob_gas_used += int(fee.blob_gas_used)
            b.txs += 1
            if tx_info.tx_type == 3:
                b.type3_txs += 1

            counts["txs_joined"] += 1

    return buckets, counts


def _write_csv(path: Path, *, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def _command_tokens_for_manifest(root: Path) -> list[str]:
    argv0 = Path(sys.argv[0])
    try:
        argv0_rel = _ensure_within_repo(root, argv0.resolve())
        script_token = str(argv0_rel)
    except SystemExit:
        script_token = sys.argv[0]
    return ["python", script_token, *sys.argv[1:]]


def _write_processed_manifest(
    *,
    as_of: date,
    manifest_out: Path | None,
    inputs: list[Path],
    outputs: list[Path],
    meta: dict[str, object],
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
            *[str(_ensure_within_repo(root, p.resolve())) for p in inputs],
            "--outputs",
            *[str(_ensure_within_repo(root, p.resolve())) for p in outputs],
            "--meta-json",
            str(meta_path),
        ]
        if manifest_out is not None:
            cmd.extend(["--out", str(_ensure_within_repo(root, manifest_out.resolve()))])
        cmd.extend(["--", *_command_tokens_for_manifest(root)])
        subprocess.run(cmd, cwd=root, check=True)
    finally:
        try:
            meta_path.unlink()
        except OSError:
            pass


def main(argv: list[str]) -> int:
    root = _repo_root()

    p = argparse.ArgumentParser(prog="l1_rollup_costs.py")
    p.add_argument("--registry", default="registry/rollup_registry_v1.csv")
    p.add_argument("--blocks-csv", default="data/processed/l1/l1_blocks.csv")
    p.add_argument("--txs-csv", default="data/processed/l1/l1_txs.csv")
    p.add_argument("--receipts-csv", default="data/processed/l1/l1_receipts.csv")
    p.add_argument("--schema-costs", default="contracts/schemas/rollup_costs_daily_v1.yaml")
    p.add_argument("--schema-decomp", default="contracts/schemas/rollup_costs_decomposition_daily_v1.yaml")

    p.add_argument("--out-costs", default="data/processed/onchain/rollup_costs_daily.csv")
    p.add_argument("--out-decomp", default="data/processed/onchain/rollup_costs_decomposition_daily.csv")

    p.add_argument("--write-manifest", action="store_true", help="Write a processed manifest via scripts/make_processed_manifest.py")
    p.add_argument("--as-of", default=None, help="Manifest as-of date (YYYY-MM-DD, UTC)")
    p.add_argument("--manifest-out", default=None, help="Optional output path for manifest JSON")
    args = p.parse_args(argv[1:])

    registry_path = Path(args.registry)
    blocks_csv = Path(args.blocks_csv)
    txs_csv = Path(args.txs_csv)
    receipts_csv = Path(args.receipts_csv)

    out_costs = Path(args.out_costs)
    out_decomp = Path(args.out_decomp)

    schema_costs = Path(args.schema_costs)
    schema_decomp = Path(args.schema_decomp)
    schema_costs_abs = schema_costs if schema_costs.is_absolute() else (root / schema_costs)
    schema_decomp_abs = schema_decomp if schema_decomp.is_absolute() else (root / schema_decomp)

    contract_costs = _assert_contract(schema_path=schema_costs_abs, expected_fields=COSTS_DAILY_OUTPUT_COLUMNS)
    contract_decomp = _assert_contract(schema_path=schema_decomp_abs, expected_fields=DECOMP_OUTPUT_COLUMNS)

    rollups, by_address = load_registry(registry_path if registry_path.is_absolute() else (root / registry_path))
    blocks = _load_blocks(blocks_csv if blocks_csv.is_absolute() else (root / blocks_csv))
    txs = _load_txs(txs_csv if txs_csv.is_absolute() else (root / txs_csv))

    buckets, counts = compute_rollup_costs(
        blocks=blocks,
        txs=txs,
        receipts_csv=(receipts_csv if receipts_csv.is_absolute() else (root / receipts_csv)),
        rollups=rollups,
        by_address=by_address,
    )

    # Build outputs.
    keys = sorted(buckets.keys())
    costs_rows: list[dict[str, str]] = []
    decomp_rows: list[dict[str, str]] = []
    for date_str, rollup_id in keys:
        b = buckets[(date_str, rollup_id)]
        row_costs = {
            "date_utc": date_str,
            "rollup_id": rollup_id,
            "rent_paid_eth": _eth_from_wei_str(b.rent_paid_wei),
            "rent_paid_wei": str(b.rent_paid_wei),
        }
        costs_rows.append(row_costs)

        row_decomp = {
            "date_utc": date_str,
            "rollup_id": rollup_id,
            "rent_paid_eth": _eth_from_wei_str(b.rent_paid_wei),
            "rent_base_fee_burn_eth": _eth_from_wei_str(b.burn_base_wei),
            "rent_blob_fee_burn_eth": _eth_from_wei_str(b.burn_blob_wei),
            "rent_priority_fee_eth": _eth_from_wei_str(b.tips_wei),
            "rollup_blob_gas_used": str(b.blob_gas_used),
            "rent_paid_wei": str(b.rent_paid_wei),
            "rent_blob_fee_burn_wei": str(b.burn_blob_wei),
            "rent_base_fee_burn_wei": str(b.burn_base_wei),
            "rent_priority_fee_wei": str(b.tips_wei),
            "unattributed_rent_eth": "",
        }
        decomp_rows.append(row_decomp)

    _write_csv(out_costs if out_costs.is_absolute() else (root / out_costs), fieldnames=COSTS_DAILY_OUTPUT_COLUMNS, rows=costs_rows)
    _write_csv(out_decomp if out_decomp.is_absolute() else (root / out_decomp), fieldnames=DECOMP_OUTPUT_COLUMNS, rows=decomp_rows)

    if args.write_manifest:
        if args.as_of is None:
            raise SystemExit("Missing --as-of (required with --write-manifest)")
        as_of = _parse_date(str(args.as_of), label="as_of")
        manifest_out = Path(args.manifest_out) if args.manifest_out else None

        registry_abs = registry_path if registry_path.is_absolute() else (root / registry_path)
        meta = {
            "contracts": {
                "rollup_costs_daily_v1": {
                    "schema_path": str(_ensure_within_repo(root, schema_costs_abs.resolve())),
                    "sha256": _sha256_file(schema_costs_abs.resolve()),
                    "contract_assertions": contract_costs,
                },
                "rollup_costs_decomposition_daily_v1": {
                    "schema_path": str(_ensure_within_repo(root, schema_decomp_abs.resolve())),
                    "sha256": _sha256_file(schema_decomp_abs.resolve()),
                    "contract_assertions": contract_decomp,
                },
            },
            "registry": {
                "path": str(_ensure_within_repo(root, registry_abs.resolve())),
                "sha256": _sha256_file(registry_abs.resolve()),
                "in_scope_rollups": sorted([k for k, v in rollups.items() if v.in_scope and v.status != "deprecated"]),
                "sender_addresses": len(by_address),
            },
            "counts": counts,
            "notes": [
                "Attribution uses only from_address allowlist (registry batcher_addresses_json).",
                "Rollup-days are emitted iff at least one attributed tx is observed for that rollup-day.",
                "Blob burn uses receipt blob fields when present; otherwise header excessBlobGas fallback per EIP-4844.",
            ],
        }

        inputs = [
            registry_abs,
            (blocks_csv if blocks_csv.is_absolute() else (root / blocks_csv)),
            (txs_csv if txs_csv.is_absolute() else (root / txs_csv)),
            (receipts_csv if receipts_csv.is_absolute() else (root / receipts_csv)),
            schema_costs_abs,
            schema_decomp_abs,
        ]
        outputs = [
            (out_costs if out_costs.is_absolute() else (root / out_costs)),
            (out_decomp if out_decomp.is_absolute() else (root / out_decomp)),
        ]
        _write_processed_manifest(as_of=as_of, manifest_out=manifest_out, inputs=inputs, outputs=outputs, meta=meta)

    print(json.dumps({"ok": True, "rows": len(keys), "out_costs": str(out_costs), "out_decomp": str(out_decomp), "counts": counts}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
