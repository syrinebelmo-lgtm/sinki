# -*- coding: utf-8 -*-
"""Boîtes, bars, pubs, karaoké OSM réels. Pas d’invention de lieux ni de tarifs."""

import os
import re
import time

from .categories import map_category, map_kind
from .france_hikes import in_metropolitan_france
from .france_places import SKIP_NAME
from .france_shopping import SHOP_HUBS, fetch_one, pin_city
from .quality import is_hotel_or_lodging, is_priced_place
from .run import load_env
from .supabase_io import fetch_all, to_outing_row, upsert_outings
from .switzerland import element_latlon, in_switzerland

SKIP_NIGHT = re.compile(
    r"\b(tabac|pmu|loto|betting|poney|équestre|equestre|mcdonald|hotel|hôtel)\b",
    re.I,
)

BLURB = {
    "nightclub": "Boîte de nuit.",
    "bar": "Bar.",
    "pub": "Pub.",
    "karaoke": "Karaoké.",
    "dance": "Dancing.",
    "biergarten": "Guinguette / biergarten.",
}


def night_types(tags):
    amenity = (tags.get("amenity") or "").strip().lower()
    leisure = (tags.get("leisure") or "").strip().lower()
    karaoke = (tags.get("karaoke") or "").strip().lower()
    bits = []
    if amenity == "nightclub" or leisure == "nightclub":
        bits.extend(["nightclub", "bar"])
    elif leisure == "dance":
        bits.extend(["nightclub", "dancing"])
    elif amenity == "karaoke_box" or karaoke in ("yes", "only"):
        bits.extend(["karaoke", "bar"])
    elif amenity == "pub":
        bits.extend(["pub", "bar"])
    elif amenity == "bar":
        bits.extend(["bar"])
    elif amenity == "biergarten":
        bits.extend(["bar", "pub"])
    return bits


def osm_to_night(el):
    tags = el.get("tags") or {}
    name = (tags.get("name:fr") or tags.get("name") or "").strip()
    if len(name) < 3 or SKIP_NAME.search(name) or SKIP_NIGHT.search(name):
        return None
    if is_hotel_or_lodging(list(tags.values())):
        return None
    types = night_types(tags)
    if not types:
        return None
    lat, lon = element_latlon(el)
    if lat is None:
        return None
    if not in_metropolitan_france(lat, lon) or in_switzerland(lat, lon):
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
    key = "nightclub"
    if "karaoke" in types:
        key = "karaoke"
    elif "dancing" in types:
        key = "dance"
    elif "pub" in types:
        key = "pub"
    elif "bar" in types:
        key = "bar"
    item = {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "price_min": 0.0,
        "price_max": 0.0,
        "currency": "EUR",
        "types": types,
        "kind": "place",
        "category": map_category(types, 0.0),
        "description": tags.get("description:fr") or tags.get("description") or BLURB.get(key, "Bar."),
        "address": addr or None,
        "photo_url": None,
        "photo_license": None,
        "website_url": website,
        "indoor": True,
        "source_name": "osm",
        "source_id": osm_id,
        "source_url": "https://www.openstreetmap.org/" + osm_id,
    }
    if item["category"] != "Soirées et concerts":
        item["category"] = "Soirées et concerts"
    if not is_priced_place(item):
        return None
    return item


def fetch_night_around(lat, lon, radius_m=12000):
    clubs = """
[out:json][timeout:90];
(
  nwr["amenity"="nightclub"]["name"](around:%s,%s,%s);
  nwr["leisure"="dance"]["name"](around:%s,%s,%s);
  nwr["amenity"="karaoke_box"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon)
    drinks = """
[out:json][timeout:90];
(
  nwr["amenity"="bar"]["name"](around:%s,%s,%s);
  nwr["amenity"="pub"]["name"](around:%s,%s,%s);
  nwr["amenity"="biergarten"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon)
    return fetch_one(clubs) + fetch_one(drinks)


def collect_elements(hubs, radius_m):
    seen = set()
    elements = []
    for name, lat, lon in hubs:
        chunk = fetch_night_around(lat, lon, radius_m)
        added = 0
        for el in chunk:
            key = (el.get("type"), el.get("id"))
            if key in seen:
                continue
            seen.add(key)
            elements.append(el)
            added += 1
        print("hub", name, "osm", len(chunk), "nouveaux", added, flush=True)
        time.sleep(2.2)
    print("osm nightlife unique", len(elements), flush=True)
    return elements


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--hub")
    parser.add_argument("--all-hubs", action="store_true")
    parser.add_argument("--radius-m", type=int, default=12000)
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
    featured = (
        "Paris",
        "Lyon",
        "Marseille",
        "Lille",
        "Toulouse",
        "Bordeaux",
        "Nantes",
        "Nice",
        "Strasbourg",
        "Montpellier",
        "Rennes",
    )
    hubs = [h for h in SHOP_HUBS if h[0] in featured]
    if args.all_hubs:
        hubs = SHOP_HUBS
    if args.hub:
        hubs = [h for h in SHOP_HUBS if h[0].lower() == args.hub.lower()]
        if not hubs:
            raise SystemExit("hub inconnu: " + args.hub)

    items = []
    for el in collect_elements(hubs, args.radius_m):
        item = osm_to_night(el)
        if item:
            items.append(item)
    print("convertis", len(items), flush=True)

    payload = []
    name_seen = set()
    skipped = 0
    clubs = 0
    for item in items:
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
        name_seen.add(geo)
        if "nightclub" in (item.get("types") or []):
            clubs += 1

    print("importables nightlife", len(payload), "boites", clubs, "ignorés", skipped, flush=True)
    if payload:
        upsert_outings(url, service_role, payload)
    print("terminé nightlife", len(payload), flush=True)


if __name__ == "__main__":
    main()
