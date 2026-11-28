"""Bildpaare und Bildverlauf je Text.

Bildpaar: Zu jedem Bild mit "hochauflosung" im Namen legt die Kamera kurz
davor oder danach dasselbe Bild klein ab, mit "standardauflosung" statt
"hochauflosung" im Namen und einem um wenige Sekunden abweichenden
Zeitstempel. Das kleine Bild nehmen wir für Push und Verlauf.

Verlauf: Je Auswertung ein kleines Vorschaubild plus Vorschaubild für die
Liste in /data (nicht in /media), dazu in SQLite, welche Texte darauf
gemeldet wurden. Aufgeräumt wird nach Liste: Texte, die nicht mehr in
"SvCam Texte" stehen, fliegen samt Bildern raus. Je Text bleiben höchstens
MAX_JE_TEXT Sichtungen, Bilder ohne erkannten Text höchstens TAGE_LEER Tage.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

from kennzeichen import normalisieren

ZEITFORMAT = "%Y%m%d%H%M%S"
MAX_JE_TEXT = 50
TAGE_LEER = 7
BREITE_VORSCHAU = 1280
BREITE_KLEIN = 480


def zeit_aus_name(name: str) -> datetime | None:
    m = re.match(r"(\d{14})_", name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), ZEITFORMAT)
    except ValueError:
        return None


def kamera_aus_name(name: str) -> str:
    rest = re.sub(r"^\d{14}_", "", name)
    rest = re.sub(r"\.(jpe?g|png)$", "", rest, flags=re.I)
    rest = re.sub(r"_?(in_)?(hoch|standard)auflosung", "", rest, flags=re.I)
    return rest.replace("_", " ").strip() or "Kamera"


def verlauf_link() -> str | None:
    """Pfad der Verlaufsseite in Home Assistant. Der Supervisor setzt den Hostnamen
    aus dem Slug der App (Unterstrich wird Bindestrich). In der aktuellen Oberfläche
    liegen App-Seiten unter /app/<slug>, der alte Pfad /hassio/ingress/<slug> führt ins Leere."""
    host = os.environ.get("HOSTNAME", "")
    if not re.fullmatch(r"[a-z0-9]+-svcam-ocr", host):
        return None
    return "/app/" + host.replace("-", "_")


def partner_finden(pfad: Path, warten_s: float = 8.0, von_s: int = -5, bis_s: int = 15) -> Path | None:
    """Das kleine Bild zum Bild mit "hochauflosung" im Namen, oder None.

    Sucht im selben Ordner nach <Zeitstempel>_<gleicher Rest mit standardauflosung>,
    Zeitstempel von_s bis bis_s Sekunden neben dem eigenen. Weil die Kamera das
    kleine Bild oft erst danach schreibt, wird bis zu warten_s Sekunden gewartet.
    """
    m = re.match(r"(\d{14})_(.+)$", pfad.name)
    if not m or "hochauflosung" not in m.group(2).lower():
        return None
    zeit = zeit_aus_name(pfad.name)
    if zeit is None:
        return None
    rest = re.sub("hochauflosung", "standardauflosung", m.group(2), flags=re.I)
    ende = time.monotonic() + max(0.0, warten_s)
    while True:
        treffer = []
        for d in range(von_s, bis_s + 1):
            p = pfad.parent / f"{(zeit + timedelta(seconds=d)).strftime(ZEITFORMAT)}_{rest}"
            if p.is_file():
                treffer.append((abs(d), p))
        if treffer:
            p = min(treffer)[1]
            if _fertig_geschrieben(p):
                return p
        if time.monotonic() >= ende:
            return None
        time.sleep(0.5)


def _fertig_geschrieben(p: Path) -> bool:
    """Größe ändert sich nicht mehr (die Kamera schreibt nicht mehr)."""
    try:
        a = p.stat().st_size
        time.sleep(0.3)
        return a > 0 and p.stat().st_size == a
    except OSError:
        return False


def _verkleinern(img: np.ndarray, breite: int, qualitaet: int) -> bytes:
    h, w = img.shape[:2]
    if w > breite:
        img = cv2.resize(img, (breite, int(h * breite / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, qualitaet])
    if not ok:
        raise ValueError("JPEG nicht erzeugbar")
    return buf.tobytes()


class Verlauf:
    """Sichtungen mit Bildern. Thread-sicher über eine Sperre."""

    def __init__(self, ordner: Path) -> None:
        self.ordner = ordner
        self.bilder = ordner / "bilder"
        self.bilder.mkdir(parents=True, exist_ok=True)
        self._sperre = threading.Lock()
        self._db = sqlite3.connect(ordner / "verlauf.db", check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS scan (
                id INTEGER PRIMARY KEY, zeit TEXT NOT NULL, kamera TEXT NOT NULL, leer INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sichtung (
                scan_id INTEGER NOT NULL, schluessel TEXT NOT NULL, anzeige TEXT NOT NULL, status TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS i_sichtung ON sichtung (schluessel);
            CREATE TABLE IF NOT EXISTS beschreibung (schluessel TEXT PRIMARY KEY, text TEXT NOT NULL);
        """)
        self._db.commit()

    # ---------- schreiben ----------

    def speichern(self, name: str, img: np.ndarray, partner: Path | None,
                  treffer: list[dict], beschreibungen: list | None = None) -> dict[str, int]:
        """Legt eine Auswertung ab. Gibt je gemeldetem Text die Anzahl Sichtungen zurück."""
        gemeldet = [t for t in treffer if t.get("status") in ("bekannt", "neu")]
        if treffer and not gemeldet:
            return {}  # nur Whitelist: nichts speichern
        zeit = zeit_aus_name(name) or datetime.now().replace(microsecond=0)
        vorschau = None
        if partner is not None:
            klein_img = cv2.imread(str(partner))
            if klein_img is not None:
                vorschau = partner.read_bytes()
                quelle = klein_img
        if vorschau is None:
            vorschau = _verkleinern(img, BREITE_VORSCHAU, 75)
            quelle = img
        klein = _verkleinern(quelle, BREITE_KLEIN, 70)

        with self._sperre:
            self._beschreibungen_setzen(beschreibungen)
            cur = self._db.execute("INSERT INTO scan (zeit, kamera, leer) VALUES (?, ?, ?)",
                                   (zeit.isoformat(sep=" "), kamera_aus_name(name), int(not gemeldet)))
            scan_id = cur.lastrowid
            (self.bilder / f"{scan_id}.jpg").write_bytes(vorschau)
            (self.bilder / f"{scan_id}_k.jpg").write_bytes(klein)
            anzahl = {}
            for t in gemeldet:
                anzeige = t.get("eintrag") or t["text"]
                key = normalisieren(anzeige)
                if not key or key in anzahl:
                    continue
                self._db.execute("INSERT INTO sichtung VALUES (?, ?, ?, ?)", (scan_id, key, anzeige, t["status"]))
                anzahl[key] = self._db.execute(
                    "SELECT COUNT(*) FROM sichtung WHERE schluessel = ?", (key,)).fetchone()[0]
                # je Text nur die neuesten MAX_JE_TEXT behalten
                self._db.execute("""
                    DELETE FROM sichtung WHERE schluessel = ? AND scan_id NOT IN (
                        SELECT s.scan_id FROM sichtung s JOIN scan ON scan.id = s.scan_id
                        WHERE s.schluessel = ? ORDER BY scan.zeit DESC, scan.id DESC LIMIT ?)""",
                                 (key, key, MAX_JE_TEXT))
            self._db.commit()
            self._verwaiste_loeschen()
        return anzahl

    def _beschreibungen_setzen(self, paare: list | None) -> None:
        if not paare:
            return
        for paar in paare:
            if (isinstance(paar, list) and len(paar) == 2
                    and isinstance(paar[0], str) and isinstance(paar[1], str)):
                key = normalisieren(paar[0])
                if not key:
                    continue
                if paar[1].strip():
                    self._db.execute("INSERT OR REPLACE INTO beschreibung VALUES (?, ?)", (key, paar[1].strip()[:500]))
                else:
                    self._db.execute("DELETE FROM beschreibung WHERE schluessel = ?", (key,))

    def aufraeumen(self, behalten: list[str], jetzt: datetime | None = None) -> int:
        """Löscht Sichtungen aller Texte, die nicht in `behalten` stehen. Gibt die Zahl gelöschter Bilder zurück."""
        keys = {normalisieren(b) for b in behalten} - {""}
        with self._sperre:
            vorhanden = {r[0] for r in self._db.execute("SELECT DISTINCT schluessel FROM sichtung")}
            weg = list(vorhanden - keys)
            for k in weg:
                self._db.execute("DELETE FROM sichtung WHERE schluessel = ?", (k,))
                self._db.execute("DELETE FROM beschreibung WHERE schluessel = ?", (k,))
            self._db.commit()
            return self._verwaiste_loeschen(jetzt)

    def _verwaiste_loeschen(self, jetzt: datetime | None = None) -> int:
        grenze = ((jetzt or datetime.now()) - timedelta(days=TAGE_LEER)).isoformat(sep=" ")
        ids = [r[0] for r in self._db.execute("""
            SELECT id FROM scan WHERE
              (leer = 0 AND id NOT IN (SELECT scan_id FROM sichtung))
              OR (leer = 1 AND zeit < ?)""", (grenze,))]
        for i in ids:
            self._db.execute("DELETE FROM scan WHERE id = ?", (i,))
            for f in (f"{i}.jpg", f"{i}_k.jpg"):
                (self.bilder / f).unlink(missing_ok=True)
        self._db.commit()
        return len(ids)

    # ---------- lesen ----------

    def texte(self) -> list[dict]:
        """Alle Texte, zuletzt gesehene zuerst."""
        with self._sperre:
            zeilen = self._db.execute("""
                SELECT s.schluessel, MAX(s.anzeige), COUNT(*), MAX(scan.zeit), b.text
                FROM sichtung s JOIN scan ON scan.id = s.scan_id
                LEFT JOIN beschreibung b ON b.schluessel = s.schluessel
                GROUP BY s.schluessel ORDER BY MAX(scan.zeit) DESC""").fetchall()
        return [{"schluessel": k, "anzeige": a, "anzahl": n, "zuletzt": z, "beschreibung": b or ""}
                for k, a, n, z, b in zeilen]

    def sichtungen(self, schluessel: str | None, seite: int, je_seite: int = 20) -> tuple[list[dict], bool]:
        """Auswertungen, neueste zuerst, optional nur für einen Text. Zweiter Wert: gibt es mehr?"""
        with self._sperre:
            if schluessel:
                scans = self._db.execute("""
                    SELECT scan.id, scan.zeit, scan.kamera FROM scan JOIN sichtung s ON s.scan_id = scan.id
                    WHERE s.schluessel = ? ORDER BY scan.zeit DESC, scan.id DESC LIMIT ? OFFSET ?""",
                                         (schluessel, je_seite + 1, seite * je_seite)).fetchall()
            else:
                scans = self._db.execute("""
                    SELECT id, zeit, kamera FROM scan ORDER BY zeit DESC, id DESC LIMIT ? OFFSET ?""",
                                         (je_seite + 1, seite * je_seite)).fetchall()
            mehr = len(scans) > je_seite
            ergebnis = []
            for sid, zeit, kamera in scans[:je_seite]:
                texte = self._db.execute("""
                    SELECT s.schluessel, s.anzeige, s.status, b.text FROM sichtung s
                    LEFT JOIN beschreibung b ON b.schluessel = s.schluessel WHERE s.scan_id = ?""",
                                         (sid,)).fetchall()
                ergebnis.append({"id": sid, "zeit": zeit, "kamera": kamera,
                                 "texte": [{"schluessel": k, "anzeige": a, "status": st, "beschreibung": b or ""}
                                           for k, a, st, b in texte]})
        return ergebnis, mehr

    def bild(self, scan_id: int, klein: bool) -> bytes | None:
        p = self.bilder / f"{scan_id}{'_k' if klein else ''}.jpg"
        return p.read_bytes() if p.is_file() else None
