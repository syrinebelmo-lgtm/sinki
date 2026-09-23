# -*- coding: utf-8 -*-
"""Importe les pays REST (villes + OSM + photos + quota). --hours 0 = jusqu’au bout."""

import argparse
import subprocess
import sys
import time

from .rest_countries import REST_OSM

PHOTO_LIMIT = 70
LEFTOVER = (
    "US,IN,IR,IL,JM,JP,JO,KZ,KE,KG,KW,LA,LS,LB,LR,LY,MG,MY,MW,ML,MU,MR,MX,MN,MZ,"
    "NA,NP,NI,NE,NG,NZ,UG,UZ,PK,PA,PY,PE,PH,QA,RW,SN,SG,SO,SD,LK,SR,SY,TW,TZ,TD,"
    "TH,TG,TM,UY,VE,VN,YE,ZM,ZW"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=0)
    parser.add_argument("--cc", default=LEFTOVER)
    args = parser.parse_args()
    codes = [c.strip().upper() for c in args.cc.split(",") if c.strip()]
    deadline = time.time() + args.hours * 3600 if args.hours > 0 else None
    done = []
    leftover = []
    for i, cc in enumerate(codes, 1):
        if deadline is not None and deadline - time.time() < 90:
            leftover = codes[i - 1 :]
            print("STOP temps restant", ",".join(leftover), flush=True)
            break
        mins = int((deadline - time.time()) / 60) if deadline else -1
        print("=== pays", cc, i, "/", len(codes), "minutes restantes", mins, flush=True)
        cities = subprocess.call([sys.executable, "-m", "pipeline.tourist_cities", "--cc", cc])
        if cities != 0:
            print("villes fail", cc, cities, flush=True)
        catalog = subprocess.call(
            [
                sys.executable,
                "-m",
                "pipeline.int_catalog",
                "--osm-only",
                "--quota-only",
                "--photo-limit",
                str(PHOTO_LIMIT),
                "--cc",
                cc,
            ]
        )
        if catalog != 0:
            print("catalog fail", cc, catalog, flush=True)
        else:
            done.append(cc)
    else:
        leftover = []
    print("FIN rest done", len(done), "/", len(codes), "reste", len(leftover), flush=True)
    if leftover:
        print("PAS FAITS", ",".join(leftover), flush=True)


if __name__ == "__main__":
    main()
