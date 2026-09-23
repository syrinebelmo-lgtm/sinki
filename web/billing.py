# -*- coding: utf-8 -*-
"""Entitlements Sinki. Les achats ne sont actifs qu’après un reçu store vérifié."""

import time

from catalog_data import CATALOG, product_by_id

PERIOD_SEC = {
    "week": 7 * 86400,
    "month": 31 * 86400,
    "year": 366 * 86400,
}


def _now():
    return time.time()


def public_entitlements(acc):
    raw = (acc or {}).get("entitlements") if isinstance(acc, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    now = _now()
    out = {}
    for kind, row in raw.items():
        if not isinstance(row, dict):
            continue
        item = dict(row)
        if item.get("lifetime"):
            item["active"] = True
        else:
            item["active"] = float(item.get("expires") or 0) > now
        out[kind] = item
    return out


def plus_active(acc):
    ents = public_entitlements(acc)
    if (ents.get("plus") or {}).get("active"):
        return True
    return str((acc or {}).get("plan") or "") == "plus"


def apply_verified(acc, product_id, source="iap"):
    prod = product_by_id(product_id)
    if not prod:
        raise ValueError("produit")
    ents = dict(acc.get("entitlements") or {})
    now = _now()
    fam = prod["family"]
    if fam == "plus":
        ents["plus"] = {
            "productId": prod["id"],
            "period": prod["period"],
            "expires": now + PERIOD_SEC.get(prod["period"], PERIOD_SEC["month"]),
            "source": source,
        }
        acc["plan"] = "plus"
    elif fam == "unlimited":
        ents["unlimited"] = {
            "productId": prod["id"],
            "period": prod["period"],
            "expires": now + PERIOD_SEC.get(prod["period"], PERIOD_SEC["month"]),
            "source": source,
        }
    elif fam == "noads":
        ents["no_ads"] = {
            "productId": prod["id"],
            "lifetime": True,
            "source": source,
            "at": now,
        }
    elif fam == "event":
        credits = list(ents.get("event_credits") or [])
        credits.append({"productId": prod["id"], "days": prod.get("days") or 0, "at": now, "used": False})
        ents["event_credits"] = credits[-40:]
    acc["entitlements"] = ents
    return acc


def confirm_rejected(body):
    """Refuse tout achat sans reçu natif vérifiable (pas de succès simulé)."""
    product_id = str((body or {}).get("productId") or "")
    receipt = str((body or {}).get("receipt") or "")
    platform = str((body or {}).get("platform") or "").lower()
    if not product_by_id(product_id):
        return "produit"
    if platform not in ("ios", "android") or not receipt.strip():
        return "store"
    return "unverified"
