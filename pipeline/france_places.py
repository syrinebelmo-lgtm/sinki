# -*- coding: utf-8 -*-
"""Parcs, musées, cinémas, salles OSM réels autour des villes trop vides. Pas d’invention."""

import os
import re
import time
import urllib.parse

from .categories import map_category, map_kind
from .france_hikes import in_metropolitan_france
from .france_shopping import SHOP_HUBS, fetch_one, pin_city
from .quality import is_hotel_or_lodging, is_priced_place
from .run import load_env
from .supabase_io import fetch_all, to_outing_row, upsert_outings
from .switzerland import element_latlon, in_switzerland

SPARSE_FIRST = (
    "Paris",
    "Lille",
    "Toulouse",
    "Bordeaux",
    "Nantes",
    "Strasbourg",
    "Nice",
    "Rennes",
    "Montpellier",
    "Rouen",
    "Reims",
    "Dijon",
    "Le Havre",
    "Tours",
    "Orléans",
    "Metz",
    "Nancy",
    "Clermont-Ferrand",
    "Angers",
    "Caen",
    "Amiens",
    "Brest",
    "Limoges",
    "Saint-Étienne",
    "Toulon",
    "Perpignan",
    "Avignon",
)

SKIP_NAME = re.compile(
    r"\b(parking|hôtel|hotel|motel|camping|residence|résidence|appartement)\b",
    re.I,
)


def place_types(tags):
    tourism = (tags.get("tourism") or "").strip().lower()
    leisure = (tags.get("leisure") or "").strip().lower()
    amenity = (tags.get("amenity") or "").strip().lower()
    bits = []
    if tourism in ("museum", "gallery"):
        bits.extend(["museum", "cultural"])
    elif tourism == "zoo":
        bits.extend(["zoo", "cultural"])
    elif leisure in ("park", "garden", "nature_reserve"):
        bits.extend(["park", "walk", "natural"])
    elif amenity in ("cinema", "theatre"):
        bits.extend(["concert", "showevent"])
    elif leisure in ("sports_centre", "stadium", "swimming_pool", "ice_rink"):
        bits.extend(["sport", "loisirs"])
    elif amenity == "community_centre":
        bits.extend(["loisirs"])
    return bits


def place_blurb(tags):
    tourism = (tags.get("tourism") or "").strip().lower()
    leisure = (tags.get("leisure") or "").strip().lower()
    amenity = (tags.get("amenity") or "").strip().lower()
    if tourism == "museum":
        return "Musée."
    if tourism == "gallery":
        return "Galerie."
    if tourism == "zoo":
        return "Zoo / parc animalier."
    if leisure in ("park", "garden"):
        return "Parc / jardin public."
    if amenity == "cinema":
        return "Cinéma."
    if amenity == "theatre":
        return "Théâtre."
    if leisure == "sports_centre":
        return "Complexe sportif."
    return "Lieu à visiter."


def osm_to_place(el):
    tags = el.get("tags") or {}
    name = (tags.get("name:fr") or tags.get("name") or "").strip()
    if len(name) < 3 or SKIP_NAME.search(name):
        return None
    if is_hotel_or_lodging(list(tags.values())):
        return None
    types = place_types(tags)
    if not types:
        return None
    lat, lon = element_latlon(el)
    if lat is None:
        return None
    if not in_metropolitan_france(lat, lon) or in_switzerland(lat, lon):
        return None
    fee = (tags.get("fee") or "").lower().strip()
    if fee in ("yes", "true") and not (tags.get("charge") or tags.get("charge:adult")):
        # musée payant sans tarif OSM : on n'invente pas le prix
        if "museum" not in types and "concert" not in types:
            return None
        return None
    website = tags.get("website") or tags.get("contact:website") or tags.get("url")
    addr = ", ".join(
        p
        for p in (
            tags.get("addr:street"),
            tags.get("addr:housenumber"),
            tags.get("addr:city") or tags.get("addr:place"),
        )
        if p
    )
    osm_id = "%s/%s" % (el.get("type"), el.get("id"))
    indoor = True
    if any(k in types for k in ("park", "walk", "natural")):
        indoor = False
    item = {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "price_min": 0.0,
        "price_max": 0.0,
        "currency": "EUR",
        "types": types,
        "kind": map_kind(types),
        "category": map_category(types, 0.0),
        "description": tags.get("description:fr") or tags.get("description") or place_blurb(tags),
        "address": addr or None,
        "photo_url": None,
        "photo_license": None,
        "website_url": website,
        "indoor": indoor,
        "source_name": "osm",
        "source_id": osm_id,
        "source_url": "https://www.openstreetmap.org/" + osm_id,
    }
    if item["category"] == "Shopping":
        return None
    if not is_priced_place(item):
        return None
    return item


def fetch_places_around(lat, lon, radius_m=16000):
    parks = """
[out:json][timeout:90];
(
  nwr["leisure"="park"]["name"](around:%s,%s,%s);
  nwr["leisure"="garden"]["name"](around:%s,%s,%s);
  nwr["leisure"="nature_reserve"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon)
    culture = """
[out:json][timeout:90];
(
  nwr["tourism"="museum"]["name"](around:%s,%s,%s);
  nwr["tourism"="gallery"]["name"](around:%s,%s,%s);
  nwr["tourism"="zoo"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon)
    soiree = """
[out:json][timeout:90];
(
  nwr["amenity"="cinema"]["name"](around:%s,%s,%s);
  nwr["amenity"="theatre"]["name"](around:%s,%s,%s);
  nwr["leisure"="sports_centre"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon)
    return fetch_one(parks) + fetch_one(culture) + fetch_one(soiree)


def collect_elements(hubs, radius_m):
    seen = set()
    elements = []
    for name, lat, lon in hubs:
        chunk = fetch_places_around(lat, lon, radius_m)
        added = 0
        for el in chunk:
            key = (el.get("type"), el.get("id"))
            if key in seen:
                continue
            seen.add(key)
            elements.append(el)
            added += 1
        print("hub", name, "osm", len(chunk), "nouveaux", added, flush=True)
        time.sleep(2.4)
    print("osm lieux unique", len(elements), flush=True)
    return elements


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--hub")
    parser.add_argument("--all-hubs", action="store_true")
    parser.add_argument("--radius-m", type=int, default=16000)
    args = parser.parse_args()

    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    cities = fetch_all(
        url,
        service_role,
        "cities",
        "id,slug,name,latitude,longitude,country_code",
        extra="&country_code=eq.FR",
    )
    cities = [row for row in cities if row.get("latitude") is not None]
    print("villes FR", len(cities), flush=True)

    hubs = [h for h in SHOP_HUBS if h[0] in SPARSE_FIRST]
    if args.all_hubs:
        hubs = SHOP_HUBS
    if args.hub:
        hubs = [h for h in SHOP_HUBS if h[0].lower() == args.hub.lower()]
        if not hubs:
            raise SystemExit("hub inconnu: " + args.hub)

    items = []
    for el in collect_elements(hubs, args.radius_m):
        item = osm_to_place(el)
        if item:
            items.append(item)
    print("convertis", len(items), flush=True)

    existing_rows = fetch_all(
        url,
        service_role,
        "outings",
        "id,source_name,source_id",
        extra="&source_name=eq.osm",
    )
    existing = set()
    for row in existing_rows:
        if row.get("source_id"):
            existing.add((row.get("source_name"), row["source_id"]))

    payload = []
    name_seen = set()
    skipped = 0
    by_cat = {}
    for item in items:
        if (item["source_name"], item["source_id"]) in existing:
            skipped += 1
            continue
        nk = re.sub(r"[^a-z0-9]+", " ", (item["name"] or "").lower()).strip()
        geo = (round(item["latitude"], 3), round(item["longitude"], 3), nk)
        if geo in name_seen:
            skipped += 1
            continue
        city = pin_city(item["latitude"], item["longitude"], cities)
        if not city or (city.get("country_code") or "") != "FR":
            skipped += 1
            continue
        row = to_outing_row(item, city["id"])
        if not row:
            skipped += 1
            continue
        row["currency"] = "EUR"
        payload.append(row)
        existing.add((item["source_name"], item["source_id"]))
        name_seen.add(geo)
        by_cat[row["category"]] = by_cat.get(row["category"], 0) + 1

    print("importables lieux", len(payload), "ignorés", skipped, "par cat", by_cat, flush=True)
    if payload:
        upsert_outings(url, service_role, payload)
    print("terminé lieux", len(payload), flush=True)


if __name__ == "__main__":
    main()
