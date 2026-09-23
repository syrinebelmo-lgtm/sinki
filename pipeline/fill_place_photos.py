# -*- coding: utf-8 -*-
"""Remplit les photos Commons libres des sorties déjà en base (ville ou catalogue)."""

import argparse
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from .fill_hike_photos import fill_one
from .quality import has_usable_photo
from .run import load_env
from .supabase_io import fetch_all

EVENT_RE = re.compile(
    r"vide[-\s]?grenier|brocante|salon du|march[eé] |f[eê]te |concert |festival ",
    re.I,
)


BIG_CITIES = {1, 2, 3, 4, 5, 6}  # Lyon, Paris, Marseille, Bordeaux, Lille, Toulouse


def _prio(row):
    """France entière : grandes villes + lieux réels d’abord, toutes catégories."""
    event = 1 if EVENT_RE.search(row.get("name") or "") else 0
    if row.get("photo_mode") == "int":
        cat = row.get("category") or ""
        if "Musée" in cat or "Randonn" in cat:
            cat_n = 0
        elif "Restaurant" in cat or "Soirée" in cat:
            cat_n = 1
        elif "balade" in cat.lower() or "Balade" in cat:
            cat_n = 2
        else:
            cat_n = 3
        return (cat_n, event)
    try:
        cid = int(row.get("city_id") or 0)
    except (TypeError, ValueError):
        cid = 0
    big = 0 if cid in BIG_CITIES else 1
    src = (row.get("source_name") or "")
    src_n = 0 if src == "official_website" else 1 if src == "osm" else 2
    return (event, big, src_n)


def _run_fill(url, service_role, missing, workers=4, chunk=80):
    cache = {}
    filled = 0
    failed = 0
    done = 0
    chunk = max(20, chunk)
    workers = max(1, workers)
    print("à traiter", len(missing), flush=True)
    for start in range(0, len(missing), chunk):
        batch = missing[start : start + chunk]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(fill_one, url, service_role, row, cache) for row in batch]
            for fut in as_completed(futs):
                ok, name = fut.result()
                done += 1
                if ok:
                    filled += 1
                    if filled <= 8 or filled % 50 == 0:
                        print("photo", filled, name, flush=True)
                else:
                    failed += 1
                if done % 50 == 0:
                    print("progress", done, "/", len(missing), "ok", filled, "sans", failed, flush=True)
    print("terminé ok", filled, "sans photo", failed, flush=True)
    return filled, failed


def fill_for_country(url, service_role, cc, workers=4, chunk=80, limit=0):
    extra = "&is_active=eq.true&or=(photo_url.is.null,photo_url.eq.)&source_name=eq.osm"
    cities = fetch_all(
        url,
        service_role,
        "cities",
        "id",
        extra="&country_code=eq." + cc + "&is_active=eq.true",
    )
    ids = [str(c["id"]) for c in cities if c.get("id") is not None]
    rows = []
    for i in range(0, len(ids), 30):
        chunk_ids = ",".join(ids[i : i + 30])
        rows.extend(
            fetch_all(
                url,
                service_role,
                "outings",
                "id,name,latitude,longitude,photo_url,category,source_name,city_id",
                extra=extra + "&city_id=in.(" + chunk_ids + ")",
            )
        )
    missing = [r for r in rows if not has_usable_photo(r.get("photo_url"))]
    for row in missing:
        row["photo_mode"] = "int"
    missing.sort(key=_prio)
    if limit:
        missing = missing[:limit]
    print("photos Commons", cc, "sans photo", len(missing), "/", len(rows), flush=True)
    return _run_fill(url, service_role, missing, workers=workers, chunk=chunk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city-id")
    parser.add_argument("--all", action="store_true", help="Toutes les sorties actives sans photo")
    parser.add_argument("--cc", help="Pays (ex. NL) : OSM sans photo de ce pays")
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk", type=int, default=200)
    args = parser.parse_args()
    if not args.city_id and not args.all and not args.category and not args.cc:
        raise SystemExit("Précise --city-id, --category, --cc ou --all")

    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    extra = "&is_active=eq.true&or=(photo_url.is.null,photo_url.eq.)&source_name=neq.nearby"
    if args.city_id:
        extra += "&city_id=eq." + urllib.parse.quote(str(args.city_id))
    if args.category:
        extra += "&category=eq." + urllib.parse.quote(args.category)
    if args.cc:
        extra += "&source_name=eq.osm"
        cities = fetch_all(
            url,
            service_role,
            "cities",
            "id",
            extra="&country_code=eq." + args.cc.strip().upper() + "&is_active=eq.true",
        )
        ids = [str(c["id"]) for c in cities if c.get("id") is not None]
        rows = []
        for i in range(0, len(ids), 30):
            chunk_ids = ",".join(ids[i : i + 30])
            rows.extend(
                fetch_all(
                    url,
                    service_role,
                    "outings",
                    "id,name,latitude,longitude,photo_url,category,source_name,city_id",
                    extra=extra + "&city_id=in.(" + chunk_ids + ")",
                )
            )
    else:
        rows = fetch_all(
            url,
            service_role,
            "outings",
            "id,name,latitude,longitude,photo_url,category,source_name,city_id",
            extra=extra,
        )
    missing = [
        r
        for r in rows
        if not has_usable_photo(r.get("photo_url")) and (r.get("source_name") or "") != "nearby"
    ]
    if args.limit:
        missing = missing[: args.limit]
    if args.cc:
        for row in missing:
            row["photo_mode"] = "int"
    missing.sort(key=_prio)
    print("à traiter", len(missing), "chargées", len(rows), flush=True)
    _run_fill(url, service_role, missing, workers=args.workers, chunk=args.chunk)


if __name__ == "__main__":
    main()
