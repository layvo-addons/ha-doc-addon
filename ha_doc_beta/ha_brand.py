"""Logo-Einstellung: layvo-Logo, kein Logo oder eigenes Logo (gespeichert in share/ha_doc/branding)."""
import base64
import io
import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOGO = os.path.join(APP_DIR, "logo_pdf.png")
MODES = ("layvo", "none", "custom")
MAX_BYTES = 2_000_000


def _cfg_path(base):
    return os.path.join(base, "branding.json")


def _custom_path(base):
    for ext in ("png", "jpg"):
        p = os.path.join(base, "branding", f"logo.{ext}")
        if os.path.isfile(p):
            return p
    return None


def load(base):
    try:
        with open(_cfg_path(base), encoding="utf-8") as f:
            mode = json.load(f).get("mode", "layvo")
    except (OSError, ValueError):
        mode = "layvo"
    if mode not in MODES:
        mode = "layvo"
    if mode == "custom" and not _custom_path(base):
        mode = "layvo"
    return {"mode": mode, "custom": _custom_path(base)}


def logo_path(base):
    """Pfad des zu verwendenden Logos oder None (kein Logo)."""
    b = load(base)
    if b["mode"] == "none":
        return None
    if b["mode"] == "custom":
        return b["custom"]
    return DEFAULT_LOGO


def save_mode(base, mode):
    if mode not in MODES:
        raise ValueError("Unbekannte Auswahl")
    os.makedirs(base, exist_ok=True)
    with open(_cfg_path(base), "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f)


def save_custom(base, b64data):
    """Speichert ein hochgeladenes PNG oder JPG (max. 2 MB). Löst ValueError bei ungültigen Dateien aus."""
    try:
        raw = base64.b64decode(b64data, validate=False)
    except Exception:
        raise ValueError("Datei konnte nicht gelesen werden")
    if len(raw) > MAX_BYTES:
        raise ValueError("Datei zu gross (max. 2 MB)")
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        ext = "png"
    elif raw[:3] == b"\xff\xd8\xff":
        ext = "jpg"
    else:
        raise ValueError("Nur PNG oder JPG erlaubt")
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    im.verify()
    d = os.path.join(base, "branding")
    os.makedirs(d, exist_ok=True)
    for e in ("png", "jpg"):
        try:
            os.remove(os.path.join(d, f"logo.{e}"))
        except OSError:
            pass
    with open(os.path.join(d, f"logo.{ext}"), "wb") as f:
        f.write(raw)
    return ext
