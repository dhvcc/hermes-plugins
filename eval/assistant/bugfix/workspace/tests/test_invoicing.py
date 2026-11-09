import unittest
from datetime import date
from decimal import Decimal

from invoicing.dates import add_months
from invoicing.discounts import apply_discount
from invoicing.money import parse_amount


class MoneyTests(unittest.TestCase):
    def test_us_format(self):
        self.assertEqual(parse_amount("1,234.56"), Decimal("1234.56"))

    def test_european_format(self):
        self.assertEqual(parse_amount("1.234,56"), Decimal("1234.56"))

    def test_plain(self):
        self.assertEqual(parse_amount(" 99,5 "), Decimal("99.5"))


class DateTests(unittest.TestCase):
    def test_regular(self):
        self.assertEqual(add_months(date(2026, 3, 15), 2), date(2026, 5, 15))

    def test_month_end_is_clamped(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_leap_year(self):
        self.assertEqual(add_months(date(2027, 11, 30), 3), date(2028, 2, 29))


class DiscountTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(apply_discount(Decimal("100.00"), 10), Decimal("90.00"))

    def test_half_up(self):
        self.assertEqual(apply_discount(Decimal("0.70"), 50), Decimal("0.35"))
        self.assertEqual(apply_discount(Decimal("2.50"), 49), Decimal("1.28"))


if __name__ == "__main__":
    unittest.main()
