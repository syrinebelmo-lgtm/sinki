# -*- coding: utf-8 -*-
import json
import os
import socket
import time
import urllib.error
import urllib.request

UPSERT_BATCH = 80


def _headers(service_role):
    return {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def fetch_all(url, service_role, path, select, extra=""):
    rows = []
    offset = 0
    while True:
        q = (
            url.rstrip("/")
            + "/rest/v1/"
            + path
            + "?select="
            + select
            + extra
            + "&order=id&limit=1000&offset="
            + str(offset)
        )
        req = urllib.request.Request(q, headers=_headers(service_role))
        batch = None
        last = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    batch = json.loads(resp.read().decode("utf-8"))
                last = None
                break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
                last = exc
                time.sleep(2.5 * (attempt + 1))
        if last is not None:
            raise last
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def fetch_city_indexes(url, service_role):
    cities = fetch_all(url, service_role, "cities", "id,slug,name,latitude,longitude")
    slugs = {}
    by_name = {}
    by_id = {}
    for row in cities:
        slugs[row["slug"]] = row["id"]
        by_id[row["id"]] = row
        key = (row.get("name") or "").strip().lower()
        if key:
            by_name.setdefault(key, []).append(row["id"])
    return slugs, by_name, by_id, cities


def _money(value):
    if value is None:
        return None
    number = float(value)
    if number < 0 or number >= 1000000:
        return None
    return round(number, 2)


def to_outing_row(item, city_id):
    price_min = _money(item.get("price_min"))
    price_max = _money(item.get("price_max"))
    if price_max is None:
        price_max = price_min
    if price_min is None:
        return None
    return {
        "city_id": city_id,
        "kind": item.get("kind") or "place",
        "category": item["category"],
        "name": item["name"][:500],
        "description": (item.get("description") or "")[:8000] or None,
        "address": item.get("address"),
        "latitude": item["latitude"],
        "longitude": item["longitude"],
        "price_min": price_min,
        "price_max": price_max,
        "currency": item.get("currency") or "EUR",
        "photo_url": (item.get("photo_url") or None),
        "photo_license": item.get("photo_license"),
        "website_url": item.get("website_url"),
        "indoor": item.get("indoor"),
        "source_name": item["source_name"],
        "source_id": item["source_id"][:200],
        "source_url": item.get("source_url"),
        "is_active": True,
    }


def upsert_outings(url, service_role, rows):
    posted = 0
    for i in range(0, len(rows), UPSERT_BATCH):
        chunk = rows[i : i + UPSERT_BATCH]
        body = json.dumps(chunk).encode("utf-8")
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/outings?on_conflict=source_name,source_id",
            data=body,
            headers=_headers(service_role),
            method="POST",
        )
        last = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    resp.read()
                posted += len(chunk)
                print("upsert", posted, "/", len(rows), flush=True)
                last = None
                break
            except urllib.error.HTTPError as exc:
                last = exc
                break
            except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionResetError) as exc:
                last = exc
                time.sleep(2 * (attempt + 1))
        if last is None:
            continue
        try:
            raise last
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            if exc.code == 400 and len(chunk) > 1:
                mid = len(chunk) // 2
                print("lot 400, split", i, flush=True)
                posted += upsert_outings(url, service_role, chunk[:mid])
                posted += upsert_outings(url, service_role, chunk[mid:])
                continue
            raise RuntimeError("Supabase upsert HTTP %s: %s" % (exc.code, detail[:500]))
        except (TimeoutError, socket.timeout, urllib.error.URLError):
            if len(chunk) == 1:
                raise
            print("timeout, split", i, "size", len(chunk), flush=True)
            posted += upsert_outings(url, service_role, chunk[: len(chunk) // 2])
            posted += upsert_outings(url, service_role, chunk[len(chunk) // 2 :])
    return posted
