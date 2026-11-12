"""Generate the agentic eval scenarios and their expected results.

    python3 eval/agentic/build.py

Every scenario gets ``<name>/workspace`` (copied for the agent) and ``<name>/expected.json`` (grader only).
Data is synthetic and seeded, so it cannot appear in any training set, and the expected results are computed
here by reference code from the same data the agent sees.
"""
from __future__ import annotations

import csv
import json
import random
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def fresh(name: str) -> Path:
    folder = ROOT / name
    shutil.rmtree(folder, ignore_errors=True)
    (folder / "workspace").mkdir(parents=True)
    return folder / "workspace"


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def save_expected(name: str, expected: dict) -> None:
    (ROOT / name / "expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False, default=str))


# 1. Expense audit -------------------------------------------------------------------------------

EXPENSE_POLICY = """# Expense policy

Apply these rules to every receipt, in order of receipt id.

1. Convert to EUR with the rate for the receipt's month in `fx.csv` (EUR per unit). Round each approved
   amount to cents at the end.
2. Duplicates: a receipt with the same employee, date, vendor and amount as an earlier receipt (lower id) is a
   duplicate and gets 0.
3. Alcohol is never reimbursed.
4. Meals: at most 45.00 EUR per employee per calendar day in total. Fill the daily allowance in receipt id
   order; the receipt that crosses the limit is reimbursed partially, later ones that day get 0.
5. Taxis on Saturday or Sunday are reimbursed only if the receipt note mentions the airport.
6. Hotels: at most 160.00 EUR per night; the receipt states the number of nights.
7. Software is reimbursed only if the receipt carries an approval reference (`APR-...`).
8. Everything else is reimbursed in full.

Status per receipt: `approved` (full amount), `partial` (some), `rejected` (0, rules 3, 5, 6 or 7, or a meal
over the daily limit), `duplicate` (rule 2).
"""


def build_expenses() -> None:
    rng = random.Random(101)
    ws = fresh("expense_audit")
    people = ["Mara Lind", "Jonas Weber", "Priya Nair", "Tom Okafor"]
    vendors = {"meal": ["Cafe Nord", "Trattoria Sole", "Ramen Ichi", "Deli 24"], "taxi": ["CityCab", "FreeNow"],
               "hotel": ["Hotel Arcadia", "Park Inn"], "software": ["Figma", "JetBrains", "Notion"],
               "alcohol": ["Bar Lumen"], "train": ["DB Fernverkehr"], "office": ["Staples"]}
    fx = {("2026-09", "EUR"): 1, ("2026-10", "EUR"): 1, ("2026-09", "USD"): 0.92, ("2026-10", "USD"): 0.94,
          ("2026-09", "GBP"): 1.17, ("2026-10", "GBP"): 1.15}
    write_csv(ws / "fx.csv", ["month", "currency", "eur_per_unit"], [[m, c, r] for (m, c), r in sorted(fx.items())])
    (ws / "policy.md").write_text(EXPENSE_POLICY)
    receipts = []
    for i in range(1, 37):
        category = rng.choices(list(vendors), [10, 5, 3, 3, 2, 2, 2])[0]
        day = date(2026, 9, 1) + timedelta(days=rng.randint(0, 45))
        receipt = {"id": f"R{i:03d}", "employee": rng.choice(people), "date": day, "category": category,
                   "vendor": rng.choice(vendors[category]), "currency": rng.choice(["EUR", "EUR", "USD", "GBP"]),
                   "note": "", "nights": None, "approval": None}
        base = {"meal": (12, 38), "taxi": (14, 60), "hotel": (120, 230), "software": (15, 90), "alcohol": (20, 60),
                "train": (40, 140), "office": (8, 50)}[category]
        receipt["amount"] = money(rng.uniform(*base))
        if category == "hotel":
            receipt["nights"] = rng.randint(1, 3)
            receipt["amount"] = money(receipt["amount"] * receipt["nights"])
        if category == "taxi":
            receipt["note"] = rng.choice(["to client office", "to airport", "from the airport", "late meeting"])
        if category == "software" and rng.random() < 0.5:
            receipt["approval"] = f"APR-{rng.randint(1000, 9999)}"
        receipts.append(receipt)
    for source, target in ((3, 17), (8, 29), (21, 34)):
        copy = dict(receipts[source], id=f"R{target + 1:03d}")
        receipts[target] = copy
    same_day = receipts[5]
    for j in (6, 7):
        receipts[j].update(employee=same_day["employee"], date=same_day["date"], category="meal",
                           vendor=rng.choice(vendors["meal"]), currency="EUR", note="", nights=None, approval=None,
                           amount=money(rng.uniform(18, 30)))
    receipts[5].update(category="meal", vendor="Cafe Nord", currency="EUR", amount=money(22.4), note="", nights=None)

    layouts = [
        lambda r, amt: f"{r['vendor']}\n{r['date']:%d.%m.%Y}\nGesamt: {amt.replace('.', ',')} {r['currency']}\n",
        lambda r, amt: f"RECEIPT - {r['vendor'].upper()}\nDate: {r['date']:%Y-%m-%d}\nAmount due: {r['currency']} {amt}\n",
        lambda r, amt: json.dumps({"merchant": r["vendor"], "day": r["date"].isoformat(), "total": float(amt),
                                   "ccy": r["currency"]}, indent=1) + "\n",
    ]
    for r in receipts:
        amount = f"{r['amount']:.2f}"
        body = rng.choice(layouts)(r, amount)
        header = f"Employee: {r['employee']}\nCategory: {r['category']}\n"
        extra = "".join(f"{k}: {v}\n" for k, v in (("Nights", r["nights"]), ("Note", r["note"] or None),
                                                     ("Approval", r["approval"])) if v)
        (ws / "receipts").mkdir(exist_ok=True)
        (ws / "receipts" / f"{r['id']}.txt").write_text(header + extra + "---\n" + body)

    seen, meals, result = set(), defaultdict(Decimal), {}
    for r in sorted(receipts, key=lambda x: x["id"]):
        eur = Decimal(str(fx[(r["date"].strftime("%Y-%m"), r["currency"])])) * r["amount"]
        key = (r["employee"], r["date"], r["vendor"], r["amount"])
        approved, status = eur, None
        if key in seen:
            approved, status = Decimal(0), "duplicate"
        seen.add(key)
        if status is None:
            if r["category"] == "alcohol":
                approved = Decimal(0)
            elif r["category"] == "meal":
                left = Decimal("45.00") - meals[(r["employee"], r["date"])]
                approved = max(Decimal(0), min(eur, left))
                meals[(r["employee"], r["date"])] += approved
            elif r["category"] == "taxi" and r["date"].weekday() >= 5 and "airport" not in r["note"]:
                approved = Decimal(0)
            elif r["category"] == "hotel":
                approved = min(eur, Decimal(160) * r["nights"])
            elif r["category"] == "software" and not r["approval"]:
                approved = Decimal(0)
            approved = money(approved)
            status = "approved" if approved == money(eur) else "partial" if approved > 0 else "rejected"
        result[r["id"]] = {"approved_eur": str(money(approved)), "status": status, "employee": r["employee"],
                           "lost": str(money(eur) - money(approved)) if status != "duplicate" else "0.00"}
    lost = defaultdict(Decimal)
    for row in result.values():
        lost[row["employee"]] += Decimal(row["lost"])
    worst = max(lost, key=lost.get)
    save_expected("expense_audit", {
        "rows": {k: {"approved_eur": v["approved_eur"], "status": v["status"]} for k, v in result.items()},
        "total": str(sum(Decimal(v["approved_eur"]) for v in result.values())),
        "worst_employee": worst, "worst_lost": str(lost[worst]),
    })


# 2. Bank reconciliation ---------------------------------------------------------------------------

RECON_RULES = """# Reconciliation rules

- Match bank transactions to invoices by the invoice number in the reference. References are typed by hand:
  expect lower case, missing dashes, `O` instead of `0`, and several invoice numbers in one payment.
- A payment that names several invoices pays them in the order listed, each in full until the money runs out.
- A payment without a usable reference belongs to an invoice of the same client with exactly that open amount.
- Banks may deduct a transfer fee: if the open amount of an invoice is 2.00 EUR or less after a payment, the
  invoice counts as paid.
- Ignore transactions that are not client payments (rent, salaries, card fees, refunds we sent).

Status: `paid`, `partial` (something received, more than 2.00 EUR still open) or `unpaid`.
"""


def build_reconciliation() -> None:
    rng = random.Random(202)
    ws = fresh("reconciliation")
    clients = ["Acme GmbH", "Globex Ltd", "Initech AG", "Umbrella BV", "Hooli Inc", "Vandelay SA", "Stark KG"]
    invoices = []
    for n in range(1, 26):
        invoices.append({"id": f"INV-{1040 + n}", "client": rng.choice(clients),
                         "amount": money(rng.choice([450, 780, 1200, 1890, 2400, 3150, 5600]) + rng.randint(0, 99)),
                         "issued": date(2026, 8, 1) + timedelta(days=rng.randint(0, 60))})
    write_csv(ws / "invoices.csv", ["invoice_id", "client", "amount_eur", "issued"],
              [[i["id"], i["client"], f"{i['amount']:.2f}", i["issued"]] for i in invoices])
    (ws / "rules.md").write_text(RECON_RULES)
    tx, received = [], defaultdict(Decimal)

    def mangle(inv_id: str) -> str:
        num = inv_id.split("-")[1]
        return rng.choice([inv_id, inv_id.lower(), f"INV{num}", f"inv {num}", inv_id.replace("0", "O"), f"Rechnung {num}"])

    plan = list(invoices)
    rng.shuffle(plan)
    for k, inv in enumerate(plan):
        day = inv["issued"] + timedelta(days=rng.randint(10, 40))
        kind = k % 7
        if kind in (0, 1):
            tx.append([day, f"{inv['amount']:.2f}", inv["client"], f"Payment {mangle(inv['id'])}"])
            received[inv["id"]] += inv["amount"]
        elif kind == 2:
            net = inv["amount"] - Decimal("1.50")
            tx.append([day, f"{net:.2f}", inv["client"], mangle(inv["id"])])
            received[inv["id"]] += net
        elif kind == 3:
            part = money(inv["amount"] * Decimal("0.4"))
            tx.append([day, f"{part:.2f}", inv["client"], f"Teilzahlung {mangle(inv['id'])}"])
            received[inv["id"]] += part
        elif kind == 4:
            tx.append([day, f"{inv['amount']:.2f}", inv["client"], "Thanks for the great work"])
            received[inv["id"]] += inv["amount"]
        elif kind == 5:
            pass
        else:
            others = [o for o in plan[:k] if o["client"] == inv["client"] and not received[o["id"]]]
            if others:
                other = others[0]
                total = inv["amount"] + other["amount"] - Decimal("1.00")
                tx.append([day, f"{total:.2f}", inv["client"], f"{mangle(inv['id'])} + {mangle(other['id'])}"])
                received[inv["id"]] += inv["amount"]
                received[other["id"]] += other["amount"] - Decimal("1.00")
            else:
                short = inv["amount"] - Decimal("35.00")
                tx.append([day, f"{short:.2f}", inv["client"], mangle(inv["id"])])
                received[inv["id"]] += short
    noise = [[date(2026, 10, 1), "-2400.00", "Landlord Immobilien", "Rent October"],
             [date(2026, 10, 28), "-8120.55", "Payroll", "Salaries October"],
             [date(2026, 10, 3), "-4.90", "Bank", "Card fees"],
             [date(2026, 9, 19), "-300.00", "Acme GmbH", "Refund credit note CN-7"]]
    rows = sorted(tx + noise, key=lambda r: r[0])
    write_csv(ws / "bank.csv", ["date", "amount_eur", "counterparty", "reference"], rows)
    expected = {}
    for inv in invoices:
        got = money(received[inv["id"]])
        status = "paid" if inv["amount"] - got <= Decimal("2.00") else "partial" if got > 0 else "unpaid"
        expected[inv["id"]] = {"status": status, "received_eur": str(got)}
    outstanding = defaultdict(Decimal)
    for inv in invoices:
        if expected[inv["id"]]["status"] != "paid":
            outstanding[inv["client"]] += inv["amount"] - Decimal(expected[inv["id"]]["received_eur"])
    top = sorted(outstanding.items(), key=lambda kv: -kv[1])[:3]
    save_expected("reconciliation", {"rows": expected, "top_debtors": [[c, str(a)] for c, a in top]})


# 3. Incident investigation ------------------------------------------------------------------------

def build_incident() -> None:
    rng = random.Random(303)
    ws = fresh("incident")
    start = datetime(2026, 11, 5, 6, 0, tzinfo=timezone.utc)
    deploy_at = start + timedelta(hours=13, minutes=rng.randint(0, 50))
    endpoints = ["/search", "/checkout", "/cart", "/login", "/products"]
    lines, first_error, after_total, after_fail, n = [], None, 0, 0, 0
    t = start
    while t < start + timedelta(hours=26):
        t += timedelta(seconds=rng.randint(10, 40))
        n += 1
        endpoint = rng.choices(endpoints, [5, 2, 3, 2, 6])[0]
        version = "2.4.1" if t >= deploy_at else "2.4.0"
        status, level, msg, latency = 200, "INFO", "ok", rng.randint(20, 250)
        if endpoint == "/search" and rng.random() < 0.04:
            status, level, msg = 500, "ERROR", "ElasticTimeout: search cluster busy"
        if endpoint == "/checkout" and version == "2.4.1":
            after_total += 1
            if rng.random() < 0.31:
                status, level, msg, latency = 502, "ERROR", "TimeoutError: payment-gateway did not respond", 30000
                after_fail += 1
                if first_error is None:
                    first_error = f"req-{n:06d}"
        lines.append(json.dumps({"ts": t.isoformat().replace("+00:00", "Z"), "level": level, "service": "shop-api",
                                 "endpoint": endpoint, "status": status, "latency_ms": latency, "version": version,
                                 "request_id": f"req-{n:06d}", "msg": msg}))
    lines.insert(next(i for i, line in enumerate(lines) if '"2.4.1"' in line),
                 json.dumps({"ts": deploy_at.isoformat().replace("+00:00", "Z"), "level": "INFO", "service": "deployer",
                             "msg": "rolled out shop-api 2.4.1"}))
    (ws / "logs").mkdir()
    half = len(lines) // 2
    (ws / "logs" / "app-1.jsonl").write_text("\n".join(lines[:half]) + "\n")
    (ws / "logs" / "app-2.jsonl").write_text("\n".join(lines[half:]) + "\n")
    save_expected("incident", {"bad_version": "2.4.1", "affected_endpoint": "/checkout",
                               "first_error_request_id": first_error,
                               "error_rate_after_pct": round(100 * after_fail / after_total, 1),
                               "root_cause_contains": "payment-gateway"})


# 4. Bug fixing with hidden tests ------------------------------------------------------------------

SHOP_FILES = {
    "shop/__init__.py": "",
    "shop/pagination.py": '''def page(items, number, size):
    """Items on 1-based page `number` of size `size`; an empty list past the last page."""
    start = number * size
    return items[start:start + size]


def page_count(total, size):
    """Number of pages needed for `total` items; 0 items need 0 pages."""
    return total // size
''',
    "shop/pricing.py": '''from decimal import Decimal


def line_total(unit_price, quantity, vat_percent):
    """Gross line total: net * (1 + VAT), rounded half-up to cents."""
    return round(unit_price * quantity * (1 + Decimal(vat_percent) / 100), 2)


def order_total(lines):
    """Sum of already-rounded line totals for (unit_price, quantity, vat_percent) lines."""
    return sum(line_total(*line) for line in lines)
''',
    "shop/reporting.py": '''from collections import Counter
from datetime import datetime


def orders_per_day(timestamps, tz):
    """Count ISO-8601 timestamps (any offset, or Z) per calendar day in time zone `tz` (a ZoneInfo)."""
    counts = Counter()
    for ts in timestamps:
        moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        counts[moment.date().isoformat()] += 1
    return dict(counts)
''',
    "shop/cart.py": '''class Cart:
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
''',
    "tests/__init__.py": "",
    "tests/test_visible.py": '''import unittest
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
''',
}

HIDDEN_TESTS = '''import unittest
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
'''


def build_bugfix() -> None:
    ws = fresh("bugfix")
    for name, text in SHOP_FILES.items():
        (ws / name).parent.mkdir(parents=True, exist_ok=True)
        (ws / name).write_text(text)
    hidden = ROOT / "bugfix" / "hidden"
    hidden.mkdir()
    (hidden / "test_hidden.py").write_text(HIDDEN_TESTS)
    save_expected("bugfix", {"hidden_tests": 7})


# 5. Meeting scheduling ------------------------------------------------------------------------------

def build_scheduling() -> None:
    rng = random.Random(505)
    ws = fresh("scheduling")
    people = {"Anna": ("Europe/Berlin", 9, 17), "Ben": ("America/New_York", 9, 17),
              "Chitra": ("Asia/Kolkata", 12, 21), "Dan": ("Europe/London", 8, 16)}
    (ws / "people.json").write_text(json.dumps(
        {name: {"time_zone": tz, "working_hours_local": f"{start:02d}:00-{end:02d}:00", "working_days": "Mon-Fri"}
         for name, (tz, start, end) in people.items()}, indent=2))
    busy = {}
    (ws / "calendars").mkdir()
    for name, (tz, start, end) in people.items():
        zone = ZoneInfo(tz)
        events = []
        for day in range(16, 21):
            for _ in range(rng.randint(2, 4)):
                hour = rng.randint(start, end - 1)
                begin = datetime(2026, 11, day, hour, rng.choice([0, 15, 30, 45]), tzinfo=zone)
                events.append((begin, begin + timedelta(minutes=rng.choice([30, 45, 60, 90]))))
        busy[name] = events
        ics = ["BEGIN:VCALENDAR", "VERSION:2.0"]
        for i, (b, e) in enumerate(events):
            ics += ["BEGIN:VEVENT", f"UID:{name}-{i}", f"DTSTART;TZID={tz}:{b:%Y%m%dT%H%M%S}",
                    f"DTEND;TZID={tz}:{e:%Y%m%dT%H%M%S}", "SUMMARY:Busy", "END:VEVENT"]
        (ws / "calendars" / f"{name.lower()}.ics").write_text("\r\n".join(ics + ["END:VCALENDAR"]) + "\r\n")

    def free(slot_start, minutes):
        slot_end = slot_start + timedelta(minutes=minutes)
        for name, (tz, start, end) in people.items():
            local_start, local_end = slot_start.astimezone(ZoneInfo(tz)), slot_end.astimezone(ZoneInfo(tz))
            if local_start.weekday() >= 5 or local_start.date() != local_end.date():
                return False
            if local_start.hour < start or (local_end.hour, local_end.minute) > (end, 0):
                return False
            if any(b < slot_end and slot_start < e for b, e in busy[name]):
                return False
        return True

    starts, t = [], datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
    while t < datetime(2026, 11, 21, tzinfo=timezone.utc):
        if free(t, 45):
            starts.append(t)
        t += timedelta(minutes=15)
    first_end = starts[0] + timedelta(minutes=45)
    # "Starts after the first one ends" reads both ways; accept a start at or strictly after that moment.
    follow_ups = {next(s for s in starts if s >= first_end), next(s for s in starts if s > first_end)}
    save_expected("scheduling", {"first": starts[0].strftime("%Y-%m-%dT%H:%MZ"),
                                 "follow_up": sorted(s.strftime("%Y-%m-%dT%H:%MZ") for s in follow_ups)})


# 6. Subscription KPI report -----------------------------------------------------------------------

METRICS = """# Metric definitions

- Price list: `plans.json`. Annual plans are billed yearly at the yearly price; their MRR is yearly price / 12.
- A subscription counts on a month-end date if it started on or before that date and has not ended by then
  (an `ended` date on or before the month end means it no longer counts).
- MRR at month end: sum of the MRR of every counting subscription, after its discount (`discount_pct`).
- Churned customers in a month: customers with at least one subscription ending in that month and no
  subscription counting at that month end.
- Report MRR rounded to cents.
"""


def build_kpi() -> None:
    rng = random.Random(606)
    ws = fresh("kpi_report")
    plans = {"starter_m": {"price": 29, "period": "month"}, "team_m": {"price": 99, "period": "month"},
             "team_y": {"price": 990, "period": "year"}, "business_m": {"price": 249, "period": "month"},
             "business_y": {"price": 2490, "period": "year"}}
    (ws / "plans.json").write_text(json.dumps(plans, indent=2))
    (ws / "metrics.md").write_text(METRICS)
    subs = []
    for i in range(1, 61):
        started = date(2026, 3, 1) + timedelta(days=rng.randint(0, 200))
        ended = started + timedelta(days=rng.randint(20, 240)) if rng.random() < 0.35 else None
        subs.append({"subscription_id": f"S{i:03d}", "customer": f"C{rng.randint(1, 42):03d}",
                     "plan": rng.choice(list(plans)), "started": started, "ended": ended,
                     "discount_pct": rng.choice([0, 0, 0, 10, 20])})
    write_csv(ws / "subscriptions.csv", ["subscription_id", "customer", "plan", "started", "ended", "discount_pct"],
              [[s["subscription_id"], s["customer"], s["plan"], s["started"], s["ended"] or "", s["discount_pct"]]
               for s in subs])

    def mrr(sub):
        plan = plans[sub["plan"]]
        base = Decimal(plan["price"]) / (12 if plan["period"] == "year" else 1)
        return base * (100 - sub["discount_pct"]) / 100

    def counts(sub, day):
        return sub["started"] <= day and not (sub["ended"] and sub["ended"] <= day)

    months = {"2026-07": date(2026, 7, 31), "2026-08": date(2026, 8, 31), "2026-09": date(2026, 9, 30),
              "2026-10": date(2026, 10, 31)}
    expected = {}
    for month, end in months.items():
        total = money(sum((mrr(s) for s in subs if counts(s, end)), Decimal(0)))
        ending = {s["customer"] for s in subs if s["ended"] and s["ended"].strftime("%Y-%m") == month}
        active = {s["customer"] for s in subs if counts(s, end)}
        expected[month] = {"mrr": str(total), "churned": len(ending - active)}
    save_expected("kpi_report", {"months": expected})


# 7. Handbook questions ----------------------------------------------------------------------------

HANDBOOK = {
    "leave.md": "# Leave\n\nFull-time employees get 28 vacation days per year. Part-time employees get the same days "
                "pro rata to their contracted hours, rounded up to whole days. Unused days expire on 31 March of the "
                "following year. Parental leave is governed by local law.\n",
    "remote.md": "# Remote work\n\nUp to 3 remote days per week. Working from abroad is allowed for at most 20 working "
                 "days per calendar year and needs approval from People Ops at least 10 working days in advance.\n",
    "equipment.md": "# Equipment\n\nLaptops are replaced every 36 months. The home office budget is 600 EUR when you join, "
                    "plus 150 EUR on each work anniversary.\n",
    "learning.md": "# Learning\n\nEach employee has a learning budget of 1,200 EUR per calendar year. Conferences abroad "
                   "count at 50% of their cost against the budget. Unused budget does not roll over.\n",
    "oncall.md": "# On-call\n\nOn-call weeks pay a flat 350 EUR. A weekend incident handled for more than 2 hours adds "
                 "one compensatory day off. On-call is capped at 8 weeks per person per year.\n",
    "old-remote-2024.md": "# Remote work (2024, superseded)\n\nUp to 2 remote days per week. Working from abroad: 10 days.\n",
}

QUESTIONS = [
    ("q1", "How many vacation days per year does someone working 24 of 40 hours get?", "17"),
    ("q2", "Today a colleague asks to work from abroad starting in 7 working days. Allowed? Answer yes or no.", "no"),
    ("q3", "Two conferences abroad cost 900 EUR and 700 EUR. How much learning budget is left this year?", "400"),
    ("q4", "How many working days per calendar year may someone work from abroad?", "20"),
    ("q5", "An engineer joined 2 years and 1 month ago. Total home office budget received so far, in EUR?", "900"),
    ("q6", "Someone was on call for 3 weeks and handled two weekend incidents of 3 and 1.5 hours. "
           "Extra pay in EUR and compensatory days? Answer as '<EUR>, <days>'.", "1050, 1"),
]


def build_handbook() -> None:
    ws = fresh("handbook")
    (ws / "handbook").mkdir()
    for name, text in HANDBOOK.items():
        (ws / "handbook" / name).write_text(text)
    (ws / "questions.json").write_text(json.dumps([{"id": q, "question": text} for q, text, _ in QUESTIONS], indent=2))
    save_expected("handbook", {"answers": {q: answer for q, _, answer in QUESTIONS}})


# 8. Inbox triage ----------------------------------------------------------------------------------

TRIAGE_RULES = """# Triage rules (we are Northwind Studio, domain northwind.studio)

For every email in ./mail decide one action:

- `pay`: an invoice or payment request addressed to us from a known supplier (see suppliers.csv). Due date = the
  due date in the email.
- `reply`: a client (see clients.csv) asks a question or requests something. Due date = 2 business days after the
  email date (Mon-Fri), unless the client states an earlier deadline, which then wins.
- `schedule`: someone proposes a meeting time. Due date = the proposed meeting date.
- `report`: a payment request or "updated bank details" email from a sender that is not a known supplier or client.
  Due date = the email date.
- `ignore`: newsletters, notifications and everything else. No due date.

Write triage.csv with columns file,action,due (YYYY-MM-DD, empty for ignore).
"""


def build_triage() -> None:
    rng = random.Random(808)
    ws = fresh("triage")
    suppliers = {"billing@printhaus.example": "Printhaus", "invoices@cloudhost.example": "CloudHost"}
    clients = {"anna@acme.example": "Acme", "li@globex.example": "Globex", "sam@initech.example": "Initech"}
    write_csv(ws / "suppliers.csv", ["email", "name"], [[k, v] for k, v in suppliers.items()])
    write_csv(ws / "clients.csv", ["email", "name"], [[k, v] for k, v in clients.items()])
    (ws / "rules.md").write_text(TRIAGE_RULES)

    def business_days(day, n):
        while n:
            day += timedelta(days=1)
            if day.weekday() < 5:
                n -= 1
        return day

    mails, expected = [], {}
    base = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    for i in range(1, 25):
        sent = base + timedelta(days=rng.randint(0, 10), hours=rng.randint(0, 8))
        kind = rng.choice(["pay", "reply", "reply_deadline", "schedule", "report", "ignore", "client_fyi"])
        due = None
        if kind == "pay":
            sender = rng.choice(list(suppliers))
            due = (sent + timedelta(days=rng.choice([14, 21, 30]))).date()
            subject, body = f"Invoice {rng.randint(100, 999)}", f"Please pay EUR {rng.randint(80, 900)}.00 by {due}."
            action = "pay"
        elif kind in ("reply", "reply_deadline"):
            sender = rng.choice(list(clients))
            due = business_days(sent.date(), 2)
            subject, body = "Question about the draft", "Could you send the revised mockups and the timeline?"
            if kind == "reply_deadline":
                earlier = sent.date() + timedelta(days=1)
                body += f" We need them by {earlier} at the latest."
                due = min(due, earlier)
            action = "reply"
        elif kind == "schedule":
            sender = rng.choice(list(clients) + ["recruiter@talent.example"])
            due = (sent + timedelta(days=rng.randint(2, 9))).date()
            subject, body = "Meeting?", f"Would {due} at 15:00 work for a 30 minute call?"
            action = "schedule"
        elif kind == "report":
            sender = rng.choice(["billing@printhaus-payments.example", "accounts@cl0udhost.example"])
            due = sent.date()
            subject, body = "Updated bank details", "Our bank details changed. Please pay the open invoice to the new IBAN."
            action = "report"
        elif kind == "client_fyi":
            sender = rng.choice(list(clients))
            subject, body = "FYI", "Just letting you know the launch went well. No action needed."
            action = "ignore"
        else:
            sender = "news@designweekly.example"
            subject, body = "This week in design", "Top stories this week."
            action = "ignore"
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = sender, "team@northwind.studio", subject
        message["Date"] = format_datetime(sent)
        message.set_content(body)
        name = f"{i:02d}.eml"
        mails.append((name, message))
        expected[name] = {"action": action, "due": str(due) if due else ""}
    (ws / "mail").mkdir()
    for name, message in mails:
        (ws / "mail" / name).write_text(message.as_string())
    save_expected("triage", {"rows": expected})


if __name__ == "__main__":
    for build in (build_expenses, build_reconciliation, build_incident, build_bugfix, build_scheduling, build_kpi,
                  build_handbook, build_triage):
        build()
    print("built", sorted(p.name for p in ROOT.iterdir() if (p / "expected.json").exists()))
