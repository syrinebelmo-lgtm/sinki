# -*- coding: utf-8 -*-
import re
import unicodedata

SINKI_CATEGORIES = {
    "loisirs": "Activités et loisirs",
    "balade": "Lieux gratuits et balades",
    "rando": "Randonnées",
    "culture": "Musées et culture",
    "resto": "Restaurants et cafés",
    "soiree": "Soirées et concerts",
    "shopping": "Shopping",
}


def slugify(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def map_category(types, price_min):
    blob = " ".join(types).lower()
    if any(
        k in blob
        for k in (
            "second_hand",
            "charity_shop",
            "friperie",
            "shopping_mall",
            "department_store",
            "marketplace",
        )
    ):
        return SINKI_CATEGORIES["shopping"]
    if any(k in blob for k in ("nightclub", "bar", "pub", "barorpub", "concert", "festival", "showevent", "entertainmentandevent")):
        return SINKI_CATEGORIES["soiree"]
    if any(k in blob for k in ("restaurant", "cafe", "foodestablishment", "winery")):
        return SINKI_CATEGORIES["resto"]
    if any(k in blob for k in ("hike", "hiking", "peak", "viewpoint", "via_ferrata", "alpine_hike", "wander")):
        return SINKI_CATEGORIES["rando"]
    if any(k in blob for k in ("museum", "cultural", "castle", "church", "heritage", "gallery", "cinema", "theatre")):
        return SINKI_CATEGORIES["culture"]
    if price_min == 0 and any(k in blob for k in ("park", "garden", "natural", "walk", "beach")):
        return SINKI_CATEGORIES["balade"]
    return SINKI_CATEGORIES["loisirs"]


def map_kind(types):
    blob = " ".join(types).lower()
    if "entertainmentandevent" in blob or "event" in blob:
        return "event"
    if "restaurant" in blob or "foodestablishment" in blob:
        return "restaurant"
    if "walk" in blob or "hike" in blob or "peak" in blob or "viewpoint" in blob or "park" in blob:
        return "walk"
    return "place"
