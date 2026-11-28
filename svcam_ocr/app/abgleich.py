"""Abgleich erkannter Texte mit der Whitelist und der Liste bekannter Texte.

Unscharf, damit einzelne Lesefehler keinen doppelten Eintrag erzeugen:
höchstens `max_abstand` Zeichen Unterschied (Levenshtein), aber nur bei
Texten ab `MIN_LAENGE_UNSCHARF` Zeichen. Kurze Texte müssen exakt passen.
"""

from __future__ import annotations

from kennzeichen import normalisieren

MIN_LAENGE_UNSCHARF = 4


def abstand(a: str, b: str, grenze: int) -> int:
    """Levenshtein-Abstand, bricht ab, sobald er größer als `grenze` wird."""
    if abs(len(a) - len(b)) > grenze:
        return grenze + 1
    vorher = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        jetzt = [i]
        for j, cb in enumerate(b, 1):
            jetzt.append(min(vorher[j] + 1, jetzt[j - 1] + 1, vorher[j - 1] + (ca != cb)))
        if min(jetzt) > grenze:
            return grenze + 1
        vorher = jetzt
    return vorher[-1]


def finden(text: str, liste: list[str], max_abstand: int) -> str | None:
    """Bester Eintrag aus `liste` für `text` (Originalschreibweise des Eintrags) oder None."""
    beste, beste_d = None, max_abstand + 1
    for eintrag in liste:
        norm = normalisieren(eintrag)
        if not norm:
            continue
        if norm == text:
            return eintrag
        if min(len(norm), len(text)) < MIN_LAENGE_UNSCHARF:
            continue
        d = abstand(norm, text, max_abstand)
        if d < beste_d:
            beste, beste_d = eintrag, d
    return beste


def abgleichen(erg: dict, bekannt: list[str], whitelist: list[str],
               max_abstand: int, min_textlaenge: int) -> list[dict]:
    """Baut die Trefferliste: je Text höchstens ein Treffer, Kennzeichen zuerst."""
    kandidaten: list[tuple[str, str]] = []
    for kz in erg.get("kennzeichen", []):
        kandidaten.append(("kennzeichen", kz["kennzeichen"]))
    for t in erg.get("texte", []):
        if "kennzeichen" in t or t.get("unsicher") or t.get("logo"):
            continue  # schon als Kennzeichen erfasst, unlesbares Kennzeichen oder Logo-Zahl
        if len(t["norm"]) >= min_textlaenge:
            kandidaten.append(("text", t["norm"]))

    treffer, texte_gesehen, eintraege_gesehen = [], set(), set()
    for art, text in kandidaten:
        if text in texte_gesehen:
            continue
        texte_gesehen.add(text)
        wl = finden(text, whitelist, max_abstand)
        if wl is not None:
            treffer.append({"art": art, "text": text, "status": "whitelist", "eintrag": wl})
            continue
        bk = finden(text, bekannt, max_abstand)
        if bk is not None:
            if bk in eintraege_gesehen:
                continue  # zwei Lesungen landen auf demselben Eintrag
            eintraege_gesehen.add(bk)
            treffer.append({"art": art, "text": text, "status": "bekannt", "eintrag": bk})
        else:
            treffer.append({"art": art, "text": text, "status": "neu", "eintrag": None})
    return treffer
