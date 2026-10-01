import unittest
from datetime import date

try:
    from CateringPayroll.calendar_utils import (
        format_jalali_date,
        gregorian_date_from_jalali,
        jalali_date_from_gregorian,
        jalali_month_length,
        parse_jalali_date,
    )
except ModuleNotFoundError:
    from calendar_utils import (
        format_jalali_date,
        gregorian_date_from_jalali,
        jalali_date_from_gregorian,
        jalali_month_length,
        parse_jalali_date,
    )


class CalendarUtilsTests(unittest.TestCase):
    def test_converts_expected_current_date(self):
        self.assertEqual(jalali_date_from_gregorian(date(2026, 9, 29)), (1405, 7, 7))
        self.assertEqual(format_jalali_date(date(2026, 9, 29)), "1405/7/7")

    def test_jalali_to_gregorian_and_back(self):
        for jalali in ((1403, 1, 1), (1403, 12, 30), (1405, 7, 7), (1404, 12, 29)):
            with self.subTest(jalali=jalali):
                gregorian = gregorian_date_from_jalali(*jalali)
                self.assertEqual(jalali_date_from_gregorian(gregorian), jalali)

    def test_esfand_length_accounts_for_jalali_leap_years(self):
        self.assertEqual(jalali_month_length(1403, 12), 30)
        self.assertEqual(jalali_month_length(1404, 12), 29)

    def test_parses_english_or_persian_digits(self):
        self.assertEqual(parse_jalali_date("1405/7/7"), date(2026, 9, 29))
        self.assertEqual(parse_jalali_date("۱۴۰۵/۷/۷"), date(2026, 9, 29))

    def test_rejects_invalid_jalali_dates(self):
        for value in ("1404/12/30", "1405/13/1", "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_jalali_date(value)


if __name__ == "__main__":
    unittest.main()
