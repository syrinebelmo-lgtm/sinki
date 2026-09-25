# -*- coding: utf-8 -*-
"""Comptes Sinki : email + code à 6 chiffres.

Le fichier data/accounts.json est un cache local (gitignoré, disque éphémère
sur Render). Dès que SUPABASE_URL + SUPABASE_SERVICE_ROLE sont là, le store
vit aussi dans une ligne groups réservée (filters JSON) du projet Supabase
catalogue, pour que local et live partagent les mêmes comptes. Pas de mot
de passe en clair : OTP hashé (sha256).
"""

import base64
import hashlib
import json
import math
import os
import secrets
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import billing as sinki_billing

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(ROOT, "..", "data"))
PATH = os.path.join(DATA_DIR, "accounts.json")
BACKUP = os.path.join(DATA_DIR, "accounts.bak.json")
AVATAR_DIR = os.path.join(DATA_DIR, "avatars")
CODE_TTL = 15 * 60
SESSION_TTL = 60 * 60 * 24 * 60
CACHE_TTL = 0
AUTH_SHARE = "ZZSKAUTH"
AUTH_LABEL = "sinki-internal-auth"
AUTH_SHARE_LEN = 28
OTP_SALT = "sinki-otp:"
OTP_SEND_WINDOW = 15 * 60
OTP_SEND_MAX = 5
OTP_LOCK_KEYS = ("sends", "otp_sends", "otp_at", "rate_lock", "locked_until", "last_otp", "mail_sends")
MAX_VERIFY_TRIES = 5
AVATAR_EXTS = ("jpg", "jpeg", "png", "webp")
AVATAR_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

_LOCK = threading.RLock()
_mem = None
_mem_at = 0
_bootstrapped = False
_last_import = 0
_group_id = ""


def normalize_email(value):
    return "".join((value or "").split()).lower()


def _empty():
    return {"accounts": {}, "pending": {}, "sessions": {}, "otp_sends": {}}


def _read_store(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("bad store")
    return _normalize_store(data)


def _normalize_store(data):
    if not isinstance(data, dict):
        return _empty()
    accounts = {}
    for key, acc in (data.get("accounts") or {}).items():
        email = normalize_email(key or (acc or {}).get("email") or "")
        if not email or not isinstance(acc, dict):
            continue
        row = dict(acc)
        row["email"] = email
        accounts[email] = row
    pending = {}
    for key, row in (data.get("pending") or {}).items():
        email = normalize_email(key)
        if email and isinstance(row, dict):
            pending[email] = dict(row)
    sessions = {}
    for token, row in (data.get("sessions") or {}).items():
        if token and isinstance(row, dict):
            sess = dict(row)
            sess["email"] = normalize_email(sess.get("email") or "")
            sessions[token] = sess
    otp_sends = {}
    for key, stamps in (data.get("otp_sends") or {}).items():
        email = normalize_email(key)
        if not email or not isinstance(stamps, list):
            continue
        keep = []
        for stamp in stamps:
            try:
                keep.append(float(stamp))
            except (TypeError, ValueError):
                continue
        if keep:
            otp_sends[email] = keep
    return {"accounts": accounts, "pending": pending, "sessions": sessions, "otp_sends": otp_sends}


def _sb_conf():
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    parts = (os.environ.get("SUPABASE_SERVICE_ROLE") or "").strip().split()
    key = parts[0] if parts else ""
    if url and key:
        return url, key
    return "", ""


def _sb_request(method, path, body=None, extra=None):
    url, key = _sb_conf()
    if not url:
        raise RuntimeError("no supabase")
    headers = {
        "apikey": key,
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if extra:
        headers.update(extra)
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, raw


def _prune(data):
    now = time.time()
    pending = {}
    for email, row in (data.get("pending") or {}).items():
        if isinstance(row, dict) and float(row.get("exp") or 0) > now:
            pending[email] = row
    sessions = {}
    for token, row in (data.get("sessions") or {}).items():
        if isinstance(row, dict) and float(row.get("exp") or 0) > now:
            sessions[token] = row
    data["pending"] = pending
    data["sessions"] = sessions
    sends = {}
    for email, stamps in (data.get("otp_sends") or {}).items():
        keep = []
        for stamp in stamps or []:
            try:
                val = float(stamp)
            except (TypeError, ValueError):
                continue
            if now - val < OTP_SEND_WINDOW:
                keep.append(val)
        if keep:
            sends[email] = keep
    data["otp_sends"] = sends
    return data


def _store_from_filters(filters):
    if not isinstance(filters, dict):
        return _empty()
    blob = filters.get("store") if isinstance(filters.get("store"), dict) else filters
    if "accounts" in (blob or {}):
        return _normalize_store(blob)
    return _empty()


def _load_file():
    for path in (PATH, BACKUP):
        try:
            return _read_store(path)
        except (OSError, ValueError):
            continue
    return _empty()


def _save_file(data):
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


def _find_auth_row():
    global _group_id
    status, raw = _sb_request(
        "GET",
        "/rest/v1/groups?origin_label=eq." + urllib.parse.quote(AUTH_LABEL) + "&select=id,share_code,filters",
    )
    rows = []
    if status < 400 and raw:
        try:
            rows = json.loads(raw.decode("utf-8") or "[]")
        except (ValueError, UnicodeDecodeError):
            rows = []
    if not rows:
        status, raw = _sb_request(
            "GET",
            "/rest/v1/groups?share_code=eq." + urllib.parse.quote(AUTH_SHARE) + "&select=id,share_code,filters",
        )
        if status < 400 and raw:
            try:
                rows = json.loads(raw.decode("utf-8") or "[]")
            except (ValueError, UnicodeDecodeError):
                rows = []
    if not rows:
        return ""
    _group_id = str(rows[0].get("id") or "")
    code = str(rows[0].get("share_code") or "")
    if _group_id and (code == AUTH_SHARE or len(code) < AUTH_SHARE_LEN):
        secret = "SK" + secrets.token_hex(13).upper()
        _sb_request(
            "PATCH",
            "/rest/v1/groups?id=eq." + urllib.parse.quote(_group_id),
            {"share_code": secret, "origin_label": AUTH_LABEL},
        )
    return _group_id


def _load_remote():
    if not _sb_conf()[0]:
        return None
    row_id = _find_auth_row()
    if not row_id:
        return _empty()
    status, raw = _sb_request(
        "GET",
        "/rest/v1/groups?id=eq." + urllib.parse.quote(row_id) + "&select=id,filters",
    )
    if status >= 400 or not raw:
        return None
    try:
        rows = json.loads(raw.decode("utf-8") or "[]")
    except (ValueError, UnicodeDecodeError):
        return None
    if not rows:
        return _empty()
    return _store_from_filters(rows[0].get("filters"))


def _save_remote(data):
    global _group_id
    if not _sb_conf()[0]:
        return False
    data = _prune(_normalize_store(data))
    filters = {
        "v": 1,
        "accounts": data.get("accounts") or {},
        "pending": data.get("pending") or {},
        "sessions": data.get("sessions") or {},
        "otp_sends": data.get("otp_sends") or {},
    }
    row_id = _group_id or _find_auth_row()
    if row_id:
        status, _raw = _sb_request(
            "PATCH",
            "/rest/v1/groups?id=eq." + urllib.parse.quote(row_id),
            {"filters": filters, "origin_label": AUTH_LABEL},
        )
        if status < 400:
            _group_id = row_id
            return True
        _group_id = ""
    body = {
        "share_code": "SK" + secrets.token_hex(13).upper(),
        "origin_label": AUTH_LABEL,
        "participant_count": 1,
        "filters": filters,
        "candidate_outing_ids": [],
        "status": "open",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat(),
    }
    status, raw = _sb_request("POST", "/rest/v1/groups", body)
    if status in (200, 201) and raw:
        try:
            rows = json.loads(raw.decode("utf-8"))
            if rows:
                _group_id = str(rows[0].get("id") or "")
        except (ValueError, UnicodeDecodeError):
            pass
        return True
    return False


def _merge_accounts(remote, local):
    """Ajoute les comptes locaux absents du store partagé. Ne log jamais les emails."""
    merged = _normalize_store(remote)
    imported = 0
    local = _normalize_store(local)
    for email, acc in (local.get("accounts") or {}).items():
        if email not in merged["accounts"]:
            merged["accounts"][email] = dict(acc)
            imported += 1
        else:
            cur = merged["accounts"][email]
            for key in ("first_name", "last_name", "nick", "group_code", "avatar_ext", "avatar_data", "avatar_rev", "plan"):
                if not cur.get(key) and acc.get(key):
                    cur[key] = acc[key]
            if not cur.get("fav_ids") and acc.get("fav_ids"):
                cur["fav_ids"] = acc.get("fav_ids")
            if not cur.get("plans") and acc.get("plans"):
                cur["plans"] = acc.get("plans")
            if acc.get("entitlements") and not cur.get("entitlements"):
                cur["entitlements"] = acc.get("entitlements")
    for token, sess in (local.get("sessions") or {}).items():
        if token not in merged["sessions"]:
            merged["sessions"][token] = dict(sess)
    sends = dict(merged.get("otp_sends") or {})
    for email, stamps in (local.get("otp_sends") or {}).items():
        have = set(sends.get(email) or [])
        for stamp in stamps or []:
            try:
                have.add(float(stamp))
            except (TypeError, ValueError):
                continue
        if have:
            sends[email] = sorted(have)
    merged["otp_sends"] = sends
    return merged, imported


def bootstrap():
    """Fusionne le cache disque vers Supabase. Appeler après load_env()."""
    global _mem, _mem_at, _bootstrapped, _last_import
    with _LOCK:
        if _bootstrapped:
            return _last_import
        _bootstrapped = True
        local = _load_file()
        remote = _load_remote()
        if remote is None:
            _mem = local
            _mem_at = time.time()
            return 0
        merged, imported = _merge_accounts(remote, local)
        _save_file(merged)
        if imported or remote != merged or not (remote.get("accounts") or {}):
            _save_remote(merged)
        _mem = merged
        _mem_at = time.time()
        _last_import = imported
        print(
            "Sinki auth → store partagé (%s comptes, +%s importés)"
            % (len(merged.get("accounts") or {}), imported),
            flush=True,
        )
        return imported


def _load():
    global _mem, _mem_at
    now = time.time()
    if _mem is not None and now - _mem_at < CACHE_TTL:
        return _mem
    remote = _load_remote()
    local = _load_file()
    if remote is None:
        data = local
    elif (remote.get("accounts") or {}) or not (local.get("accounts") or {}):
        data = remote
    else:
        data = local
    _mem = data
    _mem_at = now
    return data


def _save(data):
    global _mem, _mem_at
    data = _normalize_store(data)
    _mem = data
    _mem_at = time.time()
    _save_file(data)
    try:
        _save_remote(data)
    except Exception:
        pass


def _code_digest(token):
    return hashlib.sha256((OTP_SALT + str(token or "").strip()).encode("utf-8")).hexdigest()


def _pending_matches(pending, token):
    if not pending:
        return False
    token = str(token or "").strip()
    if not token:
        return False
    digest = pending.get("code_hash") or ""
    if digest:
        return digest == _code_digest(token)
    return str(pending.get("code") or "") == token


def email_has_account(email):
    email = normalize_email(email)
    if not email:
        return False
    with _LOCK:
        data = _load()
        return email in (data.get("accounts") or {})


def nick_key(nick):
    return (nick or "").strip().lower()


def pseudo_taken(nick, except_email=""):
    key = nick_key(nick)
    if not key:
        return False
    except_email = normalize_email(except_email)
    with _LOCK:
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


def otp_send_status(email):
    """Return (blocked, wait_sec). Failed sends must not be recorded."""
    email = normalize_email(email)
    now = time.time()
    with _LOCK:
        data = _load()
        stamps = []
        for stamp in (data.get("otp_sends") or {}).get(email) or []:
            try:
                val = float(stamp)
            except (TypeError, ValueError):
                continue
            if now - val < OTP_SEND_WINDOW:
                stamps.append(val)
    if len(stamps) >= OTP_SEND_MAX:
        wait = OTP_SEND_WINDOW - (now - min(stamps))
        return True, max(1, int(math.ceil(wait)))
    return False, 0


def record_otp_send(email):
    email = normalize_email(email)
    if not email:
        return
    now = time.time()
    with _LOCK:
        data = _load()
        sends = data.setdefault("otp_sends", {})
        stamps = []
        for stamp in sends.get(email) or []:
            try:
                val = float(stamp)
            except (TypeError, ValueError):
                continue
            if now - val < OTP_SEND_WINDOW:
                stamps.append(val)
        stamps.append(now)
        sends[email] = stamps
        data["otp_sends"] = sends
        _save(data)


def clear_otp_sends(email):
    """Drop the send window and any lock fields for one account. Never log the email."""
    email = normalize_email(email)
    if not email:
        return {"cleared": False, "had_sends": 0, "extra_keys": 0}
    with _LOCK:
        data = _load()
        stamps = (data.get("otp_sends") or {}).pop(email, None) or []
        extra = 0
        acc = (data.get("accounts") or {}).get(email)
        if isinstance(acc, dict):
            for key in OTP_LOCK_KEYS:
                if key in acc:
                    acc.pop(key, None)
                    extra += 1
        pending = (data.get("pending") or {}).get(email)
        if isinstance(pending, dict):
            for key in OTP_LOCK_KEYS:
                if key in pending:
                    pending.pop(key, None)
                    extra += 1
        _save(data)
        return {"cleared": True, "had_sends": len(stamps), "extra_keys": extra}


def request_code(email, profile=None):
    email = normalize_email(email)
    profile = profile or {}
    nick = (profile.get("nick") or "")[:40]
    if nick and pseudo_taken(nick, email):
        raise ValueError("taken")
    code = "%06d" % secrets.randbelow(1000000)
    with _LOCK:
        data = _load()
        data["pending"][email] = {
            "code_hash": _code_digest(code),
            "exp": time.time() + CODE_TTL,
            "first_name": (profile.get("first_name") or "")[:40],
            "last_name": (profile.get("last_name") or "")[:40],
            "nick": nick,
            "via": "local",
            "tries": 0,
        }
        _save(data)
    return code


def mark_pending_external(email, via="gotrue"):
    email = normalize_email(email)
    with _LOCK:
        data = _load()
        pending = (data.get("pending") or {}).get(email)
        if not pending:
            return False
        pending.pop("code", None)
        pending.pop("code_hash", None)
        pending["via"] = via
        pending["exp"] = time.time() + CODE_TTL
        data["pending"][email] = pending
        _save(data)
        return True


def pending_via(email):
    email = normalize_email(email)
    with _LOCK:
        data = _load()
        pending = (data.get("pending") or {}).get(email) or {}
        if not pending or time.time() > float(pending.get("exp") or 0):
            return ""
        return str(pending.get("via") or "local")


def _nick_taken_in(data, nick, except_email=""):
    key = nick_key(nick)
    if not key:
        return False
    except_email = normalize_email(except_email)
    for email, acc in (data.get("accounts") or {}).items():
        if email != except_email and nick_key((acc or {}).get("nick")) == key:
            return True
    for email, pending in (data.get("pending") or {}).items():
        if email != except_email and nick_key((pending or {}).get("nick")) == key:
            return True
    return False


def _upsert_account(data, email, profile, pending=None):
    pending = pending or {}
    profile = profile or {}
    accounts = data.setdefault("accounts", {})
    acc = accounts.get(email) or {"id": str(uuid.uuid4()), "email": email, "fav_ids": [], "plans": []}
    if profile.get("nick") and _nick_taken_in(data, profile.get("nick"), email):
        raise ValueError("taken")
    acc["email"] = email
    acc["first_name"] = (profile.get("first_name") or pending.get("first_name") or acc.get("first_name") or "")[:40]
    acc["last_name"] = (profile.get("last_name") or pending.get("last_name") or acc.get("last_name") or "")[:40]
    acc["nick"] = (profile.get("nick") or pending.get("nick") or acc.get("nick") or "")[:40]
    accounts[email] = acc
    return acc


def _new_session(data, email):
    sess = "sk_" + secrets.token_urlsafe(32)
    data.setdefault("sessions", {})[sess] = {"email": email, "exp": time.time() + SESSION_TTL}
    return sess


def verify_code(email, token, profile=None):
    email = normalize_email(email)
    token = str(token or "").strip()
    profile = profile or {}
    with _LOCK:
        data = _load()
        pending = (data.get("pending") or {}).get(email) or {}
        if not pending or time.time() > float(pending.get("exp") or 0):
            return None
        if pending.get("via") == "gotrue":
            return None
        if not _pending_matches(pending, token):
            tries = int(pending.get("tries") or 0) + 1
            if tries >= MAX_VERIFY_TRIES:
                data["pending"].pop(email, None)
            else:
                pending["tries"] = tries
                data["pending"][email] = pending
            _save(data)
            return None
        acc = _upsert_account(data, email, profile, pending)
        data["pending"].pop(email, None)
        sess = _new_session(data, email)
        _save(data)
        return sess, acc


def finalize_login(email, profile=None):
    """Crée session + compte après un OTP déjà validé ailleurs (GoTrue)."""
    email = normalize_email(email)
    profile = profile or {}
    with _LOCK:
        data = _load()
        pending = (data.get("pending") or {}).get(email) or {}
        acc = _upsert_account(data, email, profile, pending)
        data["pending"].pop(email, None)
        sess = _new_session(data, email)
        _save(data)
        return sess, acc


def revoke_session(token):
    token = (token or "").strip()
    if not token.startswith("sk_"):
        return False
    with _LOCK:
        data = _load()
        sessions = data.get("sessions") or {}
        if token not in sessions:
            return False
        sessions.pop(token, None)
        data["sessions"] = sessions
        _save(data)
        return True


def user_from_token(token):
    token = (token or "").strip()
    if not token.startswith("sk_"):
        return None
    with _LOCK:
        data = _load()
        sess = (data.get("sessions") or {}).get(token) or {}
        if not sess or time.time() > float(sess.get("exp") or 0):
            return None
        acc = (data.get("accounts") or {}).get(normalize_email(sess.get("email") or ""))
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
    email = normalize_email(email)
    with _LOCK:
        data = _load()
        acc = (data.get("accounts") or {}).get(email)
        if not acc:
            return None
        for key in ("first_name", "last_name", "group_code", "plans", "fav_ids", "avatar_ext", "avatar_data", "avatar_rev", "plan", "entitlements"):
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
    if not uid or ext not in AVATAR_EXTS:
        return ""
    return os.path.join(AVATAR_DIR, uid + "." + ("jpg" if ext == "jpeg" else ext))


def _shown_ext(ext):
    ext = str(ext or "").strip().lower().lstrip(".")
    if ext in ("jpg", "jpeg"):
        return "jpg"
    return ext if ext in ("png", "webp") else ""


def _avatar_blob(acc):
    raw = (acc or {}).get("avatar_data") or ""
    if not raw:
        return b""
    if str(raw).startswith("data:"):
        _header, _sep, raw = str(raw).partition(",")
    try:
        return base64.b64decode(raw, validate=False)
    except (ValueError, TypeError):
        return b""


def _account_by_id(user_id):
    uid = str(user_id or "").strip()
    if not uid:
        return None
    for acc in ((_load().get("accounts") or {}).values()):
        if str((acc or {}).get("id") or "") == uid:
            return acc
    return None


def _write_avatar_cache(uid, ext, blob):
    path = avatar_path(uid, ext)
    if not path or not blob:
        return
    try:
        os.makedirs(AVATAR_DIR, exist_ok=True)
        for name in os.listdir(AVATAR_DIR):
            if name.startswith(uid + "."):
                try:
                    os.unlink(os.path.join(AVATAR_DIR, name))
                except OSError:
                    pass
        with open(path, "wb") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass


def avatar_url(acc):
    acc = acc or {}
    uid = acc.get("id") or ""
    shown = _shown_ext(acc.get("avatar_ext"))
    if not uid or not shown:
        return ""
    path = avatar_path(uid, shown)
    has_file = bool(path and os.path.isfile(path))
    if not acc.get("avatar_data") and not has_file:
        return ""
    stamp = acc.get("avatar_rev") or (int(os.path.getmtime(path)) if has_file else 1)
    return "/avatars/" + uid + "." + shown + "?v=" + str(stamp)


def save_avatar(email, blob, ext):
    email = normalize_email(email)
    ext = _shown_ext(ext)
    if ext not in ("jpg", "png", "webp"):
        raise ValueError("Format invalide. Utilise jpg, png ou webp.")
    if not blob:
        raise ValueError("Photo invalide")
    with _LOCK:
        data = _load()
        acc = (data.get("accounts") or {}).get(email)
        if not acc:
            raise ValueError("Compte introuvable")
        uid = acc.get("id") or ""
        mime = AVATAR_MIME.get(ext) or "application/octet-stream"
        acc["avatar_ext"] = ext
        acc["avatar_data"] = "data:%s;base64,%s" % (mime, base64.b64encode(blob).decode("ascii"))
        acc["avatar_rev"] = int(time.time())
        data["accounts"][email] = acc
        _save(data)
        _write_avatar_cache(uid, ext, blob)
        return avatar_url(acc)


def read_avatar(user_id, ext):
    ext = _shown_ext(ext)
    path = avatar_path(user_id, ext)
    if path and os.path.isfile(path):
        with open(path, "rb") as fh:
            blob = fh.read()
        if blob:
            return blob, AVATAR_MIME.get(ext) or "application/octet-stream"
    with _LOCK:
        acc = _account_by_id(user_id)
        blob = _avatar_blob(acc)
        stored = _shown_ext((acc or {}).get("avatar_ext"))
        if blob and stored == ext:
            _write_avatar_cache(user_id, ext, blob)
            return blob, AVATAR_MIME.get(ext) or "application/octet-stream"
    return None, ""


def delete_account(email):
    email = normalize_email(email)
    if not email:
        return False
    with _LOCK:
        data = _load()
        acc = (data.get("accounts") or {}).pop(email, None)
        (data.get("pending") or {}).pop(email, None)
        sessions = data.get("sessions") or {}
        for token, sess in list(sessions.items()):
            if normalize_email((sess or {}).get("email")) == email:
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
