import unittest
from decimal import Decimal

from shop.cart import Cart
from shop.pagination import page
from shop.pricing import line_total


class Visible(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(page(list(range(10)), 1, 4), [0, 1, 2, 3])

    def test_line_total(self):
        self.assertEqual(line_total(Decimal("10.00"), 3, 19), Decimal("35.70"))

    def test_cart_quantity(self):
        cart = Cart()
        cart.add("a", 2)
        cart.add("a")
        self.assertEqual(cart.quantity("a"), 3)


if __name__ == "__main__":
    unittest.main()
