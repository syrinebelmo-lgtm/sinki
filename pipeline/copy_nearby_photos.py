# -*- coding: utf-8 -*-
"""Copie la photo de la sortie d’origine vers les clones nearby encore vides."""

import os

from .fill_hike_photos import patch_photo
from .quality import has_usable_photo
from .run import load_env
from .supabase_io import fetch_all


def copy_for_country(url, service_role, cc):
    cities = fetch_all(
        url,
        service_role,
        "cities",
        "id",
        extra="&country_code=eq." + cc + "&is_active=eq.true",
    )
    ids = [str(c["id"]) for c in cities if c.get("id") is not None]
    nearby = []
    for i in range(0, len(ids), 30):
        chunk_ids = ",".join(ids[i : i + 30])
        nearby.extend(
            fetch_all(
                url,
                service_role,
                "outings",
                "id,name,source_id,photo_url",
                extra="&source_name=eq.nearby&city_id=in.(" + chunk_ids + ")",
            )
        )
    missing = [r for r in nearby if not has_usable_photo(r.get("photo_url"))]
    print("nearby sans photo", cc, len(missing), "/", len(nearby), flush=True)
    orig_ids = []
    seen = set()
    for row in missing:
        oid = orig_source_id(row.get("source_id"))
        if oid and oid not in seen:
            seen.add(oid)
            orig_ids.append(oid)
    photos = {}
    for i in range(0, len(orig_ids), 80):
        chunk = orig_ids[i : i + 80]
        inlist = ",".join('"%s"' % x.replace('"', "") for x in chunk)
        rows = fetch_all(
            url,
            service_role,
            "outings",
            "source_id,photo_url,photo_license,name",
            extra="&source_name=neq.nearby&source_id=in.(" + inlist + ")",
        )
        for row in rows:
            if has_usable_photo(row.get("photo_url")):
                photos[row.get("source_id")] = (row["photo_url"], row.get("photo_license"))
        print("index photos", min(i + 80, len(orig_ids)), "/", len(orig_ids), "trouvées", len(photos), flush=True)
    patched = 0
    skipped = 0
    for row in missing:
        oid = orig_source_id(row.get("source_id"))
        hit = photos.get(oid)
        if not hit:
            skipped += 1
            continue
        patch_photo(url, service_role, row["id"], hit[0], hit[1])
        patched += 1
        if patched <= 8 or patched % 200 == 0:
            print("photo", patched, row.get("name"), flush=True)
    print("terminé nearby", cc, "ok", patched, "toujours sans", skipped, flush=True)
    return patched, skipped


def orig_source_id(sid):
    sid = sid or ""
    if not sid.startswith("near-"):
        return None
    parts = sid.split("-", 2)
    if len(parts) < 3 or not parts[2]:
        return None
    return parts[2]


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--city-id", help="Un id ou une liste (ex. 1,2)")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    extra = "&source_name=eq.nearby"
    city_ids = [part.strip() for part in str(args.city_id or "").split(",") if part.strip()]
    if len(city_ids) == 1:
        extra += "&city_id=eq." + city_ids[0]
    elif city_ids:
        extra += "&city_id=in.(" + ",".join(city_ids) + ")"

    nearby = fetch_all(
        url,
        service_role,
        "outings",
        "id,name,source_id,photo_url",
        extra=extra,
    )
    missing = [r for r in nearby if not has_usable_photo(r.get("photo_url"))]
    if args.limit:
        missing = missing[: args.limit]
    print("nearby sans photo", len(missing), "/", len(nearby), flush=True)

    orig_ids = []
    seen = set()
    for row in missing:
        oid = orig_source_id(row.get("source_id"))
        if oid and oid not in seen:
            seen.add(oid)
            orig_ids.append(oid)

    photos = {}
    for i in range(0, len(orig_ids), 80):
        chunk = orig_ids[i : i + 80]
        inlist = ",".join('"%s"' % x.replace('"', "") for x in chunk)
        rows = fetch_all(
            url,
            service_role,
            "outings",
            "source_id,photo_url,photo_license,name",
            extra="&source_name=neq.nearby&source_id=in.(" + inlist + ")",
        )
        for row in rows:
            if has_usable_photo(row.get("photo_url")):
                photos[row.get("source_id")] = (row["photo_url"], row.get("photo_license"))
        print("index photos", min(i + 80, len(orig_ids)), "/", len(orig_ids), "trouvées", len(photos), flush=True)

    patched = 0
    skipped = 0
    for row in missing:
        oid = orig_source_id(row.get("source_id"))
        hit = photos.get(oid)
        if not hit:
            skipped += 1
            continue
        patch_photo(url, service_role, row["id"], hit[0], hit[1])
        patched += 1
        if patched <= 8 or patched % 200 == 0:
            print("photo", patched, row.get("name"), flush=True)
    print("terminé nearby ok", patched, "toujours sans", skipped, flush=True)


if __name__ == "__main__":
    main()
