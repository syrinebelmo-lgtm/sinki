# -*- coding: utf-8 -*-
"""Dernier recours : les communes encore vides (DOM-TOM, îles, Corse isolée)."""

import json
import os
import sys
from collections import Counter, defaultdict

from .city_match import build_city_grid, haversine_km, nearest_cities
from .quality import has_usable_photo, is_priced_place
from .run import load_env
from .supabase_io import fetch_all, to_outing_row, upsert_outings

NEARBY_PER_CITY = 2
LOCAL_GPS_KM = 60


def _load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _photo_rank(item):
    return 0 if has_usable_photo(item.get("photo_url")) else 1


def main():
    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        sys.exit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    cities = fetch_all(url, service_role, "cities", "id,slug,name,latitude,longitude")
    existing = fetch_all(
        url,
        service_role,
        "outings",
        "city_id,kind,category,name,description,address,latitude,longitude,price_min,price_max,photo_url,photo_license,source_name,source_id,source_url",
    )
    counts = Counter(o["city_id"] for o in existing)
    empty = [c for c in cities if counts[c["id"]] == 0]
    print("communes encore vides", len(empty))
    if not empty:
        return

    seen = set()
    for row in existing:
        if row.get("source_name") and row.get("source_id"):
            seen.add((row["source_name"], row["source_id"]))

    empty_grid, cell = build_city_grid(empty)
    priced_path = "data/priced_outings.jsonl"
    payload = []
    used = defaultdict(int)
    if os.path.exists(priced_path):
        priced = _load_jsonl(priced_path)
        priced.sort(key=_photo_rank)
        for item in priced:
            if not is_priced_place(item):
                continue
            src_key = (item.get("source_name"), item.get("source_id"))
            if src_key in seen:
                continue
            lat, lon = item.get("latitude"), item.get("longitude")
            if lat is None or lon is None:
                continue
            near = nearest_cities(lat, lon, empty_grid, cell, limit=1, max_km=LOCAL_GPS_KM)
            if not near:
                continue
            city = near[0][1]
            row = to_outing_row(item, city["id"])
            if not row:
                continue
            payload.append(row)
            seen.add(src_key)
            used[city["id"]] += 1

    still = [c for c in empty if used.get(c["id"], 0) == 0]
    print("POI locaux restants", len(payload), "communes encore vides", len(still))

    priced_existing = [
        o
        for o in existing
        if o.get("latitude") is not None
        and o.get("longitude") is not None
        and (o.get("price_min") is not None or o.get("price_max") is not None)
    ]
    nearby_rows = []
    for city in still:
        ranked = []
        for src in priced_existing:
            dist = haversine_km(city["latitude"], city["longitude"], src["latitude"], src["longitude"])
            ranked.append(((_photo_rank(src), dist), src))
        ranked.sort(key=lambda x: x[0])
        picked = 0
        seen_names = set()
        for _, src in ranked:
            name = (src.get("name") or "").strip().lower()
            if name in seen_names:
                continue
            seen_names.add(name)
            orig_sid = src.get("source_id") or src.get("name") or "x"
            sid = ("near-%s-%s" % (city["id"], orig_sid))[:200]
            src_key = ("nearby", sid)
            if src_key in seen:
                continue
            clone = {
                "source_name": "nearby",
                "source_id": sid,
                "source_url": src.get("source_url"),
                "name": src["name"],
                "description": src.get("description"),
                "latitude": src["latitude"],
                "longitude": src["longitude"],
                "photo_url": src.get("photo_url"),
                "photo_license": src.get("photo_license"),
                "price_min": src.get("price_min"),
                "price_max": src.get("price_max") if src.get("price_max") is not None else src.get("price_min"),
                "address": src.get("address"),
                "category": src.get("category") or "Activités et loisirs",
                "kind": src.get("kind") or "place",
            }
            row = to_outing_row(clone, city["id"])
            if not row:
                continue
            nearby_rows.append(row)
            seen.add(src_key)
            picked += 1
            if picked >= NEARBY_PER_CITY:
                break
        if picked == 0:
            print("aucune sortie clonable pour", city["name"])

    print("clones leftovers", len(nearby_rows))
    payload.extend(nearby_rows)
    print("total leftovers", len(payload))
    posted = upsert_outings(url, service_role, payload)
    print("upsert leftovers ok", posted)


if __name__ == "__main__":
    main()
