# -*- coding: utf-8 -*-
"""Communes officielles des pays touristiques (GeoNames). Aucune sortie."""

import io
import json
import os
import re
import time
import urllib.request
import zipfile

from .categories import slugify
from .int_catalog import _post_cities
from .rest_countries import REST_PPL
from .run import load_env
from .supabase_io import fetch_all

UA = "Sinki/1.0 (https://sinki-sorties.fly.dev; cities)"
GEONAMES = "https://download.geonames.org/export/dump/%s.zip"
CACHE = os.path.join("data", "geonames")

# Niveau admin GeoNames = communes / municipalités (pas les hameaux, pas les sorties).
MUNI = {
    "AD": ("A", "ADM2"),
    "AE": ("A", "ADM2"),
    "AL": ("A", "ADM2"),
    "AR": ("A", "ADM2"),
    "AT": ("A", "ADM3"),
    "AU": ("A", "ADM2"),
    "BA": ("A", "ADM2"),
    "BE": ("A", "ADM4"),
    "BG": ("A", "ADM2"),
    "BR": ("A", "ADM2"),
    "CA": ("A", "ADM3"),
    "CH": ("A", "ADM3"),
    "CL": ("A", "ADM3"),
    "CO": ("A", "ADM2"),
    "CR": ("A", "ADM3"),
    "CY": ("A", "ADM2"),
    "CZ": ("A", "ADM3"),
    "DE": ("A", "ADM4"),
    "DK": ("A", "ADM2"),
    "DO": ("A", "ADM2"),
    "EE": ("A", "ADM2"),
    "ES": ("A", "ADM3"),
    "FI": ("A", "ADM3"),
    "GB": ("A", "ADM4"),
    "GR": ("A", "ADM3"),
    "HR": ("A", "ADM2"),
    "ID": ("A", "ADM2"),
    "IE": None,
    "IS": ("A", "ADM2"),
    "IT": ("A", "ADM3"),
    "JP": ("A", "ADM2"),
    "KE": ("A", "ADM2"),
    "KR": ("A", "ADM2"),
    "LI": ("A", "ADM2"),
    "MC": None,
    "MD": ("A", "ADM1"),
    "MK": ("A", "ADM2"),
    "XK": ("A", "ADM2"),
    "LT": ("A", "ADM2"),
    "LU": ("A", "ADM2"),
    "LV": ("A", "ADM2"),
    "MA": ("A", "ADM3"),
    "ME": ("A", "ADM2"),
    "MT": ("A", "ADM1"),
    "MX": ("A", "ADM2"),
    "MY": ("A", "ADM2"),
    "NL": ("A", "ADM2"),
    "NO": ("A", "ADM2"),
    "NZ": ("A", "ADM2"),
    "PE": ("A", "ADM2"),
    "PH": ("A", "ADM3"),
    "PL": ("A", "ADM3"),
    "PT": ("A", "ADM2"),
    "RO": ("A", "ADM2"),
    "RS": ("A", "ADM2"),
    "SE": ("A", "ADM2"),
    "SG": None,
    "SI": ("A", "ADM1"),
    "SK": ("A", "ADM3"),
    "TH": ("A", "ADM2"),
    "TN": ("A", "ADM2"),
    "TR": ("A", "ADM2"),
    "US": None,
    "VN": ("A", "ADM2"),
    "ZA": ("A", "ADM3"),
}

# Pays sans maille commune fiable : agglomérations GeoNames (P) au-dessus du seuil.
PPL_MIN = {
    "AD": 0,
    "BA": 400,
    "EG": 15000,
    "HU": 400,
    "IE": 200,
    "IN": 20000,
    "KE": 2000,
    "LI": 0,
    "MC": 0,
    "MD": 200,
    "MK": 200,
    "ME": 100,
    "RS": 500,
    "SG": 0,
    "US": 1000,
}

# ADM4 GB = paroisses, sans Londres / Manchester. On ajoute les agglomérations GeoNames.
PPL_ALSO = {
    "GB": 20000,
    "AT": 15000,
    "HR": 10000,
    "GR": 15000,
    "CZ": 20000,
    "HU": 15000,
    "PL": 20000,
    "DK": 10000,
    "SE": 20000,
    "NO": 15000,
    "FI": 15000,
    "RO": 20000,
    "BG": 15000,
    "SK": 10000,
    "SI": 8000,
    "LU": 2000,
    "EE": 8000,
    "LV": 8000,
    "LT": 10000,
    "AL": 8000,
    "CY": 5000,
    "MT": 1000,
    "IS": 5000,
    "MK": 5000,
    "XK": 3000,
    "MD": 5000,
}

PREFIX = re.compile(
    r"^(gemeente|kommune|kommun|gmina|dimos|obshtina|comuna|municipality of|city of|"
    r"grad |markaz |amphoe |changwat |provincia de |província |okres |powiat |"
    r"emirate of |state of |région |region |kraj )\s*",
    re.I,
)
SUFFIX = re.compile(
    r"\s+(gemeente|kommune|kommun|ilçesi|district|county|shi)$",
    re.I,
)
SKIP = re.compile(
    r"\b(township of|historical|secteur|arrondissement|canton|district de|bezirk)\b",
    re.I,
)


def download(cc):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, cc + ".zip")
    if os.path.exists(path) and os.path.getsize(path) > 200:
        return path
    req = urllib.request.Request(GEONAMES % cc, headers={"User-Agent": UA})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
            with open(path, "wb") as fh:
                fh.write(data)
            return path
        except Exception as exc:
            last = exc
            time.sleep(3 * (attempt + 1))
    raise last


def clean_name(name):
    name = (name or "").strip()
    name = re.sub(r"-shi$", "", name, flags=re.I)
    name = PREFIX.sub("", name).strip()
    name = SUFFIX.sub("", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name


def parse_country(cc):
    zpath = download(cc)
    wanted = MUNI.get(cc)
    min_pop = PPL_MIN.get(cc)
    if cc in REST_PPL:
        wanted = None
        min_pop = REST_PPL[cc]
    if wanted is None and min_pop is None:
        min_pop = 8000
    out = []
    seen = set()
    with zipfile.ZipFile(zpath) as zf:
        with zf.open(cc + ".txt") as fh:
            for raw in fh:
                parts = raw.decode("utf-8").split("\t")
                if len(parts) < 15:
                    continue
                name, lat_s, lon_s = parts[1], parts[4], parts[5]
                fclass, fcode, country = parts[6], parts[7], parts[8]
                try:
                    pop = int(parts[14] or 0)
                except ValueError:
                    pop = 0
                if country != cc:
                    continue
                keep = False
                if wanted and fclass == wanted[0] and fcode == wanted[1]:
                    keep = True
                if min_pop is not None and fclass == "P" and fcode.startswith("PPL") and pop >= min_pop:
                    keep = True
                extra_pop = PPL_ALSO.get(cc)
                if extra_pop is not None and fclass == "P" and fcode.startswith("PPL") and pop >= extra_pop:
                    keep = True
                if fclass == "P" and fcode in ("PPLC", "PPLA") and pop >= 1000:
                    keep = True
                if not keep:
                    continue
                try:
                    lat = float(lat_s)
                    lon = float(lon_s)
                except ValueError:
                    continue
                label = clean_name(name)
                if len(label) < 2 or SKIP.search(label):
                    continue
                key = (label.lower(), round(lat, 3), round(lon, 3))
                if key in seen:
                    continue
                seen.add(key)
                out.append((label, lat, lon, pop))
    out.sort(key=lambda r: (-r[3], r[0].lower()))
    return out


def existing_index(url, service_role, cc):
    rows = fetch_all(
        url,
        service_role,
        "cities",
        "id,slug,name,country_code,is_active",
        extra="&country_code=eq." + cc,
    )
    by_slug = {row["slug"]: row for row in rows}
    by_name = {(row.get("name") or "").strip().lower(): row for row in rows}
    return by_slug, by_name, rows


def patch_active(url, service_role, ids):
    if not ids:
        return
    headers = {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    body = json.dumps({"is_active": True}).encode("utf-8")
    for i in range(0, len(ids), 40):
        chunk = ids[i : i + 40]
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/cities?id=in.(" + ",".join(str(x) for x in chunk) + ")",
            data=body,
            headers=headers,
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        time.sleep(0.04)


def upsert_country(url, service_role, cc, places):
    by_slug, by_name, _rows = existing_index(url, service_role, cc)
    created = 0
    revived = 0
    skipped = 0
    batch = []
    revive = []
    for name, lat, lon, _pop in places:
        prev = by_name.get(name.lower())
        if prev:
            if prev.get("is_active") is False:
                revive.append(prev["id"])
                revived += 1
            else:
                skipped += 1
            continue
        base = slugify(name) or "ville"
        slug = "%s-%s" % (base, cc.lower())
        n = 2
        while slug in by_slug:
            other = by_slug[slug]
            if other.get("country_code") == cc:
                skipped += 1
                slug = None
                break
            slug = "%s-%s-%s" % (base, cc.lower(), n)
            n += 1
        if not slug:
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
        by_slug[slug] = rec
        by_name[name.lower()] = rec
        created += 1
        if len(batch) >= 40:
            _post_cities(url, service_role, batch)
            print("villes", cc, created, flush=True)
            batch = []
    if batch:
        _post_cities(url, service_role, batch)
    if revive:
        patch_active(url, service_role, revive)
    print(
        "ok",
        cc,
        "sources",
        len(places),
        "ajoutées",
        created,
        "réactivées",
        revived,
        "déjà là",
        skipped,
        flush=True,
    )
    return created, revived, skipped, len(places)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--cc", default="")
    args = parser.parse_args()
    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")
    codes = [c.strip().upper() for c in (args.cc or ",".join(sorted(set(MUNI) | set(PPL_MIN)))).split(",") if c.strip()]
    codes = [c for c in codes if c != "FR"]
    for cc in codes:
        print("=== villes", cc, flush=True)
        try:
            places = parse_country(cc)
        except Exception as exc:
            print("fail download", cc, exc, flush=True)
            continue
        print("geonames", cc, len(places), flush=True)
        upsert_country(url, service_role, cc, places)


if __name__ == "__main__":
    main()
