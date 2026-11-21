# Änderungen

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
