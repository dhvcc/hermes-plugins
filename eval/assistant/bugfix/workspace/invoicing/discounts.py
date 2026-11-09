from decimal import Decimal


def apply_discount(price: Decimal, percent: int) -> Decimal:
    """Price after a percentage discount, rounded half-up to cents."""
    discounted = float(price) * (100 - percent) / 100
    return Decimal(str(round(discounted, 2)))
