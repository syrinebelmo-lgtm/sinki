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
SKIP_NAME = re.compile(r"\b(war memorial|cenotaph|grave|tomb|statue of|bust of|h[oô]tel|hotel|hostel|motel|former|ancien|ehemalig)\b", re.I)


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
            return json.loads(raw, strict=False) if raw else None
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
    if "--world" in argv:
        url, key = env()
        log = open(os.path.expanduser("~/sinki-sauvegardes/migration/enrichissement.jsonl"), "a")
        only = [a.split("=", 1)[1] for a in argv if a.startswith("--countries=")]
        world(url, key, dry, log, skip={"FR"}, only=set(only[0].split(",")) if only else None)
        return
    wanted = [a for a in argv if not a.startswith("--")] or list(CITIES)
    url, key = env()
    log = open(os.path.expanduser("~/sinki-sauvegardes/migration/enrichissement.jsonl"), "a")
    total = 0
    for cc in wanted:
        for slug in CITIES.get(cc, []):
            try:
                total += (enrich_city_sparql if "--sparql" in argv else enrich_city)(url, key, cc, slug, dry, log)
            except Exception as exc:  # coupure réseau, serveur saturé : on passe à la suivante
                print(cc, slug, "erreur, ville sautée:", type(exc).__name__, exc, flush=True)
                time.sleep(30)
    print("TOTAL nouveaux lieux:", total, "(simulation)" if dry else "", flush=True)


def already_done(url, key, city_id):
    q = "%s/rest/v1/outings?select=id&source_name=in.(osm_wikidata,wikidata)&city_id=eq.%s&limit=1" % (url, city_id)
    return bool(http_json(q, headers={"apikey": key, "Authorization": "Bearer " + key}))


def enrich_city(url, key, cc, slug, dry, log):
    got = http_json(
        "%s/rest/v1/cities?select=id,name,latitude,longitude,country_code&slug=eq.%s" % (url, slug),
        headers={"apikey": key, "Authorization": "Bearer " + key},
    )
    if not got:
        print(cc, slug, "ville absente", flush=True)
        return 0
    city = got[0]
    if not dry and already_done(url, key, city["id"]):
        print(cc, city["name"], "déjà enrichie", flush=True)
        return 0
    try:
        els = overpass(city["latitude"], city["longitude"], 12)
    except RuntimeError as exc:
        print(cc, city["name"], "OSM indisponible, ville sautée:", exc, flush=True)
        return 0
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
    time.sleep(5)
    return len(fresh)


# --- Mode rapide : Wikidata seul (SPARQL), sans les serveurs OSM saturés ---------
WD_TYPES = {
    "Q33506": ("Musées et culture", "place"),      # musée
    "Q207694": ("Musées et culture", "place"),     # musée d'art
    "Q1007870": ("Musées et culture", "place"),    # galerie d'art
    "Q24354": ("Musées et culture", "place"),      # théâtre
    "Q41253": ("Musées et culture", "place"),      # cinéma
    "Q1060829": ("Musées et culture", "place"),    # salle de concert
    "Q23413": ("Musées et culture", "place"),      # château
    "Q16560": ("Musées et culture", "place"),      # palais
    "Q2977": ("Musées et culture", "place"),       # cathédrale
    "Q22698": ("Lieux gratuits et balades", "walk"),   # parc
    "Q1107656": ("Lieux gratuits et balades", "walk"), # jardin
    "Q167346": ("Lieux gratuits et balades", "walk"),  # jardin botanique
    "Q43501": ("Activités et loisirs", "place"),   # zoo
    "Q2281788": ("Activités et loisirs", "place"), # aquarium
    "Q194195": ("Activités et loisirs", "place"),  # parc d'attractions
    "Q11315": ("Shopping", "place"),               # centre commercial
    "Q330284": ("Shopping", "place"),              # marché
    "Q622425": ("Soirées et concerts", "place"),   # boîte de nuit
}


# Order matters: a zoo that is also a park is an activity, a concert hall is a night out.
CATEGORY_PRIORITY = ("Q43501", "Q2281788", "Q194195", "Q622425", "Q1060829", "Q11315", "Q330284",
                     "Q33506", "Q207694", "Q1007870", "Q24354", "Q41253", "Q23413", "Q16560", "Q2977",
                     "Q167346", "Q1107656", "Q22698")


def pick_category(types, fallback):
    for t in CATEGORY_PRIORITY:
        if t in types:
            cat, kind = WD_TYPES[t]
            return ("Soirées et concerts", kind) if t == "Q1060829" else (cat, kind)
    return WD_TYPES[fallback]


def sparql_places(lat, lon, km):
    q = """SELECT DISTINCT ?item ?coord ?image ?type WHERE {
  SERVICE wikibase:around { ?item wdt:P625 ?coord . bd:serviceParam wikibase:center "Point(%f %f)"^^geo:wktLiteral . bd:serviceParam wikibase:radius "%d" . }
  ?item wdt:P31 ?type .
  VALUES ?type { %s }
  ?item wdt:P18 ?image .
}""" % (lon, lat, km, " ".join("wd:" + t for t in WD_TYPES))
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q)
    data = http_json(url, headers={"Accept": "application/sparql-results+json"}, timeout=90)
    out = {}
    for b in data["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
        if not m or qid in out:
            continue
        photo = urllib.parse.unquote(b["image"]["value"].rsplit("/", 1)[-1]).replace("_", " ")
        out[qid] = {"lat": float(m.group(2)), "lon": float(m.group(1)), "photo": photo,
                    "type": b["type"]["value"].rsplit("/", 1)[-1]}
    return out


def wd_labels(qids):
    out = {}
    for i in range(0, len(qids), 50):
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
               "&props=labels|descriptions|claims&languages=fr|en&ids=" + "|".join(qids[i : i + 50]))
        try:
            data = http_json(url, timeout=60)
        except Exception:
            continue
        for qid, ent in (data.get("entities") or {}).items():
            lab = ent.get("labels") or {}
            desc = ent.get("descriptions") or {}
            site = ((ent.get("claims") or {}).get("P856") or [{}])[0]
            try:
                website = site["mainsnak"]["datavalue"]["value"]
            except (KeyError, TypeError):
                website = None
            claims = ent.get("claims") or {}
            # P576 dissolved/demolished, P3999 closure date, P582 end time: not an outing anymore.
            closed = any(claims.get(pid) for pid in ("P576", "P3999", "P582"))
            # P5817 state of use: permanently closed / demolished / ruins / disused.
            for c in claims.get("P5817") or []:
                v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
                if v.get("id") in ("Q30108381", "Q45403344", "Q109551565", "Q63065035", "Q11755880", "Q75727314"):
                    closed = True
            types = {((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id") for c in claims.get("P31") or []}
            if types & {"Q19860854", "Q1371849", "Q16831714", "Q3577956"}:  # destroyed building, demolished, gov/official residence
                closed = True
            text = " ".join(((desc.get(l) or {}).get("value") or "") for l in ("fr", "en")).lower()
            if re.search(r"\b(former|defunct|demolished|closed|ancien cin|disparu|d[eé]moli|ferm[eé]|official residence|r[eé]sidence officielle|presidential|pr[eé]sidentiel|embassy|ambassade|military|militaire|pornographic|porn)", text):
                closed = True
            name = (lab.get("fr") or lab.get("en") or {}).get("value") or ""
            out[qid] = {
                "types": types,
                "closed": closed,
                "name": name[:1].upper() + name[1:],
                "desc": (desc.get("fr") or desc.get("en") or {}).get("value") or "",
                "website": website,
            }
        time.sleep(0.3)
    return out


def enrich_city_sparql(url, key, cc, slug, dry, log, city=None):
    if city is None:
        got = http_json("%s/rest/v1/cities?select=id,name,latitude,longitude&slug=eq.%s" % (url, slug),
                        headers={"apikey": key, "Authorization": "Bearer " + key})
        if not got:
            print(cc, slug, "ville absente", flush=True)
            return 0
        city = got[0]
    if not dry and already_done(url, key, city["id"]):
        print(cc, city["name"], "déjà enrichie", flush=True)
        return 0
    places = sparql_places(city["latitude"], city["longitude"], 12)
    labels = wd_labels(sorted(places))
    meta = commons_meta(sorted({p["photo"] for p in places.values()}))
    known = existing_names(url, key, city["id"])
    now = datetime.now(timezone.utc).isoformat()
    rows, seen = [], set()
    for qid, p in places.items():
        info = labels.get(qid) or {}
        name = info.get("name", "").strip()
        lic = meta.get(p["photo"])
        if re.search(r"\b(former|ehemalig|ancien|demolished|d[eé]moli|closed|abandoned)\b", p["photo"], re.I):
            continue  # photo of a place that no longer exists
        if re.search(r"(logo|poster|affiche|\bmap\b|\bkarte\b|plan\b|locator|coat of arms|wappen|seal of|flag of|\.svg$)", p["photo"], re.I):
            continue  # not a photo of the place
        if info.get("closed") or not name or not lic or name.startswith("Q") or GENERIC.match(name) or SKIP_NAME.search(name):
            continue
        k = norm(name)
        if k in seen or k in known:
            continue
        seen.add(k)
        cat, kind = pick_category(info.get("types") or set(), p["type"])
        rows.append({
            "id": str(uuid.uuid5(NS, "wd:" + qid)),
            "city_id": city["id"], "kind": kind, "category": cat,
            "name": name[:200], "description": (info.get("desc") or "")[:500] or None,
            "address": None, "latitude": p["lat"], "longitude": p["lon"],
            "price_min": None, "price_max": None, "currency": CURRENCY.get(cc, "EUR"),
            "indoor": True if cat in ("Musées et culture", "Shopping") else (False if kind == "walk" else None),
            "vibes": [], "transport_modes": [], "opening_hours": {},
            "website_url": info.get("website"),
            "photo_url": "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(p["photo"]) + "?width=1280",
            "photo_license": lic[0], "photo_credit": lic[1],
            "image_source_url": "https://www.wikidata.org/wiki/" + qid,
            "source_name": "wikidata", "source_id": "wd:" + qid,
            "source_url": "https://www.wikidata.org/wiki/" + qid,
            "is_active": True, "verified_at": now,
        })
    print("%s %-28s Wikidata %4d -> nouveaux %4d (tous avec photo)" % (cc, city["name"], len(places), len(rows)), flush=True)
    if dry:
        with open(os.path.expanduser("~/sinki-sauvegardes/migration/simulation_%s.jsonl" % cc), "a") as out:
            for r in rows:
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
    elif rows:
        upsert(url, key, rows)
    log.write(json.dumps({"cc": cc, "city": city["name"], "new": len(rows), "mode": "sparql", "dry": dry}) + "\n")
    time.sleep(2)
    return len(rows)


# --- Tous les pays : 5 plus grandes villes de chaque pays (Wikidata) ----------------
# Pays trop grands pour la requête « plus grandes villes » : centres fournis.
EXTRA_CENTERS = {
    "CN": [(31.2304, 121.4737), (39.9042, 116.4074), (22.5431, 114.0579), (23.1291, 113.2644), (30.5728, 104.0668),
           (29.5630, 106.5516), (34.3416, 108.9398), (30.2741, 120.1551), (30.5928, 114.3055), (32.0603, 118.7969)],
    "US": [(37.7749, -122.4194), (38.9072, -77.0369), (42.3601, -71.0589), (47.6062, -122.3321), (29.9511, -90.0715),
           (32.7157, -117.1611), (39.9526, -75.1652), (29.7604, -95.3698), (28.5384, -81.3789), (30.2672, -97.7431)],
    "CA": [(45.4215, -75.6972), (51.0447, -114.0719), (53.5461, -113.4938)],
    "DE": [(51.0504, 13.7373), (48.7758, 9.1829), (51.2277, 6.7735), (51.3397, 12.3731), (49.4521, 11.0767)],
    "GB": [(51.4545, -2.5879), (53.8008, -1.5491), (51.7520, -1.2577), (52.2053, 0.1218), (51.4816, -3.1791), (54.5973, -5.9301)],
}

CITY_TYPES = "wd:Q515 wd:Q1549591 wd:Q5119 wd:Q200250 wd:Q1637706"


def biggest_cities(cc, n=5):
    n = 10 if cc in ("US", "CN", "IN", "BR", "RU", "JP", "MX", "ID", "DE", "GB", "CA", "AU") else n
    q = """SELECT ?city ?coord ?pop WHERE {
  ?country wdt:P297 "%s" .
  VALUES ?t { %s }
  ?city wdt:P31 ?t ; wdt:P17 ?country ; wdt:P1082 ?pop ; wdt:P625 ?coord .
} ORDER BY DESC(?pop) LIMIT 40""" % (cc, CITY_TYPES)
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q)
    try:
        data = http_json(url, headers={"Accept": "application/sparql-results+json"}, timeout=90)
    except urllib.error.HTTPError:
        # Big countries: too many cities to sort. Million-plus cities only.
        light = q.replace("VALUES ?t { %s }" % CITY_TYPES, "VALUES ?t { wd:Q1637706 wd:Q1549591 }")
        url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(light)
        data = http_json(url, headers={"Accept": "application/sparql-results+json"}, timeout=90)
    out, seen = [], set()
    for b in data["results"]["bindings"]:
        qid = b["city"]["value"]
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
        if not m or qid in seen:
            continue
        seen.add(qid)
        out.append((float(m.group(2)), float(m.group(1))))
        if len(out) >= n:
            break
    return out


def local_cities():
    path = os.path.expanduser("~/sinki-sauvegardes/migration/cities.jsonl.gz")
    by = {}
    for line in gzip.open(path, "rt", encoding="utf-8"):
        c = json.loads(line)
        if c.get("is_active", True):
            by.setdefault(c["country_code"], []).append(c)
    return by


def world(url, key, dry, log, skip=(), only=None):
    by = local_cities()
    total = 0
    for cc in sorted(by):
        if cc in skip or (only is not None and cc not in only):
            continue
        try:
            centers = EXTRA_CENTERS.get(cc) or biggest_cities(cc)
        except Exception as exc:
            print(cc, "villes introuvables:", type(exc).__name__, flush=True)
            continue
        used = set()
        for lat, lon in centers:
            best = min(by[cc], key=lambda c: (c["latitude"] - lat) ** 2 + (c["longitude"] - lon) ** 2)
            if dist_km((lat, lon), (best["latitude"], best["longitude"])) > 15 or best["id"] in used:
                continue
            used.add(best["id"])
            try:
                total += enrich_city_sparql(url, key, cc, best.get("slug"), dry, log, city=best)
            except Exception as exc:
                print(cc, best["name"], "erreur, ville sautée:", type(exc).__name__, flush=True)
                time.sleep(20)
        time.sleep(1)
    print("TOTAL monde nouveaux lieux:", total, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
