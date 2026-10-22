"""Customers of both brands, and who is the same person.

The generator starts from people. A person is a Fernhill customer, a Skarvik customer or both; the records
of someone who is both differ the way real records do (letter case, spaces, phone formats, a second email
address). ``golden/customer_matches.csv`` says which records belong to which person.
"""

from __future__ import annotations

from functools import lru_cache

from .common import rng

FERNHILL_ONLY = 5400
SKARVIK_ONLY = 4400
BOTH = 600  # 12% of Skarvik's 5,000 customers
HOUSEHOLDS = 40  # two different people, one phone, different surnames
SAME_NATIONAL_NUMBER = 25  # two different people, same surname, same digits in different countries

DIAL = {"GB": "+44", "IE": "+353", "SE": "+46", "NO": "+47", "DK": "+45", "FI": "+358", "DE": "+49", "US": "+1"}
EU = ("IE", "SE", "DK", "FI", "DE")
_FERNHILL_COUNTRIES = ("GB", "GB", "GB", "GB", "IE", "DE", "US")
_SKARVIK_COUNTRIES = ("SE", "SE", "SE", "SE", "NO", "DK", "FI")
_GIVEN = ("Anna", "Erik", "Maja", "Lars", "Ingrid", "Oskar", "Freja", "Nils", "Elsa", "Johan", "Sara", "Emil",
          "Olivia", "Harry", "Amelia", "George", "Isla", "Noah", "Ava", "Leo", "Mia", "Arthur", "Ella", "Oscar")  # fmt: skip
_FAMILY = ("Berg", "Lind", "Holm", "Dahl", "Nyman", "Strand", "Lund", "Hedlund", "Sandberg", "Ekman", "Falk",
           "Smith", "Jones", "Taylor", "Brown", "Wilson", "Evans", "Walker", "Wright", "Hughes", "Green", "Hall")  # fmt: skip
_DOMAINS = ("example.com", "example.org", "mail.example", "post.example", "work.example")
_TIERS = ("bronze", "bronze", "bronze", "silver", "silver", "gold")


def e164(country: str, national: str) -> str:
    return DIAL[country] + national


def _formatted(r, country: str, national: str) -> str:
    """The same number the way a person types it."""
    style = r.randrange(4)
    if style == 0:
        return e164(country, national)
    if style == 1:
        return f"{DIAL[country]} {national[:2]} {national[2:5]} {national[5:]}"
    if style == 2:
        return f"0{national[:2]}-{national[2:5]} {national[5:]}"  # national format: needs the country to resolve
    return f"00{DIAL[country][1:]}{national}"


def _messy(r, email: str) -> str:
    style = r.randrange(4)
    if style == 0:
        return email
    if style == 1:
        return email.upper()
    if style == 2:
        return f" {email.title()} "
    return email.replace("@", "@").capitalize() + " "


@lru_cache(maxsize=1)
def build() -> dict[str, list[dict]]:
    """``{"fernhill": [...], "skarvik": [...], "truth": [...]}``. ``truth`` has one row per customer record
    with the person it belongs to."""
    r = rng("people")
    fernhill: list[dict] = []
    skarvik: list[dict] = []
    truth: list[dict] = []
    used_national: set[str] = set()

    def national() -> str:
        while True:
            n = "7" + "".join(str(r.randrange(10)) for _ in range(8))
            if n not in used_national:
                used_national.add(n)
                return n

    def person(i: int, countries) -> dict:
        given, family = r.choice(_GIVEN), r.choice(_FAMILY)
        return {
            "person_id": f"P{i:06d}",
            "given": given,
            "family": family,
            "email": f"{given}.{family}{i}@{r.choice(_DOMAINS)}".lower(),
            "country": r.choice(countries),
            "national": national(),
        }

    def add_fernhill(p: dict, email: str | None = None, phone: str | None = None) -> dict:
        row = {
            "customer_id": 100000 + len(fernhill),
            "email": email if email is not None else p["email"],
            "phone": phone if phone is not None else _formatted(r, p["country"], p["national"]),
            "full_name": f"{p['given']} {p['family']}",
            "country": p["country"],
            "tier": r.choice(_TIERS),
            "updated_at": f"2026-05-{r.randint(1, 28):02d}T{r.randint(0, 23):02d}:{r.randint(0, 59):02d}:00Z",
        }
        fernhill.append(row)
        truth.append({"brand": "fernhill", "source_id": str(row["customer_id"]), "person_id": p["person_id"]})
        return row

    def add_skarvik(p: dict, email: str | None = None, phone: str | None = None, country: str | None = None) -> dict:
        row = {
            "kund_id": f"K{500000 + len(skarvik)}",
            "epost": email if email is not None else p["email"],
            "telefon": phone if phone is not None else _formatted(r, country or p["country"], p["national"]),
            "namn": f"{p['given']} {p['family']}",
            "land": country or p["country"],
            "uppdaterad": f"2026-05-{r.randint(1, 28):02d} {r.randint(0, 23):02d}:{r.randint(0, 59):02d}:00",
        }
        skarvik.append(row)
        truth.append({"brand": "skarvik", "source_id": row["kund_id"], "person_id": p["person_id"]})
        return row

    n = 0
    for _ in range(FERNHILL_ONLY - HOUSEHOLDS - SAME_NATIONAL_NUMBER):
        n += 1
        add_fernhill(person(n, _FERNHILL_COUNTRIES))
    for _ in range(SKARVIK_ONLY - HOUSEHOLDS - SAME_NATIONAL_NUMBER):
        n += 1
        add_skarvik(person(n, _SKARVIK_COUNTRIES))
    # The same person at both brands. Living in one country, so the phone number is the same number.
    for i in range(BOTH):
        n += 1
        p = person(n, _SKARVIK_COUNTRIES)
        how = i % 100
        other_email = f"{p['given'][0]}{p['family']}{n}@{r.choice(_DOMAINS)}".lower()
        if how < 70:  # same address, typed differently; a different phone on file
            add_fernhill(p, email=_messy(r, p["email"]), phone=_formatted(r, p["country"], national()))
            add_skarvik(p, email=_messy(r, p["email"]))
        elif how < 90:  # different addresses, the same phone in different formats
            add_fernhill(p, email=other_email)
            add_skarvik(p)
        elif how < 97:  # both the same
            add_fernhill(p, email=_messy(r, p["email"]))
            add_skarvik(p, email=_messy(r, p["email"]))
        else:  # nothing in common but the name: cannot be matched safely
            add_fernhill(p, email=other_email, phone=_formatted(r, p["country"], national()))
            add_skarvik(p)
    # Different people who look alike.
    for _ in range(HOUSEHOLDS):  # partners sharing a phone: different surnames, different addresses
        n += 1
        a = person(n, _SKARVIK_COUNTRIES)
        n += 1
        b = person(n, _SKARVIK_COUNTRIES)
        while b["family"] == a["family"]:
            b["family"] = r.choice(_FAMILY)
        b.update(country=a["country"], national=a["national"])
        add_fernhill(a)
        add_skarvik(b)
    for _ in range(SAME_NATIONAL_NUMBER):  # same surname, same digits, different country codes
        n += 1
        a = person(n, ("GB",))
        n += 1
        b = person(n, ("SE", "NO"))
        b.update(family=a["family"], national=a["national"])
        add_fernhill(a, phone=f"0{a['national'][:2]}-{a['national'][2:5]} {a['national'][5:]}")
        add_skarvik(b, phone=f"0{b['national'][:2]}-{b['national'][2:5]} {b['national'][5:]}")
    order = rng("people-order")
    order.shuffle(fernhill)
    order.shuffle(skarvik)
    truth.sort(key=lambda t: (t["brand"], t["source_id"]))
    return {"fernhill": fernhill, "skarvik": skarvik, "truth": truth}


FERNHILL_COLUMNS = ["customer_id", "email", "phone", "full_name", "country", "tier", "updated_at"]
SKARVIK_COLUMNS = ["kund_id", "epost", "telefon", "namn", "land", "uppdaterad"]
TRUTH_COLUMNS = ["brand", "source_id", "person_id"]
