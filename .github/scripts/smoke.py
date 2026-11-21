"""Rauchtest im laufenden Container: synthetisches Bild erzeugen, /scan aufrufen."""

import json
import sys
import time
import urllib.request

import cv2
import numpy as np

BASIS = "http://127.0.0.1:8000"

img = np.full((600, 1600, 3), 255, np.uint8)
cv2.putText(img, "SVCAM TEST", (60, 380), cv2.FONT_HERSHEY_SIMPLEX, 5, (0, 0, 0), 12)
cv2.imwrite("/media/smoke.png", img)

for _ in range(60):
    try:
        with urllib.request.urlopen(BASIS + "/health", timeout=2) as r:
            if r.status == 200:
                break
    except OSError:
        time.sleep(2)
else:
    sys.exit("Dienst startet nicht")


def post(daten: dict) -> tuple[int, dict]:
    req = urllib.request.Request(BASIS + "/scan", data=json.dumps(daten).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


status, erg = post({"path": "/media/smoke.png", "crop_top": 0})
print(json.dumps(erg, ensure_ascii=False))
texte = "".join(t["norm"] for t in erg.get("texte", []))
if status != 200 or "SVCAM" not in texte:
    sys.exit("Text nicht erkannt")

status, _ = post({"path": "/etc/passwd"})
if status != 400:
    sys.exit("Pfad außerhalb von /media wurde nicht abgelehnt")
status, _ = post({"path": "/media/../etc/passwd"})
if status != 400:
    sys.exit("Pfad mit .. wurde nicht abgelehnt")

print("Rauchtest bestanden")
