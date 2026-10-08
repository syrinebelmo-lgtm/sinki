"""Événements organisateurs : stockage durable via blobstore (fichier en test)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import events  # noqa: E402

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


class EventsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SINKI_AUTH_STORE": "file"})
        self.env.start()
        events.STORE.file_path = os.path.join(self.tmp.name, "events.json")
        self.photo = patch.object(events, "PHOTO_DIR", os.path.join(self.tmp.name, "ph"))
        self.photo.start()

    def tearDown(self):
        self.photo.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_submit_review_like_comment_purge(self):
        row = events.create_event("orga@mail.com", {"name": "Concert", "description": "Live", "address": "Lyon", "photo": PNG})
        self.assertEqual(events.list_public(), [])
        self.assertEqual(len(events.list_pending()), 1)
        with self.assertRaises(ValueError):
            events.review_event(row["id"], "approve", token="faux", require_token=True)
        events.review_event(row["id"], "approve", token=row["token"], require_token=True)
        pub = events.list_public()
        self.assertTrue(pub[0]["boosted"])
        events.toggle_like(row["id"], "fan@mail.com")
        events.add_comment(row["id"], "fan@mail.com", "Fan", "Trop bien")
        self.assertEqual(events.list_public("fan@mail.com")[0]["like_count"], 1)
        events.purge_user("fan@mail.com")
        self.assertEqual(events.list_public()[0]["like_count"], 0)
        self.assertEqual(events.list_public()[0]["comments"], [])
        events.purge_user("orga@mail.com")
        self.assertEqual(events.list_public(), [])

    def test_missing_fields_refused(self):
        with self.assertRaises(ValueError):
            events.create_event("o@mail.com", {"name": "X"})


if __name__ == "__main__":
    unittest.main()
