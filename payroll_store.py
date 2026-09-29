"""Local SQLite storage and payroll rules for the standalone catering app."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any


class PayrollError(ValueError):
    """Raised when a payroll operation would create invalid records."""


class PayrollStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                monthly_salary INTEGER NOT NULL CHECK (monthly_salary > 0),
                archived_month TEXT
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL REFERENCES employees(id),
                payroll_month TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                paid_at TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS payments_by_month
                ON payments(payroll_month, paid_at);
            CREATE INDEX IF NOT EXISTS payments_by_employee
                ON payments(employee_id, payroll_month);
            """
        )
        self.connection.commit()

    @staticmethod
    def _validate_month(month: str) -> str:
        if (
            not isinstance(month, str)
            or len(month) != 7
            or month[4] != "-"
            or not month[:4].isdigit()
            or not month[5:].isdigit()
            or not 1 <= int(month[5:]) <= 12
        ):
            raise PayrollError("ماه باید با قالب سال-ماه وارد شود.")
        return month

    @staticmethod
    def _validate_amount(amount: int, label: str) -> int:
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise PayrollError(f"{label} باید یک عدد صحیح بزرگ‌تر از صفر باشد.")
        return amount

    @staticmethod
    def _validate_employee(name: str, role: str, salary: int) -> tuple[str, str, int]:
        clean_name = name.strip() if isinstance(name, str) else ""
        clean_role = role.strip() if isinstance(role, str) else ""
        if not clean_name:
            raise PayrollError("نام کارمند را وارد کنید.")
        if not clean_role:
            raise PayrollError("سمت کارمند را وارد کنید.")
        return clean_name, clean_role, PayrollStore._validate_amount(salary, "حقوق ماهانه")

    def add_employee(self, name: str, role: str, monthly_salary: int) -> int:
        clean_name, clean_role, salary = self._validate_employee(name, role, monthly_salary)
        cursor = self.connection.execute(
            "INSERT INTO employees(name, role, monthly_salary) VALUES (?, ?, ?)",
            (clean_name, clean_role, salary),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def update_employee(self, employee_id: int, name: str, role: str, monthly_salary: int) -> None:
        clean_name, clean_role, salary = self._validate_employee(name, role, monthly_salary)
        paid_months = self.connection.execute(
            """
            SELECT payroll_month, SUM(amount) AS total_paid
            FROM payments
            WHERE employee_id = ?
            GROUP BY payroll_month
            HAVING SUM(amount) > ?
            """,
            (employee_id, salary),
        ).fetchall()
        if paid_months:
            months = "، ".join(row["payroll_month"] for row in paid_months)
            raise PayrollError(
                f"حقوق جدید از پرداخت‌های ثبت‌شده در این ماه‌ها کمتر است: {months}."
            )
        cursor = self.connection.execute(
            "UPDATE employees SET name = ?, role = ?, monthly_salary = ? WHERE id = ?",
            (clean_name, clean_role, salary, employee_id),
        )
        if cursor.rowcount != 1:
            raise PayrollError("کارمند انتخاب‌شده پیدا نشد.")
        self.connection.commit()

    def set_archived(self, employee_id: int, archived_month: str | None) -> None:
        if archived_month is not None:
            self._validate_month(archived_month)
        cursor = self.connection.execute(
            "UPDATE employees SET archived_month = ? WHERE id = ?",
            (archived_month, employee_id),
        )
        if cursor.rowcount != 1:
            raise PayrollError("کارمند انتخاب‌شده پیدا نشد.")
        self.connection.commit()

    def list_employees(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id, name, role, monthly_salary, archived_month "
            "FROM employees ORDER BY archived_month IS NOT NULL, name COLLATE NOCASE"
        ).fetchall()
        return [dict(row) for row in rows]

    def employee_totals(self, employee_id: int, month: str) -> dict[str, int]:
        month = self._validate_month(month)
        row = self.connection.execute(
            """
            SELECT e.monthly_salary, e.archived_month,
                   COALESCE(SUM(p.amount), 0) AS paid
            FROM employees e
            LEFT JOIN payments p
              ON p.employee_id = e.id AND p.payroll_month = ?
            WHERE e.id = ?
            GROUP BY e.id
            """,
            (month, employee_id),
        ).fetchone()
        if row is None:
            raise PayrollError("کارمند انتخاب‌شده پیدا نشد.")
        salary = row["monthly_salary"] if not row["archived_month"] or month <= row["archived_month"] else 0
        paid = row["paid"]
        return {"salary": salary, "paid": paid, "due": max(0, salary - paid)}

    def month_summary(self, month: str) -> dict[str, int]:
        month = self._validate_month(month)
        employees = self.list_employees()
        salaries = paid = active_count = 0
        for employee in employees:
            totals = self.employee_totals(employee["id"], month)
            salaries += totals["salary"]
            paid += totals["paid"]
            if employee["archived_month"] is None:
                active_count += 1
        return {"active_count": active_count, "salary": salaries, "paid": paid, "due": max(0, salaries - paid)}

    def add_payment(
        self,
        employee_id: int,
        month: str,
        amount: int,
        paid_at: str,
        note: str = "",
    ) -> int:
        month = self._validate_month(month)
        amount = self._validate_amount(amount, "مبلغ پرداخت")
        if not isinstance(paid_at, str):
            raise PayrollError("تاریخ پرداخت معتبر نیست.")
        try:
            if date.fromisoformat(paid_at).isoformat() != paid_at:
                raise ValueError
        except ValueError as error:
            raise PayrollError("تاریخ پرداخت معتبر نیست.") from error
        if not isinstance(note, str):
            raise PayrollError("یادداشت پرداخت معتبر نیست.")

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            totals = self.employee_totals(employee_id, month)
            if amount > totals["due"]:
                raise PayrollError(
                    f"مبلغ پرداخت از مانده بیشتر است. مانده‌ی قابل پرداخت: {totals['due']:,} تومان."
                )
            cursor = self.connection.execute(
                "INSERT INTO payments(employee_id, payroll_month, amount, paid_at, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (employee_id, month, amount, paid_at, note.strip()),
            )
            self.connection.commit()
            return int(cursor.lastrowid)
        except Exception:
            self.connection.rollback()
            raise

    def delete_payment(self, payment_id: int) -> None:
        cursor = self.connection.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
        if cursor.rowcount != 1:
            raise PayrollError("پرداخت انتخاب‌شده پیدا نشد.")
        self.connection.commit()

    def list_payments(self, month: str) -> list[dict[str, Any]]:
        month = self._validate_month(month)
        rows = self.connection.execute(
            """
            SELECT p.id, p.employee_id, e.name AS employee_name, e.role,
                   p.payroll_month, p.amount, p.paid_at, p.note
            FROM payments p
            JOIN employees e ON e.id = p.employee_id
            WHERE p.payroll_month = ?
            ORDER BY p.paid_at DESC, p.id DESC
            """,
            (month,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.connection.close()
