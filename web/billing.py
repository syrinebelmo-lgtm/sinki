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


def _account_view(acc_or_user):
    src = acc_or_user if isinstance(acc_or_user, dict) else {}
    meta = src.get("user_metadata") if isinstance(src.get("user_metadata"), dict) else {}
    raw = src.get("entitlements")
    if not isinstance(raw, dict):
        raw = meta.get("entitlements")
    if not isinstance(raw, dict):
        raw = {}
    plan = src.get("plan") or meta.get("plan") or ""
    return {"entitlements": raw, "plan": plan}


def public_entitlements(acc):
    view = _account_view(acc)
    raw = view["entitlements"]
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
    plus_on = (out.get("plus") or {}).get("active") or str(view.get("plan") or "") == "plus"
    if plus_on:
        plus_row = out.get("plus") or {}
        unlim = dict(out.get("unlimited") or {})
        if not unlim.get("active"):
            unlim["active"] = True
            if plus_row.get("expires") and not unlim.get("expires"):
                unlim["expires"] = plus_row["expires"]
            if plus_row.get("period") and not unlim.get("period"):
                unlim["period"] = plus_row["period"]
            unlim["included_in"] = "plus"
            out["unlimited"] = unlim
    return out


def plus_active(acc):
    ents = public_entitlements(acc)
    if (ents.get("plus") or {}).get("active"):
        return True
    return str(_account_view(acc).get("plan") or "") == "plus"


def unlimited_active(acc):
    ents = public_entitlements(acc)
    if (ents.get("unlimited") or {}).get("active"):
        return True
    return plus_active(acc)


def entitlements_for_user(user):
    return public_entitlements(user)


def _grant_unlimited(ents, expires, period, product_id, source):
    prev = ents.get("unlimited") if isinstance(ents.get("unlimited"), dict) else {}
    prev_exp = float(prev.get("expires") or 0)
    if prev.get("lifetime") or prev_exp >= float(expires or 0):
        return
    row = {
        "productId": prev.get("productId") or product_id,
        "period": prev.get("period") or period,
        "expires": expires,
        "source": source,
    }
    if not prev.get("productId"):
        row["included_in"] = "plus"
    ents["unlimited"] = row


def apply_verified(acc, product_id, source="iap"):
    prod = product_by_id(product_id)
    if not prod:
        raise ValueError("produit")
    ents = dict(acc.get("entitlements") or {})
    now = _now()
    fam = prod["family"]
    if fam == "plus":
        expires = now + PERIOD_SEC.get(prod["period"], PERIOD_SEC["month"])
        ents["plus"] = {
            "productId": prod["id"],
            "period": prod["period"],
            "expires": expires,
            "source": source,
        }
        acc["plan"] = "plus"
        _grant_unlimited(ents, expires, prod["period"], prod["id"], source)
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
