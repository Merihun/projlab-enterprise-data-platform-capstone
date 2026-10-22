"""Inventory events of both brands on one topic, and the stock they add up to.

Skarvik's events carry Skarvik's own SKUs; ``product_xref.csv`` maps them to the canonical SKUs. A few
Skarvik SKUs are not in it. Some events are delivered twice with the same ``event_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache

from .common import rng

SKUS = 400
UNMAPPED_SKUS = 12
EVENTS = 24000
WAREHOUSES = {"fernhill": ("LHR1", "MAN2", "EDI3"), "skarvik": ("GOT1", "STO2")}
EVENT_COLUMNS = ["event_id", "brand", "sku", "warehouse_id", "event_type", "quantity_delta", "event_ts"]


def canonical(i: int) -> str:
    return f"SKU-{i:05d}"


@lru_cache(maxsize=1)
def xref() -> dict[str, str]:
    """Skarvik SKU -> canonical SKU, for the Skarvik SKUs that have been mapped."""
    return {f"SKV-{7000 + i}": canonical(i) for i in range(1, SKUS + 1) if i % 2 == 0}


@lru_cache(maxsize=1)
def unmapped_skus() -> tuple[str, ...]:
    return tuple(f"SKV-{9000 + i}" for i in range(UNMAPPED_SKUS))


@lru_cache(maxsize=1)
def events() -> list[dict]:
    """The topic, in delivery order: unique events, with about 2% of the mapped ones delivered a second time."""
    r = rng("inventory")
    mapped = sorted(xref())
    start = datetime(2026, 8, 20, 6, 0, tzinfo=UTC)
    out = []
    for i in range(1, EVENTS + 1):
        brand = "skarvik" if r.random() < 0.4 else "fernhill"
        if brand == "fernhill":
            sku = canonical(r.randint(1, SKUS))
        elif r.random() < 0.015:
            sku = r.choice(unmapped_skus())
        else:
            sku = r.choice(mapped)
        kind = r.choices(("receipt", "sale", "adjustment"), weights=(25, 70, 5))[0]
        delta = r.randint(20, 200) if kind == "receipt" else -r.randint(1, 4) if kind == "sale" else r.randint(-10, 10)
        out.append(
            {
                "event_id": f"INV-{i:07d}",
                "brand": brand,
                "sku": sku,
                "warehouse_id": r.choice(WAREHOUSES[brand]),
                "event_type": kind,
                "quantity_delta": delta,
                "event_ts": (start + timedelta(seconds=i * 3 + r.randint(0, 2))).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    delivered = []
    for event in out:
        delivered.append(event)
        if event["sku"] not in unmapped_skus() and r.random() < 0.02:
            delivered.insert(max(0, len(delivered) - r.randint(1, 40)), event)  # again, a little out of place
    return delivered


def stock() -> list[dict]:
    """On-hand stock per ``(brand, canonical sku, warehouse_id)``: every mapped event counted once."""
    seen, totals = set(), {}
    mapping = xref()
    for e in events():
        if e["event_id"] in seen:
            continue
        seen.add(e["event_id"])
        sku = e["sku"] if e["brand"] == "fernhill" else mapping.get(e["sku"])
        if sku is None:
            continue
        key = (e["brand"], sku, e["warehouse_id"])
        totals[key] = totals.get(key, 0) + e["quantity_delta"]
    return [{"brand": b, "sku": s, "warehouse_id": w, "on_hand": n} for (b, s, w), n in sorted(totals.items())]


def expected_unmapped() -> list[dict]:
    return [{"event_id": e["event_id"], "sku": e["sku"]} for e in events() if e["sku"] in unmapped_skus()]
