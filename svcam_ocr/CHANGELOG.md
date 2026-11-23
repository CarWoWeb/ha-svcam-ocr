# Änderungen

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
