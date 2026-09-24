# -*- coding: utf-8 -*-
"""Vérifie catégorie / budget France : nom, lieu, service. Shopping = tout budget."""

import json
import os
import re
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict

from .run import load_env
from .supabase_io import fetch_all

RESTO_DU_COEUR = re.compile(
    r"restos?\s+du\s+c[oeœ]ur|restaurants?\s+du\s+c[oeœ]ur",
    re.I,
)
RESTO_RE = re.compile(
    r"\b(restaurant|brasserie|bistrot|bistro|pizzeria|cr[eê]perie|kebab|"
    r"trattoria|taverne|auberge(?!\s+de\s+jeunesse)|grill|wok|sushi|"
    r"burger\s?king|mcdonald|starbucks)\b",
    re.I,
)
SHOP_RE = re.compile(
    r"\b(friperie|friperies|frip'|d[eé]p[oô]t[-\s]?vente|kilo\s?shop|"
    r"centre commercial|centres commerciaux|galerie marchande|galerie commerciale|"
    r"shopping mall|grand magasin|westfield|"
    r"hema|primark|kiabi|uniqlo|ikea|fnac|gifi|"
    r"h\s?&\s?m|zara|pull\s?&\s?bear|bershka|stradivarius|"
    r"seconde\s+main)\b",
    re.I,
)
NOT_SHOP_RE = re.compile(
    r"\b(restaurant|brasserie|bistrot|hippopotamus|courtepaille|ninkasi|"
    r"bar |caf[eé]|match |arena|stade|location de|action game|action aventure|"
    r"equicoaching|jazz|th[eé][aâ]tre)\b",
    re.I,
)
DECATHLON_STORE = re.compile(r"\bdecathlon\b", re.I)
MUSEUM_RE = re.compile(
    r"\b(mus[eé]e|museum|galerie d['’]art|fondation [a-z].{0,20}(art|mus[eé]e))\b",
    re.I,
)
PARK_RE = re.compile(
    r"\b(parc |jardin |promenade |square |esplanade )\b",
    re.I,
)
RANDO_RE = re.compile(
    r"\b(randonn[eé]e|sentier|col de |pic de |sommet|via ferrata)\b",
    re.I,
)
NIGHT_RE = re.compile(
    r"\b(bo[iî]te de nuit|nightclub|discoth[eè]que|karaoke|karaok[eé])\b",
    re.I,
)
SHOW_RE = re.compile(
    r"\b(concert|op[eé]ra|ballet|cin[eé]ma|cinema|th[eé][aâ]tre|theatre|cabaret|jazz)\b",
    re.I,
)
SHOW_BUT_DRINK = re.compile(
    r"\b(bar|pub|caf[eé]|comptoir|brasserie|c[aà]\s*ph[eê]|coffee)\b",
    re.I,
)
SKIP_PARK = re.compile(r"\b(parking|parc auto|parc relais|acrobatique|accrobranche|aventure)\b", re.I)

CAT_RESTO = "Restaurants et cafés"
CAT_SHOP = "Shopping"
CAT_CULT = "Musées et culture"
CAT_BALADE = "Lieux gratuits et balades"
CAT_RANDO = "Randonnées"
CAT_SOIREE = "Soirées et concerts"
CAT_LOISIR = "Activités et loisirs"


def fold(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def suggest(row):
    kind = row.get("kind") or ""
    cat = row.get("category") or ""
    name = row.get("name") or ""
    folded = fold(name)
    try:
        pmin = float(row["price_min"]) if row.get("price_min") is not None else None
    except (TypeError, ValueError):
        pmin = None

    if kind == "event" or cat == "Événements temporaires":
        if cat == CAT_SHOP:
            return "Événements temporaires", "event_keep"
        return None, None

    if RESTO_DU_COEUR.search(name) or "restos du coeur" in folded or "restaurant du coeur" in folded:
        return CAT_SHOP, "charity_shop"

    if cat == CAT_RANDO:
        return None, None

    if cat == "Balades et plein air":
        return CAT_BALADE, "legacy_balade"

    if DECATHLON_STORE.search(name) and not NOT_SHOP_RE.search(name):
        return CAT_SHOP, "shop_name"
    if SHOP_RE.search(name) and not NOT_SHOP_RE.search(name) and not RESTO_RE.search(name):
        return CAT_SHOP, "shop_name"
    if RESTO_RE.search(name):
        if cat != CAT_RESTO:
            return CAT_RESTO, "resto_name"
        return None, None
    if MUSEUM_RE.search(name) and cat not in (CAT_CULT, CAT_SHOP):
        return CAT_CULT, "museum_name"
    if SHOW_RE.search(name) and cat not in (CAT_CULT, CAT_SHOP) and "musée" not in folded:
        if not NIGHT_RE.search(name) and not SHOW_BUT_DRINK.search(name):
            return CAT_CULT, "show_name"
    if NIGHT_RE.search(name) and cat not in (CAT_SOIREE, CAT_CULT) and "musée" not in folded:
        return CAT_SOIREE, "night_name"
    if (
        PARK_RE.search(name)
        and not SKIP_PARK.search(name)
        and pmin == 0
        and cat not in (CAT_BALADE, CAT_RANDO, CAT_CULT)
        and not SHOP_RE.search(name)
        and not RESTO_RE.search(name)
    ):
        return CAT_BALADE, "park_name"
    if RANDO_RE.search(name) and cat not in (CAT_RANDO, CAT_BALADE) and pmin == 0:
        return CAT_RANDO, "rando_name"
    return None, None


def patch_chunk(url, service_role, ids, body):
    headers = {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    for i in range(0, len(ids), 40):
        chunk = ids[i : i + 40]
        q = url.rstrip("/") + "/rest/v1/outings?id=in.(" + ",".join(chunk) + ")"
        req = urllib.request.Request(
            q,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        time.sleep(0.05)


def recategorize_world(url, service_role):
    from .france_nightlife import recategorize_world as move_shows

    return move_shows(url, service_role)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--world", action="store_true", help="Recatégorise concerts / ciné / écoles de danse partout")
    args = parser.parse_args()

    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = (os.environ.get("SUPABASE_SERVICE_ROLE") or "").strip().split()[0]
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")
    if args.world:
        moved = recategorize_world(url, service_role)
        print("terminé recategorize world", moved, flush=True)
        return

    rows = fetch_all(
        url,
        service_role,
        "outings",
        "id,name,kind,category,price_min,price_max,city_id,latitude,longitude",
        extra="&is_active=eq.true",
    )
    print("sorties actives", len(rows), flush=True)

    by_cat = Counter((r.get("category") or "?") for r in rows)
    print("avant", dict(by_cat), flush=True)

    shop_price = [
        r["id"]
        for r in rows
        if (r.get("category") or "") == CAT_SHOP
        and (
            (r.get("price_min") is not None and float(r["price_min"]) != 0)
            or (r.get("price_max") is not None and float(r["price_max"]) != 0)
        )
    ]
    # Annule les faux shopping (restos Part-Dieu, Action Game, Decathlon Arena…).
    undo_shop = []
    for r in rows:
        if (r.get("category") or "") != CAT_SHOP:
            continue
        name = r.get("name") or ""
        if RESTO_DU_COEUR.search(name) or "restaurant du coeur" in fold(name):
            continue
        if NOT_SHOP_RE.search(name) or RESTO_RE.search(name):
            undo_shop.append(r)
    print("faux shopping à retirer", len(undo_shop), [x.get("name") for x in undo_shop[:12]], flush=True)
    for r in undo_shop:
        name = r.get("name") or ""
        if RESTO_RE.search(name) or re.search(r"\b(hippopotamus|courtepaille|ninkasi|ciao nonna)\b", name, re.I):
            dst = CAT_RESTO
        elif re.search(r"\b(match |arena|stade)\b", name, re.I):
            dst = CAT_SOIREE
        elif re.search(r"\bth[eé][aâ]tre\b", name, re.I):
            dst = CAT_CULT
        else:
            dst = CAT_LOISIR
        if dst != CAT_SHOP:
            patch_chunk(url, service_role, [r["id"]], {"category": dst})

    print("shopping prix à remettre à 0", len(shop_price), flush=True)
    if shop_price:
        patch_chunk(url, service_role, shop_price, {"price_min": 0, "price_max": 0, "currency": "EUR"})

    moves = defaultdict(list)
    reasons = Counter()
    samples = defaultdict(list)
    for row in rows:
        target, why = suggest(row)
        if not target or target == row.get("category"):
            continue
        key = (row.get("category") or "?", target)
        moves[key].append(row["id"])
        reasons[why] += 1
        if len(samples[key]) < 8:
            samples[key].append(row.get("name"))

    for key, ids in sorted(moves.items(), key=lambda x: -len(x[1])):
        src, dst = key
        print("reclass", src, "->", dst, len(ids), "ex:", samples[key], flush=True)
        patch_chunk(url, service_role, ids, {"category": dst})

    print("raisons", dict(reasons), flush=True)

    after = fetch_all(
        url,
        service_role,
        "outings",
        "id,category,city_id,price_min",
        extra="&is_active=eq.true",
    )
    print("après cats", dict(Counter((r.get("category") or "?") for r in after)), flush=True)

    cities = {c["id"]: c.get("name") for c in fetch_all(url, service_role, "cities", "id,name", extra="&country_code=eq.FR")}
    sparse = ("Paris", "Lille", "Toulouse", "Bordeaux", "Nantes", "Strasbourg", "Nice", "Rennes")
    want = {n for n in sparse}
    by_city_cat = defaultdict(Counter)
    for row in after:
        name = cities.get(row.get("city_id"))
        if name in want:
            by_city_cat[name][(row.get("category") or "?")] += 1
    for name in sparse:
        print("ville", name, dict(by_city_cat.get(name) or {}), "total", sum((by_city_cat.get(name) or {}).values()), flush=True)
    print("terminé recategorize", flush=True)


if __name__ == "__main__":
    main()
