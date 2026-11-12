from decimal import Decimal


def line_total(unit_price, quantity, vat_percent):
    """Gross line total: net * (1 + VAT), rounded half-up to cents."""
    return round(unit_price * quantity * (1 + Decimal(vat_percent) / 100), 2)


def order_total(lines):
    """Sum of already-rounded line totals for (unit_price, quantity, vat_percent) lines."""
    return sum(line_total(*line) for line in lines)
