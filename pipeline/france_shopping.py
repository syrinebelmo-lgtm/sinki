# -*- coding: utf-8 -*-
"""Shopping France : centres commerciaux et friperies OSM réels. Pas d’invention."""

import json
import os
import re
import time
import urllib.parse
import urllib.request

from .categories import map_category, map_kind, slugify
from .france_hikes import in_metropolitan_france
from .quality import is_grocery_shop, is_hotel_or_lodging, is_priced_place
from .run import load_env
from .supabase_io import fetch_all, to_outing_row, upsert_outings
from .switzerland import UA, element_latlon, in_switzerland, nearest_city

OVERPASS_MIRRORS = (
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)

SHOP_HUBS = [
    ("Paris", 48.8566, 2.3522),
    ("Lyon", 45.7640, 4.8357),
    ("Marseille", 43.2965, 5.3698),
    ("Lille", 50.6292, 3.0573),
    ("Toulouse", 43.6047, 1.4442),
    ("Bordeaux", 44.8378, -0.5792),
    ("Nantes", 47.2184, -1.5536),
    ("Strasbourg", 48.5734, 7.7521),
    ("Montpellier", 43.6108, 3.8767),
    ("Nice", 43.7102, 7.2620),
    ("Rennes", 48.1173, -1.6778),
    ("Grenoble", 45.1885, 5.7245),
    ("Rouen", 49.4431, 1.0993),
    ("Tours", 47.3941, 0.6848),
    ("Dijon", 47.3220, 5.0415),
    ("Reims", 49.2583, 4.0317),
    ("Le Havre", 49.4944, 0.1079),
    ("Saint-Étienne", 45.4397, 4.3872),
    ("Toulon", 43.1242, 5.9280),
    ("Angers", 47.4784, -0.5632),
    ("Clermont-Ferrand", 45.7772, 3.0870),
    ("Aix-en-Provence", 43.5297, 5.4474),
    ("Metz", 49.1193, 6.1757),
    ("Nancy", 48.6921, 6.1844),
    ("Orléans", 47.9029, 1.9093),
    ("Mulhouse", 47.7508, 7.3359),
    ("Caen", 49.1829, -0.3707),
    ("Perpignan", 42.6887, 2.8948),
    ("Brest", 48.3904, -4.4861),
    ("Limoges", 45.8336, 1.2611),
    ("Amiens", 49.8941, 2.2958),
    ("Annecy", 45.8992, 6.1294),
    ("Avignon", 43.9493, 4.8055),
    ("La Rochelle", 46.1603, -1.1511),
    ("Bayonne", 43.4929, -1.4748),
    ("Chambéry", 45.5646, 5.9178),
]

SHOP_NAME_RE = re.compile(
    r"\b(friperie|friperies|frip'|d[eé]p[oô]t[-\s]?vente|kilo\s?shop|"
    r"centre commercial|centres commerciaux|galerie marchande|galerie commerciale|"
    r"shopping mall|grand magasin|westfield|part[-\s]?dieu)\b",
    re.I,
)

SECOND_HAND_SHOPS = {"second_hand", "charity"}
MALL_SHOPS = {"mall", "department_store"}
SKIP_SHOPS = {
    "car",
    "motorcycle",
    "bicycle",
    "car_repair",
    "hairdresser",
    "tobacco",
    "kiosk",
    "funeral_directors",
    "estate_agent",
    "copyshop",
    "mobile_phone",
    "electronics",
    "computer",
}


def is_shopping_tags(tags, name):
    shop = (tags.get("shop") or "").strip().lower()
    if is_grocery_shop(name, shop):
        return False
    if shop in SKIP_SHOPS:
        return bool(SHOP_NAME_RE.search(name or ""))
    if shop in SECOND_HAND_SHOPS or shop in MALL_SHOPS:
        return True
    if shop in ("clothes", "fashion", "shoes", "boutique"):
        return True
    if shop == "clothes" and (tags.get("second_hand") or "").lower() in ("yes", "only"):
        return True
    if (tags.get("second_hand") or "").lower() in ("yes", "only") and shop in ("clothes", "books", "furniture", "yes", ""):
        return True
    if (tags.get("amenity") or "") == "marketplace" and SHOP_NAME_RE.search(name or ""):
        return True
    return bool(SHOP_NAME_RE.search(name or ""))


def shopping_types(tags):
    shop = (tags.get("shop") or "").strip().lower()
    bits = ["shopping"]
    if shop in SECOND_HAND_SHOPS or (tags.get("second_hand") or "").lower() in ("yes", "only"):
        bits.extend(["second_hand", "friperie"])
    if shop == "charity":
        bits.append("charity_shop")
    if shop == "mall":
        bits.append("shopping_mall")
    if shop == "department_store":
        bits.append("department_store")
    if shop in ("clothes", "fashion", "shoes", "boutique"):
        bits.append("clothes")
    return bits


def shopping_blurb(tags):
    shop = (tags.get("shop") or "").strip().lower()
    if shop in SECOND_HAND_SHOPS or (tags.get("second_hand") or "").lower() in ("yes", "only"):
        return "Friperie / seconde main."
    if shop == "mall":
        return "Centre commercial."
    if shop == "department_store":
        return "Grand magasin."
    return "Shopping."


def osm_to_shopping(el):
    tags = el.get("tags") or {}
    name = (tags.get("name:fr") or tags.get("name") or "").strip()
    if len(name) < 3:
        return None
    if is_hotel_or_lodging(list(tags.values())):
        return None
    shop = (tags.get("shop") or "").strip().lower()
    if is_grocery_shop(name, shop):
        return None
    if re.search(r"\bdrive\b", name, re.I) and shop not in MALL_SHOPS:
        return None
    if re.fullmatch(r"garage", name, re.I):
        return None
    if not is_shopping_tags(tags, name):
        return None
    lat, lon = element_latlon(el)
    if lat is None:
        return None
    if not in_metropolitan_france(lat, lon) or in_switzerland(lat, lon):
        return None
    types = shopping_types(tags)
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
    desc = tags.get("description:fr") or tags.get("description") or shopping_blurb(tags)
    item = {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "price_min": 0.0,
        "price_max": 0.0,
        "currency": "EUR",
        "types": types,
        "kind": map_kind(types),
        "category": map_category(types, 0.0),
        "description": desc,
        "address": addr or None,
        "photo_url": None,
        "photo_license": None,
        "website_url": website,
        "indoor": True,
        "source_name": "osm",
        "source_id": osm_id,
        "source_url": "https://www.openstreetmap.org/" + osm_id,
    }
    if item["category"] != "Shopping":
        return None
    if not is_priced_place(item):
        return None
    return item


def overpass_shop(query):
    body = ("data=" + urllib.parse.quote(query)).encode("utf-8")
    last = None
    for base in OVERPASS_MIRRORS:
        req = urllib.request.Request(
            base,
            data=body,
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            last = exc
            time.sleep(2)
    raise last


def fetch_one(query):
    last_err = None
    for attempt in range(3):
        try:
            data = overpass_shop(query)
            remark = data.get("remark")
            if remark:
                print("overpass remark", remark[:180], flush=True)
            return data.get("elements") or []
        except Exception as exc:
            last_err = exc
            time.sleep(6 * (attempt + 1))
    print("shopping fail", last_err, flush=True)
    return []


def fetch_shopping_around(lat, lon, radius_m=16000):
    malls = """
[out:json][timeout:90];
(
  nwr["shop"="mall"]["name"](around:%s,%s,%s);
  nwr["shop"="department_store"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon)
    frips = """
[out:json][timeout:90];
(
  nwr["shop"="second_hand"]["name"](around:%s,%s,%s);
  nwr["shop"="charity"]["name"](around:%s,%s,%s);
  nwr["shop"="clothes"]["second_hand"~"yes|only"]["name"](around:%s,%s,%s);
  nwr["name"~"friperie|Emmaüs|Emmaus|Kilo Shop|dépôt-vente|depot-vente",i]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon)
    clothes = """
[out:json][timeout:90];
(
  nwr["shop"="clothes"]["name"](around:%s,%s,%s);
  nwr["shop"="shoes"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon)
    return fetch_one(malls) + fetch_one(frips) + fetch_one(clothes)


def collect_elements(hubs=None, radius_m=18000):
    seen = set()
    elements = []
    for name, lat, lon in hubs or SHOP_HUBS:
        chunk = fetch_shopping_around(lat, lon, radius_m)
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
    print("osm shopping unique", len(elements), flush=True)
    return elements


HUB_PIN = {slugify(name): (lat, lon, 12.0) for name, lat, lon in SHOP_HUBS}


def pin_city(lat, lon, cities):
    for slug, (hlat, hlon, maxkm) in HUB_PIN.items():
        dlat = (hlat - lat) * 111.0
        dlon = (hlon - lon) * 85.0
        if (dlat * dlat + dlon * dlon) ** 0.5 <= maxkm:
            for city in cities:
                if (city.get("slug") or "") == slug and (city.get("country_code") or "") == "FR":
                    return city
    return nearest_city(lat, lon, cities)


def attach_photos(items):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from .commons_photos import licensed_photo

    cache = {}

    def one(item):
        photo, license_name = licensed_photo(
            item["name"],
            item["latitude"],
            item["longitude"],
            None,
            cache,
            allow_geo_backup=False,
            mode="shop",
        )
        if photo:
            item["photo_url"] = photo
            item["photo_license"] = license_name
        return item

    out = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(one, item) for item in items]
        for i, fut in enumerate(as_completed(futs), 1):
            out.append(fut.result())
            if i % 20 == 0 or i == len(items):
                n = sum(1 for x in out if x.get("photo_url"))
                print("photos", i, "/", len(items), "ok", n, flush=True)
    return out


def recategorize_existing(url, service_role):
    patterns = (
        "*friperie*",
        "*emmaus*",
        "*emmaüs*",
        "*centre commercial*",
        "*galerie marchande*",
        "*depot-vente*",
        "*dépôt-vente*",
        "*kiloshop*",
        "*kilo shop*",
    )
    or_bits = ",".join("name.ilike." + urllib.parse.quote(p) for p in patterns)
    rows = fetch_all(
        url,
        service_role,
        "outings",
        "id,name,category,kind",
        extra="&or=(" + or_bits + ")",
    )
    headers = {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    n = 0
    for row in rows:
        if (row.get("kind") or "") == "event":
            continue
        if not SHOP_NAME_RE.search(row.get("name") or ""):
            continue
        if row.get("category") == "Shopping":
            continue
        body = json.dumps({"category": "Shopping"}).encode("utf-8")
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/outings?id=eq." + row["id"],
            data=body,
            headers=headers,
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        n += 1
    print("recatégorisés Shopping", n, flush=True)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--hub")
    parser.add_argument("--radius-m", type=int, default=18000)
    parser.add_argument("--photos", action="store_true")
    args = parser.parse_args()

    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    if not args.hub:
        recategorize_existing(url, service_role)

    cities = fetch_all(
        url,
        service_role,
        "cities",
        "id,slug,name,latitude,longitude,country_code",
        extra="&country_code=eq.FR",
    )
    cities = [row for row in cities if row.get("latitude") is not None]
    print("villes FR", len(cities), flush=True)

    hubs = SHOP_HUBS
    if args.hub:
        hubs = [h for h in SHOP_HUBS if h[0].lower() == args.hub.lower()]
        if not hubs:
            raise SystemExit("hub inconnu: " + args.hub)

    items = []
    for el in collect_elements(hubs, args.radius_m):
        item = osm_to_shopping(el)
        if item:
            items.append(item)
    print("convertis", len(items), flush=True)
    if args.photos:
        items = attach_photos(items)

    existing_rows = fetch_all(
        url,
        service_role,
        "outings",
        "id,source_name,source_id,photo_url",
        extra="&source_name=eq.osm&category=eq." + urllib.parse.quote("Shopping"),
    )
    existing = {}
    for row in existing_rows:
        if row.get("source_id"):
            existing[(row.get("source_name"), row["source_id"])] = row

    payload = []
    name_seen = set()
    skipped = 0
    patched = 0
    from .fill_hike_photos import patch_photo
    from .quality import has_usable_photo

    for item in items:
        prev = existing.get((item["source_name"], item["source_id"]))
        if prev:
            if args.photos and item.get("photo_url") and not has_usable_photo(prev.get("photo_url")):
                patch_photo(url, service_role, prev["id"], item["photo_url"], item.get("photo_license"))
                patched += 1
            skipped += 1
            continue
        nk = re.sub(r"[^a-z0-9]+", " ", (item["name"] or "").lower()).strip()
        geo = (round(item["latitude"], 3), round(item["longitude"], 3), nk)
        if geo in name_seen:
            skipped += 1
            continue
        city = pin_city(item["latitude"], item["longitude"], cities)
        if not city or (city.get("country_code") or "") != "FR":
            skipped += 1
            continue
        row = to_outing_row(item, city["id"])
        if not row:
            skipped += 1
            continue
        row["currency"] = "EUR"
        row["category"] = "Shopping"
        payload.append(row)
        existing[(item["source_name"], item["source_id"])] = {"id": None, "photo_url": item.get("photo_url")}
        name_seen.add(geo)

    print("importables shopping", len(payload), "ignorés", skipped, "photos mises à jour", patched, flush=True)
    if payload:
        upsert_outings(url, service_role, payload)
    print("terminé shopping", len(payload), flush=True)


if __name__ == "__main__":
    main()
