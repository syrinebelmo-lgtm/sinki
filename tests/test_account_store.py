"""Store de comptes partagé : écritures concurrentes, pannes Supabase, suppression."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import local_auth  # noqa: E402


class FakeGroups:
    """Mini PostgREST for the groups table, with updated_at compare-and-swap."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.lock = threading.Lock()
        self.tick = 0
        self.fail_reads = False

    def _stamp(self):
        self.tick += 1
        return "2026-10-07T00:00:%02d.%06d+00:00" % (self.tick // 1000000, self.tick % 1000000)

    def request(self, method, path, body=None, extra=None):
        from urllib.parse import unquote
        with self.lock:
            query = path.split("?", 1)[1] if "?" in path else ""
            q = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            def match(row):
                for key in ("origin_label", "share_code", "id", "updated_at"):
                    if key in q and key != "select":
                        want = unquote(q[key])
                        if want == "is.null":
                            if row.get(key) is not None:
                                return False
                        elif str(row.get(key)) != want.split(".", 1)[1]:
                            return False
                return True
            if method == "GET":
                if self.fail_reads:
                    return 503, b'{"message":"down"}'
                return 200, json.dumps([r for r in self.rows if match(r)]).encode()
            if method == "PATCH":
                hit = [r for r in self.rows if match(r)]
                for row in hit:
                    row.update(body)
                    row["updated_at"] = self._stamp()
                return 200, json.dumps(hit).encode()
            if method == "POST":
                row = dict(body, id=str(len(self.rows) + 1), updated_at=self._stamp())
                self.rows.append(row)
                return 201, json.dumps([row]).encode()
        return 400, b"{}"


class AccountStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_ROLE": "k", "SINKI_AUTH_STORE": ""})
        self.env.start()
        self.paths = patch.multiple(local_auth, PATH=os.path.join(self.tmp.name, "a.json"), BACKUP=os.path.join(self.tmp.name, "b.json"), DATA_DIR=self.tmp.name)
        self.paths.start()
        local_auth._mem = None
        local_auth._group_id = ""
        local_auth._remote_stamp = None
        local_auth._bootstrapped = False
        self.fake = FakeGroups()
        self.req = patch.object(local_auth, "_sb_request", side_effect=self.fake.request)
        self.req.start()

    def tearDown(self):
        self.req.stop()
        self.paths.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_code_then_login_round_trip(self):
        code = local_auth.request_code("Ana@Mail.com", {"nick": "ana"})
        sess, acc = local_auth.verify_code("ana@mail.com", code)
        self.assertTrue(sess.startswith("sk_"))
        self.assertEqual(local_auth.user_from_token(sess)["email"], "ana@mail.com")

    def test_concurrent_writes_do_not_lose_codes(self):
        emails = ["u%d@mail.com" % i for i in range(12)]
        codes = {}
        def ask(e):
            codes[e] = local_auth.request_code(e)
        threads = [threading.Thread(target=ask, args=(e,)) for e in emails]
        # Bypass the in-process lock to simulate two server processes writing at once.
        with patch.object(local_auth, "_LOCK", threading.RLock()):
            [t.start() for t in threads]
            [t.join() for t in threads]
        local_auth._mem = None
        for e in emails:
            self.assertIsNotNone(local_auth.verify_code(e, codes[e]), e)

    def test_stale_writer_retries_instead_of_overwriting(self):
        local_auth.request_code("a@mail.com")
        stale = local_auth._remote_stamp
        # Another process writes in between.
        self.fake.rows[0]["filters"]["pending"]["b@mail.com"] = {"code_hash": "x", "exp": 9e12, "via": "local"}
        self.fake.rows[0]["updated_at"] = "other"
        local_auth._remote_stamp = stale
        local_auth.request_code("c@mail.com")
        pending = self.fake.rows[0]["filters"]["pending"]
        self.assertIn("b@mail.com", pending)
        self.assertIn("c@mail.com", pending)

    def test_supabase_error_is_not_an_empty_store(self):
        local_auth.request_code("a@mail.com")
        self.fake.fail_reads = True
        local_auth._mem = None
        local_auth._group_id = ""
        with self.assertRaises(local_auth.StoreUnavailable):
            local_auth.email_has_account("a@mail.com")
        self.assertEqual(len(self.fake.rows), 1, "no second auth row may be created")

    def test_bootstrap_never_reimports_deleted_accounts(self):
        code = local_auth.request_code("gone@mail.com")
        local_auth.verify_code("gone@mail.com", code)
        # A stale local cache still lists the account...
        with open(local_auth.PATH, "w") as fh:
            json.dump({"accounts": {"gone@mail.com": {"id": "1"}, "other@mail.com": {"id": "2"}}}, fh)
        local_auth.delete_account("gone@mail.com")
        local_auth._bootstrapped = False
        local_auth._mem = None
        local_auth.bootstrap()
        self.assertFalse(local_auth.email_has_account("gone@mail.com"))
        self.assertFalse(local_auth.email_has_account("other@mail.com"))

    def test_delete_removes_sessions_and_pending(self):
        code = local_auth.request_code("d@mail.com")
        sess, _acc = local_auth.verify_code("d@mail.com", code)
        local_auth.request_code("d@mail.com")
        local_auth.delete_account("d@mail.com")
        self.assertIsNone(local_auth.user_from_token(sess))
        self.assertEqual(local_auth.pending_via("d@mail.com"), "")

    def test_wrong_code_five_times_burns_it(self):
        code = local_auth.request_code("e@mail.com")
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(local_auth.MAX_VERIFY_TRIES):
            self.assertIsNone(local_auth.verify_code("e@mail.com", wrong))
        self.assertIsNone(local_auth.verify_code("e@mail.com", code))


if __name__ == "__main__":
    unittest.main()
