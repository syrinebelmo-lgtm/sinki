# -*- coding: utf-8 -*-
"""Importe tout le JSONL tarifé dans toutes les communes (pas seulement les villes vides)."""

import argparse
import json
import os
import sys

from .city_match import build_city_grid, resolve_city_id
from .quality import is_priced_place
from .run import load_env
from .supabase_io import fetch_all, fetch_city_indexes, to_outing_row, upsert_outings


def _load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--priced-jsonl", default="data/priced_outings.jsonl")
    parser.add_argument("--upsert", action="store_true")
    parser.add_argument("--max-gps-km", type=float, default=20)
    args = parser.parse_args()

    load_env(".env")
    if not os.path.exists(args.priced_jsonl):
        sys.exit("JSONL manquant: %s" % args.priced_jsonl)

    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        sys.exit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    slugs, by_name, by_id, cities = fetch_city_indexes(url, service_role)
    existing = fetch_all(url, service_role, "outings", "source_name,source_id")
    seen = set()
    for row in existing:
        if row.get("source_name") and row.get("source_id"):
            seen.add((row["source_name"], row["source_id"]))
    print("villes", len(cities), "clés déjà en base", len(seen))

    grid, cell = build_city_grid(cities)
    payload = []
    skipped_seen = skipped_nomatch = skipped_quality = 0
    for item in _load_jsonl(args.priced_jsonl):
        if not is_priced_place(item):
            skipped_quality += 1
            continue
        src_key = (item.get("source_name"), item.get("source_id"))
        if src_key in seen:
            skipped_seen += 1
            continue
        city_id = resolve_city_id(
            item, slugs, by_name, by_id, grid, cell, max_gps_km=args.max_gps_km
        )
        if not city_id:
            skipped_nomatch += 1
            continue
        row = to_outing_row(item, city_id)
        if not row:
            skipped_quality += 1
            continue
        payload.append(row)
        seen.add(src_key)

    print(
        "nouvelles sorties",
        len(payload),
        "déjà présentes",
        skipped_seen,
        "sans commune",
        skipped_nomatch,
        "rejet qualité",
        skipped_quality,
    )
    if not args.upsert:
        print("dry-run : passe --upsert pour écrire")
        return
    posted = upsert_outings(url, service_role, payload)
    print("upsert ok", posted)


if __name__ == "__main__":
    main()
