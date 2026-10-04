"""The generated block at the end of styles.css (fonts, capsules, bar, menus)."""
import json
import re
from .. import api as th
from .catalog import CATALOG
from .config_yaml import bar_edge, menu_gap, read_widgets
from .constants import CONFIG_YAML, EDITS_JSON, STYLES, parse_colour
from .popup_css import POPUP_CSS

# ============================================================================================
#  3. EDITS  (fonts, colours, spacing, bar opacity -> one block at the end of styles.css)
# ============================================================================================
BLOCK_START = "/* >>> ShellFlow (written by the settings window - change it there, not here) >>> */"


BLOCK_END = "/* <<< ShellFlow <<< */"


# (label, css variable) of the colours that can be overridden
COLOUR_VARS = (("Accent", "accent"), ("Dark 1", "accent-dark1"), ("Dark 2", "accent-dark2"),
               ("Dark 3", "accent-dark3"), ("Light 1", "accent-light1"), ("Light 2", "accent-light2"),
               ("Light 3", "accent-light3"), ("Background", "background"), ("Foreground", "foreground"))


# the groups of styles.css: widget text and icons, menus / tooltips / clock, and the capsules
BAR_FONT_SELECTORS = (".widget .label", ".komorebi-active-layout .label", ".komorebi-control-widget .label",
                      ".power-menu-widget .label", ".systray .button", ".context-menu .menu-checkbox .checkbox")


MENU_FONT_SELECTORS = (".context-menu", ".context-menu *", ".home-menu", ".home-menu *", ".komorebi-layout-menu *",
                       ".power-menu-compact", ".power-menu-compact *", ".power-menu-popup .button",
                       ".power-menu-popup .button .label", ".taskbar-preview .header .title", ".tooltip",
                       ".clock-widget .label")


CAPSULES = (".home-widget", ".komorebi-workspaces", ".komorebi-active-layout", ".komorebi-control-widget",
            ".taskbar-widget .widget-container", ".systray", ".wallpapers-widget", ".clock-widget", ".power-menu-widget")


NERD = '"JetBrainsMono Nerd Font Propo", "JetBrainsMono NFP"'  # fallback, so icon glyphs keep working


ICON_BUTTONS = ("whkd", "notes", "control_center")  # one glyph in a capsule


TEXT_CAPSULES = ("active_window",)                  # a title in a capsule


def catalog_css(cfg_text, font="Poppins", icon_pad=14):
    """Capsule and popup styling for the catalog widgets that config.yaml defines (same look as the other capsules).
    The buttons get even padding left and right (icon_pad px). The rules start with .yasb-bar so they win over the
    general `.widget` padding, which is meant for the other capsules."""
    used = [e for e in CATALOG if e[4] in read_widgets(cfg_text).values()]
    if not used:
        return "", ()
    ff = f'"{font or "Poppins"}", "Segoe UI", sans-serif'
    caps = ",\n".join(e[5] for e in used)
    out = [caps + " {\n    background-color: var(--yasb-accent-light1);\n    border-radius: 14px;\n    margin: 5px;\n}"]
    buttons = [e[5] for e in used if e[0] in ICON_BUTTONS]
    titles = [e[5] for e in used if e[0] in TEXT_CAPSULES]
    if buttons or titles:
        out.append(",\n".join(f".yasb-bar {s}" for s in buttons + titles) + f" {{\n    padding: 0 {icon_pad}px;\n}}")
    if buttons:
        out.append(",\n".join(f".yasb-bar {s} {part}" for s in buttons for part in (".icon", ".label")) +
                   " {\n    font-size: 18px;\n    color: var(--yasb-accent-dark3);\n    padding: 0 0 2px 0;\n}")
    if titles:
        out.append(",\n".join(f".yasb-bar {s} .label" for s in titles) +
                   " {\n    font-size: 13px;\n    font-weight: 600;\n    color: var(--yasb-accent-dark3);\n    padding: 0 0 2px 0;\n}")
    out += [POPUP_CSS[e[0]].replace("__FONT__", ff).replace("__ICONFONT__", NERD) for e in used if e[0] in POPUP_CSS]
    return "\n\n".join(out), tuple(e[5] for e in used)


def px(value):
    return f"{value}px"


# every menu's root element. Newer YASB gives the clock's popup two classes (.clock-popup.calendar), so a rule for plain .calendar is weaker
# than the menu's own. Each root is therefore written twice, the second time with one class repeated (which counts for more).
MENU_ROOTS = (".context-menu", ".home-menu", ".komorebi-layout-menu", ".komorebi-control-menu", ".calendar", ".power-menu-popup",
              ".power-menu-compact", ".taskbar-preview", ".wallpapers-gallery-window",
              ".clock-popup", ".clock-popup.calendar", ".clock-popup.alarm", ".clock-popup.timer", ".notes-menu", ".control-center-menu", ".whkd-popup")


def menu_selectors():
    out = []
    for root in MENU_ROOTS:
        first = root.split(".")[1]
        out += [root, "." + first + root]  # the same element, with its first class repeated: stronger than a rule that names it once
    return out


def menu_corners(cfg_text, edits):
    """CSS for the corners of every menu, from whether they float: round all over when they float; stuck to the bar, the two corners that
    touch it are square (the top ones for a bar at the top, the bottom ones for a bar at the bottom). The radius is the Menu roundness
    (20 px unless set). Written one corner at a time: Qt's style sheets ignore the four-value form of border-radius (the corners came out
    square), and a single-value border-radius does not reliably beat a menu's own per-corner rules."""
    r = f"{int(edits.get('menu_radius', 20))}px"
    if menu_gap(cfg_text)[0]:
        tl = tr = bl = br = r
    elif bar_edge(cfg_text)[0] == "bottom":
        tl, tr, bl, br = r, r, "0px", "0px"
    else:
        tl, tr, bl, br = "0px", "0px", r, r
    menus = ",\n".join(menu_selectors()) + (f" {{\n    border-top-left-radius: {tl};\n    border-top-right-radius: {tr};\n"
                                           f"    border-bottom-left-radius: {bl};\n    border-bottom-right-radius: {br};\n}}")
    return menus


def style_block(edits, cfg_text=""):
    """The CSS for fonts, capsules, the bar and the workspace pills. A value that is not set produces nothing (styles.css stays as it is)."""
    out = []
    for key, selectors in (("font_bar", BAR_FONT_SELECTORS), ("font_menu", MENU_FONT_SELECTORS)):
        face = str(edits.get(key, "")).strip().strip("\"'")
        if face:
            out.append(",\n".join(selectors) + " {\n    font-family: \"%s\", %s;\n}" % (face, NERD))
    types = set(read_widgets(cfg_text).values())
    offline = [sel for typ, sel in (("komorebi.workspaces.WorkspaceWidget", ".komorebi-workspaces .offline-status"),
                                    ("komorebi.stack.StackWidget", ".komorebi-stack .offline-status")) if typ in types]
    if offline:  # "Komorebi Offline" is white until it is given the capsule's text colour
        out.append(",\n".join(offline) + " {\n    color: var(--yasb-accent-dark3);\n    font-weight: 600;\n}")
    base, extra = catalog_css(cfg_text, str(edits.get("font_menu", "")).strip().strip("\"'") or css_font(MENU_FONT_SELECTORS),
                              edits.get("icon_pad", 14))
    if base:
        out.insert(0, base)
    # capsules: spacing on the left and right only (never above or below), roundness, an optional border
    left, right = edits.get("spacing_l", edits.get("spacing")), edits.get("spacing_r", edits.get("spacing"))
    caps = []
    if left is not None:
        caps.append(f"    margin-left: {px(left)};")
    if right is not None:
        caps.append(f"    margin-right: {px(right)};")
    if "radius" in edits:
        caps.append(f"    border-radius: {px(edits['radius'])};")
    if edits.get("border_w"):
        r, g, b, a = parse_colour(str(edits.get("border_c", "#000000"))) or (0, 0, 0, 1.0)
        caps.append(f"    border: {px(edits['border_w'])} solid " + (f"rgb({r}, {g}, {b});" if a >= 1 else f"rgba({r}, {g}, {b}, {a:g});"))
    if caps:
        out.append(",\n".join(CAPSULES + extra) + " {\n" + "\n".join(caps) + "\n}")
    pad_l, pad_r = edits.get("pad_l", edits.get("pad")), edits.get("pad_r", edits.get("pad"))
    pads = [f"    padding-{side}: {px(v)};" for side, v in (("left", pad_l), ("right", pad_r)) if v is not None]
    if pads:
        out.append(".widget {\n" + "\n".join(pads) + "\n}")
    bar = []
    if "opacity" in edits:
        r, g, b, _ = parse_colour(edits.get("bar_colour", "#000000")) or (0, 0, 0, 1)
        bar.append(f"    background-color: rgba({r}, {g}, {b}, {edits['opacity'] / 100:.2f});")
    if "bar_radius" in edits:
        bar.append(f"    border-radius: {px(edits['bar_radius'])};")
    if bar:
        out.append(".yasb-bar {\n" + "\n".join(bar) + "\n}")
    # the workspace pills inside the komorebi workspaces capsule
    ws = ".komorebi-workspaces .ws-btn"
    pill = [f"    {css}: {value};" for key, css, value in (("ws_radius", "border-radius", px(edits.get("ws_radius"))),
                                                         ("ws_h", "height", px(edits.get("ws_h"))),
                                                         ("ws_w_empty", "width", px(edits.get("ws_w_empty"))),
                                                         ("ws_gap", "margin", f"0 {edits.get('ws_gap')}px")) if key in edits]
    if pill:
        out.append(ws + " {\n" + "\n".join(pill) + "\n}")
    if "ws_w_pop" in edits:
        out.append(ws + f".populated {{\n    width: {px(edits['ws_w_pop'])};\n}}")
    if "ws_w_active" in edits:
        out.append(ws + f".active {{\n    width: {px(edits['ws_w_active'])};\n}}")
    if types:  # last, so it wins over the radius each menu's own rule has
        out.append(menu_corners(cfg_text, edits))
    return "\n\n".join(out)


def css_font(selectors):
    """The font face your styles.css gives one of the font groups (first family of the last matching rule)."""
    try:
        css = STYLES.read_text(encoding="utf-8")
    except OSError:
        return ""
    css = re.sub(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), "", css, flags=re.S)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = ""
    for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        names = [n.strip() for n in rule.group(1).split(",")]
        m = re.search(r"font-family\s*:\s*([^;]+);", rule.group(2))
        if m and any(n in selectors for n in names):
            found = m.group(1).split(",")[0].strip().strip("\"'")
    return found


def current_colours(base_only=False):
    """{variable: "#rrggbb"} as the bar uses them now (theme_colors.css over yasb_colors.css), or only the
    Windows accent ones (base_only)."""
    out = {}
    for name in ("yasb_colors.css",) if base_only else ("yasb_colors.css", "theme_colors.css"):
        try:
            text = (th.OUT if name == "theme_colors.css" else th.CONFIG / name).read_text(encoding="utf-8")
        except OSError:
            continue
        for var, r, g, b in re.findall(r"--yasb-([\w-]+?)-rgb:\s*(\d+),\s*(\d+),\s*(\d+)", text):
            out[var] = "#%02x%02x%02x" % (int(r), int(g), int(b))
    return out


def save_edits(edits, cfg_text=None):
    """Save the settings and rewrite the ShellFlow block at the end of styles.css."""
    EDITS_JSON.write_text(json.dumps(edits, indent=2), encoding="utf-8")
    if not STYLES.exists():
        return
    css = STYLES.read_text(encoding="utf-8")
    css = re.sub(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n?", "", css, flags=re.S).rstrip("\n") + "\n"
    if cfg_text is None:
        try:
            cfg_text = CONFIG_YAML.read_text(encoding="utf-8")
        except OSError:
            cfg_text = ""
    block = style_block(edits, cfg_text)
    if block:
        css += f"\n{BLOCK_START}\n{block}\n{BLOCK_END}\n"
    STYLES.write_text(css, encoding="utf-8")


def style_block_is_current(edits, cfg_text=None):
    """True when the ShellFlow block at the end of styles.css is exactly what the current settings would write."""
    try:
        css = STYLES.read_text(encoding="utf-8").replace("\r\n", "\n")
        cfg_text = CONFIG_YAML.read_text(encoding="utf-8") if cfg_text is None else cfg_text
    except OSError:
        return True  # nothing to refresh
    m = re.search(re.escape(BLOCK_START) + r"\n(.*?)\n" + re.escape(BLOCK_END), css, re.S)
    return (m.group(1) if m else "") == style_block(edits, cfg_text)
