# -*- coding: utf-8 -*-
"""Import massif Sinki : uniquement des sorties avec photo + prix réels."""

import argparse
import json
import os
import sys

from .city_match import resolve_city_id
from .nt_extract import extract_complete_from_nt_zip
from .quality import is_complete
from .supabase_io import fetch_city_indexes, to_outing_row, upsert_outings


def load_env(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nt", default="data/datatourisme.nt.zip")
    parser.add_argument("--jsonl", default="data/complete_outings.jsonl")
    parser.add_argument("--from-jsonl", action="store_true", help="Ne pas relire le dump NT")
    parser.add_argument("--upsert", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="0 = tout le dump, pas un mini-lot")
    args = parser.parse_args()

    load_env(".env")
    if args.from_jsonl:
        if not os.path.exists(args.jsonl):
            sys.exit("JSONL manquant: %s" % args.jsonl)
        complete = []
        with open(args.jsonl, encoding="utf-8") as fh:
            for line in fh:
                complete.append(json.loads(line))
        print("chargé", args.jsonl, "lignes", len(complete))
    else:
        if not os.path.exists(args.nt):
            sys.exit("Dump manquant: %s (téléchargement en cours ou relancer)" % args.nt)
        complete, priced = extract_complete_from_nt_zip(args.nt)
        os.makedirs(os.path.dirname(args.jsonl) or ".", exist_ok=True)
        with open(args.jsonl, "w", encoding="utf-8") as fh:
            for row in complete:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        priced_path = os.path.join(os.path.dirname(args.jsonl) or ".", "priced_outings.jsonl")
        with open(priced_path, "w", encoding="utf-8") as fh:
            for row in priced:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("écrit", args.jsonl, "lignes", len(complete))
        print("écrit", priced_path, "lignes", len(priced))
    if args.limit:
        complete = complete[: args.limit]

    if not args.upsert:
        print("dry-run : passe --upsert avec SUPABASE_SERVICE_ROLE pour écrire")
        return

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not key:
        sys.exit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis pour --upsert")

    slugs, by_name, by_id, cities = fetch_city_indexes(url, key)
    print("villes indexées", len(slugs))
    payload = []
    unmatched = 0
    for item in complete:
        if not is_complete(item):
            continue
        city_id = resolve_city_id(item, slugs, by_name, by_id)
        if not city_id:
            unmatched += 1
            continue
        row = to_outing_row(item, city_id)
        if not row:
            unmatched += 1
            continue
        payload.append(row)
    print("prêtes à upsert", len(payload), "sans ville", unmatched)
    upsert_outings(url, key, payload)


if __name__ == "__main__":
    main()
