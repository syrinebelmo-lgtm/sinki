import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import serve  # noqa: E402


class GroupFlowTests(unittest.TestCase):
    def test_message_poll_vote_and_rejoin_keep_history(self):
        group = {
            "id": "test-group-id",
            "share_code": "QATEST",
            "origin_label": "Test",
            "filters": {"chat": []},
            "status": "open",
        }

        def select(path):
            return [copy.deepcopy(group)] if "share_code=eq.QATEST" in path else []

        def request(method, path, body=None):
            self.assertEqual(method, "PATCH")
            group["updated_at"] = str(len(group["filters"].get("chat") or []))
            self.assertIn("groups?id=eq.test-group-id", path)
            group["filters"] = copy.deepcopy(body["filters"])
            return [copy.deepcopy(group)]

        outings = [
            {"id": "one", "name": "Musée", "price_min": 10},
            {"id": "two", "name": "Parc", "price_min": 0},
        ]
        with patch.object(serve, "supabase_select", side_effect=select), patch.object(
            serve, "supabase_request", side_effect=request
        ):
            serve.post_group_message("QATEST", "A", "On y va ?", outings[0])
            self.assertEqual(serve.get_group("QATEST")["filters"]["chat"][0]["outing"]["id"], "one")
            serve.set_group_poll("QATEST", "A", outings)
            serve.vote_group("QATEST", "B", "voter-b", "two")
            rejoined = serve.get_group("QATEST")

        self.assertEqual(len(rejoined["filters"]["chat"]), 2)
        self.assertEqual(rejoined["filters"]["votes"]["voter-b"]["outing_id"], "two")
        self.assertEqual([o["id"] for o in rejoined["filters"]["poll"]["options"]], ["one", "two"])


class GroupConcurrencyTests(unittest.TestCase):
    def test_simultaneous_messages_are_both_kept(self):
        group = {"id": "g1", "share_code": "QACONC", "origin_label": "T", "filters": {"chat": []}, "status": "open", "updated_at": "s0"}
        state = {"n": 0, "race": True}

        def select(path):
            return [copy.deepcopy(group)] if "QACONC" in path else []

        def request(method, path, body=None):
            if state["race"]:
                # A friend's message lands between our read and our write.
                state["race"] = False
                group["filters"]["chat"].append({"id": "friend", "name": "B", "text": "moi aussi"})
                group["updated_at"] = "s-friend"
            if "updated_at=eq." + group["updated_at"] not in path:
                return []
            state["n"] += 1
            group["filters"] = copy.deepcopy(body["filters"])
            group["updated_at"] = "s%d" % state["n"]
            return [copy.deepcopy(group)]

        with patch.object(serve, "supabase_select", side_effect=select), patch.object(serve, "supabase_request", side_effect=request):
            serve.post_group_message("QACONC", "A", "on y va ?")
        texts = [m["text"] for m in group["filters"]["chat"]]
        self.assertEqual(texts, ["moi aussi", "on y va ?"])

    def test_empty_message_is_refused(self):
        with self.assertRaises(ValueError):
            serve.post_group_message("QACONC", "A", "   ")


if __name__ == "__main__":
    unittest.main()
