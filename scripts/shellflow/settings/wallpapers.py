"""The wallpaper folder, thumbnails and setting the wallpaper."""
import hashlib
import os
import re
from pathlib import Path
from PIL import Image, ImageOps
from .. import api as th
from .config_yaml import find_key, parse_scalar, read_widgets
from .constants import THUMBS

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def expand_path(p):
    """$env:NAME, %NAME% and ~ in a path from config.yaml."""
    p = re.sub(r"\$env:(\w+)", lambda m: os.environ.get(m.group(1)) or th.env(m.group(1)) or "", str(p).strip(), flags=re.I)
    return os.path.expandvars(os.path.expanduser(p))


def wallpaper_dirs(text):
    """The folders the YASB wallpapers widget picks from (its image_path), else YASB_WALLPAPERS."""
    lines = text.split("\n")
    name = next((n for n, t in read_widgets(text).items() if t == "yasb.wallpapers.WallpapersWidget"), None)
    found = []
    i = find_key(lines, ["widgets", name, "options", "image_path"]) if name else None
    if i is not None:
        rest = lines[i].split(":", 1)[1].strip()
        if rest.startswith("["):
            found = re.findall(r"[\"']([^\"']+)[\"']", rest)
        elif rest and not rest.startswith("#"):
            found = [parse_scalar(rest)]
        else:  # a list of folders, one `- path` per line
            for l in lines[i + 1:]:
                m = re.match(r"^\s*-\s*[\"']?(.+?)[\"']?\s*(#.*)?$", l)
                if m:
                    found.append(m.group(1))
                elif l.strip() and not l.strip().startswith("#"):
                    break
    if not found and th.env("YASB_WALLPAPERS"):
        found = [th.env("YASB_WALLPAPERS")]
    return [Path(expand_path(p.replace("\\\\", "\\"))) for p in found]


def list_wallpapers(dirs, limit=60):
    out = []
    for d in dirs:
        try:
            out += sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXT and p.is_file())
        except OSError:
            pass
    return out[:limit]


def make_thumb(path, size=(240, 135)):
    """A 16:9 thumbnail of a wallpaper, cached in scripts/.thumbs so the next visit is instant."""
    st = path.stat()
    cache = THUMBS / (hashlib.md5(f"{path}|{st.st_mtime_ns}|{st.st_size}|{size}".encode()).hexdigest() + ".png")
    if cache.exists():
        return Image.open(cache).convert("RGBA")
    im = Image.open(path)
    im.draft("RGB", (size[0] * 2, size[1] * 2))
    im = ImageOps.fit(im.convert("RGB"), size, Image.LANCZOS)
    try:
        THUMBS.mkdir(exist_ok=True)
        im.save(cache)
    except OSError:
        pass
    return im.convert("RGBA")


def set_wallpaper(path):
    """Set the desktop wallpaper (Windows)."""
    try:
        import ctypes
        return bool(ctypes.windll.user32.SystemParametersInfoW(0x14, 0, str(path), 3))  # SPI_SETDESKWALLPAPER, update + broadcast
    except Exception:
        return False


def same_file(a, b):
    try:
        return bool(a) and bool(b) and os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))
    except OSError:
        return False
