# -*- coding: utf-8 -*-
"""Règle Sinki : une sortie n'est importée que si photo + prix (0 € inclus si source gratuite)."""

import re

HOTEL_MARKERS = (
    "hotel",
    "hostel",
    "motel",
    "lodging",
    "accommodation",
    "camping",
    "campground",
    "campsite",
    "apartment",
    "bedandbreakfast",
    "bedandbreakfast",
    "gite",
    "gîte",
    "holidayrental",
    "holidayvillage",
    "selfcatering",
    "residence",
    "timeshare",
    "guestroom",
    "collectiveaccommodation",
    "chalet",
    "cottage",
    "homestay",
)

REQUIRED_PHOTO_PREFIXES = ("http://", "https://")

GROCERY_TAGS = {
    "supermarket",
    "hypermarket",
    "convenience",
    "greengrocer",
    "butcher",
    "seafood",
    "cheese",
    "dairy",
    "wholesale",
    "frozen_food",
}

GROCERY_NAME = re.compile(
    r"\b("
    r"carrefour|e\.?\s?leclerc|leclerc|auchan|lidl|aldi|intermarch[eé]|"
    r"super\s?u|hyper\s?u|u\s?express|franprix|monoprix|"
    r"g[eé]ant(\s+casino)?|cora|match|leader\s?price|simply(\s+market)?|"
    r"colruyt|delhaize|albert\s?heijn|"
    r"rewe|edeka|penny|kaufland|marktkauf|"
    r"mercadona|alcampo|eroski|"
    r"esselunga|conad|eurospin|"
    r"continente|pingo\s?doce|minipre[cç]o|"
    r"tesco|asda|sainsbury|morrisons|waitrose|"
    r"biedronka|zabka|"
    r"billa|hofer|migros|denner|"
    r"willys|hemk[oö]p|rema\s?1000|"
    r"prisma|s-market|k-market|alepa|citymarket|"
    r"mega\s?image|sklavenitis|konzum|plodine|"
    r"hypermarche|hypermarch[eé]|supermarch[eé]|sup[eé]rette|"
    r"grand\s+frais|biocoop|naturalia|picard|\bspar\b|netto|"
    r"carrefour\s+drive|leclerc\s+drive|auchan\s+drive"
    r")\b"
    r"|^(le drive|garage)$",
    re.I,
)


def is_grocery_shop(name, shop=None):
    """Courses / hypermarchés : pas une sortie shopping."""
    tag = (shop or "").strip().lower()
    if tag in GROCERY_TAGS:
        return True
    return bool(GROCERY_NAME.search(name or ""))


def is_hotel_or_lodging(types):
    blob = " ".join(types).lower()
    return any(m in blob for m in HOTEL_MARKERS)


def has_usable_photo(url):
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    return u.startswith(REQUIRED_PHOTO_PREFIXES) and not u.lower().endswith(".pdf")


MENU_PRICE_KEY = re.compile(r"^(charge|menu|lunch|price)(:|$)")
MENU_SKIP_KEY = re.compile(r"url|website|wikidata|wikipedia|image")
MENU_NUM = re.compile(r"(\d+(?:[.,]\d+)?)")
MENU_RANGE = re.compile(
    r"(\d{1,3}(?:[.,]\d+)?)\s*(?:€|eur|euros)?\s*(?:à|-|–|—|/)\s*(\d{1,3}(?:[.,]\d+)?)\s*(?:€|eur|euros)?",
    re.I,
)


def _menu_num(raw):
    try:
        n = float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if 1 <= n <= 250:
        return n
    return None


def menu_prices_from_tags(tags):
    """Prix de plat / menu OSM : le moins cher et le plus cher, jamais 0."""
    nums = []
    for key, val in (tags or {}).items():
        k = str(key or "").lower()
        if not MENU_PRICE_KEY.match(k) or MENU_SKIP_KEY.search(k):
            continue
        text = str(val or "").strip()
        if re.fullmatch(r"[€$£]+", text.replace(" ", "")):
            continue
        for raw in MENU_NUM.findall(text):
            n = _menu_num(raw)
            if n is not None:
                nums.append(n)
    return nums


def menu_prices_from_text(text):
    nums = []
    blob = text or ""
    if "€" not in blob and not re.search(r"\b(eur|euro|menu|formule|plat)\b", blob, re.I):
        return nums
    for a, b in MENU_RANGE.findall(blob):
        lo, hi = _menu_num(a), _menu_num(b)
        if lo is not None:
            nums.append(lo)
        if hi is not None:
            nums.append(hi)
    return nums


def resto_menu_span(tags=None, description=""):
    nums = menu_prices_from_tags(tags) + menu_prices_from_text(description)
    if not nums:
        return None
    return min(nums), max(nums)


def has_usable_price(price_min, price_max):
    if price_min is None and price_max is None:
        return False
    try:
        if price_min is not None and float(price_min) < 0:
            return False
        if price_max is not None and float(price_max) < 0:
            return False
    except (TypeError, ValueError):
        return False
    return True


def is_priced_place(row):
    """Prix + GPS + nom. Photo optionnelle (dernier recours pour communes vides)."""
    return (
        bool(row.get("name"))
        and row.get("latitude") is not None
        and row.get("longitude") is not None
        and has_usable_price(row.get("price_min"), row.get("price_max"))
        and not is_hotel_or_lodging(row.get("types") or [])
    )


def is_complete(row):
    return is_priced_place(row) and has_usable_photo(row.get("photo_url"))
