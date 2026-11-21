"""Tests für Kennzeichen-Reparatur und Abgleich. Nur Platzhalter, keine echten Kennzeichen.

Aufruf: python -m unittest discover -s svcam_ocr/tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from abgleich import abgleichen, abstand, finden  # noqa: E402
from kennzeichen import Abstimmung, ist_kandidat, normalisieren, reparieren  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
