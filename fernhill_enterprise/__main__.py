"""python -m fernhill_enterprise <command>

    generate [--force]                  write data/, golden/ and sandbox/seeded_pii_docs/
    docs --scenario NAME | --reset      change the product documents (edit_50_docs, delete_10_docs), or restore them
    mutate PLAN --mutation NAME [--out FILE]
                                        make a Terraform plan unsafe (public_bucket, sse_s3_instead_of_kms, iam_wildcard)
    score-matches FILE                  pairwise precision and recall of your customer matches (brand, source_id, golden_customer_id)
    publish-events [--topic NAME]       replay data/inventory/events.jsonl into Kafka (default topic inventory.events)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from itertools import combinations
from pathlib import Path

from . import docs, inventory, orders, people, plan
from .common import write_csv, write_jsonl

ROOT = Path(os.environ.get("FERNHILL_ENTERPRISE_ROOT", Path(__file__).resolve().parents[1]))


def generate(root: Path = ROOT) -> dict[str, int]:
    data, golden = root / "data", root / "golden"
    counts: dict[str, int] = {}
    built = people.build()
    write_csv(data / "fernhill" / "customers.csv", people.FERNHILL_COLUMNS, built["fernhill"])
    write_csv(data / "skarvik" / "kunder.csv", people.SKARVIK_COLUMNS, built["skarvik"])
    counts["customers"] = len(built["truth"])
    for day, events in orders.fernhill_cdc().items():
        write_jsonl(data / "fernhill" / "orders_cdc" / f"{day}.jsonl", events)
    files = orders.skarvik_files()
    for day, rows in files.items():
        write_csv(data / "skarvik" / "orders" / f"arrived={day}" / "ordrar.csv", orders.SKARVIK_COLUMNS, rows)
    counts["order_files"] = len(files) + len(orders.fernhill_cdc())
    write_csv(data / "fx" / "sek_gbp.csv", orders.FX_COLUMNS, [(d.isoformat(), r) for d, r in orders.fx_rates().items()])
    write_csv(data / "injections" / f"{orders.BAD_BATCH}.csv", [*orders.SKARVIK_COLUMNS, "batch_id"], orders.bad_batch())
    ledger = orders.ledger()
    write_csv(data / "finance" / "finance_gl.csv", ["month", "currency", "net_revenue"], [(m, c, f"{v:.2f}") for (m, c), v in sorted(ledger.items())])
    revenue = orders.revenue()
    write_csv(data / "finance" / "skarvik_ledger.csv", ["month", "net_revenue_sek"], [(m, f"{cell['SEK']:.2f}") for (m, b), cell in sorted(revenue.items()) if b == "skarvik"])
    write_csv(data / "incidents" / "CAP-7.2" / "gold_revenue_2026-09-03.csv", ["revenue_month", "brand", "net_revenue_gbp", "net_revenue_sek"], orders.incident_revenue())
    write_jsonl(data / "inventory" / "events.jsonl", inventory.events())
    write_csv(data / "inventory" / "product_xref.csv", ["skarvik_sku", "sku"], sorted(inventory.xref().items()))
    counts["inventory_events"] = len(inventory.events())
    totals = docs.write_catalogue(data / "product_docs")
    counts["product_docs"] = docs.PRODUCTS
    docs.write_seeded(root / "sandbox" / "seeded_pii_docs")

    silver = orders.silver_orders()
    write_csv(golden / "silver_orders_fx.csv", ["brand", "source_order_id", "order_date", "amount_local", "currency", "amount_gbp", "fx_rate_date"], silver)
    per_day: dict[tuple[str, str], int] = {}
    for o in silver:
        per_day[(o["brand"], o["order_date"])] = per_day.get((o["brand"], o["order_date"]), 0) + 1
    write_csv(golden / "silver_counts.csv", ["brand", "order_date", "n"], [(b, d, n) for (b, d), n in sorted(per_day.items())])
    write_csv(golden / "revenue_gbp_before_cr.csv", ["revenue_month", "brand", "net_revenue_gbp"], [(m, b, f"{cell['GBP']:.2f}") for (m, b), cell in sorted(revenue.items())])
    write_csv(golden / "customer_matches.csv", people.TRUTH_COLUMNS, built["truth"])
    write_csv(golden / "unified_stock.csv", ["brand", "sku", "warehouse_id", "on_hand"], inventory.stock())
    write_csv(golden / "expected_unmapped.csv", ["event_id", "sku"], inventory.expected_unmapped())
    write_csv(golden / "resent_orders.csv", ["source_order_id", "order_date"], [(o["order_nr"], o["order_date"].isoformat()) for o in orders.resent()])
    write_jsonl(golden / "support_questions.jsonl", docs.questions())
    (golden / "pii_totals.json").write_text(json.dumps(totals, indent=2) + "\n", encoding="utf-8")
    for name in ("edit_50_docs", "delete_10_docs"):
        (golden / "scenarios").mkdir(parents=True, exist_ok=True)
        (golden / "scenarios" / f"{name}.json").write_text(json.dumps(docs.scenario(name), indent=2) + "\n", encoding="utf-8")
    return counts


def score_matches(path: Path) -> tuple[float, float]:
    """Pairwise precision and recall: of the pairs of records you put in one golden customer, how many are
    one person; and of the pairs that are one person, how many you put together."""
    def pairs(groups: dict[str, list[tuple[str, str]]]) -> set[frozenset]:
        return {frozenset(p) for members in groups.values() for p in combinations(sorted(members), 2)}

    truth: dict[str, list[tuple[str, str]]] = {}
    for row in people.build()["truth"]:
        truth.setdefault(row["person_id"], []).append((row["brand"], row["source_id"]))
    yours: dict[str, list[tuple[str, str]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            yours.setdefault(row["golden_customer_id"], []).append((row["brand"], str(row["source_id"])))
    predicted, actual = pairs(yours), pairs(truth)
    hit = len(predicted & actual)
    return (hit / len(predicted) if predicted else 1.0), (hit / len(actual) if actual else 1.0)


def publish_events(topic: str) -> int:
    """CAP-3.3: the inventory events, in delivery order, keyed by brand and SKU so one item stays in one
    partition. Needs the lab's Kafka (KAFKA_BOOTSTRAP_SERVERS) and confluent-kafka, both in the workspace."""
    from confluent_kafka import Producer

    source = ROOT / "data" / "inventory" / "events.jsonl"
    if not source.is_file():
        print("data/inventory/events.jsonl is missing. Run: python -m fernhill_enterprise generate")
        return 2
    producer = Producer({"bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"), "linger.ms": 20})
    sent = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        producer.produce(topic, key=f"{event['brand']}:{event['sku']}", value=line.encode())
        sent += 1
        if sent % 5000 == 0:
            producer.flush()
    left = producer.flush(60)
    print(f"published {sent - left} events to {topic}" + (f"; {left} not delivered" if left else ""))
    return 1 if left else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m fernhill_enterprise", description=__doc__.split("\n\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--force", action="store_true")
    d = sub.add_parser("docs")
    d.add_argument("--scenario", choices=("edit_50_docs", "delete_10_docs"))
    d.add_argument("--reset", action="store_true")
    m = sub.add_parser("mutate")
    m.add_argument("plan", type=Path)
    m.add_argument("--mutation", required=True, choices=plan.MUTATIONS)
    m.add_argument("--out", type=Path)
    s = sub.add_parser("score-matches")
    s.add_argument("file", type=Path)
    e = sub.add_parser("publish-events")
    e.add_argument("--topic", default="inventory.events")
    args = parser.parse_args(argv)
    if args.command == "generate":
        if (ROOT / "golden" / "customer_matches.csv").is_file() and not args.force:
            print("data/ and golden/ are already here. Use --force to write them again.")
            return 0
        counts = generate()
        print("Wrote " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in counts.items()) + f" under {ROOT}")
        return 0
    if args.command == "docs":
        catalogue = ROOT / "data" / "product_docs"
        if args.reset:
            docs.write_catalogue(catalogue)
            print(f"{catalogue} restored: {docs.PRODUCTS} documents")
        elif args.scenario:
            done = docs.apply_scenario(catalogue, args.scenario)
            print(f"{args.scenario}: {len(done.get('edited', []))} edited, {len(done.get('deleted_doc_ids', []))} deleted. Details: golden/scenarios/{args.scenario}.json")
        else:
            parser.error("docs needs --scenario or --reset")
        return 0
    if args.command == "mutate":
        mutated = plan.mutate(json.loads(args.plan.read_text(encoding="utf-8")), args.mutation)
        out = args.out or args.plan.with_name(f"{args.plan.stem}.{args.mutation}.json")
        out.write_text(json.dumps(mutated), encoding="utf-8")
        print(f"{args.mutation}: wrote {out}")
        return 0
    if args.command == "publish-events":
        return publish_events(args.topic)
    precision, recall = score_matches(args.file)
    print(f"pairwise precision {precision:.4f} (need >= 0.99), recall {recall:.4f} (need >= 0.95)")
    return 0 if precision >= 0.99 and recall >= 0.95 else 1


if __name__ == "__main__":
    sys.exit(main())
