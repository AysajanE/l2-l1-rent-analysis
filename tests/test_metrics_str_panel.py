import math
import unittest

from src.analysis.metrics_str_panel import (
    compute_daily_str_series,
    compute_rollup_str_contributions,
)


class MetricsStrPanelTest(unittest.TestCase):
    def test_daily_str_basic_fixture(self) -> None:
        rows = [
            {"date_utc": "2024-01-01", "rollup_id": "a", "l2_fees_eth": 10, "rent_paid_eth": 1},
            {"date_utc": "2024-01-01", "rollup_id": "b", "l2_fees_eth": 20, "rent_paid_eth": 4},
            {"date_utc": "2024-01-02", "rollup_id": "a", "l2_fees_eth": 5, "rent_paid_eth": 2},
        ]

        daily = compute_daily_str_series(rows)
        self.assertEqual(len(daily), 2)

        day_1 = daily[0]
        self.assertEqual(day_1.date_utc, "2024-01-01")
        self.assertEqual(day_1.included_rollup_days, 2)
        self.assertEqual(day_1.skipped_rows, 0)
        self.assertAlmostEqual(day_1.l2_fees_eth_sum, 30.0)
        self.assertAlmostEqual(day_1.rent_paid_eth_sum, 5.0)
        self.assertAlmostEqual(day_1.str_value, 5.0 / 30.0)

        day_2 = daily[1]
        self.assertEqual(day_2.date_utc, "2024-01-02")
        self.assertAlmostEqual(day_2.str_value, 2.0 / 5.0)

    def test_daily_str_denominator_zero_is_nan(self) -> None:
        rows = [
            {"date_utc": "2024-01-03", "rollup_id": "a", "l2_fees_eth": 0, "rent_paid_eth": 0},
            {"date_utc": "2024-01-03", "rollup_id": "b", "l2_fees_eth": 0, "rent_paid_eth": 1},
        ]

        daily = compute_daily_str_series(rows)
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0].l2_fees_eth_sum, 0.0)
        self.assertTrue(math.isnan(daily[0].str_value))

    def test_missingness_rule_row_omission(self) -> None:
        rows = [
            {"date_utc": "2024-01-04", "rollup_id": "a", "l2_fees_eth": 12, "rent_paid_eth": ""},
            {"date_utc": "2024-01-04", "rollup_id": "b", "l2_fees_eth": "6", "rent_paid_eth": "3"},
        ]

        daily = compute_daily_str_series(rows)
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0].included_rollup_days, 1)
        self.assertEqual(daily[0].skipped_rows, 1)
        self.assertAlmostEqual(daily[0].l2_fees_eth_sum, 6.0)
        self.assertAlmostEqual(daily[0].rent_paid_eth_sum, 3.0)
        self.assertAlmostEqual(daily[0].str_value, 0.5)

        contributions = compute_rollup_str_contributions(rows)
        self.assertEqual(len(contributions), 1)
        self.assertEqual(contributions[0].rollup_id, "b")

    def test_rollup_diagnostics_sum_to_daily_str(self) -> None:
        rows = [
            {"date_utc": "2024-01-05", "rollup_id": "a", "l2_fees_eth": 10, "rent_paid_eth": 2},
            {"date_utc": "2024-01-05", "rollup_id": "b", "l2_fees_eth": 30, "rent_paid_eth": 3},
        ]

        daily = compute_daily_str_series(rows)
        contributions = compute_rollup_str_contributions(rows)
        self.assertEqual(len(daily), 1)
        self.assertEqual(len(contributions), 2)

        total_contribution = sum(c.contribution_to_ecosystem_str for c in contributions)
        self.assertAlmostEqual(total_contribution, daily[0].str_value)

        self.assertAlmostEqual(contributions[0].rent_share_of_day, 0.4)
        self.assertAlmostEqual(contributions[1].fees_share_of_day, 0.75)


if __name__ == "__main__":
    unittest.main()
