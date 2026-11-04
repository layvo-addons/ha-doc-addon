"""Optionale Deckblatt-Angaben: Ersteller (Firma), Kunde, Dokumentdaten. Gespeichert in share/ha_doc/cover.json."""
import json
import os

FIELDS = {
    "creator": [("name", "Firma", 120, False), ("address", "Adresse", 300, True), ("phone", "Telefon", 60, False),
                ("email", "E-Mail", 120, False), ("web", "Webseite", 120, False)],
    "customer": [("name", "Name", 120, False), ("address", "Adresse", 300, True), ("object", "Objekt / Projekt", 160, False)],
    "doc": [("version", "Version / Stand", 60, False), ("author", "Bearbeiter", 120, False)],
}


def empty():
    return {"enabled": False, **{g: {k: "" for k, *_ in f} for g, f in FIELDS.items()}}


def load(base):
    c = empty()
    try:
        with open(os.path.join(base, "cover.json"), encoding="utf-8") as f:
            d = json.load(f)
        c["enabled"] = bool(d.get("enabled"))
        for g, flds in FIELDS.items():
            for k, _l, mx, _m in flds:
                c[g][k] = str((d.get(g) or {}).get(k, ""))[:mx]
    except (OSError, ValueError):
        pass
    return c


def save_from_form(base, form):
    """form: dict aus parse_qs mit Feldern <gruppe>_<feld> und enabled."""
    c = empty()
    c["enabled"] = "enabled" in form
    for g, flds in FIELDS.items():
        for k, _l, mx, _m in flds:
            v = (form.get(f"{g}_{k}") or [""])[0].replace("\r", "").strip()
            c[g][k] = v[:mx]
    os.makedirs(base, exist_ok=True)
    tmp = os.path.join(base, "cover.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(base, "cover.json"))
    return c


def active(c):
    """Cover-Daten für das PDF oder None, wenn ausgeschaltet bzw. leer."""
    if not c or not c.get("enabled"):
        return None
    if not any(v for g in FIELDS for v in c[g].values()):
        return None
    return c
