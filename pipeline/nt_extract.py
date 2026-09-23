# -*- coding: utf-8 -*-
"""Extraction streaming du dump N-Triples DATAtourisme (Licence Ouverte 2.0)."""

import re
import zipfile
from collections import defaultdict

from .categories import map_category, map_kind, slugify
from .quality import is_complete, is_hotel_or_lodging, is_priced_place

TRIPLE = re.compile(
    r"^<([^>]+)>\s+<([^>]+)>\s+(?:<([^>]+)>|\"((?:\\.|[^\"\\])*)\"(?:@[A-Za-z0-9-]+|\^\^<[^>]+>)?)\s*\.\s*$"
)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
SCHEMA_LAT = "http://schema.org/latitude"
SCHEMA_LON = "http://schema.org/longitude"
SCHEMA_PRICE = "http://schema.org/price"
SCHEMA_MIN = "http://schema.org/minPrice"
SCHEMA_MAX = "http://schema.org/maxPrice"
SCHEMA_POSTAL = "http://schema.org/postalCode"
SCHEMA_LOCALITY = "http://schema.org/addressLocality"
SCHEMA_STREET = "http://schema.org/streetAddress"
DT_LOCATED = "https://www.datatourisme.fr/ontology/core#isLocatedAt"
DT_MAIN_REP = "https://www.datatourisme.fr/ontology/core#hasMainRepresentation"
DT_REP = "https://www.datatourisme.fr/ontology/core#hasRepresentation"
EBU_LOCATOR = "http://www.ebu.ch/metadata/ontologies/ebucore/ebucore#locator"
EBU_RESOURCE = "http://www.ebu.ch/metadata/ontologies/ebucore/ebucore#hasRelatedResource"
SCHEMA_GEO = "http://schema.org/geo"
SCHEMA_ADDRESS = "http://schema.org/address"
DT_COMMENT = "https://www.datatourisme.fr/ontology/core#hasDescription"
RDFS_COMMENT = "http://www.w3.org/2000/01/rdf-schema#comment"
SCHEMA_OFFERS = "http://schema.org/offers"
DT_OFFERS = "https://www.datatourisme.fr/ontology/core#offers"
SCHEMA_PRICE_SPEC = "http://schema.org/priceSpecification"
SCHEMA_LOW = "http://schema.org/lowPrice"
SCHEMA_HIGH = "http://schema.org/highPrice"
SCHEMA_FREE = "http://schema.org/isAccessibleForFree"
DT_FREE = "https://www.datatourisme.fr/ontology/core#isAccessibleForFree"

KEEP_PRED = {
    RDF_TYPE,
    RDFS_LABEL,
    SCHEMA_LAT,
    SCHEMA_LON,
    SCHEMA_PRICE,
    SCHEMA_MIN,
    SCHEMA_MAX,
    SCHEMA_POSTAL,
    SCHEMA_LOCALITY,
    SCHEMA_STREET,
    DT_LOCATED,
    DT_MAIN_REP,
    DT_REP,
    EBU_LOCATOR,
    EBU_RESOURCE,
    SCHEMA_GEO,
    SCHEMA_ADDRESS,
    DT_COMMENT,
    RDFS_COMMENT,
    SCHEMA_OFFERS,
    DT_OFFERS,
    SCHEMA_PRICE_SPEC,
    SCHEMA_LOW,
    SCHEMA_HIGH,
    SCHEMA_FREE,
    DT_FREE,
}


def _unescape(value):
    if value is None:
        return None
    return (
        value.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _short_type(uri):
    if "#" in uri:
        return uri.rsplit("#", 1)[-1]
    return uri.rsplit("/", 1)[-1]


def extract_complete_from_nt_zip(zip_path, progress_every=500000):
    types = defaultdict(set)
    labels = {}
    literals = defaultdict(dict)
    links = defaultdict(list)

    n_lines = 0
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".nt") or n.endswith(".ttl")]
        if not names:
            names = zf.namelist()[:1]
        with zf.open(names[0]) as raw:
            for raw_line in raw:
                n_lines += 1
                if n_lines % progress_every == 0:
                    print("triples lus:", n_lines, flush=True)
                try:
                    line = raw_line.decode("utf-8", "ignore").strip()
                except Exception:
                    continue
                if not line or line.startswith("#"):
                    continue
                m = TRIPLE.match(line)
                if not m:
                    continue
                s, p, obj_uri, obj_lit = m.group(1), m.group(2), m.group(3), m.group(4)
                if p not in KEEP_PRED:
                    continue
                if obj_uri:
                    if p == RDF_TYPE:
                        types[s].add(_short_type(obj_uri))
                    else:
                        links[s].append((p, obj_uri))
                else:
                    val = _unescape(obj_lit)
                    if p == RDFS_LABEL:
                        if s not in labels or obj_lit:  # first label
                            labels.setdefault(s, val)
                    else:
                        literals[s].setdefault(p, val)

    print("indexation terminée, assemblage des POI…", flush=True)

    def first_link(subject, pred):
        for p, o in links.get(subject, ()):
            if p == pred:
                return o
        return None

    def all_links(subject, pred):
        return [o for p, o in links.get(subject, ()) if p == pred]

    def walk_image(poi):
        media_nodes = all_links(poi, DT_MAIN_REP) + all_links(poi, DT_REP)
        for media in media_nodes:
            loc = literals.get(media, {}).get(EBU_LOCATOR)
            if loc:
                return loc
            for res in all_links(media, EBU_RESOURCE):
                loc = literals.get(res, {}).get(EBU_LOCATOR)
                if loc:
                    return loc
                if str(res).startswith("http"):
                    return res
        return None

    def walk_geo(poi):
        lat = _num(literals.get(poi, {}).get(SCHEMA_LAT))
        lon = _num(literals.get(poi, {}).get(SCHEMA_LON))
        if lat is not None and lon is not None:
            return lat, lon
        place = first_link(poi, DT_LOCATED)
        if not place:
            return None, None
        geo = first_link(place, SCHEMA_GEO) or place
        lat = _num(literals.get(geo, {}).get(SCHEMA_LAT))
        lon = _num(literals.get(geo, {}).get(SCHEMA_LON))
        return lat, lon

    def walk_address(poi):
        place = first_link(poi, DT_LOCATED) or poi
        addr = first_link(place, SCHEMA_ADDRESS) or place
        street = literals.get(addr, {}).get(SCHEMA_STREET) or literals.get(place, {}).get(SCHEMA_STREET)
        locality = literals.get(addr, {}).get(SCHEMA_LOCALITY) or literals.get(place, {}).get(SCHEMA_LOCALITY)
        postal = literals.get(addr, {}).get(SCHEMA_POSTAL) or literals.get(place, {}).get(SCHEMA_POSTAL)
        return street, locality, postal

    def walk_price(poi):
        mins, maxs = [], []
        stack = [poi]
        seen = set()
        price_preds = {SCHEMA_OFFERS, DT_OFFERS, SCHEMA_PRICE_SPEC}
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            lit = literals.get(cur, {})
            a = _num(lit.get(SCHEMA_MIN) or lit.get(SCHEMA_LOW))
            b = _num(lit.get(SCHEMA_PRICE))
            c = _num(lit.get(SCHEMA_MAX) or lit.get(SCHEMA_HIGH))
            if a is not None:
                mins.append(a)
            if b is not None:
                mins.append(b)
                maxs.append(b)
            if c is not None:
                maxs.append(c)
            for p, o in links.get(cur, ()):
                if p in price_preds and o not in seen and len(seen) < 80:
                    stack.append(o)
        if not mins and not maxs:
            free_vals = []
            for node in (poi,):
                lit = literals.get(node, {})
                for pred in (SCHEMA_FREE, DT_FREE):
                    raw = (lit.get(pred) or "").strip().lower()
                    if raw in ("true", "1", "yes"):
                        free_vals.append(True)
            if free_vals:
                return 0.0, 0.0
            return None, None
        return (min(mins) if mins else None), (max(maxs) if maxs else (min(mins) if mins else None))

    complete = []
    priced = []
    skipped_hotel = skipped_incomplete = 0
    for poi, tset in types.items():
        tlist = list(tset)
        if "PointOfInterest" not in tlist and "PlaceOfInterest" not in tlist:
            continue
        if is_hotel_or_lodging(tlist):
            skipped_hotel += 1
            continue
        name = labels.get(poi)
        lat, lon = walk_geo(poi)
        photo = walk_image(poi)
        pmin, pmax = walk_price(poi)
        street, locality, postal = walk_address(poi)
        desc = literals.get(poi, {}).get(DT_COMMENT) or literals.get(poi, {}).get(RDFS_COMMENT)
        row = {
            "source_name": "datatourisme",
            "source_id": poi.rsplit("/", 1)[-1],
            "source_url": poi,
            "name": name,
            "description": desc,
            "types": tlist,
            "latitude": lat,
            "longitude": lon,
            "photo_url": photo,
            "photo_license": "Licence Ouverte 2.0 / producteur DATAtourisme",
            "price_min": pmin,
            "price_max": pmax,
            "address": street,
            "city_name": locality,
            "postal_code": postal,
            "city_slug": slugify(locality) if locality else "",
        }
        if not is_priced_place(row):
            skipped_incomplete += 1
            continue
        row["category"] = map_category(tlist, row["price_min"])
        row["kind"] = map_kind(tlist)
        priced.append(row)
        if is_complete(row):
            complete.append(row)

    print(
        "complets photo+prix:",
        len(complete),
        "avec prix (photo optionnelle):",
        len(priced),
        "hôtels exclus:",
        skipped_hotel,
        "sans prix/GPS/nom:",
        skipped_incomplete,
        flush=True,
    )
    return complete, priced
