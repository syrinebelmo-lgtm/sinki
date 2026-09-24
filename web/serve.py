# -*- coding: utf-8 -*-
"""Serveur local Sinki : site + API catalogue Supabase."""

import base64
import io
import json
import math
import os
import re
import smtplib
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import http.client
import urllib.error
import urllib.parse
import urllib.request
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from countries import country_name, search_countries
import local_auth
import billing as sinki_billing
import events as event_store

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "5173"))
sys.path.insert(0, os.path.join(ROOT, ".."))
from pipeline.quality import is_grocery_shop, resto_menu_span


def load_env():
    path = os.path.join(ROOT, "..", ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


def scrub_env():
    for name in ("SUPABASE_SERVICE_ROLE", "SUPABASE_URL", "RESEND_API_KEY"):
        raw = os.environ.get(name) or ""
        token = raw.strip().split()[0] if raw.strip() else ""
        if token:
            os.environ[name] = token


UNI_ESC = re.compile(r"\\u([0-9a-fA-F]{4})", re.I)
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
AVATAR_FILE_RE = re.compile(
    r"^/avatars/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.(jpg|jpeg|png|webp)$",
    re.I,
)
EVENT_PHOTO_RE = re.compile(
    r"^/event-photos/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.(jpg|jpeg|png|webp)$",
    re.I,
)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_MAIL_DOMAIN = "phone.sinki.app"
PHONE_DIGITS_RE = re.compile(r"^\d{8,15}$")
NIGHT_NAME = re.compile(
    r"\b(bar|pub|club|night|karaoke|karaok[eé]|lounge|disco|discoth|"
    r"beer|cocktail|tapas|rooftop|bo[iî]te|cabaret|concert|festival|"
    r"op[eé]ra|ballet|jazz|techno|electro|dancing|afterwork|"
    r"salle de concert|live\s*music|guinguette|soir[eé]e dansante)\b",
    re.I,
)
NIGHT_KEEP = re.compile(
    r"\b(bo[iî]te(?:\s+de\s+nuit)?|nightclub|night\s*club|discoth[eè]que|"
    r"karaoke|karaok[eé]|rooftop|afterwork|concert|festival|"
    r"cabaret|op[eé]ra|ballet|jazz|techno|electro|"
    r"dancing|dj\b|salle de concert|live\s*music|moulin rouge|"
    r"paradis latin|new morning|accor arena|"
    r"soir[eé]e\s+dansante|bal\s+populaire|guinguette|club\s+de\s+nuit)\b",
    re.I,
)
NIGHT_DROP = re.compile(
    r"\b(jeune public|enfance|enfant|enfants|kids|children|young spectator|"
    r"scolaire|maternelle|petite enfance|tout[-\s]?petit|for young|"
    r"exposition|exhibition|r[eé]trospective|salon international|"
    r"mus[eé]e|museum|photographe|peinture|painting|"
    r"cin[eé]ma|cinema|film|s[eé]ance|"
    r"dinosaure|coffee show|agriculture|alchimiste|"
    r"poney\s*club|centre [eé]questre|balade|"
    r"visite en famille|\ben famille\b|petit train|"
    r"galerie|vestiaire|mode en majest|haute couture)\b",
    re.I,
)
TO_EUR = {
    "EUR": 1.0,
    "CHF": 1.05,
    "GBP": 1.17,
    "USD": 0.92,
    "CAD": 0.67,
    "AUD": 0.61,
    "NZD": 0.55,
    "JPY": 0.0062,
    "CNY": 0.13,
    "KRW": 0.00068,
    "THB": 0.027,
    "INR": 0.011,
    "IDR": 0.000056,
    "MYR": 0.21,
    "SGD": 0.71,
    "PHP": 0.016,
    "VND": 0.000037,
    "TWD": 0.029,
    "HKD": 0.12,
    "AED": 0.25,
    "SAR": 0.25,
    "QAR": 0.25,
    "KWD": 3.0,
    "ILS": 0.25,
    "TRY": 0.027,
    "EGP": 0.019,
    "ZAR": 0.052,
    "BRL": 0.17,
    "MXN": 0.048,
    "ARS": 0.00092,
    "CLP": 0.00098,
    "COP": 0.00023,
    "PEN": 0.25,
    "PLN": 0.23,
    "CZK": 0.041,
    "HUF": 0.0026,
    "RON": 0.20,
    "BGN": 0.51,
    "SEK": 0.087,
    "NOK": 0.085,
    "DKK": 0.13,
    "ISK": 0.0072,
    "RUB": 0.010,
    "UAH": 0.022,
    "RSD": 0.0085,
    "BAM": 0.51,
    "MKD": 0.016,
    "ALL": 0.010,
    "MDL": 0.052,
    "GEL": 0.34,
    "AMD": 0.0024,
    "AZN": 0.54,
    "KZT": 0.0019,
    "UZS": 0.000072,
    "PKR": 0.0033,
    "BDT": 0.0076,
    "LKR": 0.0030,
    "NPR": 0.0068,
    "KES": 0.0071,
    "NGN": 0.00059,
    "MAD": 0.092,
    "TND": 0.30,
    "DZD": 0.0069,
    "XOF": 0.0015,
    "XAF": 0.0015,
}


def unescape_text(value):
    if not isinstance(value, str) or "\\u" not in value.lower():
        return value
    return UNI_ESC.sub(lambda m: chr(int(m.group(1), 16)), value)


def unescape_payload(obj):
    if isinstance(obj, str):
        return unescape_text(obj)
    if isinstance(obj, list):
        return [unescape_payload(item) for item in obj]
    if isinstance(obj, dict):
        return {key: unescape_payload(val) for key, val in obj.items()}
    return obj


def in_swiss_box(lat, lon):
    return 45.82 <= float(lat) <= 47.85 and 5.96 <= float(lon) <= 10.55


def outside_france_mainland(lat, lon):
    lat, lon = float(lat), float(lon)
    if lon < -5.5 or lon > 8.25 or lat < 42.2 or lat > 51.15:
        return True
    if lat >= 49.9 and lon <= 2.0:
        return True
    if lat >= 49.35 and lon >= 6.45:
        return True
    return in_swiss_box(lat, lon)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


STOP_WORDS = {
    "le", "la", "les", "de", "du", "des", "et", "un", "une", "au", "aux", "en", "the", "of", "a", "d", "l",
    "dans", "avec", "pour", "sur",
}
LODGING_NAME = re.compile(
    r"\b(campanile|ibis|novotel|mercure|kyriad|premiere classe|premi[eè]re classe|ibis budget|ibis styles|hostel|auberge de jeunesse|best western|holiday inn)\b",
    re.I,
)


def outing_name_key(name):
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def outing_tokens(name):
    return {w for w in outing_name_key(name).split() if len(w) > 2 and w not in STOP_WORDS}


def outing_core_key(name):
    k = outing_name_key(name)
    k = re.sub(
        r"(?:\s+(?:de|du|des))?\s+(lyon|paris|marseille|lille|toulouse|nantes|bordeaux|nice|strasbourg|rennes|grenoble|montpellier)$",
        "",
        k,
    )
    return k.strip()


def names_are_duplicates(a, b):
    ka, kb = outing_name_key(a), outing_name_key(b)
    ca, cb = outing_core_key(a), outing_core_key(b)
    if not ka or not kb:
        return False
    if ka == kb or (ca and ca == cb):
        return True
    shorter, longer = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    if len(shorter) >= 10 and (longer.startswith(shorter + " ") or (" " + shorter + " ") in (" " + longer + " ")):
        return True
    ta, tb = outing_tokens(a), outing_tokens(b)
    if not ta or not tb:
        return False
    inter = ta & tb
    if len(inter) >= 3 and len(inter) / min(len(ta), len(tb)) >= 0.6:
        return True
    union = ta | tb
    if union and len(inter) / len(union) >= 0.55:
        return True
    return False


def rows_are_duplicates(a, b):
    if names_are_duplicates(a.get("name"), b.get("name")):
        return True
    try:
        dist = haversine_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
    except Exception:
        return False
    ta, tb = outing_tokens(a.get("name")), outing_tokens(b.get("name"))
    union = ta | tb
    jacc = (len(ta & tb) / len(union)) if union else 0
    if dist < 0.08 and jacc >= 0.4:
        return True
    long_shared = {t for t in (ta & tb) if len(t) >= 5}
    if dist < 0.15 and len(long_shared) >= 2:
        return True
    return False


def has_usable_photo(url):
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        return False
    low = u.lower().split("?", 1)[0]
    if low.endswith(".pdf"):
        return False
    if "wikipedia.org/wiki/" in low and "special:filepath" not in low:
        return False
    return True


PAID_NAME = re.compile(
    r"\b(cin[eé]ma|cinema|th[eé][aâ]tre|theater|op[eé]ra|concert|festival|"
    r"parc d['’]attractions|theme park|zoo|aquarium|escape\s?game|"
    r"bowling|laser\s?game|karting|accrobranche|"
    r"bo[iî]te de nuit|nightclub|discoth[eè]que)\b",
    re.I,
)
FREE_LOOK = re.compile(
    r"\b(parc |jardin |square |promenade |plage |beach |sentier |"
    r"viewpoint |belv[eé]d[eè]re |cimeti[eè]re|m[eé]morial)\b",
    re.I,
)
TICKETS_NAME = re.compile(
    r"\b(mus[eé]e|museum|ch[aâ]teau|palais|palace|cath[eé]drale|monument|"
    r"tour eiffel|versailles|zoo|aquarium|cin[eé]ma|cinema|th[eé][aâ]tre|"
    r"theater|op[eé]ra|concert|festival|parc d['’]attractions|theme park|"
    r"escape\s?game|billetterie)\b",
    re.I,
)
ID_NAME = re.compile(
    r"\b(bo[iî]te|nightclub|discoth[eè]que|casino|afterwork)\b",
    re.I,
)
CAT_RESTO = "Restaurants et cafés"
CAT_SHOP = "Shopping"
CAT_WALK = "Lieux gratuits et balades"
CAT_HIKE = "Randonnées"
CAT_CULT = "Musées et culture"
CAT_NIGHT = "Soirées et concerts"
CAT_PLAY = "Activités et loisirs"


def outing_blob(row):
    return " ".join(
        str(row.get(key) or "")
        for key in ("name", "description", "category", "kind")
    )


def is_nightlife(row):
    if (row.get("category") or "") in (CAT_SHOP, CAT_WALK, CAT_HIKE):
        return False
    name = row.get("name") or ""
    blob = outing_blob(row)
    if NIGHT_DROP.search(blob) and not NIGHT_KEEP.search(name):
        return False
    if NIGHT_KEEP.search(name) or NIGHT_NAME.search(name):
        return True
    if (row.get("category") or "") == CAT_NIGHT and NIGHT_KEEP.search(blob) and not NIGHT_DROP.search(blob):
        return True
    return False


def _money_pair(row):
    try:
        a = float(row["price_min"]) if row.get("price_min") is not None else None
    except (TypeError, ValueError):
        a = None
    try:
        b = float(row["price_max"]) if row.get("price_max") is not None else a
    except (TypeError, ValueError):
        b = a
    if a is not None and a < 0:
        a = 0.0
    if b is not None and b < 0:
        b = 0.0
    if a is not None and b is not None and b < a:
        b = a
    return a, b


def qc_outing(row):
    """Photo cassée → vide. 0 € sur un lieu payant → prix à confirmer. Billets / pièce d’identité seulement si utile."""
    if not isinstance(row, dict):
        return row
    url = (row.get("photo_url") or "").strip()
    if url and not has_usable_photo(url):
        row["photo_url"] = None
    cat = row.get("category") or ""
    name = row.get("name") or ""
    a, b = _money_pair(row)
    kind = row.get("kind") or ""
    is_resto = cat == CAT_RESTO or kind == "restaurant"
    unknown = False
    if is_resto:
        span = resto_menu_span(description=row.get("description") or "")
        if span:
            a, b = span
        if a is not None and a <= 0:
            a = None
        if b is not None and b <= 0:
            b = None
        if a is None and b is None:
            unknown = True
        elif a is None:
            a = b
        elif b is None:
            b = a
        eur = price_eur(a, row.get("currency")) if a is not None else 0.0
        if a is not None and eur > 400:
            unknown = True
    else:
        eur = price_eur(a, row.get("currency")) if a is not None else 0.0
    free_look = cat in (CAT_WALK, CAT_HIKE, CAT_SHOP) or bool(FREE_LOOK.search(name))
    paid_look = (
        cat in (CAT_RESTO, CAT_NIGHT, CAT_PLAY)
        or bool(PAID_NAME.search(name))
        or (cat == CAT_CULT and not FREE_LOOK.search(name))
    )
    if not is_resto:
        if a is not None and eur > 400 and cat != CAT_SHOP:
            unknown = True
        elif paid_look and not free_look and a == 0 and (b is None or b == 0):
            unknown = True
    if unknown:
        row["price_min"] = None
        row["price_max"] = None
        row["price_unknown"] = True
    else:
        row["price_min"] = a
        row["price_max"] = b if b is not None else a
        row["price_unknown"] = False
    if cat == CAT_NIGHT and not is_nightlife(row):
        row["category"] = CAT_CULT
        cat = CAT_CULT
    need_tickets = False
    need_id = bool(ID_NAME.search(name))
    if not FREE_LOOK.search(name):
        if TICKETS_NAME.search(name) or (cat == CAT_CULT and not FREE_LOOK.search(name)):
            need_tickets = True
        if cat == CAT_NIGHT and TICKETS_NAME.search(name):
            need_tickets = True
        if cat == CAT_PLAY and TICKETS_NAME.search(name):
            need_tickets = True
    if cat in (CAT_WALK, CAT_HIKE, CAT_SHOP, CAT_RESTO):
        need_tickets = False
    row["need_tickets"] = need_tickets
    row["need_id"] = need_id
    return row


def bring_from_osm(tags, row):
    if not tags:
        return
    fee = (tags.get("fee") or "").lower().strip()
    reservation = (tags.get("reservation") or tags.get("booking") or "").lower().strip()
    tickets = (tags.get("tickets") or "").lower().strip()
    amenity = (tags.get("amenity") or "").lower().strip()
    tourism = (tags.get("tourism") or "").lower().strip()
    if fee in ("no", "free", "none", "0"):
        row["need_tickets"] = False
        if amenity not in ("restaurant", "cafe", "fast_food", "ice_cream", "food_court", "biergarten"):
            row["price_min"] = 0.0
            row["price_max"] = 0.0
            row["price_unknown"] = False
    span = resto_menu_span(tags, row.get("description") or "")
    resto_amenity = amenity in ("restaurant", "cafe", "fast_food", "ice_cream", "food_court", "biergarten")
    if span and (resto_amenity or row.get("category") == CAT_RESTO):
        row["price_min"], row["price_max"] = span
        row["price_unknown"] = False
    if reservation in ("required", "yes") or tickets in ("yes", "online"):
        row["need_tickets"] = True
    if amenity in ("nightclub", "casino") or tourism == "nightclub":
        row["need_id"] = True
    age = tags.get("min_age") or tags.get("age:min") or ""
    try:
        if int(re.sub(r"\D", "", str(age)) or 0) >= 18:
            row["need_id"] = True
    except (TypeError, ValueError):
        pass


def price_eur(amount, currency):
    if amount is None:
        return 0.0
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return 0.0
    rate = TO_EUR.get(str(currency or "EUR").upper())
    if rate is None:
        return val if val <= 80 else val * 0.03
    return val * rate


def outing_rank(row):
    photo = 0 if has_usable_photo(row.get("photo_url")) else 1
    complete = 0 if photo == 0 and row.get("latitude") is not None and (row.get("name") or "").strip() else 1
    nearby = 0 if row.get("source_name") != "nearby" else 1
    dist = row.get("distance_km")
    if dist is None:
        dist = 999
    return (photo, complete, nearby, dist)


def quality_pool(rows):
    best = {}
    for row in rows:
        key = outing_core_key(row.get("name")) or outing_name_key(row.get("name"))
        if not key:
            continue
        prev = best.get(key)
        if prev is None or outing_rank(row) < outing_rank(prev):
            best[key] = row
    ranked = sorted(best.values(), key=outing_rank)
    kept = []
    for row in ranked:
        if any(rows_are_duplicates(row, prev) for prev in kept):
            continue
        kept.append(row)
        if len(kept) >= 120:
            break
    return kept


def diversify_categories(rows, limit=120):
    buckets = {}
    order = []
    for row in rows:
        cat = row.get("category") or "?"
        buckets.setdefault(cat, []).append(row)
        if cat not in order:
            order.append(cat)
    mixed = []
    while len(mixed) < limit and any(buckets.values()):
        progressed = False
        for cat in order:
            if buckets[cat]:
                mixed.append(buckets[cat].pop(0))
                progressed = True
            if len(mixed) >= limit:
                break
        if not progressed:
            break
    return mixed


_tls = threading.local()


def supabase_request(method, path, body=None):
    parsed = urllib.parse.urlparse(os.environ["SUPABASE_URL"])
    key = os.environ["SUPABASE_SERVICE_ROLE"]
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "apikey": key,
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
        "Connection": "keep-alive",
    }
    target = (parsed.path.rstrip("/") or "") + "/rest/v1/" + path
    url = parsed.scheme + "://" + parsed.netloc + target
    timeout = 12 if method == "GET" else 60
    last_err = None
    for attempt in (0, 1):
        conn = getattr(_tls, "sb", None)
        if conn is None:
            conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=timeout)
            _tls.sb = conn
        try:
            conn.request(method, target, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status >= 400:
                raise urllib.error.HTTPError(url, resp.status, resp.reason, resp.headers, io.BytesIO(raw))
            text = raw.decode("utf-8")
            return json.loads(text) if text else []
        except urllib.error.HTTPError:
            raise
        except (http.client.HTTPException, ConnectionError, BrokenPipeError, OSError) as exc:
            last_err = exc
            try:
                conn.close()
            except Exception:
                pass
            _tls.sb = None
            if attempt:
                raise
    if last_err:
        raise last_err
    return []


def supabase_select(query):
    return supabase_request("GET", query)


def safe_select(query):
    try:
        return supabase_request("GET", query)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        if exc.code >= 500 or "57014" in detail or "timeout" in detail.lower():
            return []
        raise
    except Exception:
        return []


def supabase_outings(filters, limit, pictured_only=False):
    limit = max(1, min(int(limit or 80), 80))
    base = "outings?select=" + SELECT + "&is_active=eq.true" + filters
    pictured = safe_select(base + "&photo_url=not.is.null&limit=" + str(limit))
    if pictured_only:
        return pictured
    rest = safe_select(base + "&limit=" + str(limit))
    return pictured + rest


FEATURED_FR = (
    "paris",
    "lyon",
    "marseille",
    "toulouse",
    "lille",
    "bordeaux",
    "nantes",
    "nice",
    "strasbourg",
    "montpellier",
    "rennes",
)

FEATURED_INT = {
    "CH": (
        "geneve",
        "zurich",
        "lausanne",
        "bale",
        "berne",
        "zermatt",
        "interlaken",
        "lucerne",
    ),
    "BE": (
        "bruxelles",
        "anvers",
        "gand",
        "bruges",
        "liege",
        "namur",
    ),
    "IT": ("roma-it", "milano-it", "firenze-it", "venezia-it", "napoli-it", "torino-it"),
    "ES": ("madrid-es", "barcelona-es", "valencia-es", "seville-es", "malaga-es", "palma-de-mallorca-es"),
    "DE": ("berlin-de", "munchen-landeshauptstadt-de", "hamburg-freie-und-hansestadt-de", "koln-de", "frankfurt-am-main-de"),
    "GB": ("london-gb", "manchester-gb", "edinburgh-gb", "birmingham-gb", "glasgow-gb", "liverpool-gb"),
    "PT": ("lisbon-pt", "porto-pt", "faro-pt"),
    "NL": ("amsterdam-nl", "rotterdam-nl", "utrecht-nl", "den-haag-nl"),
    "GR": ("athens-gr", "thessaloniki-gr", "irakleio-gr"),
    "AT": ("vienna-at", "salzburg-at", "innsbruck-at"),
    "HR": ("zagreb-hr", "split-hr", "dubrovnik-hr"),
    "CZ": ("prague-cz", "brno-cz", "ostrava-cz"),
    "HU": ("budapest-hu", "debrecen-hu", "szeged-hu"),
    "PL": ("warsaw-pl", "krakow-pl", "gdansk-pl"),
    "IE": ("dublin-ie", "cork-ie", "galway-ie"),
    "DK": ("copenhagen-dk", "aarhus-dk", "odense-dk"),
    "SE": ("stockholm-se", "gothenburg-se", "malmo-se"),
    "NO": ("oslo-no", "bergen-no", "trondheim-no"),
    "FI": ("helsinki-fi", "tampere-fi", "turku-fi"),
    "RO": ("bucharest-ro", "cluj-napoca-ro", "brasov-ro"),
    "BG": ("sofia-bg", "plovdiv-bg", "varna-bg"),
    "SK": ("bratislava-sk", "kosice-sk"),
    "SI": ("ljubljana-si", "maribor-si"),
    "LU": ("luxembourg-lu",),
    "EE": ("tallinn-ee", "tartu-ee"),
    "LV": ("riga-lv", "daugavpils-lv"),
    "LT": ("vilnius-lt", "kaunas-lt"),
    "RS": ("belgrade-rs", "novi-sad-rs"),
    "BA": ("sarajevo-ba", "mostar-ba"),
    "ME": ("podgorica-me", "kotor-me"),
    "AL": ("tirana-al", "durres-al"),
    "CY": ("nicosia-cy", "limassol-cy"),
    "MT": ("valletta-mt",),
    "IS": ("reykjavik-is",),
    "AD": ("andorra-la-vella-ad",),
    "LI": ("vaduz-li",),
    "MC": ("monaco-mc",),
    "MK": ("skopje-mk", "ohrid-mk"),
    "XK": ("pristina-xk", "prizren-xk"),
    "MD": ("chisinau-md",),
    "US": ("new-york-city-us", "los-angeles-us", "miami-us", "las-vegas-us", "chicago-us"),
    "MA": ("marrakech-ma", "casablanca-ma", "rabat-ma", "fes-ma", "agadir-ma"),
    "JP": ("tokyo-jp", "osaka-jp", "kyoto-jp"),
    "CA": ("montreal-ca", "toronto-ca", "vancouver-ca", "quebec-ca"),
    "TH": ("bangkok-th", "chiang-mai-th", "phuket-th", "pattaya-th"),
}


def nominatim_cities(q, country):
    country = (country or "").strip().lower()
    term = (q or "").strip()
    if len(term) < 2 or len(country) != 2:
        return []
    qs = urllib.parse.urlencode(
        {
            "q": term,
            "countrycodes": country,
            "format": "json",
            "limit": 8,
            "addressdetails": 0,
            "accept-language": "fr",
        }
    )
    req = urllib.request.Request(
        "https://nominatim.openstreetmap.org/search?" + qs,
        headers={"User-Agent": "Sinki/1.0 (https://sinki-sorties.fly.dev)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    out = []
    seen = set()
    for row in rows:
        name = (row.get("display_name") or "").split(",")[0].strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        seen.add(key)
        out.append(
            {
                "id": "",
                "name": name,
                "slug": "",
                "latitude": lat,
                "longitude": lon,
                "country_code": country.upper(),
            }
        )
    return out


GEO_CACHE = {}


def _is_private_ip(ip):
    ip = (ip or "").split("%")[0].strip()
    if not ip or ip in ("::1", "127.0.0.1", "localhost", "0.0.0.0"):
        return True
    if ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("169.254."):
        return True
    if ip.startswith("172."):
        try:
            second = int(ip.split(".")[1])
            if 16 <= second <= 31:
                return True
        except (IndexError, ValueError):
            return True
    if ip.startswith("fc") or ip.startswith("fd") or ip.startswith("fe80"):
        return True
    return False


def lookup_geo(ip):
    key = ip if ip and not _is_private_ip(ip) else "public"
    hit = GEO_CACHE.get(key)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    urls = []
    if key != "public":
        urls.append("https://ipapi.co/" + urllib.parse.quote(ip) + "/json/")
        urls.append("http://ip-api.com/json/" + urllib.parse.quote(ip) + "?fields=status,country,countryCode")
    urls.append("https://ipapi.co/json/")
    urls.append("http://ip-api.com/json/?fields=status,country,countryCode")
    payload = {}
    for url in urls:
        try:
            data = _http_json(url, 6)
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("error"):
            continue
        code = (data.get("country_code") or data.get("countryCode") or "").upper()
        if len(code) != 2:
            continue
        name = data.get("country_name") or data.get("country") or country_name(code)
        payload = {"code": code, "name": country_name(code) or name}
        break
    GEO_CACHE[key] = (time.time(), payload)
    return payload


FEATURED_ROWS = {}
FEATURED_LOCK = threading.Lock()
CITY_SEARCH_CACHE = {}
CITY_SEARCH_LOCK = threading.Lock()
CITY_SEARCH_TTL = 600


def featured_city_rows(country):
    country = (country or "").strip().upper()
    with FEATURED_LOCK:
        cached = FEATURED_ROWS.get(country)
        if cached is not None:
            return cached
    slugs = FEATURED_INT.get(country) or (FEATURED_FR if country == "FR" else ())
    rows = []
    if slugs:
        rows = supabase_select(
            "cities?select=id,name,slug,latitude,longitude,country_code&is_active=eq.true&slug=in.("
            + ",".join(slugs)
            + ")&country_code=eq."
            + country
            + "&limit=20"
        )
    with FEATURED_LOCK:
        FEATURED_ROWS[country] = rows
    return rows


def _cached_city_search(key):
    with CITY_SEARCH_LOCK:
        hit = CITY_SEARCH_CACHE.get(key)
        if hit and time.time() - hit[0] < CITY_SEARCH_TTL:
            return hit[1]
    return None


def _store_city_search(key, rows):
    with CITY_SEARCH_LOCK:
        CITY_SEARCH_CACHE[key] = (time.time(), rows)
        if len(CITY_SEARCH_CACHE) > 400:
            oldest = sorted(CITY_SEARCH_CACHE.items(), key=lambda item: item[1][0])[:80]
            for old_key, _ in oldest:
                CITY_SEARCH_CACHE.pop(old_key, None)


def search_cities(q, country=""):
    country = (country or "").strip().upper()
    term = (q or "").strip()
    if country in ("", "INT") or len(country) != 2:
        return []
    zone = "&country_code=eq." + country
    term_l = _fold_query(term)
    cache_key = (country, term_l)
    cached = _cached_city_search(cache_key)
    if cached is not None:
        return cached
    if len(term) < 1:
        rows = featured_city_rows(country)[:12]
        _store_city_search(cache_key, rows)
        return rows
    safe = "".join(ch if ch not in ",()*%" else " " for ch in term)[:40].strip()
    if not safe:
        return []
    if len(safe) <= 2:
        pattern = urllib.parse.quote(safe + "*")
    else:
        pattern = urllib.parse.quote("*" + safe + "*")
    pinned = [
        row
        for row in featured_city_rows(country)
        if _fold_query(row.get("name") or "").startswith(term_l)
        or _fold_query(row.get("slug") or "").startswith(term_l)
    ]
    local = supabase_select(
        "cities?select=id,name,slug,latitude,longitude,country_code&is_active=eq.true&or=(name.ilike."
        + pattern
        + ",slug.ilike."
        + pattern
        + ")"
        + zone
        + "&order=name.asc&limit=40"
    )
    featured_ids = {row.get("id") for row in pinned}
    seen = set(featured_ids)
    merged = list(pinned)
    for row in local:
        if row.get("id") in seen:
            continue
        merged.append(row)
        seen.add(row.get("id"))
    merged.sort(key=lambda row: (
        0 if row.get("id") in featured_ids else 1,
        0 if _fold_query(row.get("name") or "") == term_l else 1,
        0 if _fold_query(row.get("name") or "").startswith(term_l) else 1,
        0 if "(" not in (row.get("name") or "") else 1,
        len(row.get("name") or ""),
        row.get("name") or "",
    ))
    local = merged[:12]
    if country == "FR" or country in FEATURED_INT or len(term) <= 2:
        _store_city_search(cache_key, local)
        return local
    extra = nominatim_cities(term, country)
    seen = {(row.get("name") or "").lower() for row in local}
    for row in extra:
        key = (row.get("name") or "").lower()
        if key in seen:
            continue
        local.append(row)
        seen.add(key)
        if len(local) >= 8:
            break
    local.sort(key=lambda row: (
        0 if _fold_query(row.get("name") or "").startswith(term_l) else 1,
        row.get("name") or "",
    ))
    _store_city_search(cache_key, local)
    return local


THRIFT_NAME = re.compile(
    r"thrift|vintage|second[\s-]?hand|friper|fripper|fripe|charity|chatuchak|"
    r"flea|kilo\s?shop|depot.?vente|d[eé]p[oô]t|ตลาดนัด|มือสอง|op.?shop",
    re.I,
)


def shopping_is_thrift(row):
    blob = " ".join(
        str(row.get(key) or "")
        for key in ("name", "category", "kind", "description", "types")
    )
    return bool(THRIFT_NAME.search(blob))


def search_cities_world(q):
    term = (q or "").strip()
    if len(term) < 2:
        return []
    safe = "".join(ch if ch not in ",()*%" else " " for ch in term)[:40].strip()
    if not safe:
        return []
    pattern = urllib.parse.quote(safe + "*" if len(safe) <= 2 else "*" + safe + "*")
    term_l = _fold_query(term)
    slug_hits = []
    for slugs in FEATURED_INT.values():
        for slug in slugs:
            folded = slug.replace("-", " ")
            if term_l in slug or term_l in folded or slug.startswith(term_l) or folded.startswith(term_l):
                slug_hits.append(slug)
    pinned = []
    if slug_hits:
        pinned = supabase_select(
            "cities?select=id,name,slug,latitude,longitude,country_code&is_active=eq.true&slug=in.("
            + ",".join(slug_hits[:24])
            + ")&limit=24"
        )
    local = supabase_select(
        "cities?select=id,name,slug,latitude,longitude,country_code&is_active=eq.true&or=(name.ilike."
        + pattern
        + ",slug.ilike."
        + pattern
        + ")&order=name.asc&limit=40"
    )
    seen = set()
    merged = []
    for row in list(pinned) + list(local):
        cid = row.get("id")
        if cid in seen:
            continue
        seen.add(cid)
        merged.append(row)
        if len(merged) >= 12:
            break
    if merged:
        return merged
    guessed = None
    for cc, slugs in FEATURED_INT.items():
        if any(term_l in slug.replace("-", " ") or slug.startswith(term_l) for slug in slugs):
            guessed = cc
            break
    if guessed:
        return search_cities(term, guessed)[:8]
    return []


def nearest_city_row(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return None
    best = None
    best_d = 1e9
    for km in (30, 90, 220):
        dlat = km / 111.0
        dlon = km / (111.0 * max(0.2, math.cos(math.radians(lat))))
        rows = safe_select(
            "cities?select=id,name,slug,latitude,longitude,country_code&is_active=eq.true"
            "&latitude=gte."
            + str(lat - dlat)
            + "&latitude=lte."
            + str(lat + dlat)
            + "&longitude=gte."
            + str(lon - dlon)
            + "&longitude=lte."
            + str(lon + dlon)
            + "&limit=80"
        )
        for row in rows:
            try:
                dist = haversine_km(lat, lon, float(row["latitude"]), float(row["longitude"]))
            except (TypeError, ValueError, KeyError):
                continue
            if dist < best_d:
                best_d = dist
                best = row
        if best:
            out = dict(best)
            out["distance_km"] = round(best_d, 1)
            return out
    return None


SELECT = (
    "id,city_id,kind,category,name,description,address,latitude,longitude,"
    "price_min,price_max,currency,duration_minutes,indoor,photo_url,photo_license,"
    "source_url,website_url,source_name,source_id"
)


def city_country(city_id):
    if not city_id:
        return None
    rows = supabase_select(
        "cities?id=eq." + urllib.parse.quote(str(city_id)) + "&select=id,country_code"
    )
    return (rows[0].get("country_code") if rows else None)


def swiss_city_ids():
    return [
        row["id"]
        for row in safe_select("cities?country_code=eq.CH&select=id&limit=200")
        if row.get("id") is not None
    ]


def fetch_outings(params):
    city_id = (params.get("city_id") or [""])[0].strip()
    try:
        lat = float(params.get("lat", [None])[0])
        lon = float(params.get("lon", [None])[0])
    except (TypeError, ValueError):
        lat = lon = None
    try:
        radius = float((params.get("radius_km") or ["15"])[0])
    except ValueError:
        radius = 15
    budget_raw = (params.get("budget") or [""])[0]
    budget = float(budget_raw) if budget_raw not in ("", None) else None
    typ = (params.get("type") or ["all"])[0]
    if typ == "shopping" and radius < 20:
        radius = 20.0
    indoor = (params.get("indoor") or ["any"])[0]
    need_photo = (params.get("need_photo") or ["1"])[0] != "0"
    if not city_id and lat is None:
        return []

    origin_cc = city_country(city_id) if city_id else None
    type_cat = None
    if typ == "shopping":
        type_cat = "Shopping"
    elif typ == "randonnee":
        type_cat = "Randonnées"
    type_filter = ("&category=eq." + urllib.parse.quote(type_cat)) if type_cat else ""

    def geo_rows(km, pictured_only=False):
        found = []
        if city_id:
            found.extend(supabase_outings("&city_id=eq." + urllib.parse.quote(city_id) + type_filter, 80, pictured_only))
        if lat is None or lon is None or km <= 0:
            return found
        dlat = km / 111.0
        dlon = km / (111.0 * max(0.2, math.cos(math.radians(lat))))
        extra = (
            "&latitude=gte."
            + str(lat - dlat)
            + "&latitude=lte."
            + str(lat + dlat)
            + "&longitude=gte."
            + str(lon - dlon)
            + "&longitude=lte."
            + str(lon + dlon)
        )
        light = pictured_only or typ == "randonnee" or (typ == "shopping" and need_photo)
        if origin_cc and origin_cc != "FR":
            nearby_cities = safe_select(
                "cities?select=id&country_code=eq."
                + urllib.parse.quote(origin_cc)
                + extra
                + "&limit=80"
            )
            ids = [row["id"] for row in nearby_cities if row.get("id") is not None]
            if city_id:
                try:
                    cid = int(city_id)
                    if cid not in ids:
                        ids.append(cid)
                except (TypeError, ValueError):
                    pass
            if ids:
                inlist = ",".join(str(i) for i in ids)
                found.extend(supabase_outings("&city_id=in.(" + inlist + ")" + type_filter, 80, light))
            else:
                found.extend(supabase_outings(extra + type_filter, 80, light))
        elif origin_cc == "FR" and typ == "randonnee":
            found.extend(supabase_outings("&category=eq." + urllib.parse.quote("Randonnées") + extra, 80, True))
        elif typ == "shopping":
            found.extend(supabase_outings("&category=eq." + urllib.parse.quote("Shopping") + extra, 80, True))
        else:
            found.extend(supabase_outings(extra, 80, light))
        return found

    def unique_rows(items):
        seen = set()
        out_rows = []
        for row in items:
            if not row.get("id") or row["id"] in seen:
                continue
            seen.add(row["id"])
            out_rows.append(row)
        return out_rows

    def keep_row(row, beyond):
        if row.get("latitude") is None or row.get("longitude") is None:
            return False
        if not (row.get("name") or "").strip():
            return False
        qc_outing(row)
        if lat is not None:
            dist = haversine_km(lat, lon, row["latitude"], row["longitude"])
            row["distance_km"] = round(dist, 1)
            if not beyond and dist > radius:
                return False
        pmin_eur = price_eur(row.get("price_min"), row.get("currency"))
        cat = row.get("category") or ""
        kind = row.get("kind") or ""
        if budget is not None and cat != "Shopping" and typ != "shopping":
            if row.get("price_unknown"):
                if budget <= 0:
                    return False
            elif pmin_eur > budget:
                return False
        if typ == "activites" and cat != "Activités et loisirs":
            return False
        if typ == "evenements" and kind != "event":
            return False
        if typ == "restaurants" and cat != "Restaurants et cafés" and kind != "restaurant":
            return False
        if typ == "balades" and cat not in ("Lieux gratuits et balades", "Randonnées"):
            return False
        if typ == "randonnee":
            if cat != "Randonnées":
                return False
            if origin_cc == "FR":
                if (not beyond) and not has_usable_photo(row.get("photo_url")):
                    return False
                if outside_france_mainland(row["latitude"], row["longitude"]):
                    return False
        if typ == "soirees":
            if not is_nightlife(row):
                return False
        if typ == "culture" and cat != "Musées et culture":
            return False
        if typ == "shopping" and cat != "Shopping":
            return False
        if indoor == "in" and row.get("indoor") is False:
            return False
        if indoor == "out" and row.get("indoor") is True:
            return False
        if LODGING_NAME.search(row.get("name") or ""):
            return False
        if (cat == "Shopping" or typ == "shopping") and is_grocery_shop(row.get("name")):
            return False
        row["price_eur"] = round(pmin_eur, 2)
        return True

    def pool_from(items, beyond):
        kept = [row for row in unique_rows(items) if keep_row(row, beyond)]
        return quality_pool(unescape_payload(kept))

    def mark_relax(rows, reason):
        for row in rows:
            row["search_relax"] = reason
        return rows

    pooled = pool_from(geo_rows(radius), False)
    if not pooled and indoor != "any":
        saved_indoor = indoor
        indoor = "any"
        pooled = mark_relax(pool_from(geo_rows(radius), False), "indoor")
        indoor = saved_indoor
    if not pooled and typ == "soirees" and lat is not None:
        saved_r = radius
        for km in (30, 60):
            radius = km
            extra = pool_from(geo_rows(km), False)
            if extra:
                pooled = mark_relax(extra, "far")
                break
        radius = saved_r
    if not pooled and typ not in ("all", "shopping", "randonnee"):
        saved_typ = typ
        typ = "all"
        pooled = mark_relax(pool_from(geo_rows(radius), False), "type")
        typ = saved_typ
    if pooled:
        if typ == "all" or pooled[0].get("search_relax") in ("type", "city"):
            return diversify_categories(pooled)
        return pooled
    if not pooled and origin_cc and origin_cc != "FR" and typ != "shopping":
        slugs = FEATURED_INT.get(origin_cc) or ()
        if slugs:
            inslugs = ",".join(slugs)
            feat = safe_select(
                "cities?select=id,name,slug,latitude,longitude&slug=in.(" + inslugs + ")"
            )
            ids = [row["id"] for row in feat if row.get("id") is not None]
            if ids:
                saved_indoor = indoor
                indoor = "any"
                inlist = ",".join(str(i) for i in ids)
                pooled = mark_relax(pool_from(supabase_outings("&city_id=in.(" + inlist + ")" + type_filter, 80, False), True), "city")
                if not pooled:
                    pooled = mark_relax(pool_from(supabase_outings("&city_id=in.(" + inlist + ")", 80, False), True), "city")
                indoor = saved_indoor
                if pooled:
                    return diversify_categories(pooled)
    if lat is None:
        return []
    nearest = []
    if typ == "randonnee" and origin_cc == "FR" and type_filter:
        nearest = pool_from(geo_rows(250, False), True)
        if not nearest:
            extra = type_filter + "&latitude=gte.41.3&latitude=lte.51.2&longitude=gte.-5.3&longitude=lte.8.3"
            nearest = pool_from(supabase_outings(extra, 60, False), True)
    else:
        for km in (80, 180):
            nearest = pool_from(geo_rows(km, True), True)
            if nearest:
                break
        if not nearest and type_filter:
            nearest = pool_from(supabase_outings(type_filter, 60, True), True)
    nearest.sort(key=lambda row: row.get("distance_km") if row.get("distance_km") is not None else 999)
    for row in nearest:
        row["search_fallback"] = "nearest"
    return nearest


def _fold_query(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


ACTIVITY_CATS = (
    (("musee", "museum"), "Musées et culture"),
    (("resto", "restaurant", "cafe"), "Restaurants et cafés"),
    (("concert", "soiree", "bar"), "Soirées et concerts"),
    (("rando", "randonnee", "hike"), "Randonnées"),
    (("balade", "parc", "jardin"), "Lieux gratuits et balades"),
    (("shopping", "friperie", "fripperie", "friperies", "fripperies", "frip", "frips", "fripe", "mall", "thrift", "vintage", "secondhand", "charity"), "Shopping"),
)
COUNTRY_HINTS = {
    "france": "FR",
    "suisse": "CH",
    "switzerland": "CH",
    "belgique": "BE",
    "belgium": "BE",
    "thailande": "TH",
    "thailand": "TH",
}
CAT_TYPE = {
    "Musées et culture": "culture",
    "Restaurants et cafés": "restaurants",
    "Soirées et concerts": "soirees",
    "Randonnées": "randonnee",
    "Lieux gratuits et balades": "balades",
    "Activités et loisirs": "activites",
    "Shopping": "shopping",
}


def _coords_hint_ok(row, hint):
    if not hint:
        return True
    try:
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
    except (TypeError, ValueError):
        return False
    if hint == "FR":
        if 41.32 <= lat <= 43.05 and 8.15 <= lon <= 9.57:
            return True
        if 42.28 <= lat <= 51.12 and -5.15 <= lon <= 8.23:
            if 45.85 <= lat <= 47.85 and 5.96 <= lon <= 10.5 and lat >= 46.12:
                return False
            return True
        return False
    if hint == "CH":
        return 45.80 <= lat <= 47.85 and 5.90 <= lon <= 10.55
    return True


def _best_city(cities, place, country_hint=None):
    folded = _fold_query(place)
    country_hint = (country_hint or "").upper()
    exact_pref = []
    exact = []
    for city in cities:
        name = _fold_query(city.get("name") or "")
        if name != folded:
            continue
        if country_hint and city.get("country_code") == country_hint:
            exact_pref.append(city)
        elif city.get("country_code") == "FR" and not country_hint:
            exact_pref.append(city)
        else:
            exact.append(city)
    if exact_pref:
        return exact_pref[0]
    if exact:
        return exact[0]
    if country_hint:
        for city in cities:
            if city.get("country_code") == country_hint:
                return city
    for city in cities:
        if city.get("country_code") == "FR":
            return city
    return cities[0] if cities else None


def search_catalog(q, country=""):
    raw = (q or "").strip()
    folded = _fold_query(raw)
    tokens = re.findall(r"[a-z0-9]+", folded)
    skip = {"en", "au", "aux", "de", "du", "des", "le", "la", "les", "un", "une"}
    country_hint = (country or "").strip().upper()
    if len(country_hint) != 2:
        country_hint = None
    activity_cat = None
    rest = []
    for tok in tokens:
        if tok in skip:
            continue
        if tok in COUNTRY_HINTS and not country_hint:
            country_hint = COUNTRY_HINTS[tok]
            continue
        matched = False
        for keys, cat in ACTIVITY_CATS:
            hit = any(
                tok == k or (len(tok) >= 4 and (k.startswith(tok) or tok.startswith(k)))
                for k in keys
            )
            if not hit and cat == "Shopping" and tok.startswith("frip"):
                hit = True
            if hit:
                activity_cat = cat
                matched = True
                break
        if not matched:
            rest.append(tok)
    place = " ".join(rest)
    cities = []
    if country_hint and len(folded) < 1 and not activity_cat:
        return {"cities": [], "outings": []}
    if country_hint and len(folded) <= 2 and not activity_cat:
        cities = search_cities(place or raw, country_hint)[:8]
        return {"cities": cities, "outings": []}
    if place:
        if country_hint:
            cities = search_cities(place, country_hint)[:8]
        else:
            cities = search_cities_world(place)[:12]
    elif country_hint:
        cities = search_cities(place or raw, country_hint)[:8]
        if not cities:
            cities = search_cities("", country_hint)[:8]
    elif not activity_cat and len(folded) >= 2:
        cities = search_cities_world(raw)[:12]

    outings = []
    if cities:
        best = _best_city(cities, place or raw, country_hint)
        if best and best.get("latitude") is not None and best.get("longitude") is not None:
            typ = CAT_TYPE.get(activity_cat, "all")
            radius = "35" if typ == "shopping" else "20"
            qs = {
                "lat": [str(best["latitude"])],
                "lon": [str(best["longitude"])],
                "radius_km": [radius],
                "type": [typ],
            }
            if best.get("id"):
                qs["city_id"] = [str(best["id"])]
            if typ == "shopping":
                qs["need_photo"] = ["0"]
            outings = fetch_outings(qs)
            if typ == "shopping" and outings:
                thrift = [row for row in outings if shopping_is_thrift(row)]
                if thrift:
                    rest_shop = [row for row in outings if row not in thrift]
                    outings = thrift + rest_shop
    if not outings and len(folded) >= 2:
        safe = "".join(ch if ch not in ",()*%" else " " for ch in (place or raw))[:40].strip()
        path = "outings?select=" + SELECT + "&is_active=eq.true"
        pictured = "&photo_url=like.http*"
        if activity_cat:
            path += "&category=eq." + urllib.parse.quote(activity_cat)
            if activity_cat == "Musées et culture" and not place:
                path += "&or=(name.ilike." + urllib.parse.quote("*musee*") + ",name.ilike." + urllib.parse.quote("*musée*") + ",name.ilike." + urllib.parse.quote("*museum*") + ")"
        elif safe:
            path += "&name=ilike." + urllib.parse.quote("*" + safe + "*")
        if activity_cat and safe and place:
            path += "&name=ilike." + urllib.parse.quote("*" + safe + "*")
        rows = supabase_select(path + pictured + "&limit=80")
        if len(rows) < 40:
            rows = rows + supabase_select(path + "&order=photo_url.desc.nullslast&limit=80")
        if activity_cat and not rows and safe:
            rows = supabase_select(
                "outings?select="
                + SELECT
                + "&is_active=eq.true&name=ilike."
                + urllib.parse.quote("*" + safe + "*")
                + pictured
                + "&limit=80"
            )
        if country_hint:
            rows = [row for row in rows if _coords_hint_ok(row, country_hint)]
        rows = [
            row
            for row in rows
            if not LODGING_NAME.search(row.get("name") or "")
            and not is_grocery_shop(row.get("name") or "")
        ]
        outings = quality_pool(unescape_payload(rows))
    for row in outings:
        qc_outing(row)
    return {"cities": cities, "outings": outings}


def create_group(name):
    import random
    import string
    code = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    rows = supabase_request(
        "POST",
        "groups",
        {
            "share_code": code,
            "origin_label": (name or "Groupe Sinki")[:80],
            "filters": {"chat": []},
            "status": "open",
        },
    )
    return rows[0] if rows else {"share_code": code, "origin_label": name, "filters": {"chat": []}}


def get_group(code):
    code = (code or "").strip().upper()
    if len(code) < 4:
        return None
    rows = supabase_select("groups?share_code=eq." + urllib.parse.quote(code) + "&select=id,share_code,origin_label,filters,status")
    return rows[0] if rows else None


def compact_outing(outing):
    if not isinstance(outing, dict):
        return None
    oid = outing.get("id")
    name = outing.get("name")
    if not oid or not name:
        return None
    return {
        "id": oid,
        "name": name,
        "price_min": outing.get("price_min"),
        "price_max": outing.get("price_max"),
        "currency": outing.get("currency"),
        "photo_url": outing.get("photo_url"),
        "category": outing.get("category"),
    }


def group_filters(group):
    filters = group.get("filters") or {}
    return filters if isinstance(filters, dict) else {}


def save_group_filters(group, filters):
    supabase_request("PATCH", "groups?id=eq." + urllib.parse.quote(str(group["id"])), {"filters": filters})
    group["filters"] = filters
    return group


def post_group_message(code, display_name, text, outing=None):
    group = get_group(code)
    if not group:
        raise ValueError("Groupe introuvable")
    filters = group_filters(group)
    chat = list(filters.get("chat") or [])
    msg = {
        "id": str(len(chat) + 1) + "-" + str(int(__import__("time").time())),
        "name": (display_name or "Pote")[:40],
        "text": (text or "")[:2000],
        "ts": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
    }
    compact = compact_outing(outing) if outing else None
    if compact:
        msg["outing"] = compact
    chat.append(msg)
    filters["chat"] = chat[-80:]
    return save_group_filters(group, filters)


def set_group_poll(code, display_name, outings):
    group = get_group(code)
    if not group:
        raise ValueError("Groupe introuvable")
    options = []
    seen = set()
    for row in outings or []:
        compact = compact_outing(row)
        if not compact or compact["id"] in seen:
            continue
        seen.add(compact["id"])
        options.append(compact)
        if len(options) >= 3:
            break
    if len(options) < 2:
        raise ValueError("Il faut au moins 2 sorties pour voter")
    filters = group_filters(group)
    filters["poll"] = {
        "options": options,
        "ts": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
    }
    filters["votes"] = {}
    chat = list(filters.get("chat") or [])
    chat.append({
        "id": str(len(chat) + 1) + "-poll",
        "name": (display_name or "Pote")[:40],
        "text": "Votez pour une sortie : " + " · ".join(o["name"] for o in options),
        "ts": filters["poll"]["ts"],
    })
    filters["chat"] = chat[-80:]
    return save_group_filters(group, filters)


def vote_group(code, display_name, voter_id, outing_id):
    group = get_group(code)
    if not group:
        raise ValueError("Groupe introuvable")
    filters = group_filters(group)
    poll = filters.get("poll") or {}
    options = poll.get("options") or []
    allowed = {str(o.get("id")) for o in options if o.get("id")}
    outing_id = str(outing_id or "")
    if outing_id not in allowed:
        raise ValueError("Cette sortie n’est pas dans le vote")
    voter_id = (voter_id or "").strip()[:64] or (display_name or "pote").strip()[:40]
    votes = dict(filters.get("votes") or {})
    votes[voter_id] = {
        "name": (display_name or "Pote")[:40],
        "outing_id": outing_id,
    }
    filters["votes"] = votes
    return save_group_filters(group, filters)


def gotrue(method, path, body=None, bearer=None):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE"]
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "apikey": key,
        "Authorization": "Bearer " + (bearer or key),
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(base + "/auth/v1" + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def normalize_email(value):
    return (value or "").strip().lower()


def normalize_phone(value):
    raw = (value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def phone_to_mail(digits):
    return "p" + digits + "@" + PHONE_MAIL_DOMAIN


def mail_to_phone(email):
    email = normalize_email(email)
    if not email.endswith("@" + PHONE_MAIL_DOMAIN):
        return ""
    local = email.split("@", 1)[0]
    return local[1:] if local.startswith("p") else local


def auth_identity(body):
    email = normalize_email((body or {}).get("email") or "")
    if not EMAIL_RE.match(email):
        raise ValueError("Email invalide")
    return email


def public_user(user, phone=""):
    email = normalize_email(user.get("email") or "")
    meta = user.get("user_metadata") or {}
    return {
        "id": user.get("id"),
        "email": email,
        "first_name": (meta.get("first_name") or "")[:40],
        "last_name": (meta.get("last_name") or "")[:40],
        "nick": (meta.get("nick") or "")[:40],
        "plan": (meta.get("plan") or "free")[:12],
        "avatar_url": (meta.get("avatar_url") or "")[:180],
        "entitlements": meta.get("entitlements") if isinstance(meta.get("entitlements"), dict) else {},
    }


def request_is_local(host_header):
    host = (host_header or "").split(":")[0].strip().lower()
    return host in ("127.0.0.1", "localhost", "::1")


def extract_email_otp(payload):
    if not isinstance(payload, dict):
        return "", ""
    otp = str(payload.get("email_otp") or "")
    kind = str(payload.get("verification_type") or "")
    return otp, kind


def http_error_body(exc):
    raw = ""
    try:
        raw = exc.read().decode("utf-8", "ignore")
    except Exception:
        raw = str(exc)
    try:
        return json.loads(raw), raw
    except Exception:
        return {}, raw


def auth_error_code(payload):
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("error_code") or payload.get("code") or "")


def friendly_auth_error(payload, raw=""):
    code = auth_error_code(payload)
    msg = str((payload or {}).get("msg") or (payload or {}).get("error_description") or raw or "")
    blob = (code + " " + msg).lower()
    if "email_exists" in blob or "already been registered" in blob:
        return "Ce compte existe déjà. Clique Se connecter : on t’envoie un code."
    if "user_not_found" in blob or "user not found" in blob:
        return "Pas de compte avec cet email. Clique S’inscrire."
    if "rate" in blob or "over_request" in blob:
        return "Trop de codes d’un coup. Attends une minute et réessaie."
    if "invalid" in blob and "email" in blob:
        return "Email invalide."
    return "Impossible d’envoyer le code. Réessaie."


def issue_otp(email, kinds):
    last_payload, last_raw = {}, ""
    for kind in kinds:
        try:
            data = gotrue("POST", "/admin/generate_link", {"type": kind, "email": email})
            otp, _ver = extract_email_otp(data)
            if otp:
                return otp, kind, None
        except urllib.error.HTTPError as exc:
            last_payload, last_raw = http_error_body(exc)
            continue
    return "", "", last_payload or last_raw


def mail_logo_png():
    src = os.path.join(ROOT, "biche", "heureuse.png")
    if not os.path.isfile(src):
        return b""
    out_path = None
    try:
        fd, out_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        proc = subprocess.run(
            ["sips", "-z", "88", "88", src, "--out", out_path],
            capture_output=True,
            timeout=10,
        )
        if proc.returncode == 0 and os.path.getsize(out_path) > 0:
            with open(out_path, "rb") as fh:
                data = fh.read()
            if 32 < len(data) < 40000:
                return data
    except Exception:
        pass
    finally:
        if out_path:
            try:
                os.unlink(out_path)
            except OSError:
                pass
    return b""


def biche_png():
    return mail_logo_png()


def sinki_mail_html(code, with_image=True, cid=""):
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    font = "font-family:Helvetica,Arial,sans-serif;"
    logo = ""
    png = mail_logo_png() if with_image else b""
    if png:
        if cid:
            src = "cid:" + cid
        else:
            src = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        logo = (
            '<tr><td align="center" style="padding:32px 16px 10px;">'
            '<img src="' + src + '" width="44" height="44" alt="Sinki" '
            'style="display:block;border:0;width:44px;height:44px;" />'
            "</td></tr>"
        )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8" /></head>'
        '<body style="margin:0;padding:0;background:#243d2e;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#243d2e">'
        '<tr><td align="center" style="padding:0 12px 36px;">'
        '<table role="presentation" width="420" cellpadding="0" cellspacing="0">'
        + logo
        + '<tr><td align="center" style="padding:8px 28px 28px;' + font
        + 'font-size:34px;line-height:1.15;font-weight:bold;color:#fbf7f0;letter-spacing:-0.6px;">'
        "Voici ton code Sinki.</td></tr>"
        '<tr><td align="center" style="padding:0 8px 8px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#fbf7f0" '
        'style="border-radius:24px;">'
        '<tr><td align="center" style="padding:32px 24px 10px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        '<td align="center" bgcolor="#1c2a22" style="padding:6px 12px;border-radius:8px;' + font
        + 'font-size:11px;font-weight:bold;color:#fbf7f0;letter-spacing:1.4px;">SINKI</td>'
        "</tr></table></td></tr>"
        '<tr><td align="center" style="padding:6px 28px 4px;' + font
        + 'font-size:26px;line-height:1.2;font-weight:bold;color:#1c2a22;">'
        "Ton code à 6 chiffres</td></tr>"
        '<tr><td align="center" style="padding:18px 28px 6px;' + font
        + 'font-size:36px;font-weight:bold;color:#243d2e;letter-spacing:10px;">'
        + digits
        + "</td></tr>"
        '<tr><td align="center" style="padding:8px 28px 32px;' + font
        + 'font-size:14px;line-height:1.4;color:#5c6b62;">'
        "Valable 15 minutes.</td></tr>"
        "</table></td></tr>"
        '<tr><td align="center" style="padding:22px 28px 0;' + font
        + 'font-size:12px;line-height:1.4;color:#d7e4d4;">'
        "Si tu n'as rien demandé, ignore ce mail.</td></tr>"
        "</table></td></tr></table></body></html>"
    )


def sinki_mail_text(code):
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    return "Sinki\n\nVoici ton code Sinki.\n\n" + digits + "\n\nValable 15 minutes.\n"


def sinki_from_header():
    raw = (os.environ.get("MAIL_FROM") or "").strip()
    if not raw:
        raw = (os.environ.get("SMTP_USER") or "sinki@sinki.app").strip()
    if "<" in raw and ">" in raw:
        inner = raw[raw.find("<") + 1 : raw.rfind(">")].strip()
        return formataddr(("Sinki", inner or "sinki@sinki.app"))
    return formataddr(("Sinki", raw or "sinki@sinki.app"))


def build_sinki_email(to, code):
    png = mail_logo_png()
    cid = "sinki-logo" if png else ""
    msg = MIMEMultipart("related")
    msg["Subject"] = Header("Voici ton code Sinki", "utf-8")
    msg["From"] = sinki_from_header()
    msg["To"] = to
    msg["X-Mailer"] = "Sinki"
    alt = MIMEMultipart("alternative")
    msg.attach(alt)
    alt.attach(MIMEText(sinki_mail_text(code), "plain", "utf-8"))
    alt.attach(MIMEText(sinki_mail_html(code, with_image=bool(png), cid=cid), "html", "utf-8"))
    if png:
        img = MIMEImage(png, _subtype="png")
        img.add_header("Content-ID", "<" + cid + ">")
        img.add_header("Content-Disposition", "inline", filename="sinki.png")
        msg.attach(img)
    return msg


def send_macos_mail(to, code):
    if sys.platform != "darwin":
        return False
    html = sinki_mail_html(code, with_image=True)
    text = sinki_mail_text(code)
    html_path = None
    text_path = None
    js_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".html", delete=False) as fh:
            fh.write(html)
            html_path = fh.name
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as fh:
            fh.write(text)
            text_path = fh.name
        jxa = """
ObjC.import("Foundation");
function readUtf8(path) {
  var s = $.NSString.stringWithContentsOfFileEncodingError($(path), $.NSUTF8StringEncoding, null);
  return ObjC.unwrap(s);
}
function run(argv) {
  var html = readUtf8(argv[0]);
  var text = readUtf8(argv[1]);
  var to = argv[2];
  var Mail = Application("Mail");
  var msg = Mail.OutgoingMessage({
    subject: "Voici ton code Sinki",
    content: text,
    visible: false
  });
  Mail.outgoingMessages.push(msg);
  try { msg.htmlContent = html; } catch (e) {}
  msg.toRecipients.push(Mail.ToRecipient({address: to}));
  try {
    var accs = Mail.accounts();
    if (accs.length) {
      var emails = accs[0].emailAddresses();
      if (emails && emails.length) {
        var addr = emails[0];
        if (String(addr).indexOf("<") < 0) addr = "Sinki <" + addr + ">";
        msg.sender = addr;
      }
    }
  } catch (e) {}
  msg.send();
  return "ok";
}
"""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as fh:
            fh.write(jxa)
            js_path = fh.name
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", js_path, html_path, text_path, to],
            capture_output=True,
            text=True,
            timeout=40,
        )
        if proc.returncode == 0:
            return True
        return send_macos_mail_applescript(to, html, text)
    finally:
        for path in (html_path, text_path, js_path):
            if not path:
                continue
            try:
                os.unlink(path)
            except OSError:
                pass


def send_macos_mail_applescript(to, html, text=""):
    html_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".html", delete=False) as fh:
            fh.write(html)
            html_path = fh.name
        script = (
            "set htmlFile to POSIX file %s\n"
            "set htmlText to read htmlFile as «class utf8»\n"
            'tell application "Mail"\n'
            "  set msg to make new outgoing message with properties "
            '{subject:"Voici ton code Sinki", content:%s, visible:false}\n'
            "  tell msg\n"
            "    try\n"
            "      set html content to htmlText\n"
            "    end try\n"
            "    make new to recipient at end of to recipients with properties {address:%s}\n"
            "  end tell\n"
            "  send msg\n"
            "end tell\n"
        ) % (json.dumps(html_path), json.dumps(text or "Sinki"), json.dumps(to))
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=40)
        return proc.returncode == 0
    finally:
        if html_path:
            try:
                os.unlink(html_path)
            except OSError:
                pass


def send_macos_notice(to, subject, plain):
    if sys.platform != "darwin":
        return False
    script = (
        'tell application "Mail"\n'
        "  set msg to make new outgoing message with properties "
        "{subject:%s, content:%s, visible:false}\n"
        "  tell msg\n"
        "    make new to recipient at end of to recipients with properties {address:%s}\n"
        "  end tell\n"
        "  send msg\n"
        "end tell\n"
    ) % (json.dumps(subject), json.dumps(plain), json.dumps(to))
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=40)
    return proc.returncode == 0


def send_event_moderation_mail(ev, origin=""):
    to = event_store.moderator_email()
    origin = (origin or "http://127.0.0.1:5173").rstrip("/")
    approve = origin + "/api/events/review?id=" + ev["id"] + "&token=" + ev["token"] + "&action=approve"
    reject = origin + "/api/events/review?id=" + ev["id"] + "&token=" + ev["token"] + "&action=reject"
    price = ev.get("price_min")
    tarif = "Gratuit" if not price else ("%s €" % price)
    plain = (
        "Nouvel événement Sinki à valider\n\n"
        "Nom : %s\n"
        "Par : %s\n"
        "Lieu : %s\n"
        "Date : %s\n"
        "Tarif : %s\n\n"
        "%s\n\n"
        "Valider : %s\n"
        "Refuser : %s\n"
    ) % (
        ev.get("name") or "",
        ev.get("owner") or "",
        ev.get("address") or "",
        ev.get("when") or "",
        tarif,
        ev.get("description") or "",
        approve,
        reject,
    )
    try:
        return send_macos_notice(to, "Sinki — événement à valider", plain)
    except Exception:
        return False


def send_sinki_mail(to, code):
    try:
        if send_resend_mail(to, code):
            return True
    except Exception:
        pass
    try:
        if send_smtp_mail(to, code):
            return True
    except Exception:
        pass
    try:
        if send_macos_mail(to, code):
            return True
    except Exception:
        pass
    return False


def send_resend_mail(to, code):
    key = (os.environ.get("RESEND_API_KEY") or "").strip()
    if not key:
        return False
    payload = json.dumps(
        {
            "from": sinki_from_header(),
            "to": [to],
            "subject": "Voici ton code Sinki",
            "html": sinki_mail_html(code),
            "text": sinki_mail_text(code),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()
    return True


def send_smtp_mail(to, code):
    host = (os.environ.get("SMTP_HOST") or "").strip()
    user = (os.environ.get("SMTP_USER") or "").strip()
    password = (os.environ.get("SMTP_PASS") or "").strip()
    if not host or not user or not password:
        return False
    port = int(os.environ.get("SMTP_PORT") or "587")
    msg = build_sinki_email(to, code)
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.sendmail(user, [to], msg.as_string())
    return True


def send_supabase_otp_mail(email, create_user):
    gotrue("POST", "/otp", {"email": email, "create_user": bool(create_user)})
    return True


def send_login_code(body, host_header=""):
    body = body if isinstance(body, dict) else {"email": body}
    email = auth_identity(body)
    mode = str(body.get("mode") or "").strip().lower()
    exists = local_auth.email_has_account(email)
    if mode == "signup" and exists:
        raise ValueError("Ce mail a déjà un compte. Connecte-toi.")
    if mode == "login" and not exists:
        raise ValueError("Aucun compte avec ce mail. Crée-en un.")
    nick = str(body.get("nick") or "").strip()[:40]
    if nick and local_auth.pseudo_taken(nick, email):
        raise ValueError("Ce pseudo est déjà pris. Choisis-en un autre.")
    try:
        otp = local_auth.request_code(
            email,
            {
                "first_name": str(body.get("first_name") or "").strip()[:40],
                "last_name": str(body.get("last_name") or "").strip()[:40],
                "nick": nick,
            },
        )
    except ValueError as exc:
        if str(exc) == "taken":
            raise ValueError("Ce pseudo est déjà pris. Choisis-en un autre.")
        raise
    mailed = send_sinki_mail(email, otp)
    if not mailed:
        raise ValueError(
            "Impossible d’envoyer le mail Sinki. Connecte l’app Mail sur ce Mac, ou ajoute un RESEND_API_KEY gratuit dans .env."
        )
    return {"ok": True, "email_note": "Regarde tes mails et tes spams. Sinki t’a envoyé un code à 6 chiffres."}


def verify_login_code(body):
    email = auth_identity(body)
    code = str((body or {}).get("token") or "").strip()
    if not EMAIL_RE.match(email) or len(code) < 6:
        raise ValueError("Code invalide")
    profile = {
        "first_name": str((body or {}).get("first_name") or "").strip()[:40],
        "last_name": str((body or {}).get("last_name") or "").strip()[:40],
        "nick": str((body or {}).get("nick") or "").strip()[:40],
    }
    try:
        got = local_auth.verify_code(email, code, profile)
    except ValueError as exc:
        if str(exc) == "taken":
            raise ValueError("Ce pseudo est déjà pris. Choisis-en un autre.")
        raise
    if not got:
        raise ValueError("Code incorrect ou expiré")
    token, acc = got
    user = local_auth.user_from_token(token) or {
        "id": acc.get("id"),
        "email": acc.get("email") or email,
        "user_metadata": {
            "first_name": acc.get("first_name") or "",
            "last_name": acc.get("last_name") or "",
            "nick": acc.get("nick") or "",
            "avatar_url": local_auth.avatar_url(acc),
        },
    }
    return {
        "access_token": token,
        "refresh_token": "",
        "user": public_user(user),
    }


def sniff_image_ext(blob, mime=""):
    mime = (mime or "").lower()
    if blob[:3] == b"\xff\xd8\xff" or "jpeg" in mime or mime == "image/jpg":
        return "jpg"
    if blob[:8] == b"\x89PNG\r\n\x1a\n" or "png" in mime:
        return "png"
    if (blob[:4] == b"RIFF" and blob[8:12] == b"WEBP") or "webp" in mime:
        return "webp"
    return ""


def save_profile_avatar(user, body):
    if not user.get("sinki_local"):
        raise ValueError("Photo de profil dispo après connexion Sinki.")
    raw = str((body or {}).get("image") or "")
    mime = str((body or {}).get("type") or "")
    if raw.startswith("data:"):
        header, _, b64 = raw.partition(",")
        mime = header
        raw = b64
    try:
        blob = base64.b64decode(raw, validate=False)
    except Exception:
        raise ValueError("Photo invalide")
    if not blob or len(blob) > 500000:
        raise ValueError("Photo trop lourde (max 500 Ko).")
    ext = sniff_image_ext(blob, mime)
    if not ext:
        raise ValueError("Format invalide. Utilise jpg, png ou webp.")
    url = local_auth.save_avatar(user.get("email"), blob, ext)
    return {"ok": True, "avatar_url": url}


PLACE_STORY_CACHE = {}
CUISINE_FR = {
    "thai": "thaï",
    "vietnamese": "vietnamienne",
    "japanese": "japonaise",
    "korean": "coréenne",
    "chinese": "chinoise",
    "indian": "indienne",
    "italian": "italienne",
    "french": "française",
    "mexican": "mexicaine",
    "american": "américaine",
    "burger": "burgers",
    "pizza": "pizzas",
    "seafood": "fruits de mer",
    "steak": "viandes grillées",
    "barbecue": "barbecue",
    "bbq": "barbecue",
    "noodle": "nouilles",
    "noodles": "nouilles",
    "ramen": "ramen",
    "sushi": "sushi",
    "tapas": "tapas",
    "spanish": "espagnole",
    "greek": "grecque",
    "lebanese": "libanaise",
    "turkish": "turque",
    "african": "africaine",
    "ethiopian": "éthiopienne",
    "vegan": "végane",
    "vegetarian": "végétarienne",
    "coffee": "café",
    "cafe": "café",
    "dessert": "desserts",
    "ice_cream": "glaces",
    "bakery": "pâtisserie",
    "breakfast": "petit-déjeuner",
    "brunch": "brunch",
    "beer": "bières",
    "wine": "vins",
    "cocktail": "cocktails",
    "pub": "pub",
    "regional": "spécialités locales",
    "international": "cuisine internationale",
}


def _http_json(url, timeout=8):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Sinki/1.0 (https://sinki-sorties.fly.dev)", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fold_txt(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def osm_place_tags(source_id):
    raw = (source_id or "").strip().lower()
    kind, _, oid = raw.partition("/")
    if kind not in ("node", "way", "relation") or not oid.isdigit():
        return {}
    try:
        data = _http_json("https://api.openstreetmap.org/api/0.6/" + kind + "/" + oid + ".json", 8)
    except Exception:
        return {}
    els = data.get("elements") or []
    return (els[0].get("tags") or {}) if els else {}


def looks_latin(text):
    letters = [ch for ch in (text or "") if ch.isalpha()]
    if not letters:
        return True
    latin = sum(1 for ch in letters if ord(ch) < 0x250)
    return latin / len(letters) > 0.72


def wiki_langlink(title, src_lang, dest_lang):
    qs = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "langlinks",
            "titles": title,
            "lllang": dest_lang,
            "format": "json",
        }
    )
    try:
        data = _http_json("https://" + src_lang + ".wikipedia.org/w/api.php?" + qs, 8)
    except Exception:
        return ""
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        links = page.get("langlinks") or []
        if links:
            return links[0].get("*") or ""
    return ""


def wiki_summary(title, lang="fr"):
    slug = urllib.parse.quote((title or "").replace(" ", "_"))
    if not slug:
        return ""
    try:
        data = _http_json("https://" + lang + ".wikipedia.org/api/rest_v1/page/summary/" + slug, 8)
    except Exception:
        return ""
    if data.get("type") == "disambiguation":
        return ""
    extract = (data.get("extract") or "").strip()
    if len(extract) < 40:
        return ""
    return extract


def wiki_readable(title, lang="fr"):
    extract = wiki_summary(title, "fr")
    if extract and looks_latin(extract):
        return extract
    langs = []
    if lang and lang not in langs:
        langs.append(lang)
    if "en" not in langs:
        langs.append("en")
    for src in langs:
        if src == "fr":
            continue
        linked = wiki_langlink(title, src, "fr")
        if linked:
            extract = wiki_summary(linked, "fr")
            if extract:
                return extract
    extract = wiki_summary(title, "en")
    if extract and looks_latin(extract):
        return extract
    if lang and lang not in ("fr", "en"):
        extract = wiki_summary(title, lang)
        if extract and looks_latin(extract):
            return extract
    return ""


def wiki_nearby_extract(name, lat, lon):
    if lat is None or lon is None:
        return wiki_readable(name, "fr") or wiki_readable(name, "en")
    qs = urllib.parse.urlencode(
        {
            "action": "query",
            "list": "geosearch",
            "gscoord": str(lat) + "|" + str(lon),
            "gsradius": 400,
            "gslimit": 8,
            "format": "json",
        }
    )
    pages = []
    for lang in ("fr", "en"):
        try:
            data = _http_json("https://" + lang + ".wikipedia.org/w/api.php?" + qs, 8)
        except Exception:
            continue
        pages = ((data.get("query") or {}).get("geosearch") or [])
        want = _fold_txt(name)
        ranked = []
        for row in pages:
            title = row.get("title") or ""
            folded = _fold_txt(title)
            dist = row.get("dist") if row.get("dist") is not None else 999
            score = 0
            if want and (want in folded or folded in want):
                score += 20
            tokens = [w for w in want.split() if len(w) > 3]
            if tokens and all(w in folded for w in tokens[:2]):
                score += 12
            if dist <= 120:
                score += 6
            ranked.append((score, dist, title, lang))
        ranked.sort(key=lambda x: (-x[0], x[1]))
        if ranked and ranked[0][0] >= 12:
            extract = wiki_readable(ranked[0][2], ranked[0][3])
            if extract:
                return extract
        if ranked and ranked[0][1] <= 80:
            extract = wiki_readable(ranked[0][2], ranked[0][3])
            if extract:
                return extract
    return wiki_readable(name, "fr") or wiki_readable(name, "en")


def cuisine_phrase(raw):
    bits = []
    for part in re.split(r"[;,/|]", raw or ""):
        key = part.strip().lower().replace(" ", "_")
        if not key:
            continue
        bits.append(CUISINE_FR.get(key, part.strip().replace("_", " ")))
    seen = []
    for item in bits:
        if item and item not in seen:
            seen.append(item)
    if not seen:
        return ""
    if len(seen) == 1:
        return "Spécialité : " + seen[0] + "."
    return "Spécialités : " + ", ".join(seen[:-1]) + " et " + seen[-1] + "."


def osm_anecdotes(tags):
    lines = []
    cuisine = cuisine_phrase(tags.get("cuisine") or "")
    if cuisine:
        lines.append(cuisine)
    extras = []
    if (tags.get("microbrewery") or "").lower() in ("yes", "true"):
        extras.append("brasserie artisanale")
    if (tags.get("brewery") or tags.get("craft")):
        extras.append("bières sur place")
    if (tags.get("cocktails") or "cocktail" in (tags.get("cuisine") or "")):
        extras.append("cocktails")
    if (tags.get("live_music") or "").lower() in ("yes", "true"):
        extras.append("musique live")
    if (tags.get("karaoke") or "").lower() in ("yes", "true"):
        extras.append("karaoké")
    if (tags.get("outdoor_seating") or "").lower() in ("yes", "true"):
        extras.append("terrasse")
    if (tags.get("rooftop") or "").lower() in ("yes", "true") or "rooftop" in (tags.get("name") or "").lower():
        extras.append("rooftop")
    if tags.get("wheelchair") == "yes":
        extras.append("accès PMR")
    if extras:
        lines.append("Sur place : " + ", ".join(extras) + ".")
    opening = tags.get("opening_hours")
    if opening:
        pretty = opening.replace("Mo-Su", "tous les jours").replace("Mo-Fr", "en semaine")
        pretty = pretty.replace("Sa-Su", "le week-end")
        lines.append("Horaires : " + pretty + ".")
    desc = (tags.get("description:fr") or tags.get("description:en") or tags.get("description") or "").strip()
    if desc:
        lines.append(desc)
    return lines


def place_story(params):
    name = unescape_text((params.get("name") or [""])[0]).strip()
    source_id = (params.get("source_id") or [""])[0].strip()
    category = unescape_text((params.get("category") or [""])[0]).strip()
    try:
        lat = float((params.get("lat") or [""])[0])
        lon = float((params.get("lon") or [""])[0])
    except (TypeError, ValueError):
        lat = lon = None
    cache_key = source_id or (name + "|" + str(round(lat or 0, 4)) + "|" + str(round(lon or 0, 4)))
    if cache_key in PLACE_STORY_CACHE:
        return PLACE_STORY_CACHE[cache_key]
    tags = osm_place_tags(source_id)
    wiki_tag = tags.get("wikipedia:fr") or tags.get("wikipedia") or ""
    extract = ""
    if wiki_tag:
        lang, title = "fr", wiki_tag
        if ":" in wiki_tag and len(wiki_tag.split(":", 1)[0]) <= 3:
            lang, title = wiki_tag.split(":", 1)
        extract = wiki_readable(title, lang)
    if not extract:
        extract = wiki_nearby_extract(name, lat, lon)
    if not extract:
        extract = wiki_readable(name, "fr") or wiki_readable(name, "en")
    bits = []
    if extract:
        bits.append(extract)
    bits.extend(osm_anecdotes(tags))
    story = " ".join(bits).strip()
    payload = {"story": story, "has_wiki": bool(extract)}
    if tags:
        flags = {"need_tickets": None, "need_id": None, "name": name, "category": category, "description": ""}
        bring_from_osm(tags, flags)
        if flags.get("need_tickets") is not None:
            payload["need_tickets"] = flags["need_tickets"]
        if flags.get("need_id"):
            payload["need_id"] = True
        if flags.get("price_unknown") is False and flags.get("price_min") == 0 and category != CAT_RESTO:
            payload["price_min"] = 0
            payload["price_max"] = 0
            payload["price_unknown"] = False
        if category == CAT_RESTO or flags.get("price_min"):
            span = resto_menu_span(tags)
            if span:
                payload["price_min"], payload["price_max"] = span
                payload["price_unknown"] = False
    PLACE_STORY_CACHE[cache_key] = payload
    if len(PLACE_STORY_CACHE) > 400:
        PLACE_STORY_CACHE.pop(next(iter(PLACE_STORY_CACHE)))
    return payload


def user_from_bearer(header):
    raw = (header or "").strip()
    if not raw.lower().startswith("bearer "):
        return None
    token = raw.split(" ", 1)[1].strip()
    if not token:
        return None
    local = local_auth.user_from_token(token)
    if local:
        return local
    try:
        data = gotrue("GET", "/user", bearer=token)
    except urllib.error.HTTPError:
        return None
    if not data.get("id"):
        return None
    return data


def fetch_outings_by_ids(ids):
    clean = []
    seen = set()
    for item in ids:
        oid = str(item or "")
        if not UUID_RE.match(oid) or oid in seen:
            continue
        seen.add(oid)
        clean.append(oid)
    if not clean:
        return []
    found = {}
    for i in range(0, len(clean), 40):
        chunk = clean[i : i + 40]
        query = "outings?select=" + SELECT + "&id=in.(" + ",".join(chunk) + ")"
        for row in supabase_select(query):
            found[row["id"]] = row
    return unescape_payload([qc_outing(found[oid]) for oid in clean if oid in found])


def set_user_favorites(user_id, outing_ids):
    wanted = []
    seen = set()
    for oid in outing_ids or []:
        oid = str(oid or "")
        if UUID_RE.match(oid) and oid not in seen:
            seen.add(oid)
            wanted.append(oid)
    existing = {row["id"] for row in fetch_outings_by_ids(wanted)}
    wanted = [oid for oid in wanted if oid in existing]
    seen = set(wanted)
    current = supabase_select("favorites?user_id=eq." + user_id + "&select=id,outing_id")
    have = {row["outing_id"]: row["id"] for row in current}
    for oid, row_id in have.items():
        if oid not in seen:
            supabase_request("DELETE", "favorites?id=eq." + urllib.parse.quote(str(row_id)))
    for oid in wanted:
        if oid not in have:
            supabase_request("POST", "favorites", {"user_id": user_id, "outing_id": oid})
    return wanted


def attach_user_group(user_id, nick, group_code):
    code = (group_code or "").strip().upper()
    members = supabase_select(
        "group_members?member_token=eq." + urllib.parse.quote(user_id) + "&select=id,group_id"
    )
    if not code:
        for row in members:
            supabase_request("DELETE", "group_members?id=eq." + urllib.parse.quote(str(row["id"])))
        return None
    group = get_group(code)
    if not group:
        return None
    payload = {"group_id": group["id"], "display_name": (nick or "Pote")[:40], "member_token": user_id}
    if members:
        supabase_request("PATCH", "group_members?id=eq." + urllib.parse.quote(str(members[0]["id"])), payload)
    else:
        supabase_request("POST", "group_members", payload)
    return group


def save_user_meta(bearer, meta):
    gotrue("PUT", "/user", {"data": meta}, bearer=bearer)


def compact_plans(plans):
    out = []
    for item in plans or []:
        if not isinstance(item, dict) or not UUID_RE.match(str(item.get("id") or "")):
            continue
        snap = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else item
        out.append(
            {
                "id": item["id"],
                "planned_for": item.get("planned_for"),
                "snapshot": {
                    "id": snap.get("id") or item["id"],
                    "name": (snap.get("name") or "")[:200],
                    "category": snap.get("category"),
                    "photo_url": snap.get("photo_url"),
                    "price_min": snap.get("price_min"),
                    "price_max": snap.get("price_max"),
                    "address": snap.get("address"),
                    "latitude": snap.get("latitude"),
                    "longitude": snap.get("longitude"),
                    "website_url": snap.get("website_url"),
                    "source_url": snap.get("source_url"),
                    "kind": snap.get("kind"),
                },
            }
        )
        if len(out) >= 40:
            break
    return out


def hydrate_plans(meta_plans):
    ids = [p.get("id") for p in (meta_plans or [])]
    live = {row["id"]: row for row in fetch_outings_by_ids(ids)}
    rows = []
    for item in meta_plans or []:
        oid = item.get("id")
        row = dict(live.get(oid) or item.get("snapshot") or {})
        if not row.get("id"):
            continue
        row["planned_for"] = item.get("planned_for")
        rows.append(row)
    return unescape_payload(rows)


def account_payload(user, bearer=None):
    uid = user["id"]
    meta = user.get("user_metadata") or {}
    if user.get("sinki_local"):
        favs = fetch_outings_by_ids(meta.get("fav_ids") or [])
    else:
        fav_rows = supabase_select("favorites?user_id=eq." + uid + "&select=outing_id,created_at&order=created_at.desc")
        favs = fetch_outings_by_ids([row["outing_id"] for row in fav_rows])
    members = supabase_select(
        "group_members?member_token=eq." + urllib.parse.quote(uid) + "&select=group_id,display_name"
    )
    group = None
    nick = (meta.get("nick") or "")[:40]
    group_code = (meta.get("group_code") or "").strip().upper()
    if members:
        rows = supabase_select(
            "groups?id=eq." + urllib.parse.quote(str(members[0]["group_id"])) + "&select=id,share_code,origin_label,filters,status"
        )
        group = rows[0] if rows else None
        if group:
            group_code = group.get("share_code") or group_code
        if not nick:
            nick = (members[0].get("display_name") or "")[:40]
    elif group_code:
        group = get_group(group_code)
    return {
        "user": public_user(user),
        "favs": favs,
        "plans": hydrate_plans(meta.get("plans") or []),
        "group_code": group_code,
        "nick": nick,
        "group": group,
    }


def sync_account(user, bearer, body):
    uid = user["id"]
    meta = user.get("user_metadata") or {}
    nick = (body.get("nick") or meta.get("nick") or "")[:40]
    first_name = str(body.get("first_name") or meta.get("first_name") or "").strip()[:40]
    last_name = str(body.get("last_name") or meta.get("last_name") or "").strip()[:40]
    group_code = (body.get("group_code") or "").strip().upper()
    fav_ids = body.get("fav_ids") or []
    plans = compact_plans(body.get("plans") or [])
    group = None
    try:
        group = attach_user_group(uid, first_name or nick, group_code)
    except Exception:
        group = None
    if group:
        group_code = group.get("share_code") or group_code
    if user.get("sinki_local"):
        wanted = []
        seen = set()
        for oid in fav_ids:
            oid = str(oid or "")
            if UUID_RE.match(oid) and oid not in seen:
                seen.add(oid)
                wanted.append(oid)
        try:
            local_auth.save_account(
                user.get("email"),
                {
                    "nick": nick,
                    "first_name": first_name,
                    "last_name": last_name,
                    "group_code": group_code,
                    "plans": plans,
                    "fav_ids": wanted,
                },
            )
        except ValueError as exc:
            if str(exc) == "taken":
                raise ValueError("Ce pseudo est déjà pris. Choisis-en un autre.")
            raise
        fresh = local_auth.user_from_token(bearer)
        return account_payload(fresh or user, bearer)
    set_user_favorites(uid, fav_ids)
    save_user_meta(bearer, {
        "nick": nick,
        "first_name": first_name,
        "last_name": last_name,
        "group_code": group_code,
        "plans": plans,
    })
    fresh = gotrue("GET", "/user", bearer=bearer)
    return account_payload(fresh, bearer)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        print("[%s] " % self.log_date_time_string() + (fmt % args), flush=True)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api(parsed)
        hit = AVATAR_FILE_RE.match(parsed.path)
        if hit:
            blob, mime = local_auth.read_avatar(hit.group(1), hit.group(2).lower())
            if not blob:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "private, max-age=60")
            self.end_headers()
            self.wfile.write(blob)
            return
        photo = EVENT_PHOTO_RE.match(parsed.path)
        if photo:
            blob, mime = event_store.read_photo(photo.group(1), photo.group(2).lower())
            if not blob:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "private, max-age=120")
            self.end_headers()
            self.wfile.write(blob)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api(parsed, post=True)
        self.send_error(404)

    def json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def send_json(self, payload, status=200, cache="no-store"):
        data = json.dumps(unescape_payload(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("Permissions-Policy", "geolocation=(self)")
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, html, status=200):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def request_origin(self):
        proto = (self.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip()
        host = self.headers.get("Host") or ("127.0.0.1:%s" % PORT)
        return proto + "://" + host

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Permissions-Policy", "geolocation=(self)")
            if self.path.startswith("/index.html") or self.path in ("/", "/app.js", "/i18n.js", "/styles.css") or "/app.js?" in self.path or "/i18n.js?" in self.path or "/styles.css?" in self.path:
                self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def handle_api(self, parsed, post=False):
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            path = parsed.path.rstrip("/")
            if path == "/api/cities/near":
                payload = nearest_city_row((qs.get("lat") or [""])[0], (qs.get("lon") or [""])[0]) or {}
            elif path == "/api/cities":
                payload = search_cities((qs.get("q") or [""])[0], (qs.get("country") or [""])[0])
                self.send_json(payload, 200, "public, max-age=120")
                return
            elif path == "/api/countries":
                payload = search_countries((qs.get("q") or [""])[0])
            elif path == "/api/geo":
                ip = (self.headers.get("CF-Connecting-IP") or self.headers.get("X-Real-IP") or "").strip()
                if not ip:
                    forwarded = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
                    ip = forwarded or (self.client_address[0] if self.client_address else "")
                payload = lookup_geo(ip)
            elif path == "/api/outings":
                try:
                    payload = fetch_outings(qs)
                except urllib.error.HTTPError:
                    payload = []
            elif path == "/api/search":
                payload = search_catalog((qs.get("q") or [""])[0], (qs.get("country") or [""])[0])
            elif path == "/api/weather":
                lat = (qs.get("lat") or [""])[0]
                lon = (qs.get("lon") or [""])[0]
                url = (
                    "https://api.open-meteo.com/v1/forecast?latitude="
                    + urllib.parse.quote(lat)
                    + "&longitude="
                    + urllib.parse.quote(lon)
                    + "&current=temperature_2m,weather_code"
                )
                with urllib.request.urlopen(url, timeout=20) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            elif path == "/api/groups" and post:
                body = self.json_body()
                payload = create_group(body.get("name") or "Groupe Sinki")
            elif path == "/api/groups":
                payload = get_group((qs.get("code") or [""])[0]) or {"error": "introuvable"}
            elif path == "/api/place-story":
                payload = place_story(qs)
            elif path == "/api/health":
                payload = {"ok": True, "app": "sinki", "v": 97}
            elif path == "/api/billing/catalog":
                payload = {"ok": True, "catalog": __import__("catalog_data").CATALOG}
            elif path == "/api/billing/entitlements":
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                payload = {"ok": True, "entitlements": (user.get("user_metadata") or {}).get("entitlements") or {}}
            elif path == "/api/billing/confirm" and post:
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                why = sinki_billing.confirm_rejected(self.json_body())
                self.send_json({
                    "ok": False,
                    "verified": False,
                    "error": why,
                    "entitlements": (user.get("user_metadata") or {}).get("entitlements") or {},
                }, 402)
                return
            elif path == "/api/billing/restore" and post:
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                payload = {
                    "ok": True,
                    "entitlements": (user.get("user_metadata") or {}).get("entitlements") or {},
                }
            elif path == "/api/events/review":
                qs_id = (qs.get("id") or [""])[0]
                token = (qs.get("token") or [""])[0]
                action = (qs.get("action") or [""])[0]
                if post:
                    user = user_from_bearer(self.headers.get("Authorization"))
                    if not user:
                        self.send_json({"error": "non connecté"}, 401)
                        return
                    local = request_is_local(self.headers.get("Host"))
                    if not event_store.is_moderator(user.get("email"), local):
                        self.send_json({"error": "interdit"}, 403)
                        return
                    body = self.json_body()
                    payload = event_store.review_event(body.get("id") or qs_id, body.get("action") or action)
                else:
                    row = event_store.review_event(qs_id, action, token)
                    ok = row.get("status") == "approved"
                    title = "Événement validé" if ok else "Événement refusé"
                    note = "Il est boosté 24 h dans Explorer." if ok else "Il n’apparaîtra pas dans l’app."
                    self.send_html(
                        "<!doctype html><html lang=\"fr\"><meta charset=\"utf-8\"><title>Sinki</title>"
                        "<body style=\"font-family:Inter,sans-serif;padding:32px;color:#1c2a22\">"
                        "<h1>Sinki</h1><p><strong>%s</strong></p><p>%s</p></body></html>" % (title, note)
                    )
                    return
            elif path == "/api/events/like" and post:
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                body = self.json_body()
                payload = event_store.toggle_like(body.get("id"), user.get("email"))
            elif path == "/api/events/comment" and post:
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                body = self.json_body()
                nick = (user.get("user_metadata") or {}).get("nick") or user.get("email") or "Sinki"
                payload = event_store.add_comment(body.get("id"), user.get("email"), nick, body.get("text"))
            elif path == "/api/events" and post:
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                row = event_store.create_event(user.get("email"), self.json_body())
                send_event_moderation_mail(row, self.request_origin())
                payload = event_store.public_row(row)
            elif path == "/api/events":
                want_mine = (qs.get("mine") or [""])[0] in ("1", "true")
                want_pending = (qs.get("pending") or [""])[0] in ("1", "true")
                if want_mine or want_pending:
                    user = user_from_bearer(self.headers.get("Authorization"))
                    if not user:
                        self.send_json({"error": "non connecté"}, 401)
                        return
                    if want_pending:
                        local = request_is_local(self.headers.get("Host"))
                        if not event_store.is_moderator(user.get("email"), local):
                            self.send_json({"error": "interdit"}, 403)
                            return
                        payload = {"events": event_store.list_pending(user.get("email"))}
                    else:
                        payload = {"events": event_store.list_mine(user.get("email"))}
                else:
                    viewer = ""
                    user = user_from_bearer(self.headers.get("Authorization"))
                    if user:
                        viewer = user.get("email") or ""
                    payload = {"events": event_store.list_public(viewer)}
            elif path == "/api/auth/pseudo":
                q = (qs.get("q") or [""])[0]
                email = (qs.get("email") or [""])[0]
                payload = {"taken": local_auth.pseudo_taken(q, email)}
            elif path == "/api/auth/send" and post:
                payload = send_login_code(self.json_body(), self.headers.get("Host"))
            elif path == "/api/auth/verify" and post:
                body = self.json_body()
                payload = verify_login_code(body)
            elif path == "/api/me":
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                payload = account_payload(user)
            elif path == "/api/me/sync" and post:
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                token = self.headers.get("Authorization", "").split(" ", 1)[1].strip()
                payload = sync_account(user, token, self.json_body())
            elif path == "/api/me/avatar" and post:
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                payload = save_profile_avatar(user, self.json_body())
            elif path == "/api/me/delete" and post:
                user = user_from_bearer(self.headers.get("Authorization"))
                if not user:
                    self.send_json({"error": "non connecté"}, 401)
                    return
                email = user.get("email") or ""
                uid = user.get("id") or ""
                try:
                    event_store.purge_user(email)
                except Exception:
                    pass
                local_auth.delete_account(email)
                try:
                    members = supabase_select(
                        "group_members?member_token=eq." + urllib.parse.quote(str(uid)) + "&select=id"
                    )
                    for row in members:
                        supabase_request("DELETE", "group_members?id=eq." + urllib.parse.quote(str(row["id"])))
                except Exception:
                    pass
                try:
                    favs = supabase_select("favorites?user_id=eq." + urllib.parse.quote(str(uid)) + "&select=id")
                    for row in favs:
                        supabase_request("DELETE", "favorites?id=eq." + urllib.parse.quote(str(row["id"])))
                except Exception:
                    pass
                payload = {"ok": True}
            elif path == "/api/groups/message" and post:
                body = self.json_body()
                payload = post_group_message(
                    body.get("code"),
                    body.get("name"),
                    body.get("text"),
                    body.get("outing"),
                )
            elif path == "/api/groups/poll" and post:
                body = self.json_body()
                payload = set_group_poll(body.get("code"), body.get("name"), body.get("outings"))
            elif path == "/api/groups/vote" and post:
                body = self.json_body()
                payload = vote_group(
                    body.get("code"),
                    body.get("name"),
                    body.get("voter_id"),
                    body.get("outing_id"),
                )
            else:
                self.send_error(404)
                return
            status = 404 if isinstance(payload, dict) and payload.get("error") == "introuvable" else 200
            self.send_json(payload, status)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:400]
            if "57014" in detail or "timeout" in detail.lower():
                self.send_json({"error": "La recherche a pris trop de temps. Réessaie."}, 503)
                return
            self.send_json({"error": "Erreur serveur"}, exc.code if exc.code < 500 else 502)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)


def main():
    load_env()
    scrub_env()
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE"):
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis dans .env")
    os.chdir(ROOT)
    def warm():
        try:
            featured_city_rows("FR")
        except Exception:
            pass
    threading.Thread(target=warm, daemon=True).start()
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, PORT), Handler)
    print("Sinki → http://%s:%s" % (host, PORT), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
