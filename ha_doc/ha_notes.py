"""Eigene Bemerkungen: Speicherung (notes.json in share/ha_doc) und Erfassungsseite."""
import html
import json
import os
import time
from collections import defaultdict

import ha_doc

_E = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return {"general": d.get("general", ""), "items": d.get("items", {}), "labels": d.get("labels", {})}
    except (OSError, ValueError):
        return {"general": "", "items": {}, "labels": {}}


def save(path, notes):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def ent_key(e):
    return e.get("entry_id") or f"{e.get('domain')}|{e.get('title')}"


def labels_for(data):
    """Schlüssel -> lesbare Bezeichnung (für den Änderungsvergleich)."""
    n = ha_doc.Namer(data)
    lab = {}
    for a in data["areas"]:
        lab[f"area:{a['area_id']}"] = "Bereich: " + a["name"]
    lab["area:_none"] = "Bereich: Ohne Bereich"
    for d in data["devices"]:
        lab[f"device:{d['id']}"] = "Gerät: " + (d.get("name_by_user") or d.get("name") or "?")
    for e in data["entities"]:
        lab[f"entity:{e['entity_id']}"] = "Entität: " + e["entity_id"]
    for e in data["entries"]:
        lab[f"integration:{ent_key(e)}"] = "Integration: " + (e.get("title") or e.get("domain") or "?")
    for x in ha_doc.collect_network(data):
        lab[f"net:{x['mac'] or x['ip']}"] = f"Netzwerk: {x['name']} ({x['ip']})"
    for kind, coll in (("automation", data["automations"]), ("script", data["scripts"]), ("scene", data["scenes"])):
        for it in coll:
            lab[f"{kind}:{it['entity_id']}"] = f"{kind.capitalize()}: " + (it["attrs"].get("friendly_name") or it["entity_id"])
    return lab


CSS = """
:root{--bg:#fafbfc;--fg:#1f2933;--card:#fff;--line:#e1e5e9;--muted:#52606d;--accent:#03a9f4;--link:#0277bd;--note:#fff8dc;color-scheme:light}
@media (prefers-color-scheme: dark){:root{--bg:#1c1c1c;--fg:#e1e1e1;--card:#2a2a2a;--line:#3c3c3c;--muted:#a8a8a8;--link:#4fc3f7;--note:#3a3420;color-scheme:dark}}
body{font-family:system-ui,sans-serif;margin:0;padding:24px;max-width:980px;color:var(--fg);background:var(--bg)}
h1{margin-top:0} h2{font-size:16px;margin:22px 0 6px}
a{color:var(--link)} button{background:var(--accent);color:#fff;border:0;padding:10px 20px;border-radius:8px;font-size:15px;cursor:pointer}
input[type=text],textarea,input[type=search]{box-sizing:border-box;width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);font:inherit}
textarea{min-height:44px;resize:vertical}
details{border:1px solid var(--line);border-radius:8px;margin:6px 0;background:var(--card)}
details details{margin:4px 8px;background:transparent}
summary{cursor:pointer;padding:8px 10px;list-style:none} summary::-webkit-details-marker{display:none}
summary::before{content:"+";display:inline-block;width:1.3em;color:var(--link);font-weight:700}
details[open]>summary::before{content:"\\2212"}
.body{padding:4px 10px 10px}.sub{color:var(--muted);font-size:12px;margin-left:6px}
.mark{color:#e0a800;margin-left:6px}
.row{display:grid;grid-template-columns:minmax(120px,1fr) minmax(160px,1.1fr) 1.6fr;gap:8px;align-items:center;margin:4px 0}
.row code{font-size:12px;color:var(--muted);word-break:break-all}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 0;z-index:5;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.bar input[type=search]{max-width:340px}
.msg{color:var(--muted);margin:8px 0}.ok{color:#2e7d32}
.hint{color:var(--muted);font-size:13px}
"""

JS = """
try{const cs=getComputedStyle(window.parent.document.documentElement);
const m={'--bg':'--primary-background-color','--fg':'--primary-text-color','--card':'--card-background-color','--line':'--divider-color','--muted':'--secondary-text-color','--accent':'--primary-color'};
for(const k in m){const v=cs.getPropertyValue(m[k]).trim();if(v)document.documentElement.style.setProperty(k,v);}}catch(e){}
const q=document.getElementById('q');
function filt(){const t=q.value.trim().toLowerCase();
document.querySelectorAll('details.dev,details.flat').forEach(d=>{const ok=!t||d.dataset.s.includes(t);d.style.display=ok?'':'none';if(t&&ok)d.open=true;});
document.querySelectorAll('details.grp').forEach(g=>{const any=[...g.querySelectorAll('details.dev,details.flat')].some(x=>x.style.display!=='none');
const ok=!t||any||(g.dataset.s||'').includes(t);g.style.display=ok?'':'none';if(t&&any)g.open=true;});}
q.addEventListener('input',filt);
"""


def _mark(txt):
    return '<span class="mark" title="Bemerkung vorhanden">&#9679;</span>' if txt else ""


def page(data, notes, diag=False, saved=False):
    it = notes["items"]
    N = lambda kind, key: it.get(f"{kind}:{key}", "")
    nm = ha_doc.Namer(data).names
    dev_by = {d["id"]: d for d in data["devices"]}
    ent_by_dev = defaultdict(list)
    area_of = {}
    ent_cat = {e["entity_id"]: e.get("entity_category") for e in data["entities"]}
    for e in data["entities"]:
        if e.get("device_id"):
            ent_by_dev[e["device_id"]].append(e["entity_id"])
        area_of[e["entity_id"]] = e.get("area_id") or dev_by.get(e.get("device_id"), {}).get("area_id")
    with_dev = {e["entity_id"] for e in data["entities"] if e.get("device_id")}
    floors = {f["floor_id"]: f for f in data["floors"]}

    def vis(ents):
        return sorted(ents) if diag else sorted(x for x in ents if ent_cat.get(x) not in ("config", "diagnostic"))

    def erow(e):
        v = N("entity", e)
        label = nm.get(e, "")
        return (f'<div class="row"><span>{_E(label if label != e else "")}</span><code>{_E(e)}</code>'
                f'<input type="text" name="n:entity:{_E(e)}" value="{_E(v)}" placeholder="Bemerkung zur Entität"></div>')

    def ta(name, v, ph):
        return f'<textarea name="{_E(name)}" placeholder="{_E(ph)}">{_E(v)}</textarea>'

    out = []
    # Allgemein
    out.append(f'<details class="grp" data-s="allgemein"><summary><b>Allgemeine Bemerkung</b> <span class="sub">erscheint auf dem Deckblatt des PDFs</span>{_mark(notes["general"])}</summary>'
               f'<div class="body">{ta("n:general", notes["general"], "z. B. Standort, Verantwortlicher, Stand der Dokumentation")}</div></details>')
    # Bereiche und Geräte
    areas = sorted(data["areas"], key=lambda a: (floors.get(a.get("floor_id"), {}).get("level", 99), a["name"]))
    areas = areas + [{"area_id": None, "name": "Ohne Bereich", "floor_id": None}]
    inner = []
    for a in areas:
        aid = a["area_id"]
        devs = sorted([d for d in data["devices"] if d.get("area_id") == aid], key=lambda d: (d.get("name_by_user") or d.get("name") or "").lower())
        loose = vis([e for e, ar in area_of.items() if ar == aid and e not in with_dev])
        if not devs and not loose and not (aid and N("area", aid)):
            continue
        fl = floors.get(a.get("floor_id"), {}).get("name")
        akey = aid or "_none"
        blocks = []
        for d in devs:
            dn = d.get("name_by_user") or d.get("name") or "?"
            ents = vis(ent_by_dev.get(d["id"], []))
            has = bool(N("device", d["id"])) or any(N("entity", e) for e in ents)
            search = (dn + " " + (d.get("manufacturer") or "") + " " + (d.get("model") or "") + " " + " ".join(ents) + " " + " ".join(nm.get(e, "") for e in ents)).lower()
            blocks.append(f'<details class="dev" data-s="{_E(search)}"><summary>{_E(dn)}<span class="sub">{_E(((d.get("manufacturer") or "") + " " + (d.get("model") or "")).strip())}</span>{_mark(has)}</summary>'
                          f'<div class="body">{ta("n:device:" + d["id"], N("device", d["id"]), "Bemerkung zum Gerät")}'
                          + "".join(erow(e) for e in ents) + '</div></details>')
        if loose:
            search = " ".join(loose).lower() + " " + " ".join(nm.get(e, "") for e in loose).lower()
            blocks.append(f'<details class="dev" data-s="{_E(search)}"><summary>Entitäten ohne Gerät{_mark(any(N("entity", e) for e in loose))}</summary>'
                          f'<div class="body">' + "".join(erow(e) for e in loose) + '</div></details>')
        title = a["name"] + (f" ({fl})" if fl else "")
        inner.append(f'<details class="grp" data-s="{_E(title.lower())}"><summary><b>{_E(title)}</b>{_mark(N("area", akey))}</summary><div class="body">'
                     f'{ta("n:area:" + akey, N("area", akey), "Bemerkung zum Bereich")}' + "".join(blocks) + '</div></details>')
    out.append('<h2>Bereiche und Geräte</h2>' + "".join(inner))

    def flat_section(title, kind, rows):
        """rows: (key, label, sub, search)"""
        if not rows:
            return ""
        body = "".join(
            f'<details class="flat" data-s="{_E(s.lower())}"><summary>{_E(lab)}<span class="sub">{_E(sub)}</span>{_mark(N(kind, key))}</summary>'
            f'<div class="body">{ta("n:" + kind + ":" + key, N(kind, key), "Bemerkung")}</div></details>' for key, lab, sub, s in rows)
        return f'<h2>{_E(title)}</h2><details class="grp" data-s="{_E(title.lower())}"><summary><b>{_E(title)} ({len(rows)})</b></summary><div class="body">{body}</div></details>'

    out.append(flat_section("Integrationen", "integration", [
        (ent_key(e), e.get("title") or e.get("domain") or "?", e.get("domain") or "", f"{e.get('title')} {e.get('domain')}")
        for e in sorted(data["entries"], key=lambda x: (x.get("title") or x.get("domain") or "").lower())]))
    out.append(flat_section("Netzwerk-Clients (nur UniFi / Fritz!Box)", "net", [
        (x["mac"] or x["ip"], x["name"], f"{x['ip']}  {x['mac']}", f"{x['name']} {x['ip']} {x['mac']}")
        for x in sorted(ha_doc.collect_network(data), key=lambda x: x["name"].lower())]))
    for title, kind, coll in (("Automatisierungen", "automation", data["automations"]), ("Skripte", "script", data["scripts"]), ("Szenen", "scene", data["scenes"])):
        out.append(flat_section(title, kind, [
            (i["entity_id"], i["attrs"].get("friendly_name") or i["entity_id"], i["entity_id"], f"{i['attrs'].get('friendly_name')} {i['entity_id']}")
            for i in sorted(coll, key=lambda x: (x["attrs"].get("friendly_name") or x["entity_id"]).lower())]))

    diag_link = ('<a href="notes">Diagnose-Entitäten ausblenden</a>' if diag else '<a href="notes?diag=1">auch Konfigurations-/Diagnose-Entitäten anzeigen</a>')
    return ("<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>Bemerkungen</title><style>{CSS}</style></head><body>"
            "<h1>Bemerkungen erfassen</h1>"
            '<p><a href="./">&larr; zurück zur Dokumentation</a></p>'
            '<p class="hint">Klicke auf ein Plus, um ein Gerät aufzuklappen und Bemerkungen zum Gerät oder zu einzelnen Entitäten zu erfassen. '
            'Die Bemerkungen erscheinen im PDF, in der Excel-Datei und im Änderungsvergleich. Mit &#9679; markierte Einträge haben bereits eine Bemerkung. '
            f'Gespeichert wird in <code>share/ha_doc/notes.json</code> (bleibt bei einer Neuinstallation erhalten). {diag_link}</p>'
            + ('<p class="msg ok">Gespeichert.</p>' if saved else "") +
            '<form method="post" action="notes"><div class="bar"><button>Speichern</button>'
            '<input type="search" id="q" placeholder="Suchen (Gerät, Entität, Name …)"></div>'
            + "".join(out) +
            f'<p><button>Speichern</button></p></form><script>{JS}</script></body></html>')


def apply_post(notes, form, labels):
    """Übernimmt die gesendeten Felder (n:<Art>:<Schlüssel>); leere Felder löschen die Bemerkung."""
    items, lab = notes["items"], notes["labels"]
    for k, vals in form.items():
        if not k.startswith("n:"):
            continue
        v = (vals[0] if vals else "").strip()
        if k == "n:general":
            notes["general"] = v
            continue
        key = k[2:]
        if v:
            items[key] = v
            lab[key] = labels.get(key, key)
        else:
            items.pop(key, None)
            lab.pop(key, None)
    return notes
