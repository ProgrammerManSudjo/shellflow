"""Colour schemes (Material You), the seed colour (wallpaper or Windows accent), the palette every theme is built from, and applying a scheme."""
import ctypes
import importlib
import json
import re
from functools import lru_cache
from types import SimpleNamespace
from materialyoucolor.hct import Hct
from materialyoucolor.quantize import QuantizeCelebi
from materialyoucolor.score.score import Score
from PIL import Image
from .core import CONFIG, DATA, OUT, parse_colour, write_if_changed

# (key, label) in grid order. "windows" = no override, the plain Windows accent.
MENU = [("windows", "Windows accent"), ("content", "Content"), ("fidelity", "Fidelity"),
        ("tonal_spot", "Tonal Spot"), ("monochrome", "Monochrome"), ("expressive", "Expressive"),
        ("neutral", "Neutral"), ("vibrant", "Vibrant"),
        ("fruit_salad", "Fruit Salad")]


# Tone of each --yasb-accent* variable (same look as the Windows-accent palette)
TONES = {"accent": 50, "dark1": 40, "dark2": 25, "dark3": 10, "light1": 60, "light2": 80, "light3": 90}


SHADES = ("accent", "accent-dark1", "accent-dark2", "accent-dark3", "accent-light1", "accent-light2", "accent-light3")


# ============================================================================================
#  2. COLOUR HELPERS
#  Material You schemes and small colour conversions.
# ============================================================================================
@lru_cache(maxsize=64)
def scheme(name, seed):
    """A dark Material You scheme of one variant (tonal_spot, fidelity ...) built from a seed colour. Remembered: the Colors page asks for
    nine of them every time it is drawn."""
    cls = "Scheme" + name.title().replace("_", "")  # tonal_spot -> SchemeTonalSpot
    module = importlib.import_module(f"materialyoucolor.scheme.scheme_{name}")
    return getattr(module, cls)(Hct.from_int(seed), True, 0.0)


def rgb(c):
    """An ARGB integer as (r, g, b)."""
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


def hx(t, f=1.0):
    """(r, g, b) as "#rrggbb", scaled by f (f < 1 = darker)."""
    return "#%02x%02x%02x" % tuple(min(255, round(v * f)) for v in t)


def lerp(a, b, t):
    """Blend two (r, g, b) colours; t = 0 gives a, t = 1 gives b."""
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


# the colours of the "custom" scheme (set in the settings window, Edits page; saved in settings.json)
CUSTOM_VARS = ("accent", "accent-dark1", "accent-dark2", "accent-dark3", "accent-light1", "accent-light2",
               "accent-light3", "background", "foreground")


def custom_colours():
    """{variable: (r, g, b, alpha)} of the colours you set yourself, or {} (then there is no custom scheme)."""
    try:
        raw = json.loads((DATA / "settings.json").read_text(encoding="utf-8")).get("colours", {})
    except (OSError, ValueError):
        return {}
    found = {v: parse_colour(str(raw[v])) for v in CUSTOM_VARS if v in raw}
    return {v: c for v, c in found.items() if c}


def menu_items():
    """The schemes in the picker: MENU, then "Custom" (the colours set on the settings window's Edits page)."""
    return MENU + [("custom", "Custom")]


def wallpaper_seed():
    """The dominant colour of the current wallpaper (Material You style), or None."""
    buf = ctypes.create_unicode_buffer(520)
    ctypes.windll.user32.SystemParametersInfoW(0x73, 520, buf, 0)  # SPI_GETDESKWALLPAPER
    try:
        img = Image.open(buf.value).convert("RGB")
        img.thumbnail((128, 128))
        pixels = [(r << 16) | (g << 8) | b | 0xFF000000 for r, g, b in img.getdata()]
        return Score.score(QuantizeCelebi(pixels, 128))[0]
    except Exception:
        return None


def windows_accent_seed():
    """The Windows accent colour, read from the registry."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as k:
        abgr = winreg.QueryValueEx(k, "AccentColor")[0]
    return 0xFF000000 | ((abgr & 0xFF) << 16) | (abgr & 0xFF00) | ((abgr >> 16) & 0xFF)


def get_seed():
    """The wallpaper's dominant colour, else the Windows accent."""
    return wallpaper_seed() or windows_accent_seed()


def accent_shades(effective=False):
    """Accent shades as (r, g, b), read from yasb_colors.css (the Windows accent the bar starts from).
    effective=True lets theme_colors.css (the scheme you applied) take over, so it matches the bar right now."""
    try:
        text = (CONFIG / "yasb_colors.css").read_text(encoding="utf-8")
        out = {k: tuple(map(int, re.search(rf"--yasb-{k}-rgb:\s*(\d+),\s*(\d+),\s*(\d+)", text).groups())) for k in SHADES}
    except (OSError, AttributeError):  # missing file: derive the shades from the Windows accent
        try:
            p = scheme("tonal_spot", windows_accent_seed()).primary_palette
        except Exception:
            p = scheme("tonal_spot", 0xFF6B8CCF).primary_palette
        out = {k: rgb(p.tone(t)) for k, t in zip(SHADES, (50, 40, 25, 10, 60, 80, 90))}
    if effective:
        try:
            over = (OUT).read_text(encoding="utf-8")
            for k in SHADES:
                m = re.search(rf"--yasb-{k}-rgb:\s*(\d+),\s*(\d+),\s*(\d+)", over)
                if m:
                    out[k] = tuple(map(int, m.groups()))
        except OSError:
            pass
    return out


# ============================================================================================
#  5. APPLYING A SCHEME
#  Writes theme_colors.css for the bar, then refreshes the app themes.
# ============================================================================================
def apply(name, seed=None):
    """Apply a scheme: write theme_colors.css (cleared for "windows"), then refresh the app themes. Returns {app: what went wrong}."""
    if name not in dict(menu_items()):
        raise ValueError(f"unknown scheme or command: {name!r}")
    if name == "windows":
        write_if_changed(OUT, "/* Windows accent in use - no override */\n")
    elif name == "custom":  # only the colours you set; the rest stays the Windows accent (nothing set = Windows accent)
        lines = ["/* Generated by theme.py - variant: custom */", ":root {"]
        for var, (r, g, b, a) in custom_colours().items():
            lines += [f"    --yasb-{var}: " + (f"rgb({r}, {g}, {b});" if a >= 1 else f"rgba({r}, {g}, {b}, {a:g});"),
                      f"    --yasb-{var}-rgb: {r}, {g}, {b};"]
        write_if_changed(OUT, "\n".join(lines + ["}"]) + "\n")
    else:
        seed = seed or get_seed()
        p = scheme(name, seed).primary_palette
        lines = [f"/* Generated by theme.py - variant: {name}, seed: #{seed & 0xFFFFFF:06x} */", ":root {"]
        for key, tone in TONES.items():
            r, g, b = rgb(p.tone(tone))
            var = "--yasb-accent" + ("" if key == "accent" else "-" + key)
            lines += [f"    {var}: rgb({r}, {g}, {b});", f"    {var}-rgb: {r}, {g}, {b};"]
        write_if_changed(OUT, "\n".join(lines + ["}"]) + "\n")
    from .themes import write_apps
    return write_apps()


def current_variant():
    """The scheme that is applied right now, read from theme_colors.css."""
    try:
        return re.search(r"variant: (\w+)", OUT.read_text()).group(1)
    except (OSError, AttributeError):
        return "windows"


def applied_scheme():
    """(variant, seed) of the scheme applied from the Colors page, read from the first line of theme_colors.css. None when the
    Windows accent (or your custom colours) are in use."""
    try:
        m = re.search(r"variant: (\w+), seed: #([0-9a-fA-F]{6})", OUT.read_text(encoding="utf-8").split("\n", 1)[0])
    except OSError:
        return None
    return (m.group(1), 0xFF000000 | int(m.group(2), 16)) if m else None


def palette(effective=True):
    """The colours every theme is built from: the accent shades, a tint scale and terminal colours. With effective=True (the
    default) it follows the scheme applied from the Colors page, so the apps and the settings window match the bar;
    effective=False is the plain Windows accent."""
    c = accent_shades(effective)
    acc = c["accent"]
    applied = applied_scheme() if effective else None
    try:
        seed = applied[1] if applied else windows_accent_seed()
    except Exception:  # the registry value is missing: build the palette from the accent itself
        seed = 0xFF000000 | (acc[0] << 16) | (acc[1] << 8) | acc[2]
    s = scheme(applied[0] if applied else "tonal_spot", seed)
    tone = lambda p: (lambda t: "#%02x%02x%02x" % rgb(p.tone(t)))
    # terminal colours (also what Yazi, Neovim and every program that says "yellow" or "magenta" show): red, green and yellow keep their
    # meaning but lean toward the accent and are muted by it; blue, purple and cyan are the accent and its close neighbours.
    # A vivid accent gives colourful terminal colours, a grey scheme (Monochrome) gives nearly grey ones.
    accent_hct = Hct.from_int(0xFF000000 | (acc[0] << 16) | (acc[1] << 8) | acc[2])
    hue, vivid = accent_hct.hue, max(0.0, min(1.0, accent_hct.chroma / 36))

    def lean(h, share, limit):  # move hue h toward the accent by `share` of the way, but never more than `limit` degrees
        gap = ((hue - h + 540) % 360) - 180
        return (h + max(-limit, min(limit, gap * share))) % 360
    tint = lambda h, chroma, t, floor=0: hx(rgb(Hct.from_hct(h % 360, max(floor, chroma * vivid), t).to_int()))
    term = lambda t: [tint(lean(25, .5, 15), 40, t, 14), tint(lean(140, .4, 22), 34, t, 14), tint(lean(90, .6, 28), 30, t, 12),
                      tint(hue, 44, t), tint(hue - 16, 30, t), tint(hue + 16, 32, t)]
    return SimpleNamespace(
        t=lambda f: hx(acc, f),  # the accent over black: 0.05 = darkest, 0.35 = a button
        acc=hx(acc), d1=hx(c["accent-dark1"]), d2=hx(c["accent-dark2"]), d3=hx(c["accent-dark3"]), l1=hx(c["accent-light1"]),
        l2=hx(c["accent-light2"]), l3=hx(c["accent-light3"]),
        sec=tone(s.secondary_palette), ter=tone(s.tertiary_palette), neu=tone(s.neutral_palette),
        ansi=term(62), bright=term(78))


def al(colour, alpha):
    """"#rrggbb" -> "#rrggbbaa" (with transparency)."""
    return colour + "%02x" % round(255 * alpha)


def shade(colour, f):
    """"#rrggbb" scaled by f (f < 1 = darker)."""
    return hx(tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5)), f)
