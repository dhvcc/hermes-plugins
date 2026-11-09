class Cart:
    def __init__(self, items=[]):
        self.items = items

    def add(self, sku, quantity=1):
        """Add `quantity` of `sku`; adding an existing sku increases its quantity."""
        self.items.append((sku, quantity))

    def quantity(self, sku):
        return sum(q for s, q in self.items if s == sku)

    def distinct(self):
        """Number of distinct skus in the cart."""
        return len(self.items)
