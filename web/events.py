# -*- coding: utf-8 -*-
"""Événements organisateurs : dépôt, validation, boost 24 h à l’approbation.

Stockage durable : ligne réservée Supabase (blobstore) + photos dans Supabase
Storage. Avant, tout vivait dans data/events.json, effacé à chaque redémarrage
de Render.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import time
import uuid

import blobstore

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.environ.get("SINKI_DATA_DIR") or os.path.join(ROOT, "..", "data"))
PATH = os.path.join(DATA_DIR, "events.json")
PHOTO_DIR = os.path.join(DATA_DIR, "event_photos")
BOOST_SEC = 24 * 60 * 60
MAX_PHOTO = 500 * 1024
DATA_URL = re.compile(r"^data:image/(jpeg|jpg|png|webp);base64,(.+)$", re.I | re.S)


def _empty():
    return {"events": []}


STORE = blobstore.BlobStore("sinki-internal-events", PATH, _empty)


def _load():
    data = STORE.load()
    if not isinstance(data.get("events"), list):
        data["events"] = []
    return data


def _mutate(fn):
    def run(data):
        if not isinstance(data.get("events"), list):
            data["events"] = []
        return fn(data)
    return STORE.mutate(run)


def durable():
    """True when events survive a restart (Supabase configured)."""
    return bool(blobstore.supabase_conf()[0])


def moderator_email():
    return (os.environ.get("SINKI_MODERATOR_EMAIL") or "thesinkiisinki@gmail.com").strip().lower()


def is_moderator(email, local=False):
    email = (email or "").strip().lower()
    if email and email == moderator_email():
        return True
    return bool(local and email)


def _photo_ext(kind):
    kind = (kind or "jpeg").lower()
    if kind == "jpg":
        kind = "jpeg"
    if kind not in ("jpeg", "png", "webp"):
        return ""
    return "jpg" if kind == "jpeg" else kind


def save_photo(event_id, data_url):
    raw = (data_url or "").strip()
    hit = DATA_URL.match(raw)
    if not hit:
        raise ValueError("photo")
    ext = _photo_ext(hit.group(1))
    if not ext:
        raise ValueError("photo")
    try:
        blob = base64.b64decode(hit.group(2))
    except Exception:
        raise ValueError("photo")
    if not blob or len(blob) > MAX_PHOTO:
        raise ValueError("photo")
    name = event_id + "." + ext
    mime = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[ext]
    if durable():
        return blobstore.upload_public("event-photos", name, blob, mime)
    os.makedirs(PHOTO_DIR, exist_ok=True)
    with open(os.path.join(PHOTO_DIR, name), "wb") as fh:
        fh.write(blob)
    return "/event-photos/" + name


def read_photo(event_id, ext):
    ext = (ext or "").lower()
    if ext == "jpeg":
        ext = "jpg"
    if ext not in ("jpg", "png", "webp"):
        return b"", ""
    path = os.path.join(PHOTO_DIR, event_id + "." + ext)
    if not os.path.isfile(path):
        return b"", ""
    mime = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[ext]
    with open(path, "rb") as fh:
        return fh.read(), mime


def _money(val):
    if val in ("", None):
        return 0.0
    try:
        n = float(val)
    except (TypeError, ValueError):
        raise ValueError("tarif")
    if n < 0 or n > 500:
        raise ValueError("tarif")
    return n


def email_key(email):
    email = (email or "").strip().lower()
    if not email:
        return ""
    return hashlib.sha256(("sinki-like|" + email).encode("utf-8")).hexdigest()[:40]


def _likes(ev):
    raw = ev.get("likes")
    if not isinstance(raw, list):
        return []
    out = []
    seen = set()
    for item in raw:
        token = str(item or "").strip().lower()
        if "@" in token:
            token = email_key(token)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _comments(ev):
    raw = ev.get("comments")
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()[:280]
        if not text:
            continue
        out.append({
            "nick": str(item.get("nick") or "Sinki")[:40],
            "text": text,
            "created": item.get("created") or 0,
        })
    return out[-80:]


def public_row(ev, now=None, viewer=""):
    now = time.time() if now is None else now
    viewer = (viewer or "").strip().lower()
    boost_until = float(ev.get("boost_until") or 0)
    return {
        "id": ev.get("id"),
        "name": ev.get("name"),
        "description": ev.get("description"),
        "address": ev.get("address"),
        "when": ev.get("when") or "",
        "photo_url": ev.get("photo_url") or "",
        "price_min": ev.get("price_min"),
        "price_max": ev.get("price_max"),
        "currency": ev.get("currency") or "EUR",
        "status": ev.get("status") or "pending",
        "boosted": (ev.get("status") == "approved") and boost_until > now,
        "boostUntil": int(boost_until * 1000) if boost_until else 0,
        "category": "Événements temporaires",
        "kind": "event",
        "owner": ev.get("owner") or "",
        "like_count": len(_likes(ev)),
        "liked": bool(viewer and email_key(viewer) in _likes(ev)),
        "comments": _comments(ev),
    }


def create_event(owner, body):
    name = str(body.get("name") or "").strip()[:80]
    description = str(body.get("description") or "").strip()[:800]
    address = str(body.get("address") or "").strip()[:160]
    when = str(body.get("when") or "").strip()[:12]
    photo = body.get("photo") or ""
    if not name or not description or not address or not photo:
        raise ValueError("champs")
    extra_days = 0
    try:
        extra_days = int(body.get("extra_boost_days") or 0)
    except (TypeError, ValueError):
        extra_days = 0
    if extra_days not in (0, 3, 7, 30):
        extra_days = 0
    price = _money(body.get("price_min"))
    eid = str(uuid.uuid4())
    photo_url = save_photo(eid, photo)
    row = {
        "id": eid,
        "owner": (owner or "").strip().lower(),
        "name": name,
        "description": description,
        "address": address,
        "when": when,
        "photo_url": photo_url,
        "price_min": price,
        "price_max": price,
        "currency": "EUR",
        "status": "pending",
        "token": secrets.token_urlsafe(24),
        "boost_until": 0,
        "extra_boost_days": extra_days,
        "likes": [],
        "comments": [],
        "created": time.time(),
    }

    def change(data):
        data["events"].insert(0, row)
        data["events"] = data["events"][:500]
        return row

    return _mutate(change)


def list_public(viewer=""):
    now = time.time()
    out = []
    for ev in _load()["events"]:
        if ev.get("status") != "approved":
            continue
        out.append(public_row(ev, now, viewer))
        out[-1]["owner"] = ""
    return out


def list_mine(email):
    email = (email or "").strip().lower()
    now = time.time()
    return [public_row(ev, now, email) for ev in _load()["events"] if ev.get("owner") == email]


def list_pending(viewer=""):
    now = time.time()
    return [public_row(ev, now, viewer) for ev in _load()["events"] if ev.get("status") == "pending"]


def get_event(eid):
    eid = str(eid or "")
    for ev in _load()["events"]:
        if ev.get("id") == eid:
            return ev
    return None


def review_event(eid, action, token="", require_token=False):
    action = (action or "").strip().lower()
    if action not in ("approve", "reject"):
        raise ValueError("action")

    def change(data):
        found = next((ev for ev in data["events"] if ev.get("id") == eid), None)
        if not found:
            raise ValueError("introuvable")
        if (require_token or token) and not secrets.compare_digest(str(token), str(found.get("token") or "")):
            raise ValueError("lien")
        found["status"] = "approved" if action == "approve" else "rejected"
        if action == "approve":
            extra = int(found.get("extra_boost_days") or 0)
            found["boost_until"] = time.time() + BOOST_SEC + extra * 24 * 60 * 60
        else:
            found["boost_until"] = 0
        return public_row(found)

    return _mutate(change)


def toggle_like(eid, email):
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("compte")
    key = email_key(email)

    def change(data):
        found = next((ev for ev in data["events"] if ev.get("id") == eid), None)
        if not found or found.get("status") != "approved":
            raise ValueError("introuvable")
        likes = _likes(found)
        found["likes"] = [x for x in likes if x != key] if key in likes else likes + [key]
        return public_row(found, viewer=email)

    return _mutate(change)


def add_comment(eid, email, nick, text):
    email = (email or "").strip().lower()
    text = str(text or "").strip()[:280]
    nick = str(nick or "Sinki").strip()[:40] or "Sinki"
    if not email:
        raise ValueError("compte")
    if not text:
        raise ValueError("commentaire")

    def change(data):
        found = next((ev for ev in data["events"] if ev.get("id") == eid), None)
        if not found or found.get("status") != "approved":
            raise ValueError("introuvable")
        comments = found.get("comments") if isinstance(found.get("comments"), list) else []
        comments.append({"author": email_key(email), "nick": nick, "text": text, "created": time.time()})
        found["comments"] = comments[-80:]
        return public_row(found, viewer=email)

    return _mutate(change)


def purge_user(email):
    email = (email or "").strip().lower()
    if not email:
        return
    key = email_key(email)
    removed = []

    def change(data):
        kept = []
        for ev in data["events"]:
            if (ev.get("owner") or "") == email:
                removed.append(ev)
                continue
            ev["likes"] = [x for x in _likes(ev) if x != key]
            comments = []
            for item in ev.get("comments") or []:
                if not isinstance(item, dict):
                    continue
                author = str(item.get("author") or item.get("email") or "").strip().lower()
                if author == email or author == key:
                    continue
                comments.append({
                    "author": email_key(author) if "@" in author else author,
                    "nick": item.get("nick") or "Sinki",
                    "text": item.get("text") or "",
                    "created": item.get("created") or 0,
                })
            ev["comments"] = comments
            kept.append(ev)
        data["events"] = kept

    _mutate(change)
    for ev in removed:
        url = str(ev.get("photo_url") or "")
        if "/storage/v1/object/public/event-photos/" in url:
            blobstore.delete_public("event-photos", [url.rsplit("/", 1)[-1]])
        elif ev.get("id") and os.path.isdir(PHOTO_DIR):
            for name in os.listdir(PHOTO_DIR):
                if name.startswith(str(ev["id"]) + "."):
                    try:
                        os.unlink(os.path.join(PHOTO_DIR, name))
                    except OSError:
                        pass

