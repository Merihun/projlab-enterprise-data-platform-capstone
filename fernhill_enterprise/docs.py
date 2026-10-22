"""The product documents the support chatbot answers from, the questions used to judge retrieval, and the
personal data that was pasted into some of them.

A document is Markdown with a small front matter (``doc_id``, ``title``, ``brand``, ``updated_at``) and one
``##`` section per topic. The front matter is metadata: it is not part of any chunk's text.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .common import rng

PRODUCTS = 600
WITH_PII = 40
SEEDED = 12
QUESTIONS = 200
EDITED, REMOVED_SECTIONS, DELETED = 50, 10, 10
SECTIONS = ("Overview", "Sizing", "Care instructions", "Materials", "Warranty")

_LINES = ("Fjallvind", "Stormhavn", "Nordlys", "Tindra", "Granit", "Havsbris", "Skogsro", "Isbjorn", "Kustled",
          "Vinterdag", "Ridgeway", "Lakeside", "Moorland", "Highcrag", "Tarnside", "Fellfoot", "Peakline",
          "Heathrow", "Saltmarsh", "Birchwood", "Snowfield", "Driftwood", "Summit", "Harbour", "Glacier",
          "Juniper", "Lichen", "Basalt", "Ember", "Frost")  # fmt: skip
_TYPES = ("Shell Jacket", "Down Vest", "Trail Shoe", "Hiking Boot", "Fleece Pullover", "Rain Trousers",
          "Base Layer Top", "Merino Beanie", "Trekking Pole", "Daypack", "Sleeping Bag", "Camping Stove",
          "Softshell Glove", "Running Tight", "Insulated Parka", "Wind Shirt", "Gaiter", "Dry Bag",
          "Headlamp", "Water Bottle", "Ski Sock", "Climbing Harness", "Bivvy Tent", "Travel Towel")  # fmt: skip
_ACTIVITIES = ("day hikes", "alpine climbing", "trail running", "winter camping", "ski touring", "city commuting",
               "sea kayaking", "multi-day trekking", "bikepacking", "fishing trips")  # fmt: skip
_FEATURES = ("taped seams", "a helmet-compatible hood", "pit zips", "a two-way front zip", "reflective piping",
             "an adjustable hem", "articulated elbows", "a stowable hood", "glove-friendly pulls",
             "a reinforced toe cap", "a removable liner", "a roll-top closure", "a chest pocket for a map",
             "recycled insulation", "a rubberised grip", "flatlock stitching")  # fmt: skip
_FITS = ("runs small, so choose one size up", "is true to size", "has a relaxed cut for layering",
         "has a slim athletic cut", "is cut long in the sleeve", "is wide in the forefoot")  # fmt: skip
_WASH = ("at 30 degrees on a gentle cycle", "at 40 degrees with a technical detergent", "by hand in cool water",
         "with a damp cloth only", "at 30 degrees inside a mesh bag")  # fmt: skip
_DRY = ("Tumble dry on low to restore the water repellency", "Hang to dry away from direct heat",
        "Dry flat and reshape while damp", "Air dry fully before storing", "Tumble dry with two clean tennis balls")  # fmt: skip
_NEVER = ("fabric softener", "bleach", "an iron", "dry cleaning", "a radiator to speed up drying")
_FABRICS = ("recycled polyester", "ripstop nylon", "merino wool", "organic cotton", "polyamide", "elastane",
            "full-grain leather", "anodised aluminium", "responsibly sourced down")  # fmt: skip
_COVER = ("manufacturing faults", "seam and zip failures", "delamination", "broken buckles and poles")
_QUESTION = {
    "Overview": ("Is the {name} suitable for {activity}?", "What features does the {name} have?"),
    "Sizing": ("What sizes does the {name} come in?", "Does the {name} run small or large?"),
    "Care instructions": ("How do I wash the {name}?", "Can I tumble dry the {name}?"),
    "Materials": ("What is the {name} made of?", "Which fabric does the {name} use?"),
    "Warranty": ("How long is the warranty on the {name}?", "What does the warranty on the {name} cover?"),
}
_EMAIL_DOMAINS = ("example.com", "example.org", "mail.example")


@lru_cache(maxsize=1)
def products() -> list[dict]:
    r = rng("products")
    names: dict[str, None] = {}
    while len(names) < PRODUCTS:
        names.setdefault(f"{r.choice(_LINES)} {r.randint(1, 9)} {r.choice(_TYPES)}")
    out = []
    for i, name in enumerate(names):
        low = r.choice((34, 36, 38, 40))
        fabrics = r.sample(_FABRICS, 2)
        share = r.choice((60, 70, 80, 85, 92))
        out.append(
            {
                "doc_id": f"PRD-{1001 + i}",
                "title": name,
                "brand": "skarvik" if i % 5 < 2 else "fernhill",
                "updated_at": f"2026-{r.choice((5, 6, 7)):02d}-{r.randint(1, 28):02d}T{r.randint(6, 18):02d}:{r.randint(0, 59):02d}:00Z",
                "sections": {
                    "Overview": f"The {name} is built for {r.choice(_ACTIVITIES)} and {r.choice(_ACTIVITIES)}. It has {', '.join(r.sample(_FEATURES, 3))}. Weight is {r.randint(90, 980)} g in the middle size.",
                    "Sizing": f"The {name} comes in sizes {low} to {low + 2 * r.randint(4, 7)}, in steps of two. It {r.choice(_FITS)}. Measure over the layers you plan to wear.",
                    "Care instructions": f"Wash the {name} {r.choice(_WASH)}. {r.choice(_DRY)}. Never use {r.choice(_NEVER)}.",
                    "Materials": f"The {name} is {share} percent {fabrics[0]} and {100 - share} percent {fabrics[1]}. The lining is free of fluorocarbons.",
                    "Warranty": f"The {name} has a {r.choice((2, 3, 5, 10))} year warranty that covers {r.choice(_COVER)} and {r.choice(_COVER)}. Normal wear is not covered.",
                },
            }
        )
    return out


def _pii(r) -> tuple[str, dict[str, int]]:
    """A pasted support note, and how many of each kind of personal data it holds."""
    counts = {"EMAIL": 0, "PHONE": 0, "IBAN": 0}
    lines = []
    for _ in range(r.randint(2, 4)):
        kind = r.choice(("EMAIL", "PHONE", "IBAN", "EMAIL", "PHONE"))
        counts[kind] += 1
        if kind == "EMAIL":
            address = f"{r.choice(('anna', 'erik', 'maja', 'j.smith', 'O.Taylor'))}.{r.choice(('berg', 'lind', 'jones', 'evans'))}{r.randint(1, 99)}@{r.choice(_EMAIL_DOMAINS)}"
            lines.append(f"Customer wrote from {address} about a broken zip.")
        elif kind == "PHONE":
            n = "".join(str(r.randrange(10)) for _ in range(7))
            phone = r.choice((f"+46 70 {n[:3]} {n[3:5]} {n[5:]}", f"070-{n[:3]} {n[3:5]} {n[5:]}", f"+44 7700 9{n[:5]}", f"0046 73{n}"))
            lines.append(f"Asked for a call back on {phone} after six.")
        else:
            digits = "".join(str(r.randrange(10)) for _ in range(20))
            iban = f"SE{digits[:2]}{digits[2:]}" if r.random() < 0.5 else f"SE{digits[:2]} {digits[2:6]} {digits[6:10]} {digits[10:14]} {digits[14:18]} {digits[18:]}"
            lines.append(f"Refund to be paid to {iban} as agreed.")
    return "\n".join(lines), counts


@lru_cache(maxsize=1)
def pasted() -> dict[str, tuple[str, dict[str, int]]]:
    """``doc_id -> (support note, counts)`` for the catalogue documents that had tickets pasted into them."""
    r = rng("pii")
    chosen = r.sample([p["doc_id"] for p in products()], WITH_PII)
    return {doc_id: _pii(r) for doc_id in sorted(chosen)}


def render(product: dict, note: str | None = None) -> str:
    front = "\n".join(f"{k}: {product[k]}" for k in ("doc_id", "title", "brand", "updated_at"))
    body = "\n\n".join(f"## {name}\n\n{text}" for name, text in product["sections"].items())
    extra = f"\n\n## Support notes\n\n{note}" if note else ""
    return f"---\n{front}\n---\n\n# {product['title']}\n\n{body}{extra}\n"


def write_catalogue(root: Path) -> dict[str, int]:
    """Write the catalogue to ``root`` (emptying it first). Returns the totals of pasted personal data."""
    root.mkdir(parents=True, exist_ok=True)
    for old in root.glob("PRD-*.md"):
        old.unlink()
    totals = {"documents_with_pii": 0, "EMAIL": 0, "PHONE": 0, "IBAN": 0}
    for product in products():
        note, counts = pasted().get(product["doc_id"], (None, {}))
        (root / f"{product['doc_id']}.md").write_text(render(product, note), encoding="utf-8")
        if note:
            totals["documents_with_pii"] += 1
            for kind, n in counts.items():
                totals[kind] += n
    return totals


def write_seeded(root: Path) -> dict[str, dict[str, int]]:
    """CAP-6.2: a dozen small documents with planted personal data, and how many of each kind each one has."""
    r = rng("seeded")
    root.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for i, product in enumerate(r.sample(products(), SEEDED), start=1):
        note, counts = _pii(r)
        name = f"seeded_{i:02d}.md"
        doc = {**product, "doc_id": f"SEED-{i:02d}", "sections": {k: product["sections"][k] for k in ("Overview", "Care instructions")}}
        (root / name).write_text(render(doc, note), encoding="utf-8")
        manifest[name] = counts
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def questions() -> list[dict]:
    """Support questions with the document (and section) that answers each."""
    r = rng("questions")
    out = []
    for i, product in enumerate(r.sample(products(), QUESTIONS), start=1):
        section = SECTIONS[i % len(SECTIONS)]
        text = r.choice(_QUESTION[section]).format(name=product["title"], activity=r.choice(_ACTIVITIES))
        out.append({"question_id": f"Q{i:03d}", "question": text, "relevant_doc_ids": [product["doc_id"]], "section": section})
    return out


def scenario(name: str) -> dict:
    """What a scenario changes: which documents, and which of their sections."""
    r = rng("scenario", name)
    ids = [p["doc_id"] for p in products()]
    if name == "delete_10_docs":
        return {"scenario": name, "deleted_doc_ids": sorted(r.sample(ids, DELETED))}
    if name == "edit_50_docs":
        chosen = sorted(r.sample(ids, EDITED))
        return {
            "scenario": name,
            "edited": [
                {"doc_id": d, "changed_sections": ["Care instructions"], "removed_sections": ["Warranty"] if i < REMOVED_SECTIONS else []}
                for i, d in enumerate(chosen)
            ],
        }
    raise ValueError(f"unknown scenario {name!r}; choose edit_50_docs or delete_10_docs")


def apply_scenario(root: Path, name: str) -> dict:
    """Change the catalogue in ``root`` the way the scenario says. Applying it twice changes nothing more."""
    plan = scenario(name)
    by_id = {p["doc_id"]: p for p in products()}
    for doc_id in plan.get("deleted_doc_ids", []):
        (root / f"{doc_id}.md").unlink(missing_ok=True)
    for edit in plan.get("edited", []):
        product = by_id[edit["doc_id"]]
        sections = dict(product["sections"])
        sections["Care instructions"] += " Updated advice: reproof after every fifth wash."
        for removed in edit["removed_sections"]:
            sections.pop(removed)
        changed = {**product, "updated_at": "2026-09-01T08:00:00Z", "sections": sections}
        note = pasted().get(product["doc_id"], (None, {}))[0]
        (root / f"{product['doc_id']}.md").write_text(render(changed, note), encoding="utf-8")
    return plan
