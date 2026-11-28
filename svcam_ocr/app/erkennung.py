"""Texterkennung auf einem Bild: alle Texte plus Kennzeichen.

Kennzeichen kommen ab 0.3.0 aus zwei spezialisierten Modellen (beide MIT, ONNX,
beim Bauen ins Image geladen):
  - open-image-models YOLOv9 findet Kennzeichen, auch kleine und nachts.
    Findet es im ganzen Bild nichts, sucht es in vier überlappenden Vierteln.
  - fast-plate-ocr liest jeden Fund mit drei verschieden großen Rändern, die
    Lesungen stimmen nach Konfidenz ab, deutscher Aufbau wird geprüft.
RapidOCR liest weiter alle übrigen Texte (Firmennamen). RapidOCR-Texte, die
einem gefundenen Kennzeichen entsprechen, werden diesem zugeordnet. Findet der
Detektor ein Kennzeichen nicht, bleibt die bisherige RapidOCR-Abstimmung als Rückfall.
"""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np
from rapidocr import RapidOCR

from abgleich import abstand
from kennzeichen import Abstimmung, ist_kandidat, ist_logo_zahl, normalisieren, reparieren

DETEKTOR = "yolo-v9-s-608-license-plate-end2end"
LESER = "cct-xs-v2-global-model"
DETEKTOR_SCHWELLE = 0.25
# Lesungen darunter sind meist zu kleine oder unscharfe Kennzeichen: verwerfen statt Unsinn melden
MIN_SICHERHEIT = 0.4
# Ränder um den gefundenen Kasten (Anteil von Breite bzw. Höhe je Seite)
RAENDER = ((0.04, 0.10), (0.10, 0.25), (0.20, 0.45))

# Anteil, der links vom Kennzeichen-Ausschnitt abgeschnitten wird (blaues EU-Feld),
# falls das blaue Feld nicht zu finden ist (nachts, Graubild)
BESCHNITTE_LINKS = (0.0, 0.06, 0.10, 0.14)
# Gewicht einer Lesung, bei der das gefundene EU-Feld genau abgeschnitten wurde
GEWICHT_EU_SCHNITT = 1.0


def eu_feld_ende(aus: np.ndarray) -> int | None:
    """Spalte, an der das blaue EU-Feld links im Ausschnitt endet, sonst None."""
    h, w = aus.shape[:2]
    if w < 20 or h < 8:
        return None
    hsv = cv2.cvtColor(aus, cv2.COLOR_BGR2HSV)
    blau = (hsv[..., 0] > 95) & (hsv[..., 0] < 135) & (hsv[..., 1] > 80) & (hsv[..., 2] > 40)
    anteil = blau.mean(axis=0)
    # Das Feld muss am linken Rand (in den ersten 8 %) beginnen und ist höchstens ~25 % breit
    start = next((i for i in range(max(1, int(w * 0.08))) if anteil[i] > 0.3), None)
    if start is None:
        return None
    ende = start
    while ende < w and anteil[ende] > 0.3:
        ende += 1
    if ende - start < 3 or ende > w * 0.3:
        return None
    return ende


class Erkennung:
    def __init__(self, ortskennungen: list[str] | None = None, kennzeichen_modell: bool = True) -> None:
        self._engine = RapidOCR()
        self._lock = threading.Lock()  # RapidOCR ist nicht threadsicher
        self.ortskennungen = frozenset(o.strip().upper() for o in (ortskennungen or []) if o.strip())
        self._detektor = self._leser = None
        if kennzeichen_modell:
            from fast_plate_ocr import LicensePlateRecognizer
            from open_image_models import create_detector
            self._detektor = create_detector(DETEKTOR, conf_thresh=DETEKTOR_SCHWELLE)
            self._leser = LicensePlateRecognizer(LESER)

    # ---------- Kennzeichen über Detektor und Lesemodell ----------

    def _kaesten(self, img: np.ndarray) -> list[tuple[float, float, float, float, float]]:
        """Kennzeichen-Kästen (x1, y1, x2, y2, Konfidenz). Erst ganzes Bild, sonst vier Viertel."""
        funde = [(b.x1, b.y1, b.x2, b.y2, float(r.confidence))
                 for r in self._detektor.predict(img) for b in [r.bounding_box]]
        if funde:
            return funde
        h, w = img.shape[:2]
        for y0 in (0, h // 2 - h // 8):
            for x0 in (0, w // 2 - w // 8):
                teil = img[y0:y0 + h // 2 + h // 8, x0:x0 + w // 2 + w // 8]
                funde += [(b.x1 + x0, b.y1 + y0, b.x2 + x0, b.y2 + y0, float(r.confidence))
                          for r in self._detektor.predict(teil) for b in [r.bounding_box]]
        # Doppelte aus überlappenden Vierteln zusammenfassen
        einzeln: list[tuple[float, float, float, float, float]] = []
        for f in sorted(funde, key=lambda f: -f[4]):
            if not any(_ueberlappung(f, e) > 0.3 for e in einzeln):
                einzeln.append(f)
        return einzeln

    def _modell_lesen(self, img: np.ndarray, kasten) -> dict | None:
        x1, y1, x2, y2, _ = kasten
        w, h = x2 - x1, y2 - y1
        stimmen: dict[str, float] = {}
        for rx, ry in RAENDER:
            aus = img[max(0, int(y1 - h * ry)):int(y2 + h * ry), max(0, int(x1 - w * rx)):int(x2 + w * rx)]
            if aus.size == 0:
                continue
            p = self._leser.run(aus, return_confidence=True)[0]
            kz = reparieren(normalisieren(p.plate)) if p.plate else None
            if not kz:
                continue
            konf = float(np.mean(p.char_probs[:len(p.plate)])) if len(p.plate) else 0.0
            stimmen[kz] = stimmen.get(kz, 0.0) + konf
        if not stimmen:
            return None
        # Bei Gleichstand das längere: ein abgeschnittenes E/H ist wahrscheinlicher als ein erfundenes
        sieger = max(stimmen, key=lambda k: (round(stimmen[k], 2), len(k)))
        return {"kennzeichen": sieger,
                "sicherheit": round(stimmen[sieger] / len(RAENDER), 2),
                "varianten": {k: round(v, 2) for k, v in sorted(stimmen.items(), key=lambda kv: -kv[1])},
                "quelle": "modell",
                "kasten": [int(x1), int(y1), int(x2), int(y2)]}

    def _ocr(self, img: np.ndarray, nur_lesen: bool = False):
        # use_* immer ausdrücklich setzen: RapidOCR merkt sich sonst den letzten Aufruf
        if nur_lesen:
            return self._engine(img, use_det=False, use_cls=False, use_rec=True)
        return self._engine(img, use_det=True, use_cls=True, use_rec=True)

    def scan(self, img: np.ndarray, crop_top: float, min_score: float) -> dict:
        h, w = img.shape[:2]
        oben = int(h * crop_top)
        img = img[oben:, :]

        t0 = time.perf_counter()
        with self._lock:
            kennzeichen, verworfen = [], []
            if self._detektor is not None:
                for kasten in self._kaesten(img):
                    kz = self._modell_lesen(img, kasten)
                    if not kz or kz["sicherheit"] < MIN_SICHERHEIT:
                        verworfen.append(kasten)
                    elif kz["kennzeichen"] not in {k["kennzeichen"] for k in kennzeichen}:
                        kennzeichen.append(kz)
            res = self._ocr(img)
            texte = []
            for box, txt, score in zip(res.boxes if res.boxes is not None else [],
                                       res.txts or [], res.scores or []):
                if score < min_score:
                    continue
                norm = normalisieren(txt)
                if not norm:
                    continue
                eintrag = {"text": txt, "norm": norm, "score": round(float(score), 3)}
                kaesten = [k["kasten"] for k in kennzeichen if "kasten" in k] + verworfen
                if ist_logo_zahl(norm, box, kaesten):
                    eintrag["logo"] = True  # Markenlogo oder Kennzeichen-Bruchstück, nicht melden
                elif ist_kandidat(norm):
                    # Gehört der Text zu einem schon gelesenen Kennzeichen? Dann nicht doppelt melden.
                    # Im Kasten zählt nur, was selbst wie ein Kennzeichen aussieht (Schriftzüge bleiben Text).
                    wie_kz = reparieren(norm) is not None
                    passend = next((k for k in kennzeichen if k.get("quelle") == "modell"
                                    and ((wie_kz and _im_kasten(box, k["kasten"]))
                                         or abstand(norm, k["kennzeichen"], 2) <= 2)), None)
                    if passend:
                        eintrag["kennzeichen"] = passend
                    elif wie_kz and any(_im_kasten(box, k) for k in verworfen):
                        eintrag["unsicher"] = True  # unlesbares Kennzeichen, nicht als Text melden
                    else:
                        kz = self._kennzeichen_lesen(img, box, txt, score)
                        if kz:
                            kz["quelle"] = "ocr"
                            eintrag["kennzeichen"] = kz
                            kennzeichen.append(kz)
                texte.append(eintrag)
        dauer = time.perf_counter() - t0

        return {
            "breite": w,
            "hoehe": h,
            "dauer_s": round(dauer, 2),
            "texte": texte,
            "kennzeichen": kennzeichen,
        }

    def _kennzeichen_lesen(self, img: np.ndarray, box, txt: str, score: float) -> dict | None:
        abst = Abstimmung(ortskennungen=self.ortskennungen)
        xs = [int(p[0]) for p in box]
        ys = [int(p[1]) for p in box]
        x0, x1 = max(0, min(xs)), min(img.shape[1], max(xs))
        y0, y1 = max(0, min(ys)), min(img.shape[0], max(ys))
        if x1 - x0 < 8 or y1 - y0 < 4:
            abst.lesung(txt, score)
            erg = abst.ergebnis()
            return None if not erg else {"kennzeichen": erg[0], "sicherheit": round(erg[1], 2),
                                         "varianten": {k: round(v, 2) for k, v in erg[2].items()}}
        abst.lesung(txt, score)
        box_bild = img[y0:y1, x0:x1]
        ende = eu_feld_ende(box_bild)
        if ende is not None:
            # EU-Feld gefunden: genau dahinter abschneiden. Ein fester Beschnitt würde bei
            # Kennzeichen, deren EU-Feld nicht mitgelesen wurde, den ersten Buchstaben kappen.
            rand = max(1, (x1 - x0) // 100)
            for schnitt, gewicht in ((ende + rand, GEWICHT_EU_SCHNITT), (0, 1.0)):
                r = self._ocr(box_bild[:, schnitt:], nur_lesen=True)
                if r.txts:
                    abst.lesung(r.txts[0], float(r.scores[0]) * gewicht, eu_feld=schnitt == 0)
        else:
            for anteil in BESCHNITTE_LINKS:
                aus = box_bild[:, int((x1 - x0) * anteil):]
                r = self._ocr(aus, nur_lesen=True)
                if r.txts:
                    abst.lesung(r.txts[0], float(r.scores[0]))
        erg = abst.ergebnis()
        if not erg:
            return None
        sieger, anteil_stimmen, stimmen = erg
        return {
            "kennzeichen": sieger,
            "sicherheit": round(anteil_stimmen, 2),
            "varianten": {k: round(v, 2) for k, v in sorted(stimmen.items(), key=lambda kv: -kv[1])},
        }


def _ueberlappung(a, b) -> float:
    """Schnitt durch Vereinigung zweier Kästen (x1, y1, x2, y2, ...)."""
    sx = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    sy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    schnitt = sx * sy
    fa = (a[2] - a[0]) * (a[3] - a[1])
    fb = (b[2] - b[0]) * (b[3] - b[1])
    return schnitt / (fa + fb - schnitt) if fa + fb - schnitt > 0 else 0.0


def _im_kasten(box, kasten) -> bool:
    """Liegt der Mittelpunkt der RapidOCR-Box im Kennzeichen-Kasten?"""
    mx = sum(float(p[0]) for p in box) / len(box)
    my = sum(float(p[1]) for p in box) / len(box)
    return kasten[0] <= mx <= kasten[2] and kasten[1] <= my <= kasten[3]


def bild_laden(pfad: str) -> np.ndarray | None:
    return cv2.imread(pfad)
