"""Kleiner HTTP-Dienst für Home Assistant.

POST /scan   {"path": "/media/...jpg", "crop_top": 0.07,
              "bekannt": [...], "whitelist": [...],
              "beschreibungen": [[eintrag, text], ...]}   -> JSON mit Texten, Kennzeichen, Treffern
POST /scan   {"aktion": "aufraeumen", "behalten": [...]}  -> Verlauf auf diese Texte beschränken
GET  /health                                              -> {"status": "ok"}

"bekannt" und "whitelist" sind optional. Sind sie da, enthält die Antwort
"treffer" mit Status whitelist / bekannt / neu je erkanntem Text, dazu je
gemeldetem Text "anzahl" (Sichtungen im Verlauf). Die Auswertung landet dann
im Verlauf. "vorschau" ist das kleine Bild des Bildpaars (oder null),
"verlauf_link" der Pfad der Verlaufsseite in Home Assistant.

Port 8000 ist nur im internen Netz der Apps erreichbar (kein Port nach außen)
und liest ausschließlich Bilder unterhalb von MEDIA_ROOT. Die Verlaufsseite
läuft auf INGRESS_PORT und antwortet nur dem Ingress-Proxy des Supervisors.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from abgleich import abgleichen
from erkennung import Erkennung, bild_laden
from kennzeichen import normalisieren
from seite import bilder_seite, texte_seite
from verlauf import Verlauf, partner_finden, verlauf_link

OPTIONEN_DATEI = Path(os.environ.get("SVCAM_OPTIONS", "/data/options.json"))
MEDIA_ROOT = Path(os.environ.get("SVCAM_MEDIA_ROOT", "/media")).resolve()
PORT = int(os.environ.get("SVCAM_PORT", "8000"))
INGRESS_PORT = int(os.environ.get("SVCAM_INGRESS_PORT", "8099"))
# Ingress-Proxy des Supervisors; leer = jeder (nur für lokale Tests)
INGRESS_QUELLE = os.environ.get("SVCAM_INGRESS_QUELLE", "172.30.32.2")
VERLAUF_ORDNER = Path(os.environ.get("SVCAM_DATA", "/data")) / "verlauf"
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
                "max_abstand": 1, "min_textlaenge": 3, "bildpaar_warten_s": 8,
                "kennzeichen_modell": True}
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


def paare_pruefen(wert) -> list | None:
    """[[eintrag, beschreibung], ...] mit vernünftiger Größe, sonst None."""
    if wert is None:
        return []
    if not isinstance(wert, list) or len(wert) > MAX_EINTRAEGE:
        return None
    for p in wert:
        if not (isinstance(p, list) and len(p) == 2 and all(isinstance(x, str) for x in p)
                and len(p[0]) <= MAX_EINTRAG_LAENGE and len(p[1]) <= 2000):
            return None
    return wert


class Handler(BaseHTTPRequestHandler):
    server_version = "svcam_ocr"
    erkennung: Erkennung
    optionen: dict
    verlauf: Verlauf | None = None

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

        if anfrage.get("aktion") == "aufraeumen":
            behalten = liste_pruefen(anfrage.get("behalten"))
            if behalten is None:
                self._antwort(400, {"fehler": "behalten muss eine Liste von Texten sein"})
                return
            geloescht = self.verlauf.aufraeumen(behalten) if self.verlauf else 0
            log.info("Verlauf aufgeräumt: %d Bilder gelöscht", geloescht)
            self._antwort(200, {"geloescht": geloescht})
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
        beschreibungen = paare_pruefen(anfrage.get("beschreibungen"))
        if bekannt is None or whitelist is None or beschreibungen is None:
            self._antwort(400, {"fehler": "bekannt, whitelist und beschreibungen haben das falsche Format"})
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
        partner = partner_finden(pfad, float(self.optionen["bildpaar_warten_s"]))
        erg["vorschau"] = str(partner) if partner and pfad_pruefen(str(partner)) else None
        erg["verlauf_link"] = verlauf_link()
        if mit_abgleich:
            erg["treffer"] = abgleichen(erg, bekannt, whitelist,
                                        int(self.optionen["max_abstand"]),
                                        int(self.optionen["min_textlaenge"]))
            if self.verlauf is not None:
                try:
                    anzahl = self.verlauf.speichern(pfad.name, img, partner if erg["vorschau"] else None,
                                                    erg["treffer"], beschreibungen)
                except Exception:  # Verlauf darf die Erkennung nicht verhindern
                    log.exception("Fehler beim Speichern im Verlauf")
                    anzahl = {}
                for t in erg["treffer"]:
                    if t["status"] != "whitelist":
                        t["anzahl"] = anzahl.get(normalisieren(t.get("eintrag") or t["text"]), 1)
        # Keine Inhalte ins Protokoll, nur Zahlen (Kennzeichen sind personenbezogen)
        log.info("%s: %d Texte, %d Kennzeichen, %.2f s",
                 pfad.name, len(erg["texte"]), len(erg["kennzeichen"]), erg["dauer_s"])
        self._antwort(200, erg)

    def log_message(self, fmt: str, *args) -> None:
        log.debug("%s - %s", self.address_string(), fmt % args)


class IngressHandler(BaseHTTPRequestHandler):
    """Verlaufsseite. Antwortet nur dem Ingress-Proxy, der vorher die Anmeldung prüft."""

    server_version = "svcam_ocr"
    verlauf: Verlauf

    def _senden(self, status: int, typ: str, body: bytes, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=86400" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if INGRESS_QUELLE and self.client_address[0] != INGRESS_QUELLE:
            self._senden(403, "text/plain; charset=utf-8", b"nur ueber Home Assistant")
            return
        teile = urlsplit(self.path)
        q = parse_qs(teile.query)
        m = re.fullmatch(r"/bild/(\d{1,10})", teile.path)
        if m:
            daten = self.verlauf.bild(int(m.group(1)), klein="klein" in q)
            if daten is None:
                self._senden(404, "text/plain; charset=utf-8", b"nicht gefunden")
            else:
                self._senden(200, "image/jpeg", daten, cache=True)
            return
        if teile.path != "/":
            self._senden(404, "text/plain; charset=utf-8", b"nicht gefunden")
            return
        if q.get("ansicht") == ["texte"]:
            html = texte_seite(self.verlauf)
        else:
            schluessel = normalisieren(q.get("t", [""])[0][:MAX_EINTRAG_LAENGE]) or None
            try:
                seite = min(max(int(q.get("s", ["0"])[0]), 0), 10000)
            except ValueError:
                seite = 0
            html = bilder_seite(self.verlauf, schluessel, seite)
        self._senden(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def log_message(self, fmt: str, *args) -> None:
        log.debug("Ingress %s - %s", self.address_string(), fmt % args)


def main() -> None:
    optionen = optionen_laden()
    logging.basicConfig(level=optionen["log_level"].upper(),
                        format="%(asctime)s %(levelname)s %(message)s")
    log.info("Lade Modelle …")
    Handler.erkennung = Erkennung(optionen.get("ortskennungen"), bool(optionen["kennzeichen_modell"]))
    Handler.optionen = optionen
    verlauf = Verlauf(VERLAUF_ORDNER)
    Handler.verlauf = verlauf
    IngressHandler.verlauf = verlauf
    ingress = ThreadingHTTPServer(("0.0.0.0", INGRESS_PORT), IngressHandler)
    threading.Thread(target=ingress.serve_forever, daemon=True).start()
    log.info("Verlaufsseite auf Port %d (Ingress)", INGRESS_PORT)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log.info("Bereit auf Port %d, Bilder unter %s", PORT, MEDIA_ROOT)
    server.serve_forever()


if __name__ == "__main__":
    main()
