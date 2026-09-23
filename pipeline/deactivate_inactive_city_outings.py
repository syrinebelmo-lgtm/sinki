# -*- coding: utf-8 -*-
"""Masque les sorties des villes BE/CH désactivées (communes hors pays)."""

import json
import os
import time
import urllib.request

from .run import load_env
from .supabase_io import fetch_all


def patch_outings(url, service_role, city_ids):
    headers = {
        "apikey": service_role,
        "Authorization": "Bearer " + service_role,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    body = json.dumps({"is_active": False}).encode("utf-8")
    n = 0
    for cid in city_ids:
        last = None
        for attempt in range(4):
            req = urllib.request.Request(
                url.rstrip("/") + "/rest/v1/outings?city_id=eq." + str(cid) + "&is_active=eq.true",
                data=body,
                headers=headers,
                method="PATCH",
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    resp.read()
                last = None
                break
            except Exception as exc:
                last = exc
                time.sleep(2 * (attempt + 1))
        if last:
            print("fail city", cid, last, flush=True)
        n += 1
        if n % 50 == 0:
            print("villes traitées", n, "/", len(city_ids), flush=True)
        time.sleep(0.03)
    return n


def main():
    load_env(".env")
    url = os.environ.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        raise SystemExit("SUPABASE_URL et SUPABASE_SERVICE_ROLE requis")
    for cc in ("BE", "CH"):
        inactive = fetch_all(
            url,
            service_role,
            "cities",
            "id,name,slug",
            extra="&country_code=eq." + cc + "&is_active=eq.false",
        )
        ids = [row["id"] for row in inactive if row.get("id") is not None]
        print("inactive", cc, len(ids), flush=True)
        if ids:
            patch_outings(url, service_role, ids)
        active = fetch_all(
            url,
            service_role,
            "cities",
            "id",
            extra="&country_code=eq." + cc + "&is_active=eq.true",
        )
        print("actives", cc, len(active), flush=True)


if __name__ == "__main__":
    main()
