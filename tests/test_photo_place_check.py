"""Une photo Wikimedia n’est montrée que si son nom de fichier désigne le lieu."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import serve  # noqa: E402

C = "https://commons.wikimedia.org/wiki/Special:FilePath/"


class PhotoPlaceCheckTests(unittest.TestCase):
    def check(self, name, file, address, expected):
        self.assertEqual(serve.photo_matches_place(C + file, name, address), expected, name)

    def test_real_mismatches_seen_in_lyon_are_hidden(self):
        self.check("Cinéma Lumière Fourmi", "Lyon%201er%20-%20Cin%C3%A9ma%20Lumi%C3%A8re%20Terreaux.jpg", "69008 Lyon", False)
        self.check("Théâtre Carré 30", "Lyon%201er%20-%20Mus%C3%A9e%20des%20Beaux-Arts%20-%20Jeune%20Homme.jpeg", "69001 Lyon", False)
        self.check("Ciao Nonna Gare Part-Dieu", "Gare%20de%20Lyon-Part-Dieu%2C%20galerie.jpg", "69003 Lyon", False)

    def test_same_name_elsewhere_is_hidden(self):
        self.check("Home Sweet Home", "Foster%20Elementary%20School%20in%20Sweet%20Home%2C%20Oregon.jpg", "75011 Paris", False)
        self.check("Shen Yun", "Beach%20handball%20Shen%20Yun.jpg", "Paris", False)

    def test_named_and_located_photo_is_kept(self):
        self.check("Restaurant Le Jean Moulin", "Restaurant%20Le%20Jean%20Moulin%2C%20rue%20de%20S%C3%A8ze%20(Lyon).jpg", "45 rue de Sèze, 69006 Lyon", True)

    def test_audio_file_is_never_a_photo(self):
        self.check("Magyd Cherfi Concert", "Magyd%20Cherfi%20Lyon.wav", "Lyon", False)

    def test_non_wikimedia_photos_are_untouched(self):
        self.assertTrue(serve.photo_matches_place("https://static.apidae-tourisme.com/x.jpg", "Anything", ""))


if __name__ == "__main__":
    unittest.main()
