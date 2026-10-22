"""Shared helpers. Standard library only."""

from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SEED = "fernhill-enterprise-v1"
FIRST_DAY = date(2026, 6, 1)
LAST_DAY = date(2026, 8, 31)
LAST_ARRIVAL = date(2026, 9, 2)
CENT = Decimal("0.01")


def rng(*parts: object) -> random.Random:
    return random.Random(":".join([SEED, *map(str, parts)]))


def days(start: date = FIRST_DAY, end: date = LAST_DAY) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def write_csv(path: Path, columns: list[str], rows: list[dict] | list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row[c] for c in columns] if isinstance(row, dict) else row)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
