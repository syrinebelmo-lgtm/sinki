# -*- coding: utf-8 -*-
"""Miroir Python de web/catalog.js — garder les ids et EUR alignés."""

CATALOG = {
    "plus": {
        "week": {"id": "sinki.plus.week", "family": "plus", "period": "week", "eur": 2.99},
        "month": {"id": "sinki.plus.month", "family": "plus", "period": "month", "eur": 9.99},
        "year": {"id": "sinki.plus.year", "family": "plus", "period": "year", "eur": 99.99},
    },
    "unlimited": {
        "week": {"id": "sinki.unlimited.week", "family": "unlimited", "period": "week", "eur": 1.99},
        "month": {"id": "sinki.unlimited.month", "family": "unlimited", "period": "month", "eur": 7.99},
        "year": {"id": "sinki.unlimited.year", "family": "unlimited", "period": "year", "eur": 89.99},
    },
    "event": {
        "publish": {"id": "sinki.event.publish", "family": "event", "period": "once", "eur": 4.99, "days": 1},
        "3": {"id": "sinki.event.boost.3", "family": "event", "period": "once", "eur": 7.99, "days": 3},
        "7": {"id": "sinki.event.boost.7", "family": "event", "period": "once", "eur": 12.99, "days": 7},
        "30": {"id": "sinki.event.boost.30", "family": "event", "period": "once", "eur": 39.99, "days": 30},
    },
    "noads": {
        "lifetime": {"id": "sinki.noads.lifetime", "family": "noads", "period": "lifetime", "eur": 5.99},
    },
}


def product_by_id(pid):
    pid = str(pid or "")
    for fam in CATALOG.values():
        for row in fam.values():
            if row.get("id") == pid:
                return row
    return None
