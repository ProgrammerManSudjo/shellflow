"""Rounded shapes, switches, buttons, sliders and the avatar."""
import math
from functools import lru_cache
from PIL import Image, ImageDraw, ImageOps, ImageTk
from .. import api as th
from .icons import icon_pil

# ============================================================================================
#  6. DRAWING PARTS  (rounded shapes, toggle, buttons, slider, avatar - smooth, via Pillow)
# ============================================================================================
def _rounded_pil(w, h, r, fill, outline, bw, corners, ss):
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], r * ss, fill=fill, outline=outline, width=round(bw * ss), corners=corners)
    return img.resize((w, h), Image.LANCZOS)


def rounded_big_pil(w, h, r, fill, outline, bw, corners):
    """A big rounded rectangle built from one small, smooth one: its four corners are copied to the corners, and a one pixel slice of each
    edge is stretched along that edge (the straight parts of a rounded rectangle are the same all along). The same picture as drawing it
    big, in a fraction of the time (a card on a wide window used to take 30 ms)."""
    half = r + 3
    S = 2 * half + 2
    small = _rounded_pil(S, S, r, fill, outline, bw, corners, 4)
    big = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for box, at in (((0, 0, half, half), (0, 0)), ((S - half, 0, S, half), (w - half, 0)), ((0, S - half, half, S), (0, h - half)),
                    ((S - half, S - half, S, S), (w - half, h - half))):
        big.paste(small.crop(box), at)
    big.paste(small.crop((half, 0, half + 1, half)).resize((w - 2 * half, half), Image.NEAREST), (half, 0))
    big.paste(small.crop((half, S - half, half + 1, S)).resize((w - 2 * half, half), Image.NEAREST), (half, h - half))
    big.paste(small.crop((0, half, half, half + 1)).resize((half, h - 2 * half), Image.NEAREST), (0, half))
    big.paste(small.crop((S - half, half, S, half + 1)).resize((half, h - 2 * half), Image.NEAREST), (w - half, half))
    big.paste(Image.new("RGBA", (w - 2 * half, h - 2 * half), small.getpixel((half, half))), (half, half))
    return big


@lru_cache(maxsize=None)
def rounded(w, h, r, fill, outline=None, bw=0, corners=None):
    """A rounded rectangle. corners=(top left, top right, bottom right, bottom left) as True/False picks which corners are round."""
    half = r + 3
    if w * h >= 30_000 and w > 2 * half + 2 and h > 2 * half + 2:
        return ImageTk.PhotoImage(rounded_big_pil(w, h, r, fill, outline, bw, corners))
    return ImageTk.PhotoImage(_rounded_pil(w, h, r, fill, outline, bw, corners, 4 if w * h < 150_000 else 2))


@lru_cache(maxsize=None)
def switch(on, accent, ink, track, line, scale=1.0):
    """Noctalia-style toggle: on = accent track with a dark knob, off = dark track with an accent knob."""
    ss = 4
    w, h = round(48 * scale), round(26 * scale)
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], h * ss // 2, fill=accent if on else track, outline=None if on else line, width=round(2 * scale * ss))
    cx = (w - 13 * scale) * ss if on else 13 * scale * ss
    r = 8 * scale * ss
    d.ellipse([cx - r, h * ss / 2 - r, cx + r, h * ss / 2 + r], fill=ink if on else accent)
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=512)
def switch_at(pos, accent, ink, track, line, scale=1.0):
    """The toggle with its knob at pos (0 = off, 1 = on; a spring can push it a little past either end). The knob stretches while
    it moves, the track blends from one colour to the other."""
    ss = 4
    w, h = round(48 * scale), round(26 * scale)
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    mix = max(0.0, min(1.0, pos))
    blend = lambda a, b: "#%02x%02x%02x" % tuple(round(int(a[i:i + 2], 16) * (1 - mix) + int(b[i:i + 2], 16) * mix) for i in (1, 3, 5))
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], h * ss // 2, fill=blend(track, accent), outline=None if mix > .98 else line, width=round(2 * scale * ss * (1 - mix)))
    x = (13 + 22 * pos) * scale * ss
    stretch = 1 + 0.55 * math.sin(math.pi * max(0.0, min(1.0, pos)))  # longest in the middle of the move
    r = 8 * scale * ss
    d.rounded_rectangle([x - r * stretch, h * ss / 2 - r, x + r * stretch, h * ss / 2 + r], r, fill=blend(accent, ink))
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=None)
def pill_button(text, w, h, fill, ink, outline, glyph, font_px, hover, scale=1.0):
    """A button: optional icon, then text. `outline` draws a coloured border instead of a fill."""
    ss = 3
    w, h, font_px = round(w * scale), round(h * scale), font_px * scale
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], int(min(14 * scale, h // 2) * ss), fill=hover if hover else fill,
                        outline=outline, width=2 * ss if outline else 0)
    f = th.font(int(font_px * ss))
    tw = d.textlength(text, font=f) if text else 0
    gs = int(18 * ss * scale) if glyph else 0
    gap = int(8 * ss * scale) if glyph and text else 0
    x = (w * ss - (gs + gap + tw)) / 2
    if glyph:
        g = icon_pil(glyph, 18, ink, 2.0).resize((gs, gs), Image.LANCZOS)
        img.alpha_composite(g, (int(x), int((h * ss - gs) / 2)))
    if text:
        d.text((x + gs + gap, h * ss / 2), text, font=f, fill=ink, anchor="lm")
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=None)
def slider_img(w, frac, accent, track, ink):
    ss, h = 3, 26
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy, x = h * ss / 2, 12 * ss + frac * (w - 24) * ss
    d.rounded_rectangle([0, cy - 3 * ss, w * ss, cy + 3 * ss], 3 * ss, fill=track)
    d.rounded_rectangle([0, cy - 3 * ss, x, cy + 3 * ss], 3 * ss, fill=accent)
    d.ellipse([x - 10 * ss, cy - 10 * ss, x + 10 * ss, cy + 10 * ss], fill=accent)
    d.ellipse([x - 4 * ss, cy - 4 * ss, x + 4 * ss, cy + 4 * ss], fill=ink)
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=None)
def logo_img(size, accent, ink):
    """The ShellFlow mark: a rounded square with three bars that flow."""
    ss = 3
    S = size * ss
    k = S / 96
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S - 1, S - 1], int(S * .27), fill=accent)
    for y, x0, x1 in ((28, 20, 76), (46, 20, 58), (64, 38, 76)):
        d.rounded_rectangle([x0 * k, y * k, x1 * k, (y + 10) * k], 5 * k, fill=ink)
    return ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))


def wall_tile(thumb, picked, current, accent, ink, panel):
    """A wallpaper tile: the thumbnail with rounded corners; a ring when picked, a small "Current" badge when it is the wallpaper."""
    ss = 2
    w, h = thumb.size
    big = thumb.resize((w * ss, h * ss), Image.LANCZOS)
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, big.size[0] - 1, big.size[1] - 1], 16 * ss, fill=255)
    img = Image.new("RGBA", big.size, (0, 0, 0, 0))
    img.paste(big, (0, 0), mask)
    d = ImageDraw.Draw(img)
    if picked:
        d.rounded_rectangle([0, 0, big.size[0] - 1, big.size[1] - 1], 16 * ss, outline=accent, width=5 * ss)
    if current:
        f = th.font(13 * ss)
        tw = d.textlength("Current", font=f)
        d.rounded_rectangle([10 * ss, 10 * ss, 10 * ss + tw + 22 * ss, 36 * ss], 13 * ss, fill=accent)
        d.text((21 * ss, 23 * ss), "Current", font=f, fill=ink, anchor="lm")
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=32)
def avatar(path, size, ring, fill, mtime=0):
    """A round profile picture (the file's centre, cropped square), or an empty round placeholder."""
    ss = 3
    S = size * ss
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.ellipse([0, 0, S - 1, S - 1], fill=fill)
    try:
        pic = ImageOps.fit(Image.open(path).convert("RGBA"), (S - 8 * ss, S - 8 * ss), Image.LANCZOS)
        mask = Image.new("L", pic.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, pic.size[0] - 1, pic.size[1] - 1], fill=255)
        base.paste(pic, (4 * ss, 4 * ss), mask)
    except Exception:
        u = icon_pil("user", size // 2, ring, 1.7).resize((S // 2, S // 2), Image.LANCZOS)
        base.alpha_composite(u, (S // 4, S // 4))
    d.ellipse([0, 0, S - 1, S - 1], outline=ring, width=3 * ss)
    return ImageTk.PhotoImage(base.resize((size, size), Image.LANCZOS))
