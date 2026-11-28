"""Kennzeichen aus OCR-Lesungen herausarbeiten.

Jedes Kennzeichen wird mehrfach gelesen (ganzes Bild, Ausschnitte mit
unterschiedlich viel Rand links). Jede Lesung wird normalisiert, nach dem
Aufbau deutscher Kennzeichen repariert und als Stimme gezählt. Gewinner ist
die Variante mit der höchsten Summe der OCR-Konfidenzen.

Aufbau: Ortskennung (1-3 Buchstaben) + Erkennung (1-2 Buchstaben)
+ Zahl (1-4 Ziffern, keine führende 0) + optional E oder H.
Zusammen höchstens 8 Zeichen ohne E/H.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Verwechslungen: im Ziffernblock Buchstabe -> Ziffer, im Buchstabenblock Ziffer -> Buchstabe
ZU_ZIFFER = {"O": "0", "D": "0", "Q": "0", "G": "0", "I": "1", "L": "1", "T": "1",
             "Z": "2", "S": "5", "B": "8"}
ZU_BUCHSTABE = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}

BUCHSTABEN = "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ"


def normalisieren(text: str) -> str:
    """Großbuchstaben, nur A-Z, Umlaute und Ziffern."""
    return re.sub(r"[^A-Z0-9ÄÖÜ]", "", text.upper())


def ist_kandidat(norm: str) -> bool:
    """Grobfilter: könnte ein Kennzeichen sein (Buchstaben und Ziffern gemischt)."""
    return (4 <= len(norm) <= 11
            and any(c in BUCHSTABEN for c in norm)
            and any(c.isdigit() or c in ZU_ZIFFER for c in norm[1:]))


def ist_logo_zahl(norm: str, box, kaesten) -> bool:
    """Kurze reine Zahl direkt über oder auf einem Kennzeichen: meist ein Markenlogo
    (z. B. vier Ringe, als "1395" gelesen) oder ein Bruchstück des Kennzeichens.

    box: vier Eckpunkte des Textes, kaesten: Kennzeichenkästen (x1, y1, x2, y2, ...).
    Gesucht wird seitlich eine halbe Kastenbreite daneben, nach oben drei Kastenhöhen,
    nach unten eine halbe. Hausnummern und Schilder weiter weg bleiben Text.
    """
    if not re.fullmatch(r"\d{1,4}", norm):
        return False
    mx = sum(p[0] for p in box) / len(box)
    my = sum(p[1] for p in box) / len(box)
    for k in kaesten:
        x1, y1, x2, y2 = (float(v) for v in k[:4])
        b, h = x2 - x1, y2 - y1
        if x1 - b / 2 <= mx <= x2 + b / 2 and y1 - 3 * h <= my <= y2 + h / 2:
            return True
    return False


def _aufteilen(s: str, suffix: str) -> list[tuple[int, str]]:
    """Alle gültigen Aufteilungen von s in Buchstaben + Ziffern, mit Anzahl Ersetzungen."""
    ergebnisse = []
    for n in range(1, 5):
        if len(s) - n < 2:
            break
        vorn, block = s[:-n], s[-n:]
        if not any(c in BUCHSTABEN for c in vorn):
            continue  # vorn mindestens ein echter Buchstabe
        if not all(c.isdigit() or c in ZU_ZIFFER for c in block):
            continue
        if not any(c.isdigit() for c in block):
            continue  # mindestens eine echte Ziffer
        ziffern = "".join(ZU_ZIFFER.get(c, c) for c in block)
        if ziffern.startswith("0"):
            continue
        buchstaben = "".join(ZU_BUCHSTABE.get(c, c) for c in vorn)
        if not all(c in BUCHSTABEN for c in buchstaben):
            continue
        if not 2 <= len(buchstaben) <= 5 or len(buchstaben) + len(ziffern) > 8:
            continue
        kosten = sum(a != b for a, b in zip(vorn + block, buchstaben + ziffern))
        ergebnisse.append((kosten, buchstaben + ziffern + suffix))
    return ergebnisse


def reparieren(norm: str) -> str | None:
    """Macht aus einer Lesung ein gültiges deutsches Kennzeichen, mit so wenig
    Ersetzungen wie möglich. None, wenn das nicht geht."""
    kandidaten = _aufteilen(norm, "")
    if len(norm) > 3 and norm[-1] in "EH":
        kandidaten += _aufteilen(norm[:-1], norm[-1])
    if not kandidaten:
        return None
    # wenigste Ersetzungen gewinnt, bei Gleichstand das längere Ergebnis
    kandidaten.sort(key=lambda k: (k[0], -len(k[1])))
    return kandidaten[0][1]


@dataclass
class Abstimmung:
    """Sammelt Lesungen eines Kennzeichens und wählt die beste Variante."""

    ortskennungen: frozenset[str] = frozenset()
    stimmen: dict[str, float] = field(default_factory=dict)

    def lesung(self, text: str, score: float, eu_feld: bool = True) -> None:
        """eu_feld=False: Das EU-Feld ist sicher abgeschnitten, also keine Variante ohne ersten Buchstaben."""
        norm = normalisieren(text)
        if not norm:
            return
        varianten = []
        rep = reparieren(norm)
        if rep:
            varianten.append((rep, 1.0))
        # Blaues EU-Feld wird oft als zusätzlicher Buchstabe vorn gelesen
        if eu_feld and len(norm) > 4 and norm[0] in BUCHSTABEN:
            rep2 = reparieren(norm[1:])
            if rep2 and rep2 != rep:
                varianten.append((rep2, 0.8))
        for kz, gewicht in varianten:
            self.stimmen[kz] = self.stimmen.get(kz, 0.0) + score * gewicht * self._ort_faktor(kz)

    def _ort_faktor(self, kz: str) -> float:
        """Bonus für bekannte Ortskennungen, Abzug für unmögliche Aufteilungen.

        Beginnt die Lesung mit einer bekannten Ortskennung, müssen danach 1-2
        Erkennungsbuchstaben folgen. "XX" + "QYY" wäre unmöglich; das passiert,
        wenn die Plaketten zwischen Ortskennung und Erkennung als Buchstabe
        gelesen werden.
        """
        if not self.ortskennungen:
            return 1.0
        buchstaben = re.match(r"[A-ZÄÖÜ]*", kz).group()
        bekannt = [n for n in (1, 2, 3) if buchstaben[:n] in self.ortskennungen]
        if not bekannt:
            return 1.0
        if any(1 <= len(buchstaben) - n <= 2 for n in bekannt):
            return 1.5
        return 0.3

    def ergebnis(self) -> tuple[str, float, dict[str, float]] | None:
        if not self.stimmen:
            return None
        sieger = max(self.stimmen, key=self.stimmen.get)
        gesamt = sum(self.stimmen.values())
        return sieger, self.stimmen[sieger] / gesamt, dict(self.stimmen)
