"""Optionaler Änderungsvergleich: speichert Momentaufnahmen (JSON) und vergleicht den aktuellen Stand mit dem letzten."""
import datetime as dt
import difflib
import json
import os

import ha_doc

KEEP_SNAPSHOTS = 24
MAX_LIST = 200
MAX_DIFF_LINES = 40


def snapshot(data, notes=None):
    areas = {a["area_id"]: a["name"] for a in data["areas"]}
    devices = {d["id"]: {"Name": d.get("name_by_user") or d.get("name") or "?", "Hersteller": d.get("manufacturer") or "",
                         "Modell": d.get("model") or "", "Bereich": areas.get(d.get("area_id"), ""), "Firmware": d.get("sw_version") or ""}
               for d in data["devices"]}
    dev_name = {k: v["Name"] for k, v in devices.items()}
    entities = {e["entity_id"]: {"Integration": e.get("platform") or "", "Gerät": dev_name.get(e.get("device_id"), ""),
                                 "Deaktiviert": e.get("disabled_by") or ""} for e in data["entities"]}
    entries = {(e.get("entry_id") or f"{e.get('domain')}|{e.get('title')}"): {"Name": e.get("title") or e.get("domain") or "?",
                                                                               "Integration": e.get("domain") or ""} for e in data["entries"]}

    def items(coll):
        return {i["entity_id"]: {"Name": (i.get("config") or {}).get("alias") or (i.get("config") or {}).get("name")
                                 or (i.get("attrs") or {}).get("friendly_name") or i["entity_id"], "config": i.get("config")} for i in coll}

    net = {x["mac"] or x["ip"]: {"Name": x["name"], "IP": x["ip"], "VLAN": "" if x["vlan"] is None else str(x["vlan"])}
           for x in ha_doc.collect_network(data)}
    return {"time": dt.datetime.now().isoformat(timespec="seconds"), "version": data["config"].get("version", "?"),
            "areas": {k: {"Name": v} for k, v in areas.items()}, "devices": devices, "entities": entities, "entries": entries,
            "automations": items(data["automations"]), "scripts": items(data["scripts"]), "scenes": items(data["scenes"]), "network": net,
            "notes": {k: {"Name": (notes.get("labels") or {}).get(k, k), "Bemerkung": v} for k, v in (notes or {}).get("items", {}).items() if v}}


CATEGORIES = [("areas", "Bereiche"), ("devices", "Geräte"), ("entities", "Entitäten (Registry)"), ("entries", "Integrationen"),
              ("automations", "Automatisierungen"), ("scripts", "Skripte"), ("scenes", "Szenen"), ("network", "Netzwerk (IP/MAC)"), ("notes", "Bemerkungen")]


def _title(key, v):
    return v.get("Name") or key if "Name" in v else key


def _pretty(cfg):
    return json.dumps(cfg, indent=1, sort_keys=True, ensure_ascii=False, default=str).splitlines()


def compare(prev, cur):
    base = {"cur_time": cur["time"], "cur_version": cur["version"]}
    if not prev:
        return dict(base, first=True)
    cats, total = [], 0
    for key, label in CATEGORIES:
        p, c = prev.get(key, {}), cur.get(key, {})
        added = sorted(_title(k, c[k]) + ("" if key in ("entities",) else "") for k in c.keys() - p.keys())
        removed = sorted(_title(k, p[k]) for k in p.keys() - c.keys())
        changed = []
        for k in sorted(c.keys() & p.keys()):
            fields = [(f, p[k].get(f, ""), c[k].get(f, "")) for f in c[k] if f != "config" and p[k].get(f, "") != c[k].get(f, "")]
            diff = []
            if "config" in c[k] and p[k].get("config") != c[k].get("config"):
                a, b = _pretty(p[k].get("config")), _pretty(c[k].get("config"))
                diff = [l for l in difflib.unified_diff(a, b, lineterm="", n=1) if not l.startswith(("---", "+++"))]
            if fields or diff:
                changed.append({"title": _title(k, c[k]), "fields": fields, "diff": diff})
        n = len(added) + len(removed) + len(changed)
        total += n
        cats.append({"key": key, "label": label, "added": added, "removed": removed, "changed": changed, "count": n})
    return dict(base, first=False, prev_time=prev["time"], prev_version=prev["version"], cats=cats, total=total)


def _files(folder):
    return sorted(f for f in os.listdir(folder) if f.startswith("ha_snapshot_") and f.endswith(".json")) if os.path.isdir(folder) else []


def load_latest(folder):
    files = _files(folder)
    if not files:
        return None
    try:
        with open(os.path.join(folder, files[-1]), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save(folder, snap):
    os.makedirs(folder, exist_ok=True)
    name = "ha_snapshot_" + snap["time"].replace("-", "").replace(":", "").replace("T", "_") + ".json"
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    files = _files(folder)
    for old in files[:-KEEP_SNAPSHOTS]:
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass
