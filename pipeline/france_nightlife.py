# -*- coding: utf-8 -*-
"""Boîtes, bars, karaoké OSM réels. Concerts / cabarets → culture. Pas d’invention de tarifs."""

import json
import os
import re
import time
import urllib.parse
import urllib.request

from .categories import map_category
from .france_hikes import in_metropolitan_france
from .france_places import SKIP_NAME
from .france_shopping import SHOP_HUBS, fetch_one, pin_city
from .quality import is_hotel_or_lodging, is_priced_place
from .rest_countries import REST_CURRENCY, REST_OSM
from .run import load_env
from .supabase_io import fetch_all, patch_outing_fields, to_outing_row, upsert_outings
from .switzerland import element_latlon, in_switzerland, nearest_city

SKIP_NIGHT = re.compile(
    r"\b(tabac|pmu|loto|betting|poney|équestre|equestre|mcdonald|hotel|hôtel)\b",
    re.I,
)
DANCE_SCHOOL = re.compile(
    r"\b(studio|école|ecole|school|cours|conservatoire|centre .{0,24}danse|"
    r"tango|salsa|bachata|milonga|ifpro|nilanthi)\b",
    re.I,
)
CULTURE_SHOW = re.compile(
    r"\b(concerts?|cabaret|jazz|op[eé]ra|ballet|th[eé][aâ]tre|theatre|theater|"
    r"philharmonie|spectacle|moulin rouge|paradis latin|new morning|"
    r"cin[eé]ma|cinema)\b",
    re.I,
)
SHOW_BUT_DRINK = re.compile(
    r"\b(bar|pub|caf[eé]|comptoir|brasserie|c[aà]\s*ph[eê]|coffee)\b",
    re.I,
)
DANCE_SCHOOL_MOVE = re.compile(
    r"(?:[eé]cole|ecole|studio|acad[eé]mie|institut|conservatoire|cfa|centre)\b.{0,40}\bdanse\b|"
    r"\bdanse\b.{0,24}\b(?:[eé]cole|studio|acad[eé]mie)\b|"
    r"dance\s+(?:school|academy|studio)|"
    r"studio\s+nilanthi|\bnilanthi\b|"
    r"\bmilonga\b|"
    r"cours de danse|"
    r"espace\s+(?:de\s+)?danse|atelier\s+chor[eé]graphique|\bchor[eé]graphique\b",
    re.I,
)
NIGHT_CLUBISH = re.compile(
    r"bo[iî]te|nightclub|discoth|club de nuit|karaoke|karaok[eé]|rooftop",
    re.I,
)

BLURB = {
    "nightclub": "Boîte de nuit.",
    "bar": "Bar.",
    "pub": "Pub.",
    "karaoke": "Karaoké.",
    "dance": "Dancing.",
    "biergarten": "Guinguette / biergarten.",
}

WORLD_SLUGS = (
    "geneve", "zurich", "lausanne", "bale", "berne", "zermatt", "interlaken", "lucerne",
    "bruxelles", "anvers", "gand", "bruges", "liege", "namur",
    "roma-it", "milano-it", "firenze-it", "venezia-it", "napoli-it", "torino-it",
    "madrid-es", "barcelona-es", "valencia-es", "seville-es", "malaga-es", "palma-de-mallorca-es",
    "berlin-de", "munchen-landeshauptstadt-de", "hamburg-freie-und-hansestadt-de", "koln-de", "frankfurt-am-main-de",
    "london-gb", "manchester-gb", "edinburgh-gb", "birmingham-gb", "glasgow-gb", "liverpool-gb",
    "lisbon-pt", "porto-pt", "faro-pt",
    "amsterdam-nl", "rotterdam-nl", "utrecht-nl", "den-haag-nl",
    "athens-gr", "thessaloniki-gr", "irakleio-gr",
    "vienna-at", "salzburg-at", "innsbruck-at",
    "zagreb-hr", "split-hr", "dubrovnik-hr",
    "prague-cz", "brno-cz", "ostrava-cz",
    "budapest-hu", "debrecen-hu", "szeged-hu",
    "warsaw-pl", "krakow-pl", "gdansk-pl",
    "dublin-ie", "cork-ie", "galway-ie",
    "copenhagen-dk", "aarhus-dk", "odense-dk",
    "stockholm-se", "gothenburg-se", "malmo-se",
    "oslo-no", "bergen-no", "trondheim-no",
    "helsinki-fi", "tampere-fi", "turku-fi",
    "bucharest-ro", "cluj-napoca-ro", "brasov-ro",
    "sofia-bg", "plovdiv-bg", "varna-bg",
    "bratislava-sk", "kosice-sk",
    "ljubljana-si", "maribor-si",
    "luxembourg-lu",
    "tallinn-ee", "tartu-ee",
    "riga-lv", "daugavpils-lv",
    "vilnius-lt", "kaunas-lt",
    "belgrade-rs", "novi-sad-rs",
    "sarajevo-ba", "mostar-ba",
    "podgorica-me", "kotor-me",
    "tirana-al", "durres-al",
    "nicosia-cy", "limassol-cy",
    "valletta-mt",
    "reykjavik-is",
    "andorra-la-vella-ad",
    "vaduz-li",
    "monaco-mc",
    "skopje-mk", "ohrid-mk",
    "pristina-xk", "prizren-xk",
    "chisinau-md",
    "new-york-city-us", "los-angeles-us", "miami-us", "las-vegas-us", "chicago-us",
    "marrakech-ma", "casablanca-ma", "rabat-ma", "fes-ma", "agadir-ma",
    "tokyo-jp", "osaka-jp", "kyoto-jp",
    "montreal-ca", "toronto-ca", "vancouver-ca", "quebec-ca",
    "bangkok-th", "chiang-mai-th", "phuket-th", "pattaya-th",
)

EURO = {
    "FR", "BE", "IT", "ES", "DE", "PT", "NL", "GR", "AT", "IE", "LU", "CY", "MT",
    "AD", "MC", "SI", "SK", "EE", "LV", "LT", "FI", "HR", "ME",
}


def currency_for(cc):
    cc = (cc or "").upper()
    if cc in REST_CURRENCY:
        return REST_CURRENCY[cc]
    if cc in EURO:
        return "EUR"
    return {"GB": "GBP", "CH": "CHF", "US": "USD", "JP": "JPY", "CA": "CAD", "TH": "THB", "MA": "MAD"}.get(cc, "EUR")


def night_types(tags, name):
    amenity = (tags.get("amenity") or "").strip().lower()
    leisure = (tags.get("leisure") or "").strip().lower()
    karaoke = (tags.get("karaoke") or "").strip().lower()
    bits = []
    if amenity == "nightclub" or leisure == "nightclub":
        bits.extend(["nightclub", "bar"])
    elif leisure == "dance":
        if DANCE_SCHOOL.search(name or ""):
            return []
        bits.extend(["nightclub", "dancing"])
    elif amenity == "karaoke_box" or karaoke in ("yes", "only"):
        bits.extend(["karaoke", "bar"])
    elif amenity == "pub":
        bits.extend(["pub", "bar"])
    elif amenity == "bar":
        bits.extend(["bar"])
    elif amenity == "biergarten":
        bits.extend(["bar", "pub"])
    return bits


def osm_to_night(el, require_fr=True):
    tags = el.get("tags") or {}
    name = (tags.get("name:fr") or tags.get("name") or "").strip()
    if len(name) < 3 or SKIP_NAME.search(name) or SKIP_NIGHT.search(name):
        return None
    if is_hotel_or_lodging(list(tags.values())):
        return None
    types = night_types(tags, name)
    if not types:
        return None
    lat, lon = element_latlon(el)
    if lat is None:
        return None
    if require_fr:
        if not in_metropolitan_france(lat, lon) or in_switzerland(lat, lon):
            return None
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
    key = "nightclub"
    if "karaoke" in types:
        key = "karaoke"
    elif "dancing" in types:
        key = "dance"
    elif "pub" in types:
        key = "pub"
    elif "bar" in types:
        key = "bar"
    item = {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "price_min": 0.0,
        "price_max": 0.0,
        "currency": "EUR",
        "types": types,
        "kind": "place",
        "category": map_category(types, 0.0),
        "description": tags.get("description:fr") or tags.get("description") or BLURB.get(key, "Bar."),
        "address": addr or None,
        "photo_url": None,
        "photo_license": None,
        "website_url": website,
        "indoor": True,
        "source_name": "osm",
        "source_id": osm_id,
        "source_url": "https://www.openstreetmap.org/" + osm_id,
    }
    if CULTURE_SHOW.search(name) and not NIGHT_CLUBISH.search(name):
        item["category"] = "Musées et culture"
    else:
        item["category"] = "Soirées et concerts"
    if not is_priced_place(item):
        return None
    return item


def fetch_night_around(lat, lon, radius_m=12000, clubs_only=False):
    clubs = """
[out:json][timeout:90];
(
  nwr["amenity"="nightclub"]["name"](around:%s,%s,%s);
  nwr["amenity"="karaoke_box"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon)
    if clubs_only:
        return fetch_one(clubs)
    dance = """
[out:json][timeout:90];
(
  nwr["leisure"="dance"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon)
    drinks = """
[out:json][timeout:90];
(
  nwr["amenity"="bar"]["name"](around:%s,%s,%s);
  nwr["amenity"="pub"]["name"](around:%s,%s,%s);
  nwr["amenity"="biergarten"]["name"](around:%s,%s,%s);
);
out center;
""" % (radius_m, lat, lon, radius_m, lat, lon, radius_m, lat, lon)
    return fetch_one(clubs) + fetch_one(dance) + fetch_one(drinks)


def fetch_france_clubs():
    query = """
[out:json][timeout:180];
area["ISO3166-1"="FR"][admin_level=2]->.fr;
(
  nwr["amenity"="nightclub"]["name"](area.fr);
  nwr["amenity"="karaoke_box"]["name"](area.fr);
);
out center;
"""
    return fetch_one(query)


def collect_elements(hubs, radius_m, clubs_only=False):
    seen = set()
    elements = []
    for name, lat, lon in hubs:
        chunk = fetch_night_around(lat, lon, radius_m, clubs_only=clubs_only)
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
    print("osm nightlife unique", len(elements), flush=True)
    return elements


def fetch_cities_by_slugs(url, service_role, slugs):
    rows = []
    chunk = 40
    for i in range(0, len(slugs), chunk):
        part = slugs[i : i + chunk]
        extra = "&slug=in.(" + ",".join(urllib.parse.quote(s, safe="") for s in part) + ")"
        rows.extend(
            fetch_all(
                url,
                service_role,
                "cities",
                "id,slug,name,latitude,longitude,country_code",
                extra=extra,
            )
        )
    return [row for row in rows if row.get("latitude") is not None]


def extra_country_hubs(featured_cc):
    hubs = []
    for cc, spec in REST_OSM.items():
        if cc in featured_cc:
            continue
        south, west, north, east = spec[0], spec[1], spec[2], spec[3]
        hubs.append((cc, (south + north) / 2.0, (west + east) / 2.0))
    return hubs


def recategorize_culture_shows(url, service_role):
    needles = (
        "concert",
        "cabaret",
        "jazz",
        "opéra",
        "opera",
        "ballet",
        "théâtre",
        "theatre",
        "theater",
        "moulin rouge",
        "paradis latin",
        "new morning",
        "spectacle",
        "philharmonie",
        "cinema",
        "cinéma",
        "école de danse",
        "studio de danse",
        "académie de danse",
        "milonga",
    )
    seen = set()
    moved = 0
    print("recategorize culture…", flush=True)
    for needle in needles:
        extra = (
            "&category=eq."
            + urllib.parse.quote("Soirées et concerts")
            + "&name=ilike.*"
            + urllib.parse.quote(needle)
            + "*&limit=800&offset=0"
        )
        q = (
            url.rstrip("/")
            + "/rest/v1/outings?select=id,name,description,category"
            + extra
        )
        req = urllib.request.Request(
            q,
            headers={
                "apikey": service_role,
                "Authorization": "Bearer " + service_role,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print("culture skip", needle, exc, flush=True)
            continue
        to_move = []
        samples = []
        for row in rows:
            oid = row.get("id")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            name = row.get("name") or ""
            blob = name + " " + (row.get("description") or "")
            if NIGHT_CLUBISH.search(name):
                continue
            if DANCE_SCHOOL_MOVE.search(name):
                to_move.append(oid)
                if len(samples) < 6:
                    samples.append(name)
                continue
            if not CULTURE_SHOW.search(blob):
                continue
            if SHOW_BUT_DRINK.search(name) and not re.search(r"\b(spectacle|concert|ballet)\b", name, re.I):
                continue
            to_move.append(oid)
            if len(samples) < 6:
                samples.append(name)
        for i in range(0, len(to_move), 40):
            chunk = to_move[i : i + 40]
            ids = ",".join(str(x) for x in chunk)
            body = json.dumps({"category": "Musées et culture"}).encode("utf-8")
            reqp = urllib.request.Request(
                url.rstrip("/") + "/rest/v1/outings?id=in.(" + ids + ")",
                data=body,
                headers={
                    "apikey": service_role,
                    "Authorization": "Bearer " + service_role,
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                method="PATCH",
            )
            with urllib.request.urlopen(reqp, timeout=60) as resp:
                resp.read()
            moved += len(chunk)
        print("culture needle", needle, "batch", len(rows), "chunk", len(to_move), "moved", moved, "ex:", samples, flush=True)
        time.sleep(0.2)
    extra = (
        "&category=eq."
        + urllib.parse.quote("Soirées et concerts")
        + "&description=eq."
        + urllib.parse.quote("Dancing.")
        + "&limit=800&offset=0"
    )
    q = url.rstrip("/") + "/rest/v1/outings?select=id,name,description,category" + extra
    req = urllib.request.Request(
        q,
        headers={
            "apikey": service_role,
            "Authorization": "Bearer " + service_role,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print("culture skip dancing-desc", exc, flush=True)
        rows = []
    to_move = []
    samples = []
    for row in rows:
        oid = row.get("id")
        if not oid or oid in seen:
            continue
        name = row.get("name") or ""
        if NIGHT_CLUBISH.search(name):
            continue
        if DANCE_SCHOOL_MOVE.search(name) or DANCE_SCHOOL.search(name):
            seen.add(oid)
            to_move.append(oid)
            if len(samples) < 8:
                samples.append(name)
    for i in range(0, len(to_move), 40):
        chunk = to_move[i : i + 40]
        ids = ",".join(str(x) for x in chunk)
        body = json.dumps({"category": "Musées et culture"}).encode("utf-8")
        reqp = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/outings?id=in.(" + ids + ")",
            data=body,
            headers={
                "apikey": service_role,
                "Authorization": "Bearer " + service_role,
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            method="PATCH",
        )
        with urllib.request.urlopen(reqp, timeout=60) as resp:
            resp.read()
        moved += len(chunk)
    print("culture dancing-desc", len(rows), "chunk", len(to_move), "moved", moved, "ex:", samples, flush=True)
    print("terminé recategorize culture", moved, flush=True)
    return moved


def recategorize_world(url, service_role):
    """Même règles partout : concerts / cabarets / ciné / écoles de danse → culture."""
    return recategorize_culture_shows(url, service_role)


def build_payload(items, cities, require_fr=True):
    payload = []
    name_seen = set()
    skipped = 0
    clubs = 0
    for item in items:
        nk = re.sub(r"[^a-z0-9]+", " ", (item["name"] or "").lower()).strip()
        geo = (round(item["latitude"], 3), round(item["longitude"], 3), nk)
        if geo in name_seen:
            skipped += 1
            continue
        if require_fr:
            city = pin_city(item["latitude"], item["longitude"], cities)
            if not city or (city.get("country_code") or "") != "FR":
                skipped += 1
                continue
        else:
            city = nearest_city(item["latitude"], item["longitude"], cities)
            if not city:
                skipped += 1
                continue
        row = to_outing_row(item, city["id"])
        if not row:
            skipped += 1
            continue
        row["currency"] = currency_for(city.get("country_code"))
        row["category"] = item["category"]
        payload.append(row)
        name_seen.add(geo)
        if "nightclub" in (item.get("types") or []):
            clubs += 1
    return payload, skipped, clubs


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--hub")
    parser.add_argument("--all-hubs", action="store_true")
    parser.add_argument("--france-area", action="store_true")
    parser.add_argument("--world", action="store_true")
    parser.add_argument("--recategorize-culture", action="store_true")
    parser.add_argument("--radius-m", type=int, default=12000)
    args = parser.parse_args()

    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = (os.environ.get("SUPABASE_SERVICE_ROLE") or "").strip().split()[0]
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")

    if args.recategorize_culture:
        recategorize_world(url, service_role)
        if not (args.world or args.france_area or args.all_hubs or args.hub):
            return

    fr_cities = fetch_all(
        url,
        service_role,
        "cities",
        "id,slug,name,latitude,longitude,country_code",
        extra="&country_code=eq.FR",
    )
    fr_cities = [row for row in fr_cities if row.get("latitude") is not None]

    if args.france_area:
        elements = fetch_france_clubs()
        print("france area osm", len(elements), flush=True)
        items = [osm_to_night(el, True) for el in elements]
        items = [item for item in items if item]
        payload, skipped, clubs = build_payload(items, fr_cities, True)
        print("importables france clubs", len(payload), "boites", clubs, "ignorés", skipped, flush=True)
        if payload:
            upsert_outings(url, service_role, payload)

    featured = (
        "Paris",
        "Lyon",
        "Marseille",
        "Lille",
        "Toulouse",
        "Bordeaux",
        "Nantes",
        "Nice",
        "Strasbourg",
        "Montpellier",
        "Rennes",
    )
    hubs = [h for h in SHOP_HUBS if h[0] in featured]
    if args.all_hubs:
        hubs = SHOP_HUBS
    if args.hub:
        hubs = [h for h in SHOP_HUBS if h[0].lower() == args.hub.lower()]
        if not hubs:
            raise SystemExit("hub inconnu: " + args.hub)

    if args.hub or args.all_hubs or not (args.world or args.france_area or args.recategorize_culture):
        items = []
        for el in collect_elements(hubs, args.radius_m, clubs_only=False):
            item = osm_to_night(el, True)
            if item:
                items.append(item)
        print("convertis FR", len(items), flush=True)
        payload, skipped, clubs = build_payload(items, fr_cities, True)
        print("importables nightlife FR", len(payload), "boites", clubs, "ignorés", skipped, flush=True)
        if payload:
            upsert_outings(url, service_role, payload)

    if args.world:
        world_cities = fetch_cities_by_slugs(url, service_role, list(WORLD_SLUGS))
        pin_cities = world_cities + fr_cities
        hubs_w = [(row["name"], row["latitude"], row["longitude"]) for row in world_cities]
        featured_cc = {row.get("country_code") for row in world_cities}
        hubs_w.extend(extra_country_hubs(featured_cc))
        print("world hubs", len(hubs_w), flush=True)
        items = []
        for el in collect_elements(hubs_w, args.radius_m, clubs_only=True):
            item = osm_to_night(el, False)
            if item:
                items.append(item)
        print("convertis world", len(items), flush=True)
        payload, skipped, clubs = build_payload(items, pin_cities, False)
        print("importables nightlife world", len(payload), "boites", clubs, "ignorés", skipped, flush=True)
        if payload:
            upsert_outings(url, service_role, payload)

    print("terminé nightlife", flush=True)


if __name__ == "__main__":
    main()
