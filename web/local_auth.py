# -*- coding: utf-8 -*-
"""Comptes Sinki en local : email + code à 6 chiffres."""

import json
import os
import secrets
import shutil
import time
import uuid

import billing as sinki_billing

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(ROOT, "..", "data"))
PATH = os.path.join(DATA_DIR, "accounts.json")
BACKUP = os.path.join(DATA_DIR, "accounts.bak.json")
AVATAR_DIR = os.path.join(DATA_DIR, "avatars")
CODE_TTL = 15 * 60
SESSION_TTL = 60 * 60 * 24 * 60


def _empty():
    return {"accounts": {}, "pending": {}, "sessions": {}}


def _read_store(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("bad store")
    data.setdefault("accounts", {})
    data.setdefault("pending", {})
    data.setdefault("sessions", {})
    return data


def _load():
    for path in (PATH, BACKUP):
        try:
            return _read_store(path)
        except (OSError, ValueError):
            continue
    return _empty()


def _save(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, PATH)
    try:
        shutil.copy2(PATH, BACKUP)
    except OSError:
        pass


def email_has_account(email):
    email = (email or "").strip().lower()
    if not email:
        return False
    data = _load()
    return email in (data.get("accounts") or {})


def nick_key(nick):
    return (nick or "").strip().lower()


def pseudo_taken(nick, except_email=""):
    key = nick_key(nick)
    if not key:
        return False
    except_email = (except_email or "").strip().lower()
    data = _load()
    for email, acc in (data.get("accounts") or {}).items():
        if email == except_email:
            continue
        if nick_key(acc.get("nick")) == key:
            return True
    for email, pending in (data.get("pending") or {}).items():
        if email == except_email:
            continue
        if nick_key(pending.get("nick")) == key:
            return True
    return False


def request_code(email, profile=None):
    email = (email or "").strip().lower()
    profile = profile or {}
    nick = (profile.get("nick") or "")[:40]
    if nick and pseudo_taken(nick, email):
        raise ValueError("taken")
    code = "%06d" % secrets.randbelow(1000000)
    data = _load()
    data["pending"][email] = {
        "code": code,
        "exp": time.time() + CODE_TTL,
        "first_name": (profile.get("first_name") or "")[:40],
        "last_name": (profile.get("last_name") or "")[:40],
        "nick": (profile.get("nick") or "")[:40],
    }
    _save(data)
    return code


def verify_code(email, token, profile=None):
    email = (email or "").strip().lower()
    token = str(token or "").strip()
    profile = profile or {}
    data = _load()
    pending = (data.get("pending") or {}).get(email) or {}
    if not pending or time.time() > float(pending.get("exp") or 0):
        return None
    if str(pending.get("code") or "") != token:
        return None
    accounts = data.setdefault("accounts", {})
    acc = accounts.get(email) or {"id": str(uuid.uuid4()), "email": email, "fav_ids": [], "plans": []}
    if profile.get("nick") and pseudo_taken(profile.get("nick"), email):
        raise ValueError("taken")
    acc["first_name"] = (profile.get("first_name") or pending.get("first_name") or acc.get("first_name") or "")[:40]
    acc["last_name"] = (profile.get("last_name") or pending.get("last_name") or acc.get("last_name") or "")[:40]
    acc["nick"] = (profile.get("nick") or pending.get("nick") or acc.get("nick") or "")[:40]
    accounts[email] = acc
    data["pending"].pop(email, None)
    sess = "sk_" + secrets.token_urlsafe(32)
    data.setdefault("sessions", {})[sess] = {"email": email, "exp": time.time() + SESSION_TTL}
    _save(data)
    return sess, acc


def user_from_token(token):
    token = (token or "").strip()
    if not token.startswith("sk_"):
        return None
    data = _load()
    sess = (data.get("sessions") or {}).get(token) or {}
    if not sess or time.time() > float(sess.get("exp") or 0):
        return None
    acc = (data.get("accounts") or {}).get(sess.get("email") or "")
    if not acc:
        return None
    return {
        "id": acc.get("id"),
        "email": acc.get("email"),
        "sinki_local": True,
        "user_metadata": {
            "first_name": acc.get("first_name") or "",
            "last_name": acc.get("last_name") or "",
            "nick": acc.get("nick") or "",
            "group_code": acc.get("group_code") or "",
            "plans": acc.get("plans") or [],
            "fav_ids": acc.get("fav_ids") or [],
            "plan": "plus" if sinki_billing.plus_active(acc) else "free",
            "avatar_url": avatar_url(acc),
            "avatar_ext": acc.get("avatar_ext") or "",
            "entitlements": sinki_billing.public_entitlements(acc),
        },
    }


def save_account(email, fields):
    email = (email or "").strip().lower()
    data = _load()
    acc = (data.get("accounts") or {}).get(email)
    if not acc:
        return None
    for key in ("first_name", "last_name", "group_code", "plans", "fav_ids", "avatar_ext"):
        if key in fields:
            acc[key] = fields[key]
    if "nick" in fields:
        nick = fields.get("nick") or ""
        if nick and pseudo_taken(nick, email):
            raise ValueError("taken")
        acc["nick"] = nick[:40]
    data["accounts"][email] = acc
    _save(data)
    return acc


def avatar_path(user_id, ext):
    uid = str(user_id or "").strip()
    ext = str(ext or "").strip().lower().lstrip(".")
    if not uid or ext not in ("jpg", "jpeg", "png", "webp"):
        return ""
    return os.path.join(AVATAR_DIR, uid + "." + ("jpg" if ext == "jpeg" else ext))


def avatar_url(acc):
    uid = (acc or {}).get("id") or ""
    ext = (acc or {}).get("avatar_ext") or ""
    path = avatar_path(uid, ext)
    if not path or not os.path.isfile(path):
        return ""
    stamp = int(os.path.getmtime(path))
    shown = "jpg" if ext in ("jpg", "jpeg") else ext
    return "/avatars/" + uid + "." + shown + "?v=" + str(stamp)


def save_avatar(email, blob, ext):
    email = (email or "").strip().lower()
    ext = "jpg" if ext in ("jpg", "jpeg") else ext
    data = _load()
    acc = (data.get("accounts") or {}).get(email)
    if not acc:
        raise ValueError("Compte introuvable")
    os.makedirs(AVATAR_DIR, exist_ok=True)
    uid = acc.get("id") or ""
    for name in os.listdir(AVATAR_DIR):
        if name.startswith(uid + "."):
            try:
                os.unlink(os.path.join(AVATAR_DIR, name))
            except OSError:
                pass
    path = avatar_path(uid, ext)
    with open(path, "wb") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    acc["avatar_ext"] = ext
    data["accounts"][email] = acc
    _save(data)
    return avatar_url(acc)


def read_avatar(user_id, ext):
    path = avatar_path(user_id, ext)
    if not path or not os.path.isfile(path):
        return None, ""
    with open(path, "rb") as fh:
        blob = fh.read()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "application/octet-stream")
    return blob, mime


def delete_account(email):
    email = (email or "").strip().lower()
    if not email:
        return False
    data = _load()
    acc = (data.get("accounts") or {}).pop(email, None)
    (data.get("pending") or {}).pop(email, None)
    sessions = data.get("sessions") or {}
    for token, sess in list(sessions.items()):
        if (sess or {}).get("email") == email:
            sessions.pop(token, None)
    _save(data)
    uid = (acc or {}).get("id") or ""
    if uid and os.path.isdir(AVATAR_DIR):
        for name in os.listdir(AVATAR_DIR):
            if name.startswith(uid + "."):
                try:
                    os.unlink(os.path.join(AVATAR_DIR, name))
                except OSError:
                    pass
    return True
