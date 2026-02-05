import csv
import hashlib
import json
import unittest
from pathlib import Path

from src.analysis.counterfactual_eip7918 import SUMMARY_COLUMNS, compute_daily_counterfactual, load_panel_csv


REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_meta_json(summary_csv: Path) -> dict[str, object]:
    with summary_csv.open("r", encoding="utf-8", newline="") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("# meta_json:"):
                payload = line.split(":", 1)[1].strip()
                return json.loads(payload)
            if not line.lstrip().startswith("#") and line.strip() != "":
                break
    raise AssertionError(f"missing meta_json header: {summary_csv}")


def _load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        raw_lines = f.readlines()
    lines = [ln for ln in raw_lines if not ln.lstrip().startswith("#") and ln.strip() != ""]
    reader = csv.DictReader(lines)
    if reader.fieldnames is None:
        raise AssertionError(f"missing header: {path}")
    rows = [dict(r) for r in reader]
    return list(reader.fieldnames), rows


def _normalize_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class CounterfactualEip7918SampleTest(unittest.TestCase):
    def test_summary_csv_rows_match_compute(self) -> None:
        panel = REPO_ROOT / "data/samples/panels/daily_rollup_panel_v2_sample.csv"
        summary = REPO_ROOT / "reports/tables/eip7918_counterfactual_summary_sample.csv"
        self.assertTrue(panel.exists())
        self.assertTrue(summary.exists())

        fieldnames, panel_rows = load_panel_csv(panel)
        self.assertIn("date_utc", fieldnames)
        self.assertIn("rollup_id", fieldnames)

        computed = compute_daily_counterfactual(panel_rows)
        out_cols, out_rows = _load_csv_rows(summary)

        self.assertEqual(out_cols, SUMMARY_COLUMNS)
        self.assertEqual(len(out_rows), len(computed))

        for i, (got, exp) in enumerate(zip(out_rows, computed, strict=True)):
            norm_exp = {k: _normalize_value(exp.get(k, "")) for k in SUMMARY_COLUMNS}
            norm_got = {k: (got.get(k) or "") for k in SUMMARY_COLUMNS}
            self.assertEqual(norm_got, norm_exp, msg=f"row mismatch at idx={i} date={norm_got.get('date_utc')}")

        by_date = {r["date_utc"]: r for r in out_rows}
        self.assertIn("2024-03-14", by_date)
        binding = by_date["2024-03-14"]
        self.assertEqual(binding["floor_binding"], "true")
        self.assertEqual(binding["l1_blob_base_fee_wei"], "2000000000")
        self.assertEqual(binding["reserve_blob_base_fee_wei"], "3000000000")
        self.assertEqual(binding["cf_blob_base_fee_wei"], "3000000000")
        self.assertGreater(float(binding["delta_rent_blob_burn_eth_sum"]), 0.0)

    def test_summary_meta_json_has_assumptions_and_input_hash(self) -> None:
        panel = REPO_ROOT / "data/samples/panels/daily_rollup_panel_v2_sample.csv"
        summary = REPO_ROOT / "reports/tables/eip7918_counterfactual_summary_sample.csv"
        meta = _load_meta_json(summary)

        assumptions = meta.get("assumptions")
        self.assertIsInstance(assumptions, dict)
        assumption_ids = assumptions.get("assumption_ids")
        self.assertEqual(assumption_ids, ["A001"])

        constants = assumptions.get("constants")
        self.assertIsInstance(constants, dict)
        self.assertEqual(constants.get("BLOB_BASE_COST"), 8192)
        self.assertEqual(constants.get("GAS_PER_BLOB"), 131072)
        self.assertEqual(constants.get("WEI_PER_ETH"), 10**18)

        inputs = meta.get("inputs")
        self.assertIsInstance(inputs, dict)
        self.assertEqual(inputs.get("panel_path"), "data/samples/panels/daily_rollup_panel_v2_sample.csv")
        self.assertEqual(inputs.get("panel_sha256"), _sha256_file(panel))
        self.assertIsNone(inputs.get("panel_manifest_sha256"))

        self.assertEqual(meta.get("tag"), "sample")
        self.assertEqual(meta.get("schema_version"), 1)
        self.assertEqual(meta.get("script_path"), "src/analysis/counterfactual_eip7918.py")

    def test_run_manifest_hashes_match_files(self) -> None:
        run_json = REPO_ROOT / "reports/tables/eip7918_counterfactual_summary_sample_run.json"
        summary = REPO_ROOT / "reports/tables/eip7918_counterfactual_summary_sample.csv"
        svg = REPO_ROOT / "reports/figures/eip7918_counterfactual_sample.svg"
        panel = REPO_ROOT / "data/samples/panels/daily_rollup_panel_v2_sample.csv"

        payload = json.loads(run_json.read_text(encoding="utf-8"))
        self.assertIn("assumptions", payload)
        self.assertEqual(payload["assumptions"]["assumption_ids"], ["A001"])

        inputs = payload.get("inputs")
        self.assertIsInstance(inputs, list)
        self.assertGreaterEqual(len(inputs), 1)
        self.assertEqual(inputs[0]["path"], "data/samples/panels/daily_rollup_panel_v2_sample.csv")
        self.assertEqual(inputs[0]["sha256"], _sha256_file(panel))

        outputs = payload.get("outputs")
        self.assertIsInstance(outputs, list)
        out_by_path = {o["path"]: o for o in outputs}
        self.assertIn("reports/tables/eip7918_counterfactual_summary_sample.csv", out_by_path)
        self.assertIn("reports/figures/eip7918_counterfactual_sample.svg", out_by_path)
        self.assertEqual(out_by_path["reports/tables/eip7918_counterfactual_summary_sample.csv"]["sha256"], _sha256_file(summary))
        self.assertEqual(out_by_path["reports/figures/eip7918_counterfactual_sample.svg"]["sha256"], _sha256_file(svg))


if __name__ == "__main__":
    unittest.main()

