# -*- coding: utf-8 -*-
"""Belgique : villes + POI OSM avec tarif déclaré (0 € si gratuit). Pas d’invention."""

import json
import os
import re
import time
import urllib.request

from .categories import map_category, map_kind
from .france_hikes import in_metropolitan_france
from .france_shopping import fetch_one
from .quality import is_hotel_or_lodging, is_priced_place
from .run import load_env
from .supabase_io import fetch_all, to_outing_row, upsert_outings
from .switzerland import (
    HOTEL_TOURISM,
    element_latlon,
    is_hike,
    osm_types,
    parse_price,
)

BE_CITIES = [
    ("Bruxelles", "bruxelles", 50.8503, 4.3517),
    ("Anvers", "anvers", 51.2194, 4.4025),
    ("Gand", "gand", 51.0543, 3.7174),
    ("Liège", "liege", 50.6326, 5.5797),
    ("Bruges", "bruges", 51.2093, 3.2247),
    ("Charleroi", "charleroi-be", 50.4108, 4.4446),
    ("Namur", "namur", 50.4674, 4.8718),
    ("Louvain", "louvain", 50.8798, 4.7005),
    ("Mons", "mons-be", 50.4542, 3.9523),
    ("Ostende", "ostende", 51.2154, 2.9286),
]


def in_belgium(lat, lon):
    if not (49.45 <= lat <= 51.55 and 2.52 <= lon <= 6.42):
        return False
    # Lille / Nord-Pas-de-Calais
    if lon < 3.18 and lat < 50.82:
        return False
    if in_metropolitan_france(lat, lon) and lon < 3.25 and lat < 50.85:
        return False
    return True


def upsert_be_cities(url, service_role):
    existing = {
        row["slug"]: row
        for row in fetch_all(url, service_role, "cities", "id,slug,name,country_code,latitude,longitude")
    }
    created = []
    headers = {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    for name, slug, lat, lon in BE_CITIES:
        prev = existing.get(slug)
        if prev and prev.get("country_code") == "BE":
            created.append(prev)
            continue
        body = json.dumps(
            {
                "name": name,
                "slug": slug,
                "country_code": "BE",
                "latitude": lat,
                "longitude": lon,
                "is_active": True,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/cities?on_conflict=slug",
            data=body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            rows = json.loads(resp.read().decode() or "[]")
        row = rows[0] if rows else {"slug": slug, "name": name, "latitude": lat, "longitude": lon, "country_code": "BE"}
        created.append(row)
        existing[slug] = row
        print("ville", name, flush=True)
    return created


def osm_to_item(el):
    tags = el.get("tags") or {}
    name = (tags.get("name:fr") or tags.get("name:nl") or tags.get("name") or "").strip()
    if len(name) < 3:
        return None
    if (tags.get("tourism") or "") in HOTEL_TOURISM:
        return None
    if is_hotel_or_lodging(list(tags.values())):
        return None
    lat, lon = element_latlon(el)
    if lat is None or not in_belgium(lat, lon):
        return None
    country = (tags.get("addr:country") or tags.get("addr:countrycode") or "").upper()
    if country in ("FR", "FRA", "NL", "NLD", "DE", "DEU", "LU", "LUX"):
        return None
    parsed = parse_price(tags)
    if parsed is None:
        return None
    price_min, price_max, currency = parsed
    if currency == "CHF":
        currency = "EUR"
    types = osm_types(tags)
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
    indoor = False if is_hike(tags) else None
    item = {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "price_min": price_min,
        "price_max": price_max,
        "currency": currency,
        "types": types,
        "kind": map_kind(types),
        "category": map_category(types, price_min),
        "description": tags.get("description:fr") or tags.get("description") or None,
        "address": addr or None,
        "photo_url": None,
        "photo_license": None,
        "website_url": website,
        "indoor": indoor,
        "source_name": "osm",
        "source_id": osm_id,
        "source_url": "https://www.openstreetmap.org/" + osm_id,
    }
    if not is_priced_place(item):
        return None
    return item


def fetch_around(lat, lon, radius_m=14000):
    query = """
[out:json][timeout:80];
(
  nwr["tourism"~"museum|attraction|zoo|theme_park|gallery|aquarium"]["name"]["fee"](around:%s,%s,%s);
  nwr["tourism"~"museum|attraction|zoo|theme_park|gallery|aquarium"]["name"]["charge"](around:%s,%s,%s);
  nwr["leisure"~"park|nature_reserve"]["name"]["fee"="no"](around:%s,%s,%s);
  nwr["tourism"="viewpoint"]["name"]["fee"="no"](around:%s,%s,%s);
);
out center tags;
""" % (radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon)
    return fetch_one(query)


def nearest_be(lat, lon, cities):
    best = None
    best_d = 35
    for city in cities:
        dlat = (city["latitude"] - lat) * 111
        dlon = (city["longitude"] - lon) * 85
        dist = (dlat * dlat + dlon * dlon) ** 0.5
        if dist < best_d:
            best_d = dist
            best = city
    return best


def main():
    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    upsert_be_cities(url, service_role)
    cities = [
        row
        for row in fetch_all(url, service_role, "cities", "id,slug,name,latitude,longitude,country_code")
        if (row.get("country_code") or "") == "BE" and row.get("latitude") is not None
    ]
    print("villes BE", len(cities), flush=True)

    seen = set()
    elements = []
    for name, _slug, lat, lon in BE_CITIES:
        chunk = fetch_around(lat, lon)
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
    print("osm unique", len(elements), flush=True)

    be_ids = ",".join(str(c["id"]) for c in cities if c.get("id") is not None)
    existing_rows = fetch_all(
        url,
        service_role,
        "outings",
        "id,source_name,source_id",
        extra="&city_id=in.(" + be_ids + ")" if be_ids else "&limit=1",
    )
    existing = set()
    for row in existing_rows:
        if row.get("source_id"):
            existing.add((row.get("source_name"), row["source_id"]))

    payload = []
    name_seen = set()
    skipped = 0
    for el in elements:
        item = osm_to_item(el)
        if not item:
            skipped += 1
            continue
        if (item["source_name"], item["source_id"]) in existing:
            skipped += 1
            continue
        nk = re.sub(r"[^a-z0-9]+", " ", (item["name"] or "").lower()).strip()
        geo = (round(item["latitude"], 3), round(item["longitude"], 3), nk)
        if geo in name_seen:
            skipped += 1
            continue
        city = nearest_be(item["latitude"], item["longitude"], cities)
        if not city:
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

    print("importables BE", len(payload), "ignorés", skipped, flush=True)
    if payload:
        upsert_outings(url, service_role, payload)
    print("terminé belgique", len(payload), flush=True)


if __name__ == "__main__":
    main()
