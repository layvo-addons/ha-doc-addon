#!/usr/bin/env python3
"""
ha_doc - Home Assistant Dokumentation als PDF (Prototyp)

Verwendung:
    python ha_doc.py --url http://homeassistant.local:8123 --token <LONG_LIVED_TOKEN> -o ha_doku.pdf
    python ha_doc.py --demo -o demo.pdf          # ohne HA, mit Beispieldaten

Abhaengigkeiten:  pip install reportlab requests websocket-client
Token erstellen:  HA-Profil -> Sicherheit -> Langlebige Zugriffstoken
"""
import argparse
import ipaddress
import re
import datetime as dt
import json
import sys
from collections import defaultdict
from xml.sax.saxutils import escape

# --------------------------------------------------------------------------
# 1. Daten holen
# --------------------------------------------------------------------------


class HAClient:
    def __init__(self, url, token, supervisor=False):
        import requests
        import websocket

        # Im Add-on laeuft alles ueber den Supervisor-Proxy
        self.base = "http://supervisor/core" if supervisor else url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.requests = requests
        ws_path = "/websocket" if supervisor else "/api/websocket"
        ws_url = self.base.replace("https://", "wss://").replace("http://", "ws://") + ws_path
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.ws.recv()  # auth_required
        self.ws.send(json.dumps({"type": "auth", "access_token": token}))
        if json.loads(self.ws.recv()).get("type") != "auth_ok":
            raise SystemExit("Authentifizierung fehlgeschlagen (Token pruefen).")
        self._id = 0

    def ws_call(self, msg_type, **kw):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "type": msg_type, **kw}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if not msg.get("success", True):
                    return []
                return msg.get("result")

    def get(self, path):
        r = self.requests.get(self.base + path, headers=self.headers, timeout=30)
        if r.status_code != 200:
            return None
        return r.json()


def fetch_all(url, token, supervisor=False, light=False):
    c = HAClient(url, token, supervisor)
    data = {
        "config": c.get("/api/config") or {},
        "states": c.ws_call("get_states") or [],
        "entities": c.ws_call("config/entity_registry/list") or [],
        "devices": c.ws_call("config/device_registry/list") or [],
        "areas": c.ws_call("config/area_registry/list") or [],
        "floors": c.ws_call("config/floor_registry/list") or [],
        "entries": c.ws_call("config_entries/get") or [],
        "automations": [],
        "scripts": [],
        "scenes": [],
        "blueprints": {},
    }
    for dom in () if light else ("automation", "script"):
        bp = c.ws_call("blueprint/list", domain=dom)
        data["blueprints"][dom] = bp if isinstance(bp, dict) else {}
    for st in data["states"]:
        eid = st["entity_id"]
        dom, obj = eid.split(".", 1)
        attrs = st.get("attributes", {})
        if dom == "automation":
            cfg = c.get(f"/api/config/automation/config/{attrs['id']}") if attrs.get("id") and not light else None
            data["automations"].append({"entity_id": eid, "state": st["state"], "attrs": attrs, "config": cfg})
        elif dom == "script":
            cfg = None if light else c.get(f"/api/config/script/config/{obj}")
            data["scripts"].append({"entity_id": eid, "state": st["state"], "attrs": attrs, "config": cfg})
        elif dom == "scene":
            cfg = c.get(f"/api/config/scene/config/{attrs['id']}") if attrs.get("id") and not light else None
            data["scenes"].append({"entity_id": eid, "state": st["state"], "attrs": attrs, "config": cfg})
    return data


def demo_data():
    now = dt.datetime.now().isoformat()
    st = lambda eid, s="on", **a: {"entity_id": eid, "state": s, "attributes": a, "last_changed": now}
    states = [
        st("light.wohnzimmer_decke", friendly_name="Wohnzimmer Decke"),
        st("light.kueche_spots", friendly_name="Küche Spots"),
        st("cover.wohnzimmer_storen", "open", friendly_name="Wohnzimmer Storen"),
        st("binary_sensor.bewegung_flur", "off", friendly_name="Bewegung Flur", device_class="motion"),
        st("sensor.temp_wohnzimmer", "21.4", friendly_name="Temperatur Wohnzimmer", unit_of_measurement="°C"),
        st("sensor.alter_sensor", "unavailable", friendly_name="Alter Sensor"),
        st("input_boolean.gaeste_modus", "off", friendly_name="Gäste-Modus"),
        st("input_number.heizung_soll", "21", friendly_name="Heizung Soll", min=15, max=25, unit_of_measurement="°C"),
        st("timer.waschmaschine", "idle", friendly_name="Timer Waschmaschine"),
        st("person.anna", "home", friendly_name="Anna"),
        st("scene.nacht", "unknown", friendly_name="Nacht"),
        st("device_tracker.switch_rack", "home", friendly_name="Switch-Rack Switch-Rack", source_type="router", ip="192.168.1.5", mac="02:00:00:00:00:01"),
        st("device_tracker.ap_wohnzimmer", "home", friendly_name="AP-Wohnzimmer AP-Wohnzimmer", source_type="router", ip="192.168.1.7", mac="02:00:00:00:00:02"),
        st("device_tracker.steckdose_drucker", "home", friendly_name="steckdose-drucker Steckdose-Drucker", source_type="router", ip="192.168.80.20",
           mac="02:00:00:00:00:03", host_name="steckdose-drucker", is_guest=False, vlan=80, oui="Espressif Inc.", essid="IoT", ap_mac="02:00:00:00:00:02", name="Steckdose-Drucker"),
        st("device_tracker.imac", "home", friendly_name="iMac iMac", source_type="router", ip="192.168.50.15", mac="02:00:00:00:00:04",
           host_name="iMac", is_guest=False, vlan=50, oui="Apple, Inc."),
        st("device_tracker.nas", "not_home", friendly_name="nas nas", source_type="router", ip="192.168.50.10", mac="02:00:00:00:00:05",
           host_name="nas.internal", is_guest=False, vlan=50, oui="Example Vendor", name="nas"),
        st("device_tracker.unifi_default_02_00_00_00_00_06", "home", source_type="router", ip="192.168.50.101", mac="02:00:00:00:00:06",
           host_name="", is_guest=False, vlan=50, oui="Example Virtual Machines"),
    ]
    return {
        "config": {"location_name": "Zuhause", "version": "2026.10.3", "time_zone": "Europe/Zurich",
                   "unit_system": {"temperature": "°C"}, "latitude": 46.9, "longitude": 7.4, "elevation": 540},
        "states": states,
        "floors": [{"floor_id": "eg", "name": "Erdgeschoss", "level": 0}, {"floor_id": "og", "name": "Obergeschoss", "level": 1}],
        "areas": [{"area_id": "wohnzimmer", "name": "Wohnzimmer", "floor_id": "eg"},
                  {"area_id": "kueche", "name": "Küche", "floor_id": "eg"},
                  {"area_id": "flur", "name": "Flur", "floor_id": "og"}],
        "devices": [
            {"id": "d1", "name": "IKEA Deckenleuchte", "name_by_user": None, "manufacturer": "IKEA", "model": "TRADFRI Driver", "area_id": "wohnzimmer", "sw_version": "2.3.086"},
            {"id": "d2", "name": "Somfy Storen", "name_by_user": "Storen Wohnzimmer", "manufacturer": "Somfy", "model": "Sonesse 30", "area_id": "wohnzimmer", "sw_version": "1.0"},
            {"id": "d3", "name": "Aqara Bewegung", "name_by_user": None, "manufacturer": "Aqara", "model": "RTCGQ11LM", "area_id": "flur", "sw_version": "3"},
            {"id": "d5", "name": "Steckdose Drucker", "name_by_user": None, "manufacturer": "ESPHome", "model": "esp32", "area_id": "flur", "sw_version": "2026.9",
             "connections": [["mac", "02:00:00:00:00:03"]]},
            {"id": "d4", "name": "Hue Spots", "name_by_user": None, "manufacturer": "Signify", "model": "LCG002", "area_id": "kueche", "sw_version": "1.88"},
        ],
        "entities": [
            {"entity_id": "light.wohnzimmer_decke", "device_id": "d1", "area_id": None, "platform": "zha", "disabled_by": None},
            {"entity_id": "cover.wohnzimmer_storen", "device_id": "d2", "area_id": None, "platform": "somfy_mylink", "disabled_by": None},
            {"entity_id": "binary_sensor.bewegung_flur", "device_id": "d3", "area_id": None, "platform": "zha", "disabled_by": None},
            {"entity_id": "light.kueche_spots", "device_id": "d4", "area_id": None, "platform": "hue", "disabled_by": None},
            {"entity_id": "sensor.alter_sensor", "device_id": None, "area_id": None, "platform": "mqtt", "disabled_by": None},
        ] + [{"entity_id": e, "device_id": None, "area_id": None, "platform": "unifi", "disabled_by": None} for e in (
            "device_tracker.switch_rack", "device_tracker.ap_wohnzimmer", "device_tracker.steckdose_drucker", "device_tracker.imac",
            "device_tracker.nas", "device_tracker.unifi_default_02_00_00_00_00_06")],
        "entries": [
            {"domain": "zha", "title": "Zigbee (ZHA)", "state": "loaded", "source": "user"},
            {"domain": "hue", "title": "Philips Hue", "state": "loaded", "source": "zeroconf"},
            {"domain": "mqtt", "title": "MQTT", "state": "loaded", "source": "user"},
            {"domain": "met", "title": "Wetter", "state": "loaded", "source": "onboarding"},
        ],
        "automations": [
            {"entity_id": "automation.flur_licht", "state": "on",
             "attrs": {"friendly_name": "Flur Licht bei Bewegung", "last_triggered": now, "mode": "restart"},
             "config": {"alias": "Flur Licht bei Bewegung", "description": "Licht im Flur schaltet sich bei Bewegung ein.", "mode": "restart",
                        "triggers": [{"trigger": "state", "entity_id": "binary_sensor.bewegung_flur", "to": "on"}],
                        "conditions": [{"condition": "sun", "after": "sunset", "after_offset": "-00:30:00"},
                                       {"condition": "state", "entity_id": "input_boolean.gaeste_modus", "state": "off"}],
                        "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.wohnzimmer_decke"}, "data": {"brightness_pct": 40}},
                                    {"wait_for_trigger": [{"trigger": "state", "entity_id": "binary_sensor.bewegung_flur", "to": "off", "for": "00:02:00"}]},
                                    {"action": "light.turn_off", "target": {"entity_id": "light.wohnzimmer_decke"}}]}},
            {"entity_id": "automation.storen_hitze", "state": "on",
             "attrs": {"friendly_name": "Storen bei Hitze schliessen", "last_triggered": None},
             "config": {"alias": "Storen bei Hitze schliessen", "mode": "single",
                        "triggers": [{"trigger": "numeric_state", "entity_id": "sensor.temp_wohnzimmer", "above": 25},
                                     {"trigger": "time", "at": "13:00:00"}],
                        "conditions": [{"condition": "or", "conditions": [
                            {"condition": "time", "weekday": ["mon", "tue", "wed", "thu", "fri"]},
                            {"condition": "state", "entity_id": "person.anna", "state": "home"}]}],
                        "actions": [{"if": [{"condition": "state", "entity_id": "cover.wohnzimmer_storen", "state": "open"}],
                                     "then": [{"action": "cover.set_cover_position", "target": {"entity_id": "cover.wohnzimmer_storen"}, "data": {"position": 20}}],
                                     "else": [{"stop": "Bereits geschlossen"}]}]}},
            {"entity_id": "automation.s42_storen_buro", "state": "on",
             "attrs": {"friendly_name": "S42_Storensteuerung Büro", "last_triggered": now, "mode": "parallel"},
             "config": {"alias": "S42_Storensteuerung Büro", "use_blueprint": {"path": "s42/storensteuerung.yaml",
                        "input": {"storen": "cover.wohnzimmer_storen", "temp_sensor": "sensor.temp_wohnzimmer", "schwelle": 27, "nachts": True,
                                  "erweitert": {"puffer": 10}, "fenster": "binary_sensor.fenster_buero"}}}},
            {"entity_id": "automation.nachts", "state": "off",
             "attrs": {"friendly_name": "Gute Nacht", "last_triggered": None},
             "config": {"alias": "Gute Nacht", "mode": "single",
                        "triggers": [{"trigger": "time", "at": "22:30:00"}],
                        "actions": [{"action": "scene.turn_on", "target": {"entity_id": "scene.nacht"}},
                                    {"choose": [{"conditions": [{"condition": "state", "entity_id": "person.anna", "state": "home"}],
                                                 "sequence": [{"action": "notify.mobile_app_anna", "data": {"message": "Gute Nacht!"}}]}],
                                     "default": []}]}},
        ],
        "blueprints": {"automation": {"s42/storensteuerung.yaml": {"metadata": {
            "name": "S42 Storensteuerung", "description": "Steuert Storen nach Sonne, Temperatur und Anwesenheit.",
            "input": {"storen": {"name": "Storen", "selector": {}}, "temp_sensor": {"name": "Temperatursensor", "selector": {}},
                      "schwelle": {"name": "Hitze-Schwelle", "default": 25, "selector": {}},
                      "nachts": {"name": "Nachts schliessen", "default": True, "selector": {}},
                      "erweitert": {"name": "Erweitert", "input": {"puffer": {"name": "Puffer (min)", "default": 10, "selector": {}}}}}}}}},
        "scripts": [
            {"entity_id": "script.alles_aus", "state": "off", "attrs": {"friendly_name": "Alles aus"},
             "config": {"alias": "Alles aus", "description": "Schaltet alle Lichter aus.", "mode": "single",
                        "sequence": [{"action": "light.turn_off", "target": {"entity_id": "all"}},
                                     {"delay": {"minutes": 1}},
                                     {"action": "cover.close_cover", "target": {"area_id": "wohnzimmer"}}]}},
        ],
        "scenes": [
            {"entity_id": "scene.nacht", "state": "unknown", "attrs": {"friendly_name": "Nacht"},
             "config": {"name": "Nacht", "entities": {"light.wohnzimmer_decke": {"state": "off"}, "light.kueche_spots": {"state": "off"}}}},
        ],
    }


# --------------------------------------------------------------------------
# 2. Klartext-Beschreibung
# --------------------------------------------------------------------------

IGNORE_UNAVAILABLE_DOMAINS = ("scene", "button", "automation", "script", "stt", "tts", "conversation", "event",
                              "notify", "ai_task", "input_button")

SECTIONS = [("uebersicht", "Übersicht"), ("bereiche", "Bereiche und Geräte"), ("integrationen", "Integrationen"),
            ("netzwerk", "Netzwerk (nur Fritz!Box / UniFi)"),
            ("automatisierungen", "Automatisierungen (Text)"), ("schema", "Automatisierungen (Schema)"), ("skripte", "Skripte"), ("szenen", "Szenen"),
            ("helfer", "Helfer"), ("auffaelligkeiten", "Auffälligkeiten"), ("aenderungen", "Änderungen seit letztem Stand (optional)")]

WEEKDAYS = {"mon": "Mo", "tue": "Di", "wed": "Mi", "thu": "Do", "fri": "Fr", "sat": "Sa", "sun": "So"}


class Namer:
    def __init__(self, data):
        self.names = {}
        for s in data["states"]:
            self.names[s["entity_id"]] = s.get("attributes", {}).get("friendly_name") or s["entity_id"]
        self.areas = {a["area_id"]: a["name"] for a in data["areas"]}

    def ent(self, v):
        if v is None:
            return "?"
        if isinstance(v, list):
            return ", ".join(self.ent(x) for x in v)
        if v == "all":
            return "alle Entitäten"
        n = self.names.get(v)
        return f"{n} [{v}]" if n and n != v else str(v)

    def target(self, t):
        if not isinstance(t, dict):
            return ""
        parts = []
        if t.get("entity_id"):
            parts.append(self.ent(t["entity_id"]))
        if t.get("area_id"):
            ids = t["area_id"] if isinstance(t["area_id"], list) else [t["area_id"]]
            parts.append("Bereich " + ", ".join(self.areas.get(i, i) for i in ids))
        if t.get("device_id"):
            parts.append("Gerät " + (", ".join(t["device_id"]) if isinstance(t["device_id"], list) else t["device_id"]))
        return "; ".join(parts)


def dur(v):
    if isinstance(v, dict):
        units = {"hours": "h", "minutes": "min", "seconds": "s", "milliseconds": "ms", "days": "d"}
        return " ".join(f"{v[k]} {u}" for k, u in units.items() if v.get(k))
    return str(v)


def fmt_data(d):
    if not d:
        return ""
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}" for k, v in d.items())


def describe_trigger(t, n):
    p = t.get("trigger") or t.get("platform") or "?"
    if p == "state":
        s = f"Wenn {n.ent(t.get('entity_id'))} wechselt"
        if t.get("from") is not None:
            s += f" von «{t['from']}»"
        if t.get("to") is not None:
            s += f" auf «{t['to']}»"
        if t.get("for"):
            s += f" für {dur(t['for'])}"
        return s
    if p == "numeric_state":
        s = f"Wenn {n.ent(t.get('entity_id'))}"
        if t.get("above") is not None:
            s += f" über {t['above']}"
        if t.get("below") is not None:
            s += f" unter {t['below']}"
        return s + " steigt/fällt"
    if p == "time":
        return f"Um {t.get('at')} Uhr"
    if p == "time_pattern":
        return "Zeitmuster: " + ", ".join(f"{k}={v}" for k, v in t.items() if k in ("hours", "minutes", "seconds"))
    if p == "sun":
        off = f" (Versatz {t['offset']})" if t.get("offset") else ""
        return f"Bei {'Sonnenaufgang' if t.get('event') == 'sunrise' else 'Sonnenuntergang'}{off}"
    if p == "event":
        return f"Bei Ereignis «{t.get('event_type')}»"
    if p == "homeassistant":
        return f"Beim {'Start' if t.get('event') == 'start' else 'Herunterfahren'} von Home Assistant"
    if p == "zone":
        return f"Wenn {n.ent(t.get('entity_id'))} Zone {t.get('zone')} {'betritt' if t.get('event') == 'enter' else 'verlässt'}"
    if p == "template":
        return f"Wenn Template wahr wird: {t.get('value_template')}"
    if p == "webhook":
        return f"Bei Webhook «{t.get('webhook_id')}»"
    if p == "mqtt":
        return f"Bei MQTT-Nachricht auf «{t.get('topic')}»"
    if p == "device":
        return f"Gerätetrigger: {t.get('type')} ({t.get('subtype', '')})".strip()
    if p == "calendar":
        return f"Kalender {n.ent(t.get('entity_id'))}: {t.get('event')}"
    return f"Trigger «{p}»: " + fmt_data({k: v for k, v in t.items() if k not in ("trigger", "platform", "id", "alias")})


def summarize_triggers(triggers, n, short=False):
    """Beschreibt Auslöser; Zustandsauslöser derselben Entität (z. B. on/off) werden zu einer Zeile zusammengefasst."""
    items, groups = [], {}
    for t in triggers:
        p = t.get("trigger") or t.get("platform")
        eid = t.get("entity_id")
        if p == "state" and isinstance(eid, str) and t.get("from") is None:
            key = (eid, str(t.get("for")))
            if key in groups:
                if t.get("to") not in groups[key]["tos"]:
                    groups[key]["tos"].append(t.get("to"))
                continue
            groups[key] = {"t": t, "tos": [t.get("to")]}
            items.append(groups[key])
        else:
            items.append({"t": t, "tos": None})
    lines = []
    for it in items:
        t, tos = it["t"], it["tos"]
        if not tos or len(tos) == 1:
            lines.append(short_trigger(t, n) if short else describe_trigger(t, n))
            continue
        who = short_name(n, t.get("entity_id")) if short else n.ent(t.get("entity_id"))
        if None in tos:
            s = f"Wenn {who} den Zustand wechselt" if not short else f"{who} wechselt"
        else:
            s = (f"Wenn {who} wechselt auf " if not short else f"{who} wird ") + " oder ".join(f"«{x}»" for x in tos)
        if t.get("for"):
            s += f" für {dur(t['for'])}"
        lines.append(s)
    return lines


def describe_condition(c, n, indent=0):
    if isinstance(c, str):
        return [("  " * indent) + f"Template: {c}"]
    k = c.get("condition", "?")
    pad = "  " * indent
    if k == "state":
        return [pad + f"{n.ent(c.get('entity_id'))} ist «{c.get('state')}»"]
    if k == "numeric_state":
        s = f"{n.ent(c.get('entity_id'))}"
        if c.get("above") is not None:
            s += f" > {c['above']}"
        if c.get("below") is not None:
            s += f" < {c['below']}"
        return [pad + s]
    if k == "time":
        parts = []
        if c.get("after"):
            parts.append(f"nach {c['after']}")
        if c.get("before"):
            parts.append(f"vor {c['before']}")
        if c.get("weekday"):
            parts.append("an " + "/".join(WEEKDAYS.get(w, w) for w in c["weekday"]))
        return [pad + "Zeit: " + ", ".join(parts)]
    if k == "sun":
        parts = []
        for key, word in (("after", "nach"), ("before", "vor")):
            if c.get(key):
                off = c.get(f"{key}_offset")
                parts.append(f"{word} {'Sonnenaufgang' if c[key] == 'sunrise' else 'Sonnenuntergang'}" + (f" ({off})" if off else ""))
        return [pad + "Sonne: " + ", ".join(parts)]
    if k == "template":
        return [pad + f"Template: {c.get('value_template')}"]
    if k == "zone":
        return [pad + f"{n.ent(c.get('entity_id'))} ist in Zone {c.get('zone')}"]
    if k == "trigger":
        ids = c.get("id")
        return [pad + "Ausgelöst durch Trigger-ID " + (", ".join(ids) if isinstance(ids, list) else str(ids))]
    if k in ("and", "or", "not"):
        label = {"and": "ALLE davon", "or": "EINE davon", "not": "KEINE davon"}[k]
        out = [pad + label + ":"]
        for sub in c.get("conditions", []):
            out += describe_condition(sub, n, indent + 1)
        return out
    return [pad + f"Bedingung «{k}»: " + fmt_data({a: b for a, b in c.items() if a != "condition"})]


def describe_actions(actions, n, indent=0):
    out = []
    pad = "  " * indent
    if isinstance(actions, dict):
        actions = [actions]
    for a in actions or []:
        if not isinstance(a, dict):
            out.append(pad + str(a))
            continue
        if a.get("enabled") is False:
            out.append(pad + "(deaktiviert) " + (a.get("alias") or "Schritt"))
            continue
        svc = a.get("action") or a.get("service")
        if svc:
            tgt = n.target(a.get("target") or ({"entity_id": a["entity_id"]} if a.get("entity_id") else {}))
            line = f"{svc}" + (f" auf {tgt}" if tgt else "")
            d = fmt_data(a.get("data"))
            out.append(pad + line + (f" ({d})" if d else ""))
        elif "delay" in a:
            out.append(pad + f"Warte {dur(a['delay'])}")
        elif "wait_for_trigger" in a:
            out.append(pad + "Warte auf: " + " / ".join(describe_trigger(t, n) for t in a["wait_for_trigger"]))
        elif "wait_template" in a:
            out.append(pad + f"Warte bis Template wahr: {a['wait_template']}")
        elif "choose" in a:
            out.append(pad + "Auswahl:")
            for i, opt in enumerate(a["choose"], 1):
                out.append(pad + f"  Fall {i} – wenn:")
                for c in opt.get("conditions", []):
                    out += describe_condition(c, n, indent + 2)
                out.append(pad + "  dann:")
                out += describe_actions(opt.get("sequence"), n, indent + 2)
            if a.get("default"):
                out.append(pad + "  Sonst:")
                out += describe_actions(a["default"], n, indent + 2)
        elif "if" in a:
            out.append(pad + "Wenn:")
            for c in a["if"]:
                out += describe_condition(c, n, indent + 1)
            out.append(pad + "dann:")
            out += describe_actions(a.get("then"), n, indent + 1)
            if a.get("else"):
                out.append(pad + "sonst:")
                out += describe_actions(a["else"], n, indent + 1)
        elif "repeat" in a:
            r = a["repeat"]
            kind = "für Anzahl " + str(r["count"]) if "count" in r else "while/until" if ("while" in r or "until" in r) else "für jedes Element" if "for_each" in r else ""
            out.append(pad + f"Wiederhole ({kind}):")
            out += describe_actions(r.get("sequence"), n, indent + 1)
        elif "parallel" in a:
            out.append(pad + "Parallel:")
            out += describe_actions(a["parallel"], n, indent + 1)
        elif "sequence" in a:
            out += describe_actions(a["sequence"], n, indent)
        elif "variables" in a:
            out.append(pad + "Variablen setzen: " + ", ".join(a["variables"].keys()))
        elif "event" in a:
            out.append(pad + f"Ereignis auslösen «{a['event']}»")
        elif "stop" in a:
            out.append(pad + f"Stopp: {a['stop']}")
        elif "condition" in a:
            out.append(pad + "Prüfe Bedingung (Abbruch wenn falsch):")
            out += describe_condition(a, n, indent + 1)
        elif "scene" in a:
            out.append(pad + f"Szene aktivieren: {a['scene']}")
        elif "device_id" in a:
            out.append(pad + f"Geräteaktion: {a.get('type')} (Gerät {a['device_id']})")
        else:
            out.append(pad + fmt_data(a))
    return out


# --------------------------------------------------------------------------
# 3. PDF
# --------------------------------------------------------------------------


def short_name(n, v):
    if v is None:
        return "?"
    if isinstance(v, list):
        return ", ".join(short_name(n, x) for x in v)
    return n.names.get(v, str(v))


def short_target(t, n):
    if not isinstance(t, dict):
        return ""
    parts = []
    if t.get("entity_id"):
        parts.append("alle" if t["entity_id"] == "all" else short_name(n, t["entity_id"]))
    if t.get("area_id"):
        ids = t["area_id"] if isinstance(t["area_id"], list) else [t["area_id"]]
        parts.append("Bereich " + ", ".join(n.areas.get(i, i) for i in ids))
    if t.get("device_id"):
        parts.append("Gerät")
    return "; ".join(parts)


def short_trigger(t, n):
    p = t.get("trigger") or t.get("platform") or "?"
    nm = short_name(n, t.get("entity_id")) if t.get("entity_id") else ""
    if p == "state":
        s = nm
        if t.get("from") is not None and t.get("to") is not None:
            s += f" von «{t['from']}» auf «{t['to']}»"
        elif t.get("to") is not None:
            s += f" wird «{t['to']}»"
        elif t.get("from") is not None:
            s += f" verlässt «{t['from']}»"
        else:
            s += " wechselt"
        if t.get("for"):
            s += f" ({dur(t['for'])})"
        return s
    if p == "numeric_state":
        return nm + (f" > {t['above']}" if t.get("above") is not None else "") + (f" < {t['below']}" if t.get("below") is not None else "")
    if p == "time":
        return f"{t.get('at')} Uhr"
    if p == "time_pattern":
        return "Zeitmuster " + ", ".join(f"{k}={v}" for k, v in t.items() if k in ("hours", "minutes", "seconds"))
    if p == "sun":
        return "Sonnenaufgang" if t.get("event") == "sunrise" else "Sonnenuntergang"
    if p == "event":
        return f"Ereignis «{t.get('event_type')}»"
    if p == "homeassistant":
        return "HA-Start" if t.get("event") == "start" else "HA-Stopp"
    if p == "zone":
        return f"{nm} {'betritt' if t.get('event') == 'enter' else 'verlässt'} {t.get('zone')}"
    if p == "template":
        return "Template wird wahr"
    if p == "webhook":
        return f"Webhook {t.get('webhook_id')}"
    if p == "mqtt":
        return f"MQTT {t.get('topic')}"
    if p == "calendar":
        return f"Kalender {nm}: {t.get('event')}"
    return f"Trigger «{p}»"


def short_cond(c, n):
    if isinstance(c, str):
        return "Template"
    k = c.get("condition", "?")
    nm = short_name(n, c.get("entity_id")) if c.get("entity_id") else ""
    if k == "state":
        st = c.get("state")
        return f"{nm} = " + (" / ".join(f"«{x}»" for x in st) if isinstance(st, list) else f"«{st}»")
    if k == "numeric_state":
        return nm + (f" > {c['above']}" if c.get("above") is not None else "") + (f" < {c['below']}" if c.get("below") is not None else "")
    if k == "time":
        parts = []
        if c.get("after"):
            parts.append(f"nach {c['after']}")
        if c.get("before"):
            parts.append(f"vor {c['before']}")
        if c.get("weekday"):
            parts.append("/".join(WEEKDAYS.get(w, w) for w in c["weekday"]))
        return "Zeit: " + ", ".join(parts)
    if k == "sun":
        parts = []
        for key, word in (("after", "nach"), ("before", "vor")):
            if c.get(key):
                parts.append(f"{word} {'Sonnenaufgang' if c[key] == 'sunrise' else 'Sonnenuntergang'}")
        return ", ".join(parts)
    if k == "template":
        return "Template"
    if k == "zone":
        return f"{nm} in Zone {c.get('zone')}"
    if k == "trigger":
        ids = c.get("id")
        return "Auslöser " + (", ".join(ids) if isinstance(ids, list) else str(ids))
    if k in ("and", "or", "not"):
        subs = [short_cond(x, n) for x in c.get("conditions", [])]
        if k == "not":
            return "nicht (" + " oder ".join(subs) + ")"
        return "(" + (" und " if k == "and" else " oder ").join(subs) + ")"
    return f"Bedingung {k}"


def short_actions(actions, n, depth=0):
    out, pad = [], "  " * depth
    if isinstance(actions, dict):
        actions = [actions]
    for a in actions or []:
        if not isinstance(a, dict) or a.get("enabled") is False:
            continue
        svc = a.get("action") or a.get("service")
        if svc:
            tgt = short_target(a.get("target") or ({"entity_id": a["entity_id"]} if a.get("entity_id") else {}), n)
            out.append(pad + svc + (f" – {tgt}" if tgt else ""))
        elif "delay" in a:
            out.append(pad + f"Warte {dur(a['delay'])}")
        elif "wait_for_trigger" in a:
            out.append(pad + "Warte auf: " + " / ".join(short_trigger(t, n) for t in a["wait_for_trigger"]))
        elif "wait_template" in a:
            out.append(pad + "Warte auf Template")
        elif "choose" in a:
            for i, opt in enumerate(a["choose"], 1):
                out.append(pad + f"Fall {i}: wenn " + " und ".join(short_cond(x, n) for x in opt.get("conditions", [])))
                out += short_actions(opt.get("sequence"), n, depth + 1)
            if a.get("default"):
                out.append(pad + "Sonst:")
                out += short_actions(a["default"], n, depth + 1)
        elif "if" in a:
            out.append(pad + "Wenn " + " und ".join(short_cond(x, n) for x in a["if"]) + ":")
            out += short_actions(a.get("then"), n, depth + 1)
            if a.get("else"):
                out.append(pad + "Sonst:")
                out += short_actions(a["else"], n, depth + 1)
        elif "repeat" in a:
            out.append(pad + "Wiederhole:")
            out += short_actions(a["repeat"].get("sequence"), n, depth + 1)
        elif "parallel" in a:
            out.append(pad + "Parallel:")
            out += short_actions(a["parallel"], n, depth + 1)
        elif "sequence" in a:
            out += short_actions(a["sequence"], n, depth)
        elif "variables" in a:
            out.append(pad + "Variablen setzen")
        elif "event" in a:
            out.append(pad + f"Ereignis «{a['event']}»")
        elif "stop" in a:
            out.append(pad + f"Stopp: {a['stop']}")
        elif "condition" in a:
            out.append(pad + "Prüfe: " + short_cond(a, n))
        elif "scene" in a:
            out.append(pad + "Szene " + short_name(n, a["scene"]))
        elif "device_id" in a:
            out.append(pad + f"Geräteaktion {a.get('type')}")
        else:
            out.append(pad + "Weiterer Schritt")
    return out


def fmt_value(v, n):
    if v is None or v == "" or v == []:
        return "–"
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, list):
        return ", ".join(fmt_value(x, n) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k}: {fmt_value(x, n)}" for k, x in v.items())
    if isinstance(v, str) and v in n.names and n.names[v] != v:
        return f"{n.names[v]} [{v}]"
    return str(v)


def bp_rows(inputs, meta, n):
    """Blueprint-Eingaben als (Bezeichnung, Wert); Werte gleich dem Standardwert werden weggelassen und gezählt."""
    defs, sections = {}, set()

    def walk_meta(inp):
        for k, v in (inp or {}).items():
            if isinstance(v, dict) and "input" in v and "selector" not in v:
                sections.add(k)
                walk_meta(v["input"])
            else:
                defs[k] = v if isinstance(v, dict) else {}

    walk_meta(meta.get("input"))
    flat = {}

    def walk_vals(vals):
        for k, v in (vals or {}).items():
            if k in sections and isinstance(v, dict):
                walk_vals(v)
            else:
                flat[k] = v

    walk_vals(inputs)
    rows, same = [], 0
    for k, v in flat.items():
        d = defs.get(k, {})
        if "default" in d and d["default"] == v:
            same += 1
            continue
        rows.append((d.get("name") or k, fmt_value(v, n)))
    return rows, same


def collect_network(data):
    """Geräte-Tracker der Integrationen UniFi und AVM Fritz!Box (IP, MAC, VLAN …)."""
    NET_PLATFORMS = {"unifi": "UniFi", "fritz": "Fritz!Box"}
    plat_of = {e["entity_id"]: e.get("platform") for e in data["entities"]}
    net = []
    for s in data["states"]:
        eid = s["entity_id"]
        a = s.get("attributes") or {}
        if not eid.startswith("device_tracker.") or plat_of.get(eid) not in NET_PLATFORMS or not a.get("ip"):
            continue
        plat = plat_of[eid]
        fn = (a.get("friendly_name") or "").strip()
        half = len(fn) // 2
        if fn and len(fn) % 2 == 1 and fn[:half] == fn[half + 1:]:
            fn = fn[:half]  # "Name Name" -> "Name"
        name = a.get("name") or a.get("host_name") or fn or "(unbenannt)"
        net.append({"name": name, "ip": a["ip"], "mac": (a.get("mac") or "").lower(), "oui": a.get("oui") or "", "vlan": a.get("vlan"),
                    "essid": a.get("essid"), "ap_mac": (a.get("ap_mac") or "").lower(), "online": s["state"] == "home", "platform": plat,
                    "infra": plat == "unifi" and "is_guest" not in a and "vlan" not in a})
    return net


def build_pdf(data, out_path, title="Home Assistant Dokumentation", sections=None, options=None):
    opts = options or {}
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph,
                                    Spacer, Table, TableStyle)
    from reportlab.platypus.tableofcontents import TableOfContents

    n = Namer(data)
    on = lambda key: sections is None or key in sections
    cfg = data["config"]
    ss = getSampleStyleSheet()
    ACC = colors.HexColor("#03a9f4")
    DARK = colors.HexColor("#1f2933")
    H1 = ParagraphStyle("H1", parent=ss["Heading1"], textColor=DARK, fontSize=18, spaceBefore=6, spaceAfter=8)
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], textColor=ACC, fontSize=13, spaceBefore=10, spaceAfter=4, keepWithNext=1)
    H3 = ParagraphStyle("H3", parent=ss["Heading3"], textColor=DARK, fontSize=10.5, spaceBefore=6, spaceAfter=2)
    BODY = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9, leading=12)
    SMALL = ParagraphStyle("S", parent=BODY, fontSize=8, textColor=colors.grey)
    LINE = ParagraphStyle("L", parent=BODY, fontSize=8.5, leading=11, fontName="Courier")
    CELL = ParagraphStyle("C", parent=BODY, fontSize=8, leading=10)

    class Doc(BaseDocTemplate):
        def afterFlowable(self, fl):
            if isinstance(fl, Paragraph) and fl.style.name in ("H1", "H2"):
                self.notify("TOCEntry", (0 if fl.style.name == "H1" else 1, fl.getPlainText(), self.page))

    import os
    from reportlab.pdfgen import canvas as rl_canvas
    # Logo: opts["logo_path"] (None = kein Logo); ohne Angabe das mitgelieferte layvo-Logo
    logo_path = opts["logo_path"] if "logo_path" in opts else os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_pdf.png")
    has_logo = bool(logo_path) and os.path.isfile(logo_path)
    logo_ratio = 1165 / 399  # Breite / Höhe (Standardlogo)
    if has_logo:
        try:
            from PIL import Image as PILImage
            with PILImage.open(logo_path) as _im:
                logo_ratio = _im.width / _im.height
        except Exception:
            has_logo = False

    def footer(canvas, doc):
        canvas.saveState()
        x = 20 * mm
        if has_logo:
            fh = min(4.4 * mm, 24 * mm / logo_ratio)
            fwid = fh * logo_ratio
            canvas.drawImage(logo_path, x, 8.2 * mm, width=fwid, height=fh, mask="auto")
            x += fwid + 3 * mm
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(x, 10 * mm, title)
        canvas.restoreState()

    class NumberedCanvas(rl_canvas.Canvas):
        """Zeichnet «Seite n / N» (Gesamtzahl erst am Schluss bekannt)."""
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st)
                self.setFont("Helvetica", 8)
                self.setFillColor(colors.grey)
                self.drawRightString(190 * mm, 10 * mm, f"Seite {self._pageNumber} / {total}")
                super().showPage()
            super().save()

    doc = Doc(out_path, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
              title=title, author="ha_doc")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height)],
                                       onPage=footer)])

    def P(t, s=BODY):
        return Paragraph(escape(str(t)), s)

    def table(rows, widths, header=True):
        t = Table([[Paragraph(escape(str(c)), CELL) for c in r] for r in rows], colWidths=widths, repeatRows=1 if header else 0)
        style = [("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fa")])]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e1f3fc"))]
        t.setStyle(TableStyle(style))
        return t

    W = doc.width
    story = []

    def cover_table(rows, widths, header=True):
        t = table(rows, widths, header)
        t.hAlign = "LEFT"
        return t
    notes = opts.get("notes") or {}
    NOTE = lambda kind, key: (notes.get(f"{kind}:{key}") or "").strip()
    NOTE_FILL = colors.HexColor("#fff8dc")

    def note_html(txt):
        return "<i>Bemerkung:</i> " + escape(txt).replace("\n", "<br/>")

    def note_box(txt):
        t = Table([[Paragraph(note_html(txt), CELL)]], colWidths=[W])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NOTE_FILL), ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#e6d9a0"))]))
        return t

    # Deckblatt: Logo oben links (falls logo_pdf.png neben dem Skript liegt)
    from reportlab.platypus import Image as RLImage
    logo = []
    if has_logo:
        lw = min(52 * mm, 26 * mm * logo_ratio)
        logo = [RLImage(logo_path, width=lw, height=lw / logo_ratio, hAlign="LEFT"), Spacer(1, 28 * mm)]
    story += ([] if logo else [Spacer(1, 70 * mm)]) + logo + [Paragraph(escape(title), ParagraphStyle("T", parent=H1, fontSize=30, leading=36)),
              Spacer(1, 6 * mm), P(cfg.get("location_name", "Home Assistant"), ParagraphStyle("T2", parent=BODY, fontSize=16, leading=20, textColor=ACC)),
              Spacer(1, 12 * mm)]
    cv = opts.get("cover")
    if cv:
        def blk(head, lines):
            lines = [x for x in lines if x]
            if not lines:
                return ""
            return [Paragraph(escape(head).upper(), ParagraphStyle("CH", parent=SMALL, fontSize=7.5, spaceAfter=2)),
                    Paragraph("<br/>".join(f"<b>{escape(l)}</b>" if i == 0 else escape(l) for i, l in enumerate(lines)),
                              ParagraphStyle("CB", parent=BODY, fontSize=9.5, leading=13))]
        cr, cu = cv["creator"], cv["customer"]
        left = blk("Erstellt von", [cr["name"]] + cr["address"].split("\n") + [cr["phone"], cr["email"], cr["web"]])
        right = blk("Erstellt für", [cu["name"]] + cu["address"].split("\n") + ([f"Objekt: {cu['object']}"] if cu["object"] else []))
        cells = [x for x in (left, right) if x]
        if cells:
            t = Table([cells], colWidths=[W / 2 - 2 * mm] * len(cells) if len(cells) > 1 else [W * 0.6], hAlign="LEFT")
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            story += [t, Spacer(1, 10 * mm)]
    info = [["Home Assistant Version", cfg.get("version", "?")], ["Zeitzone", cfg.get("time_zone", "?")],
            ["Erstellt am", dt.datetime.now().strftime("%d.%m.%Y %H:%M")]]
    if cv and cv["doc"]["version"]:
        info.append(["Version / Stand", cv["doc"]["version"]])
    if cv and cv["doc"]["author"]:
        info.append(["Bearbeiter", cv["doc"]["author"]])
    story += [cover_table(info, [50 * mm, 80 * mm], header=False)]
    if (opts.get("general_note") or "").strip():
        story += [Spacer(1, 10 * mm), note_box(opts["general_note"].strip())]
    story.append(PageBreak())

    main = story  # Hauptliste; Abschnitte, die nicht gewählt sind, landen in einer Wegwerfliste

    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("t0", fontSize=10, leftIndent=0, spaceBefore=4),
                       ParagraphStyle("t1", fontSize=9, leftIndent=12, textColor=colors.HexColor("#444444"))]
    story += [Paragraph("Inhaltsverzeichnis", ParagraphStyle("TH", parent=H1)), toc, PageBreak()]

    # Uebersicht
    doms = defaultdict(int)
    for s in data["states"]:
        doms[s["entity_id"].split(".")[0]] += 1
    unavailable = [s for s in data["states"] if s["state"] in ("unavailable", "unknown") and s["entity_id"].split(".")[0] not in IGNORE_UNAVAILABLE_DOMAINS]
    story = main if on("uebersicht") else []
    story.append(Paragraph("Übersicht", H1))
    story.append(table([["Kennzahl", "Anzahl"], ["Entitäten (aktiv)", len(data["states"])], ["Geräte", len(data["devices"])],
                        ["Bereiche", len(data["areas"])], ["Integrationen", len(data["entries"])],
                        ["Automatisierungen", len(data["automations"])], ["Skripte", len(data["scripts"])],
                        ["Szenen", len(data["scenes"])], ["Nicht verfügbare Entitäten", len(unavailable)]],
                       [90 * mm, 30 * mm]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Entitäten nach Domain", H2))
    top = sorted(doms.items(), key=lambda x: -x[1])
    story.append(table([["Domain", "Anzahl"]] + [[d, c] for d, c in top], [60 * mm, 30 * mm]))
    story.append(PageBreak())

    # Bereiche & Geraete
    dev_by_id = {d["id"]: d for d in data["devices"]}
    ents_by_dev = defaultdict(list)
    area_of_ent = {}
    for e in data["entities"]:
        if e.get("device_id"):
            ents_by_dev[e["device_id"]].append(e["entity_id"])
        area_of_ent[e["entity_id"]] = e.get("area_id") or (dev_by_id.get(e.get("device_id"), {}).get("area_id"))
    floors = {f["floor_id"]: f for f in data["floors"]}
    story = main if on("bereiche") else []
    story.append(Paragraph("Bereiche und Geräte", H1))
    areas_sorted = sorted(data["areas"], key=lambda a: (floors.get(a.get("floor_id"), {}).get("level", 99), a["name"]))
    CELLM = ParagraphStyle("CM", parent=CELL, fontName="Courier", fontSize=7, leading=9)

    net = collect_network(data)
    name_by_mac = {x["mac"]: x["name"] for x in net if x["mac"]}
    ip_by_mac = {x["mac"]: x["ip"] for x in net if x["mac"]}

    def ip_key(x):
        try:
            return (0, int(ipaddress.ip_address(x["ip"])))
        except ValueError:
            return (1, 0)

    def device_ip(d):
        for c in d.get("connections") or []:
            if len(c) == 2 and c[0] == "mac" and str(c[1]).lower() in ip_by_mac:
                return ip_by_mac[str(c[1]).lower()]
        return None

    def device_table(head_text, sub_text, ents, hidden=0, note=""):
        """Ein Kasten pro Gerät: Kopfzeile mit Gerätename, darunter eine Zeile pro Entität (Kopf wiederholt sich auf Folgeseiten)."""
        head = Paragraph("<b>" + escape(head_text) + "</b>" +
                         (f"  <font color='#6b7785'>{escape(sub_text)}</font>" if sub_text else ""), CELL)
        rows = [[head, ""]]
        if note:
            rows.append([Paragraph(note_html(note), CELL), ""])
        for e in ents:
            nm = n.names.get(e, "")
            en = NOTE("entity", e)
            rows.append([Paragraph(escape(nm if nm != e else ""), CELL),
                         [Paragraph(escape(e), CELLM)] + ([Paragraph(note_html(en), CELL)] if en else [])])
        if hidden:
            rows.append([Paragraph("", SMALL), Paragraph(f"+ {hidden} Konfigurations-/Diagnose-Entitäten ausgeblendet", SMALL)])
        elif not ents:
            rows.append([Paragraph("(keine Entitäten)", SMALL), ""])
        t = Table(rows, colWidths=[75 * mm, W - 75 * mm], repeatRows=1)
        t.setStyle(TableStyle([("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e1f3fc")),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fa")]),
                               *([("SPAN", (0, 1), (-1, 1)), ("BACKGROUND", (0, 1), (-1, 1), NOTE_FILL)] if note else [])]))
        return t

    ent_ids_with_device = {e["entity_id"] for e in data["entities"] if e.get("device_id")}
    ent_cat = {e["entity_id"]: e.get("entity_category") for e in data["entities"]}

    def split_diag(ents):
        if not opts.get("hide_diagnostic"):
            return ents, 0
        shown = [e for e in ents if ent_cat.get(e) not in ("config", "diagnostic")]
        return shown, len(ents) - len(shown)

    for a in areas_sorted + [{"area_id": None, "name": "Ohne Bereich", "floor_id": None}]:
        if opts.get("areas") is not None and (a["area_id"] or "_none") not in opts["areas"]:
            continue
        devs = [d for d in data["devices"] if d.get("area_id") == a["area_id"]]
        loose = [e for e, ar in area_of_ent.items() if ar == a["area_id"] and e not in ent_ids_with_device]
        if not devs and not loose:
            continue
        fl = floors.get(a.get("floor_id"), {}).get("name")
        story.append(Paragraph(escape(a["name"] + (f"  ({fl})" if fl else "")), H2))
        if NOTE("area", a["area_id"] or "_none"):
            story += [note_box(NOTE("area", a["area_id"] or "_none")), Spacer(1, 1.5 * mm)]
        for d in sorted(devs, key=lambda x: (x.get("name_by_user") or x.get("name") or "").lower()):
            sub = f"{d.get('manufacturer') or ''} {d.get('model') or ''}".strip()
            ip = device_ip(d)
            if ip:
                sub = (sub + "  ·  IP " + ip).strip()
            shown, hid = split_diag(ents_by_dev.get(d["id"], []))
            story.append(device_table(d.get("name_by_user") or d.get("name") or "?", sub, shown, hid, note=NOTE("device", d["id"])))
            story.append(Spacer(1, 2.5 * mm))
        if loose:
            shown, hid = split_diag(sorted(loose))
            story.append(device_table("Entitäten ohne Gerät", "z. B. Helfer, Vorlagen, Automatisierungen", shown, hid))
            story.append(Spacer(1, 2.5 * mm))
    story.append(PageBreak())

    # Integrationen
    story = main if on("integrationen") else []
    story.append(Paragraph("Integrationen", H1))
    ek = lambda e: e.get("entry_id") or f"{e.get('domain')}|{e.get('title')}"
    entries_sorted = sorted(data["entries"], key=lambda x: x.get("domain", ""))
    if any(NOTE("integration", ek(e)) for e in entries_sorted):
        story.append(table([["Integration", "Domain", "Status", "Quelle", "Bemerkung"]] +
                           [[e.get("title"), e.get("domain"), e.get("state"), e.get("source"), NOTE("integration", ek(e))] for e in entries_sorted],
                           [42 * mm, 30 * mm, 22 * mm, 22 * mm, W - 116 * mm]))
    else:
        story.append(table([["Integration", "Domain", "Status", "Quelle"]] +
                           [[e.get("title"), e.get("domain"), e.get("state"), e.get("source")] for e in entries_sorted],
                           [55 * mm, 40 * mm, 30 * mm, W - 125 * mm]))
    story.append(PageBreak())

    # Netzwerk
    story = main if on("netzwerk") else []
    story.append(Paragraph("Netzwerk", H1))
    story.append(P("Quelle: Geräte-Tracker der Integrationen UniFi Network und AVM FRITZ!Box Tools. Dieser Abschnitt funktioniert nur mit "
                   "einem Fritz!Box- oder UniFi-Gateway; andere Router werden nicht ausgewertet.", SMALL))
    story.append(Spacer(1, 3 * mm))
    if not net:
        story.append(P("Keine Netzwerkdaten gefunden. Richte die Integration «UniFi Network» oder «AVM FRITZ!Box Tools» ein und aktiviere das "
                       "Verfolgen von Netzwerk-Clients."))
    else:
        infra = sorted([x for x in net if x["infra"]], key=ip_key)
        clients = [x for x in net if not x["infra"]]
        online = sum(1 for x in net if x["online"])
        story.append(table([["Kennzahl", "Anzahl"], ["Netzwerkgeräte (UniFi)", len(infra)], ["Clients", len(clients)],
                            ["Online", online], ["Offline", len(net) - online]], [60 * mm, 30 * mm]))
        story.append(Spacer(1, 3 * mm))
        cols = [48 * mm, 28 * mm, 33 * mm, 32 * mm, W - 141 * mm]
        nk = lambda x: NOTE("net", x["mac"] or x["ip"])
        has_nn = any(nk(x) for x in net)
        if infra:
            story.append(Paragraph("Netzwerkgeräte", H2))
            story.append(table([["Name", "IP", "MAC", "Status", "Bemerkung" if has_nn else ""]] +
                               [[x["name"], x["ip"], x["mac"], "online" if x["online"] else "offline", nk(x)] for x in infra], cols))
        groups = defaultdict(list)
        for x in clients:
            groups[x["vlan"] if x["vlan"] is not None else "-"].append(x)
        for vlan in sorted(groups, key=lambda v: (v == "-", v if isinstance(v, int) else 0)):
            lst = sorted(groups[vlan], key=ip_key)
            story.append(Paragraph(f"VLAN {vlan}" if vlan != "-" else "Clients", H2))
            rows = [["Name", "IP", "MAC", "Hersteller", "Verbindung"] + (["Bemerkung"] if has_nn else [])]
            for x in lst:
                if x["essid"]:
                    conn = "WLAN " + x["essid"] + (f" ({name_by_mac[x['ap_mac']]})" if x["ap_mac"] in name_by_mac else "")
                else:
                    conn = "LAN" if x["platform"] == "unifi" else ""
                rows.append([x["name"] + ("" if x["online"] else " (offline)"), x["ip"], x["mac"], x["oui"], conn] + ([nk(x)] if has_nn else []))
            story.append(table(rows, [38 * mm, 24 * mm, 30 * mm, 26 * mm, 26 * mm, W - 144 * mm] if has_nn else cols))
    story.append(PageBreak())

    known = {s["entity_id"] for s in data["states"]}

    def missing_refs(it):
        c = it.get("config")
        if not c:
            return []
        refs = set(_find_entity_refs(c)) | set(_blueprint_refs((c.get("use_blueprint") or {}).get("input")))
        return sorted(r for r in refs if r not in known and r != "all")

    def blueprint_block(c, kind):
        bp = c.get("use_blueprint") or {}
        path = bp.get("path", "?")
        dom = "script" if kind == "script" else "automation"
        meta = ((data.get("blueprints") or {}).get(dom, {}).get(path) or {}).get("metadata", {}) or {}
        rows, same = bp_rows(bp.get("input"), meta, n)
        out = [Paragraph("<b>Blueprint:</b> " + escape(meta.get("name") or path) +
                         f"  <font color='#6b7785'>({escape(path)})</font>", BODY)]
        if meta.get("description"):
            out.append(P(re.sub(r"\s+", " ", str(meta["description"]))[:400], SMALL))
        out.append(P("Auslöser, Bedingungen und Aktionen sind im Blueprint festgelegt; hier stehen nur die eingestellten Werte.", SMALL))
        out.append(Spacer(1, 1.5 * mm))
        if rows:
            out.append(table([["Eingabe", "Wert"]] + [list(r) for r in rows], [70 * mm, W - 70 * mm]))
        else:
            out.append(P("Alle Eingaben stehen auf dem Standardwert.", SMALL))
        if same and rows:
            out.append(P(f"{same} weitere Eingaben stehen auf dem Standardwert (nicht aufgeführt).", SMALL))
        return out

    def schema_table(c):
        """Drei Kästen (Auslöser → Bedingungen → Aktionen) als Übersichtsgrafik."""
        from reportlab.graphics.shapes import Drawing, Line, Polygon
        MAXL = 12
        trig = c.get("triggers", c.get("trigger", [])) or []
        cond = c.get("conditions", c.get("condition", [])) or []
        act = c.get("actions", c.get("action", [])) or []
        trig = [trig] if isinstance(trig, dict) else trig
        cond = [cond] if isinstance(cond, (dict, str)) else cond
        cols = [("AUSLÖSER", ["• " + x for x in summarize_triggers(trig, n, short=True)], "#e1f3fc", "#0288d1"),
                ("BEDINGUNGEN", ["• " + short_cond(x, n) for x in cond] or ["keine"], "#fdf3e0", "#b26a00"),
                ("AKTIONEN", short_actions(act, n) or ["keine"], "#e6f4ea", "#2e7d32")]
        SCH = ParagraphStyle("sch", parent=BODY, fontSize=7.5, leading=9.5)
        cells, styles = [], []
        for ci, (label, lines, bg, fg) in enumerate(cols):
            if len(lines) > MAXL:
                lines = lines[:MAXL] + [f"… +{len(lines) - MAXL} weitere"]
            fl = [Paragraph(f"<b>{label}</b>", ParagraphStyle("schl", parent=SCH, textColor=colors.HexColor(fg), fontSize=7.5, spaceAfter=2))]
            for ln in lines:
                st = ln.lstrip(" ")
                fl.append(Paragraph(escape(st), ParagraphStyle("schi", parent=SCH, leftIndent=(len(ln) - len(st)) * 3, firstLineIndent=0)))
            cells.append(fl)
            col = ci * 2
            styles += [("BACKGROUND", (col, 0), (col, 0), colors.HexColor(bg)), ("BOX", (col, 0), (col, 0), 0.6, colors.HexColor(fg))]

        def arrow():
            d = Drawing(7 * mm, 10 * mm)
            d.add(Line(0.5 * mm, 5 * mm, 4.5 * mm, 5 * mm, strokeColor=colors.grey, strokeWidth=1.2))
            d.add(Polygon([4 * mm, 3.2 * mm, 6.8 * mm, 5 * mm, 4 * mm, 6.8 * mm], fillColor=colors.grey, strokeColor=colors.grey))
            return d

        t = Table([[cells[0], arrow(), cells[1], arrow(), cells[2]]], colWidths=[52 * mm, 7 * mm, 52 * mm, 7 * mm, 52 * mm])
        t.setStyle(TableStyle(styles + [("VALIGN", (0, 0), (-1, -1), "TOP"), ("VALIGN", (1, 0), (1, 0), "MIDDLE"), ("VALIGN", (3, 0), (3, 0), "MIDDLE"),
                                        ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
                                        ("LEFTPADDING", (3, 0), (3, 0), 0), ("RIGHTPADDING", (3, 0), (3, 0), 0),
                                        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return t

    # Automatisierungen
    def render_items(heading, items, kind, text=True, schema=False):
        story.append(Paragraph(heading, H1))
        if opts.get("only_problems"):
            items = [it for it in items if missing_refs(it)]
            story.append(P("Gefiltert: nur Einträge mit fehlenden Entitäten.", SMALL))
        if not items:
            story.append(P("Keine vorhanden." if not opts.get("only_problems") else "Keine Einträge mit fehlenden Entitäten."))
        for it in sorted(items, key=lambda x: (x["attrs"].get("friendly_name") or x["entity_id"]).lower()):
            c = it["config"]
            name = it["attrs"].get("friendly_name") or it["entity_id"]
            status = {"on": "aktiv", "off": "deaktiviert"}.get(it["state"], it["state"]) if kind == "automation" else ""
            blk = [Paragraph(escape(name), H3), P(it["entity_id"] + (f"  |  Status: {status}" if status else "") +
                   (f"  |  Modus: {c.get('mode') or it['attrs'].get('mode')}" if kind != "scene" and (c or it['attrs'].get('mode')) else ""), SMALL)]
            if NOTE(kind, it["entity_id"]):
                blk.append(note_box(NOTE(kind, it["entity_id"])))
            mr = missing_refs(it)
            if mr:
                blk.append(P("Fehlende Entitäten: " + ", ".join(mr), ParagraphStyle("miss", parent=SMALL, textColor=colors.HexColor("#c62828"))))
            if c is None:
                blk.append(P("Konfiguration nicht über die API lesbar (z. B. in YAML definiert).", SMALL))
                story.append(KeepTogether(blk))
                continue
            if c.get("description"):
                blk.append(P(c["description"]))
            if c.get("use_blueprint") and kind in ("automation", "script"):
                la = it["attrs"].get("last_triggered")
                if la:
                    blk.append(P(f"Zuletzt ausgelöst: {la[:16].replace('T', ' ')}", SMALL))
                blk += blueprint_block(c, kind)
                story.append(KeepTogether(blk))
                story.append(Spacer(1, 2 * mm))
                continue
            lines = []
            if kind == "automation":
                trig = c.get("triggers", c.get("trigger", []))
                cond = c.get("conditions", c.get("condition", []))
                act = c.get("actions", c.get("action", []))
                trig = [trig] if isinstance(trig, dict) else trig
                cond = [cond] if isinstance(cond, (dict, str)) else cond
                lines.append(("AUSLÖSER", summarize_triggers(trig, n)))
                if cond:
                    cl = []
                    for x in cond:
                        cl += describe_condition(x, n)
                    lines.append(("BEDINGUNGEN (alle müssen zutreffen)", cl))
                lines.append(("AKTIONEN", describe_actions(act, n)))
                la = it["attrs"].get("last_triggered")
                if la:
                    blk.append(P(f"Zuletzt ausgelöst: {la[:16].replace('T', ' ')}", SMALL))
            elif kind == "script":
                lines.append(("ABLAUF", describe_actions(c.get("sequence"), n)))
            else:
                lines.append(("ENTITÄTEN", [f"{n.ent(e)} -> {v.get('state', '') if isinstance(v, dict) else v}" for e, v in (c.get("entities") or {}).items()]))
            head_n = 4
            if schema and kind == "automation":
                blk.append(Spacer(1, 1.5 * mm))
                blk.append(schema_table(c))
                blk.append(Spacer(1, 2 * mm))
                head_n = len(blk)
            if not text:
                lines = []
            for lab, ls in lines:
                blk.append(P(lab, ParagraphStyle("lab", parent=SMALL, textColor=ACC, spaceBefore=3)))
                for l in ls or ["(leer)"]:
                    stripped = l.lstrip(" ")
                    ind = len(l) - len(stripped)
                    blk.append(Paragraph(escape(stripped), ParagraphStyle("li", parent=LINE, leftIndent=4 + ind * 3.5)))
            story.append(KeepTogether(blk[:head_n]))
            story.extend(blk[head_n:])
        story.append(PageBreak())

    story = main if (on("automatisierungen") or on("schema")) else []
    render_items("Automatisierungen", data["automations"], "automation", text=on("automatisierungen"), schema=on("schema"))
    story = main if on("skripte") else []
    render_items("Skripte", data["scripts"], "script")
    story = main if on("szenen") else []
    render_items("Szenen", data["scenes"], "scene")

    # Helfer
    helper_doms = ("input_boolean", "input_number", "input_select", "input_text", "input_datetime", "input_button", "counter", "timer", "schedule")
    helpers = [s for s in data["states"] if s["entity_id"].split(".")[0] in helper_doms]
    story = main if on("helfer") else []
    story.append(Paragraph("Helfer", H1))
    story.append(table([["Name", "Entität", "Typ", "Aktueller Wert"]] +
                       [[s["attributes"].get("friendly_name", ""), s["entity_id"], s["entity_id"].split(".")[0], s["state"]] for s in sorted(helpers, key=lambda x: x["entity_id"])],
                       [45 * mm, 60 * mm, 30 * mm, W - 135 * mm]) if helpers else P("Keine vorhanden."))
    story.append(PageBreak())

    # Probleme
    story = main if on("auffaelligkeiten") else []
    story.append(Paragraph("Auffälligkeiten", H1))
    story.append(Paragraph("Nicht verfügbare Entitäten", H2))
    story.append(table([["Entität", "Name", "Status"]] + [[s["entity_id"], s["attributes"].get("friendly_name", ""), s["state"]] for s in unavailable],
                       [70 * mm, 60 * mm, W - 130 * mm]) if unavailable else P("Keine."))
    # Referenzen: Entitaeten in Automationen, die nicht (mehr) existieren
    known = {s["entity_id"] for s in data["states"]}
    broken = []
    for coll in (data["automations"], data["scripts"], data["scenes"]):
        for it in coll:
            if not it["config"]:
                continue
            for ref in sorted(set(_find_entity_refs(it["config"])) | set(_blueprint_refs((it["config"].get("use_blueprint") or {}).get("input")))):
                if ref not in known and ref != "all":
                    broken.append([it["attrs"].get("friendly_name") or it["entity_id"], ref])
    story.append(Paragraph("Referenzen auf nicht existierende Entitäten", H2))
    story.append(table([["Verwendet in", "Fehlende Entität"]] + broken, [80 * mm, W - 80 * mm]) if broken else P("Keine."))

    # Änderungen seit letztem Stand (optional, Daten kommen vom Server: opts["changes"])
    if on("aenderungen") and main and not isinstance(main[-1], PageBreak):
        main.append(PageBreak())
    story = main if on("aenderungen") else []
    story.append(Paragraph("Änderungen seit letztem Stand", H1))
    ch = opts.get("changes")
    fmt_t = lambda iso: dt.datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    if not ch:
        story.append(P("Kein Vergleich verfügbar."))
    elif ch.get("first"):
        story.append(P(f"Erster gespeicherter Stand ({fmt_t(ch['cur_time'])}, Home Assistant {ch['cur_version']}). "
                       "Der Vergleich ist ab dem nächsten Bericht mit dieser Option möglich."))
    else:
        story.append(P(f"Vergleich: {fmt_t(ch['prev_time'])} (Home Assistant {ch['prev_version']}) → {fmt_t(ch['cur_time'])} "
                       f"(Home Assistant {ch['cur_version']})"))
        story.append(Spacer(1, 3 * mm))
        if not ch["total"]:
            story.append(P("Keine Änderungen seit dem letzten Stand."))
        else:
            story.append(table([["Kategorie", "Neu", "Entfernt", "Geändert"]] +
                               [[c["label"], len(c["added"]), len(c["removed"]), len(c["changed"])] for c in ch["cats"]],
                               [70 * mm, 25 * mm, 25 * mm, 25 * mm]))
            DIFF = ParagraphStyle("DF", parent=LINE, fontSize=7, leading=8.5)

            def lst(items):
                shown = items[:200]
                rows = [[x] for x in shown] + ([[f"… und {len(items) - 200} weitere"]] if len(items) > 200 else [])
                return table([["Name"]] + rows, [W])

            for c in ch["cats"]:
                if not c["count"]:
                    continue
                story.append(Paragraph(escape(c["label"]), H2))
                if c["added"]:
                    story += [Paragraph("Neu", H3), lst(c["added"])]
                if c["removed"]:
                    story += [Paragraph("Entfernt", H3), lst(c["removed"])]
                if c["changed"]:
                    story.append(Paragraph("Geändert", H3))
                    for it in c["changed"][:200]:
                        story.append(Paragraph("<b>" + escape(str(it["title"])) + "</b>", BODY))
                        if it["fields"]:
                            story.append(table([["Feld", "Vorher", "Nachher"]] + [[f, o or "–", nw or "–"] for f, o, nw in it["fields"]],
                                               [35 * mm, (W - 35 * mm) / 2, (W - 35 * mm) / 2]))
                        if it["diff"]:
                            lines = it["diff"][:40]
                            story.append(Paragraph("Konfiguration (– vorher, + nachher):", SMALL))
                            for ln in lines:
                                col = "#b00020" if ln.startswith("-") else "#1b7f3b" if ln.startswith("+") else "#6b7785"
                                story.append(Paragraph(f"<font color='{col}'>" + escape(ln).replace(" ", "&nbsp;") + "</font>", DIFF))
                            if len(it["diff"]) > 40:
                                story.append(Paragraph(f"… {len(it['diff']) - 40} weitere Zeilen", SMALL))
                        story.append(Spacer(1, 2.5 * mm))

    while main and isinstance(main[-1], PageBreak):
        main.pop()
    doc.multiBuild(main, canvasmaker=NumberedCanvas)


def _blueprint_refs(obj):
    """Entitäts-IDs in den Eingaben eines Blueprints (Werte sind dort nicht unter 'entity_id' abgelegt)."""
    import re as _re
    pat = _re.compile(r"^(light|switch|sensor|binary_sensor|cover|climate|person|input_boolean|input_number|input_select|input_text|input_datetime|scene|script|automation|media_player|fan|lock|timer|counter|device_tracker|zone|sun|weather|camera|vacuum|button|number|select|calendar|group)\.[a-z0-9_]+$")
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _blueprint_refs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _blueprint_refs(v)
    elif isinstance(obj, str) and pat.match(obj):
        yield obj


def _find_entity_refs(obj):
    import re
    pat = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
    skip = ("light", "switch", "sensor", "binary_sensor", "cover", "climate", "person", "input_boolean", "input_number", "input_select",
            "input_text", "input_datetime", "scene", "script", "automation", "media_player", "fan", "lock", "timer", "counter",
            "device_tracker", "zone", "sun", "weather", "camera", "vacuum", "button", "number", "select", "calendar", "group")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "entity_id":
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, str) and pat.match(x) and x.split(".")[0] in skip:
                        yield x
            else:
                yield from _find_entity_refs(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _find_entity_refs(x)


# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description="Home Assistant Dokumentation als PDF")
    ap.add_argument("--url", help="z. B. http://homeassistant.local:8123")
    ap.add_argument("--token", help="Langlebiges Zugriffstoken")
    ap.add_argument("--demo", action="store_true", help="Beispieldaten verwenden")
    ap.add_argument("--dump-json", help="Rohdaten zusätzlich als JSON speichern")
    ap.add_argument("-o", "--output", default="ha_dokumentation.pdf")
    ap.add_argument("--areas", help="Kommagetrennt: Bereichs-IDs (und _none für «Ohne Bereich»); Standard: alle")
    ap.add_argument("--only-problems", action="store_true", help="Automatisierungen/Skripte/Szenen nur mit fehlenden Entitäten")
    ap.add_argument("--hide-diagnostic", action="store_true", help="Konfigurations- und Diagnose-Entitäten ausblenden")
    ap.add_argument("--sections", help="Kommagetrennt, z. B. automatisierungen,helfer (Standard: alles). Mögliche Werte: " + ",".join(k for k, _ in SECTIONS))
    a = ap.parse_args()
    if a.demo:
        data = demo_data()
    elif a.url and a.token:
        data = fetch_all(a.url, a.token)
    else:
        ap.error("Entweder --demo oder --url und --token angeben.")
    if a.dump_json:
        with open(a.dump_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    build_pdf(data, a.output, sections=a.sections.split(",") if a.sections else None,
              options={"areas": a.areas.split(",") if a.areas else None, "only_problems": a.only_problems,
                       "hide_diagnostic": a.hide_diagnostic})
    print(f"Fertig: {a.output}")


if __name__ == "__main__":
    sys.exit(main())
