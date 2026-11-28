"""Tests für Kennzeichen-Reparatur und Abgleich. Nur Platzhalter, keine echten Kennzeichen.

Aufruf: python -m unittest discover -s svcam_ocr/tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from abgleich import abgleichen, abstand, finden  # noqa: E402
from kennzeichen import Abstimmung, ist_kandidat, ist_logo_zahl, normalisieren, reparieren  # noqa: E402


class Kennzeichen(unittest.TestCase):
    def test_normalisieren(self):
        self.assertEqual(normalisieren("xx-yy 100"), "XXYY100")
        self.assertEqual(normalisieren("Ö·XY 1"), "ÖXY1")

    def test_gueltig_bleibt(self):
        self.assertEqual(reparieren("XXYY100"), "XXYY100")
        self.assertEqual(reparieren("XY1"), "XY1")
        self.assertEqual(reparieren("XXY100E"), "XXY100E")

    def test_ziffern_im_buchstabenblock(self):
        # 1 statt I in der Mitte, O statt 0 hinten
        self.assertEqual(reparieren("X1Y100"), "XIY100")
        self.assertEqual(reparieren("XX1100"), "XX1100")  # gültig: X X 1100
        self.assertEqual(reparieren("XXY1O0"), "XXY100")

    def test_wenigste_ersetzungen(self):
        # Ein D hinten in der Erkennung darf nicht zur Ziffer werden
        self.assertEqual(reparieren("XXYD100"), "XXYD100")

    def test_ungueltig(self):
        self.assertIsNone(reparieren("XYZ"))
        self.assertIsNone(reparieren("1234"))
        self.assertIsNone(reparieren("XXYYZZ100"))  # zu viele Buchstaben

    def test_kandidat(self):
        self.assertTrue(ist_kandidat("XXYY100"))
        self.assertFalse(ist_kandidat("DHL"))
        self.assertFalse(ist_kandidat("DEUTSCHEPOST"))

    def test_abstimmung_eu_feld(self):
        a = Abstimmung()
        a.lesung("BXX YY 100", 0.95)   # EU-Feld als B gelesen
        a.lesung("XX YY 100", 0.9)     # Ausschnitt ohne EU-Feld
        a.lesung("XX YY 100", 0.9)
        self.assertEqual(a.ergebnis()[0], "XXYY100")

    def test_ortskennung_bonus(self):
        a = Abstimmung(ortskennungen=frozenset({"XX"}))
        a.lesung("BXXY100", 0.9)
        self.assertEqual(a.ergebnis()[0], "XXY100")

    def test_plakette_als_buchstabe(self):
        # Plakette zwischen Ortskennung und Erkennung als "Q" gelesen: XX + QYY ist unmöglich
        a = Abstimmung(ortskennungen=frozenset({"XX"}))
        a.lesung("XXQYY100", 0.95, eu_feld=False)
        a.lesung("XXQYY100", 0.9, eu_feld=False)
        a.lesung("XXYY100", 0.8, eu_feld=False)
        self.assertEqual(a.ergebnis()[0], "XXYY100")

    def test_eu_feld_sicher_abgeschnitten(self):
        a = Abstimmung()
        a.lesung("XXY100", 0.9, eu_feld=False)
        self.assertEqual(list(a.stimmen), ["XXY100"])


class Abgleich(unittest.TestCase):
    def test_abstand(self):
        self.assertEqual(abstand("XXYY100", "XXYY100", 1), 0)
        self.assertEqual(abstand("XXYY100", "XXYY106", 1), 1)
        self.assertEqual(abstand("XXYY100", "XXY100", 1), 1)
        self.assertGreater(abstand("XXYY100", "AB12", 1), 1)

    def test_finden_unscharf_nur_bei_langen(self):
        self.assertEqual(finden("XXYY106", ["XX-YY 100"], 1), "XX-YY 100")
        self.assertIsNone(finden("DPD", ["DHL"], 1))        # kurz: nur exakt
        self.assertEqual(finden("DHL", ["dhl"], 1), "dhl")
        self.assertEqual(finden("DEUTSCHEPPOST", ["Deutsche Post"], 1), "Deutsche Post")

    def test_abgleichen(self):
        erg = {
            "kennzeichen": [{"kennzeichen": "XXYY100"}, {"kennzeichen": "XXZ200"}],
            "texte": [
                {"norm": "XXYY100", "kennzeichen": {}},
                {"norm": "DHL"},
                {"norm": "7"},
                {"norm": "NEUFIRMA"},
            ],
        }
        t = abgleichen(erg, bekannt=["DHL", "XX YY 100"], whitelist=["XX Z 200"],
                       max_abstand=1, min_textlaenge=3)
        status = {x["text"]: x["status"] for x in t}
        self.assertEqual(status, {"XXYY100": "bekannt", "XXZ200": "whitelist",
                                  "DHL": "bekannt", "NEUFIRMA": "neu"})

    def test_doppelte_lesung_ein_eintrag(self):
        erg = {"kennzeichen": [{"kennzeichen": "XXYY100"}, {"kennzeichen": "XXYY106"}], "texte": []}
        t = abgleichen(erg, ["XXYY100"], [], 1, 3)
        self.assertEqual(len(t), 1)


def _box(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


class LogoZahl(unittest.TestCase):
    KASTEN = [960, 395, 1000, 428, 0.9]  # Kennzeichen, 40 x 33

    def test_logo_ueber_kennzeichen(self):
        self.assertTrue(ist_logo_zahl("1395", _box(978, 364, 1000, 381), [self.KASTEN]))

    def test_bruchstueck_im_kennzeichen(self):
        self.assertTrue(ist_logo_zahl("123", _box(980, 400, 998, 420), [self.KASTEN]))

    def test_hausnummer_weiter_weg_bleibt(self):
        self.assertFalse(ist_logo_zahl("12", _box(1300, 300, 1330, 330), [self.KASTEN]))
        self.assertFalse(ist_logo_zahl("12", _box(970, 200, 990, 220), [self.KASTEN]))

    def test_nur_kurze_reine_zahlen(self):
        box = _box(978, 364, 1000, 381)
        self.assertFalse(ist_logo_zahl("13955", box, [self.KASTEN]))
        self.assertFalse(ist_logo_zahl("Q4", box, [self.KASTEN]))

    def test_ohne_kennzeichen_nichts_filtern(self):
        self.assertFalse(ist_logo_zahl("1395", _box(978, 364, 1000, 381), []))

    def test_abgleich_ueberspringt_logo(self):
        erg = {"kennzeichen": [], "texte": [{"text": "1395", "norm": "1395", "logo": True}]}
        self.assertEqual(abgleichen(erg, [], [], 1, 3), [])


if __name__ == "__main__":
    unittest.main()
