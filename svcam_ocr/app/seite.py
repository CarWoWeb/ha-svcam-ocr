"""HTML-Seite "SvCam Verlauf" für die Seitenleiste von Home Assistant (Ingress).

Alle Links sind relativ, weil Ingress die Seite unter einem wechselnden
Pfad ausliefert. Bilder werden seitenweise (20 je Seite) und erst beim
Hinscrollen geladen (loading="lazy"), in der Liste nur als kleine Vorschau.
"""

from __future__ import annotations

from html import escape
from urllib.parse import quote

from verlauf import Verlauf

STIL = """
:root { --bg:#fafafa; --fg:#1c1c1c; --dim:#6b6b6b; --karte:#fff; --rand:#e2e2e2; --akzent:#03a9f4; --neu:#e65100; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#111; --fg:#e8e8e8; --dim:#9a9a9a; --karte:#1c1c1c; --rand:#2e2e2e; --akzent:#4fc3f7; --neu:#ffab40; } }
* { box-sizing: border-box; }
body { margin:0; padding:16px; background:var(--bg); color:var(--fg);
       font: 15px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
h1 { font-size:20px; margin:0 0 4px; } h2 { font-size:16px; margin:20px 0 8px; }
a { color:var(--akzent); text-decoration:none; }
nav { display:flex; gap:16px; margin:4px 0 12px; flex-wrap:wrap; }
.dim { color:var(--dim); font-size:13px; }
.raster { display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px; }
.karte { background:var(--karte); border:1px solid var(--rand); border-radius:10px; overflow:hidden; }
.karte img { width:100%; aspect-ratio:16/9; object-fit:cover; display:block; background:var(--rand); }
.karte .inhalt { padding:8px 10px; }
.text { font-weight:600; font-family: ui-monospace, Consolas, monospace; }
.neu { color:var(--neu); font-size:12px; font-weight:600; margin-left:4px; }
table { border-collapse:collapse; width:100%; background:var(--karte); }
td, th { text-align:left; padding:6px 8px; border-bottom:1px solid var(--rand); vertical-align:top; }
th { font-size:13px; color:var(--dim); font-weight:500; }
.weiter { margin:16px 0; display:flex; gap:16px; }
"""


def _kopf(titel: str) -> str:
    return (f'<!doctype html><html lang="de"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(titel)}</title><style>{STIL}</style></head><body>'
            f'<h1>SvCam Verlauf</h1>'
            f'<nav><a href="./">Neueste Bilder</a><a href="./?ansicht=texte">Alle Texte</a></nav>')


def _zeit(z: str) -> str:
    """'2026-11-23 21:52:20' -> '23.11.2026 21:52'"""
    try:
        d, t = z.split(" ")
        j, m, tag = d.split("-")
        return f"{tag}.{m}.{j} {t[:5]}"
    except ValueError:
        return escape(z)


def texte_seite(v: Verlauf) -> str:
    zeilen = []
    for t in v.texte():
        zeilen.append(
            f'<tr><td><a class="text" href="./?t={quote(t["schluessel"])}">{escape(t["anzeige"])}</a></td>'
            f'<td>{escape(t["beschreibung"])}</td><td>{t["anzahl"]}×</td><td>{_zeit(t["zuletzt"])}</td></tr>')
    tabelle = ("<table><tr><th>Text</th><th>Beschreibung</th><th>Gesehen</th><th>Zuletzt</th></tr>"
               + "".join(zeilen) + "</table>") if zeilen else '<p class="dim">Noch nichts gespeichert.</p>'
    return _kopf("SvCam Texte") + "<h2>Alle Texte, zuletzt gesehene zuerst</h2>" + tabelle + "</body></html>"


def bilder_seite(v: Verlauf, schluessel: str | None, seite: int) -> str:
    scans, mehr = v.sichtungen(schluessel, seite)
    if schluessel:
        info = next((t for t in v.texte() if t["schluessel"] == schluessel), None)
        titel = info["anzeige"] if info else schluessel
        unter = (f'{escape(info["beschreibung"]) + " · " if info and info["beschreibung"] else ""}'
                 f'{info["anzahl"]}× gesehen' if info else "")
        kopf = f'<h2><span class="text">{escape(titel)}</span></h2><p class="dim">{unter}</p>'
    else:
        kopf = "<h2>Neueste Bilder</h2>"
    karten = []
    for s in scans:
        texte = []
        for t in s["texte"]:
            neu = '<span class="neu">neu</span>' if t["status"] == "neu" else ""
            beschr = f' <span class="dim">{escape(t["beschreibung"])}</span>' if t["beschreibung"] else ""
            texte.append(f'<div><a class="text" href="./?t={quote(t["schluessel"])}">{escape(t["anzeige"])}</a>'
                         f'{neu}{beschr}</div>')
        if not texte:
            texte.append('<div class="dim">nichts erkannt</div>')
        karten.append(
            f'<div class="karte"><a href="bild/{s["id"]}"><img loading="lazy" src="bild/{s["id"]}?klein=1" alt=""></a>'
            f'<div class="inhalt"><div class="dim">{_zeit(s["zeit"])} · {escape(s["kamera"])}</div>'
            f'{"".join(texte)}</div></div>')
    inhalt = f'<div class="raster">{"".join(karten)}</div>' if karten else '<p class="dim">Keine Bilder.</p>'
    basis = f"./?t={quote(schluessel)}&" if schluessel else "./?"
    weiter = []
    if seite > 0:
        weiter.append(f'<a href="{basis}s={seite - 1}">← neuer</a>')
    if mehr:
        weiter.append(f'<a href="{basis}s={seite + 1}">älter →</a>')
    return (_kopf("SvCam Verlauf") + kopf + inhalt
            + f'<div class="weiter">{"".join(weiter)}</div></body></html>')
