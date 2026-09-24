# -*- coding: utf-8 -*-
"""Photos Wikimedia Commons / Wikidata, licences libres uniquement."""

import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Sinki/1.0 (https://sinki-sorties.fly.dev; hike photos)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
SWISS_Q = "Q39"
FRANCE_Q = "Q142"
ALLOWED_COUNTRY_Q = {SWISS_Q, FRANCE_Q}
_HTTP_LOCK = threading.Lock()
_CACHE_LOCK = threading.RLock()


def _bucket(cache, name):
    with _CACHE_LOCK:
        return cache.setdefault(name, {})

FREE_LICENSES = (
    "cc0",
    "cc-zero",
    "cc-by",
    "cc-by-sa",
    "pd",
    "pdm",
    "public domain",
    "gfdl",
)
SKIP_TITLE = (
    "map of",
    "location map",
    "karte ",
    "karte_",
    "logo",
    "icon",
    "coat of arms",
    "blason",
    "flag of",
    "diagram",
    "panorama sketch",
    "contour",
)
SKIP_EXT = (".svg", ".pdf", ".djvu", ".ogg", ".ogv", ".webm", ".stl")
STOPWORDS = {
    "der",
    "die",
    "das",
    "le",
    "la",
    "les",
    "the",
    "de",
    "du",
    "des",
    "und",
    "and",
    "mont",
    "monte",
    "mount",
    "peak",
    "pizzo",
    "berg",
    "horn",
    "alp",
    "alps",
    "suisse",
    "schweiz",
    "switzerland",
    "rando",
    "randonnee",
    "randonnée",
    "hike",
    "hiking",
    "sentier",
    "trail",
    "first",
    "klein",
    "kleine",
    "gross",
    "grosse",
    "ober",
    "unter",
    "gipfel",
    "viewpoint",
    "panorama",
    "signal",
    "kreuz",
    "stock",
}


def license_is_free(name):
    blob = (name or "").lower()
    if "noncommercial" in blob or "nc-" in blob or " nd" in blob or "cc-by-nd" in blob:
        return False
    return any(token in blob for token in FREE_LICENSES)


def _tokens(text):
    parts = re.findall(r"[a-zà-ÿ0-9]+", (text or "").lower())
    return [p for p in parts if len(p) >= 4 and p not in STOPWORDS]


def _title_ok(title):
    blob = (title or "").lower()
    if any(blob.endswith(ext) for ext in SKIP_EXT):
        return False
    return not any(bad in blob for bad in SKIP_TITLE)


def _name_matches(name, title, all_tokens=False):
    toks = _tokens(name)
    if not toks:
        return False
    blob = (title or "").lower().replace("_", " ")
    if not all_tokens:
        return any(t in blob for t in toks)
    folded = " ".join(toks)
    if folded in blob:
        return True
    if len(toks) == 1:
        return toks[0] in blob
    shopish = any(w in blob for w in ("shop", "store", "magasin", "winkel", "filiale", "boutique"))
    if not shopish:
        return False
    toks = sorted(toks, key=len, reverse=True)
    return all(t in blob for t in toks[:2])


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(a)))


def _get(url, cache_http):
    with _HTTP_LOCK:
        if url in cache_http:
            return cache_http[url]
    data = None
    last_err = None
    for attempt in range(4):
        time.sleep(0.12 * (attempt + 1))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            last_err = None
            break
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            data = None
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_err = exc
            continue
    if last_err is not None and data is None:
        return None
    with _HTTP_LOCK:
        cache_http[url] = data
        return cache_http[url]


def _api(base, params, cache_http):
    qs = urllib.parse.urlencode(params)
    return _get(base + "?" + qs, cache_http)


def _cover_url(filename):
    name = filename[5:] if filename.startswith("File:") else filename
    return "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(name) + "?width=1280"


def _info_from_pages(pages):
    for page in (pages or {}).values():
        if page.get("missing") or page.get("invalid"):
            continue
        title = page.get("title") or ""
        if not _title_ok(title):
            continue
        iis = page.get("imageinfo") or []
        if not iis:
            continue
        info = iis[0]
        meta = info.get("extmetadata") or {}
        license_name = (meta.get("LicenseShortName") or {}).get("value") or ""
        license_id = (meta.get("License") or {}).get("value") or ""
        if not license_is_free(license_name + " " + license_id):
            continue
        filename = title if title.startswith("File:") else "File:" + title
        return {"url": _cover_url(filename), "license": license_name or "commons", "title": title}
    return None


def file_if_free(filename, cache):
    if not filename:
        return None
    filename = urllib.parse.unquote(filename.replace("_", " ")).strip()
    if filename.startswith("Category:"):
        return None
    key = filename.lower()
    files = _bucket(cache, "file")
    if key in files:
        return files[key]
    title = filename if filename.startswith("File:") else "File:" + filename
    data = _api(
        COMMONS_API,
        {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "extmetadata|url",
            "format": "json",
        },
        _bucket(cache, "http"),
    )
    pages = (data or {}).get("query", {}).get("pages")
    found = _info_from_pages(pages)
    files[key] = found
    return found


def category_photo(category, name, cache, all_tokens=False):
    if not category:
        return None
    title = category if category.startswith("Category:") else "Category:" + category
    cats = _bucket(cache, "cat")
    ckey = title + ("|all" if all_tokens else "")
    if ckey in cats:
        return cats[ckey]
    data = _api(
        COMMONS_API,
        {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": title,
            "gcmtype": "file",
            "gcmlimit": "12",
            "prop": "imageinfo",
            "iiprop": "extmetadata|url",
            "format": "json",
        },
        _bucket(cache, "http"),
    )
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    ranked = []
    for page in pages.values():
        hit = _info_from_pages({page.get("pageid", 0): page})
        if not hit:
            continue
        if all_tokens and not _name_matches(name, hit["title"], all_tokens=True):
            continue
        ranked.append((0 if _name_matches(name, hit["title"], all_tokens=all_tokens) else 1, hit))
    ranked.sort(key=lambda x: x[0])
    found = ranked[0][1] if ranked else None
    cats[ckey] = found
    return found


def _claim_filename(entity, prop):
    claims = ((entity or {}).get("claims") or {}).get(prop) or []
    for claim in claims:
        snak = (claim.get("mainsnak") or {})
        val = ((snak.get("datavalue") or {}).get("value"))
        if isinstance(val, str) and val:
            return val
    return None


def _claim_coords(entity):
    claims = ((entity or {}).get("claims") or {}).get("P625") or []
    for claim in claims:
        val = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        if "latitude" in val and "longitude" in val:
            return float(val["latitude"]), float(val["longitude"])
    return None


def _claim_country_ok(entity):
    claims = ((entity or {}).get("claims") or {}).get("P17") or []
    if not claims:
        return True
    for claim in claims:
        val = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        if val.get("id") in ALLOWED_COUNTRY_Q:
            return True
    return False


def wikidata_entity_photo(qid, lat, lon, cache, require_nearby=False, any_country=False):
    if not qid:
        return None
    wd = _bucket(cache, "wd")
    key = qid + ("|near" if require_nearby else "") + ("|any" if any_country else "")
    if key in wd:
        return wd[key]
    data = _api(
        WIKIDATA_API,
        {"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"},
        _bucket(cache, "http"),
    )
    entity = ((data or {}).get("entities") or {}).get(qid)
    if not entity or entity.get("missing"):
        wd[key] = None
        return None
    coords = _claim_coords(entity)
    if not any_country and not _claim_country_ok(entity):
        near = (
            coords
            and lat is not None
            and lon is not None
            and _haversine_km(lat, lon, coords[0], coords[1]) <= 30
        )
        if not near:
            wd[key] = None
            return None
    if require_nearby:
        if not coords or lat is None or lon is None:
            wd[key] = None
            return None
        if _haversine_km(lat, lon, coords[0], coords[1]) > 25:
            wd[key] = None
            return None
    elif coords and lat is not None and lon is not None and not any_country:
        if _haversine_km(lat, lon, coords[0], coords[1]) > 30:
            wd[key] = None
            return None
    filename = _claim_filename(entity, "P18")
    found = file_if_free(filename, cache) if filename else None
    wd[key] = found
    return found


def wikidata_search_photo(name, lat, lon, cache, chains=False):
    if not name or len(name.strip()) < 3 or not _tokens(name):
        return None
    key = name.strip().lower() + ("|chain" if chains else "")
    searches = _bucket(cache, "wdsearch")
    if key in searches:
        qids = searches[key]
    else:
        data = _api(
            WIKIDATA_API,
            {
                "action": "wbsearchentities",
                "search": name.strip(),
                "language": "fr",
                "uselang": "fr",
                "type": "item",
                "limit": "6",
                "format": "json",
            },
            _bucket(cache, "http"),
        )
        qids = [hit.get("id") for hit in (data or {}).get("search") or [] if hit.get("id")]
        searches[key] = qids
    for qid in qids:
        found = wikidata_entity_photo(
            qid,
            lat,
            lon,
            cache,
            require_nearby=not chains,
            any_country=chains,
        )
        if found:
            return found
    return None


def wikipedia_photo(wiki, lat, lon, cache):
    if not wiki:
        return None
    wikis = _bucket(cache, "wiki")
    if wiki in wikis:
        return wikis[wiki]
    lang, _, title = wiki.partition(":")
    if not title:
        lang, title = "de", wiki
    if lang not in ("de", "fr", "en", "it", "rm", "nl", "es", "pt", "el", "hr"):
        lang, title = "en", wiki
    data = _api(
        "https://%s.wikipedia.org/w/api.php" % lang,
        {
            "action": "query",
            "titles": title,
            "prop": "pageimages|pageprops",
            "piprop": "original|name",
            "ppprop": "wikibase_item",
            "format": "json",
        },
        _bucket(cache, "http"),
    )
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    found = None
    for page in pages.values():
        qid = (page.get("pageprops") or {}).get("wikibase_item")
        if qid:
            found = wikidata_entity_photo(qid, lat, lon, cache)
            if found:
                break
        original = page.get("original") or {}
        source = original.get("source") or ""
        pageimage = page.get("pageimage")
        if pageimage:
            found = file_if_free(pageimage, cache)
            if found:
                break
        if source and "commons" in source:
            filename = urllib.parse.unquote(source.rsplit("/", 1)[-1].split("?", 1)[0])
            found = file_if_free(filename, cache)
            if found:
                break
    wikis[wiki] = found
    return found


def commons_search_photo(name, cache, mode="place"):
    if not name or len(name.strip()) < 3 or not _tokens(name):
        return None
    key = name.strip().lower() + "|" + mode
    searches = _bucket(cache, "search")
    if key in searches:
        return searches[key]
    queries = []
    if mode == "shop":
        queries = [
            '"%s" (shop OR store OR magasin OR winkel OR filiale)' % name.strip(),
            name.strip(),
        ]
    elif mode == "night":
        queries = [
            '"%s" (nightclub OR discotheque OR disco OR club OR concert OR venue OR bar)'
            % name.strip(),
            name.strip(),
        ]
    elif mode == "int":
        queries = [
            '"%s" (museum OR cinema OR restaurant OR park OR church OR castle OR gallery OR tower OR nightclub OR concert OR bar OR club OR venue)'
            % name.strip(),
            name.strip(),
        ]
    else:
        queries = [
            '"%s" (France OR Suisse OR Switzerland OR Alpes OR Alps OR Pyrénées OR Pyrenees OR Corse OR Corsica)'
            % name.strip(),
            '"%s" (shop OR store OR magasin)' % name.strip(),
            name.strip(),
        ]
    found = None
    for query in queries:
        data = _api(
            COMMONS_API,
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": "6",
                "gsrlimit": "12",
                "prop": "imageinfo",
                "iiprop": "extmetadata|url",
                "format": "json",
            },
            _bucket(cache, "http"),
        )
        pages = ((data or {}).get("query") or {}).get("pages") or {}
        ranked = []
        for page in pages.values():
            hit = _info_from_pages({page.get("pageid", 0): page})
            if not hit or not _name_matches(name, hit["title"], all_tokens=(mode == "shop")):
                continue
            ranked.append(hit)
        if ranked:
            found = ranked[0]
            break
    searches[key] = found
    return found


def commons_geo_photo(lat, lon, name, cache, allow_backup=True):
    if lat is None or lon is None:
        return None
    key = "%.3f,%.3f:%s" % (lat, lon, "b" if allow_backup else "n")
    geos = _bucket(cache, "geo")
    if key in geos:
        return geos[key]
    data = _api(
        COMMONS_API,
        {
            "action": "query",
            "list": "geosearch",
            "gscoord": "%s|%s" % (lat, lon),
            "gsradius": "900",
            "gsnamespace": "6",
            "gslimit": "12",
            "format": "json",
        },
        _bucket(cache, "http"),
    )
    hits = ((data or {}).get("query") or {}).get("geosearch") or []
    found = None
    backup = None
    for hit in hits:
        title = hit.get("title") or ""
        if not _title_ok(title):
            continue
        licensed = file_if_free(title, cache)
        if not licensed:
            continue
        if _name_matches(name, title):
            found = licensed
            break
        if backup is None:
            backup = licensed
    # Sans nom dans le fichier : seulement très proche (le geosearch est déjà 900 m).
    result = found or (backup if allow_backup else None)
    geos[key] = result
    return result


def _file_and_category_from_tags(tags):
    tags = tags or {}
    commons = (tags.get("wikimedia_commons") or "").strip()
    filename = None
    category = None
    if commons.startswith("File:"):
        filename = commons[5:]
    elif commons.startswith("Category:"):
        category = commons
    elif commons:
        filename = commons
    image = tags.get("image") or ""
    if not filename and "Special:FilePath/" in image:
        filename = urllib.parse.unquote(image.split("Special:FilePath/", 1)[-1].split("?", 1)[0])
    if not filename and "File:" in image and "commons.wikimedia.org" in image:
        filename = urllib.parse.unquote(image.split("File:", 1)[-1].split("?", 1)[0])
    return filename, category


def licensed_photo(name, lat, lon, tags=None, cache=None, allow_geo_backup=True, mode="place"):
    """Retourne (url, licence) Commons libre, sinon (None, None)."""
    cache = cache if cache is not None else {}
    tags = tags or {}
    filename, category = _file_and_category_from_tags(tags)
    hit = file_if_free(filename, cache) if filename else None
    if not hit and tags.get("wikidata"):
        hit = wikidata_entity_photo(
            tags.get("wikidata"), lat, lon, cache, any_country=(mode in ("shop", "int", "night"))
        )
    if not hit and tags.get("wikipedia"):
        hit = wikipedia_photo(tags.get("wikipedia"), lat, lon, cache)
    if not hit and category:
        hit = category_photo(category, name, cache)
    if not hit and mode == "shop":
        hit = category_photo(name.strip(), name, cache, all_tokens=True)
    if not hit:
        hit = wikidata_search_photo(name, lat, lon, cache, chains=(mode == "shop"))
    if not hit:
        hit = commons_search_photo(name, cache, mode=mode)
    if not hit:
        geo_backup = allow_geo_backup and mode not in ("shop", "night")
        hit = commons_geo_photo(lat, lon, name, cache, allow_backup=geo_backup)
    if not hit:
        return None, None
    return hit["url"], hit["license"]
