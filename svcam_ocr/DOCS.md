# SvCam OCR

Liest Texte auf Kamerabildern, zum Beispiel Kennzeichen und Firmenaufschriften auf Fahrzeugen. Alles läuft lokal auf dem Home-Assistant-Rechner, es geht kein Bild ins Internet.

## Wie es funktioniert

Die App bietet im internen Netz von Home Assistant einen kleinen Dienst an. Eine Automation schickt ihr den Pfad eines Bildes unter `/media`, die App antwortet mit allen erkannten Texten.

- Oben wird ein Streifen abgeschnitten, damit der eingeblendete Zeitstempel nicht mitgelesen wird.
- **Kennzeichen** findet ein eigener Kennzeichen-Detektor (YOLOv9 aus open-image-models), auch kleine und nachts. Findet er im ganzen Bild nichts, sucht er in vier überlappenden Vierteln. Jeden Fund liest ein Kennzeichen-Lesemodell (fast-plate-ocr) mit drei verschieden großen Rändern. Die Lesungen stimmen ab, der Aufbau deutscher Kennzeichen wird geprüft. Unsichere Lesungen (zu klein, verwischt) werden verworfen statt gemeldet. Kurze reine Zahlen direkt über oder auf einem Kennzeichen (Markenlogos am Heck) meldet die App nicht als Text.
- **Alle anderen Texte** (Firmennamen) liest RapidOCR. Findet der Detektor ein Kennzeichen nicht, liest RapidOCR es wie bisher mehrfach und stimmt ab. Typische Lesefehler (blaues EU-Feld, Plakette, 0/O, 1/I) werden dabei ausgeglichen.
- Die App hat nur Lesezugriff auf `/media` und öffnet keinen Port nach außen.
- **Verlauf:** Bei jeder Auswertung mit Abgleich legt die App ein verkleinertes Bild in ihrem eigenen Speicher ab (`/data`, nicht in `/media`) und merkt sich, welche Texte darauf gemeldet wurden. Die Seite **SvCam Verlauf** (Seitenleiste, über die Anmeldung von Home Assistant) zeigt die Bilder je Text, neueste zuerst, 20 je Seite. Je Text bleiben höchstens 50 Bilder, Bilder ohne Text 7 Tage. Mit `{"aktion": "aufraeumen", "behalten": [...]}` an `/scan` löscht die App alle Texte, die nicht in der Liste stehen.
- **Bildpaare:** Zu einem Bild mit `hochauflosung` im Namen sucht die App ein Bild mit `standardauflosung` statt `hochauflosung` und sonst gleichem Namen, Zeitstempel 5 s davor bis 15 s danach. Es wird als `vorschau` zurückgegeben und für den Verlauf genommen.

## Einstellungen

| Option | Standard | Bedeutung |
|:--|:--|:--|
| `crop_top` | `0.07` | Anteil der Bildhöhe, der oben abgeschnitten wird (Zeitstempel). `0.07` = 7 %. |
| `min_score` | `0.5` | Texte mit geringerer Sicherheit werden verworfen. |
| `ortskennungen` | leer | Nur für den Rückfall über RapidOCR: die Ortskennungen, die bei dir häufig vorkommen. Sie werden bei unsicheren Lesungen bevorzugt. Das Kennzeichen-Modell braucht sie nicht. |
| `max_abstand` | `1` | Abgleich: so viele Zeichen dürfen von einem Listeneintrag abweichen (nur bei Texten ab 4 Zeichen). `0` = nur exakt. |
| `min_textlaenge` | `3` | Abgleich: kürzere Texte (zum Beispiel einzelne Ziffern) werden übergangen. Kennzeichen zählen immer. |
| `kennzeichen_modell` | `true` | Kennzeichen über Detektor und Lesemodell. `false` = nur RapidOCR wie bis 0.2.2 (schneller, aber deutlich schlechter). |
| `bildpaar_warten_s` | `8` | So lange wartet die App nach der Erkennung höchstens auf das kleine Bild des Bildpaars. `0` = nicht warten. |
| `log_level` | `info` | Ausführlichkeit des Protokolls. |

## Aufruf aus Home Assistant

Den Hostnamen der App findest du auf der Info-Seite der App (zum Beispiel `xxxxxxxx-svcam-ocr`).

```yaml
rest_command:
  svcam_scan:
    url: "http://HOSTNAME:8000/scan"
    method: POST
    content_type: "application/json"
    payload: '{"path": "{{ path }}"}'
    timeout: 60
```

Aufruf in einer Automation:

```yaml
- action: rest_command.svcam_scan
  data:
    path: /media/ordner/bild.jpg
  response_variable: ocr
# ocr.content.texte       -> alle Texte
# ocr.content.kennzeichen -> erkannte Kennzeichen
```

## Abgleich mit Listen

Schickt die Automation zusätzlich `bekannt` und `whitelist` mit (Listen von Texten, zum Beispiel die Einträge zweier To-do-Listen), gleicht die App jeden erkannten Text ab und liefert `treffer`:

```json
{"path": "/media/ordner/bild.jpg", "bekannt": ["XX-YY 100", "DHL"], "whitelist": ["XX Z 200"]}
```

```json
"treffer": [
  {"art": "kennzeichen", "text": "XXYY100", "status": "bekannt", "eintrag": "XX-YY 100"},
  {"art": "text", "text": "NEUFIRMA", "status": "neu", "eintrag": null}
]
```

Schreibweise (Groß/klein, Leerzeichen, Bindestriche) spielt keine Rolle. Die Whitelist wird zuerst geprüft.

## Antwort

```json
{
  "datei": "bild.jpg",
  "breite": 3840,
  "hoehe": 2160,
  "dauer_s": 2.1,
  "texte": [
    {"text": "DHL", "norm": "DHL", "score": 0.98}
  ],
  "kennzeichen": [
    {"kennzeichen": "XXYY000", "sicherheit": 0.81, "varianten": {"XXYY000": 3.4}}
  ]
}
```

## Datenschutz

Kennzeichen sind personenbezogene Daten. Die App speichert nur für den Verlauf: verkleinerte Bilder und die gemeldeten Texte in `/data/verlauf`, je Text höchstens 50, Bilder ohne Text 7 Tage. Texte, die beim nächtlichen Aufräumen nicht mehr in der Liste stehen, werden samt Bildern gelöscht. Das Protokoll enthält keine erkannten Texte. Alles andere (Listen, Löschfristen, wer Meldungen bekommt) legst du in deinen Automationen fest. Das ist keine Rechtsberatung.
