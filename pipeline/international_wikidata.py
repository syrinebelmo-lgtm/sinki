# -*- coding: utf-8 -*-
"""Enrichit les grandes villes hors France avec des lieux réels et leur photo officielle.

Source : OpenStreetMap (lieux nommés, liés à Wikidata) + Wikidata (photo P18 et
coordonnées P625) + Wikimedia Commons (auteur et licence de la photo).

Règles :
- un lieu n'est gardé que si son entrée Wikidata a des coordonnées à moins de
  1 km du lieu OSM (évite les liens vers une personne, une marque, une ville) ;
- la photo est celle de l'entrée Wikidata du lieu lui-même, avec auteur et
  licence ; sans photo officielle, pas de photo ;
- prix seulement si OSM l'indique (fee / charge), sinon inconnu ;
- identifiant stable (uuid5 de l'objet OSM) : relancer met à jour sans doublon.

Usage : python3 -m pipeline.international_wikidata [GB ES IT ...] [--dry]
Utilise ~/sinki/.env.nouveau (nouveau projet Supabase).
"""

import gzip
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

UA = {"User-Agent": "SINKI/1.0 (thesinkiisinki@gmail.com; enrichissement des sorties)"}
OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
NS = uuid.UUID("6f1d3a52-5b8e-4c1e-9a77-51a1c0de0001")

# Grandes villes par pays (slugs de la table cities).
CITIES = {
    "GB": ["london-gb", "manchester-gb", "edinburgh-gb", "birmingham-gb", "glasgow-gb", "liverpool-gb"],
    "ES": ["madrid-es", "barcelona-es", "valencia-es", "seville-es", "malaga-es", "palma-de-mallorca-es"],
    "IT": ["roma-it", "milano-it", "firenze-it", "venezia-it", "napoli-it", "torino-it"],
    "DE": ["berlin-de", "munchen-landeshauptstadt-de", "hamburg-freie-und-hansestadt-de", "koln-de", "frankfurt-am-main-de"],
    "PT": ["lisbon-pt", "porto-pt", "faro-pt"],
    "NL": ["amsterdam-nl", "rotterdam-nl", "utrecht-nl", "den-haag-nl"],
    "BE": ["bruxelles", "anvers", "gand", "bruges", "liege", "namur"],
    "CH": ["geneve", "zurich", "lausanne", "bale", "berne", "lucerne"],
    "AT": ["vienna-at", "salzburg-at", "innsbruck-at"],
    "IE": ["dublin-ie", "cork-ie", "galway-ie"],
    "GR": ["athens-gr", "thessaloniki-gr"],
    "CZ": ["prague-cz", "brno-cz"],
    "HU": ["budapest-hu"],
    "PL": ["warsaw-pl", "krakow-pl", "gdansk-pl"],
    "DK": ["copenhagen-dk", "aarhus-dk"],
    "SE": ["stockholm-se", "gothenburg-se"],
    "NO": ["oslo-no", "bergen-no"],
    "FI": ["helsinki-fi"],
    "HR": ["zagreb-hr", "split-hr", "dubrovnik-hr"],
    "LU": ["luxembourg-lu"],
    "MA": ["marrakech-ma", "casablanca-ma", "rabat-ma", "fes-ma"],
    "US": ["new-york-city-us", "los-angeles-us", "miami-us", "las-vegas-us", "chicago-us"],
    "CA": ["montreal-ca", "toronto-ca", "vancouver-ca", "quebec-ca"],
    "JP": ["tokyo-jp", "osaka-jp", "kyoto-jp"],
    "TH": ["bangkok-th", "chiang-mai-th", "phuket-th"],
}

CURRENCY = {
    "GB": "GBP", "CH": "CHF", "CZ": "CZK", "HU": "HUF", "PL": "PLN", "DK": "DKK", "SE": "SEK",
    "NO": "NOK", "MA": "MAD", "US": "USD", "CA": "CAD", "JP": "JPY", "TH": "THB",
}

CHARGE_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
GENERIC = re.compile(
    r"^(park|parc|parque|parco|garden|jardin|jard[ií]n|giardino|museum|mus[eé]e|museo|cinema|"
    r"theatre|theater|teatro|monument|memorial|war memorial|statue|playground|green|square|plaza|"
    r"beffroi|rondvaart|recreation ground)$",
    re.I,
)
SKIP_NAME = re.compile(r"\b(war memorial|cenotaph|grave|tomb|statue of|bust of|h[oô]tel|hotel|hostel|motel)\b", re.I)


def env():
    path = os.path.expanduser("~/sinki/.env.nouveau")
    vals = dict(line.strip().split("=", 1) for line in open(path) if "=" in line)
    return vals["SUPABASE_URL"], vals["SUPABASE_SERVICE_ROLE"]


def http_json(url, data=None, headers=None, timeout=120, method=None, tries=4):
    h = dict(UA)
    h.update(headers or {})
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429 or attempt == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == tries - 1:
                raise
        time.sleep(10 * (attempt + 1))


def overpass(lat, lon, km):
    """City square split in 2x2 tiles: lighter queries for busy public servers."""
    dlat = km / 111.0
    dlon = km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    found = {}
    for i in (0, 1):
        for j in (0, 1):
            s, w = lat - dlat + i * dlat, lon - dlon + j * dlon
            for el in overpass_box("%f,%f,%f,%f" % (s, w, s + dlat, w + dlon)):
                found[(el.get("type"), el.get("id"))] = el
    return list(found.values())


def overpass_box(bb):
    q = """[out:json][timeout:120];
(
 nwr["tourism"~"^(museum|attraction|gallery|zoo|aquarium|theme_park|viewpoint)$"]["name"]["wikidata"](%(bb)s);
 nwr["leisure"~"^(park|garden|water_park|escape_game|bowling_alley|miniature_golf|ice_rink)$"]["name"]["wikidata"](%(bb)s);
 nwr["amenity"~"^(theatre|cinema|arts_centre|nightclub|concert_hall|planetarium)$"]["name"]["wikidata"](%(bb)s);
 nwr["historic"~"^(castle|palace|fort)$"]["name"]["wikidata"](%(bb)s);
 nwr["shop"~"^(mall|department_store)$"]["name"]["wikidata"](%(bb)s);
 nwr["amenity"="marketplace"]["name"]["wikidata"](%(bb)s);
);
out center tags;""" % {"bb": bb}
    last = None
    for attempt in range(6):
        url = OVERPASS[attempt % len(OVERPASS)]
        try:
            return http_json(url, urllib.parse.urlencode({"data": q}).encode(), timeout=240, tries=1)["elements"]
        except Exception as exc:  # serveurs publics souvent saturés
            last = exc
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("overpass: %s" % last)


def wikidata(qids):
    out = {}
    for i in range(0, len(qids), 50):
        url = (
            "https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
            "&props=claims|descriptions&languages=fr|en&ids=" + "|".join(qids[i : i + 50])
        )
        for attempt in range(4):
            try:
                data = http_json(url, timeout=60)
                break
            except Exception:
                time.sleep(5 * (attempt + 1))
        else:
            continue
        for qid, ent in (data.get("entities") or {}).items():
            claims = ent.get("claims") or {}
            p18 = claims.get("P18") or []
            p625 = claims.get("P625") or []
            try:
                photo = p18[0]["mainsnak"]["datavalue"]["value"]
            except (KeyError, IndexError, TypeError):
                photo = None
            try:
                v = p625[0]["mainsnak"]["datavalue"]["value"]
                coord = (float(v["latitude"]), float(v["longitude"]))
            except (KeyError, IndexError, TypeError, ValueError):
                coord = None
            desc = (ent.get("descriptions") or {})
            text = (desc.get("fr") or desc.get("en") or {}).get("value") or ""
            out[qid] = {"photo": photo, "coord": coord, "desc": text}
        time.sleep(0.3)
    return out


def commons_meta(files):
    """{file: (license, author)} for free Commons files."""
    out = {}
    for i in range(0, len(files), 50):
        titles = "|".join("File:" + f for f in files[i : i + 50])
        url = (
            "https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo"
            "&iiprop=extmetadata&titles=" + urllib.parse.quote(titles)
        )
        try:
            data = http_json(url, timeout=60)
        except Exception:
            continue
        norm = {n["to"]: n["from"] for n in (data.get("query") or {}).get("normalized") or []}
        for page in ((data.get("query") or {}).get("pages") or {}).values():
            info = (page.get("imageinfo") or [{}])[0].get("extmetadata") or {}
            lic = (info.get("LicenseShortName") or {}).get("value") or ""
            artist = re.sub(r"<[^>]+>", "", (info.get("Artist") or {}).get("value") or "").strip()
            title = norm.get(page.get("title"), page.get("title") or "")
            if lic:
                out[title[5:] if title.startswith("File:") else title] = (lic[:60], artist[:80])
        time.sleep(0.3)
    return out


def dist_km(a, b):
    r = math.radians
    dlat, dlon = r(b[0] - a[0]), r(b[1] - a[1])
    x = math.sin(dlat / 2) ** 2 + math.cos(r(a[0])) * math.cos(r(b[0])) * math.sin(dlon / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


RELIGIOUS = re.compile(r"\b(church|cathedral|abbey|chapel|basilica|minster|mosque|synagogue|temple|kirche|dom|iglesia|catedral|chiesa|duomo|basilica|igreja|kerk|kosci[oó]ł|[eé]glise|cath[eé]drale|abbaye)\b", re.I)


def category(tags):
    t = tags.get
    if t("amenity") == "place_of_worship" or t("building") in ("church", "cathedral", "chapel", "mosque", "temple") or RELIGIOUS.search(t("name") or ""):
        return "Musées et culture", "place"
    if t("shop") in ("mall", "department_store") or t("amenity") == "marketplace":
        return "Shopping", "place"
    if t("amenity") == "nightclub":
        return "Soirées et concerts", "place"
    if t("amenity") in ("theatre", "cinema", "arts_centre", "concert_hall", "planetarium") or t("tourism") in ("museum", "gallery") or t("historic"):
        return "Musées et culture", "place"
    if t("leisure") in ("park", "garden") or t("tourism") == "viewpoint":
        return "Lieux gratuits et balades", "walk"
    return "Activités et loisirs", "place"


def price(tags, cc):
    fee = (tags.get("fee") or "").lower().strip()
    if fee in ("no", "free", "none", "0"):
        return 0.0, 0.0
    charge = " ".join(str(tags.get(k) or "") for k in ("charge", "charge:adult", "fee:adult"))
    nums = [float(x.replace(",", ".")) for x in CHARGE_RE.findall(charge)]
    if nums and max(nums) < 1000:
        return min(nums), max(nums)
    return None, None


def address(tags):
    street = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
    town = " ".join(x for x in (tags.get("addr:postcode"), tags.get("addr:city")) if x)
    return ", ".join(x for x in (street, town) if x) or None


def build_rows(city, elements, wd, meta, cc):
    rows, seen = [], set()
    now = datetime.now(timezone.utc).isoformat()
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name:fr") or tags.get("name") or "").strip()
        qid = tags.get("wikidata")
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if not name or not qid or lat is None or GENERIC.match(name) or SKIP_NAME.search(name):
            continue
        info = wd.get(qid) or {}
        if not info.get("coord") or dist_km((lat, lon), info["coord"]) > 1.0:
            continue  # lien Wikidata vers autre chose qu'un lieu proche
        key = norm(name)
        if key in seen:
            continue
        seen.add(key)
        cat, kind = category(tags)
        pmin, pmax = price(tags, cc)
        photo = info.get("photo")
        lic = meta.get(photo) if photo else None
        osm_id = "%s/%s" % (el.get("type"), el.get("id"))
        rows.append({
            "id": str(uuid.uuid5(NS, osm_id)),
            "city_id": city["id"],
            "kind": kind,
            "category": cat,
            "name": name[:200],
            "description": (info.get("desc") or "")[:500] or None,
            "address": address(tags),
            "latitude": lat,
            "longitude": lon,
            "price_min": pmin,
            "price_max": pmax,
            "currency": CURRENCY.get(cc, "EUR"),
            "indoor": True if cat in ("Musées et culture", "Shopping") else (False if kind == "walk" else None),
            "vibes": [],
            "transport_modes": [],
            "opening_hours": {"osm": tags["opening_hours"]} if tags.get("opening_hours") else {},
            "website_url": tags.get("website") or tags.get("contact:website"),
            "photo_url": ("https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(photo) + "?width=1280") if (photo and lic) else None,
            "photo_license": lic[0] if lic else None,
            "photo_credit": lic[1] if lic else None,
            "image_source_url": "https://www.wikidata.org/wiki/" + qid,
            "source_name": "osm_wikidata",
            "source_id": "osm:" + osm_id,
            "source_url": "https://www.openstreetmap.org/" + osm_id,
            "is_active": True,
            "verified_at": now,
        })
    return rows


def existing_names(url, key, city_id):
    names, offset = set(), 0
    while True:
        q = "%s/rest/v1/outings?select=name,source_name&city_id=eq.%s&limit=1000&offset=%d" % (url, city_id, offset)
        rows = http_json(q, headers={"apikey": key, "Authorization": "Bearer " + key})
        for r in rows:
            if r.get("source_name") != "osm_wikidata":
                names.add(norm(r.get("name")))
        if len(rows) < 1000:
            return names
        offset += 1000


def upsert(url, key, rows):
    headers = {
        "apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    for i in range(0, len(rows), 500):
        http_json(url + "/rest/v1/outings", json.dumps(rows[i : i + 500]).encode(), headers, method="POST")


def main(argv):
    dry = "--dry" in argv
    wanted = [a for a in argv if not a.startswith("--")] or list(CITIES)
    url, key = env()
    log = open(os.path.expanduser("~/sinki-sauvegardes/migration/enrichissement.jsonl"), "a")
    total = 0
    for cc in wanted:
        for slug in CITIES.get(cc, []):
            got = http_json(
                "%s/rest/v1/cities?select=id,name,latitude,longitude,country_code&slug=eq.%s" % (url, slug),
                headers={"apikey": key, "Authorization": "Bearer " + key},
            )
            if not got:
                print(cc, slug, "ville absente", flush=True)
                continue
            city = got[0]
            try:
                els = overpass(city["latitude"], city["longitude"], 12)
            except RuntimeError as exc:
                print(cc, city["name"], "OSM indisponible, ville sautée:", exc, flush=True)
                continue
            qids = sorted({e["tags"]["wikidata"] for e in els if (e.get("tags") or {}).get("wikidata")})
            wd = wikidata(qids)
            photos = sorted({v["photo"] for v in wd.values() if v.get("photo")})
            meta = commons_meta(photos)
            rows = build_rows(city, els, wd, meta, cc)
            known = existing_names(url, key, city["id"])
            fresh = [r for r in rows if norm(r["name"]) not in known]
            with_photo = sum(1 for r in fresh if r["photo_url"])
            print("%s %-28s OSM %4d -> gardés %4d (nouveaux %4d, avec photo %4d)" % (cc, city["name"], len(els), len(rows), len(fresh), with_photo), flush=True)
            if dry:
                with open(os.path.expanduser("~/sinki-sauvegardes/migration/simulation_%s.jsonl" % cc), "a") as out:
                    for r in fresh:
                        out.write(json.dumps(r, ensure_ascii=False) + "\n")
            elif fresh:
                upsert(url, key, fresh)
            log.write(json.dumps({"cc": cc, "city": city["name"], "kept": len(rows), "new": len(fresh), "photo": with_photo, "dry": dry}) + "\n")
            total += len(fresh)
            time.sleep(5)
    print("TOTAL nouveaux lieux:", total, "(simulation)" if dry else "", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
