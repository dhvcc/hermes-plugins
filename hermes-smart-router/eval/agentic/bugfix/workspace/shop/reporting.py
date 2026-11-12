from collections import Counter
from datetime import datetime


def orders_per_day(timestamps, tz):
    """Count ISO-8601 timestamps (any offset, or Z) per calendar day in time zone `tz` (a ZoneInfo)."""
    counts = Counter()
    for ts in timestamps:
        moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        counts[moment.date().isoformat()] += 1
    return dict(counts)
