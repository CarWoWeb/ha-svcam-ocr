"""Tests für Bildpaare, Verlauf und Verlaufsseite. Nur Platzhalter, keine echten Kennzeichen.

Aufruf: python -m unittest discover -s svcam_ocr/tests
"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from kennzeichen import reparieren  # noqa: E402
from seite import bilder_seite, texte_seite  # noqa: E402
from verlauf import Verlauf, kamera_aus_name, partner_finden  # noqa: E402

HOCH = "_kamera_eins_in_hochauflosung.jpg"
STANDARD = "_kamera_eins_in_standardauflosung.jpg"


def bild(breite=1600, hoehe=900):
    return np.full((hoehe, breite, 3), 128, dtype=np.uint8)


class Bildpaar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def datei(self, name):
        p = self.ordner / name
        p.write_bytes(b"x" * 10)
        return p

    def test_partner_kurz_danach(self):
        hoch = self.datei("20261123215220" + HOCH)
        self.datei("20261123215221" + STANDARD)
        self.assertEqual(partner_finden(hoch, 0).name, "20261123215221" + STANDARD)

    def test_partner_kurz_davor(self):
        hoch = self.datei("20261123215222" + HOCH)
        self.datei("20261123215221" + STANDARD)
        self.assertEqual(partner_finden(hoch, 0).name, "20261123215221" + STANDARD)

    def test_ueber_stundenwechsel(self):
        hoch = self.datei("20261123215958" + HOCH)
        self.datei("20261123220001" + STANDARD)
        self.assertEqual(partner_finden(hoch, 0).name, "20261123220001" + STANDARD)

    def test_andere_kamera_zaehlt_nicht(self):
        hoch = self.datei("20261123215220" + HOCH)
        self.datei("20261123215221_kamera_eins_standardauflosung.jpg")  # anderer Rest
        self.datei("20261123215221_kamera_zwei_in_standardauflosung.jpg")
        self.assertIsNone(partner_finden(hoch, 0))

    def test_naechster_gewinnt(self):
        hoch = self.datei("20261123215220" + HOCH)
        self.datei("20261123215224" + STANDARD)
        self.datei("20261123215221" + STANDARD)
        self.assertEqual(partner_finden(hoch, 0).name, "20261123215221" + STANDARD)

    def test_nur_fuer_hochauflosung(self):
        std = self.datei("20261123215221" + STANDARD)
        self.assertIsNone(partner_finden(std, 0))

    def test_zu_weit_weg(self):
        hoch = self.datei("20261123215220" + HOCH)
        self.datei("20261123215300" + STANDARD)
        self.assertIsNone(partner_finden(hoch, 0))

    def test_kamera_name(self):
        self.assertEqual(kamera_aus_name("20261123215220" + HOCH), "kamera eins")


class VerlaufTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.v = Verlauf(Path(self.tmp.name))

    def tearDown(self):
        self.v._db.close()
        self.tmp.cleanup()

    def scan(self, zeit, treffer, beschr=None):
        return self.v.speichern(f"{zeit}{HOCH}", bild(), None, treffer, beschr)

    def test_zaehlt_und_sortiert(self):
        neu = [{"text": "XXQ300", "status": "neu", "eintrag": None}]
        bek = [{"text": "XXQ300", "status": "bekannt", "eintrag": "XX-Q 300"}]
        self.assertEqual(self.scan("20261123100000", neu), {"XXQ300": 1})
        self.assertEqual(self.scan("20261123110000", bek, [["XX-Q 300", "Paket"]]), {"XXQ300": 2})
        texte = self.v.texte()
        self.assertEqual(texte[0]["anzahl"], 2)
        self.assertEqual(texte[0]["beschreibung"], "Paket")
        scans, mehr = self.v.sichtungen("XXQ300", 0)
        self.assertEqual([s["zeit"][11:16] for s in scans], ["11:00", "10:00"])
        self.assertFalse(mehr)
        # Bilder sind klein
        self.assertLess(len(self.v.bild(scans[0]["id"], True)), 60_000)

    def test_nur_whitelist_wird_nicht_gespeichert(self):
        self.assertEqual(self.scan("20261123100000", [{"text": "A1", "status": "whitelist", "eintrag": "A1"}]), {})
        self.assertEqual(self.v.sichtungen(None, 0)[0], [])

    def test_aufraeumen_nach_liste(self):
        self.scan("20261123100000", [{"text": "XXQ300", "status": "neu", "eintrag": None}])
        self.scan("20261123100100", [{"text": "XXR400", "status": "neu", "eintrag": None}])
        geloescht = self.v.aufraeumen(["XX-Q 300"], jetzt=datetime(2026, 11, 23, 12))
        self.assertEqual(geloescht, 1)
        self.assertEqual([t["schluessel"] for t in self.v.texte()], ["XXQ300"])
        self.assertEqual(len(list(self.v.bilder.glob("*.jpg"))), 2)  # ein Scan, groß und klein

    def test_leere_bilder_nach_sieben_tagen_weg(self):
        gestern = datetime.now() - timedelta(days=1)
        self.scan(gestern.strftime("%Y%m%d%H%M%S"), [])
        self.assertEqual(self.v.aufraeumen([], jetzt=gestern + timedelta(days=5)), 0)
        self.assertEqual(self.v.aufraeumen([], jetzt=gestern + timedelta(days=8)), 1)

    def test_hoechstens_50_je_text(self):
        for i in range(55):
            self.scan(f"202611231{i // 60:01d}{i % 60:02d}00",
                      [{"text": "XXQ300", "status": "bekannt", "eintrag": "XXQ300"}])
        self.assertEqual(self.v.texte()[0]["anzahl"], 50)
        self.assertEqual(len(list(self.v.bilder.glob("*_k.jpg"))), 50)

    def test_seite_maskiert_html(self):
        self.scan("20261123100000", [{"text": "XXQ300", "status": "bekannt", "eintrag": "XXQ300"}],
                  [["XXQ300", "<script>x</script>"]])
        for html in (texte_seite(self.v), bilder_seite(self.v, None, 0), bilder_seite(self.v, "XXQ300", 0)):
            self.assertNotIn("<script>x", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn('loading="lazy"', html) if "bild/" in html else None


class Link(unittest.TestCase):
    def test_link_auf_app_seite(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"HOSTNAME": "1a2b3c4d-svcam-ocr"}):
            from verlauf import verlauf_link
            self.assertEqual(verlauf_link(), "/app/1a2b3c4d_svcam_ocr")
        with mock.patch.dict(os.environ, {"HOSTNAME": "fremder-host"}):
            self.assertIsNone(verlauf_link())


class Endung(unittest.TestCase):
    def test_e_und_h_am_ende(self):
        self.assertEqual(reparieren("XXY100E"), "XXY100E")
        self.assertEqual(reparieren("XXY100H"), "XXY100H")


if __name__ == "__main__":
    unittest.main()
