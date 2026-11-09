import unittest
from decimal import Decimal
from zoneinfo import ZoneInfo

from shop.cart import Cart
from shop.pagination import page, page_count
from shop.pricing import line_total, order_total
from shop.reporting import orders_per_day


class Hidden(unittest.TestCase):
    def test_pages(self):
        items = list(range(10))
        self.assertEqual(page(items, 1, 4), [0, 1, 2, 3])
        self.assertEqual(page(items, 3, 4), [8, 9])
        self.assertEqual(page(items, 4, 4), [])

    def test_page_count(self):
        self.assertEqual(page_count(0, 4), 0)
        self.assertEqual(page_count(8, 4), 2)
        self.assertEqual(page_count(9, 4), 3)

    def test_half_up(self):
        self.assertEqual(line_total(Decimal("0.125"), 1, 0), Decimal("0.13"))
        self.assertEqual(line_total(Decimal("2.50"), 1, 7), Decimal("2.68"))

    def test_order_total_sums_rounded_lines(self):
        lines = [(Decimal("0.333"), 1, 0), (Decimal("0.333"), 1, 0), (Decimal("0.333"), 1, 0)]
        self.assertEqual(order_total(lines), Decimal("0.99"))

    def test_days_in_zone(self):
        berlin = ZoneInfo("Europe/Berlin")
        stamps = ["2026-10-24T22:30:00Z", "2026-10-25T00:30:00+02:00", "2026-10-25T23:30:00Z"]
        self.assertEqual(orders_per_day(stamps, berlin), {"2026-10-25": 2, "2026-10-26": 1})

    def test_carts_are_independent(self):
        first, second = Cart(), Cart()
        first.add("a")
        self.assertEqual(second.quantity("a"), 0)

    def test_distinct(self):
        cart = Cart()
        cart.add("a")
        cart.add("a")
        cart.add("b")
        self.assertEqual(cart.distinct(), 2)


if __name__ == "__main__":
    unittest.main()
