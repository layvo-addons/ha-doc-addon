"""Excel-Export der Home-Assistant-Dokumentation: Geräteliste mit ein-/ausklappbaren Entitäten."""
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import ha_doc

HEAD_FILL = PatternFill("solid", fgColor="1F4E79")
AREA_FILL = PatternFill("solid", fgColor="D9E7F5")
DEV_FILL = PatternFill("solid", fgColor="EEF4FA")
WHITE = Font(bold=True, color="FFFFFF")


def _header(ws, cols, widths):
    ws.append(cols)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        c = ws.cell(row=1, column=i)
        c.font, c.fill = WHITE, HEAD_FILL
    ws.freeze_panes = "A2"


def build_xlsx(data, out_path, options=None):
    opts = options or {}
    notes = opts.get("notes") or {}
    NOTE = lambda kind, key: (notes.get(f"{kind}:{key}") or "").strip()
    n = ha_doc.Namer(data)
    net = ha_doc.collect_network(data)
    ip_by_mac = {x["mac"]: x["ip"] for x in net if x["mac"]}
    state_of = {s["entity_id"]: s["state"] for s in data["states"]}
    dev_by_id = {d["id"]: d for d in data["devices"]}
    ents_by_dev = defaultdict(list)
    area_of_ent = {}
    for e in data["entities"]:
        if e.get("device_id"):
            ents_by_dev[e["device_id"]].append(e["entity_id"])
        area_of_ent[e["entity_id"]] = e.get("area_id") or dev_by_id.get(e.get("device_id"), {}).get("area_id")
    with_dev = {e["entity_id"] for e in data["entities"] if e.get("device_id")}
    ent_cat = {e["entity_id"]: e.get("entity_category") for e in data["entities"]}
    floors = {f["floor_id"]: f for f in data["floors"]}

    def shown(ents):
        ents = sorted(ents)
        if opts.get("hide_diagnostic"):
            ents = [e for e in ents if ent_cat.get(e) not in ("config", "diagnostic")]
        return ents

    wb = Workbook()
    ws = wb.active
    ws.title = "Geräte"
    _header(ws, ["Bereich / Gerät / Entität", "Hersteller / Modell", "IP", "Entität-ID", "Zustand", "Entitäten", "Bemerkung"],
            [46, 34, 16, 52, 18, 10, 60])
    ws.sheet_properties.outlinePr.summaryBelow = False  # +/- Knopf steht in der Gerätezeile
    areas = sorted(data["areas"], key=lambda a: (floors.get(a.get("floor_id"), {}).get("level", 99), a["name"]))
    areas.append({"area_id": None, "name": "Ohne Bereich", "floor_id": None})

    def add_device(title, sub, ip, ents, note=""):
        ents = shown(ents)
        ws.append([title, sub, ip, "", "", len(ents), note])
        r = ws.max_row
        for c in range(1, 8):
            ws.cell(row=r, column=c).fill = DEV_FILL
        ws.cell(row=r, column=1).font = Font(bold=True)
        ws.cell(row=r, column=1).alignment = Alignment(indent=1)
        for e in ents:
            nm = n.names.get(e, "")
            ws.append([nm if nm != e else "", "", "", e, state_of.get(e, ""), "", NOTE("entity", e)])
            rr = ws.max_row
            ws.cell(row=rr, column=1).alignment = Alignment(indent=3)
            ws.row_dimensions[rr].outlineLevel = 1
            ws.row_dimensions[rr].hidden = True  # eingeklappt

    for a in areas:
        if opts.get("areas") is not None and (a["area_id"] or "_none") not in opts["areas"]:
            continue
        devs = [d for d in data["devices"] if d.get("area_id") == a["area_id"]]
        loose = [e for e, ar in area_of_ent.items() if ar == a["area_id"] and e not in with_dev]
        if not devs and not loose:
            continue
        fl = floors.get(a.get("floor_id"), {}).get("name")
        ws.append([a["name"] + (f"  ({fl})" if fl else ""), "", "", "", "", "", NOTE("area", a["area_id"] or "_none")])
        r = ws.max_row
        for c in range(1, 8):
            ws.cell(row=r, column=c).fill = AREA_FILL
        ws.cell(row=r, column=1).font = Font(bold=True, size=12)
        for d in sorted(devs, key=lambda x: (x.get("name_by_user") or x.get("name") or "").lower()):
            ip = next((ip_by_mac[str(c[1]).lower()] for c in d.get("connections") or []
                       if len(c) == 2 and c[0] == "mac" and str(c[1]).lower() in ip_by_mac), "")
            add_device(d.get("name_by_user") or d.get("name") or "?",
                       f"{d.get('manufacturer') or ''} {d.get('model') or ''}".strip(), ip, ents_by_dev.get(d["id"], []), NOTE("device", d["id"]))
        if loose:
            add_device("Entitäten ohne Gerät", "", "", loose)
    ws.sheet_format.outlineLevelRow = 1

    if net:
        wn = wb.create_sheet("Netzwerk")
        _header(wn, ["Name", "IP", "MAC", "Hersteller", "VLAN", "Verbindung", "Status", "Quelle", "Bemerkung"], [30, 16, 20, 30, 8, 28, 10, 12, 50])
        name_by_mac = {x["mac"]: x["name"] for x in net if x["mac"]}
        for x in sorted(net, key=lambda x: (x["vlan"] if isinstance(x["vlan"], int) else -1, ha_doc_ip_key(x))):
            conn = ("WLAN " + x["essid"] + (f" ({name_by_mac[x['ap_mac']]})" if x["ap_mac"] in name_by_mac else "")) if x["essid"] \
                else ("Netzwerkgerät" if x["infra"] else ("LAN" if x["platform"] == "unifi" else ""))
            wn.append([x["name"], x["ip"], x["mac"], x["oui"], x["vlan"] if x["vlan"] is not None else "", conn,
                       "online" if x["online"] else "offline", x["platform"], NOTE("net", x["mac"] or x["ip"])])
        wn.auto_filter.ref = f"A1:I{wn.max_row}"

    wi = wb.create_sheet("Integrationen")
    _header(wi, ["Integration", "Domain", "Status", "Quelle", "Bemerkung"], [40, 28, 16, 16, 50])
    for e in sorted(data["entries"], key=lambda x: x.get("domain", "")):
        wi.append([e.get("title"), e.get("domain"), e.get("state"), e.get("source"),
                   NOTE("integration", e.get("entry_id") or f"{e.get('domain')}|{e.get('title')}")])
    wi.auto_filter.ref = f"A1:E{wi.max_row}"
    wb.save(out_path)


def ha_doc_ip_key(x):
    import ipaddress
    try:
        return int(ipaddress.ip_address(x["ip"]))
    except ValueError:
        return 0
