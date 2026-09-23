# -*- coding: utf-8 -*-
"""Import Suisse : communes touristiques + POIs OSM avec tarif déclaré (pas d'invention)."""

import json
import os
import re
import time
import urllib.parse
import urllib.request

from .categories import map_category, map_kind, slugify
from .commons_photos import licensed_photo
from .quality import is_hotel_or_lodging, is_priced_place, resto_menu_span
from .run import load_env
from .supabase_io import fetch_all, to_outing_row, upsert_outings

OVERPASS = "https://overpass-api.de/api/interpreter"
UA = "Sinki/1.0 (https://sinki-sorties.fly.dev)"
CHARGE_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
HOTEL_TOURISM = {
    "hotel",
    "hostel",
    "guest_house",
    "motel",
    "chalet",
    "apartment",
    "alpine_hut",
    "wilderness_hut",
    "camp_site",
}

# Contour simplifié (pas les enclaves). Sert à écarter France / Allemagne / Autriche / Italie.
CH_RING = [
    (6.02, 46.35), (6.09, 46.13), (6.18, 46.20), (6.20, 46.28), (6.55, 46.28),
    (6.85, 45.86), (7.15, 45.90), (7.70, 45.92), (8.45, 46.05), (8.80, 45.84),
    (9.25, 46.25), (10.28, 46.45), (10.45, 46.85), (9.85, 47.25), (9.55, 47.52),
    (9.05, 47.70), (8.55, 47.58), (8.10, 47.70), (7.62, 47.62), (7.50, 47.60),
    (7.05, 47.50), (6.75, 47.35), (6.15, 46.55),
]


def in_switzerland(lat, lon):
    inside = False
    n = len(CH_RING)
    for i in range(n):
        x1, y1 = CH_RING[i]
        x2, y2 = CH_RING[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            xinters = (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1
            if lon < xinters:
                inside = not inside
    return inside


SWISS_CITIES = [
    ("Genève", "geneve", 46.2044, 6.1432),
    ("Zurich", "zurich", 47.3769, 8.5417),
    ("Berne", "berne", 46.9480, 7.4474),
    ("Bâle", "bale", 47.5596, 7.5886),
    ("Lausanne", "lausanne", 46.5197, 6.6323),
    ("Lucerne", "lucerne", 47.0502, 8.3093),
    ("Lugano", "lugano", 46.0037, 8.9511),
    ("Saint-Gall", "saint-gall", 47.4245, 9.3767),
    ("Winterthour", "winterthour", 47.5001, 8.7241),
    ("Fribourg", "fribourg-ch", 46.8065, 7.1617),
    ("Sion", "sion-ch", 46.2331, 7.3606),
    ("Neuchâtel", "neuchatel", 46.9930, 6.9293),
    ("Bienne", "bienne", 47.1368, 7.2467),
    ("Thoune", "thoune", 46.7580, 7.6280),
    ("Montreux", "montreux-ch", 46.4312, 6.9107),
    ("Vevey", "vevey", 46.4628, 6.8434),
    ("Nyon", "nyon", 46.3833, 6.2390),
    ("Yverdon-les-Bains", "yverdon-les-bains", 46.7785, 6.6410),
    ("Interlaken", "interlaken", 46.6863, 7.8632),
    ("Zermatt", "zermatt", 46.0207, 7.7491),
    ("Coire", "coire", 46.8508, 9.5320),
    ("Locarno", "locarno", 46.1709, 8.7995),
    ("Bellinzone", "bellinzone", 46.1928, 9.0170),
    ("Schaffhouse", "schaffhouse", 47.6973, 8.6349),
    ("Saint-Moritz", "saint-moritz", 46.4908, 9.8355),
    ("Grindelwald", "grindelwald", 46.6242, 8.0364),
    ("Davos", "davos", 46.8027, 9.8360),
    ("La Chaux-de-Fonds", "la-chaux-de-fonds", 47.0996, 6.8256),
    ("Engelberg", "engelberg", 46.8197, 8.4076),
    ("Lauterbrunnen", "lauterbrunnen", 46.5936, 7.9076),
    ("Wengen", "wengen", 46.6056, 7.9214),
    ("Saas-Fee", "saas-fee", 46.1089, 7.9274),
    ("Verbier", "verbier", 46.0969, 7.2286),
    ("Arosa", "arosa", 46.7779, 9.6790),
    ("Kandersteg", "kandersteg", 46.4953, 7.6717),
    ("Andermatt", "andermatt", 46.6356, 8.5936),
    ("Appenzell", "appenzell", 47.3309, 9.4090),
    ("Flims", "flims", 46.8375, 9.2844),
    ("Pontresina", "pontresina", 46.4950, 9.9010),
    ("Meiringen", "meiringen", 46.7261, 8.1840),
    ("Crans-Montana", "crans-montana", 46.3119, 7.4795),
]


def _headers(service_role, prefer="return=representation"):
    return {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def upsert_swiss_cities(url, service_role):
    existing = {
        row["slug"]: row
        for row in fetch_all(url, service_role, "cities", "id,slug,name,country_code,latitude,longitude")
    }
    created = []
    for name, slug, lat, lon in SWISS_CITIES:
        prev = existing.get(slug)
        if prev and prev.get("country_code") == "CH":
            created.append(prev)
            continue
        body = json.dumps(
            {
                "name": name,
                "slug": slug,
                "country_code": "CH",
                "latitude": lat,
                "longitude": lon,
                "is_active": True,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/cities?on_conflict=slug",
            data=body,
            headers=_headers(service_role, "resolution=merge-duplicates,return=representation"),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            rows = json.loads(resp.read().decode() or "[]")
        row = rows[0] if rows else {"slug": slug, "name": name, "latitude": lat, "longitude": lon}
        created.append(row)
        existing[slug] = row
        print("ville", name, flush=True)
    return created


def overpass(query):
    req = urllib.request.Request(
        OVERPASS,
        data=query.encode("utf-8"),
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
    )
    body = "data=" + urllib.parse.quote(query)
    req = urllib.request.Request(
        OVERPASS,
        data=body.encode("utf-8"),
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def fetch_osm_chunk(south, west, north, east):
    bbox = "%s,%s,%s,%s" % (south, west, north, east)
    query = """
[out:json][timeout:70];
(
  nwr["tourism"~"museum|attraction|zoo|theme_park|gallery|aquarium"]["name"]["fee"](%s);
  nwr["tourism"~"museum|attraction|zoo|theme_park|gallery|aquarium"]["name"]["charge"](%s);
  nwr["leisure"~"park|nature_reserve"]["name"]["fee"="no"](%s);
  nwr["tourism"="viewpoint"]["name"]["fee"="no"](%s);
);
out center tags;
""" % (bbox, bbox, bbox, bbox)
    last_err = None
    for attempt in range(4):
        try:
            return overpass(query).get("elements") or []
        except Exception as exc:
            last_err = exc
            time.sleep(8 * (attempt + 1))
    print("overpass fail", south, west, last_err, flush=True)
    return []


def parse_price(tags):
    amenity = (tags.get("amenity") or "").lower().strip()
    if amenity in ("restaurant", "cafe", "fast_food", "ice_cream", "food_court", "biergarten"):
        span = resto_menu_span(tags)
        if not span:
            return None
        blob = " ".join(str(v) for v in (tags or {}).values()).lower()
        cur = "EUR" if ("eur" in blob or "€" in blob) else "CHF"
        return span[0], span[1], cur
    if is_hike(tags):
        fee = (tags.get("fee") or "").lower().strip()
        charge = tags.get("charge") or tags.get("charge:adult") or ""
        if fee in ("yes", "true") and not charge:
            return None
        if charge:
            nums = [float(x.replace(",", ".")) for x in CHARGE_RE.findall(str(charge))]
            if nums:
                currency = "EUR" if "eur" in str(charge).lower() or "€" in str(charge) else "CHF"
                return min(nums), max(nums), currency
        return 0.0, 0.0, "CHF"
    fee = (tags.get("fee") or "").lower().strip()
    charge = " ".join(
        str(tags.get(key) or "")
        for key in ("charge", "charge:adult", "fee:adult", "payment:charge")
    )
    blob = (charge + " " + fee).lower()
    if fee in ("no", "free", "none", "0"):
        return 0.0, 0.0, "CHF"
    nums = [float(x.replace(",", ".")) for x in CHARGE_RE.findall(charge)]
    if not nums:
        return None
    if "eur" in blob or "€" in charge:
        currency = "EUR"
    else:
        currency = "CHF"
    lo, hi = min(nums), max(nums)
    if hi > 500:
        return None
    return lo, hi, currency


def is_hike(tags):
    if tags.get("route") == "hiking":
        return True
    if tags.get("natural") == "peak":
        return True
    if tags.get("tourism") == "viewpoint":
        return True
    if tags.get("sac_scale") or tags.get("osmc:symbol"):
        return True
    return False


def element_latlon(el):
    if "lat" in el and "lon" in el:
        return el["lat"], el["lon"]
    center = el.get("center") or {}
    if "lat" in center:
        return center["lat"], center["lon"]
    return None, None


def osm_types(tags):
    bits = [
        tags.get("tourism") or "",
        tags.get("leisure") or "",
        tags.get("amenity") or "",
        tags.get("natural") or "",
        tags.get("route") or "",
        tags.get("sport") or "",
        tags.get("shop") or "",
    ]
    if is_hike(tags):
        bits.extend(["hike", "hiking", "walk"])
        if tags.get("natural") == "peak":
            bits.append("peak")
        if tags.get("tourism") == "viewpoint":
            bits.append("viewpoint")
    elif tags.get("fee") == "no" and (tags.get("leisure") or tags.get("tourism") == "viewpoint"):
        bits.append("park")
        bits.append("walk")
    return bits


def nearest_city(lat, lon, cities):
    best = None
    best_d = 80
    for city in cities:
        dlat = (city["latitude"] - lat) * 111
        dlon = (city["longitude"] - lon) * 85
        dist = (dlat * dlat + dlon * dlon) ** 0.5
        if dist < best_d:
            best_d = dist
            best = city
    return best


def osm_to_item(el, photo_cache):
    tags = el.get("tags") or {}
    name = tags.get("name:fr") or tags.get("name")
    if not name or len(name.strip()) < 3:
        return None
    if (tags.get("tourism") or "") in HOTEL_TOURISM:
        return None
    if is_hotel_or_lodging(list(tags.values())):
        return None
    lat, lon = element_latlon(el)
    if lat is None:
        return None
    parsed = parse_price(tags)
    if parsed is None:
        return None
    country = (
        tags.get("addr:country")
        or tags.get("addr:countrycode")
        or tags.get("is_in:country_code")
        or ""
    ).upper()
    if country in ("FR", "FRA", "FRANCE", "DE", "DEU", "AT", "AUT", "IT", "ITA", "LI"):
        return None
    if not in_switzerland(lat, lon):
        return None
    price_min, price_max, currency = parsed
    types = osm_types(tags)
    website = tags.get("website") or tags.get("contact:website") or tags.get("url")
    addr = ", ".join(
        p for p in (tags.get("addr:street"), tags.get("addr:housenumber"), tags.get("addr:city") or tags.get("addr:place")) if p
    )
    osm_id = "%s/%s" % (el.get("type"), el.get("id"))
    indoor = False if is_hike(tags) else None
    if tags.get("indoor") == "yes":
        indoor = True
    elif tags.get("indoor") == "no":
        indoor = False
    photo, license_name = licensed_photo(name.strip(), lat, lon, tags, photo_cache)
    bits = []
    if tags.get("ele"):
        bits.append("Altitude %s m." % tags.get("ele"))
    if tags.get("sac_scale"):
        bits.append("Difficulté SAC : %s." % tags.get("sac_scale"))
    desc = tags.get("description:fr") or tags.get("description") or " ".join(bits) or None
    return {
        "name": name.strip(),
        "latitude": lat,
        "longitude": lon,
        "price_min": price_min,
        "price_max": price_max,
        "currency": currency,
        "types": types,
        "kind": map_kind(types),
        "category": map_category(types, price_min),
        "description": desc,
        "address": addr or None,
        "photo_url": photo,
        "photo_license": license_name,
        "website_url": website,
        "indoor": indoor,
        "source_name": "osm",
        "source_id": osm_id,
        "source_url": "https://www.openstreetmap.org/" + osm_id,
    }


def fetch_hikes_around(lat, lon):
    query = """
[out:json][timeout:55];
(
  node["natural"="peak"]["name"](around:22000,%s,%s);
  node["tourism"="viewpoint"]["name"](around:18000,%s,%s);
  relation["route"="hiking"]["name"]["network"~"nwn|rwn|lwn"](around:18000,%s,%s);
);
out center tags 80;
""" % (lat, lon, lat, lon, lat, lon)
    last_err = None
    for attempt in range(3):
        try:
            return overpass(query).get("elements") or []
        except Exception as exc:
            last_err = exc
            time.sleep(6 * (attempt + 1))
    print("hikes fail", lat, lon, last_err, flush=True)
    return []


def main():
    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    cities = upsert_swiss_cities(url, service_role)
    cities = [
        row
        for row in fetch_all(url, service_role, "cities", "id,slug,name,latitude,longitude,country_code")
        if (row.get("country_code") or "").strip() == "CH" and row.get("latitude") is not None
    ]
    print("villes CH", len(cities), flush=True)

    cache_path = os.path.join("data", "swiss_osm_elements.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            elements = json.load(fh)
        print("cache OSM", len(elements), flush=True)
    else:
        seen_osm = set()
        elements = []
        lats = [45.82, 46.55, 47.25, 47.85]
        lons = [5.96, 7.4, 8.9, 10.55]
        for i in range(len(lats) - 1):
            for j in range(len(lons) - 1):
                chunk = fetch_osm_chunk(lats[i], lons[j], lats[i + 1], lons[j + 1])
                print("bbox", lats[i], lons[j], "n", len(chunk), flush=True)
                for el in chunk:
                    osm_key = (el.get("type"), el.get("id"))
                    if osm_key in seen_osm:
                        continue
                    seen_osm.add(osm_key)
                    elements.append(el)
                time.sleep(2)
        os.makedirs("data", exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(elements, fh)
        print("cache écrit", len(elements), flush=True)

    hike_path = os.path.join("data", "swiss_osm_hikes.json")
    if os.path.exists(hike_path):
        with open(hike_path, encoding="utf-8") as fh:
            hikes = json.load(fh)
        print("cache rando", len(hikes), flush=True)
    else:
        seen_h = set()
        hikes = []
        for city in cities:
            chunk = fetch_hikes_around(city["latitude"], city["longitude"])
            print("rando", city.get("name"), len(chunk), flush=True)
            for el in chunk:
                osm_key = (el.get("type"), el.get("id"))
                if osm_key in seen_h:
                    continue
                seen_h.add(osm_key)
                hikes.append(el)
            time.sleep(1.2)
        os.makedirs("data", exist_ok=True)
        with open(hike_path, "w", encoding="utf-8") as fh:
            json.dump(hikes, fh)
        print("cache rando écrit", len(hikes), flush=True)
    seen_el = {(el.get("type"), el.get("id")) for el in elements}
    for el in hikes:
        osm_key = (el.get("type"), el.get("id"))
        if osm_key not in seen_el:
            elements.append(el)
            seen_el.add(osm_key)

    photo_cache = {}
    existing = fetch_all(url, service_role, "outings", "id,source_name,source_id,latitude,longitude,photo_url", extra="&source_name=eq.osm")
    del_headers = {"apikey": service_role, "Authorization": "Bearer " + service_role}
    kept = []
    for row in existing:
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (TypeError, ValueError):
            continue
        if not in_switzerland(lat, lon):
            req = urllib.request.Request(
                url.rstrip("/") + "/rest/v1/outings?id=eq." + row["id"],
                headers=del_headers,
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
            continue
        photo = row.get("photo_url") or ""
        if photo and "commons.wikimedia.org" not in photo:
            patch = json.dumps({"photo_url": None, "photo_license": None}).encode("utf-8")
            preq = urllib.request.Request(
                url.rstrip("/") + "/rest/v1/outings?id=eq." + row["id"],
                data=patch,
                headers={**del_headers, "Content-Type": "application/json", "Prefer": "return=minimal"},
                method="PATCH",
            )
            with urllib.request.urlopen(preq, timeout=30) as resp:
                resp.read()
        kept.append(row)
    seen = {(r.get("source_name"), r.get("source_id")) for r in kept if r.get("source_id")}
    payload = []
    skipped = 0
    name_seen = set()
    for el in elements:
        item = osm_to_item(el, photo_cache)
        if not item or not is_priced_place(item):
            skipped += 1
            continue
        nk = re.sub(r"[^a-z0-9]+", " ", (item["name"] or "").lower()).strip()
        geo = (round(item["latitude"], 3), round(item["longitude"], 3), nk)
        if geo in name_seen:
            skipped += 1
            continue
        if (item["source_name"], item["source_id"]) in seen:
            skipped += 1
            continue
        city = nearest_city(item["latitude"], item["longitude"], cities)
        if not city:
            skipped += 1
            continue
        row = to_outing_row(item, city["id"])
        if not row:
            skipped += 1
            continue
        payload.append(row)
        seen.add((item["source_name"], item["source_id"]))
        name_seen.add(geo)

    print("importables", len(payload), "ignorés", skipped, flush=True)
    if payload:
        upsert_outings(url, service_role, payload)
    print("ok suisse", len(payload), flush=True)


if __name__ == "__main__":
    main()
