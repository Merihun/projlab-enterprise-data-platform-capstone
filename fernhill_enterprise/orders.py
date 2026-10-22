"""Orders of both brands as their systems deliver them, exchange rates, and what finance has in its ledgers.

Fernhill orders arrive as change events (an order is created, later it may be cancelled), a file per day,
not always in order. Skarvik's ERP writes a file per day too, in its own field names and in SEK; some orders
are in a later file than their order date, and the files that arrived on 2 September repeat orders that had
already been delivered. Everything finance reports is worked out here from the final state of each order.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache

from . import people
from .common import FIRST_DAY, LAST_ARRIVAL, LAST_DAY, days, money, rng

FIRST_RATE_DAY = date(2026, 5, 25)
RESEND_ARRIVAL = date(2026, 9, 2)  # CAP-7.2
RESEND_FROM = date(2026, 8, 24)
INCIDENT_OVERSTATEMENT = Decimal("0.031")
BAD_BATCH = "bad_batch_2026_08_20"

FX_COLUMNS = ["rate_date", "gbp_per_sek"]
CDC_COLUMNS = ["op", "event_ts", "order_id", "customer_id", "status", "amount", "currency", "order_ts"]
SKARVIK_COLUMNS = ["order_nr", "kund_id", "belopp_sek", "orderdatum", "ordertid", "status"]


@lru_cache(maxsize=1)
def fx_rates() -> dict[date, Decimal]:
    """GBP per SEK, published on business days only. A weekend or holiday uses the latest earlier rate."""
    r = rng("fx")
    rate, out = Decimal("0.07450"), {}
    for day in days(FIRST_RATE_DAY, LAST_ARRIVAL):
        if day.weekday() < 5 and day != date(2026, 6, 19):  # Midsummer Eve: no rate published
            rate = (rate + Decimal(r.randint(-40, 40)) / Decimal(100000)).quantize(Decimal("0.00001"))
            out[day] = rate
    return out


def rate_on(day: date) -> tuple[date, Decimal] | None:
    """``(rate date, rate)``: the latest rate published on or before ``day``. None before the first rate."""
    rates = fx_rates()
    while day >= FIRST_RATE_DAY:
        if day in rates:
            return day, rates[day]
        day -= timedelta(days=1)
    return None


def _moment(r, day: date) -> datetime:
    return datetime.combine(day, time(), UTC) + timedelta(seconds=r.randrange(86400))


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@lru_cache(maxsize=1)
def fernhill_orders() -> list[dict]:
    """Every Fernhill order in its final state, with the day its cancellation (if any) happened."""
    customers = [c["customer_id"] for c in people.build()["fernhill"]]
    out = []
    for day in days():
        r = rng("fernhill-orders", day)
        for i in range(1, 100 + (30 if day.weekday() >= 5 else 0) + r.randint(0, 40) + 1):
            placed = _moment(r, day)
            cancelled = placed + timedelta(hours=r.randint(2, 60)) if r.random() < 0.05 else None
            out.append(
                {
                    "order_id": f"FH-{day:%Y%m%d}-{i:04d}",
                    "customer_id": r.choice(customers),
                    "amount": money(Decimal(r.randint(900, 24000)) / 100),
                    "order_ts": placed,
                    "order_date": day,
                    "cancelled_at": cancelled,
                    "status": "cancelled" if cancelled else "paid",
                }
            )
    return out


def fernhill_cdc() -> dict[date, list[dict]]:
    """The change events by the day they were delivered. An event is delivered on the day it happened; about
    1 in 100 creations turns up a day late, after a newer event for the same order may already have arrived."""
    files: dict[date, list[dict]] = {d: [] for d in days(FIRST_DAY, LAST_ARRIVAL)}
    r = rng("fernhill-cdc")
    for o in fernhill_orders():
        base = {"order_id": o["order_id"], "customer_id": o["customer_id"], "amount": str(o["amount"]), "currency": "GBP", "order_ts": _stamp(o["order_ts"])}  # fmt: skip
        created_file = o["order_date"] + timedelta(days=1 if r.random() < 0.01 else 0)
        files[created_file].append({"op": "c", "event_ts": _stamp(o["order_ts"]), **base, "status": "paid"})
        if o["cancelled_at"]:
            files[min(o["cancelled_at"].date(), LAST_ARRIVAL)].append(
                {"op": "u", "event_ts": _stamp(o["cancelled_at"]), **base, "status": "cancelled"}
            )
    for day, events in files.items():
        rng("fernhill-cdc-order", day).shuffle(events)
    return files


@lru_cache(maxsize=1)
def skarvik_orders() -> list[dict]:
    """Every Skarvik order, with the day the file that first carried it arrived."""
    customers = [c["kund_id"] for c in people.build()["skarvik"]]
    out = []
    for day in days():
        r = rng("skarvik-orders", day)
        for i in range(1, 75 + (20 if day.weekday() >= 5 else 0) + r.randint(0, 30) + 1):
            placed = _moment(r, day)
            late = r.choice((1, 2, 3)) if r.random() < 0.08 else 0
            out.append(
                {
                    "order_nr": f"SK{day:%y%m%d}{i:04d}",
                    "kund_id": r.choice(customers),
                    "belopp_sek": money(Decimal(r.randint(9900, 399900)) / 100),
                    "order_ts": placed,
                    "order_date": day,
                    "status": "annullerad" if r.random() < 0.04 else "betald",
                    "arrived": min(day + timedelta(days=1 + late), LAST_ARRIVAL),
                }
            )
    return out


def _file_row(o: dict) -> dict:
    return {
        "order_nr": o["order_nr"],
        "kund_id": o["kund_id"],
        "belopp_sek": f"{o['belopp_sek']:.2f}".replace(".", ","),  # the ERP writes decimal commas
        "orderdatum": o["order_date"].isoformat(),
        "ordertid": o["order_ts"].strftime("%Y-%m-%d %H:%M:%S"),
        "status": o["status"],
    }


def gbp(o: dict) -> tuple[Decimal, date]:
    rate_date, rate = rate_on(o["order_date"])
    return money(o["belopp_sek"] * rate), rate_date


def sek(o: dict) -> tuple[Decimal, date]:
    rate_date, rate = rate_on(o["order_date"])
    return money(o["amount"] / rate), rate_date


@lru_cache(maxsize=1)
def resent() -> list[dict]:
    """CAP-7.2: the Skarvik orders that the files of 2 September carried a second time. Enough of them, from
    24 August on, that counting them twice puts August's revenue in GBP 3.1% above the ledger."""
    target = INCIDENT_OVERSTATEMENT * sum(v for (m, c), v in ledger().items() if m == "2026-08" and c == "GBP")
    total, chosen = Decimal(0), []
    for o in skarvik_orders():
        if RESEND_FROM <= o["order_date"] <= LAST_DAY and o["status"] == "betald" and o["arrived"] < RESEND_ARRIVAL:
            chosen.append(o)
            total += gbp(o)[0]
            if total >= target:
                break
    return chosen


def skarvik_files() -> dict[date, list[dict]]:
    """The ERP's files by arrival day. A file holds the orders first delivered that day; the file of
    2 September also repeats ``resent()``."""
    files: dict[date, list[dict]] = {}
    for o in skarvik_orders():
        files.setdefault(o["arrived"], []).append(_file_row(o))
    files.setdefault(RESEND_ARRIVAL, []).extend(_file_row(o) for o in resent())
    return dict(sorted(files.items()))


def bad_batch() -> list[dict]:
    """CAP-5.1: a batch that must not reach gold. Duplicate order numbers, negative amounts, a customer that
    does not exist and an amount that is not a number."""
    good = [o for o in skarvik_orders() if o["order_date"] == date(2026, 8, 20)][:40]
    rows = [{**_file_row(o), "order_nr": o["order_nr"].replace("SK", "SB"), "batch_id": BAD_BATCH} for o in good]
    rows += [dict(rows[i]) for i in (0, 1, 2, 3, 4)]
    for i in (5, 6, 7):
        rows[i]["belopp_sek"] = "-" + rows[i]["belopp_sek"]
    rows[8]["kund_id"] = "K999999"
    rows[9]["belopp_sek"] = "n/a"
    return rows


# ---------------------------------------------------------------- what is true


def silver_orders() -> list[dict]:
    """Both brands' orders in the canonical shape, once each, in their final state."""
    out = []
    for o in fernhill_orders():
        rate = rate_on(o["order_date"])
        out.append(
            {
                "brand": "fernhill", "source_order_id": o["order_id"], "order_date": o["order_date"].isoformat(),
                "amount_local": f"{o['amount']:.2f}", "currency": "GBP", "amount_gbp": f"{o['amount']:.2f}",
                "fx_rate_date": rate[0].isoformat() if rate else "", "status": o["status"],
            }
        )  # fmt: skip
    for o in skarvik_orders():
        amount, rate_date = gbp(o)
        out.append(
            {
                "brand": "skarvik", "source_order_id": o["order_nr"], "order_date": o["order_date"].isoformat(),
                "amount_local": f"{o['belopp_sek']:.2f}", "currency": "SEK", "amount_gbp": f"{amount:.2f}",
                "fx_rate_date": rate_date.isoformat(), "status": "cancelled" if o["status"] == "annullerad" else "paid",
            }
        )  # fmt: skip
    return out


@lru_cache(maxsize=1)
def revenue() -> dict[tuple[str, str], dict[str, Decimal]]:
    """Net revenue (orders that were not cancelled) per ``(month, brand)`` in both currencies."""
    out: dict[tuple[str, str], dict[str, Decimal]] = {}
    for o in fernhill_orders():
        if o["status"] != "cancelled":
            cell = out.setdefault((f"{o['order_date']:%Y-%m}", "fernhill"), {"GBP": Decimal(0), "SEK": Decimal(0)})
            cell["GBP"] += o["amount"]
            cell["SEK"] += sek(o)[0]
    for o in skarvik_orders():
        if o["status"] != "annullerad":
            cell = out.setdefault((f"{o['order_date']:%Y-%m}", "skarvik"), {"GBP": Decimal(0), "SEK": Decimal(0)})
            cell["GBP"] += gbp(o)[0]
            cell["SEK"] += o["belopp_sek"]
    return out


def ledger() -> dict[tuple[str, str], Decimal]:
    """Finance's general ledger: net revenue per ``(month, currency)``, both brands together."""
    out: dict[tuple[str, str], Decimal] = {}
    for (month, _brand), cell in revenue().items():
        for currency, value in cell.items():
            out[(month, currency)] = out.get((month, currency), Decimal(0)) + value
    return out


def incident_revenue() -> list[dict]:
    """CAP-7.2: August as the gold revenue table showed it on the morning of 3 September, with the orders
    that were delivered twice counted twice."""
    twice = sum(gbp(o)[0] for o in resent())
    twice_sek = sum(o["belopp_sek"] for o in resent())
    rows = []
    for (month, brand), cell in sorted(revenue().items()):
        extra = month == "2026-08" and brand == "skarvik"
        rows.append(
            {
                "revenue_month": month, "brand": brand,
                "net_revenue_gbp": f"{cell['GBP'] + (twice if extra else 0):.2f}",
                "net_revenue_sek": f"{cell['SEK'] + (twice_sek if extra else 0):.2f}",
            }
        )  # fmt: skip
    return rows
