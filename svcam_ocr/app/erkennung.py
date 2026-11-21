"""Texterkennung auf einem Bild: alle Texte plus abgestimmte Kennzeichen."""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np
from rapidocr import RapidOCR

from kennzeichen import Abstimmung, ist_kandidat, normalisieren

# Anteil, der links vom Kennzeichen-Ausschnitt abgeschnitten wird (blaues EU-Feld)
BESCHNITTE_LINKS = (0.0, 0.06, 0.10, 0.14)


class Erkennung:
    def __init__(self, ortskennungen: list[str] | None = None) -> None:
        self._engine = RapidOCR()
        self._lock = threading.Lock()  # RapidOCR ist nicht threadsicher
        self.ortskennungen = frozenset(o.strip().upper() for o in (ortskennungen or []) if o.strip())

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
            res = self._ocr(img)
            texte, kennzeichen = [], []
            for box, txt, score in zip(res.boxes if res.boxes is not None else [],
                                       res.txts or [], res.scores or []):
                if score < min_score:
                    continue
                norm = normalisieren(txt)
                if not norm:
                    continue
                eintrag = {"text": txt, "norm": norm, "score": round(float(score), 3)}
                if ist_kandidat(norm):
                    kz = self._kennzeichen_lesen(img, box, txt, score)
                    if kz:
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
        abst.lesung(txt, score)
        xs = [int(p[0]) for p in box]
        ys = [int(p[1]) for p in box]
        x0, x1 = max(0, min(xs)), min(img.shape[1], max(xs))
        y0, y1 = max(0, min(ys)), min(img.shape[0], max(ys))
        if x1 - x0 < 8 or y1 - y0 < 4:
            return None
        for anteil in BESCHNITTE_LINKS:
            aus = img[y0:y1, x0 + int((x1 - x0) * anteil):x1]
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


def bild_laden(pfad: str) -> np.ndarray | None:
    return cv2.imread(pfad)
