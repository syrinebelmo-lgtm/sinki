import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import commons_photos
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import serve


class PhotoMatchingTests(unittest.TestCase):
    def test_existing_bus_stop_photo_is_hidden_for_unrelated_activity(self):
        outing = {"name": "Fun Escalade Climb Up Confluence", "category": "Activités et loisirs",
                  "photo_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Bus_stop_Confluence.jpg"}
        serve.qc_outing(outing)
        self.assertIsNone(outing["photo_url"])

    def test_nearby_bus_stop_is_not_used_as_a_place_photo(self):
        places = {"query": {"geosearch": [
            {"title": "File:Bus stop Confluence.jpg"},
            {"title": "File:Climb Up Confluence Lyon.jpg"},
        ]}}
        with patch.object(commons_photos, "_api", return_value=places), \
             patch.object(commons_photos, "file_if_free", side_effect=lambda title, _: {"url": title}):
            image = commons_photos.commons_geo_photo(45.74, 4.82, "Fun Escalade Climb Up Confluence", {}, True)
        self.assertEqual(image["url"], "File:Climb Up Confluence Lyon.jpg")

    def test_nearby_unrelated_photo_is_left_blank_and_cache_is_place_specific(self):
        places = {"query": {"geosearch": [{"title": "File:Bus stop Confluence.jpg"}]}}
        cache = {}
        with patch.object(commons_photos, "_api", return_value=places), \
             patch.object(commons_photos, "file_if_free", side_effect=lambda title, _: {"url": title}):
            self.assertIsNone(commons_photos.commons_geo_photo(45.74, 4.82, "Climb Up Confluence", cache))
            self.assertEqual(
                commons_photos.commons_geo_photo(45.74, 4.82, "Bus stop Confluence", cache)["url"],
                "File:Bus stop Confluence.jpg",
            )


if __name__ == "__main__":
    unittest.main()
