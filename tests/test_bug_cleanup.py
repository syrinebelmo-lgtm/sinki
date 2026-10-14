"""Régressions du nettoyage de bugs : paramètres invalides, chat de groupe,
récit Wikipédia d'un lieu, connexion à un compte existant. Aucun appel réseau."""
import copy
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import serve  # noqa: E402
import local_auth  # noqa: E402


class SearchParamTests(unittest.TestCase):
    def parse(self, **query):
        return serve.outing_search_params({k: [v] for k, v in query.items()})

    def test_bad_numbers_fall_back_instead_of_crashing(self):
        lat, lon, radius, budget = self.parse(lat="45.76", lon="4.83", budget="abc", radius_km="xyz")
        self.assertEqual((lat, lon, radius, budget), (45.76, 4.83, 15.0, None))

    def test_infinite_or_negative_radius_is_bounded(self):
        # radius_km=inf used to return outings from Birmingham for a search in Lyon.
        self.assertEqual(self.parse(lat="45", lon="4", radius_km="inf")[2], 15.0)
        self.assertEqual(self.parse(lat="45", lon="4", radius_km="-5")[2], 15.0)
        self.assertEqual(self.parse(lat="45", lon="4", radius_km="5000")[2], 300.0)

    def test_nan_or_out_of_range_position_is_ignored(self):
        self.assertEqual(self.parse(lat="nan", lon="4")[:2], (None, None))
        self.assertEqual(self.parse(lat="95", lon="4")[:2], (None, None))
        self.assertEqual(self.parse(lat="45", lon="")[:2], (None, None))

    def test_negative_budget_means_free(self):
        self.assertEqual(self.parse(budget="-3")[3], 0.0)


class ApiRouteTests(unittest.TestCase):
    """Real HTTP round trips against Handler, with every outside call mocked."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, method, path, body=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {"Content-Type": "application/json"} if data is not None else {}
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        text = resp.read().decode("utf-8")
        conn.close()
        return resp.status, text

    def test_broken_json_gets_a_readable_error(self):
        status, text = self.call("POST", "/api/auth/send", raw=b"{oops")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(text)["error"], "Requête invalide")

    def test_json_list_body_is_not_a_server_error(self):
        with patch.object(serve, "create_group", return_value={"share_code": "ABCDEF"}) as create:
            status, _text = self.call("POST", "/api/groups", body=[1, 2])
        self.assertEqual(status, 200)
        create.assert_called_once_with("Groupe Sinki")

    def test_weather_rejects_bad_position_without_calling_open_meteo(self):
        with patch.object(serve.urllib.request, "urlopen") as urlopen:
            status, text = self.call("GET", "/api/weather?lat=abc&lon=def")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(text)["error"], "Position invalide")
        urlopen.assert_not_called()

    def test_weather_outage_is_a_502_not_a_client_error(self):
        with patch.object(serve.urllib.request, "urlopen", side_effect=OSError("down")):
            status, _text = self.call("GET", "/api/weather?lat=45.7&lon=4.8")
        self.assertEqual(status, 502)

    def test_outings_with_text_budget_still_search(self):
        serve.OUTINGS_CACHE.clear()
        with patch.object(serve, "supabase_outings", return_value=[]) as outings, \
             patch.object(serve, "safe_select", return_value=[]):
            status, text = self.call("GET", "/api/outings?lat=45.76&lon=4.83&budget=abc&radius_km=inf")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text), [])
        self.assertTrue(outings.called)

    def test_bad_moderation_link_shows_a_page(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with patch.dict(os.environ, {"SINKI_AUTH_STORE": "file"}), \
             patch.object(serve.event_store.STORE, "file_path", os.path.join(tmp.name, "events.json")):
            status, text = self.call("GET", "/api/events/review?id=nope&token=t&action=approve")
        self.assertEqual(status, 400)
        self.assertIn("Lien invalide", text)


class GroupChatTests(unittest.TestCase):
    def test_shared_outing_card_is_retyped(self):
        card = serve.compact_outing({
            "id": "o1", "name": "Musée", "price_min": "12", "price_max": True,
            "currency": "<img src=x onerror=alert(1)>", "photo_url": "javascript:alert(1)",
            "category": {"x": 1},
        })
        self.assertEqual(card["currency"], None)
        self.assertEqual(card["photo_url"], None)
        self.assertEqual(card["price_min"], 12)
        self.assertEqual(card["price_max"], None)
        self.assertEqual(card["category"], None)
        good = serve.compact_outing({"id": "o2", "name": "Parc", "currency": "chf", "photo_url": "https://upload.wikimedia.org/a.jpg"})
        self.assertEqual(good["currency"], "CHF")
        self.assertEqual(good["photo_url"], "https://upload.wikimedia.org/a.jpg")

    def test_non_text_fields_do_not_crash(self):
        group = {"id": "g", "share_code": "QATYPE", "origin_label": "T", "status": "open", "updated_at": "s0", "filters": {"chat": []}}

        def select(path):
            return [copy.deepcopy(group)] if "QATYPE" in path else []

        def request(method, path, body=None):
            group["filters"] = copy.deepcopy(body["filters"])
            return [copy.deepcopy(group)]

        with patch.object(serve, "supabase_select", side_effect=select), patch.object(serve, "supabase_request", side_effect=request):
            serve.post_group_message("QATYPE", 42, 1234)
        self.assertEqual(group["filters"]["chat"][0]["text"], "1234")
        self.assertEqual(group["filters"]["chat"][0]["name"], "42")

    def test_report_retry_after_concurrent_write_still_hides_the_message(self):
        group = {"id": "g3", "share_code": "QARETRY", "origin_label": "T", "status": "open", "updated_at": "s0",
                 "filters": {"chat": [{"id": "m1", "name": "A", "text": "ok"}, {"id": "m2", "name": "B", "text": "insulte"}]}}
        state = {"race": True}

        def select(path):
            return [copy.deepcopy(group)] if "QARETRY" in path else []

        def request(method, path, body=None):
            if state["race"]:
                state["race"] = False
                group["filters"]["chat"].append({"id": "m3", "name": "C", "text": "salut"})
                group["updated_at"] = "s-other"
            if "updated_at=eq." + group["updated_at"] not in path:
                return []
            group["filters"] = copy.deepcopy(body["filters"])
            group["updated_at"] = "s1"
            return [copy.deepcopy(group)]

        with patch.object(serve, "supabase_select", side_effect=select), patch.object(serve, "supabase_request", side_effect=request), \
             patch.object(serve, "has_resend_key", return_value=False), patch.object(serve.time, "sleep"):
            self.assertTrue(serve.report_group_message({"code": "QARETRY", "message_id": "m2"})["ok"])
        self.assertEqual([m["id"] for m in group["filters"]["chat"]], ["m1", "m3"])

    def test_report_of_unknown_message_writes_nothing(self):
        group = {"id": "g4", "share_code": "QANONE", "origin_label": "T", "status": "open", "filters": {"chat": []}}
        with patch.object(serve, "supabase_select", return_value=[copy.deepcopy(group)]), \
             patch.object(serve, "supabase_request") as write:
            with self.assertRaises(ValueError):
                serve.report_group_message({"code": "QANONE", "message_id": "zz"})
        write.assert_not_called()


class PlaceStoryTests(unittest.TestCase):
    def setUp(self):
        serve.PLACE_STORY_CACHE.clear()

    def test_name_lookup_must_be_near_the_place(self):
        toy = {"type": "standard", "extract": "Le bilboquet est un jeu d'adresse composé d'une boule percée et d'un bâton.",
               "coordinates": {"lat": 43.0, "lon": 1.0}}
        with patch.object(serve, "_http_json", return_value=toy):
            self.assertEqual(serve.wiki_summary("Le Bilboquet", "fr", near=(48.85, 2.33)), "")
            self.assertTrue(serve.wiki_summary("Le Bilboquet", "fr", near=(43.001, 1.001)))
        no_geo = dict(toy)
        no_geo.pop("coordinates")
        with patch.object(serve, "_http_json", return_value=no_geo):
            self.assertEqual(serve.wiki_summary("Le Bilboquet", "fr", near=(48.85, 2.33)), "")

    def test_closest_unrelated_page_is_not_the_story(self):
        street = {"type": "standard", "extract": "La rue de Marseille est une rue du quartier de la Guillotière à Lyon, en France.",
                  "coordinates": {"lat": 45.7503, "lon": 4.8388}}

        def fake(url, timeout=8):
            if "geosearch" in url:
                return {"query": {"geosearch": [{"title": "Rue de Marseille", "dist": 20}]}}
            if "Rue_de_Marseille" in url:
                return street
            return {}

        with patch.object(serve, "_http_json", side_effect=fake), patch.object(serve, "wiki_langlink", return_value=""):
            story = serve.place_story({"name": ["Club Exemple"], "lat": ["45.7503"], "lon": ["4.8388"]})
        self.assertEqual(story["story"], "")

    def test_matching_nearby_page_is_kept(self):
        page = {"type": "standard", "extract": "Le musée des Confluences est un musée d'histoire naturelle situé à Lyon.",
                "coordinates": {"lat": 45.7337, "lon": 4.8187}}

        def fake(url, timeout=8):
            if "geosearch" in url:
                return {"query": {"geosearch": [{"title": "Musée des Confluences", "dist": 15}]}}
            return page

        with patch.object(serve, "_http_json", side_effect=fake), patch.object(serve, "wiki_langlink", return_value=""):
            story = serve.place_story({"name": ["Musée des Confluences"], "lat": ["45.7337"], "lon": ["4.8187"]})
        self.assertIn("musée des Confluences", story["story"])

    def test_no_position_means_no_guess(self):
        with patch.object(serve, "_http_json") as fetch:
            story = serve.place_story({"name": ["foo"], "lat": ["abc"]})
        self.assertEqual(story["story"], "")
        fetch.assert_not_called()


class ExistingAccountLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SINKI_AUTH_STORE": "file"})
        self.env.start()
        self.paths = patch.multiple(local_auth, PATH=os.path.join(self.tmp.name, "a.json"), BACKUP=os.path.join(self.tmp.name, "b.json"), DATA_DIR=self.tmp.name)
        self.paths.start()
        local_auth._mem = None

    def tearDown(self):
        self.paths.stop()
        self.env.stop()
        self.tmp.cleanup()
        local_auth._mem = None

    def signup(self, email, first, nick):
        code = local_auth.request_code(email, {"first_name": first, "last_name": "X", "nick": nick})
        return local_auth.verify_code(email, code, {"first_name": first, "last_name": "X", "nick": nick})

    def test_login_with_leftover_signup_form_keeps_the_account(self):
        self.signup("ana@mail.com", "Ana", "ana")
        self.signup("bob@mail.com", "Bob", "bob")
        # Same phone: Ana's sign-up form is still filled when Bob logs in.
        stale = {"first_name": "Ana", "last_name": "X", "nick": "ana"}
        code = local_auth.request_code("bob@mail.com", stale)
        _sess, acc = local_auth.verify_code("bob@mail.com", code, stale)
        self.assertEqual((acc["first_name"], acc["nick"]), ("Bob", "bob"))

    def test_send_code_for_existing_account_ignores_taken_pseudo(self):
        self.signup("ana@mail.com", "Ana", "ana")
        self.signup("bob@mail.com", "Bob", "bob")
        with patch.object(serve, "has_resend_key", return_value=False), \
             patch.object(serve, "dev_mail_console", return_value=True), \
             patch.object(serve, "gotrue_user_exists", return_value=None):
            result = serve.send_login_code({"email": "bob@mail.com", "mode": "login", "nick": "ana"})
        self.assertTrue(result["ok"])

    def test_new_account_still_cannot_take_a_used_pseudo(self):
        self.signup("ana@mail.com", "Ana", "ana")
        with self.assertRaises(ValueError):
            local_auth.request_code("new@mail.com", {"nick": "Ana"})


if __name__ == "__main__":
    unittest.main()
