# -*- coding: utf-8 -*-
"""Remplit les communes sans sortie : POI réels avec prix, photo si possible, nearby en dernier recours."""

import argparse
import json
import os
import sys
from collections import defaultdict

from .city_match import build_city_grid, nearest_cities, resolve_city_id
from .nt_extract import extract_complete_from_nt_zip
from .quality import has_usable_photo, is_priced_place
from .run import load_env
from .supabase_io import fetch_all, fetch_city_indexes, to_outing_row, upsert_outings

NEARBY_PER_CITY = 2
MAX_NEAR_KM = 80
MAX_GPS_KM = 12


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--nt", default="data/datatourisme.nt.zip")
    parser.add_argument("--priced-jsonl", default="data/priced_outings.jsonl")
    parser.add_argument("--from-jsonl", action="store_true")
    parser.add_argument("--upsert", action="store_true")
    args = parser.parse_args()

    load_env(".env")
    if args.from_jsonl and os.path.exists(args.priced_jsonl):
        priced = _load_jsonl(args.priced_jsonl)
        print("chargé", args.priced_jsonl, "lignes", len(priced))
    else:
        if not os.path.exists(args.nt):
            sys.exit("Dump manquant: %s" % args.nt)
        _, priced = extract_complete_from_nt_zip(args.nt)
        os.makedirs(os.path.dirname(args.priced_jsonl) or ".", exist_ok=True)
        with open(args.priced_jsonl, "w", encoding="utf-8") as fh:
            for row in priced:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("écrit", args.priced_jsonl, "lignes", len(priced))

    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        sys.exit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    slugs, by_name, by_id, cities = fetch_city_indexes(url, service_role)
    existing = fetch_all(
        url,
        service_role,
        "outings",
        "city_id,kind,category,name,description,address,latitude,longitude,price_min,price_max,photo_url,photo_license,source_name,source_id,source_url",
    )
    print("villes", len(cities), "sorties actuelles", len(existing))

    counts = defaultdict(int)
    seen = set()
    for row in existing:
        counts[row["city_id"]] += 1
        if row.get("source_name") and row.get("source_id"):
            seen.add((row["source_name"], row["source_id"]))
    empty_ids = {c["id"] for c in cities if counts[c["id"]] == 0}
    print("communes vides avant", len(empty_ids))

    grid, cell = build_city_grid(cities)
    priced.sort(key=_photo_rank)
    payload = []
    used_empty = defaultdict(int)
    skipped_seen = skipped_filled = skipped_nomatch = 0

    for item in priced:
        if not is_priced_place(item):
            continue
        src_key = (item.get("source_name"), item.get("source_id"))
        if src_key in seen:
            skipped_seen += 1
            continue
        city_id = resolve_city_id(
            item, slugs, by_name, by_id, grid, cell, max_gps_km=MAX_GPS_KM
        )
        if not city_id or city_id not in empty_ids:
            skipped_filled += 1 if city_id else 0
            skipped_nomatch += 0 if city_id else 1
            continue
        row = to_outing_row(item, city_id)
        if not row:
            continue
        payload.append(row)
        seen.add(src_key)
        used_empty[city_id] += 1

    n_touched = sum(1 for n in used_empty.values() if n > 0)
    still_empty = [
        c for c in cities if c["id"] in empty_ids and used_empty.get(c["id"], 0) == 0
    ]
    print(
        "POI réels pour communes vides",
        len(payload),
        "communes touchées",
        n_touched,
        "encore vides",
        len(still_empty),
        "déjà en base",
        skipped_seen,
        "ville déjà fournie",
        skipped_filled,
        "sans match",
        skipped_nomatch,
    )

    priced_by_coords = [
        o
        for o in existing
        if o.get("latitude") is not None
        and o.get("longitude") is not None
        and (o.get("price_min") is not None or o.get("price_max") is not None)
    ]
    outing_grid, ocell = build_city_grid(
        [{"id": i, "latitude": o["latitude"], "longitude": o["longitude"], "row": o} for i, o in enumerate(priced_by_coords)]
    )
    nearby_rows = []
    no_nearby = 0
    for city in still_empty:
        near = nearest_cities(
            city["latitude"], city["longitude"], outing_grid, ocell, limit=12, max_km=MAX_NEAR_KM
        )
        if not near:
            near = nearest_cities(
                city["latitude"], city["longitude"], outing_grid, ocell, limit=4, max_km=250
            )
        near.sort(key=lambda x: (_photo_rank(x[1]["row"]), x[0]))
        picked = []
        seen_names = set()
        for dist, holder in near:
            src = holder["row"]
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
            picked.append(src)
            if len(picked) >= NEARBY_PER_CITY:
                break
        if not picked:
            no_nearby += 1

    print("clones nearby", len(nearby_rows), "communes sans voisin < %skm" % MAX_NEAR_KM, no_nearby)
    payload.extend(nearby_rows)
    print("total à upsert", len(payload))

    if not args.upsert:
        print("dry-run : passe --upsert pour écrire")
        return
    posted = upsert_outings(url, service_role, payload)
    print("upsert ok", posted)


if __name__ == "__main__":
    main()
