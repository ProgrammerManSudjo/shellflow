"""The scheme picker window (theme.py menu)."""
import math
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ..colors import accent_shades, apply, current_variant, custom_colours, get_seed, lerp, menu_items, rgb, scheme
from .winapi import make_dpi_aware, monitor_info, round_window

# ============================================================================================
#  9. SCHEME PICKER
#  The window opened by `theme.py menu`: a grid of schemes, hover to preview
#  the colours, click to apply.
# ============================================================================================
BASE = (18, 18, 18)  # tile colour at rest


TILE_W, TILE_H, GAP, PAD, TILE_R, LIFT, SS = 150, 120, 10, 10, 18, 4, 2  # SS = supersampling


def build_items(seed):
    """One picker tile per scheme: its label and the colours shown on it."""
    items = []
    for key, label in menu_items():
        if key in ("windows", "custom"):
            c = accent_shades()
            mine = custom_colours() if key == "custom" else {}
            pick = lambda var: tuple(mine[var][:3]) if var in mine else c[var]
            dots, tint = [pick("accent-light2"), pick("accent"), pick("accent-light1")], pick("accent-dark2")
        else:  # middle dot = the accent the bar uses; the side dots show the scheme's character
            s = scheme(key, seed)
            dots = [rgb(s.secondary_palette.tone(65)), rgb(s.primary_palette.tone(50)),
                    rgb(s.tertiary_palette.tone(65))]
            tint = rgb(s.primary_palette.tone(22))
        items.append({"key": key, "label": label, "dots": dots, "tint": tint})
    return items


def layout(n, s):
    """Tile rectangles (2 rows) and the window size, at scale s."""
    rows = 2 if n > 3 else 1
    cols = math.ceil(n / rows)
    tw, th, gap, pad = (round(v * s) for v in (TILE_W, TILE_H, GAP, PAD))
    rects = [(pad + i % cols * (tw + gap), pad + i // cols * (th + gap)) for i in range(n)]
    rects = [(x, y, x + tw, y + th) for x, y in rects]
    return rects, (2 * pad + cols * tw + (cols - 1) * gap, 2 * pad + rows * th + (rows - 1) * gap)


def font(size):
    """The picker's font: Poppins if it is installed, else Segoe UI."""
    fonts = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts"
    for name in ("Poppins-Medium.ttf", "segoeuib.ttf"):
        for path in (fonts / name, name):
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
    return ImageFont.load_default(size)


def render(items, rects, size, s, hover, active, bg=(0, 0, 0)):
    """Draw the whole picker as one image. hover holds 0..1 per tile (0 = idle, 1 = hovered)."""
    img = Image.new("RGB", (size[0] * SS, size[1] * SS), bg)
    d = ImageDraw.Draw(img)
    f = font(round(13 * s * SS))
    for it, (x0, y0, x1, y1), t in zip(items, rects, hover):
        grow = LIFT * s * t
        box = [(x0 - grow) * SS, (y0 - grow) * SS, (x1 + grow) * SS, (y1 + grow) * SS]
        fill, radius, ring = lerp(BASE, it["tint"], t * 0.85), (TILE_R + 2 * t) * s * SS, it["dots"][1]
        d.rounded_rectangle(box, radius=radius, fill=fill)
        if it["key"] == active:
            d.rounded_rectangle(box, radius=radius, outline=ring, width=round(2.5 * s * SS))
        elif t > 0.02:
            d.rounded_rectangle(box, radius=radius, outline=lerp(fill, ring, 0.55 * t), width=round(1.5 * s * SS))
        cx, cy, scale = (x0 + x1) / 2, y0 + (y1 - y0) * 0.38, 1 + 0.12 * t
        for dx, rad, col in ((-33, 12, it["dots"][0]), (0, 18, it["dots"][1]), (33, 12, it["dots"][2])):
            r, px, py = rad * s * scale * SS, (cx + dx * s * scale) * SS, cy * SS
            d.ellipse([px - r, py - r, px + r, py + r], fill=col)  # the scheme's real colours, always (hover only lifts the tile)
        d.text((cx * SS, (y0 + (y1 - y0) * 0.80) * SS), it["label"], font=f,
               fill=lerp((190, 190, 190), (255, 255, 255), t), anchor="mm")
    return img.resize(size, Image.LANCZOS)


def show_picker():
    """Open the picker on the monitor under the cursor; clicking a tile applies that scheme."""
    import tkinter as tk
    from PIL import ImageTk

    make_dpi_aware()
    seed = get_seed()
    items, active = build_items(seed), current_variant()
    n = len(items)
    work, s = monitor_info()
    rects, size = layout(n, s)

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.configure(bg="black")
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.0)
    x, y = work[0] + (work[2] - work[0] - size[0]) // 2, work[1] + (work[3] - work[1] - size[1]) // 2
    root.geometry(f"{size[0]}x{size[1]}+{x}+{y}")
    label = tk.Label(root, bd=0, highlightthickness=0, bg="black")
    label.pack()

    hover, target = [0.0] * n, [0.0] * n
    st = {"alpha": 0.0, "goal": 1.0, "running": False, "closing": False, "choice": None}

    def tick():  # animate hover and fade, redraw, stop when nothing moves
        busy = False
        for i in range(n):
            if abs(target[i] - hover[i]) > 0.01:
                hover[i] += (target[i] - hover[i]) * 0.35
                busy = True
            else:
                hover[i] = target[i]
        if abs(st["goal"] - st["alpha"]) > 0.01:
            st["alpha"] += (st["goal"] - st["alpha"]) * 0.4
            busy = True
        else:
            st["alpha"] = st["goal"]
        root.attributes("-alpha", max(0.0, min(1.0, st["alpha"])))
        label.image = photo = ImageTk.PhotoImage(render(items, rects, size, s, hover, active))
        label.configure(image=photo)
        if busy:
            root.after(16, tick)
        else:
            st["running"] = False
            if st["closing"]:
                root.destroy()

    def kick():
        if not st["running"]:
            st["running"] = True
            tick()

    def hit(e):
        return next((i for i, (x0, y0, x1, y1) in enumerate(rects) if x0 <= e.x < x1 and y0 <= e.y < y1), -1)

    def hot(i):
        target[:] = [1.0 if k == i else 0.0 for k in range(n)]
        kick()

    def close(choice=None):
        if not st["closing"]:
            st.update(closing=True, choice=choice, goal=0.0)
            kick()

    label.bind("<Motion>", lambda e: hot(hit(e)))
    label.bind("<Leave>", lambda e: hot(-1))
    label.bind("<Button-1>", lambda e: hit(e) >= 0 and close(items[hit(e)]["key"]))
    root.bind("<Escape>", lambda e: close())
    root.bind("<FocusOut>", lambda e: root.after(120, lambda: None if root.focus_displayof() else close()))

    root.update_idletasks()
    root.deiconify()
    root.update()
    round_window(root)
    root.lift()
    root.focus_force()
    kick()
    root.mainloop()
    if st["choice"]:
        apply(st["choice"], seed)
