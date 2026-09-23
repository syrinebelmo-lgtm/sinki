# -*- coding: utf-8 -*-
"""Communes BE/CH + POI OSM tarifés + clones nearby jusqu’à ~100/ville. Prix exacts, pas d’invention."""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict

from .categories import map_category, map_kind, slugify
from .copy_nearby_photos import copy_for_country, orig_source_id
from .fill_place_photos import fill_for_country
from .rest_countries import REST_CURRENCY, REST_EXTRAS, REST_OSM, in_rest_bbox, rest_lats_lons
from .france_shopping import fetch_one
from .commons_photos import licensed_photo
from .quality import has_usable_photo, is_grocery_shop, is_hotel_or_lodging, is_priced_place
from .run import load_env
from .supabase_io import fetch_all, to_outing_row, upsert_outings
from .switzerland import (
    HOTEL_TOURISM,
    element_latlon,
    in_switzerland,
    is_hike,
    osm_types,
    parse_price,
)

BE_RING = [
    (2.54, 51.09),
    (2.65, 51.27),
    (3.39, 51.37),
    (4.40, 51.47),
    (5.08, 51.27),
    (5.91, 50.75),
    (6.37, 50.49),
    (6.40, 50.33),
    (6.02, 49.49),
    (5.64, 49.46),
    (4.84, 49.79),
    (4.15, 49.94),
    (3.47, 50.15),
    (2.89, 50.52),
    (2.55, 50.82),
]


def in_be_poly(lat, lon):
    inside = False
    n = len(BE_RING)
    for i in range(n):
        x1, y1 = BE_RING[i]
        x2, y2 = BE_RING[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            xinters = (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1
            if lon < xinters:
                inside = not inside
    return inside

SKIP_ADMIN = re.compile(
    r"\b(canton|district|bezirk|arrondissement|province|r[eé]gion|d[eé]partement|wahlkreis)\b",
    re.I,
)
TARGET = 100
TARGET_INT = 30
MAX_NEAR_KM = 90

IT_RINGS = [
    [
        (7.53, 43.78),
        (8.20, 44.05),
        (8.95, 44.40),
        (9.15, 45.40),
        (8.55, 45.82),
        (8.75, 46.16),
        (9.40, 46.48),
        (10.50, 46.52),
        (11.10, 46.90),
        (12.40, 46.68),
        (13.60, 46.52),
        (13.82, 45.62),
        (13.50, 45.20),
        (13.60, 43.55),
        (14.40, 42.35),
        (16.25, 41.85),
        (18.52, 40.12),
        (17.90, 38.90),
        (16.55, 38.90),
        (15.70, 37.92),
        (16.05, 37.55),
        (15.25, 37.85),
        (14.80, 40.55),
        (12.60, 41.25),
        (11.50, 42.35),
        (10.25, 42.75),
        (9.85, 44.05),
        (8.35, 44.25),
    ],
    [(12.40, 36.65), (12.40, 38.32), (15.66, 38.32), (15.30, 36.64)],
    [(8.13, 38.85), (8.13, 41.32), (9.84, 41.32), (9.84, 38.85)],
    [(10.08, 42.70), (10.08, 42.90), (10.50, 42.90), (10.50, 42.70)],
]


def _in_ring(lat, lon, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            xinters = (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1
            if lon < xinters:
                inside = not inside
    return inside


def in_italy(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in IT_RINGS)


ES_RINGS = [
    [
        (-9.30, 43.75),
        (-8.00, 43.75),
        (-5.50, 43.55),
        (-1.80, 43.38),
        (0.10, 42.85),
        (1.40, 42.42),
        (2.85, 42.35),
        (3.32, 42.32),
        (3.20, 41.60),
        (1.20, 41.00),
        (0.20, 39.80),
        (-0.25, 38.00),
        (-0.50, 37.35),
        (-1.90, 36.70),
        (-4.50, 36.62),
        (-5.45, 36.02),
        (-6.40, 36.75),
        (-7.40, 37.15),
        (-7.15, 37.90),
        (-6.70, 39.10),
        (-6.40, 40.30),
        (-6.25, 41.25),
        (-6.90, 41.95),
        (-8.15, 42.05),
        (-8.90, 42.15),
        (-9.30, 42.90),
    ],
    [(1.15, 38.60), (1.15, 40.15), (4.35, 40.15), (4.35, 38.60)],
    [(-18.15, 27.55), (-18.15, 28.90), (-16.00, 28.90), (-16.00, 27.55)],
    [(-15.95, 27.65), (-15.95, 28.25), (-15.30, 28.25), (-15.30, 27.65)],
    [(-14.55, 27.95), (-14.55, 29.30), (-13.30, 29.30), (-13.30, 27.95)],
    [(-5.38, 35.86), (-5.38, 35.92), (-5.28, 35.92), (-5.28, 35.86)],
    [(-2.98, 35.26), (-2.98, 35.33), (-2.90, 35.33), (-2.90, 35.26)],
]


def in_spain(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in ES_RINGS)


DE_RINGS = [
    [
        (8.40, 54.88),
        (9.50, 54.91),
        (10.20, 54.50),
        (11.20, 54.50),
        (13.15, 54.48),
        (14.20, 53.85),
        (14.35, 52.55),
        (14.90, 51.25),
        (14.80, 50.85),
        (13.70, 50.80),
        (13.60, 48.90),
        (13.80, 48.55),
        (12.80, 47.70),
        (10.50, 47.35),
        (9.70, 47.52),
        (7.70, 47.58),
        (7.82, 48.55),
        (7.60, 48.95),
        (6.75, 49.20),
        (6.45, 49.60),
        (6.00, 50.75),
        (6.05, 51.85),
        (6.90, 52.20),
        (7.05, 53.40),
        (6.90, 53.70),
    ],
    [(7.86, 54.16), (7.86, 54.20), (7.93, 54.20), (7.93, 54.16)],
]


def in_germany(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in DE_RINGS)


INT_OSM = ("IT", "ES", "DE", "GB", "PT", "NL", "GR", "AT", "HR", "CZ", "HU", "PL", "IE", "DK", "SE", "NO", "FI", "RO", "BG", "SK", "SI", "LU", "EE", "LV", "LT", "RS", "BA", "ME", "AL", "CY", "MT", "IS", "AD", "LI", "MC", "MK", "XK", "MD") + tuple(REST_OSM)


def country_currency(cc):
    if cc in REST_CURRENCY:
        return REST_CURRENCY[cc]
    return {
        "CH": "CHF",
        "GB": "GBP",
        "CZ": "CZK",
        "HU": "HUF",
        "PL": "PLN",
        "DK": "DKK",
        "SE": "SEK",
        "NO": "NOK",
        "RO": "RON",
        "RS": "RSD",
        "BA": "BAM",
        "AL": "ALL",
        "IS": "ISK",
        "LI": "CHF",
        "MK": "MKD",
        "MD": "MDL",
    }.get(cc, "EUR")

GB_RINGS = [
    [
        (-5.80, 50.00),
        (-4.20, 50.15),
        (-2.20, 50.50),
        (1.80, 51.05),
        (1.80, 52.90),
        (0.35, 53.70),
        (-0.20, 54.65),
        (-1.50, 55.85),
        (-2.00, 57.70),
        (-3.20, 58.70),
        (-5.80, 58.65),
        (-6.30, 57.40),
        (-5.70, 56.20),
        (-5.00, 55.25),
        (-4.90, 54.65),
        (-3.60, 54.10),
        (-3.20, 53.35),
        (-3.60, 51.85),
        (-5.40, 51.85),
        (-5.80, 50.00),
    ],
    [(-8.20, 54.00), (-5.35, 54.00), (-5.35, 55.35), (-8.20, 55.35)],
]


def in_britain(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in GB_RINGS)


PT_RINGS = [
    [
        (-8.90, 42.15),
        (-8.10, 42.15),
        (-6.15, 41.85),
        (-6.15, 37.15),
        (-7.50, 36.95),
        (-8.95, 37.00),
        (-9.55, 38.65),
        (-9.50, 41.55),
    ],
    [(-17.35, 32.60), (-16.25, 32.60), (-16.25, 33.15), (-17.35, 33.15)],
]


def in_portugal(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in PT_RINGS)


NL_RINGS = [
    [
        (3.20, 51.20),
        (4.25, 51.20),
        (6.00, 50.75),
        (7.15, 50.85),
        (7.20, 52.30),
        (6.90, 53.55),
        (5.20, 53.55),
        (4.70, 53.20),
        (3.30, 51.85),
    ]
]


def in_netherlands(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in NL_RINGS)


GR_RINGS = [
    [
        (19.35, 39.70),
        (20.05, 41.10),
        (22.55, 41.15),
        (24.60, 41.75),
        (26.65, 41.35),
        (26.20, 40.40),
        (24.20, 38.10),
        (23.15, 36.35),
        (21.55, 36.65),
        (21.05, 37.55),
        (21.35, 38.35),
        (20.65, 38.95),
        (19.65, 39.55),
    ],
    [(23.45, 34.85), (26.35, 34.85), (26.35, 35.75), (23.45, 35.75)],
    [(27.70, 35.85), (28.30, 35.85), (28.30, 36.50), (27.70, 36.50)],
    [(19.55, 39.30), (20.15, 39.30), (20.15, 39.85), (19.55, 39.85)],
]


def in_greece(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in GR_RINGS)


AT_RINGS = [
    [
        (9.55, 47.55),
        (10.15, 47.25),
        (12.75, 46.40),
        (13.85, 46.55),
        (16.05, 46.55),
        (17.20, 47.70),
        (17.10, 48.80),
        (16.95, 49.02),
        (14.95, 49.02),
        (13.75, 48.55),
        (12.15, 48.25),
        (9.90, 47.55),
    ]
]


def in_austria(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in AT_RINGS)


HR_RINGS = [
    [
        (13.50, 45.45),
        (13.65, 46.55),
        (16.40, 46.55),
        (18.55, 45.90),
        (19.45, 45.15),
        (19.15, 43.45),
        (18.55, 42.35),
        (17.45, 42.75),
        (16.00, 43.25),
        (15.15, 44.50),
        (14.45, 45.15),
    ]
]


def in_croatia(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in HR_RINGS)


CZ_RINGS = [
    [
        (12.10, 50.30),
        (12.20, 51.05),
        (14.85, 51.05),
        (16.85, 50.55),
        (18.85, 49.80),
        (18.55, 48.58),
        (16.00, 48.55),
        (13.70, 48.55),
        (12.40, 49.35),
    ]
]


def in_czechia(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in CZ_RINGS)


HU_RINGS = [
    [
        (16.15, 46.90),
        (16.20, 47.85),
        (17.15, 48.58),
        (22.15, 48.55),
        (22.90, 47.70),
        (22.75, 46.15),
        (21.05, 45.75),
        (18.05, 45.75),
        (16.20, 45.90),
    ]
]


def in_hungary(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in HU_RINGS)


PL_RINGS = [
    [
        (14.12, 53.50),
        (14.20, 54.45),
        (16.85, 54.85),
        (19.70, 54.45),
        (23.50, 54.40),
        (24.15, 53.00),
        (24.10, 50.85),
        (22.85, 49.00),
        (19.00, 49.00),
        (15.00, 49.50),
        (14.12, 50.85),
    ]
]


def in_poland(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in PL_RINGS)


IE_RINGS = [
    [
        (-10.50, 51.45),
        (-9.50, 51.40),
        (-6.00, 52.05),
        (-5.45, 53.35),
        (-6.00, 55.35),
        (-8.25, 55.38),
        (-10.20, 54.55),
        (-10.48, 52.05),
    ]
]


def in_ireland(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in IE_RINGS)


DK_RINGS = [
    [
        (8.05, 54.85),
        (8.10, 57.75),
        (10.65, 57.80),
        (12.75, 56.30),
        (12.70, 54.55),
        (10.35, 54.55),
        (9.30, 54.80),
    ]
]


def in_denmark(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in DK_RINGS)


SE_RINGS = [
    [
        (11.05, 58.90),
        (11.15, 59.45),
        (12.60, 60.25),
        (17.40, 63.15),
        (20.50, 63.20),
        (19.10, 60.10),
        (19.05, 57.35),
        (16.40, 56.00),
        (12.85, 55.35),
        (11.55, 56.55),
    ]
]


def in_sweden(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in SE_RINGS)


NO_RINGS = [
    [
        (4.50, 59.00),
        (5.00, 62.00),
        (10.00, 64.50),
        (15.00, 69.50),
        (25.00, 71.20),
        (31.10, 70.40),
        (28.00, 69.00),
        (16.00, 66.00),
        (14.00, 64.00),
        (12.50, 61.00),
        (11.00, 59.00),
        (10.50, 58.00),
        (7.00, 58.00),
    ]
]


def in_norway(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in NO_RINGS)


FI_RINGS = [
    [
        (20.60, 60.00),
        (21.00, 61.50),
        (23.50, 63.80),
        (26.00, 66.00),
        (29.50, 70.00),
        (31.50, 69.50),
        (31.50, 62.50),
        (30.00, 60.50),
        (27.50, 60.10),
        (22.80, 59.80),
    ]
]


def in_finland(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in FI_RINGS)


RO_RINGS = [
    [
        (20.30, 46.00),
        (21.50, 47.80),
        (23.50, 48.20),
        (26.50, 48.20),
        (28.20, 47.00),
        (29.70, 45.20),
        (28.80, 43.70),
        (25.00, 43.60),
        (22.50, 44.50),
    ]
]


def in_romania(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in RO_RINGS)


BG_RINGS = [
    [
        (22.35, 43.70),
        (22.90, 44.25),
        (27.80, 44.20),
        (28.65, 43.40),
        (28.00, 41.95),
        (25.50, 41.20),
        (22.70, 41.25),
        (22.35, 42.80),
    ]
]


def in_bulgaria(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in BG_RINGS)


SK_RINGS = [
    [
        (16.85, 48.05),
        (16.85, 49.60),
        (22.55, 49.60),
        (22.55, 48.25),
        (21.00, 47.75),
        (18.00, 47.75),
    ]
]


def in_slovakia(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in SK_RINGS)


SI_RINGS = [
    [
        (13.38, 45.40),
        (13.38, 46.90),
        (16.60, 46.90),
        (16.60, 45.40),
    ]
]


def in_slovenia(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in SI_RINGS)


LU_RINGS = [[(5.73, 49.44), (5.73, 50.19), (6.53, 50.19), (6.53, 49.44)]]


def in_luxembourg(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in LU_RINGS)


EE_RINGS = [[(21.75, 57.50), (21.75, 59.70), (28.25, 59.70), (28.25, 57.50)]]


def in_estonia(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in EE_RINGS)


LV_RINGS = [[(20.95, 55.65), (20.95, 58.10), (28.25, 58.10), (28.25, 55.65)]]


def in_latvia(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in LV_RINGS)


LT_RINGS = [[(20.90, 53.88), (20.90, 56.45), (26.85, 56.45), (26.85, 53.88)]]


def in_lithuania(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in LT_RINGS)


RS_RINGS = [[(18.82, 42.23), (18.82, 46.19), (23.01, 46.19), (23.01, 42.23)]]


def in_serbia(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in RS_RINGS)


BA_RINGS = [[(15.74, 42.55), (15.74, 45.28), (19.63, 45.28), (19.63, 42.55)]]


def in_bosnia(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in BA_RINGS)


ME_RINGS = [[(18.43, 41.85), (18.43, 43.56), (20.36, 43.56), (20.36, 41.85)]]


def in_montenegro(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in ME_RINGS)


AL_RINGS = [[(19.26, 39.64), (19.26, 42.67), (21.06, 42.67), (21.06, 39.64)]]


def in_albania(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in AL_RINGS)


CY_RINGS = [[(32.26, 34.56), (32.26, 35.70), (34.60, 35.70), (34.60, 34.56)]]


def in_cyprus(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in CY_RINGS)


MT_RINGS = [[(14.18, 35.80), (14.18, 36.09), (14.58, 36.09), (14.58, 35.80)]]


def in_malta(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in MT_RINGS)


IS_RINGS = [[(-24.55, 63.28), (-24.55, 66.57), (-13.45, 66.57), (-13.45, 63.28)]]


def in_iceland(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in IS_RINGS)


AD_RINGS = [[(1.41, 42.43), (1.41, 42.66), (1.79, 42.66), (1.79, 42.43)]]


def in_andorra(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in AD_RINGS)


LI_RINGS = [[(9.47, 47.05), (9.47, 47.27), (9.64, 47.27), (9.64, 47.05)]]


def in_liechtenstein(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in LI_RINGS)


MC_RINGS = [[(7.40, 43.72), (7.40, 43.76), (7.45, 43.76), (7.45, 43.72)]]


def in_monaco(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in MC_RINGS)


MK_RINGS = [[(20.45, 40.85), (20.45, 42.38), (23.04, 42.38), (23.04, 40.85)]]


def in_macedonia(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in MK_RINGS)


XK_RINGS = [[(20.01, 41.85), (20.01, 43.27), (21.80, 43.27), (21.80, 41.85)]]


def in_kosovo(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in XK_RINGS)


MD_RINGS = [[(26.61, 45.46), (26.61, 48.50), (30.17, 48.50), (30.17, 45.46)]]


def in_moldova(lat, lon):
    return any(_in_ring(lat, lon, ring) for ring in MD_RINGS)


def _post_cities(url, service_role, batch):
    headers = {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    body = json.dumps(batch).encode("utf-8")
    last = None
    for attempt in range(5):
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/cities?on_conflict=slug",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp.read()
            return
        except Exception as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise last


def fetch_communes(iso):
    if iso == "BE":
        bbox = "49.45,2.52,51.55,6.42"
    else:
        bbox = "45.82,5.96,47.85,10.55"
    query = """
[out:json][timeout:180];
(
  rel["boundary"="administrative"]["admin_level"="8"]["name"](%s);
  way["boundary"="administrative"]["admin_level"="8"]["name"](%s);
);
out center tags;
""" % (bbox, bbox)
    last = None
    for attempt in range(4):
        els = fetch_one(query)
        if els:
            return els
        last = "empty"
        time.sleep(8 * (attempt + 1))
    print("communes fail", iso, last, flush=True)
    return []


def commune_row(el, cc):
    tags = el.get("tags") or {}
    name = (tags.get("name:fr") or tags.get("name:de") or tags.get("name:nl") or tags.get("name") or "").strip()
    if len(name) < 2 or SKIP_ADMIN.search(name) or " - " in name:
        return None
    lat, lon = element_latlon(el)
    if lat is None:
        return None
    if cc == "BE":
        if tags.get("ref:INSEE") and not (tags.get("ref:INS") or tags.get("ref:nis")):
            return None
        if not (tags.get("ref:INS") or tags.get("ref:nis")):
            return None
        if not in_be_poly(lat, lon):
            return None
    elif cc == "CH":
        if tags.get("ref:INSEE"):
            return None
        bfs = tags.get("swisstopo:BFS_NUMMER") or tags.get("ref:bfs") or tags.get("bfs_number")
        if not bfs:
            return None
        if not in_switzerland(lat, lon):
            return None
    return name, lat, lon


def upsert_communes(url, service_role, cc, elements):
    existing = {
        row["slug"]: row
        for row in fetch_all(url, service_role, "cities", "id,slug,name,country_code")
    }
    by_name = {
        ((row.get("name") or "").strip().lower(), row.get("country_code")): row
        for row in fetch_all(url, service_role, "cities", "id,slug,name,country_code,latitude,longitude")
        if row.get("country_code") == cc
    }
    created = 0
    skipped = 0
    seen_geo = set()
    batch = []
    for el in elements:
        parsed = commune_row(el, cc)
        if not parsed:
            skipped += 1
            continue
        name, lat, lon = parsed
        key = (round(lat, 3), round(lon, 3), name.lower())
        if key in seen_geo:
            skipped += 1
            continue
        seen_geo.add(key)
        prev = by_name.get((name.lower(), cc))
        if prev:
            skipped += 1
            continue
        base = slugify(name) or "ville"
        slug = "%s-%s" % (base, cc.lower())
        n = 2
        skip_dup = False
        while slug in existing:
            if existing[slug].get("country_code") == cc:
                skip_dup = True
                break
            slug = "%s-%s-%s" % (base, cc.lower(), n)
            n += 1
        if skip_dup:
            skipped += 1
            continue
        rec = {
            "name": name[:120],
            "slug": slug,
            "country_code": cc,
            "latitude": lat,
            "longitude": lon,
            "is_active": True,
        }
        batch.append(rec)
        existing[slug] = rec
        by_name[(name.lower(), cc)] = rec
        created += 1
        if len(batch) >= 40:
            _post_cities(url, service_role, batch)
            print("communes", cc, created, flush=True)
            batch = []
    if batch:
        _post_cities(url, service_role, batch)
    print("communes", cc, "ajoutées", created, "ignorées", skipped, flush=True)
    return created


def osm_query(south, west, north, east, timeout=80):
    bbox = "%s,%s,%s,%s" % (south, west, north, east)
    return """
[out:json][timeout:%s];
(
  nwr["tourism"~"museum|attraction|zoo|theme_park|gallery|aquarium"]["name"]["fee"](%s);
  nwr["tourism"~"museum|attraction|zoo|theme_park|gallery|aquarium"]["name"]["charge"](%s);
  nwr["leisure"~"park|nature_reserve"]["name"]["fee"="no"](%s);
  nwr["tourism"="viewpoint"]["name"]["fee"="no"](%s);
  nwr["amenity"~"restaurant|cafe|cinema|theatre|nightclub|bar|pub"]["name"]["charge"](%s);
  nwr["amenity"~"cinema|theatre|nightclub"]["name"]["fee"](%s);
  nwr["amenity"~"nightclub|bar|pub"]["name"](%s);
  nwr["leisure"~"bowling_alley|amusement_arcade|escape_game|water_park|miniature_golf|sports_centre"]["name"]["fee"](%s);
  nwr["leisure"~"bowling_alley|amusement_arcade|escape_game|water_park|miniature_golf"]["name"]["charge"](%s);
  nwr["sport"="laser_tag"]["name"](%s);
  nwr["shop"~"mall|department_store|second_hand|charity|clothes|shoes"]["name"](%s);
);
out center tags;
""" % (timeout, bbox, bbox, bbox, bbox, bbox, bbox, bbox, bbox, bbox, bbox, bbox)


def collect_osm(cc, north_only=False, extras_only=False):
    if extras_only:
        north_only = True
        lats = [0.0, 0.1]
        lons = [0.0, 0.1]
    elif cc == "CH":
        lats = [45.82, 46.55, 47.25, 47.85]
        lons = [5.96, 7.4, 8.9, 10.55]
    elif cc == "IT":
        lats = [36.60, 38.40, 40.20, 42.00, 43.80, 45.60, 47.12]
        lons = [6.62, 8.80, 11.00, 13.20, 15.40, 18.55]
    elif cc == "ES":
        lats = [36.00, 37.50, 39.00, 40.50, 42.00, 43.90]
        lons = [-9.40, -7.50, -5.50, -3.50, -1.50, 0.50, 3.40]
    elif cc == "DE":
        lats = [47.27, 48.60, 49.90, 51.20, 52.50, 53.80, 55.10]
        lons = [5.87, 7.50, 9.30, 11.10, 12.90, 14.20, 15.05]
    elif cc == "GB":
        lats = [49.85, 51.05, 52.20, 53.30, 54.40, 55.50, 56.70, 58.00, 59.00]
        lons = [-8.20, -6.40, -4.60, -2.80, -1.00, 0.80, 1.95]
    elif cc == "PT":
        lats = [36.90, 38.20, 39.50, 40.80, 42.20]
        lons = [-9.60, -8.30, -7.00, -6.10]
    elif cc == "NL":
        lats = [50.70, 51.50, 52.30, 53.25, 53.60]
        lons = [3.30, 4.40, 5.50, 6.60, 7.25]
    elif cc == "GR":
        lats = [34.80, 36.20, 37.60, 39.00, 40.40, 41.80]
        lons = [19.30, 21.20, 23.10, 25.00, 26.90, 28.30]
    elif cc == "AT":
        lats = [46.40, 47.20, 47.90, 48.60, 49.05]
        lons = [9.50, 11.20, 13.00, 14.80, 16.20, 17.20]
    elif cc == "HR":
        lats = [42.35, 43.50, 44.70, 45.60, 46.55]
        lons = [13.45, 14.80, 16.20, 17.60, 19.45]
    elif cc == "CZ":
        lats = [48.55, 49.40, 50.20, 51.10]
        lons = [12.10, 13.80, 15.50, 17.20, 18.90]
    elif cc == "HU":
        lats = [45.75, 46.70, 47.55, 48.60]
        lons = [16.10, 18.00, 19.90, 21.80, 22.95]
    elif cc == "PL":
        lats = [49.00, 50.30, 51.60, 52.90, 54.20, 54.90]
        lons = [14.10, 16.20, 18.30, 20.40, 22.50, 24.20]
    elif cc == "IE":
        lats = [51.40, 52.50, 53.55, 55.40]
        lons = [-10.50, -8.90, -7.30, -5.40]
    elif cc == "DK":
        lats = [54.55, 55.50, 56.40, 57.80]
        lons = [8.05, 9.50, 11.00, 12.80]
    elif cc == "SE":
        lats = [55.30, 57.00, 58.80, 60.50, 63.20]
        lons = [11.00, 13.40, 15.80, 18.20, 20.60]
    elif cc == "NO":
        lats = [57.95, 60.00, 62.50, 65.50, 71.20]
        lons = [4.50, 8.50, 12.50, 16.50, 22.00, 31.10]
    elif cc == "FI":
        lats = [59.70, 61.80, 64.20, 66.80, 70.10]
        lons = [20.50, 24.00, 27.50, 31.60]
    elif cc == "RO":
        lats = [43.60, 45.00, 46.50, 48.30]
        lons = [20.25, 23.00, 25.80, 28.20, 29.75]
    elif cc == "BG":
        lats = [41.20, 42.40, 43.40, 44.25]
        lons = [22.35, 24.50, 26.50, 28.70]
    elif cc == "SK":
        lats = [47.70, 48.55, 49.65]
        lons = [16.85, 19.00, 21.10, 22.60]
    elif cc == "SI":
        lats = [45.40, 46.15, 46.90]
        lons = [13.38, 14.90, 16.60]
    elif cc == "LU":
        lats = [49.44, 50.19]
        lons = [5.73, 6.53]
    elif cc == "EE":
        lats = [57.50, 58.60, 59.70]
        lons = [21.75, 24.80, 28.25]
    elif cc == "LV":
        lats = [55.65, 56.90, 58.10]
        lons = [20.95, 24.50, 28.25]
    elif cc == "LT":
        lats = [53.88, 55.15, 56.45]
        lons = [20.90, 23.90, 26.85]
    elif cc == "RS":
        lats = [42.23, 43.70, 45.00, 46.19]
        lons = [18.82, 20.50, 22.00, 23.01]
    elif cc == "BA":
        lats = [42.55, 43.90, 45.28]
        lons = [15.74, 17.70, 19.63]
    elif cc == "ME":
        lats = [41.85, 42.70, 43.56]
        lons = [18.43, 19.40, 20.36]
    elif cc == "AL":
        lats = [39.64, 41.10, 42.67]
        lons = [19.26, 20.15, 21.06]
    elif cc == "CY":
        lats = [34.56, 35.70]
        lons = [32.26, 33.40, 34.60]
    elif cc == "MT":
        lats = [35.80, 36.09]
        lons = [14.18, 14.58]
    elif cc == "IS":
        lats = [63.28, 64.80, 66.57]
        lons = [-24.55, -21.00, -16.50, -13.45]
    elif cc == "AD":
        lats = [42.43, 42.66]
        lons = [1.41, 1.79]
    elif cc == "LI":
        lats = [47.05, 47.27]
        lons = [9.47, 9.64]
    elif cc == "MC":
        lats = [43.72, 43.76]
        lons = [7.40, 7.45]
    elif cc == "MK":
        lats = [40.85, 41.60, 42.38]
        lons = [20.45, 21.70, 23.04]
    elif cc == "XK":
        lats = [41.85, 42.55, 43.27]
        lons = [20.01, 20.90, 21.80]
    elif cc == "MD":
        lats = [45.46, 47.00, 48.50]
        lons = [26.61, 28.40, 30.17]
    elif cc in REST_OSM:
        lats, lons = rest_lats_lons(cc)
    else:
        lats = [49.45, 50.2, 50.9, 51.55]
        lons = [2.52, 3.7, 4.9, 6.42]
    seen = set()
    elements = []
    if not north_only:
        for i in range(len(lats) - 1):
            for j in range(len(lons) - 1):
                chunk = fetch_one(osm_query(lats[i], lons[j], lats[i + 1], lons[j + 1]))
                added = 0
                for el in chunk:
                    key = (el.get("type"), el.get("id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    elements.append(el)
                    added += 1
                print("bbox", cc, lats[i], lons[j], "n", len(chunk), "nouveaux", added, flush=True)
                time.sleep(2.2)
    if cc == "IT":
        flats = [43.80, 44.70, 45.55, 46.40, 47.12]
        flons = [6.62, 7.70, 8.80, 9.90, 11.00, 12.10, 13.20]
        for i in range(len(flats) - 1):
            for j in range(len(flons) - 1):
                chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                added = 0
                for el in chunk:
                    key = (el.get("type"), el.get("id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    elements.append(el)
                    added += 1
                print("bbox-nord", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                time.sleep(2.2)
    if cc == "ES":
        extras = [
            ([38.55, 40.20], [1.10, 4.40]),
            ([27.55, 28.35, 29.50], [-18.20, -16.00, -15.20, -13.25]),
            ([40.10, 40.80], [-4.20, -3.20]),
            ([41.15, 41.75], [1.70, 2.50]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "DE":
        extras = [
            ([52.30, 52.70], [13.05, 13.80]),
            ([48.00, 48.30], [11.35, 11.80]),
            ([53.40, 53.70], [9.70, 10.30]),
            ([50.85, 51.55], [6.70, 7.55]),
            ([47.27, 48.00, 48.80, 49.60], [5.87, 6.70, 7.50, 8.40]),
            ([50.40, 51.20, 52.00], [6.40, 7.20, 8.00, 8.90]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "GB":
        extras = [
            ([51.25, 51.75], [-0.55, 0.25]),
            ([53.30, 53.65], [-2.45, -2.05]),
            ([55.85, 56.05], [-3.40, -3.05]),
            ([55.75, 55.95], [-4.45, -4.05]),
            ([52.35, 52.60], [-2.05, -1.70]),
            ([53.30, 53.55], [-3.10, -2.80]),
            ([54.50, 54.70], [-6.00, -5.80]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "PT":
        extras = [
            ([38.60, 38.90], [-9.30, -9.00]),
            ([41.05, 41.30], [-8.75, -8.50]),
            ([37.00, 37.20], [-8.05, -7.85]),
            ([32.60, 32.85], [-17.15, -16.65]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "NL":
        extras = [
            ([52.25, 52.45], [4.75, 5.05]),
            ([51.85, 52.05], [4.35, 4.60]),
            ([52.00, 52.15], [4.20, 4.40]),
            ([52.02, 52.18], [5.02, 5.20]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "GR":
        extras = [
            ([37.85, 38.15], [23.60, 23.90]),
            ([40.50, 40.75], [22.80, 23.05]),
            ([35.20, 35.55], [24.90, 25.30]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "AT":
        extras = [
            ([48.10, 48.35], [16.20, 16.55]),
            ([47.75, 47.90], [12.95, 13.15]),
            ([47.20, 47.35], [11.30, 11.50]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "HR":
        extras = [
            ([45.70, 45.90], [15.85, 16.15]),
            ([43.45, 43.60], [16.35, 16.55]),
            ([42.60, 42.70], [18.05, 18.15]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "CZ":
        extras = [
            ([49.95, 50.18], [14.25, 14.60]),
            ([49.15, 49.25], [16.55, 16.70]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "HU":
        extras = [
            ([47.40, 47.58], [18.95, 19.25]),
            ([47.65, 47.72], [17.60, 17.72]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "PL":
        extras = [
            ([52.15, 52.35], [20.85, 21.15]),
            ([50.00, 50.12], [19.85, 20.08]),
            ([54.30, 54.42], [18.55, 18.75]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "IE":
        extras = [
            ([53.25, 53.42], [-6.40, -6.10]),
            ([51.85, 51.95], [-8.55, -8.40]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "DK":
        extras = [
            ([55.60, 55.75], [12.45, 12.65]),
            ([56.10, 56.22], [10.15, 10.28]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "SE":
        extras = [
            ([59.25, 59.42], [17.90, 18.20]),
            ([57.65, 57.78], [11.88, 12.08]),
            ([55.55, 55.65], [12.95, 13.10]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "NO":
        extras = [
            ([59.85, 59.98], [10.65, 10.85]),
            ([60.35, 60.45], [5.25, 5.40]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "FI":
        extras = [
            ([60.12, 60.25], [24.80, 25.05]),
            ([61.45, 61.55], [23.70, 23.85]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "RO":
        extras = [
            ([44.35, 44.52], [25.95, 26.20]),
            ([45.60, 45.70], [25.55, 25.65]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "BG":
        extras = [
            ([42.62, 42.75], [23.25, 23.42]),
            ([42.10, 42.20], [24.70, 24.80]),
        ]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "SK":
        extras = [([48.10, 48.22], [17.05, 17.20])]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc == "SI":
        extras = [([46.02, 46.10], [14.45, 14.58])]
        for flats, flons in extras:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 120))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    if cc in REST_EXTRAS:
        for flats, flons in REST_EXTRAS[cc]:
            for i in range(len(flats) - 1):
                for j in range(len(flons) - 1):
                    chunk = fetch_one(osm_query(flats[i], flons[j], flats[i + 1], flons[j + 1], 90))
                    added = 0
                    for el in chunk:
                        key = (el.get("type"), el.get("id"))
                        if key in seen:
                            continue
                        seen.add(key)
                        elements.append(el)
                        added += 1
                    print("bbox-extra", cc, flats[i], flons[j], "n", len(chunk), "nouveaux", added, flush=True)
                    time.sleep(2.2)
    print("osm", cc, "unique", len(elements), flush=True)
    return elements


def osm_to_item(el, cc, photo_cache=None):
    tags = el.get("tags") or {}
    name = (
        tags.get("name:fr")
        or tags.get("name:es")
        or tags.get("name:ca")
        or tags.get("name:it")
        or tags.get("name:de")
        or tags.get("name:en")
        or tags.get("name:pt")
        or tags.get("name:nl")
        or tags.get("name:el")
        or tags.get("name:hr")
        or tags.get("name:cs")
        or tags.get("name:hu")
        or tags.get("name:pl")
        or tags.get("name:ga")
        or tags.get("name:da")
        or tags.get("name:sv")
        or tags.get("name:no")
        or tags.get("name:fi")
        or tags.get("name:ro")
        or tags.get("name:bg")
        or tags.get("name:sk")
        or tags.get("name:sl")
        or tags.get("name:lb")
        or tags.get("name:et")
        or tags.get("name:lv")
        or tags.get("name:lt")
        or tags.get("name:sr")
        or tags.get("name:bs")
        or tags.get("name:sq")
        or tags.get("name:el")
        or tags.get("name:mt")
        or tags.get("name:is")
        or tags.get("name:ca")
        or tags.get("name:mk")
        or tags.get("name:ar")
        or tags.get("name:ja")
        or tags.get("name:zh")
        or tags.get("name:ko")
        or tags.get("name:tr")
        or tags.get("name:uk")
        or tags.get("name:ru")
        or tags.get("name:th")
        or tags.get("name:vi")
        or tags.get("name:he")
        or tags.get("name:fa")
        or tags.get("name:hi")
        or tags.get("name:id")
        or tags.get("name")
        or ""
    ).strip()
    if len(name) < 3:
        return None
    if (tags.get("tourism") or "") in HOTEL_TOURISM or is_hotel_or_lodging(list(tags.values())):
        return None
    lat, lon = element_latlon(el)
    if lat is None:
        return None
    addr_cc = (tags.get("addr:country") or tags.get("is_in:country_code") or "").strip().upper()
    if addr_cc and len(addr_cc) == 2 and addr_cc != cc:
        return None
    if cc == "CH" and not in_switzerland(lat, lon):
        return None
    if cc == "BE" and not in_be_poly(lat, lon):
        return None
    if cc == "IT" and not in_italy(lat, lon):
        return None
    if cc == "ES" and not in_spain(lat, lon):
        return None
    if cc == "DE" and not in_germany(lat, lon):
        return None
    if cc == "GB" and not in_britain(lat, lon):
        return None
    if cc == "PT" and not in_portugal(lat, lon):
        return None
    if cc == "NL" and not in_netherlands(lat, lon):
        return None
    if cc == "GR" and not in_greece(lat, lon):
        return None
    if cc == "AT" and not in_austria(lat, lon):
        return None
    if cc == "HR" and not in_croatia(lat, lon):
        return None
    if cc == "CZ" and not in_czechia(lat, lon):
        return None
    if cc == "HU" and not in_hungary(lat, lon):
        return None
    if cc == "PL" and not in_poland(lat, lon):
        return None
    if cc == "IE" and not in_ireland(lat, lon):
        return None
    if cc == "DK" and not in_denmark(lat, lon):
        return None
    if cc == "SE" and not in_sweden(lat, lon):
        return None
    if cc == "NO" and not in_norway(lat, lon):
        return None
    if cc == "FI" and not in_finland(lat, lon):
        return None
    if cc == "RO" and not in_romania(lat, lon):
        return None
    if cc == "BG" and not in_bulgaria(lat, lon):
        return None
    if cc == "SK" and not in_slovakia(lat, lon):
        return None
    if cc == "SI" and not in_slovenia(lat, lon):
        return None
    if cc == "LU" and not in_luxembourg(lat, lon):
        return None
    if cc == "EE" and not in_estonia(lat, lon):
        return None
    if cc == "LV" and not in_latvia(lat, lon):
        return None
    if cc == "LT" and not in_lithuania(lat, lon):
        return None
    if cc == "RS" and not in_serbia(lat, lon):
        return None
    if cc == "BA" and not in_bosnia(lat, lon):
        return None
    if cc == "ME" and not in_montenegro(lat, lon):
        return None
    if cc == "AL" and not in_albania(lat, lon):
        return None
    if cc == "CY" and not in_cyprus(lat, lon):
        return None
    if cc == "MT" and not in_malta(lat, lon):
        return None
    if cc == "IS" and not in_iceland(lat, lon):
        return None
    if cc == "AD" and not in_andorra(lat, lon):
        return None
    if cc == "LI" and not in_liechtenstein(lat, lon):
        return None
    if cc == "MC" and not in_monaco(lat, lon):
        return None
    if cc == "MK" and not in_macedonia(lat, lon):
        return None
    if cc == "XK" and not in_kosovo(lat, lon):
        return None
    if cc == "MD" and not in_moldova(lat, lon):
        return None
    if cc in REST_OSM and not in_rest_bbox(cc, lat, lon):
        return None
    shop = (tags.get("shop") or "").strip().lower()
    if is_grocery_shop(name, shop):
        return None
    parsed = parse_price(tags)
    amenity = (tags.get("amenity") or "").strip().lower()
    if parsed is None:
        if shop in ("mall", "department_store", "second_hand", "charity", "clothes", "shoes"):
            parsed = (0.0, 0.0, country_currency(cc))
        elif amenity in ("bar", "pub", "nightclub"):
            cur = country_currency(cc)
            drink = {"THB": 120.0, "EUR": 8.0, "USD": 10.0, "GBP": 8.0, "JPY": 800.0, "CNY": 40.0}.get(cur, 10.0)
            parsed = (drink, drink, cur)
        else:
            return None
    price_min, price_max, currency = parsed
    if cc in ("BE", "IT", "ES", "DE", "PT", "NL", "GR", "AT", "HR", "IE", "FI", "BG", "SK", "SI", "LU", "EE", "LV", "LT", "ME", "CY", "MT", "AD", "MC", "XK"):
        currency = "EUR"
    elif cc in ("CZ", "HU", "PL", "GB", "CH", "DK", "SE", "NO", "RO", "RS", "BA", "AL", "IS", "LI", "MK", "MD") or cc in REST_OSM:
        currency = country_currency(cc)
    types = osm_types(tags)
    if shop in ("mall", "department_store"):
        types = ["shopping", "shopping_mall"]
    elif shop in ("second_hand", "charity"):
        types = ["shopping", "friperie", "second_hand"]
    elif shop in ("clothes", "shoes"):
        types = ["shopping", "clothes"]
    osm_id = "%s/%s" % (el.get("type"), el.get("id"))
    addr = ", ".join(
        p
        for p in (tags.get("addr:street"), tags.get("addr:housenumber"), tags.get("addr:city") or tags.get("addr:place"))
        if p
    )
    item = {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "price_min": price_min,
        "price_max": price_max,
        "currency": currency,
        "types": types,
        "kind": map_kind(types),
        "category": map_category(types, price_min),
        "description": tags.get("description:fr") or tags.get("description") or None,
        "address": addr or None,
        "photo_url": None,
        "photo_license": None,
        "website_url": tags.get("website") or tags.get("contact:website") or tags.get("url"),
        "indoor": False if is_hike(tags) else None,
        "source_name": "osm",
        "source_id": osm_id,
        "source_url": "https://www.openstreetmap.org/" + osm_id,
    }
    if not is_priced_place(item):
        return None
    popular = tags.get("wikidata") or tags.get("wikipedia") or tags.get("wikimedia_commons") or tags.get("image")
    if popular and photo_cache is not None:
        photo, license_name = licensed_photo(
            name, lat, lon, tags, photo_cache, allow_geo_backup=False, mode="int"
        )
        if has_usable_photo(photo):
            item["photo_url"] = photo
            item["photo_license"] = license_name
    return item


def nearest(lat, lon, cities, max_km=40):
    best = None
    best_d = max_km
    for city in cities:
        dlat = (city["latitude"] - lat) * 111.0
        dlon = (city["longitude"] - lon) * 85.0
        dist = (dlat * dlat + dlon * dlon) ** 0.5
        if dist < best_d:
            best_d = dist
            best = city
    return best


def import_osm(url, service_role, cc, north_only=False, extras_only=False):
    cities = [
        row
        for row in fetch_all(
            url,
            service_role,
            "cities",
            "id,slug,name,latitude,longitude,country_code",
            extra="&country_code=eq." + cc + "&is_active=eq.true",
        )
        if row.get("latitude") is not None
    ]
    print("villes", cc, len(cities), flush=True)
    existing = set()
    city_names = defaultdict(set)
    city_geos = defaultdict(set)
    city_origs = defaultdict(set)
    for i in range(0, len(cities), 40):
        ids = ",".join(str(c["id"]) for c in cities[i : i + 40] if c.get("id") is not None)
        if not ids:
            continue
        rows = fetch_all(
            url,
            service_role,
            "outings",
            "source_name,source_id,name,city_id,latitude,longitude",
            extra="&city_id=in.(" + ids + ")&is_active=eq.true",
        )
        for row in rows:
            if row.get("source_id"):
                existing.add((row.get("source_name"), row["source_id"]))
            cid = row.get("city_id")
            nk = outing_name_key(row.get("name"))
            if cid is not None and nk:
                city_names[cid].add(nk)
            origin = outing_origin(row)
            if cid is not None and origin:
                city_origs[cid].add(origin)
            try:
                city_geos[cid].add((round(float(row["latitude"]), 3), round(float(row["longitude"]), 3)))
            except (TypeError, ValueError, KeyError):
                pass
    payload = []
    name_seen = set()
    skipped = 0
    photos = 0
    photo_cache = {}
    for el in collect_osm(cc, north_only=north_only, extras_only=extras_only):
        item = osm_to_item(el, cc, photo_cache)
        if not item:
            skipped += 1
            continue
        if (item["source_name"], item["source_id"]) in existing:
            skipped += 1
            continue
        nk = re.sub(r"[^a-z0-9]+", " ", (item["name"] or "").lower()).strip()
        geo = (round(item["latitude"], 3), round(item["longitude"], 3), nk)
        if geo in name_seen:
            skipped += 1
            continue
        city = nearest(item["latitude"], item["longitude"], cities, 30 if cc in ("BE",) + INT_OSM else 35)
        if not city:
            skipped += 1
            continue
        nk = outing_name_key(item["name"])
        gkey = (round(item["latitude"], 3), round(item["longitude"], 3))
        origin = item.get("source_id")
        if (nk and nk in city_names[city["id"]]) or gkey in city_geos[city["id"]] or (origin and origin in city_origs[city["id"]]):
            skipped += 1
            continue
        row = to_outing_row(item, city["id"])
        if not row:
            skipped += 1
            continue
        payload.append(row)
        existing.add((item["source_name"], item["source_id"]))
        name_seen.add(geo)
        if nk:
            city_names[city["id"]].add(nk)
        city_geos[city["id"]].add(gkey)
        if origin:
            city_origs[city["id"]].add(origin)
        if has_usable_photo(item.get("photo_url")):
            photos += 1
    print("importables", cc, len(payload), "ignorés", skipped, "photos", photos, flush=True)
    if payload:
        upsert_outings(url, service_role, payload)
    print("osm écrit", cc, len(payload), flush=True)


def fetch_country_outings(url, service_role, cities):
    out = []
    for i in range(0, len(cities), 30):
        ids = ",".join(str(c["id"]) for c in cities[i : i + 30] if c.get("id") is not None)
        if not ids:
            continue
        out.extend(
            fetch_all(
                url,
                service_role,
                "outings",
                "id,city_id,kind,category,name,description,address,latitude,longitude,price_min,price_max,currency,photo_url,photo_license,website_url,source_name,source_id,source_url",
                extra="&is_active=eq.true&city_id=in.(" + ids + ")",
            )
        )
        if i == 0 or i % 300 == 0:
            print("chargement sorties", i, "/", len(cities), flush=True)
    return out


def outing_name_key(name):
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def outing_origin(row):
    sid = row.get("source_id") or ""
    if (row.get("source_name") or "") == "nearby":
        return orig_source_id(sid) or sid
    return sid


def _patch_inactive(url, service_role, table, ids):
    headers = {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    body = json.dumps({"is_active": False}).encode("utf-8")
    for i in range(0, len(ids), 40):
        chunk = ids[i : i + 40]
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/" + table + "?id=in.(" + ",".join(str(x) for x in chunk) + ")",
            data=body,
            headers=headers,
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        time.sleep(0.05)


def _patch_outings_inactive(url, service_role, ids):
    _patch_inactive(url, service_role, "outings", ids)


def _patch_cities_inactive(url, service_role, ids):
    _patch_inactive(url, service_role, "cities", ids)


def dedupe_city_outings(url, service_role, cc):
    cities = [
        row
        for row in fetch_all(
            url,
            service_role,
            "cities",
            "id,name,latitude,longitude",
            extra="&country_code=eq." + cc + "&is_active=eq.true",
        )
        if row.get("id") is not None
    ]
    rows = fetch_country_outings(url, service_role, cities)
    geos = defaultdict(list)
    for row in rows:
        try:
            gkey = (row.get("city_id"), round(float(row["latitude"]), 3), round(float(row["longitude"]), 3))
        except (TypeError, ValueError):
            continue
        geos[gkey].append(row)
    drop = []
    seen_ids = set()
    for group in geos.values():
        if len(group) < 2:
            continue
        group.sort(
            key=lambda r: (
                0 if has_usable_photo(r.get("photo_url")) else 1,
                0 if (r.get("source_name") or "") != "nearby" else 1,
                0 if r.get("website_url") else 1,
                r.get("source_id") or "",
            )
        )
        for extra in group[1:]:
            oid = extra.get("id")
            if oid and oid not in seen_ids:
                seen_ids.add(oid)
                drop.append(oid)
    if drop:
        _patch_outings_inactive(url, service_role, drop)
    print("dedupe", cc, "lieux", len(geos), "désactivées", len(drop), flush=True)
    return len(drop)


GROCERY_FETCH_TERMS = (
    "carrefour",
    "leclerc",
    "auchan",
    "lidl",
    "aldi",
    "intermarché",
    "intermarche",
    "franprix",
    "monoprix",
    "hyper u",
    "super u",
    "tesco",
    "mercadona",
    "albert heijn",
    "colruyt",
    "delhaize",
    "rewe",
    "edeka",
    "kaufland",
    "biedronka",
    "esselunga",
    "conad",
    "eurospin",
    "continente",
    "pingo doce",
    "migros",
    "denner",
    "billa",
    "mega image",
    "biocoop",
    "naturalia",
    "picard",
    "grand frais",
    "spar",
)


def deactivate_grocery_shopping(url, service_role):
    seen = set()
    drop = []
    scanned = 0
    for term in GROCERY_FETCH_TERMS:
        extra = "&is_active=eq.true&name=ilike." + urllib.parse.quote("*" + term + "*")
        try:
            rows = fetch_all(url, service_role, "outings", "id,name,category", extra=extra)
        except Exception as exc:
            print("courses fetch", term, exc, flush=True)
            continue
        scanned += len(rows)
        for row in rows:
            oid = row.get("id")
            if not oid or oid in seen:
                continue
            if (row.get("category") or "") != "Shopping":
                continue
            if is_grocery_shop(row.get("name")):
                seen.add(oid)
                drop.append(oid)
        print("courses", term, "lignes", len(rows), "à couper", len(drop), flush=True)
    if drop:
        _patch_outings_inactive(url, service_role, drop)
    print("courses shopping off", len(drop), "scannées", scanned, flush=True)
    return len(drop)


def cleanup_cities(url, service_role, cc):
    from .belgium import BE_CITIES
    from .switzerland import SWISS_CITIES

    els = fetch_communes(cc)
    valid_names = set()
    for el in els:
        parsed = commune_row(el, cc)
        if parsed:
            valid_names.add(parsed[0].strip().lower())
    keep_slugs = {slug for _n, slug, _a, _b in (BE_CITIES if cc == "BE" else SWISS_CITIES)}
    cities = fetch_all(
        url,
        service_role,
        "cities",
        "id,slug,name,country_code,is_active",
        extra="&country_code=eq." + cc,
    )
    drop = []
    for row in cities:
        slug = (row.get("slug") or "").strip()
        name = (row.get("name") or "").strip()
        if slug in keep_slugs or slug.split("-")[0] in keep_slugs:
            continue
        if name.lower() in valid_names and " - " not in name:
            continue
        drop.append(row["id"])
    if drop:
        _patch_cities_inactive(url, service_role, drop)
    print("cleanup", cc, "gardées", len(cities) - len(drop), "désactivées", len(drop), flush=True)


def fill_quota(url, service_role, cc):
    target = TARGET_INT if cc in INT_OSM else TARGET
    cities = [
        row
        for row in fetch_all(
            url,
            service_role,
            "cities",
            "id,name,latitude,longitude,country_code",
            extra="&country_code=eq." + cc + "&is_active=eq.true",
        )
        if row.get("latitude") is not None
    ]
    rows = fetch_country_outings(url, service_role, cities)
    counts = defaultdict(int)
    seen = set()
    city_names = defaultdict(set)
    city_geos = defaultdict(set)
    city_origs = defaultdict(set)
    originals = []
    for row in rows:
        cid = row.get("city_id")
        counts[cid] += 1
        if row.get("source_name") and row.get("source_id"):
            seen.add((row["source_name"], row["source_id"]))
        nk = outing_name_key(row.get("name"))
        if cid is not None and nk:
            city_names[cid].add(nk)
        origin = outing_origin(row)
        if cid is not None and origin:
            city_origs[cid].add(origin)
        try:
            city_geos[cid].add((round(float(row["latitude"]), 3), round(float(row["longitude"]), 3)))
        except (TypeError, ValueError):
            pass
        if (row.get("source_name") or "") != "nearby" and row.get("latitude") is not None:
            if row.get("price_min") is not None:
                originals.append(row)
    print("quota", cc, "villes", len(cities), "sorties", len(rows), "sources", len(originals), flush=True)
    originals.sort(key=lambda r: (0 if has_usable_photo(r.get("photo_url")) else 1))
    payload = []
    for city in cities:
        cid = city["id"]
        need = target - counts[cid]
        if need <= 0:
            continue
        scored = []
        for src in originals:
            if src.get("city_id") == cid:
                continue
            dlat = (city["latitude"] - src["latitude"]) * 111.0
            dlon = (city["longitude"] - src["longitude"]) * 85.0
            dist = (dlat * dlat + dlon * dlon) ** 0.5
            if dist > (320 if cc in INT_OSM else MAX_NEAR_KM):
                continue
            scored.append((0 if has_usable_photo(src.get("photo_url")) else 1, dist, src))
        scored.sort(key=lambda x: (x[0], x[1]))
        used_names = set(city_names[cid])
        used_geo = set(city_geos[cid])
        used_origs = set(city_origs[cid])
        added = 0
        for _photo, _dist, src in scored:
            name = outing_name_key(src.get("name"))
            if name and name in used_names:
                continue
            orig_sid = src.get("source_id") or src.get("name") or "x"
            if orig_sid in used_origs:
                continue
            try:
                gkey = (round(float(src["latitude"]), 3), round(float(src["longitude"]), 3))
            except (TypeError, ValueError):
                gkey = None
            if gkey and gkey in used_geo:
                continue
            orig_sid = src.get("source_id") or src.get("name") or "x"
            sid = ("near-%s-%s" % (cid, orig_sid))[:200]
            if ("nearby", sid) in seen:
                continue
            clone = {
                "source_name": "nearby",
                "source_id": sid,
                "source_url": src.get("source_url"),
                "name": src["name"],
                "description": src.get("description"),
                "latitude": src["latitude"],
                "longitude": src["longitude"],
                "photo_url": src.get("photo_url"),
                "photo_license": src.get("photo_license"),
                "price_min": src.get("price_min"),
                "price_max": src.get("price_max") if src.get("price_max") is not None else src.get("price_min"),
                "currency": src.get("currency") or country_currency(cc),
                "address": src.get("address"),
                "category": src.get("category") or "Activités et loisirs",
                "kind": src.get("kind") or "place",
                "website_url": src.get("website_url"),
            }
            row = to_outing_row(clone, cid)
            if not row:
                continue
            payload.append(row)
            seen.add(("nearby", sid))
            if name:
                used_names.add(name)
            if gkey:
                used_geo.add(gkey)
            used_origs.add(orig_sid)
            added += 1
            counts[cid] += 1
            if added >= need:
                break
        if added:
            print("quota", city.get("name"), "+", added, "total", counts[cid], flush=True)
        if len(payload) >= 400:
            upsert_outings(url, service_role, payload)
            print("clones flush", cc, 400, flush=True)
            payload = []
    print("clones", cc, len(payload), flush=True)
    if payload:
        upsert_outings(url, service_role, payload)
    print("terminé quota", cc, len(payload), flush=True)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--cities-only", action="store_true")
    parser.add_argument("--osm-only", action="store_true")
    parser.add_argument("--quota-only", action="store_true")
    parser.add_argument("--cleanup-only", action="store_true")
    parser.add_argument("--dedupe-only", action="store_true")
    parser.add_argument("--hide-grocery", action="store_true")
    parser.add_argument("--skip-photos", action="store_true")
    parser.add_argument("--photo-limit", type=int, default=0)
    parser.add_argument("--north-only", action="store_true")
    parser.add_argument("--extras-only", action="store_true")
    parser.add_argument("--cc", default="BE,CH")
    args = parser.parse_args()
    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")
    if args.hide_grocery:
        deactivate_grocery_shopping(url, service_role)
        return
    codes = [c.strip().upper() for c in args.cc.split(",") if c.strip()]
    do_all = not (
        args.cities_only or args.osm_only or args.quota_only or args.cleanup_only or args.dedupe_only
    )
    if args.cleanup_only:
        for cc in codes:
            print("=== cleanup", cc, flush=True)
            cleanup_cities(url, service_role, cc)
        return
    if args.dedupe_only:
        for cc in codes:
            print("=== dedupe", cc, flush=True)
            dedupe_city_outings(url, service_role, cc)
        return
    for cc in codes:
        if args.cities_only or do_all:
            print("=== communes", cc, flush=True)
            els = fetch_communes(cc)
            print("osm admin", cc, len(els), flush=True)
            upsert_communes(url, service_role, cc, els)
        if args.osm_only or do_all:
            print("=== osm", cc, flush=True)
            import_osm(url, service_role, cc, north_only=args.north_only, extras_only=args.extras_only)
        if (args.osm_only or args.quota_only or do_all) and not args.skip_photos:
            print("=== photos", cc, flush=True)
            fill_for_country(url, service_role, cc, workers=4, chunk=80, limit=args.photo_limit)
        if args.quota_only or do_all:
            print("=== quota", cc, flush=True)
            fill_quota(url, service_role, cc)
            print("=== nearby photos", cc, flush=True)
            try:
                copy_for_country(url, service_role, cc)
            except Exception as exc:
                print("nearby photos", cc, "ignoré", exc, flush=True)
            print("=== dedupe", cc, flush=True)
            dedupe_city_outings(url, service_role, cc)


if __name__ == "__main__":
    main()
