import tempfile
import sqlite3
import unittest
from pathlib import Path
from datetime import date

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

    def test_pay_day_defaults_to_17_and_can_be_changed(self):
        self.assertEqual(self.store.list_employees()[0]["pay_day"], 17)
        self.store.update_employee(self.employee_id, "علی رضایی", "پیک", 25_000_000, 23)
        self.assertEqual(self.store.list_employees()[0]["pay_day"], 23)
        with self.assertRaises(PayrollError):
            self.store.update_employee(self.employee_id, "علی رضایی", "پیک", 25_000_000, 32)

    def test_employee_start_date_is_saved_and_editable(self):
        self.store.update_employee(
            self.employee_id, "علی رضایی", "پیک", 25_000_000, 17, "2026-09-29"
        )
        self.assertEqual(self.store.list_employees()[0]["start_date"], "2026-09-29")
        self.store.update_employee(
            self.employee_id, "علی رضایی", "پیک", 25_000_000, 17, None
        )
        self.assertIsNone(self.store.list_employees()[0]["start_date"])
        with self.assertRaises(PayrollError):
            self.store.update_employee(
                self.employee_id, "علی رضایی", "پیک", 25_000_000, 17, "1405/7/7"
            )

    def test_salary_cannot_be_reduced_below_recorded_payments(self):
        self.store.add_payment(self.employee_id, "2026-09", 2_000_000, "2026-09-10")

        with self.assertRaises(PayrollError):
            self.store.update_employee(self.employee_id, "علی رضایی", "پیک", 1_000_000)

        self.assertEqual(self.store.list_employees()[0]["monthly_salary"], 25_000_000)

    def test_payment_can_be_deleted(self):
        payment_id = self.store.add_payment(self.employee_id, "2026-09", 2_000_000, "2026-09-10")
        self.store.delete_payment(payment_id)

        self.assertEqual(self.store.employee_totals(self.employee_id, "2026-09")["due"], 25_000_000)

    def test_payment_amount_date_and_note_can_be_corrected(self):
        payment_id = self.store.add_payment(
            self.employee_id, "2026-09", 2_000_000, "2026-09-10", "اشتباه"
        )
        self.store.update_payment(payment_id, 4_000_000, "2026-09-11", "اصلاح‌شده")

        payment = self.store.list_employee_payments(self.employee_id)[0]
        self.assertEqual(
            (payment["amount"], payment["paid_at"], payment["note"]),
            (4_000_000, "2026-09-11", "اصلاح‌شده"),
        )
        self.assertEqual(
            self.store.employee_totals(self.employee_id, "2026-09")["due"], 21_000_000
        )

    def test_payment_correction_cannot_exceed_remaining_salary(self):
        first_id = self.store.add_payment(
            self.employee_id, "2026-09", 10_000_000, "2026-09-10"
        )
        self.store.add_payment(self.employee_id, "2026-09", 10_000_000, "2026-09-11")

        with self.assertRaises(PayrollError):
            self.store.update_payment(first_id, 16_000_000, "2026-09-10")

        self.assertEqual(
            self.store.employee_totals(self.employee_id, "2026-09")["paid"], 20_000_000
        )

    def test_opening_legacy_database_adds_pay_day_and_migrates_months(self):
        database_path = Path(self.temp_directory.name) / "legacy.sqlite3"
        connection = sqlite3.connect(database_path)
        connection.executescript(
            """
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                monthly_salary INTEGER NOT NULL,
                archived_month TEXT
            );
            CREATE TABLE payments (
                id INTEGER PRIMARY KEY,
                employee_id INTEGER NOT NULL,
                payroll_month TEXT NOT NULL,
                amount INTEGER NOT NULL,
                paid_at TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO employees VALUES (1, 'علی رضایی', 'پیک', 25000000, '2026-09');
            INSERT INTO payments VALUES (1, 1, '2026-09', 2000000, '2026-09-17', '');
            """
        )
        connection.commit()
        connection.close()

        migrated = PayrollStore(database_path)
        try:
            employee = migrated.list_employees()[0]
            payment = migrated.list_employee_payments(1)[0]
            self.assertEqual(employee["pay_day"], 17)
            self.assertIsNone(employee["start_date"])
            self.assertEqual(employee["archived_month"], "1405-06")
            self.assertEqual(payment["payroll_month"], "1405-06")
            self.assertEqual(payment["amount"], 2_000_000)
            migrated.set_archived(1, None)
            migrated.add_payment(1, "2026-09", 1_000_000, "2026-09-18")
        finally:
            migrated.close()

        reopened = PayrollStore(database_path)
        try:
            months = {payment["payroll_month"] for payment in reopened.list_employee_payments(1)}
            self.assertEqual(months, {"1405-06", "2026-09"})
        finally:
            reopened.close()

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
