# Enterprise Data Platform: what this starter gives you

You are given the two companies' source systems and the numbers finance, security and support will hold
you to. The platform is yours to design and build. Everything here is generated from fixed seeds, so every
copy of the project has the same data and the same expected results.

    python -m fernhill_enterprise generate        writes data/, golden/ and sandbox/seeded_pii_docs/ (2 seconds, 12 MB)

Run it once after unpacking, and as the first step of any CI job that needs the data: none of it is in git.
The generator needs only Python. You do not change `fernhill_enterprise/`.

## The sources (`data/`)

| Path | What it is |
|------|------------|
| `fernhill/customers.csv` | 6,000 Fernhill customers: `customer_id`, `email`, `phone`, `full_name`, `country`, `tier`, `updated_at`. |
| `skarvik/kunder.csv` | 5,000 Skarvik customers in the ERP's names: `kund_id`, `epost`, `telefon`, `namn`, `land`, `uppdaterad`. 600 of them (12%) are also Fernhill customers. |
| `fernhill/orders_cdc/<day>.jsonl` | Fernhill order change events, a file per delivery day: `op` (`c` created, `u` updated), `event_ts`, `order_id`, `customer_id`, `status`, `amount`, `currency`, `order_ts`. An order is created `paid` and may later become `cancelled`. About 1 creation in 100 is delivered a day late, after the cancellation may already have arrived. |
| `skarvik/orders/arrived=<day>/ordrar.csv` | The ERP's order file per arrival day: `order_nr`, `kund_id`, `belopp_sek` (decimal comma), `orderdatum`, `ordertid`, `status` (`betald`, `annullerad`). Most orders arrive the day after their order date, about 8% one to three days later. |
| `fx/sek_gbp.csv` | `rate_date`, `gbp_per_sek`. Published on business days only, from 25 May 2026. |
| `finance/finance_gl.csv` | Finance's ledger: net revenue per `month` and `currency`, both brands together. |
| `finance/skarvik_ledger.csv` | Skarvik's own ledger: `month`, `net_revenue_sek`. |
| `inventory/events.jsonl` | 24,467 inventory events of both brands in delivery order: `event_id`, `brand`, `sku`, `warehouse_id`, `event_type`, `quantity_delta`, `event_ts`. Publish them to your topic to replay them. |
| `inventory/product_xref.csv` | `skarvik_sku` to canonical `sku`. |
| `product_docs/PRD-*.md` | 600 product documents. |
| `injections/bad_batch_2026_08_20.csv` | CAP-5.1: a batch that must never reach gold. |
| `incidents/CAP-7.2/gold_revenue_2026-09-03.csv` | CAP-7.2: the revenue table as it stood on the morning the incident was raised. |

Orders run from 1 June to 31 August 2026; files arrive until 2 September.

### What the numbers mean

- **Net revenue** is the sum of the amounts of orders whose final status is not cancelled, by order date.
- **GBP for a Skarvik order** is `belopp_sek × gbp_per_sek`, with the latest rate published on or before the
  order date, rounded half up to 2 decimal places. **SEK for a Fernhill order** is `amount ÷ gbp_per_sek`
  with the same rule. Sum the rounded amounts.
- **A person** may be a customer of one brand or both. The records of someone who is both differ the way
  real records do: letter case and spaces in the email address, phone numbers written nationally or
  internationally, sometimes a second email address. Some different people share a phone, and some have the
  same surname and the same digits in different countries.
- **EU customers** for CAP-4.3 are those whose country is in the EU: Sweden, Denmark, Finland, Ireland and
  Germany here. Norway, the United Kingdom and the United States are not.

## The expected results (`golden/`)

| File | Ticket | What it holds |
|------|--------|---------------|
| `silver_orders_fx.csv` | CAP-3.1 | Every order of both brands once: `brand`, `source_order_id`, `order_date`, `amount_local`, `currency`, `amount_gbp`, `fx_rate_date`. |
| `silver_counts.csv` | CAP-3.2 | Orders per `brand` and `order_date` once every file has arrived. |
| `unified_stock.csv`, `expected_unmapped.csv` | CAP-3.3 | Stock per `(brand, sku, warehouse_id)`, and the events whose SKU has no mapping. |
| `customer_matches.csv` | CAP-4.1 | Which person each customer record belongs to. |
| `revenue_gbp_before_cr.csv` | CAP-7.1 | Net revenue in GBP per month and brand, before the change request. |
| `resent_orders.csv` | CAP-7.2 | The orders the late files carried a second time, with their dates: the dates your backfill may rewrite. |
| `support_questions.jsonl` | CAP-6.1 | 200 questions with the document that answers each. |
| `pii_totals.json` | CAP-6.2 | How much personal data is pasted into the catalogue, by kind. |
| `scenarios/*.json` | CAP-6.3 | Which documents and sections each scenario changes. |

`sandbox/seeded_pii_docs/` holds twelve small documents with planted personal data and `manifest.json`,
the count of each kind in each document.

## Tools

    python -m fernhill_enterprise score-matches customer_match_export.csv
        pairwise precision and recall of your matching. Your file needs brand, source_id, golden_customer_id.
    python -m fernhill_enterprise mutate plan.json --mutation public_bucket
        CAP-2.1: writes plan.public_bucket.json, an unsafe copy of your Terraform plan. Also
        sse_s3_instead_of_kms and iam_wildcard. Your policy tests must fail on each.
    python -m fernhill_enterprise docs --scenario edit_50_docs      (or delete_10_docs)
        CAP-6.3: changes data/product_docs the way the scenario says.
    python -m fernhill_enterprise docs --reset
        puts the product documents back.

## Product documents

A document has a front matter (`doc_id`, `title`, `brand`, `updated_at`) and one `##` section per topic.
The front matter is metadata, not text to embed. Forty documents have support tickets pasted into them,
with email addresses, phone numbers and IBANs. Apart from those, no document contains anything that looks
like personal data, so a correct pipeline has nothing to redact in the other 560.

Retrieval is judged per document: a question counts as answered when its document is among the ten nearest
chunks. Plain word matching already passes 0.8 on these questions, so the criterion does not depend on
which embedding model you choose; record the one you use.

## The lab

The lakehouse lab (a workspace with PySpark, Delta Lake and JupyterLab, and S3-compatible storage) plus the
two services the capstone needs: a Kafka broker and PostgreSQL 16 with pgvector.

    docker compose up -d --build --wait
    docker compose exec workspace python -m pytest -q tests/test_environment.py
    docker compose exec workspace python -m fernhill_enterprise generate
    docker compose exec workspace python -m fernhill_enterprise publish-events     replay the inventory topic

Inside the workspace these are set for you:

| Variable | Value |
|----------|-------|
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `postgres`, `5432`, `projlab`, `projlab`, `projlab` (pgvector enabled) |
| `S3_ENDPOINT_URL`, `S3_BUCKET` | `http://seaweedfs:8333`, `lakehouse` |

`publish-events` sends the events to `inventory.events` keyed by brand and SKU; run it again to replay them
(your ledger must make the second replay change nothing). AWS and Databricks are your own accounts: the lab
stands in for them while you build and test.
