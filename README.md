# SvCam Apps für Home Assistant

App-Repository (Add-ons) für Home Assistant.

## Enthaltene Apps

- **SvCam OCR**: lokale Texterkennung für Kamerabilder (Kennzeichen und Firmenaufschriften). Läuft auf Raspberry Pi 5 (aarch64) und x86 (amd64) ohne Beschleuniger. Details in [svcam_ocr/DOCS.md](svcam_ocr/DOCS.md).

## Installation

1. In Home Assistant: **Einstellungen → Apps → App-Store → ⋮ → Repositories**.
2. Diese Adresse eintragen: `https://github.com/CarWoWeb/ha-svcam-ocr`
3. **SvCam OCR** installieren und starten. Home Assistant lädt ein fertiges Image (amd64 oder aarch64) von `ghcr.io/carwoweb/ha-svcam-ocr`, gebaut wird nichts.

## Lizenz

MIT. Die Texterkennung nutzt [RapidOCR](https://github.com/RapidAI/RapidOCR) (Apache 2.0) mit PaddleOCR-Modellen (Apache 2.0).
