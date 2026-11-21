"""Kleiner HTTP-Dienst für Home Assistant.

POST /scan   {"path": "/media/...jpg", "crop_top": 0.07,
              "bekannt": [...], "whitelist": [...]}       -> JSON mit Texten, Kennzeichen, Treffern
GET  /health                                              -> {"status": "ok"}

"bekannt" und "whitelist" sind optional. Sind sie da, enthält die Antwort
"treffer" mit Status whitelist / bekannt / neu je erkanntem Text.

Der Dienst ist nur im internen Netz der Apps erreichbar (kein Port nach außen)
und liest ausschließlich Bilder unterhalb von MEDIA_ROOT.
"""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from abgleich import abgleichen
from erkennung import Erkennung, bild_laden

OPTIONEN_DATEI = Path(os.environ.get("SVCAM_OPTIONS", "/data/options.json"))
MEDIA_ROOT = Path(os.environ.get("SVCAM_MEDIA_ROOT", "/media")).resolve()
PORT = int(os.environ.get("SVCAM_PORT", "8000"))
ENDUNGEN = {".jpg", ".jpeg", ".png"}
MAX_BODY = 512 * 1024  # Listen mit einigen tausend Einträgen passen locker
MAX_EINTRAEGE = 20000
MAX_EINTRAG_LAENGE = 200

log = logging.getLogger("svcam_ocr")


def liste_pruefen(wert) -> list[str] | None:
    """Liste von Strings mit vernünftiger Größe, sonst None."""
    if wert is None:
        return []
    if not isinstance(wert, list) or len(wert) > MAX_EINTRAEGE:
        return None
    if not all(isinstance(e, str) and len(e) <= MAX_EINTRAG_LAENGE for e in wert):
        return None
    return wert


def optionen_laden() -> dict:
    standard = {"crop_top": 0.07, "min_score": 0.5, "ortskennungen": [], "log_level": "info",
                "max_abstand": 1, "min_textlaenge": 3}
    if OPTIONEN_DATEI.is_file():
        standard.update(json.loads(OPTIONEN_DATEI.read_text(encoding="utf-8")))
    return standard


def pfad_pruefen(roh: str) -> Path | None:
    """Nur existierende Bilddateien unterhalb von MEDIA_ROOT, keine Ausbrüche per .. oder Symlink."""
    if not isinstance(roh, str) or not roh or "\x00" in roh:
        return None
    pfad = Path(roh).resolve()
    if not pfad.is_relative_to(MEDIA_ROOT):
        return None
    if pfad.suffix.lower() not in ENDUNGEN or not pfad.is_file():
        return None
    return pfad


class Handler(BaseHTTPRequestHandler):
    server_version = "svcam_ocr"
    erkennung: Erkennung
    optionen: dict

    def _antwort(self, status: int, daten: dict) -> None:
        body = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._antwort(200, {"status": "ok"})
        else:
            self._antwort(404, {"fehler": "unbekannter Pfad"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/scan":
            self._antwort(404, {"fehler": "unbekannter Pfad"})
            return
        try:
            laenge = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            laenge = -1
        if not 0 < laenge <= MAX_BODY:
            self._antwort(400, {"fehler": "Anfrage fehlt oder ist zu groß"})
            return
        try:
            anfrage = json.loads(self.rfile.read(laenge))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._antwort(400, {"fehler": "kein gültiges JSON"})
            return
        if not isinstance(anfrage, dict):
            self._antwort(400, {"fehler": "JSON-Objekt erwartet"})
            return

        pfad = pfad_pruefen(anfrage.get("path"))
        if pfad is None:
            self._antwort(400, {"fehler": f"Pfad muss eine Bilddatei unter {MEDIA_ROOT} sein"})
            return

        try:
            crop_top = float(anfrage.get("crop_top", self.optionen["crop_top"]))
        except (TypeError, ValueError):
            crop_top = self.optionen["crop_top"]
        crop_top = min(max(crop_top, 0.0), 0.5)

        bekannt = liste_pruefen(anfrage.get("bekannt"))
        whitelist = liste_pruefen(anfrage.get("whitelist"))
        if bekannt is None or whitelist is None:
            self._antwort(400, {"fehler": "bekannt und whitelist müssen Listen von Texten sein"})
            return
        mit_abgleich = "bekannt" in anfrage or "whitelist" in anfrage

        img = bild_laden(str(pfad))
        if img is None:
            self._antwort(422, {"fehler": "Bild nicht lesbar"})
            return
        try:
            erg = self.erkennung.scan(img, crop_top, float(self.optionen["min_score"]))
        except Exception:  # Erkennung darf den Dienst nicht abschießen
            log.exception("Fehler bei der Erkennung")
            self._antwort(500, {"fehler": "Fehler bei der Erkennung"})
            return
        erg["datei"] = pfad.name
        if mit_abgleich:
            erg["treffer"] = abgleichen(erg, bekannt, whitelist,
                                        int(self.optionen["max_abstand"]),
                                        int(self.optionen["min_textlaenge"]))
        # Keine Inhalte ins Protokoll, nur Zahlen (Kennzeichen sind personenbezogen)
        log.info("%s: %d Texte, %d Kennzeichen, %.2f s",
                 pfad.name, len(erg["texte"]), len(erg["kennzeichen"]), erg["dauer_s"])
        self._antwort(200, erg)

    def log_message(self, fmt: str, *args) -> None:
        log.debug("%s - %s", self.address_string(), fmt % args)


def main() -> None:
    optionen = optionen_laden()
    logging.basicConfig(level=optionen["log_level"].upper(),
                        format="%(asctime)s %(levelname)s %(message)s")
    log.info("Lade Modelle …")
    Handler.erkennung = Erkennung(optionen.get("ortskennungen"))
    Handler.optionen = optionen
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log.info("Bereit auf Port %d, Bilder unter %s", PORT, MEDIA_ROOT)
    server.serve_forever()


if __name__ == "__main__":
    main()
