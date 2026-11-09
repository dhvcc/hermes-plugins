from decimal import Decimal


def parse_amount(text: str) -> Decimal:
    """Parse amounts written as "1,234.56" or "1.234,56" (European)."""
    cleaned = text.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)
