# Änderungen

## 0.3.2

- Kurze reine Zahlen (bis 4 Ziffern) direkt über oder auf einem gefundenen Kennzeichen meldet die App nicht mehr als Text. Das waren Markenlogos am Heck, die die Texterkennung als Ziffern liest, oder Bruchstücke des Kennzeichens. Hausnummern und Schilder weiter weg bleiben Text.

## 0.3.1

- Push antippen öffnet die Verlaufsseite wieder: Link auf `/app/<slug>` statt `/hassio/ingress/<slug>`, den die aktuelle Oberfläche von Home Assistant nicht mehr kennt.

## 0.3.0

- **Kennzeichen neu:** eigener Kennzeichen-Detektor (open-image-models YOLOv9-s) und Kennzeichen-Lesemodell (fast-plate-ocr cct-xs-v2), Abstimmung über drei Ränder, unsichere Lesungen werden verworfen. Findet auch kleine Kennzeichen und nachts. RapidOCR bleibt für alle anderen Texte und als Rückfall. Auf den bisherigen Testbildern 12 statt 7 von 13 Kennzeichen richtig. Neue Option `kennzeichen_modell`.
- Neue Seite **SvCam Verlauf** in der Seitenleiste (Ingress): Bilder je Text, neueste zuerst, seitenweise und nur als kleine Vorschau geladen. Die Bilder liegen verkleinert im Speicher der App.
- Bildpaare: Zu einem Bild mit `hochauflosung` wird das passende Bild mit `standardauflosung` gesucht (gleicher Name, Zeitstempel -5 bis +15 s) und als `vorschau` geliefert. Neue Option `bildpaar_warten_s`.
- `/scan` liefert je gemeldetem Text die Anzahl der Sichtungen (`anzahl`) und den Link zur Verlaufsseite (`verlauf_link`). Optional nimmt es `beschreibungen` an.
- `/scan` mit `{"aktion": "aufraeumen", "behalten": [...]}` räumt den Verlauf auf.

## 0.2.2

- Kennzeichen: Das blaue EU-Feld wird jetzt im Bild gesucht und genau dahinter abgeschnitten. Der bisherige feste Beschnitt links konnte bei Kennzeichen ohne mitgelesenes EU-Feld den ersten Buchstaben der Ortskennung kappen.
- Kennzeichen: Mit eingetragenen `ortskennungen` werden unmögliche Aufteilungen abgewertet (nach der Ortskennung höchstens zwei Erkennungsbuchstaben). Das hilft, wenn die Plaketten als Buchstabe gelesen werden.

## 0.2.1

- Installation repariert: `build.yaml` entfernt (seit Supervisor 2026.04 veraltet), Basis-Image fest im Dockerfile.
- Fertige Images für amd64 und aarch64 auf ghcr.io: Home Assistant lädt die App herunter statt sie auf dem Gerät zu bauen.

## 0.2.0

- Abgleich mit einer Liste bekannter Texte und einer Whitelist: `/scan` nimmt optional `bekannt` und `whitelist` an und liefert `treffer` mit Status `whitelist`, `bekannt` oder `neu`.
- Unscharfer Abgleich (Levenshtein, Standard höchstens 1 Zeichen Abstand, erst ab 4 Zeichen), damit einzelne Lesefehler keinen neuen Eintrag erzeugen.
- Neue Optionen `max_abstand` und `min_textlaenge`. Kurze Schnipsel wie einzelne Ziffern werden beim Abgleich übergangen.
- Kennzeichen-Reparatur: vorne muss mindestens ein echter Buchstabe stehen.
- Protokoll enthält keine erkannten Texte, nur Anzahl und Dauer.

## 0.1.0

- Erste Version: Texterkennung mit RapidOCR (PP-OCRv6) über ONNX Runtime, nur CPU.
- Kennzeichen-Abstimmung über mehrere Lesungen mit Korrektur typischer Lesefehler.
- Zeitstempel-Streifen oben einstellbar ausblenden.
