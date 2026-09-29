import tempfile
import unittest
from pathlib import Path

try:
    from CateringPayroll.app import format_grouped_input, local_digits, money, parse_local_integer
    from CateringPayroll.payroll_store import PayrollError, PayrollStore
except ModuleNotFoundError:
    from app import format_grouped_input, local_digits, money, parse_local_integer
    from payroll_store import PayrollError, PayrollStore


class PayrollStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.store = PayrollStore(Path(self.temp_directory.name) / "payroll.sqlite3")
        self.employee_id = self.store.add_employee("علی رضایی", "پیک", 25_000_000)

    def tearDown(self):
        self.store.close()
        self.temp_directory.cleanup()

    def test_partial_payments_reduce_monthly_balance(self):
        self.store.add_payment(self.employee_id, "2026-09", 2_000_000, "2026-09-10", "علی‌الحساب")
        self.store.add_payment(self.employee_id, "2026-09", 3_000_000, "2026-09-20")

        self.assertEqual(
            self.store.employee_totals(self.employee_id, "2026-09"),
            {"salary": 25_000_000, "paid": 5_000_000, "due": 20_000_000},
        )
        self.assertEqual(
            self.store.month_summary("2026-09"),
            {"active_count": 1, "salary": 25_000_000, "paid": 5_000_000, "due": 20_000_000},
        )

    def test_overpayment_is_rejected_without_saving(self):
        with self.assertRaises(PayrollError):
            self.store.add_payment(self.employee_id, "2026-09", 25_000_001, "2026-09-10")

        self.assertEqual(self.store.list_payments("2026-09"), [])
        self.assertEqual(self.store.employee_totals(self.employee_id, "2026-09")["due"], 25_000_000)

    def test_payments_are_separated_by_payroll_month(self):
        self.store.add_payment(self.employee_id, "2026-08", 2_000_000, "2026-08-10")

        self.assertEqual(self.store.employee_totals(self.employee_id, "2026-09")["paid"], 0)
        self.assertEqual(self.store.month_summary("2026-08")["due"], 23_000_000)

    def test_archiving_keeps_salary_until_the_selected_month(self):
        self.store.set_archived(self.employee_id, "2026-09")

        self.assertEqual(self.store.employee_totals(self.employee_id, "2026-09")["salary"], 25_000_000)
        self.assertEqual(self.store.employee_totals(self.employee_id, "2026-10")["salary"], 0)
        self.assertEqual(self.store.month_summary("2026-10")["active_count"], 0)

    def test_invalid_salary_is_rejected(self):
        with self.assertRaises(PayrollError):
            self.store.add_employee("مریم", "آشپز", 0)

    def test_salary_cannot_be_reduced_below_recorded_payments(self):
        self.store.add_payment(self.employee_id, "2026-09", 2_000_000, "2026-09-10")

        with self.assertRaises(PayrollError):
            self.store.update_employee(self.employee_id, "علی رضایی", "پیک", 1_000_000)

        self.assertEqual(self.store.list_employees()[0]["monthly_salary"], 25_000_000)

    def test_payment_can_be_deleted(self):
        payment_id = self.store.add_payment(self.employee_id, "2026-09", 2_000_000, "2026-09-10")
        self.store.delete_payment(payment_id)

        self.assertEqual(self.store.employee_totals(self.employee_id, "2026-09")["due"], 25_000_000)

    def test_amount_input_accepts_persian_digits_and_group_separators(self):
        self.assertEqual(parse_local_integer("۲۵٬۰۰۰٬۰۰۰"), 25_000_000)
        self.assertEqual(parse_local_integer("2,000,000"), 2_000_000)

    def test_amount_input_displays_english_digits_with_live_grouping(self):
        self.assertEqual(format_grouped_input("250000000"), "250,000,000")
        self.assertEqual(format_grouped_input("۲۵۰۰۰۰۰۰۰"), "250,000,000")
        self.assertEqual(format_grouped_input("250,000,000"), "250,000,000")
        self.assertEqual(format_grouped_input(""), "")

    def test_displayed_amounts_and_dates_use_english_digits(self):
        self.assertEqual(money(250_000_000), "250,000,000 تومان")
        self.assertEqual(local_digits("۱۴۰۵/۰۷/۰۷"), "1405/07/07")


if __name__ == "__main__":
    unittest.main()
