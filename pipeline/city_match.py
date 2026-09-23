# -*- coding: utf-8 -*-
import math
import re
from collections import defaultdict

from .categories import slugify

ARRONDISSEMENT = re.compile(
    r"^(?P<city>.+?)\s+\d{1,2}e(?:r)?\s+arrondissement\b",
    re.IGNORECASE,
)
ARRONDISSEMENT_SLUG = re.compile(r"^(.+?)-\d{1,2}e(?:r)?-arrondissement$")
CEDEX = re.compile(r"\s+cedex\b.*$", re.IGNORECASE)


def _saint_variants(slug):
    if not slug:
        return []
    out = [slug]
    repl = (
        ("saint-", "st-"),
        ("sainte-", "ste-"),
        ("st-", "saint-"),
        ("ste-", "sainte-"),
    )
    for a, b in repl:
        if a in slug:
            out.append(slug.replace(a, b, 1))
    return out


def candidate_slugs(city_name, postal_code, city_slug):
    out = []
    raw_name = CEDEX.sub("", city_name or "").strip()
    slug = city_slug or slugify(raw_name)
    if slug:
        out.append(slug)
        out.extend(_saint_variants(slug))
    if raw_name and postal_code:
        out.append(slugify("%s (%s)" % (raw_name, postal_code)))
        if slug:
            out.append("%s-%s" % (slug, postal_code))
            for v in _saint_variants(slug):
                out.append("%s-%s" % (v, postal_code))
    match = ARRONDISSEMENT.match(raw_name)
    if match:
        parent = slugify(match.group("city"))
        if parent:
            out.append(parent)
            out.extend(_saint_variants(parent))
    slug_arr = ARRONDISSEMENT_SLUG.match(slug or "")
    if slug_arr:
        out.append(slug_arr.group(1))
    seen = set()
    unique = []
    for item in out:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def build_city_grid(cities, cell=0.15):
    grid = defaultdict(list)
    for city in cities:
        key = (int(city["latitude"] / cell), int(city["longitude"] / cell))
        grid[key].append(city)
    return grid, cell


def nearest_cities(lat, lon, grid, cell, limit=8, max_km=40):
    gi, gj = int(lat / cell), int(lon / cell)
    span = max(2, int(max_km / max(cell * 111.0, 1e-6)) + 1)
    found = []
    for di in range(-span, span + 1):
        for dj in range(-span, span + 1):
            for city in grid.get((gi + di, gj + dj), ()):
                dist = haversine_km(lat, lon, city["latitude"], city["longitude"])
                if dist <= max_km:
                    found.append((dist, city))
    found.sort(key=lambda x: x[0])
    return found[:limit]


def resolve_city_id(item, by_slug, by_name, city_by_id=None, grid=None, cell=0.15, max_gps_km=12):
    for slug in candidate_slugs(item.get("city_name"), item.get("postal_code"), item.get("city_slug")):
        if slug in by_slug:
            return by_slug[slug]
    name = CEDEX.sub("", (item.get("city_name") or "")).strip().lower()
    lat, lon = item.get("latitude"), item.get("longitude")
    if name and name in by_name:
        ids = by_name[name]
        if len(ids) == 1:
            return ids[0]
        if lat is not None and lon is not None and city_by_id:
            best_id, best_d = None, 1e9
            for cid in ids:
                city = city_by_id.get(cid)
                if not city:
                    continue
                d = haversine_km(lat, lon, city["latitude"], city["longitude"])
                if d < best_d:
                    best_id, best_d = cid, d
            if best_id is not None and best_d <= 25:
                return best_id
    if grid is not None and lat is not None and lon is not None:
        near = nearest_cities(lat, lon, grid, cell, limit=1, max_km=max_gps_km)
        if near:
            return near[0][1]["id"]
    return None
