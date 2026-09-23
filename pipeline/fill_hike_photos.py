# -*- coding: utf-8 -*-
"""Remplit les photos Commons libres des randonnées OSM déjà en base."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from .commons_photos import licensed_photo
from .run import load_env
from .supabase_io import fetch_all


def _headers(service_role):
    return {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def patch_photo(url, service_role, outing_id, photo_url, license_name):
    body = json.dumps({"photo_url": photo_url, "photo_license": license_name}).encode("utf-8")
    last = None
    for attempt in range(5):
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/outings?id=eq." + outing_id,
            data=body,
            headers=_headers(service_role),
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(1.2 * (attempt + 1))
    raise last


def fill_one(url, service_role, row, cache):
    try:
        lat = float(row["latitude"])
        lon = float(row["longitude"])
    except (TypeError, ValueError):
        return False, row.get("name")
    try:
        shop = (row.get("category") or "") == "Shopping"
        mode = row.get("photo_mode") or ("shop" if shop else "place")
        photo, license_name = licensed_photo(
            row.get("name") or "",
            lat,
            lon,
            None,
            cache,
            allow_geo_backup=(not shop),
            mode=mode,
        )
        if not photo:
            return False, row.get("name")
        patch_photo(url, service_role, row["id"], photo, license_name)
        return True, row.get("name")
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, row.get("name")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    rows = fetch_all(
        url,
        service_role,
        "outings",
        "id,name,latitude,longitude,photo_url,category,source_name",
        extra="&source_name=eq.osm&category=eq." + urllib.parse.quote("Randonnées"),
    )
    missing = [r for r in rows if not (r.get("photo_url") or "").strip()]
    if args.limit:
        missing = missing[: args.limit]
    print("randos OSM", len(rows), "sans photo", len(missing), flush=True)

    cache = {}
    filled = 0
    failed = 0
    done = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(fill_one, url, service_role, row, cache) for row in missing]
        for fut in as_completed(futs):
            ok, name = fut.result()
            done += 1
            if ok:
                filled += 1
                if filled <= 8 or filled % 40 == 0:
                    print("photo", filled, name, flush=True)
            else:
                failed += 1
            if done % 50 == 0:
                print("progress", done, "/", len(missing), "ok", filled, "sans", failed, flush=True)
    print("terminé ok", filled, "sans photo", failed, flush=True)


if __name__ == "__main__":
    main()
