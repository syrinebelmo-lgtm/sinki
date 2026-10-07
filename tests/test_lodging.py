"""Les hôtels ne sont jamais proposés comme sorties (sauf monuments)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import serve  # noqa: E402


class LodgingTests(unittest.TestCase):
    def test_hotels_excluded_monuments_kept(self):
        cases = [
            ("Hôtel Mercure Lyon", "Activités et loisirs", True),
            ("Grand Hôtel du Lac", "Restaurants et cafés", True),
            ("Auberge de jeunesse HI", "Activités et loisirs", True),
            ("Hôtel de Ville de Lyon", "Musées et culture", False),
            ("Hôtel-Dieu", "Lieux gratuits et balades", False),
            ("Hôtel de la Marine", "Lieux gratuits et balades", False),
            ("Auberge du Pont", "Restaurants et cafés", False),
        ]
        for name, cat, lodging in cases:
            self.assertEqual(serve.is_lodging({"name": name, "category": cat}), lodging, name)


if __name__ == "__main__":
    unittest.main()
