# SvCam OCR

Liest Texte auf Kamerabildern, zum Beispiel Kennzeichen und Firmenaufschriften auf Fahrzeugen. Alles läuft lokal auf dem Home-Assistant-Rechner, es geht kein Bild ins Internet.

## Wie es funktioniert

Die App bietet im internen Netz von Home Assistant einen kleinen Dienst an. Eine Automation schickt ihr den Pfad eines Bildes unter `/media`, die App antwortet mit allen erkannten Texten.

- Oben wird ein Streifen abgeschnitten, damit der eingeblendete Zeitstempel nicht mitgelesen wird.
- Texte, die wie ein deutsches Kennzeichen aussehen, werden mehrfach gelesen und nach dem Aufbau deutscher Kennzeichen geprüft. Typische Lesefehler (blaues EU-Feld, Plakette, 0/O, 1/I) werden dabei ausgeglichen.
- Die App hat nur Lesezugriff auf `/media` und öffnet keinen Port nach außen.

## Einstellungen

| Option | Standard | Bedeutung |
|:--|:--|:--|
| `crop_top` | `0.07` | Anteil der Bildhöhe, der oben abgeschnitten wird (Zeitstempel). `0.07` = 7 %. |
| `min_score` | `0.5` | Texte mit geringerer Sicherheit werden verworfen. |
| `ortskennungen` | leer | Empfohlen: die Ortskennungen, die bei dir häufig vorkommen (zum Beispiel die eigene und die Nachbarkreise). Sie werden bei unsicheren Lesungen bevorzugt, und Lesungen, bei denen eine Plakette als Buchstabe mitgelesen wurde, fallen raus. |
| `max_abstand` | `1` | Abgleich: so viele Zeichen dürfen von einem Listeneintrag abweichen (nur bei Texten ab 4 Zeichen). `0` = nur exakt. |
| `min_textlaenge` | `3` | Abgleich: kürzere Texte (zum Beispiel einzelne Ziffern) werden übergangen. Kennzeichen zählen immer. |
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

Kennzeichen sind personenbezogene Daten. Die App selbst speichert nichts, sie liest nur und antwortet. Was mit den Ergebnissen passiert (Speichern, Löschfristen, wer Meldungen bekommt), legst du in deinen Automationen fest. Das ist keine Rechtsberatung.
