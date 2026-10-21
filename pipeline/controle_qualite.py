# -*- coding: utf-8 -*-
"""Contrôle qualité des sorties ajoutées automatiquement (OSM quotidien + Wikidata).

Ne supprime rien : les lignes fautives passent en is_active=false, après une
sauvegarde complète dans ~/sinki-sauvegardes/migration/controle_qualite/.

    python3 pipeline/controle_qualite.py [--dry] [--boucle]   (--boucle : toutes les 15 min tant que l'enrichissement tourne)
"""

import gzip
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import international_wikidata as w  # noqa: E402
from osm_quotidien import key_of  # noqa: E402

OUT = os.path.expanduser("~/sinki-sauvegardes/migration/controle_qualite")
MAX_KM = 25
# Seulement des mots sans ambiguïté (« University Park », un musée dans un ancien hôpital… restent).
BAD_NAME = re.compile(
    r"\b(hotel|h[oô]tel|hostel|motel|guest ?house|private|staff only|employees only|embassy|ambassade|"
    r"clinic|clinique|pharmacy|pharmacie|atm|parking|gas station|petrol station|station[- ]service|toilets?|"
    r"fixme|no name|sans nom)\b", re.I)
JUNK_NAME = re.compile(r"^(\W*|\d{6,}|[\d\s+().-]{7,}|(https?://|www\.)\S+)$")  # vide, identifiant, téléphone, site web
CLOSED_NAME = re.compile(r"\((closed|abandoned|demolished|ferm[eé]e?|cerrado|abandonado|geschlossen)\)|\b(abandoned|demolished|permanently closed)\b", re.I)
GENERIC_NAME = re.compile(r"^(restaurant|restaurante|cafe|café|caf[eé]teria|coffee|coffee shop|bar|pub|park|parc|parque|beach|plage|"
                          r"playa|museum|cinema|market|mercado|fast ?food|shop|store|mall|pizza|pizzeria|kiosk|kiosko|"
                          r"snack|bakery|grill|burger|ice cream|glacier|food court|canteen)$", re.I)
KEEP_NAME = re.compile(r"(museum|mus[eé]e|museo|muzeum|theat|th[eé][aâ]tre|teatro|park|parc|parque|garden|jardin|"
                       r"mall|shopping|complex|gallery|galerie|cinema|palace|palais)", re.I)


def rest(url, key, path):
    return w.http_json(url + "/rest/v1/" + path, headers={"apikey": key, "Authorization": "Bearer " + key})


def page(url, key, base):
    out, off = [], 0
    while True:
        rows = rest(url, key, "%s&order=id&limit=1000&offset=%d" % (base, off))
        out += rows
        if len(rows) < 1000:
            return out
        off += 1000


def cities():
    path = os.path.expanduser("~/sinki-sauvegardes/migration/cities.jsonl.gz")
    return {c["id"]: c for c in map(json.loads, gzip.open(path, "rt", encoding="utf-8"))}


def check(url, key, dry):
    by_city = cities()
    cols = "id,city_id,name,latitude,longitude,category,photo_url,source_name,is_active"
    rows = page(url, key, "outings?select=%s&source_name=eq.osm_local&is_active=eq.true" % cols)
    rows += page(url, key, "outings?select=%s&source_name=eq.wikidata&is_active=eq.true" % cols)
    # Les workers insèrent pendant la lecture : la pagination peut renvoyer une ligne deux fois.
    rows = list({r["id"]: r for r in rows}.values())
    bad = {}
    for r in rows:
        name = (r.get("name") or "").strip()
        city = by_city.get(r["city_id"])
        if not name or len(name) < 2 or JUNK_NAME.match(name):
            bad[r["id"]] = "nom vide ou illisible"
        elif CLOSED_NAME.search(name):
            bad[r["id"]] = "fermé ou abandonné"
        elif r["source_name"] == "osm_local" and GENERIC_NAME.match(name):
            bad[r["id"]] = "nom générique (pas un vrai nom de lieu)"
        elif r["source_name"] == "osm_local" and BAD_NAME.search(name) and not KEEP_NAME.search(name):
            bad[r["id"]] = "pas une sortie (hôtel, privé, service…)"
        elif r.get("latitude") in (None, 0) or r.get("longitude") in (None, 0):
            bad[r["id"]] = "coordonnées manquantes"
        elif city and w.dist_km((r["latitude"], r["longitude"]), (city["latitude"], city["longitude"])) > MAX_KM:
            bad[r["id"]] = "trop loin de sa ville"
    # Doublons : même ville + même nom qu'une autre sortie active (on garde celle avec photo / l'ancienne).
    per_city = {}
    for r in rows:
        if r["id"] not in bad:
            per_city.setdefault(r["city_id"], []).append(r)
    for cid, mine in per_city.items():
        if not any(r["source_name"] == "osm_local" for r in mine):
            continue
        others = rest(url, key, "outings?select=id,name&city_id=eq.%s&is_active=eq.true"
                      "&source_name=not.in.(osm_local,wikidata)&limit=5000" % cid)
        seen = {key_of(o.get("name")) for o in others}
        for r in sorted(mine, key=lambda r: (r["source_name"] == "osm_local", not r.get("photo_url"))):
            k = key_of(r["name"])
            if k in seen:
                bad[r["id"]] = "doublon"
            seen.add(k)
    return rows, bad


def hide(url, key, rows, bad):
    os.makedirs(OUT, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(OUT, "masquees_%s.jsonl" % stamp), "w") as fh:
        for r in rows:
            if r["id"] in bad:
                fh.write(json.dumps(dict(r, motif=bad[r["id"]]), ensure_ascii=False) + "\n")
    headers = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
               "Prefer": "return=minimal"}
    ids = sorted(bad)
    for i in range(0, len(ids), 100):
        chunk = ",".join(ids[i:i + 100])
        w.http_json(url + "/rest/v1/outings?id=in.(%s)" % urllib.parse.quote(chunk, safe=","),
                    json.dumps({"is_active": False}).encode(), headers, method="PATCH")


def once(dry):
    url, key = w.env()
    rows, bad = check(url, key, dry)
    motifs = {}
    for m in bad.values():
        motifs[m] = motifs.get(m, 0) + 1
    print("%s contrôlées %d, fautives %d %s" % (datetime.now().strftime("%H:%M"), len(rows), len(bad), motifs), flush=True)
    if bad and not dry:
        hide(url, key, rows, bad)


def running():
    return subprocess.run(["pgrep", "-f", "pipeline/(osm_quotidien|international_wikidata)"],
                          capture_output=True).returncode == 0


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    if "--boucle" in sys.argv:
        while running():
            try:
                once(dry)
            except Exception as exc:
                print("contrôle en erreur:", type(exc).__name__, exc, flush=True)
            time.sleep(900)
    once(dry)
