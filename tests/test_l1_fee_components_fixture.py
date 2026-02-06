import json
import unittest
from pathlib import Path

from src.etl.l1_fee_components import compute_fee_components_wei


class FeeComponentsFixtureTest(unittest.TestCase):
    def test_blob_tx_fee_components_fixture(self) -> None:
        root = Path(__file__).resolve().parents[1]
        fixture = root / "data" / "samples" / "l1" / "fixtures" / "blob_tx_fee_components_v1.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("schema_version"), 1)
        cases = payload.get("cases")
        self.assertIsInstance(cases, list)
        self.assertGreater(len(cases), 0)

        for case in cases:
            self.assertIsInstance(case, dict)
            name = case.get("name")
            self.assertIsInstance(name, str)
            inputs = case.get("inputs")
            expected = case.get("expected")
            self.assertIsInstance(inputs, dict, msg=name)
            self.assertIsInstance(expected, dict, msg=name)

            got = compute_fee_components_wei(
                gas_used=int(inputs["gas_used"]),
                effective_gas_price_wei=int(inputs["effective_gas_price_wei"]),
                base_fee_per_gas_wei=int(inputs["base_fee_per_gas_wei"]),
                tx_type=inputs.get("tx_type"),
                receipt_blob_gas_used=inputs.get("receipt_blob_gas_used"),
                receipt_blob_gas_price_wei=inputs.get("receipt_blob_gas_price_wei"),
                tx_blob_versioned_hashes_count=inputs.get("tx_blob_versioned_hashes_count"),
                block_excess_blob_gas=inputs.get("block_excess_blob_gas"),
                tx_max_fee_per_blob_gas_wei=inputs.get("tx_max_fee_per_blob_gas_wei"),
            )

            self.assertEqual(int(got.burn_base_wei), expected.get("burn_base_wei"), msg=name)
            self.assertEqual(int(got.tips_wei), expected.get("tips_wei"), msg=name)
            self.assertEqual(int(got.burn_blob_wei), expected.get("burn_blob_wei"), msg=name)
            self.assertEqual(int(got.blob_gas_used), expected.get("blob_gas_used"), msg=name)
            self.assertEqual(got.base_fee_per_blob_gas_wei, expected.get("base_fee_per_blob_gas_wei"), msg=name)


if __name__ == "__main__":
    unittest.main()

