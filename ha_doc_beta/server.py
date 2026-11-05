#!/usr/bin/env python3
"""Ingress-Weboberfläche und Zeitplan für das HA-Doku-Add-on (nur Standardbibliothek + ha_doc)."""
import calendar
import datetime as dt
import html
import json
import os
import signal
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote

import ha_brand
import ha_changes
import ha_cover
import ha_schedule
import ha_doc
import ha_notes

OUT_DIR = os.environ.get("HA_DOC_OUT", "/share/ha_doc")
OUT_FOLDER = os.path.basename(OUT_DIR.rstrip("/")) or "ha_doc"
DATA_DIR = os.environ.get("HA_DOC_DATA", "/data")
SNAP_DIR = os.path.join(OUT_DIR, "snapshots")
NOTES_FILE = os.path.join(OUT_DIR, "notes.json")
DEMO = os.environ.get("HA_DOC_DEMO") == "1"
PORT = int(os.environ.get("HA_DOC_PORT", "8099"))
SUPERVISOR_IP = "172.30.32.2"  # Ingress-Anfragen kommen nur von hier
os.makedirs(OUT_DIR, exist_ok=True)


def load_options():
    path = os.environ.get("HA_DOC_OPTIONS", os.path.join(DATA_DIR, "options.json"))
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


OPTIONS = load_options()
ALL_SECTIONS = [k for k, _ in ha_doc.SECTIONS]
state = {"running": False, "msg": "", "error": "", "sections": [k for k in ALL_SECTIONS if k != "aenderungen"], "areas": None,
         "hide_diag": False, "only_problems": False, "save_snap": False}
lock = threading.Lock()
_areas_cache = {"t": 0.0, "v": []}
_tz_cache = {}


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------

def sup_get(path):
    import requests
    r = requests.get("http://supervisor/core" + path, headers={"Authorization": "Bearer " + os.environ["SUPERVISOR_TOKEN"]}, timeout=20)
    return r.json() if r.status_code == 200 else None


def get_tz():
    if "tz" not in _tz_cache:
        name = "UTC"
        try:
            if not DEMO:
                name = (sup_get("/api/config") or {}).get("time_zone") or "UTC"
            from zoneinfo import ZoneInfo
            _tz_cache["tz"] = ZoneInfo(name)
        except Exception:
            _tz_cache["tz"] = dt.timezone.utc
    return _tz_cache["tz"]


def get_areas():
    """Liste (area_id, Name) für die Bereichsauswahl, 2 Minuten zwischengespeichert."""
    if time.time() - _areas_cache["t"] < 120 and _areas_cache["v"]:
        return _areas_cache["v"]
    try:
        if DEMO:
            raw = ha_doc.demo_data()["areas"]
        else:
            c = ha_doc.HAClient(None, os.environ["SUPERVISOR_TOKEN"], supervisor=True)
            raw = c.ws_call("config/area_registry/list") or []
            c.ws.close()
        _areas_cache["v"] = sorted(((a["area_id"], a["name"]) for a in raw), key=lambda x: x[1].lower())
        _areas_cache["t"] = time.time()
    except Exception:
        traceback.print_exc()
    return _areas_cache["v"]


_light = {"t": 0.0, "v": None}


def light_data(force=False):
    """Leichtgewichtige Daten (ohne Konfigurationen) für die Erfassungsseite, 5 Minuten zwischengespeichert."""
    if force or not _light["v"] or time.time() - _light["t"] > 300:
        _light["v"] = ha_doc.demo_data() if DEMO else ha_doc.fetch_all(None, os.environ["SUPERVISOR_TOKEN"], supervisor=True, light=True)
        _light["t"] = time.time()
    return _light["v"]


def is_doc_file(f):
    return f.startswith(("ha_dokumentation_", "ha_monatsbericht_")) and f.endswith((".pdf", ".xlsx"))


def cleanup_old():
    keep = sched()["keep_last"]
    # Nur automatisch erstellte Berichte werden aufgeräumt; manuell erstellte Dateien bleiben bis zum Löschen.
    files = sorted(f for f in os.listdir(OUT_DIR) if f.startswith("ha_monatsbericht_") and f.endswith(".pdf"))
    for f in files[:-keep] if len(files) > keep else []:
        try:
            os.remove(os.path.join(OUT_DIR, f))
        except OSError:
            pass


def generate(sections, options, source="manuell", fmt="pdf"):
    try:
        state.update(msg="Lese Daten aus Home Assistant …", error="")
        data = ha_doc.demo_data() if DEMO else ha_doc.fetch_all(None, os.environ["SUPERVISOR_TOKEN"], supervisor=True)
        nt = ha_notes.load(NOTES_FILE)
        options = dict(options, notes=nt["items"], general_note=nt["general"], logo_path=ha_brand.logo_path(OUT_DIR),
                       cover=ha_cover.active(ha_cover.load(OUT_DIR)))
        if fmt == "pdf" and "aenderungen" in (sections or []):
            cur = ha_changes.snapshot(data, nt)
            prev = ha_changes.load_latest(SNAP_DIR)
            options = dict(options, changes=ha_changes.compare(prev, cur))
            if prev is None or source == "automatisch" or options.get("save_snapshot"):
                ha_changes.save(SNAP_DIR, cur)
        state["msg"] = "Erstelle Excel …" if fmt == "xlsx" else "Erstelle PDF …"
        prefix = "ha_monatsbericht_" if source == "automatisch" else "ha_dokumentation_"
        name = dt.datetime.now().strftime(prefix + "%Y%m%d_%H%M%S.") + fmt
        if fmt == "xlsx":
            import ha_xlsx
            ha_xlsx.build_xlsx(data, os.path.join(OUT_DIR, name), options=options)
        else:
            ha_doc.build_pdf(data, os.path.join(OUT_DIR, name), sections=sections, options=options)
        cleanup_old()
        state["msg"] = f"Fertig ({source}): {name}"
    except Exception:
        state["error"] = traceback.format_exc()
        state["msg"] = "Fehler beim Erstellen"
    finally:
        state["running"] = False


def start_generation(sections, options, source="manuell", fmt="pdf"):
    with lock:
        if state["running"]:
            return False
        state["running"] = True
        state["msg"] = "Starte …"
    threading.Thread(target=generate, args=(sections, options, source, fmt), daemon=True).start()
    return True


# --------------------------------------------------------------------------
# Monatlicher Bericht
# --------------------------------------------------------------------------

SCHED_FILE = os.path.join(DATA_DIR, "scheduler.json")
UI_FILE = os.path.join(DATA_DIR, "schedule_ui.json")


def sched():
    """Aktuelle Einstellungen des Monatsberichts (Datei share/ha_doc/schedule.json)."""
    return ha_schedule.load(OUT_DIR, ALL_SECTIONS, OPTIONS, UI_FILE)


def last_run():
    try:
        with open(SCHED_FILE, encoding="utf-8") as f:
            return json.load(f).get("last", "")
    except Exception:
        return ""


def mark_run(key):
    try:
        with open(SCHED_FILE, "w", encoding="utf-8") as f:
            json.dump({"last": key}, f)
    except Exception:
        traceback.print_exc()


def scheduled_settings():
    """Abschnitte und Filter für den Monatsbericht. Rückgabe: (Abschnitte, Optionen, Quelle)."""
    c = sched()
    return c["sections"], {"hide_diagnostic": c["hide_diagnostic"], "only_problems": c["only_problems"], "areas": c["areas"]}, "Einstellungen Monatsbericht"


def scheduler_loop():
    while True:
        try:
            c = sched()
            if c["enabled"]:
                now = dt.datetime.now(get_tz())
                day = min(c["day"], calendar.monthrange(now.year, now.month)[1])
                key = now.strftime("%Y-%m")
                if now.day == day and now.strftime("%H:%M") >= c["time"] and last_run() != key:
                    sections, opts, _ = scheduled_settings()
                    if start_generation(sections, opts, source="automatisch"):
                        mark_run(key)
        except Exception:
            traceback.print_exc()
        time.sleep(30)


def schedule_info():
    c = sched()
    if not c["enabled"]:
        return "Automatischer Monatsbericht: aus (einschalten unter «Einstellungen Monatsbericht»)."
    last = last_run()
    sections, o, _ = scheduled_settings()
    labels = dict(ha_doc.SECTIONS)
    inhalt = "alle Abschnitte" if len(sections) == len(ALL_SECTIONS) else ", ".join(labels[x] for x in sections)
    filt = [x for x, on in (("ohne Diagnose-Entitäten", o["hide_diagnostic"]), ("nur fehlende Entitäten", o["only_problems"]),
                            ("ausgewählte Bereiche", o["areas"] is not None)) if on]
    return (f"Automatischer Monatsbericht: jeden Monat am {c['day']}. um {c['time']} Uhr "
            f"({inhalt}" + (f"; {', '.join(filt)}" if filt else "") + f"), die letzten {c['keep_last']} automatischen PDFs werden behalten"
            + (f", zuletzt: {last}." if last else "."))


# --------------------------------------------------------------------------
# Weboberfläche
# --------------------------------------------------------------------------

def toggle_bar(name, extra=""):
    """Knöpfe «Alle» und «Keine» für eine Gruppe von Kontrollkästchen im selben Formular (extra: weitere Knöpfe dahinter)."""
    js = "this.form.querySelectorAll('input[name={n}]').forEach(function(c){{c.checked={v};}})"
    return (f'<div class="tgl"><button type="button" class="mini" onclick="{js.format(n=name, v="true")}">Alle auswählen</button>'
            f'<button type="button" class="mini" onclick="{js.format(n=name, v="false")}">Keine auswählen</button>{extra}</div>')


def checkbox(name, value, label, checked):
    return f'<label class="opt"><input type="checkbox" name="{name}" value="{html.escape(value)}"{" checked" if checked else ""}> {html.escape(label)}</label>'


def cover_block():
    c = ha_cover.load(OUT_DIR)
    E = html.escape

    def inp(g, k, label, mx, multi):
        v = c[g][k]
        if multi:
            return f'<label class="fld">{E(label)}<textarea name="{g}_{k}" maxlength="{mx}" rows="2">{E(v)}</textarea></label>'
        return f'<label class="fld">{E(label)}<input type="text" name="{g}_{k}" maxlength="{mx}" value="{E(v, quote=True)}"></label>'

    def group(title, g):
        return f'<div><b>{E(title)}</b>' + "".join(inp(g, k, lab, mx, m) for k, lab, mx, m in ha_cover.FIELDS[g]) + '</div>'
    return (
        '<details><summary>Deckblatt: Ersteller und Kunde (optional)</summary>'
        '<form method="post" action="cover">'
        f'<label class="opt"><input type="checkbox" name="enabled" value="1"{" checked" if c["enabled"] else ""}> Angaben auf dem Deckblatt anzeigen</label>'
        '<div class="opts" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr))">'
        + group("Ersteller (Firma)", "creator") + group("Kunde", "customer") + group("Dokument", "doc") +
        '</div><p class="msg">Das PDF enthält dann diese Namen und Adressen. Du bist für Weitergabe und Datenschutz selbst verantwortlich.</p>'
        '<p><button class="sec" style="margin-left:0">Deckblatt speichern</button></p></form></details>')


def logo_block():
    b = ha_brand.load(OUT_DIR)
    chk = lambda m: " checked" if b["mode"] == m else ""
    cust = ('<img src="branding/logo" alt="Eigenes Logo" style="max-height:40px;vertical-align:middle;margin-left:8px;background:#fff;border-radius:4px;padding:2px">'
            if b["custom"] else '<span class="msg"> (noch kein eigenes Logo hochgeladen)</span>')
    return (
        '<details><summary>Logo im PDF</summary>'
        '<form method="post" action="branding"><div class="opts" style="grid-template-columns:1fr">'
        f'<label class="opt"><input type="radio" name="mode" value="layvo"{chk("layvo")}> layvo-Logo</label>'
        f'<label class="opt"><input type="radio" name="mode" value="none"{chk("none")}> Kein Logo</label>'
        f'<label class="opt"><input type="radio" name="mode" value="custom" id="r_custom"{chk("custom")}> Eigenes Logo (PNG oder JPG, max. 2 MB){cust}</label>'
        '</div><p><input type="file" id="lf" accept="image/png,image/jpeg"> '
        '<input type="hidden" name="data" id="ld"><button class="sec" style="margin-left:0">Logo speichern</button></p></form>'
        '<script>document.getElementById("lf").onchange=function(){var f=this.files[0];if(!f)return;'
        'if(f.size>2000000){alert("Datei zu gross (max. 2 MB)");this.value="";return;}'
        'var r=new FileReader();r.onload=function(){document.getElementById("ld").value=r.result.split(",")[1];'
        'document.getElementById("r_custom").checked=true;};r.readAsDataURL(f);};</script></details>')


def head_html(refresh=""):
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">{refresh}
<meta name="viewport" content="width=device-width,initial-scale=1"><title>layvo Doku</title>
<style>
:root{{--bg:#fafbfc;--fg:#1f2933;--card:#fff;--line:#e1e5e9;--muted:#52606d;--accent:#03a9f4;--link:#0277bd;--errbg:#fdecea;color-scheme:light}}
@media (prefers-color-scheme: dark){{:root{{--bg:#1c1c1c;--fg:#e1e1e1;--card:#2a2a2a;--line:#3c3c3c;--muted:#a8a8a8;--link:#4fc3f7;--errbg:#4a2626;color-scheme:dark}}}}
body{{font-family:system-ui,sans-serif;margin:0;padding:24px;max-width:820px;color:var(--fg);background:var(--bg)}}
h1{{margin-top:0}} h2{{font-size:15px;margin:18px 0 6px;color:var(--muted)}}
button{{background:var(--accent);color:#fff;border:0;padding:12px 22px;border-radius:8px;font-size:16px;cursor:pointer}}
button[disabled]{{opacity:.5;cursor:wait}} button.del{{background:transparent;color:var(--link);border:1px solid var(--line);padding:4px 10px;font-size:13px}} a.btn{{display:inline-block;padding:12px 22px;border-radius:8px;font-size:16px;text-decoration:none;margin-left:8px}} a.btn.sec{{border:1px solid var(--link);color:var(--link)}} label.fld{{display:block;margin:6px 0;font-size:13px;color:var(--muted)}} label.fld input,label.fld textarea{{display:block;width:100%;box-sizing:border-box;margin-top:2px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);font:inherit}} button.sec{{background:transparent;color:var(--link);border:1px solid var(--link);margin-left:8px}} table{{border-collapse:collapse;width:100%;margin-top:18px;background:var(--card)}}
td,th{{border:1px solid var(--line);padding:8px 10px;text-align:left}} .msg{{margin:14px 0;color:var(--muted)}}
.tgl{{margin:4px 0}} td.cb,th.cb{{width:28px;text-align:center}} .tgl button.del{{margin-left:6px}} button.mini{{background:transparent;color:var(--link);border:1px solid var(--line);padding:4px 10px;font-size:13px;margin-right:6px}}
.opts{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px;margin:8px 0}}
.opt{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;cursor:pointer;display:block}}
details{{margin:10px 0}} summary{{cursor:pointer;color:var(--link)}} a{{color:var(--link)}}
.err{{background:var(--errbg);padding:10px;overflow:auto;font-size:12px}}
</style>
<script>
try{{const cs=getComputedStyle(window.parent.document.documentElement);
const m={{'--bg':'--primary-background-color','--fg':'--primary-text-color','--card':'--card-background-color','--line':'--divider-color','--muted':'--secondary-text-color','--accent':'--primary-color'}};
for(const k in m){{const v=cs.getPropertyValue(m[k]).trim();if(v)document.documentElement.style.setProperty(k,v);}}
const c=getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
const t=document.createElement('canvas').getContext('2d');t.fillStyle=c;t.fillRect(0,0,1,1);const d=t.getImageData(0,0,1,1).data;
document.documentElement.style.colorScheme=(0.299*d[0]+0.587*d[1]+0.114*d[2])<128?'dark':'light';}}catch(e){{}}
</script></head><body>"""


def schedule_page(msg="", ok=True):
    c = sched()
    E = html.escape
    secs = "".join(checkbox("sections", k, label, k in c["sections"]) for k, label in ha_doc.SECTIONS)
    areas = get_areas()
    area_html = ""
    if areas:
        sel = c["areas"]
        items = "".join(checkbox("areas", aid, name, sel is None or aid in sel) for aid, name in areas)
        items += checkbox("areas", "_none", "Ohne Bereich", sel is None or "_none" in sel)
        area_html = (f'<details><summary>Bereiche auswählen ({len(areas) + 1})</summary><input type="hidden" name="areas_present" value="1">'
                     f'{toggle_bar("areas")}<div class="opts">{items}</div></details>')
    flt = (checkbox("hide_diag", "1", "Konfigurations- und Diagnose-Entitäten ausblenden (kürzere Geräteliste)", c["hide_diagnostic"]) +
           checkbox("only_problems", "1", "Automatisierungen, Skripte, Szenen: nur mit fehlenden Entitäten", c["only_problems"]))
    note = f'<p class="msg"><b>{E(msg)}</b></p>' if msg else ""
    return head_html() + f"""<h1>Einstellungen Monatsbericht</h1>
<p><a href="./">&larr; Zurück zu layvo Doku</a></p>{note}
<p class="msg">Einmal im Monat erstellt das Add-on automatisch ein PDF. Das Add-on muss dafür laufen («Beim Systemstart starten» einschalten). Änderungen gelten sofort, ein Neustart ist nicht nötig. Das Logo und die Deckblatt-Angaben der Hauptseite werden übernommen.</p>
<form method="post" action="schedule">
<h2>Zeitplan</h2>
<div class="opts" style="grid-template-columns:1fr">{checkbox("enabled", "1", "Monatlichen Bericht automatisch erstellen", c["enabled"])}</div>
<div class="opts" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
<label class="fld">Tag im Monat (1 bis 28)<input type="number" name="day" min="1" max="28" value="{c['day']}" required></label>
<label class="fld">Uhrzeit (HH:MM, Zeitzone von Home Assistant)<input type="text" name="time" pattern="([01][0-9]|2[0-3]):[0-5][0-9]" value="{E(c['time'], quote=True)}" required></label>
<label class="fld">Anzahl aufbewahrter PDFs (1 bis 100)<input type="number" name="keep_last" min="1" max="100" value="{c['keep_last']}" required></label>
</div>
<p class="msg">Die Anzahl gilt nur für automatisch erstellte Berichte (<code>ha_monatsbericht_…</code>). Manuell erstellte Dateien löschst du auf der Hauptseite.</p>
<h2>Abschnitte</h2>{toggle_bar("sections")}<div class="opts">{secs}</div>
<h2>Optionen</h2><div class="opts" style="grid-template-columns:1fr">{flt}</div>
{area_html}
<p><button>Speichern</button><a class="btn sec" href="./">Abbrechen</a></p></form>
<p class="msg">{E(schedule_info())}</p>
</body></html>"""


def page():
    files = sorted((f for f in os.listdir(OUT_DIR) if is_doc_file(f)),
                   key=lambda f: os.path.getmtime(os.path.join(OUT_DIR, f)), reverse=True)
    rows = "".join(
        f'<tr><td class="cb"><input type="checkbox" name="file" value="{html.escape(f)}" aria-label="{html.escape(f)} auswählen"></td>'
        f'<td><a href="files/{html.escape(f)}" target="_blank">{html.escape(f)}</a></td>'
        f'<td>{os.path.getsize(os.path.join(OUT_DIR, f)) // 1024} KB</td>'
        f'<td><button class="del" name="one" value="{html.escape(f)}" title="Löschen" '
        f'onclick="return confirm(\'Datei wirklich löschen?\')">Löschen</button></td></tr>' for f in files
    ) or '<tr><td colspan="4">Noch keine Dateien erstellt.</td></tr>'
    multi_js = ("var n=this.form.querySelectorAll('input[name=file]:checked').length;"
                "if(!n){alert('Bitte mindestens eine Datei auswählen.');return false;}"
                "return confirm(n===1?'1 Datei wirklich löschen?':n+' Dateien wirklich löschen?');")
    multi = toggle_bar("file", f'<button class="del" name="multi" value="1" onclick="{multi_js}">Ausgewählte löschen</button>') if files else ""
    refresh = '<meta http-equiv="refresh" content="2">' if state["running"] else ""
    btn = "disabled" if state["running"] else ""
    err = f'<pre class="err">{html.escape(state["error"])}</pre>' if state["error"] else ""
    boxes = "".join(checkbox("sections", k, label, k in state["sections"]) for k, label in ha_doc.SECTIONS)
    areas = get_areas()
    area_html = ""
    if areas:
        sel = state["areas"]
        items = "".join(checkbox("areas", aid, name, sel is None or aid in sel) for aid, name in areas)
        items += checkbox("areas", "_none", "Ohne Bereich", sel is None or "_none" in sel)
        area_html = (f'<details><summary>Bereiche auswählen ({len(areas) + 1})</summary><input type="hidden" name="areas_present" value="1">'
                     f'{toggle_bar("areas")}<div class="opts">{items}</div></details>')
    logo_html = cover_block() + logo_block()
    extra = (checkbox("save_snap", "1", "Änderungsvergleich: diesen Stand als neue Referenz speichern (sonst nur Vergleich; automatische Berichte speichern immer)", state["save_snap"]) +
             checkbox("hide_diag", "1", "Konfigurations- und Diagnose-Entitäten ausblenden (kürzere Geräteliste)", state["hide_diag"]) +
             checkbox("only_problems", "1", "Automatisierungen, Skripte, Szenen: nur mit fehlenden Entitäten", state["only_problems"]))
    return head_html(refresh) + f"""
<h1>Home Assistant Dokumentation</h1>
<p>Erstellt ein PDF deiner Installation. Wähle, was enthalten sein soll.</p>
<form method="post" action="generate" onsubmit="if(!document.querySelector('input[name=sections]:checked')){{alert('Bitte mindestens einen Abschnitt auswählen.');return false;}}">
<h2>Abschnitte</h2>{toggle_bar("sections")}<div class="opts">{boxes}</div>
<h2>Optionen</h2><div class="opts" style="grid-template-columns:1fr">{extra}</div>
{area_html}
<p><button name="action" value="generate" {btn}>PDF erstellen</button>
<button name="action" value="xlsx" class="sec" {btn} title="Excel-Datei mit Geräten (Entitäten ein-/ausklappbar), Netzwerk und Integrationen. Verwendet Bereiche und Diagnose-Filter.">Excel erstellen</button>
<a class="btn sec" href="notes" title="Eigene Bemerkungen zu Bereichen, Geräten, Entitäten, Automatisierungen u. a. erfassen">Bemerkungen erfassen</a>
<a class="btn sec" href="schedule" title="Automatischen Monatsbericht einschalten, Zeitpunkt, Abschnitte und Filter festlegen">Einstellungen Monatsbericht</a></p></form>
<h2>Darstellung</h2>
{logo_html}
<div class="msg">{html.escape(state["msg"])}</div>{err}
<form method="post" action="delete">{multi}<table><tr><th class="cb"></th><th>Datei</th><th>Grösse</th><th></th></tr>{rows}</table></form>
<p class="msg">{html.escape(schedule_info())}<br>Ablage: Freigabe «share» → Ordner {html.escape(OUT_FOLDER)}</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _allowed(self):
        if DEMO:
            return True
        if self.client_address[0] != SUPERVISOR_IP:
            self.send_error(403)
            return False
        return True

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._allowed():
            return
        path = self.path.split("?")[0]
        if path.endswith("/schedule") or path == "schedule":
            return self._send(200, schedule_page())
        if path.endswith("/notes") or path == "notes":
            q = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            try:
                body = ha_notes.page(light_data(force="reload" in q), ha_notes.load(NOTES_FILE), diag="diag" in q, saved="saved" in q)
            except Exception:
                body = "<pre>" + html.escape(traceback.format_exc()) + "</pre>"
            return self._send(200, body)
        if path.endswith("/branding/logo") or path == "branding/logo":
            p = ha_brand.load(OUT_DIR)["custom"]
            if p and os.path.isfile(p):
                with open(p, "rb") as f:
                    return self._send(200, f.read(), "image/png" if p.endswith(".png") else "image/jpeg")
            return self.send_error(404)
        if "/files/" in path:
            name = os.path.basename(unquote(path.split("/files/", 1)[1]))
            full = os.path.join(OUT_DIR, name)
            if name.endswith((".pdf", ".xlsx")) and os.path.isfile(full):
                xl = name.endswith(".xlsx")
                with open(full, "rb") as f:
                    return self._send(200, f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if xl else "application/pdf",
                                      {"Content-Disposition": f'{"attachment" if xl else "inline"}; filename="{name}"'})
            return self.send_error(404)
        self._send(200, page())

    def do_POST(self):
        if not self._allowed():
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = parse_qs(raw)
        if self.path.split("?")[0].endswith("/schedule") or self.path.split("?")[0] == "schedule":
            try:
                ids = {a for a, _ in get_areas()} | {"_none"}
                ha_schedule.save_from_form(OUT_DIR, parse_qs(raw), ALL_SECTIONS, ids)
                return self._send(200, schedule_page("Einstellungen gespeichert."))
            except ValueError as e:
                return self._send(200, schedule_page(str(e)))
        if self.path.split("?")[0].endswith("/cover") or self.path.split("?")[0] == "cover":
            try:
                ha_cover.save_from_form(OUT_DIR, parse_qs(raw))
                state["msg"] = "Deckblatt-Angaben gespeichert."
            except Exception as e:
                state["msg"] = f"Deckblatt nicht gespeichert: {e}"
            return self._send(303, "", extra={"Location": "./"})
        if self.path.split("?")[0].endswith("/branding") or self.path.split("?")[0] == "branding":
            f = parse_qs(raw)
            try:
                if f.get("data") and f["data"][0]:
                    ha_brand.save_custom(OUT_DIR, f["data"][0])
                ha_brand.save_mode(OUT_DIR, (f.get("mode") or ["layvo"])[0])
                state["msg"] = "Logo-Einstellung gespeichert."
            except Exception as e:
                state["msg"] = f"Logo nicht gespeichert: {e}"
            return self._send(303, "", extra={"Location": "./"})
        if self.path.split("?")[0].endswith("/notes") or self.path.split("?")[0] == "notes":
            try:
                form_all = parse_qs(raw, keep_blank_values=True)
                ha_notes.save(NOTES_FILE, ha_notes.apply_post(ha_notes.load(NOTES_FILE), form_all, ha_notes.labels_for(light_data())))
            except Exception:
                state["error"] = traceback.format_exc()
            return self._send(303, "", extra={"Location": "notes?saved=1"})
        if self.path.split("?")[0].endswith("/delete") or self.path.split("?")[0] == "delete":
            wanted = form["one"][:1] if form.get("one") else form.get("file", [])
            done = []
            for name in dict.fromkeys(os.path.basename(x) for x in wanted):
                if is_doc_file(name) and os.path.isfile(os.path.join(OUT_DIR, name)):
                    os.remove(os.path.join(OUT_DIR, name))
                    done.append(name)
            if not done:
                state["msg"] = "Keine Datei gelöscht (keine ausgewählt)."
            elif len(done) == 1:
                state["msg"] = f"Gelöscht: {done[0]}"
            else:
                state["msg"] = f"Gelöscht: {len(done)} Dateien"
            return self._send(303, "", extra={"Location": "./"})
        sections = [x for x in form.get("sections", []) if x in ALL_SECTIONS]
        area_ids = {a for a, _ in get_areas()} | {"_none"}
        areas = [x for x in form.get("areas", []) if x in area_ids] if "areas_present" in form else None
        opts = {"save_snapshot": "save_snap" in form, "hide_diagnostic": "hide_diag" in form, "only_problems": "only_problems" in form, "areas": areas}
        action = (form.get("action") or ["generate"])[0]
        if not sections:
            state["msg"] = "Bitte mindestens einen Abschnitt auswählen."
        else:
            state.update(sections=sections, areas=areas, save_snap=opts["save_snapshot"], hide_diag=opts["hide_diagnostic"], only_problems=opts["only_problems"])
            start_generation(sections, opts, fmt="xlsx" if action == "xlsx" else "pdf")
        self._send(303, "", extra={"Location": "./"})

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


def _stop(signum, frame):
    """Beim Stoppen durch den Supervisor (SIGTERM) sofort sauber beenden statt nach 10 Sekunden abgebrochen zu werden."""
    print("HA-Doku-Server wird beendet", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    print(f"HA-Doku-Server auf Port {PORT}", flush=True)
    threading.Thread(target=scheduler_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
