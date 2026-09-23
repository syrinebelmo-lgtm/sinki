# -*- coding: utf-8 -*-
"""Randonnées France : OSM réels + photo Commons libre obligatoire. Pas d’invention."""

import json
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from .categories import map_category, map_kind
from .commons_photos import licensed_photo
from .quality import has_usable_photo, is_complete, is_hotel_or_lodging, is_priced_place
from .run import load_env
from .supabase_io import fetch_all, to_outing_row, upsert_outings
from .switzerland import (
    HOTEL_TOURISM,
    UA,
    element_latlon,
    in_switzerland,
    is_hike,
    nearest_city,
    osm_types,
    overpass,
)

FR_HUBS = [
    ("Chamonix", 45.9237, 6.8694),
    ("Saint-Gervais-les-Bains", 45.8928, 6.7136),
    ("Annecy", 45.8992, 6.1294),
    ("La Clusaz", 45.9040, 6.4230),
    ("Morzine", 46.1790, 6.7090),
    ("Chambéry", 45.5646, 5.9178),
    ("Albertville", 45.6758, 6.3926),
    ("Bourg-Saint-Maurice", 45.6180, 6.7710),
    ("Val-d'Isère", 45.4480, 6.9800),
    ("Pralognan-la-Vanoise", 45.3820, 6.7220),
    ("Grenoble", 45.1885, 5.7245),
    ("La Grave", 45.0460, 6.3060),
    ("Briançon", 44.8992, 6.6435),
    ("Serre Chevalier", 44.9330, 6.5660),
    ("Gap", 44.5590, 6.0790),
    ("Embrun", 44.5640, 6.4960),
    ("Barcelonnette", 44.3860, 6.6540),
    ("Digne-les-Bains", 44.0920, 6.2320),
    ("Castellane", 43.8470, 6.5130),
    ("La Palud-sur-Verdon", 43.7800, 6.3420),
    ("Nice", 43.7102, 7.2620),
    ("Menton", 43.7765, 7.5046),
    ("Cassis", 43.2140, 5.5380),
    ("Marseille", 43.2965, 5.3698),
    ("Cauterets", 42.8890, -0.1150),
    ("Gavarnie", 42.7350, -0.0100),
    ("Luz-Saint-Sauveur", 42.8720, -0.0030),
    ("Saint-Lary-Soulan", 42.8180, 0.3230),
    ("Bagnères-de-Luchon", 42.7910, 0.5930),
    ("Ax-les-Thermes", 42.7200, 1.8390),
    ("Font-Romeu", 42.5040, 2.0480),
    ("Céret", 42.4880, 2.7490),
    ("Corte", 42.3060, 9.1510),
    ("Calvi", 42.5660, 8.7570),
    ("Porto-Vecchio", 41.5910, 9.2790),
    ("Ajaccio", 41.9192, 8.7386),
    ("Le Puy-en-Velay", 45.0433, 3.8852),
    ("Florac", 44.3240, 3.5980),
    ("Millau", 44.0980, 3.0780),
    ("Gérardmer", 48.0730, 6.8780),
    ("Les Rousses", 46.4860, 6.0610),
]

FORBIDDEN_COUNTRY = {
    "CH", "CHE", "SUISSE", "SWITZERLAND",
    "DE", "DEU", "AT", "AUT", "IT", "ITA", "ES", "ESP",
    "BE", "BEL", "LU", "LUX", "AD", "AND", "GB", "UK", "MC", "MCO",
}


def in_chamonix_valley(lat, lon):
    return 45.80 <= lat <= 46.035 and 6.70 <= lon <= 7.12


def in_aosta_italy(lat, lon):
    return 45.60 <= lat <= 45.90 and 6.90 <= lon <= 7.45


def in_metropolitan_france(lat, lon):
    if 41.32 <= lat <= 43.05 and 8.15 <= lon <= 9.57:
        return True
    if not (42.28 <= lat <= 51.12 and -5.15 <= lon <= 8.23):
        return False
    if in_chamonix_valley(lat, lon):
        return True
    if in_aosta_italy(lat, lon):
        return False
    if in_switzerland(lat, lon):
        return False
    if lon > 7.55 and lat < 44.05:
        return False
    if 42.43 <= lat <= 42.66 and 1.40 <= lon <= 1.79:
        return False
    return True


def photo_hint_score(el):
    tags = el.get("tags") or {}
    score = 0
    if tags.get("wikimedia_commons"):
        score += 4
    if tags.get("wikidata"):
        score += 3
    if tags.get("wikipedia"):
        score += 2
    if tags.get("natural") == "peak":
        score += 1
    return score


def osm_to_france_hike(el, photo_cache):
    tags = el.get("tags") or {}
    if not is_hike(tags):
        return None
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
    country = (
        (tags.get("addr:country") or "")
        + " "
        + (tags.get("addr:countrycode") or "")
        + " "
        + (tags.get("is_in:country_code") or "")
        + " "
        + (tags.get("is_in:country") or "")
    ).upper()
    if any(tok in country for tok in FORBIDDEN_COUNTRY):
        if "FR" not in country.split() and "FRA" not in country and "FRANCE" not in country:
            return None
    if not in_metropolitan_france(lat, lon):
        return None
    if in_switzerland(lat, lon):
        return None
    types = osm_types(tags)
    photo, license_name = licensed_photo(name.strip(), lat, lon, tags, photo_cache)
    if not has_usable_photo(photo) or "commons.wikimedia.org" not in (photo or ""):
        return None
    website = tags.get("website") or tags.get("contact:website") or tags.get("url")
    addr = ", ".join(
        p for p in (tags.get("addr:street"), tags.get("addr:housenumber"), tags.get("addr:city") or tags.get("addr:place")) if p
    )
    osm_id = "%s/%s" % (el.get("type"), el.get("id"))
    bits = []
    if tags.get("ele"):
        bits.append("Altitude %s m." % tags.get("ele"))
    if tags.get("sac_scale"):
        bits.append("Difficulté SAC : %s." % tags.get("sac_scale"))
    desc = tags.get("description:fr") or tags.get("description") or " ".join(bits) or None
    item = {
        "name": name.strip(),
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
        "photo_url": photo,
        "photo_license": license_name,
        "website_url": website,
        "indoor": False,
        "source_name": "osm",
        "source_id": osm_id,
        "source_url": "https://www.openstreetmap.org/" + osm_id,
    }
    if item["category"] != "Randonnées":
        return None
    if not is_complete(item) or not is_priced_place(item):
        return None
    return item


def fetch_france_hikes_around(lat, lon):
    query = """
[out:json][timeout:70];
area["ISO3166-1"="FR"][admin_level=2]->.fr;
(
  node["natural"="peak"]["name"](area.fr)(around:24000,%s,%s);
  node["tourism"="viewpoint"]["name"](area.fr)(around:20000,%s,%s);
  relation["route"="hiking"]["name"]["network"~"nwn|rwn|lwn"](area.fr)(around:20000,%s,%s);
);
out center tags 80;
""" % (lat, lon, lat, lon, lat, lon)
    last_err = None
    for attempt in range(3):
        try:
            return overpass(query).get("elements") or []
        except Exception as exc:
            last_err = exc
            time.sleep(7 * (attempt + 1))
    print("hikes FR fail", lat, lon, last_err, flush=True)
    from .switzerland import fetch_hikes_around
    fallback = fetch_hikes_around(lat, lon)
    kept = []
    for el in fallback:
        plat, plon = element_latlon(el)
        if plat is None:
            continue
        if in_metropolitan_france(plat, plon):
            kept.append(el)
    return kept


def collect_elements():
    cache_path = os.path.join("data", "france_osm_hikes.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            elements = json.load(fh)
        print("cache rando FR", len(elements), flush=True)
        return elements
    seen = set()
    elements = []
    for name, lat, lon in FR_HUBS:
        chunk = fetch_france_hikes_around(lat, lon)
        added = 0
        for el in chunk:
            osm_key = (el.get("type"), el.get("id"))
            if osm_key in seen:
                continue
            seen.add(osm_key)
            elements.append(el)
            added += 1
        print("hub", name, "osm", added, "total", len(elements), flush=True)
        time.sleep(1.3)
    os.makedirs("data", exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(elements, fh)
    print("cache rando FR écrit", len(elements), flush=True)
    return elements


def convert_with_photos(elements):
    cache = {}
    elements = sorted(elements, key=photo_hint_score, reverse=True)
    items = []
    failed = 0

    def one(el):
        return osm_to_france_hike(el, cache)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(one, el) for el in elements]
        for i, fut in enumerate(as_completed(futs), 1):
            item = fut.result()
            if item:
                items.append(item)
            else:
                failed += 1
            if i % 80 == 0:
                print("photos", i, "/", len(elements), "ok", len(items), "sans", failed, flush=True)
    print("convertis avec photo", len(items), "ignorés", failed, flush=True)
    return items


def five_verifications(url, service_role, payload, cities):
    city_by_id = {c["id"]: c for c in cities}
    errors = []

    # 1. Photo Commons + licence + catégorie
    for row in payload:
        if row.get("category") != "Randonnées":
            errors.append("v1 catégorie " + str(row.get("name")))
        if not has_usable_photo(row.get("photo_url")) or "commons.wikimedia.org" not in (row.get("photo_url") or ""):
            errors.append("v1 photo " + str(row.get("name")))
        if (row.get("currency") or "") != "EUR":
            errors.append("v1 devise " + str(row.get("name")))
        if float(row.get("price_min") or 0) < 0:
            errors.append("v1 prix " + str(row.get("name")))

    # 2. GPS France, pas Suisse
    for row in payload:
        lat, lon = float(row["latitude"]), float(row["longitude"])
        if not in_metropolitan_france(lat, lon) or in_switzerland(lat, lon):
            errors.append("v2 gps " + str(row.get("name")))

    # 3. Ville FR uniquement
    for row in payload:
        city = city_by_id.get(row.get("city_id"))
        if not city or (city.get("country_code") or "") != "FR":
            errors.append("v3 ville " + str(row.get("name")))

    # 4. Source OSM unique
    seen = set()
    for row in payload:
        key = (row.get("source_name"), row.get("source_id"))
        if key in seen:
            errors.append("v4 doublon " + str(row.get("source_id")))
        seen.add(key)
        if row.get("source_name") != "osm":
            errors.append("v4 source " + str(row.get("name")))

    # 5. Relecture base après upsert
    if url:
        db = fetch_all(
            url,
            service_role,
            "outings",
            "id,name,latitude,longitude,photo_url,photo_license,category,currency,city_id,source_name,source_id",
            extra="&source_name=eq.osm&category=eq." + urllib.parse.quote("Randonnées"),
        )
        fr_ids = {c["id"] for c in cities}
        fr_rows = [r for r in db if r.get("city_id") in fr_ids]
        if len(fr_rows) < 20:
            errors.append("v5 trop peu en base: %s" % len(fr_rows))
        sample = fr_rows[:80]
        for row in sample:
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
            except (TypeError, ValueError):
                errors.append("v5 gps manquant " + str(row.get("name")))
                continue
            if not in_metropolitan_france(lat, lon) or in_switzerland(lat, lon):
                errors.append("v5 hors France " + str(row.get("name")))
            if not has_usable_photo(row.get("photo_url")) or "commons.wikimedia.org" not in (row.get("photo_url") or ""):
                errors.append("v5 photo " + str(row.get("name")))
            if (row.get("currency") or "") != "EUR":
                errors.append("v5 devise " + str(row.get("name")))

    uniq = []
    seen_e = set()
    for err in errors:
        if err in seen_e:
            continue
        seen_e.add(err)
        uniq.append(err)
        if len(uniq) >= 25:
            break
    return uniq


def main():
    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    cities = [
        row
        for row in fetch_all(url, service_role, "cities", "id,slug,name,latitude,longitude,country_code")
        if (row.get("country_code") or "").strip() == "FR" and row.get("latitude") is not None
    ]
    print("villes FR", len(cities), flush=True)
    if len(cities) < 50:
        raise SystemExit("catalogue villes FR insuffisant")

    elements = collect_elements()
    items = convert_with_photos(elements)
    existing = {
        (r.get("source_name"), r.get("source_id"))
        for r in fetch_all(url, service_role, "outings", "source_name,source_id", extra="&source_name=eq.osm")
        if r.get("source_id")
    }

    payload = []
    name_seen = set()
    skipped = 0
    for item in items:
        if (item["source_name"], item["source_id"]) in existing:
            skipped += 1
            continue
        nk = re.sub(r"[^a-z0-9]+", " ", (item["name"] or "").lower()).strip()
        geo = (round(item["latitude"], 3), round(item["longitude"], 3), nk)
        if geo in name_seen:
            skipped += 1
            continue
        city = nearest_city(item["latitude"], item["longitude"], cities)
        if not city or (city.get("country_code") or "") != "FR":
            skipped += 1
            continue
        row = to_outing_row(item, city["id"])
        if not row or not has_usable_photo(row.get("photo_url")):
            skipped += 1
            continue
        row["currency"] = "EUR"
        payload.append(row)
        existing.add((item["source_name"], item["source_id"]))
        name_seen.add(geo)

    print("importables FR", len(payload), "ignorés", skipped, flush=True)
    pre = five_verifications(None, None, payload, cities)
    if pre:
        print("verif pré-upsert", pre[:10], flush=True)
        raise SystemExit("verif 1-4 KO avant écriture")
    print("verif 1-4 OK", len(payload), flush=True)

    if payload:
        upsert_outings(url, service_role, payload)
    post = five_verifications(url, service_role, payload, cities)
    if post:
        print("verif post", post[:15], flush=True)
        raise SystemExit("verif 5 KO")
    print("verif 1-5 OK randos FR", len(payload), flush=True)


if __name__ == "__main__":
    main()
