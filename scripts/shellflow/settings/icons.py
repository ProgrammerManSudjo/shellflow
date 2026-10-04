"""The line icons."""
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageTk

# ============================================================================================
#  5. ICONS  (monochrome line icons, drawn here - no emoji, no icon font needed)
# ============================================================================================
# Each icon is a list of shapes on a 24 x 24 grid: line (a path), circle, dot (filled), rect, arc.
_FILE = [("line", [(6, 3), (14, 3), (19, 8), (19, 21), (6, 21), (6, 3)]), ("line", [(14, 3), (14, 8), (19, 8)])]


ICONS = {
    "panel": [("rect", 3, 4, 21, 20, 3), ("line", [(9, 4), (9, 20)])],
    "search": [("circle", 10.5, 10.5, 6.5), ("line", [(15.3, 15.3), (20.5, 20.5)])],
    "sliders": [("line", [(4, 7), (6.6, 7)]), ("line", [(11.4, 7), (20, 7)]), ("circle", 9, 7, 2.4),
                ("line", [(4, 17), (12.6, 17)]), ("line", [(17.4, 17), (20, 17)]), ("circle", 15, 17, 2.4)],
    "palette": [("circle", 12, 12, 9), ("dot", 8, 10.5, 1.2), ("dot", 11.5, 7.2, 1.2), ("dot", 16, 9, 1.2), ("dot", 16.5, 14, 1.2)],
    "grid": [("rect", 4, 4, 10.5, 10.5, 2), ("rect", 13.5, 4, 20, 10.5, 2), ("rect", 4, 13.5, 10.5, 20, 2), ("rect", 13.5, 13.5, 20, 20, 2)],
    "bar": [("rect", 3, 4, 21, 10, 3), ("dot", 7.5, 7, 1.1), ("dot", 12, 7, 1.1), ("dot", 16.5, 7, 1.1), ("line", [(3, 20), (21, 20)])],
    "layers": [("line", [(12, 3), (21, 8), (12, 13), (3, 8), (12, 3)]), ("line", [(3, 12.5), (12, 17.5), (21, 12.5)]), ("line", [(3, 16.5), (12, 21.5), (21, 16.5)])],
    "pen": [("line", [(4, 20), (4.8, 15.6), (15.5, 4.9), (19.1, 8.5), (8.4, 19.2), (4, 20)]), ("line", [(13.5, 6.9), (17.1, 10.5)])],
    "folder": [("line", [(3, 7), (3, 18.5), (21, 18.5), (21, 9), (11.5, 9), (9.5, 6), (4, 6), (3, 7)])],
    "info": [("circle", 12, 12, 9), ("line", [(12, 11), (12, 16.5)]), ("dot", 12, 7.8, 1.2)],
    "tiles": [("rect", 3, 4, 21, 20, 2.5), ("line", [(12, 4), (12, 20)]), ("line", [(12, 12), (21, 12)])],
    "monitor": [("rect", 3, 4, 21, 16, 2.5), ("line", [(8, 20), (16, 20)]), ("line", [(12, 16), (12, 20)])],
    "x": [("line", [(6, 6), (18, 18)]), ("line", [(18, 6), (6, 18)])],
    "user": [("circle", 12, 8, 4), ("arc", 12, 21, 8, 190, 350)],
    "file": _FILE,
    "file_text": _FILE + [("line", [(9, 13), (16, 13)]), ("line", [(9, 17), (16, 17)])],
    "file_code": _FILE + [("line", [(10.5, 12), (8.5, 14.5), (10.5, 17)]), ("line", [(14.5, 12), (16.5, 14.5), (14.5, 17)])],
    "terminal": [("rect", 3, 5, 21, 19, 2.5), ("line", [(7, 10), (10, 12), (7, 14)]), ("line", [(12, 15), (17, 15)])],
    "reset": [("arc", 12, 12, 8, 40, 330), ("line", [(19.5, 3.5), (19.5, 8.5), (14.5, 8.5)])],
    "up": [("line", [(12, 19), (12, 5)]), ("line", [(6, 11), (12, 5), (18, 11)])],
    "down": [("line", [(12, 5), (12, 19)]), ("line", [(6, 13), (12, 19), (18, 13)])],
    "left": [("line", [(19, 12), (5, 12)]), ("line", [(11, 6), (5, 12), (11, 18)])],
    "right": [("line", [(5, 12), (19, 12)]), ("line", [(13, 6), (19, 12), (13, 18)])],
    "eye": [("circle", 12, 12, 3), ("line", [(2, 12), (6, 7.5), (12, 5.5), (18, 7.5), (22, 12), (18, 16.5), (12, 18.5), (6, 16.5), (2, 12)])],
    "eye_off": [("circle", 12, 12, 3), ("line", [(2, 12), (6, 7.5), (12, 5.5), (18, 7.5), (22, 12), (18, 16.5), (12, 18.5), (6, 16.5), (2, 12)]), ("line", [(4, 4), (20, 20)])],
    "plus": [("line", [(12, 5), (12, 19)]), ("line", [(5, 12), (19, 12)])],
    "check": [("line", [(5, 12.5), (10, 17.5), (19, 7)])],
    "chev_down": [("line", [(6, 9), (12, 15), (18, 9)])],
    "chev_right": [("line", [(9, 6), (15, 12), (9, 18)])],
    "clock": [("circle", 12, 12, 9), ("line", [(12, 7), (12, 12), (15.5, 14)])],
    "home": [("line", [(3, 11), (12, 3), (21, 11)]), ("line", [(5.5, 9.5), (5.5, 20), (18.5, 20), (18.5, 9.5)])],
    "power": [("arc", 12, 13, 7.5, 310, 230), ("line", [(12, 3.5), (12, 11.5)])],
    "image": [("rect", 3, 4, 21, 20, 2.5), ("circle", 9, 9.5, 1.7), ("line", [(3, 17), (9, 12.5), (14, 17), (17, 14.5), (21, 18)])],
    "window": [("rect", 3, 4, 21, 20, 2.5), ("line", [(3, 9), (21, 9)])],
    "dots": [("dot", 6, 12, 1.5), ("dot", 12, 12, 1.5), ("dot", 18, 12, 1.5)],
    "pill_dots": [("rect", 3, 8, 21, 16, 4), ("dot", 8, 12, 1.1), ("dot", 12, 12, 1.1), ("dot", 16, 12, 1.1)],
    "zone_left": [("rect", 2.5, 6, 21.5, 18, 3), ("rect", 5.5, 9, 10.5, 15, 1.2)],
    "zone_center": [("rect", 2.5, 6, 21.5, 18, 3), ("rect", 9.5, 9, 14.5, 15, 1.2)],
    "zone_right": [("rect", 2.5, 6, 21.5, 18, 3), ("rect", 13.5, 9, 18.5, 15, 1.2)],
    "cpu": [("rect", 6, 6, 18, 18, 2), ("rect", 9.5, 9.5, 14.5, 14.5, 1), ("line", [(9, 3), (9, 6)]), ("line", [(15, 3), (15, 6)]), ("line", [(9, 18), (9, 21)]), ("line", [(15, 18), (15, 21)])],
    "battery": [("rect", 3, 8, 19, 16, 2.5), ("line", [(21.5, 11), (21.5, 13)])],
    "wifi": [("arc", 12, 17, 12, 235, 305), ("arc", 12, 17, 7.5, 230, 310), ("dot", 12, 18, 1.3)],
    "volume": [("line", [(4, 9.5), (8, 9.5), (13, 5.5), (13, 18.5), (8, 14.5), (4, 14.5), (4, 9.5)]), ("arc", 13, 12, 5, 300, 60), ("arc", 13, 12, 8.5, 300, 60)],
    "bell": [("line", [(6, 16), (6, 11), (12, 4.5), (18, 11), (18, 16), (20, 18), (4, 18), (6, 16)]), ("line", [(10, 21), (14, 21)])],
    "cloud": [("line", [(7, 18), (17, 18), (20, 15), (17.5, 11.5), (14.5, 12), (12, 8.5), (8.5, 9.5), (7.5, 13), (4, 14.5), (7, 18)])],
    "music": [("line", [(9, 18), (9, 6), (19, 4), (19, 16)]), ("circle", 6.5, 18, 2.5), ("circle", 16.5, 16, 2.5)],
    "code": [("line", [(8, 7), (3, 12), (8, 17)]), ("line", [(16, 7), (21, 12), (16, 17)]), ("line", [(14, 5), (10, 19)])],
    "globe": [("circle", 12, 12, 9), ("line", [(3, 12), (21, 12)]), ("arc", 12, 12, 9, 120, 240), ("arc", 12, 12, 9, -60, 60), ("line", [(12, 3), (12, 21)])],
    "video": [("rect", 3, 6, 15, 18, 3), ("line", [(15, 11), (21, 7.5), (21, 16.5), (15, 13)])],
    "message": [("line", [(4, 5), (20, 5), (20, 16), (11, 16), (7, 20), (7, 16), (4, 16), (4, 5)])],
    "copy": [("rect", 8, 8, 20, 20, 2.5), ("line", [(16, 8), (16, 5.5), (13.5, 3.5), (5.5, 3.5), (4, 5), (4, 14), (5.5, 16), (8, 16)])],
    "box": [("rect", 5, 5, 19, 19, 4)],
    "link": [("line", [(10, 14), (14, 10)]), ("line", [(9, 10), (6.5, 10), (4, 12), (6.5, 14), (9, 14)]), ("line", [(15, 10), (17.5, 10), (20, 12), (17.5, 14), (15, 14)])],
    "arrow_ur": [("line", [(7, 17), (17, 7)]), ("line", [(8, 7), (17, 7), (17, 16)])],
    "keyboard": [("rect", 2.5, 6.5, 21.5, 17.5, 3), ("dot", 6.5, 10.5, 1), ("dot", 10, 10.5, 1), ("dot", 14, 10.5, 1), ("dot", 17.5, 10.5, 1), ("line", [(7, 14.5), (17, 14.5)])],
    "audio": [("line", [(5, 15), (5, 10)]), ("line", [(9, 19), (9, 6)]), ("line", [(13, 16), (13, 9)]), ("line", [(17, 18), (17, 12)]), ("line", [(21, 14), (21, 11)])],
    "title": [("rect", 3, 5, 21, 19, 3), ("line", [(7, 10), (17, 10)]), ("line", [(7, 14), (13, 14)])],
    "trash": [("line", [(4, 7), (20, 7)]), ("line", [(9, 7), (9, 4.5), (15, 4.5), (15, 7)]), ("line", [(6, 7), (7, 20), (17, 20), (18, 7)]), ("line", [(10, 11), (10, 16)]), ("line", [(14, 11), (14, 16)])],
    "archive": [("rect", 3, 4, 21, 9, 2), ("rect", 5, 9, 19, 20, 2), ("line", [(10, 13), (14, 13)])],
    "camera": [("rect", 3, 7, 21, 19, 3), ("circle", 12, 13, 3.5), ("line", [(8.5, 7), (10, 4.5), (14, 4.5), (15.5, 7)])],
}


# the icon of a widget, by its type or name (the first word that matches)
WIDGET_ICONS = (("whkd", "keyboard"), ("notes", "file_text"), ("cava", "audio"), ("active_window", "title"), ("activewindow", "title"),
                ("clock", "clock"), ("workspace", "pill_dots"), ("layout", "tiles"), ("control", "sliders"),
                ("taskbar", "window"), ("systray", "dots"), ("power", "power"), ("home", "home"),
                ("wallpaper", "image"), ("battery", "battery"), ("wifi", "wifi"), ("network", "wifi"),
                ("volume", "volume"), ("media", "music"), ("weather", "cloud"), ("meteo", "cloud"),
                ("cpu", "cpu"), ("memory", "cpu"), ("disk", "cpu"), ("notif", "bell"), ("bell", "bell"),
                ("obs", "video"), ("custom", "code"), ("app", "grid"))


def widget_icon(name, wtype=""):
    key = (name + " " + wtype).lower()
    return next((icon for word, icon in WIDGET_ICONS if word in key), "box")


def file_icon(path):
    ext = Path(path).suffix.lower()
    if ext in (".py", ".css", ".json", ".yaml", ".yml", ".toml", ".lua", ".ahk"):
        return "file_code"
    if ext in (".log", ".txt", ".md", ".env", ""):
        return "file_text"
    return "file"


def icon_pil(name, size, colour, stroke=1.9):
    ss = 8
    S, k = size * ss, size * ss / 24
    w = max(1, round(stroke * k))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for kind, *a in ICONS[name]:
        if kind == "line":
            pts = [(x * k, y * k) for x, y in a[0]]
            d.line(pts, fill=colour, width=w, joint="curve")
            for px, py in (pts[0], pts[-1]):
                d.ellipse([px - w / 2, py - w / 2, px + w / 2, py + w / 2], fill=colour)
        elif kind == "circle":
            cx, cy, r = a
            d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], outline=colour, width=w)
        elif kind == "dot":
            cx, cy, r = a
            d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=colour)
        elif kind == "rect":
            x0, y0, x1, y1, r = a
            d.rounded_rectangle([x0 * k, y0 * k, x1 * k, y1 * k], r * k, outline=colour, width=w)
        elif kind == "arc":
            cx, cy, r, s, e = a
            d.arc([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], s, e, fill=colour, width=w)
    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=None)
def icon(name, size, colour):
    return ImageTk.PhotoImage(icon_pil(name, size, colour))
