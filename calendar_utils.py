"""Conversions between Gregorian dates and the Jalali (Persian) calendar."""

from __future__ import annotations

from datetime import date


JALALI_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
JALALI_BREAKS = (
    -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181,
    1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394,
    2456, 3178,
)


def _jalali_calendar(year: int) -> tuple[int, int, int]:
    if not JALALI_BREAKS[0] <= year < JALALI_BREAKS[-1]:
        raise ValueError("سال جلالی خارج از بازه‌ی پشتیبانی است.")
    gregorian_year = year + 621
    leap_jalali = -14
    previous_break = JALALI_BREAKS[0]
    jump = 0
    for current_break in JALALI_BREAKS[1:]:
        jump = current_break - previous_break
        if year < current_break:
            break
        leap_jalali += (jump // 33) * 8 + (jump % 33) // 4
        previous_break = current_break
    offset = year - previous_break
    leap_jalali += (offset // 33) * 8 + ((offset % 33) + 3) // 4
    if jump % 33 == 4 and jump - offset == 4:
        leap_jalali += 1
    leap_gregorian = gregorian_year // 4 - ((gregorian_year // 100 + 1) * 3 // 4) - 150
    march = 20 + leap_jalali - leap_gregorian
    if jump - offset < 6:
        offset = offset - jump + ((jump + 4) // 33) * 33
    leap = (((offset + 1) % 33) - 1) % 4
    if leap == -1:
        leap = 4
    return gregorian_year, march, leap


def _gregorian_to_jdn(year: int, month: int, day: int) -> int:
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def _jdn_to_gregorian(jdn: int) -> tuple[int, int, int]:
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def _jalali_to_jdn(year: int, month: int, day: int) -> int:
    gregorian_year, march, _leap = _jalali_calendar(year)
    return (
        _gregorian_to_jdn(gregorian_year, 3, march)
        + (month - 1) * 31
        - (month // 7) * (month - 7)
        + day - 1
    )


def jalali_date_from_gregorian(value: date) -> tuple[int, int, int]:
    jalali_year = value.year - 621
    gregorian_year, march, leap = _jalali_calendar(jalali_year)
    first_day = _gregorian_to_jdn(gregorian_year, 3, march)
    offset = _gregorian_to_jdn(value.year, value.month, value.day) - first_day
    if offset >= 0:
        if offset <= 185:
            return jalali_year, 1 + offset // 31, offset % 31 + 1
        offset -= 186
    else:
        jalali_year -= 1
        offset += 179
        if leap == 1:
            offset += 1
    return jalali_year, 7 + offset // 30, offset % 30 + 1


def jalali_month_length(year: int, month: int) -> int:
    if not 1 <= month <= 12:
        raise ValueError("ماه جلالی باید بین 1 و 12 باشد.")
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if _jalali_calendar(year)[2] == 0 else 29


def gregorian_date_from_jalali(year: int, month: int, day: int) -> date:
    if not 1 <= month <= 12 or not 1 <= day <= jalali_month_length(year, month):
        raise ValueError("تاریخ جلالی معتبر نیست.")
    gregorian_year, gregorian_month, gregorian_day = _jdn_to_gregorian(
        _jalali_to_jdn(year, month, day)
    )
    return date(gregorian_year, gregorian_month, gregorian_day)


def parse_jalali_date(value: str) -> date:
    parts = value.strip().replace("-", "/").split("/")
    if len(parts) != 3 or not all(part.isdecimal() for part in parts):
        raise ValueError("تاریخ را با قالب سال/ماه/روز شمسی وارد کنید.")
    try:
        year, month, day = (int(part) for part in parts)
        return gregorian_date_from_jalali(year, month, day)
    except (ValueError, OverflowError) as error:
        raise ValueError("تاریخ شمسی واردشده معتبر نیست.") from error


def format_jalali_date(value: date) -> str:
    year, month, day = jalali_date_from_gregorian(value)
    return f"{year}/{month}/{day}"


def jalali_month_from_gregorian(value: date) -> tuple[int, int]:
    year, month, _day = jalali_date_from_gregorian(value)
    return year, month


def shift_jalali_month(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute_month = year * 12 + month - 1 + offset
    return absolute_month // 12, absolute_month % 12 + 1
