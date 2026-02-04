import math
import unittest

from src.analysis.metrics_str import compute_daily_ecosystem_str, compute_rollup_str_rows


class MetricsStrTest(unittest.TestCase):
    def test_daily_ecosystem_str_basic(self) -> None:
        rows = [
            {"date_utc": "2024-01-01", "rollup_id": "a", "l2_fees_eth": 10, "rent_paid_eth": 1},
            {"date_utc": "2024-01-01", "rollup_id": "b", "l2_fees_eth": 20, "rent_paid_eth": 4},
        ]
        daily = compute_daily_ecosystem_str(rows)
        self.assertEqual(len(daily), 1)
        r = daily[0]
        self.assertEqual(r.date_utc, "2024-01-01")
        self.assertEqual(r.included_rollup_days, 2)
        self.assertEqual(r.skipped_rows, 0)
        self.assertAlmostEqual(r.l2_fees_eth_sum, 30.0)
        self.assertAlmostEqual(r.rent_paid_eth_sum, 5.0)
        self.assertAlmostEqual(r.str_value, 5.0 / 30.0)

    def test_daily_ecosystem_str_denominator_zero_is_nan(self) -> None:
        rows = [
            {"date_utc": "2024-01-02", "rollup_id": "a", "l2_fees_eth": 0, "rent_paid_eth": 0},
        ]
        daily = compute_daily_ecosystem_str(rows)
        self.assertEqual(len(daily), 1)
        r = daily[0]
        self.assertEqual(r.included_rollup_days, 1)
        self.assertEqual(r.l2_fees_eth_sum, 0.0)
        self.assertTrue(math.isnan(r.str_value))

    def test_missingness_rule_skips_row(self) -> None:
        rows = [
            {"date_utc": "2024-01-03", "rollup_id": "a", "l2_fees_eth": 10, "rent_paid_eth": ""},
            {"date_utc": "2024-01-03", "rollup_id": "b", "l2_fees_eth": "10", "rent_paid_eth": "1"},
        ]
        daily = compute_daily_ecosystem_str(rows)
        self.assertEqual(len(daily), 1)
        r = daily[0]
        self.assertEqual(r.included_rollup_days, 1)
        self.assertEqual(r.skipped_rows, 1)
        self.assertAlmostEqual(r.l2_fees_eth_sum, 10.0)
        self.assertAlmostEqual(r.rent_paid_eth_sum, 1.0)
        self.assertAlmostEqual(r.str_value, 0.1)

    def test_rollup_str_rows_fee_zero_is_nan(self) -> None:
        rows = [
            {"date_utc": "2024-01-04", "rollup_id": "a", "l2_fees_eth": 0, "rent_paid_eth": 1},
        ]
        out = compute_rollup_str_rows(rows)
        self.assertEqual(len(out), 1)
        self.assertTrue(math.isnan(out[0].str_value))

    def test_negative_values_raise(self) -> None:
        rows = [
            {"date_utc": "2024-01-05", "rollup_id": "a", "l2_fees_eth": -1, "rent_paid_eth": 1},
        ]
        with self.assertRaises(ValueError):
            compute_rollup_str_rows(rows)


if __name__ == "__main__":
    unittest.main()

