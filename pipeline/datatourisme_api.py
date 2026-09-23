# -*- coding: utf-8 -*-
"""Import via API DATAtourisme : pagination complète (page_size=250), pas de lots de 15."""

import json
import os
import urllib.parse
import urllib.request
import time

from .categories import map_category, map_kind, slugify
from .quality import is_complete, is_hotel_or_lodging

FIELDS = ",".join(
    [
        "uuid",
        "uri",
        "label",
        "type",
        "isLocatedAt",
        "hasMainRepresentation",
        "hasRepresentation",
        "hasDescription",
        "offers",
        "lastUpdate",
    ]
)

EXCLUDED_TYPES = "Hotel,Hostel,Camping,Campground,Apartment,BedAndBreakfast,HolidayRental,Accommodation,LodgingBusiness"


def _pick_label(value):
    if isinstance(value, dict):
        return value.get("fr") or value.get("en") or next(iter(value.values()), None)
    if isinstance(value, list) and value:
        return _pick_label(value[0])
    return value


def _find_locator(node, depth=0):
    if depth > 6 or node is None:
        return None
    if isinstance(node, str) and node.startswith("http"):
        if any(node.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
            return node
        return None
    if isinstance(node, list):
        for item in node:
            found = _find_locator(item, depth + 1)
            if found:
                return found
        return None
    if isinstance(node, dict):
        for key in ("ebucore:locator", "locator", "url", "contentUrl"):
            if node.get(key):
                loc = node[key]
                if isinstance(loc, str) and loc.startswith("http"):
                    return loc
        for val in node.values():
            found = _find_locator(val, depth + 1)
            if found:
                return found
    return None


def _find_prices(node, acc=None, depth=0):
    if acc is None:
        acc = []
    if depth > 8 or node is None:
        return acc
    if isinstance(node, list):
        for item in node:
            _find_prices(item, acc, depth + 1)
        return acc
    if isinstance(node, dict):
        for key in ("minPrice", "schema:minPrice", "price", "schema:price", "maxPrice", "schema:maxPrice"):
            if key in node and node[key] is not None:
                try:
                    acc.append(float(node[key]))
                except (TypeError, ValueError):
                    pass
        for val in node.values():
            if isinstance(val, (dict, list)):
                _find_prices(val, acc, depth + 1)
    return acc


def _geo(poi):
    located = poi.get("isLocatedAt") or {}
    if isinstance(located, list):
        located = located[0] if located else {}
    geo = located.get("geo") or located.get("schema:geo") or {}
    if isinstance(geo, list):
        geo = geo[0] if geo else {}
    lat = geo.get("latitude") or geo.get("schema:latitude")
    lon = geo.get("longitude") or geo.get("schema:longitude")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def _address(poi):
    located = poi.get("isLocatedAt") or {}
    if isinstance(located, list):
        located = located[0] if located else {}
    addr = located.get("address") or {}
    if isinstance(addr, list):
        addr = addr[0] if addr else {}
    street = addr.get("streetAddress") or addr.get("schema:streetAddress")
    city = addr.get("addressLocality") or addr.get("schema:addressLocality")
    postal = addr.get("postalCode") or addr.get("schema:postalCode")
    if isinstance(city, dict):
        city = _pick_label(city)
    return street, city, postal


def poi_to_row(poi):
    types = poi.get("type") or []
    if isinstance(types, str):
        types = [types]
    types = [t.split("#")[-1].split("/")[-1] for t in types]
    name = _pick_label(poi.get("label"))
    desc = _pick_label(poi.get("hasDescription"))
    photo = _find_locator(poi.get("hasMainRepresentation")) or _find_locator(poi.get("hasRepresentation"))
    prices = _find_prices(poi.get("offers"))
    pmin = min(prices) if prices else None
    pmax = max(prices) if prices else None
    lat, lon = _geo(poi)
    street, city, postal = _address(poi)
    uri = poi.get("uri") or ""
    row = {
        "source_name": "datatourisme",
        "source_id": poi.get("uuid") or uri.rsplit("/", 1)[-1],
        "source_url": uri,
        "name": name,
        "description": desc if isinstance(desc, str) else None,
        "types": types,
        "latitude": lat,
        "longitude": lon,
        "photo_url": photo,
        "photo_license": "Licence Ouverte 2.0 / producteur DATAtourisme",
        "price_min": pmin,
        "price_max": pmax,
        "address": street,
        "city_name": city,
        "postal_code": postal,
        "city_slug": slugify(city) if city else "",
    }
    if is_hotel_or_lodging(types) or not is_complete(row):
        return None
    row["category"] = map_category(types, pmin)
    row["kind"] = map_kind(types)
    return row


def iter_catalog(api_key):
    params = {
        "api_key": api_key,
        "lang": "fr",
        "page_size": "250",
        "fields": FIELDS,
        "type[nin]": EXCLUDED_TYPES,
    }
    url = "https://api.datatourisme.fr/v1/placeOfInterest?" + urllib.parse.urlencode(params)
    while url:
        req = urllib.request.Request(url, headers={"X-API-Key": api_key, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        objects = payload.get("objects") or []
        meta = payload.get("meta") or {}
        print("page", meta.get("page"), "/", meta.get("total_pages"), "objets", len(objects), flush=True)
        for poi in objects:
            yield poi
        url = meta.get("next")
        time.sleep(0.12)
