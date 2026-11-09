"""Count events per local day. Usage: python3 report.py events.jsonl

Prints one line per day, oldest first: "YYYY-MM-DD <count>".
Days are calendar days in Europe/Berlin. Lines that are not valid events are skipped.
"""
import json
import sys
from collections import Counter
from datetime import datetime


def main(path):
    counts = Counter()
    for line in open(path):
        event = json.loads(line)
        ts = datetime.strptime(event["ts"], "%Y-%m-%dT%H:%M:%S%z")
        counts[ts.date().isoformat()] += 1
    for day in sorted(counts):
        print(day, counts[day])


if __name__ == "__main__":
    main(sys.argv[1])
