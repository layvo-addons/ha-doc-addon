"""Einstellungen für den automatischen Monatsbericht. Gespeichert in share/ha_doc/schedule.json (bleibt bei Neuinstallation erhalten)."""
import json
import os
import re

FILE = "schedule.json"


def defaults(all_sections):
    return {"enabled": False, "day": 1, "time": "03:00", "keep_last": 12,
            "sections": [k for k in all_sections if k != "aenderungen"],
            "hide_diagnostic": True, "only_problems": False, "areas": None}


def load(base, all_sections, legacy_options=None, legacy_ui=None):
    """Lädt schaltbare Werte. Fehlt die Datei, werden alte Werte aus der Add-on-Konfiguration bzw. der früheren
    «Auswahl für Monatsbericht» übernommen (einmalige Migration beim ersten Start)."""
    s = defaults(all_sections)
    path = os.path.join(base, FILE)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        return _clean(d, s, all_sections)
    o = legacy_options or {}
    d = {"enabled": o.get("schedule_enabled", False), "day": o.get("schedule_day", 1), "time": o.get("schedule_time", "03:00"),
         "keep_last": o.get("keep_last", 12)}
    if any(k.startswith("schedule_") for k in o):
        d["sections"] = [k for k in all_sections if o.get(f"schedule_{k}", k != "aenderungen")]
        d["hide_diagnostic"] = o.get("schedule_hide_diagnostic", True)
        d["only_problems"] = o.get("schedule_only_problems", False)
    if legacy_ui and os.path.isfile(legacy_ui) and o.get("schedule_from_ui", True):
        try:
            with open(legacy_ui, encoding="utf-8") as f:
                u = json.load(f)
            d.update(sections=u.get("sections"), hide_diagnostic=bool(u.get("hide_diagnostic")),
                     only_problems=bool(u.get("only_problems")), areas=u.get("areas"))
        except (OSError, ValueError):
            pass
    return _clean(d, s, all_sections)


def _clean(d, base, all_sections):
    s = dict(base)
    s["enabled"] = bool(d.get("enabled", s["enabled"]))
    try:
        s["day"] = min(28, max(1, int(d.get("day", s["day"]))))
        s["keep_last"] = min(100, max(1, int(d.get("keep_last", s["keep_last"]))))
    except (TypeError, ValueError):
        pass
    t = str(d.get("time", s["time"]))
    s["time"] = t if re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", t) else s["time"]
    secs = [x for x in (d.get("sections") or []) if x in all_sections]
    s["sections"] = secs or s["sections"]
    s["hide_diagnostic"] = bool(d.get("hide_diagnostic", s["hide_diagnostic"]))
    s["only_problems"] = bool(d.get("only_problems", s["only_problems"]))
    a = d.get("areas")
    s["areas"] = [str(x) for x in a] if isinstance(a, list) else None
    return s


def save_from_form(base, form, all_sections, area_ids):
    """form = parse_qs-Dict. Gibt die gespeicherten Einstellungen zurück oder wirft ValueError mit Meldung."""
    day = int((form.get("day") or ["1"])[0] or 1)
    keep = int((form.get("keep_last") or ["12"])[0] or 12)
    t = (form.get("time") or ["03:00"])[0].strip()
    if not 1 <= day <= 28:
        raise ValueError("Tag im Monat muss zwischen 1 und 28 liegen.")
    if not 1 <= keep <= 100:
        raise ValueError("Anzahl PDFs muss zwischen 1 und 100 liegen.")
    if not re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", t):
        raise ValueError("Uhrzeit bitte im Format HH:MM angeben.")
    secs = [x for x in form.get("sections", []) if x in all_sections]
    if not secs:
        raise ValueError("Bitte mindestens einen Abschnitt auswählen.")
    areas = None
    if "areas_present" in form:
        sel = [x for x in form.get("areas", []) if x in area_ids]
        areas = None if set(sel) >= set(area_ids) else sel
    s = {"enabled": "enabled" in form, "day": day, "time": t, "keep_last": keep, "sections": secs,
         "hide_diagnostic": "hide_diag" in form, "only_problems": "only_problems" in form, "areas": areas}
    os.makedirs(base, exist_ok=True)
    tmp = os.path.join(base, FILE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(base, FILE))
    return s
