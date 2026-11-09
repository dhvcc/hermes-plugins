from datetime import date


def add_months(start: date, months: int) -> date:
    """Same day of month `months` later, clamped to the last day of a shorter month."""
    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    return start.replace(year=year, month=month)
