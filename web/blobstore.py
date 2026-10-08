# -*- coding: utf-8 -*-
"""Petit store JSON durable : une ligne réservée de la table groups (Supabase),
écrite en compare-and-swap sur updated_at, ou un fichier local en dev/tests.

Render efface son disque à chaque redémarrage : tout ce qui doit survivre
(événements organisateurs…) passe par ici. Même principe que local_auth.
"""

import copy
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


class StoreError(RuntimeError):
    pass


def supabase_conf():
    if (os.environ.get("SINKI_AUTH_STORE") or "").strip().lower() == "file":
        return "", ""
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    parts = (os.environ.get("SUPABASE_SERVICE_ROLE") or "").strip().split()
    key = parts[0] if parts else ""
    return (url, key) if url and key else ("", "")


def request(method, path, body=None, raw=None, content_type="application/json", timeout=20):
    url, key = supabase_conf()
    headers = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": content_type}
    if path.startswith("/rest/"):
        headers["Prefer"] = "return=representation"
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode("utf-8"))
    req = urllib.request.Request(url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, OSError) as exc:
        raise StoreError("%s %s: %s" % (method, path.split("?")[0], type(exc).__name__))


class BlobStore:
    def __init__(self, label, file_path, empty):
        self.label = label
        self.file_path = file_path
        self.empty = empty
        self.lock = threading.RLock()
        self.row_id = ""
        self.stamp = None

    # -- remote ------------------------------------------------------------
    def _get(self):
        status, raw = request(
            "GET",
            "/rest/v1/groups?origin_label=eq." + urllib.parse.quote(self.label) + "&select=id,filters,updated_at&order=created_at.asc",
        )
        if status >= 400:
            raise StoreError("read %s: HTTP %s" % (self.label, status))
        rows = json.loads(raw or b"[]")
        if not rows:
            self.row_id, self.stamp = "", None
            return self.empty()
        self.row_id, self.stamp = str(rows[0]["id"]), rows[0].get("updated_at")
        data = (rows[0].get("filters") or {}).get("data")
        return data if isinstance(data, dict) else self.empty()

    def _put(self, data):
        now = datetime.now(timezone.utc).isoformat()
        filters = {"v": 1, "data": data}
        if self.row_id:
            guard = ("&updated_at=eq." + urllib.parse.quote(self.stamp)) if self.stamp else "&updated_at=is.null"
            status, raw = request(
                "PATCH",
                "/rest/v1/groups?id=eq." + urllib.parse.quote(self.row_id) + guard,
                {"filters": filters, "updated_at": now},
            )
            if status >= 400:
                raise StoreError("write %s: HTTP %s" % (self.label, status))
            rows = json.loads(raw or b"[]")
            if not rows:
                return False
            self.stamp = rows[0].get("updated_at")
            return True
        status, raw = request("POST", "/rest/v1/groups", {
            # Long random share code: the row can never be opened as a friends' group.
            "share_code": "SX" + secrets.token_hex(13).upper(),
            "origin_label": self.label,
            "participant_count": 1,
            "filters": filters,
            "candidate_outing_ids": [],
            "status": "open",
            "updated_at": now,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat(),
        })
        if status not in (200, 201):
            raise StoreError("create %s: HTTP %s" % (self.label, status))
        rows = json.loads(raw or b"[]")
        if rows:
            self.row_id, self.stamp = str(rows[0]["id"]), rows[0].get("updated_at")
        return True

    # -- file (dev / tests) ---------------------------------------------------
    def _read_file(self):
        try:
            with open(self.file_path, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else self.empty()
        except (OSError, ValueError):
            return self.empty()

    def _write_file(self, data):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        tmp = self.file_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.file_path)

    # -- public -------------------------------------------------------------
    def load(self):
        with self.lock:
            return self._get() if supabase_conf()[0] else self._read_file()

    def mutate(self, fn):
        """fn(data) -> result; data is saved afterwards, retried on conflict."""
        with self.lock:
            for attempt in range(6):
                data = copy.deepcopy(self.load())
                result = fn(data)
                if not supabase_conf()[0]:
                    self._write_file(data)
                    return result
                if self._put(data):
                    return result
                time.sleep(0.05 * (attempt + 1))
            raise StoreError("%s: too many concurrent writes" % self.label)


# -- Supabase Storage (photos) ------------------------------------------------
_buckets_ready = set()


def ensure_bucket(name):
    if name in _buckets_ready:
        return
    status, _raw = request("POST", "/storage/v1/bucket", {"id": name, "name": name, "public": True})
    # 200 created; 400/409 when it already exists.
    if status not in (200, 201, 400, 409):
        raise StoreError("bucket %s: HTTP %s" % (name, status))
    _buckets_ready.add(name)


def upload_public(bucket, path, blob, mime):
    """Upload (or replace) a public file and return its public URL."""
    ensure_bucket(bucket)
    url, _key = supabase_conf()
    status, raw = request(
        "POST", "/storage/v1/object/" + bucket + "/" + path, raw=blob, content_type=mime,
    )
    if status in (400, 409):
        status, raw = request("PUT", "/storage/v1/object/" + bucket + "/" + path, raw=blob, content_type=mime)
    if status >= 400:
        raise StoreError("upload %s/%s: HTTP %s" % (bucket, path, status))
    return url + "/storage/v1/object/public/" + bucket + "/" + path


def delete_public(bucket, paths):
    if not paths or not supabase_conf()[0]:
        return
    request("DELETE", "/storage/v1/object/" + bucket, {"prefixes": list(paths)})
