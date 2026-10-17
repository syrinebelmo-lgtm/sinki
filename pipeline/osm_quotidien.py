# -*- coding: utf-8 -*-
"""Sorties du quotidien (OpenStreetMap) pour les pays peu couverts.

Restaurants, cafés, bars, clubs, glaciers, parcs, plages, points de vue, sports
et loisirs dans les plus grandes villes de chaque pays. Aucune donnée inventée :
pas de photo si OSM n'en relie pas, prix seulement si OSM l'indique (fee/charge),
sinon « prix à confirmer ».

    python3 pipeline/osm_quotidien.py --countries=PE,QA [--dry]
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import international_wikidata as w  # noqa: E402

KM = 6  # rayon autour du centre-ville
SERVERS = ("https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter")

# (filtre OSM, catégorie, kind, description, max gardés par ville)
GROUPS = [
    ('["amenity"="restaurant"]', "Restaurants et cafés", "restaurant", "Restaurant", 90),
    ('["amenity"="cafe"]', "Restaurants et cafés", "restaurant", "Café", 40),
    ('["amenity"="fast_food"]', "Restaurants et cafés", "restaurant", "Restauration rapide", 25),
    ('["amenity"="ice_cream"]', "Restaurants et cafés", "restaurant", "Glacier", 15),
    ('["amenity"~"^(bar|pub|biergarten)$"]', "Soirées et concerts", "place", "Bar", 40),
    ('["amenity"="nightclub"]', "Soirées et concerts", "place", "Boîte de nuit", 25),
    ('["amenity"~"^(cinema|theatre|arts_centre)$"]', "Musées et culture", "place", "Culture", 25),
    ('["tourism"~"^(museum|gallery)$"]', "Musées et culture", "place", "Musée", 30),
    ('["leisure"~"^(park|garden)$"]', "Lieux gratuits et balades", "walk", "Parc", 30),
    ('["natural"="beach"]', "Lieux gratuits et balades", "walk", "Plage", 20),
    ('["tourism"="viewpoint"]', "Lieux gratuits et balades", "walk", "Point de vue", 15),
    ('["leisure"~"^(water_park|bowling_alley|escape_game|miniature_golf|ice_rink|amusement_arcade|trampoline_park)$"]',
     "Activités et loisirs", "place", "Loisirs", 30),
    ('["tourism"~"^(zoo|aquarium|theme_park)$"]', "Activités et loisirs", "place", "Parc de loisirs", 10),
    ('["leisure"="sports_centre"]["access"!="private"]', "Activités et loisirs", "place", "Centre sportif", 15),
    ('["shop"~"^(mall|department_store)$"]', "Shopping", "place", "Centre commercial", 15),
    ('["amenity"="marketplace"]', "Shopping", "place", "Marché", 15),
]

CUISINE_FR = {
    "pizza": "pizza", "burger": "burgers", "chicken": "poulet", "coffee_shop": "café", "chinese": "chinoise",
    "italian": "italienne", "indian": "indienne", "japanese": "japonaise", "sushi": "sushi", "mexican": "mexicaine",
    "seafood": "fruits de mer", "regional": "locale", "local": "locale", "thai": "thaï", "lebanese": "libanaise",
    "turkish": "turque", "arab": "arabe", "kebab": "kebab", "french": "française", "asian": "asiatique",
    "vegetarian": "végétarienne", "vegan": "végane", "steak_house": "grillades", "bbq": "barbecue",
    "peruvian": "péruvienne", "korean": "coréenne", "vietnamese": "vietnamienne", "american": "américaine",
    "ice_cream": "glaces", "sandwich": "sandwichs", "breakfast": "petit-déjeuner", "cake": "pâtisserie",
}
SKIP = re.compile(r"\b(hotel|h[oô]tel|hostel|motel|resort|lodge|guest ?house|inn|private|staff|canteen|cantine|"
                  r"military|army|embassy|kfc|mcdonald|burger king|subway|domino|pizza hut|starbucks)\b", re.I)


def query(lat, lon):
    import math
    dlat = KM / 111.0
    dlon = KM / (111.0 * max(0.2, math.cos(math.radians(lat))))
    bb = "%f,%f,%f,%f" % (lat - dlat, lon - dlon, lat + dlat, lon + dlon)
    body = "".join(" nwr%s[\"name\"](%s);\n" % (f, bb) for f, *_ in GROUPS)
    q = "[out:json][timeout:180];\n(\n%s);\nout center tags 6000;" % body
    for attempt in range(9):
        url = SERVERS[(attempt + int(os.environ.get("SINKI_SERVER", "0"))) % len(SERVERS)]
        try:
            # curl: le Python système est trop ancien pour le TLS d'overpass-api.de
            out = subprocess.run(["curl", "-sS", "-m", "240", "-A", w.UA["User-Agent"], "--data-urlencode", "data@-", url],
                                 input=q.encode(), capture_output=True, timeout=260).stdout
            if not out.lstrip().startswith(b"{"):
                raise ValueError(out[:80])
            return json.loads(out, strict=False)["elements"]
        except Exception as exc:
            print("   overpass", url.split("/")[2], type(exc).__name__, str(exc)[:60], flush=True)
            time.sleep(15 * (attempt + 1))
    raise RuntimeError("overpass indisponible")


def matches(tags, flt):
    for k, op, v in re.findall(r'\["([^"]+)"(=|~|!=)"([^"]+)"\]', flt):
        val = tags.get(k) or ""
        if op == "=" and val != v or op == "~" and not re.search(v, val) or op == "!=" and val == v:
            return False
    return True


def key_of(name):
    # norm() ne garde que l'alphabet latin : écritures persane, arabe, chinoise…
    return w.norm(name) or re.sub(r"\s+", " ", (name or "").strip().lower())


def richness(tags):
    return sum(1 for k in ("website", "contact:website", "opening_hours", "phone", "contact:phone",
                           "cuisine", "addr:street", "wikidata", "image") if tags.get(k))


def describe(base, tags):
    bits = [base]
    cui = [CUISINE_FR.get(c.strip(), None) for c in (tags.get("cuisine") or "").split(";")]
    cui = [c for c in cui if c]
    if cui:
        bits.append("cuisine " + ", ".join(dict.fromkeys(cui)))
    if tags.get("outdoor_seating") == "yes":
        bits.append("terrasse")
    return " · ".join(bits) + "."


def build(city, elements, cc, known):
    now = datetime.now(timezone.utc).isoformat()
    buckets = {i: [] for i in range(len(GROUPS))}
    for el in elements:
        tags = el.get("tags") or {}
        for i, g in enumerate(GROUPS):
            if matches(tags, g[0]):
                buckets[i].append(el)
                break
    rows, seen = [], set(known)
    for i, (flt, cat, kind, base, cap) in enumerate(GROUPS):
        kept = 0
        for el in sorted(buckets[i], key=lambda e: -richness(e.get("tags") or {})):
            if kept >= cap:
                break
            tags = el.get("tags") or {}
            name = (tags.get("name:fr") or tags.get("name:en") or tags.get("name") or "").strip()
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if (not name or lat is None or len(name) < 2 or w.GENERIC.match(name) or w.SKIP_NAME.search(name)
                    or SKIP.search(name) or tags.get("disused") or tags.get("access") in ("private", "no")
                    or tags.get("tourism") == "hotel"):
                continue
            k = key_of(name)
            if not k or k in seen:
                continue
            seen.add(k)
            kept += 1
            pmin, pmax = w.price(tags, cc)
            osm_id = "%s/%s" % (el.get("type"), el.get("id"))
            rows.append({
                "id": str(uuid.uuid5(w.NS, "local:" + osm_id)),  # jamais l'id d'une ligne existante
                "city_id": city["id"], "kind": kind, "category": cat,
                "name": name[:200], "description": describe(base, tags)[:500],
                "address": w.address(tags), "latitude": lat, "longitude": lon,
                "price_min": pmin, "price_max": pmax, "currency": w.CURRENCY.get(cc, "EUR"),
                "indoor": False if kind == "walk" else (True if cat in ("Musées et culture", "Shopping") else None),
                "vibes": [], "transport_modes": [],
                "opening_hours": {"osm": tags["opening_hours"]} if tags.get("opening_hours") else {},
                "website_url": tags.get("website") or tags.get("contact:website"),
                "photo_url": None, "photo_license": None, "photo_credit": None,
                "source_name": "osm_local", "source_id": "osm:" + osm_id,
                "source_url": "https://www.openstreetmap.org/" + osm_id,
                "is_active": True, "verified_at": now,
            })
    return rows


def all_names(url, key, city_id):
    names, offset = set(), 0
    while True:
        q = "%s/rest/v1/outings?select=name&city_id=eq.%s&order=id&limit=1000&offset=%d" % (url, city_id, offset)
        rows = w.http_json(q, headers={"apikey": key, "Authorization": "Bearer " + key})
        names.update(key_of(r.get("name")) for r in rows)
        if len(rows) < 1000:
            return names
        offset += 1000


def done_cities(log_path):
    out = set()
    if os.path.exists(log_path):
        for line in open(log_path):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("mode") == "osm_local" and not d.get("dry"):
                out.add(d["city_id"])
    return out


def main(argv):
    dry = "--dry" in argv
    only = [a.split("=", 1)[1] for a in argv if a.startswith("--countries=")]
    wanted = only[0].split(",") if only else []
    url, key = w.env()
    by = w.local_cities()
    log_path = os.path.expanduser("~/sinki-sauvegardes/migration/enrichissement_osm_local.jsonl")
    done = done_cities(log_path)
    log = open(log_path, "a")
    total = 0
    for cc in wanted:
        if cc not in by:
            print(cc, "aucune ville dans la base", flush=True)
            continue
        try:
            centers = w.EXTRA_CENTERS.get(cc) or w.biggest_cities(cc)
        except Exception as exc:
            print(cc, "villes introuvables:", type(exc).__name__, flush=True)
            continue
        used = set()
        for lat, lon in centers:
            city = min(by[cc], key=lambda c: (c["latitude"] - lat) ** 2 + (c["longitude"] - lon) ** 2)
            if w.dist_km((lat, lon), (city["latitude"], city["longitude"])) > 15 or city["id"] in used:
                continue
            used.add(city["id"])
            if city["id"] in done:
                print(cc, city["name"], "déjà faite", flush=True)
                continue
            try:
                els = query(lat, lon)
                known = set() if dry else all_names(url, key, city["id"])
                rows = build(city, els, cc, known)
            except Exception as exc:
                print(cc, city["name"], "erreur, ville sautée:", type(exc).__name__, flush=True)
                continue
            cats = {}
            for r in rows:
                cats[r["category"]] = cats.get(r["category"], 0) + 1
            print("%s %-24s OSM %5d -> nouveaux %4d %s" % (cc, city["name"], len(els), len(rows), cats), flush=True)
            if dry:
                with open(os.path.expanduser("~/sinki-sauvegardes/migration/simulation_osm_%s.jsonl" % cc), "a") as out:
                    for r in rows:
                        out.write(json.dumps(r, ensure_ascii=False) + "\n")
            elif rows:
                w.upsert(url, key, rows)
            log.write(json.dumps({"cc": cc, "city": city["name"], "city_id": city["id"], "new": len(rows),
                                  "mode": "osm_local", "dry": dry}) + "\n")
            log.flush()
            total += len(rows)
            time.sleep(3)
    print("TOTAL nouveaux lieux:", total, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
