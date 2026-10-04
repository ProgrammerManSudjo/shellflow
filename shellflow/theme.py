"""YASB theme tool: Material You colours for the bar, plus apps that follow the Windows accent.

USAGE
  pythonw theme.py menu      open the scheme picker
  pythonw theme.py <name>    apply a scheme: windows, content, fidelity, tonal_spot, monochrome,
                             expressive, neutral, vibrant, fruit_salad, custom
  pythonw theme.py apps      refresh the app themes only
  pythonw theme.py settings  open ShellFlow, the settings window (settings.py, next to this file)
  pythonw theme.py watch     keep the app themes in sync when the wallpaper or the accent changes (runs in the background)
  python  theme.py doctor    check why ShellFlow will not open and write shellflow_doctor.txt (run it from a terminal)
  python  theme.py install-menu   (re)write the Home menu entry that opens ShellFlow, with full paths
  python  theme.py setup     do everything once: the Home menu entry, and the background helper (now and with Windows)
  python  theme.py windhawk  recolour the Windhawk styler mods with the current scheme (switch Windhawk on under Templates first)

HOW IT WORKS
  1. A scheme writes theme_colors.css (imported by styles.css after yasb_colors.css).
     The seed colour is the wallpaper's dominant colour, or the Windows accent.
  2. The app themes always follow the Windows accent (read from yasb_colors.css) and are
     refreshed on every run. An app that is not installed is skipped.

WHERE THE APP THEMES GO
  Default locations are found automatically (listed above each app below). To change one, set its
  YASB_* variable in the environment or in the .env next to styles.css: the folders you list
  (";"-separated, created if missing) are then used instead. All variables are in .env.example.
  YASB_APPS (for example zed,obs) limits which apps are written; the settings window sets it.

ERRORS
  pythonw hides them, so they are written to theme_error.log next to this file.
"""
import ctypes
import hashlib
import importlib
import json
import math
import os
import re
import subprocess
import sys
import time
import traceback
import zlib
import warnings
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

# YASB is a bundled app. A program it starts can inherit its Tcl/Tk folders, and Tk then fails to start with no
# window and no message. These two variables are dropped when they point outside this Python's own folder.
for _v, _f in (("TCL_LIBRARY", "init.tcl"), ("TK_LIBRARY", "tk.tcl")):
    _p = os.environ.get(_v)
    if _p and not os.path.abspath(_p).lower().startswith(os.path.abspath(sys.base_prefix).lower()):
        os.environ.pop(_v, None)
CLEAN_ENV_DROP = ("PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY")  # not passed on to helpers we start

# ============================================================================================
#  0. EARLY START  (only for `theme.py settings`; runs before the heavy imports below)
#  The first start after a restart can take many seconds: Python, Tk, Pillow and materialyoucolor
#  all load from a cold disk. So this block, using nothing but the standard library, makes sure that
#    - only one ShellFlow is starting or open (pressing the menu again brings the open one forward),
#    - a small "ShellFlow is starting" window shows at once,
#    - every step is timed in shellflow_start.log, so a slow or failed start can be read afterwards.
# ============================================================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
_T0 = time.time()
_PIDFILE = os.path.join(_HERE, "shellflow.pid")
_STARTLOG = os.path.join(_HERE, "shellflow_start.log")


_LOGS = None


def logs_on():
    """The diagnostic logs (start, helper, hang) are written only when the .env has YASB_LOGS=1 (ShellFlow > Backup > Log files).
    Read once per process; set th._LOGS = None to read it again. Errors still go to theme_error.log either way."""
    global _LOGS
    if _LOGS is None:
        _LOGS = False
        conf = os.path.dirname(_HERE) if os.path.basename(_HERE).lower() == "scripts" else _HERE
        try:
            for line in open(os.path.join(conf, ".env"), encoding="utf-8-sig"):
                key, _, value = line.partition("=")
                if key.strip() == "YASB_LOGS":
                    _LOGS = value.strip().strip("\"'") == "1"
        except OSError:
            pass
    return _LOGS


def start_log(text):
    """One line in shellflow_start.log (the last 60 are kept), with the seconds since this process began. Only with logs on."""
    if not logs_on():
        return
    try:
        old = open(_STARTLOG, encoding="utf-8").read().splitlines()[-60:] if os.path.exists(_STARTLOG) else []
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + "[pid %d +%.1fs] " % (os.getpid(), time.time() - _T0) + text
        open(_STARTLOG, "w", encoding="utf-8").write("\n".join(old + [line]) + "\n")
    except OSError:
        pass


def proc_start(pid):
    """When a process started (a number that never repeats), or None if it is not running. Checking this too makes a
    pid that Windows handed to another program after a restart harmless."""
    try:
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        c, e, kt, ut = (ctypes.c_ulonglong() for _ in range(4))
        ok = k.GetProcessTimes(ctypes.c_void_p(h), ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut))
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
        k.CloseHandle(ctypes.c_void_p(h))
        return c.value if ok and code.value == 259 else None  # 259 = still running
    except Exception:
        return None


def _wait_for_replaced():
    """SHELLFLOW_REPLACE=<pid> means this ShellFlow was started by another one that is closing (the settings window reopens itself when
    its width or sidebar must change): wait for that one to be gone (at most 6 s) before looking for other copies."""
    try:
        old = int(os.environ.get("SHELLFLOW_REPLACE", "0"))
    except ValueError:
        return
    for _ in range(60):
        if not old or old == os.getpid() or proc_start(old) is None:
            break
        time.sleep(.1)


def _other_instance():
    """(pid, seconds since it started) of another ShellFlow that is really still running, else None."""
    try:
        pid, born, stamp = open(_PIDFILE, encoding="utf-8").read().split()
        if int(pid) != os.getpid() and proc_start(pid) == int(born):
            return int(pid), time.time() - float(stamp)
    except (OSError, ValueError):
        pass
    return None


def _windows_of(pid):
    """[(hwnd, visible)]: the top-level windows titled ShellFlow that belong to process `pid` (and nobody else:
    a folder or project that happens to be called ShellFlow must never count as the settings window)."""
    found = []
    try:
        u = ctypes.windll.user32

        def each(hwnd, _):
            owner = ctypes.c_ulong()
            u.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(owner))
            if owner.value == pid:
                n = u.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(ctypes.c_void_p(hwnd), buf, n + 1)
                if buf.value == "ShellFlow":
                    found.append((hwnd, bool(u.IsWindowVisible(ctypes.c_void_p(hwnd)))))
            return True
        u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(each), 0)
    except Exception:
        pass
    return found


def _front_existing(pid):
    """Bring the open ShellFlow of process `pid` to the front. True only if it has a VISIBLE window."""
    try:
        u = ctypes.windll.user32
        for hwnd, visible in _windows_of(pid):
            if visible:
                u.ShowWindow(ctypes.c_void_p(hwnd), 5)
                u.SetForegroundWindow(ctypes.c_void_p(hwnd))
                return True
    except Exception:
        pass
    return False


def _splash_colours():
    """(border, background, title) for the "starting" window: the colours the bar and ShellFlow use right now
    (yasb_colors.css, with the applied scheme in theme_colors.css on top). Standard library only, so it is instant."""
    here = os.path.dirname(os.path.abspath(__file__))
    conf = os.path.dirname(here) if os.path.basename(here).lower() == "scripts" else here
    shades = {}
    for name in ("yasb_colors.css", "theme_colors.css"):  # the applied scheme wins over the Windows accent
        try:
            text = open(os.path.join(conf, name), encoding="utf-8").read()
        except OSError:
            continue
        for key, r, g, b in re.findall(r"--yasb-([\w-]+?)-rgb:\s*(\d+),\s*(\d+),\s*(\d+)", text):
            shades[key] = (int(r), int(g), int(b))
    acc = shades.get("accent", (130, 115, 82))
    hexa = lambda c, f=1.0: "#%02x%02x%02x" % tuple(min(255, round(v * f)) for v in c)
    return hexa(shades.get("accent-light1", acc)), hexa(acc, .06), hexa(shades.get("accent-light2", acc))


SPLASH_BORDER = 5  # px: the accent border of the starting window


def _mix(a, b, t):
    """Blend two #rrggbb colours (t = 0 gives a)."""
    pa, pb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x * (1 - t) + y * t) for x, y in zip(pa, pb))


def _ring(w, h, inset, r):
    """The points of a rounded rectangle (clockwise, a point at least every 10 px), for the border the light travels along."""
    import math
    x0, y0, x1, y1 = inset, inset, w - inset, h - inset
    pts = []
    corners = ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180))
    for n, (cx, cy, start) in enumerate(corners):
        arc = [(cx + r * math.cos(math.radians(start + k)), cy + r * math.sin(math.radians(start + k))) for k in range(0, 91, 10)]
        if pts:  # the straight edge between the previous corner and this one
            (ax, ay), (bx, by) = pts[-1], arc[0]
            steps = max(1, int(math.hypot(bx - ax, by - ay) // 10))
            pts += [(ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps) for i in range(1, steps)]
        pts += arc
    (ax, ay), (bx, by) = pts[-1], pts[0]  # and the edge that closes it
    steps = max(1, int(math.hypot(bx - ax, by - ay) // 10))
    pts += [(ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps) for i in range(1, steps)]
    return pts


def _show_splash():
    """The small "ShellFlow is starting" window, in the current accent colours: a thick accent border with a light that runs around
    it while the real window is built. Returns the (hidden) Tk root; the splash is its Toplevel, `root.splash`, so settings.py can
    keep it up while the real window is built behind it. If anything fails, the root is destroyed again (a second Tk root would
    break the images of the real window)."""
    import tkinter as tk
    border, bg, title = _splash_colours()
    root = tk.Tk()
    root.withdraw()
    try:
        top = tk.Toplevel(root)
        top.title("ShellFlow starting")
        top.overrideredirect(True)
        top.configure(bg=bg)
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        w, h = 460, 150
        top.geometry("%dx%d+%d+%d" % (w, h, (sw - w) // 2, (sh - h) // 2))
        cv = tk.Canvas(top, width=w, height=h, bg=bg, highlightthickness=0)
        cv.place(x=0, y=0)
        pts = _ring(w, h, SPLASH_BORDER / 2 + 1, 12)
        flat = [v for p in pts for v in p]
        cv.create_polygon(flat, outline=_mix(border, bg, .55), fill="", width=SPLASH_BORDER)  # the border itself
        light = cv.create_line(flat[:4], fill=_mix(border, "#ffffff", .25), width=SPLASH_BORDER, capstyle="round", joinstyle="round")  # the light
        seg = max(4, len(pts) * 22 // 100)  # about a fifth of the way round
        cv.create_text(w // 2, 62, text="ShellFlow", fill=title, font=("Segoe UI", 22, "bold"))
        cv.create_text(w // 2, 100, text="Starting...  the first start after a restart can take a little while", fill="#b3b3b3", font=("Segoe UI", 9))
        top.attributes("-topmost", True)
        try:
            top.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        top.update()
        for step in range(1, 6):  # fade in right here, in ~60 ms: nothing else runs while ShellFlow is busy starting
            top.attributes("-alpha", step / 5)
            top.update()
            time.sleep(.012)
    except Exception:
        root.destroy()
        raise
    try:  # rounded corners (Windows 11); the border is drawn above, so Windows' own thin border is switched off
        dwm = ctypes.windll.dwmapi
        hwnd = ctypes.windll.user32.GetParent(top.winfo_id()) or top.winfo_id()
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)  # DWMWA_WINDOW_CORNER_PREFERENCE = round
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(ctypes.c_int(-2)), 4)  # DWMWA_BORDER_COLOR = none
    except Exception:
        pass
    t0 = time.time()

    def tick():
        try:
            age = time.time() - t0
            i = int(age * len(pts) * .9) % len(pts)  # about one lap in 1.1 s
            cv.coords(light, *[v for p in (pts + pts)[i:i + seg] for v in p])
            top.after(26, tick)
        except tk.TclError:
            pass  # the splash is gone
    tick()
    root.splash = top
    return root


def _early():
    if __name__ != "__main__" or sys.argv[1:2] != ["settings"]:
        return None
    start_log("start: python=%s cwd=%s" % (sys.executable, os.getcwd()))
    _wait_for_replaced()
    other = _other_instance()
    if other:
        pid, age = other
        if _front_existing(pid):
            start_log("another ShellFlow (pid %d) is open: brought its window to the front" % pid)
            sys.exit(0)
        if age < 45:  # the first press is still starting (cold disk): do not pile up a second copy
            start_log("another ShellFlow (pid %d) is still starting after %.0fs: this press does nothing" % (pid, age))
            sys.exit(0)
        start_log("another ShellFlow (pid %d) has had no visible window for %.0fs: ending it and starting again" % (pid, age))
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
        except Exception:
            pass
    try:
        open(_PIDFILE, "w", encoding="utf-8").write("%d %d %f" % (os.getpid(), proc_start(os.getpid()) or 0, time.time()))
    except OSError:
        pass
    try:
        import atexit
        atexit.register(lambda: os.path.exists(_PIDFILE) and open(_PIDFILE).read().split()[0] == str(os.getpid()) and os.remove(_PIDFILE))
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # before any window exists, so it draws sharply
    except Exception:
        pass
    try:
        root = _show_splash()
        start_log("splash shown")
        return root
    except Exception as e:
        start_log("no splash: %s" % e)
        return None


EARLY_ROOT = _early()

try:
    from materialyoucolor.blend import Blend
    from materialyoucolor.hct import Hct
    from materialyoucolor.quantize import QuantizeCelebi
    from materialyoucolor.score.score import Score
    from PIL import Image, ImageDraw, ImageFont
except ImportError as _e:  # pythonw would swallow this and ShellFlow would simply not appear
    start_log("FAILED: a Python package is missing: %s (python=%s)" % (_e, sys.executable))
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        if EARLY_ROOT is not None:
            EARLY_ROOT.destroy()
        _r = _tk.Tk()
        _r.withdraw()
        _r.attributes("-topmost", True)
        _mb.showerror("ShellFlow", "A Python package is missing:\n\n%s\n\nInstall it with:\n  \"%s\" -m pip install pillow materialyoucolor\n\nPython used: %s"
                      % (_e, sys.executable.replace("pythonw", "python"), sys.executable), parent=_r)
    except Exception:
        pass
    raise

# ============================================================================================
#  1. SETTINGS
#  Where things live, and the names and tones used below.
# ============================================================================================
warnings.simplefilter("ignore")
start_log("heavy imports done") if __name__ == "__main__" and sys.argv[1:2] == ["settings"] else None
HERE = Path(__file__).parent
CONFIG = HERE.parent if HERE.name.lower() == "scripts" else HERE  # folder with styles.css
OUT = CONFIG / "theme_colors.css"
LOG = HERE / "theme_error.log"

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


# ============================================================================================
#  3. SEED COLOUR
#  The colour a scheme is built from: the wallpaper's dominant colour,
#  or the Windows accent when there is no usable wallpaper.
# ============================================================================================


def write_if_changed(path, text):
    """Write a text file only when its content differs. YASB, Discord, Zed and the rest reload whenever a file is
    touched, so rewriting identical content would make them reload for nothing (and can start a reload loop)."""
    path = Path(path)
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except (OSError, UnicodeDecodeError):
        pass
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


def fhash(path):
    """A fingerprint of a file's content (so a rewrite with the same content is not a change)."""
    try:
        return hashlib.md5(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def parse_colour(text):
    """"#rgb", "#rrggbb", "#rrggbbaa", "rgb(r, g, b)" or "rgba(r, g, b, a)" -> (r, g, b, alpha 0..1), else None."""
    t = text.strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})", t)
    if m:
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) in (3, 4) else h
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), (int(h[6:8], 16) / 255 if len(h) == 8 else 1.0)
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)\s*(?:[,/]\s*([\d.]+%?)\s*)?\)", t)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        a = m.group(4)
        a = 1.0 if a is None else (float(a[:-1]) / 100 if a.endswith("%") else float(a))
        if max(r, g, b) <= 255 and 0 <= a <= 1:
            return r, g, b, a
    return None


# the colours of the "custom" scheme (set in the settings window, Edits page; saved in settings.json)
CUSTOM_VARS = ("accent", "accent-dark1", "accent-dark2", "accent-dark3", "accent-light1", "accent-light2",
               "accent-light3", "background", "foreground")


def custom_colours():
    """{variable: (r, g, b, alpha)} of the colours you set yourself, or {} (then there is no custom scheme)."""
    try:
        raw = json.loads((HERE / "settings.json").read_text(encoding="utf-8")).get("colours", {})
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


# ============================================================================================
#  4. WINDOWS ACCENT
#  The accent shades YASB writes to yasb_colors.css: what the bar uses and
#  what every app theme below is built from.
# ============================================================================================


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
    return write_apps()


def current_variant():
    """The scheme that is applied right now, read from theme_colors.css."""
    try:
        return re.search(r"variant: (\w+)", OUT.read_text()).group(1)
    except (OSError, AttributeError):
        return "windows"


# ============================================================================================
#  6. APP THEMES - SHARED PARTS
#  How settings, folders and the shared colour palette work for every app.
# ============================================================================================
_DOTENV = {"stamp": None, "data": {}}


def dotenv():
    """The .env next to styles.css as a dict (read again whenever the file changes)."""
    path = CONFIG / ".env"
    try:
        st = path.stat()
    except OSError:
        return {}
    stamp = (st.st_mtime_ns, st.st_size)
    if _DOTENV["stamp"] != stamp:
        data = {}
        try:
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                key, sep, value = line.partition("=")
                if sep and not key.strip().startswith("#"):
                    data[key.strip()] = value.strip().strip("\"'")
        except OSError:
            pass
        _DOTENV.update(stamp=stamp, data=data)
    return _DOTENV["data"]


# The settings ShellFlow writes itself. They are read from the .env ONLY: YASB loads that file into its own environment when
# it starts, so every program YASB starts (ShellFlow, the helper) inherits a copy that goes stale as soon as a setting changes.
LIVE_KEYS = {"YASB_FILEPILOT_EXE", "YASB_HELIUM_AUTORESTART", "YASB_HELIUM_EXE", "YASB_HELIUM_TAB", "YASB_SOUND_VARY", "YASB_WINDHAWK_ACTIVE", "YASB_WINDHAWK_MATCH", "YASB_ATTACH", "YASB_ATTACH_ALIGN", "YASB_MOTION", "YASB_LOGS", "YASB_SOUNDS", "YASB_SOUND_VOLUME", "YASB_BAR_SOUNDS", "YASB_SYNC", "YASB_APPS", "YASB_USERNAME", "YASB_PFP", "YASB_SPLASH"}


def env(name):
    """A setting. Normally the environment variable, else the same key in the .env next to styles.css; the settings ShellFlow
    writes itself (LIVE_KEYS and the app folders) come from the .env only, so a change you make is the change that is used."""
    live = name in LIVE_KEYS or name in {row[2] for row in globals().get("APP_TABLE", ())}
    if not live and os.environ.get(name):
        return os.environ[name]
    return dotenv().get(name, "")


def where(name):
    """A Windows folder from its environment variable: APPDATA, LOCALAPPDATA, USERPROFILE ..."""
    return Path(os.environ.get(name) or "/not-set")


def folders(var, pairs, sub=""):
    """Where an app's theme goes: the folders in `var` (";"-separated) if set, otherwise each default
    folder (marker, folder) whose marker exists, meaning the app is installed. `sub` is added; created."""
    """Where an app's theme goes: the folders in `var` (";"-separated), else each default folder
    (marker, folder) whose marker exists, i.e. the app is installed. `sub` is appended; created."""
    custom = env(var)
    dirs = [Path(p.strip().strip("\"'")) for p in custom.split(";") if p.strip()] if custom \
        else [folder for marker, folder in pairs if marker.is_dir()]
    dirs = list(dict.fromkeys(d / sub for d in dirs))
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def defaults(key):
    """An app's default folders as ([(marker, folder), ...], sub), used when its YASB_* variable is not
    set. A folder is used when its marker exists (the app is installed); `sub` is added to each."""
    appdata, local, home = where("APPDATA"), where("LOCALAPPDATA"), where("USERPROFILE")
    if key == "discord":
        return [(appdata / c, appdata / c / "themes") for c in ("BetterDiscord", "Vencord", "Equicord")], ""
    if key == "zed":
        return [(appdata / "Zed", appdata / "Zed" / "themes")], ""
    if key == "obsidian":  # every vault Obsidian knows
        try:
            vaults = [v["path"] for v in json.loads((appdata / "obsidian" / "obsidian.json")
                                                    .read_text(encoding="utf-8"))["vaults"].values()]
        except (OSError, KeyError, ValueError):
            vaults = []
        return [(Path(v) / ".obsidian", Path(v)) for v in vaults], ".obsidian/snippets"
    if key == "vscode":
        return [(home / n, home / n / "extensions") for n in (".vscode", ".vscode-insiders", ".vscode-oss")], \
            "yasb.yasb-accent-1.0.0"
    if key == "nvim":
        return [(local / "nvim", local / "nvim" / "colors")], ""
    if key == "wt":
        fragments = local / "Microsoft" / "Windows Terminal" / "Fragments" / "yasb"
        return [(local / "Packages" / pkg, fragments) for pkg in (
            "Microsoft.WindowsTerminal_8wekyb3d8bbwe", "Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe")] \
            + [(local / "Microsoft" / "Windows Terminal", fragments)], ""
    if key in ("firefox", "zen"):  # every profile
        root = appdata / ("Mozilla/Firefox/Profiles" if key == "firefox" else "zen/Profiles")
        return [(p, p) for p in sorted(root.glob("*")) if p.is_dir()], "chrome"
    if key == "yazi":
        return [(appdata / "yazi", appdata / "yazi" / "config" / "flavors")], "yasb-accent.yazi"
    if key == "obs":
        return [(appdata / "obs-studio", appdata / "obs-studio" / "themes")], ""
    if key == "tacky":
        return [(home / ".config" / "tacky-borders", home / ".config" / "tacky-borders")], ""
    if key == "filepilot":  # FPilot-Config.json; File Pilot creates it, ShellFlow only adds the colour scheme to it
        return [(base / "Voidstar" / "FilePilot", base / "Voidstar" / "FilePilot") for base in (local, appdata)], ""
    if key == "helium":  # the theme is a folder to load once; it is written when one of these browsers is installed
        folder = CONFIG / "helium-theme"
        return [(local / "imput" / "Helium", folder), (local / "Google" / "Chrome", folder), (local / "BraveSoftware", folder),
                (local / "Vivaldi", folder), (local / "Microsoft" / "Edge", folder)], ""
    raise KeyError(key)


def save(dirs, name, text):
    """Write one file into every folder."""
    for d in dirs:
        write_if_changed(d / name, text)


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


# ============================================================================================
#  7. APP THEMES - ONE FUNCTION PER APP
#  Each function says: what it writes, the default location, the variable that changes it,
#  and the one-time step in the app. Colours come from the palette P (accent shades,
#  plus P.t(f) = the accent over black, P.sec/ter/neu(tone) and the terminal colours).
# ============================================================================================


def write_discord(P):
    """Discord (midnight): yasb-colors.theme.css, overriding midnight's colours.
    Default:  %APPDATA%/BetterDiscord, Vencord or Equicord  +  /themes
    Variable: YASB_DISCORD_THEMES
    Then:     enable "yasb-colors" next to "midnight" in the client's theme settings."""
    # backgrounds: the accent over black (35% = the taskbar pills)
    v = {"--bg-1": P.t(.22), "--bg-2": P.t(.35), "--bg-3": P.t(.05), "--bg-4": P.t(.09),
         "--hover": al(P.l1, .12), "--active": al(P.l1, .20), "--active-2": al(P.l1, .30),
         "--button-border": al(P.l3, .12), "--accent-1": P.l3, "--accent-2": P.l2,
         "--accent-3": P.l1, "--accent-4": P.acc, "--accent-5": P.d1}
    body = "\n".join(f"    {k}: {x} !important;" for k, x in v.items())
    controls = f"""
/* window controls, in the accent colours. midnight's own --custom-window-controls setting is left exactly as you have it:
   off = Discord's own buttons (icons tinted below), on = midnight's three dots (coloured by the three variables below) */
[class*="winButtons_"] {{
    --red-2: {P.d1} !important;
    --yellow-2: {P.l1} !important;
    --green-2: {P.l2} !important;
}}
[class*="winButton_"] {{
    color: {P.l1} !important;
}}
[class*="winButton_"]:hover {{
    color: {P.l3} !important;
}}

/* video and clip player: only the seek bar is touched (the accent); the rest of the player is left to Discord and midnight */
[class*="mediaBarProgress_"] {{
    background-color: {P.l1} !important;
}}
[class*="mediaBarGrabber_"] {{
    background-color: {P.l3} !important;
}}
"""
    dirs = folders("YASB_DISCORD_THEMES", *defaults("discord"))
    save(dirs, "yasb-colors.theme.css",
         "/**\n * @name yasb-colors\n * @description Windows accent colour for midnight (written by theme.py)\n"
         " * @author theme.py\n * @version 1.4\n */\n:root {\n" + body + "\n}\n" + controls)


def write_zed(P):
    """Zed: yasb-colors.json, a dark theme called "YASB Accent" (white text, accent-coloured UI).
    Default:  %APPDATA%/Zed/themes
    Variable: YASB_ZED_THEMES
    Then:     pick "YASB Accent" in Zed's theme selector."""
    t, clear, white = P.t, "#00000000", "#ffffff"
    bg, ed = t(.07), t(.05)
    style = {
        "background": bg, "background.appearance": "opaque",
        "surface.background": t(.08), "elevated_surface.background": t(.11),
        "border": t(.32), "border.variant": t(.20), "border.focused": P.acc,
        "border.selected": P.l1, "border.transparent": clear,
        "element.background": t(.22), "element.hover": t(.35), "element.active": t(.45),
        "element.selected": al(P.l1, .24),
        "ghost_element.background": clear, "ghost_element.hover": t(.20),
        "ghost_element.active": t(.30), "ghost_element.selected": al(P.l1, .20),
        "text": white, "text.muted": "#bfbfbf", "text.placeholder": "#8c8c8c",
        "text.disabled": "#6b6b6b", "text.accent": P.l1,
        "icon": white, "icon.muted": "#bfbfbf", "icon.disabled": "#6b6b6b", "icon.accent": P.l1,
        "status_bar.background": t(.12), "title_bar.background": t(.16), "title_bar.inactive_background": t(.10), "toolbar.background": ed,
        "tab_bar.background": t(.10), "tab.inactive_background": t(.10), "tab.active_background": t(.20),
        "panel.background": t(.08), "panel.focused_border": P.acc,
        "search.match_background": al(P.l1, .30),
        "scrollbar.thumb.background": al(P.l1, .25), "scrollbar.thumb.hover_background": al(P.l1, .40),
        "editor.foreground": white, "editor.background": ed, "editor.gutter.background": ed,
        "editor.active_line.background": al(P.l1, .10), "editor.highlighted_line.background": al(P.l1, .14),
        "editor.line_number": "#8c8c8c", "editor.active_line_number": "#e6e6e6",
        "editor.wrap_guide": al(P.l1, .12), "editor.active_wrap_guide": al(P.l1, .25),
        "editor.indent_guide": al(P.l1, .10), "editor.indent_guide_active": al(P.l1, .30),
        "editor.document_highlight.read_background": al(P.l1, .16),
        "terminal.background": ed, "terminal.foreground": white, "link_text.hover": P.l2,
        "players": [{"cursor": P.l1, "background": P.l1, "selection": al(P.l1, .28)}],
    }
    groups = [  # syntax colour -> the syntax keys that use it
        (P.l1, "keyword tag label string.escape variable.special title emphasis emphasis.strong"),
        (P.l2, "type constructor enum variant"),
        ("#e6e6e6", "operator punctuation.list_marker punctuation.special"),
        (white, "variable embedded primary"),
        (P.sec(80), "string link_text text.literal"), (P.sec(70), "property"),
        (P.ter(80), "function attribute string.regex string.special string.special.symbol"),
        (P.ter(70), "number boolean constant link_uri"),
        (P.neu(70), "punctuation punctuation.bracket punctuation.delimiter preproc"), (P.neu(60), "hint"),
    ]
    syntax = {k: {"color": colour} for colour, keys in groups for k in keys.split()}
    for k in ("comment", "comment.doc", "predictive"):
        syntax[k] = {"color": P.neu(55), "font_style": "italic"}
    syntax["emphasis"]["font_style"] = "italic"
    syntax["title"]["font_weight"] = syntax["emphasis.strong"]["font_weight"] = 700
    style["syntax"] = syntax
    save(folders("YASB_ZED_THEMES", *defaults("zed")), "yasb-colors.json",
         json.dumps({"$schema": "https://zed.dev/schema/themes/v0.2.0.json", "name": "YASB Accent",
                     "author": "theme.py", "themes": [{"name": "YASB Accent", "appearance": "dark",
                                                       "style": style}]}, indent=2))


def write_obsidian(P):
    """Obsidian: yasb-colors.css, a CSS snippet (works on top of any theme). The text you read and write is white; headings,
    bold, links, tags, list markers, quotes and the title bar carry the accent.
    Default:  every vault in %APPDATA%/obsidian/obsidian.json  +  /.obsidian/snippets
    Variable: YASB_OBSIDIAN_VAULTS (the vault folders themselves)
    Then:     Settings > Appearance > CSS snippets > turn on yasb-colors."""
    variables = {
        "--background-primary": P.t(.05), "--background-primary-alt": P.t(.07),
        "--background-secondary": P.t(.07), "--background-secondary-alt": P.t(.09),
        "--background-modifier-border": P.t(.20), "--background-modifier-hover": al(P.l1, .10),
        "--background-modifier-active-hover": al(P.l1, .16), "--background-modifier-form-field": P.t(.12),
        "--text-normal": "#ffffff", "--text-muted": "#bfbfbf", "--text-faint": "#8c8c8c",  # the text itself: white, like Zed
        "--text-accent": P.l1, "--text-accent-hover": P.l2, "--text-selection": al(P.l1, .28),
        "--text-highlight-bg": al(P.l1, .30),
        # titles and a few elements: the accent
        "--h1-color": P.l2, "--h2-color": P.l1, "--h3-color": P.l1, "--h4-color": P.l1, "--h5-color": P.l1, "--h6-color": P.l1,
        "--inline-title-color": P.l2, "--bold-color": P.l2, "--italic-color": "#ffffff",
        "--link-color": P.l1, "--link-color-hover": P.l2, "--link-external-color": P.l1, "--link-unresolved-color": P.d1,
        "--tag-color": P.l1, "--tag-background": al(P.l1, .14), "--tag-background-hover": al(P.l1, .24),
        "--list-marker-color": P.l1, "--blockquote-border-color": P.acc, "--hr-color": P.d1,
        "--code-normal": P.l3, "--code-background": P.t(.12),
        "--checkbox-color": P.acc, "--nav-item-color-active": P.l2, "--nav-item-background-active": al(P.l1, .16),
        "--tab-text-color-focused-active": P.l2, "--tab-text-color-focused-active-current": P.l2,
        "--titlebar-background": P.t(.12), "--titlebar-background-focused": P.t(.16),
        "--titlebar-text-color": P.l1, "--titlebar-text-color-focused": P.l2, "--titlebar-text-color-highlighted": P.l3,
        "--interactive-normal": P.t(.22), "--interactive-hover": P.t(.35),
        "--interactive-accent": P.acc, "--interactive-accent-hover": P.l1,
        "--color-accent": P.acc, "--color-accent-1": P.l1, "--color-accent-2": P.l2,
    }
    body = "\n".join(f"    {k}: {v} !important;" for k, v in variables.items())
    css = f"body.theme-dark,\n.theme-dark {{\n{body}\n}}\n"
    save(folders("YASB_OBSIDIAN_VAULTS", *defaults("obsidian")), "yasb-colors.css", css)


def write_vscode(P):
    """VS Code: a small theme extension, "YASB Accent" (colours + syntax).
    Default:  %USERPROFILE%/.vscode, .vscode-insiders or .vscode-oss  +  /extensions
    Variable: YASB_VSCODE_EXTENSIONS
    Then:     restart VS Code and pick "YASB Accent" (Reload Window after later changes)."""
    colours = {
        "foreground": P.l3, "descriptionForeground": P.t(.8), "focusBorder": P.acc,
        "editor.background": P.t(.05), "editor.foreground": P.l3,
        "editor.lineHighlightBackground": al(P.l1, .10), "editor.selectionBackground": al(P.l1, .28),
        "editorCursor.foreground": P.l1, "editorLineNumber.foreground": P.t(.75),
        "editorLineNumber.activeForeground": P.l2, "editorWhitespace.foreground": P.t(.30),
        "editorIndentGuide.background1": al(P.l1, .10), "editorIndentGuide.activeBackground1": al(P.l1, .30),
        "editorWidget.background": P.t(.11), "editorSuggestWidget.background": P.t(.11),
        "editorSuggestWidget.selectedBackground": P.t(.35),
        "activityBar.background": P.t(.07), "activityBar.foreground": P.l1,
        "activityBar.inactiveForeground": P.t(.75), "activityBarBadge.background": P.acc,
        "activityBarBadge.foreground": P.t(.05),
        "sideBar.background": P.t(.08), "sideBar.foreground": P.l3, "sideBarTitle.foreground": P.l2,
        "sideBarSectionHeader.background": P.t(.07),
        "titleBar.activeBackground": P.t(.07), "titleBar.activeForeground": P.l3,
        "titleBar.inactiveBackground": P.t(.06),
        "statusBar.background": P.t(.07), "statusBar.foreground": P.l2,
        "statusBar.noFolderBackground": P.t(.07),
        "tab.activeBackground": P.t(.05), "tab.inactiveBackground": P.t(.07),
        "tab.activeForeground": P.l3, "tab.inactiveForeground": P.t(.8),
        "tab.activeBorderTop": P.acc, "editorGroupHeader.tabsBackground": P.t(.07),
        "panel.background": P.t(.05), "panel.border": P.t(.20), "panelTitle.activeForeground": P.l2,
        "terminal.background": P.t(.05), "terminal.foreground": P.l3,
        "button.background": P.t(.35), "button.foreground": P.l3, "button.hoverBackground": P.t(.45),
        "input.background": P.t(.12), "input.foreground": P.l3, "input.border": P.t(.20),
        "dropdown.background": P.t(.12), "badge.background": P.acc, "badge.foreground": P.t(.05),
        "list.activeSelectionBackground": P.t(.35), "list.activeSelectionForeground": P.l3,
        "list.inactiveSelectionBackground": P.t(.22), "list.hoverBackground": P.t(.20),
        "menu.background": P.t(.11), "menu.selectionBackground": P.t(.35),
        "progressBar.background": P.acc, "textLink.foreground": P.l1,
        "scrollbarSlider.background": al(P.l1, .20), "scrollbarSlider.hoverBackground": al(P.l1, .35),
    }
    for i, name in enumerate(("Red", "Green", "Yellow", "Blue", "Magenta", "Cyan")):
        colours[f"terminal.ansi{name}"], colours[f"terminal.ansiBright{name}"] = P.ansi[i], P.bright[i]
    tokens = [(P.neu(55), "italic", "comment"), (P.sec(80), "", "string"),
              (P.ter(70), "", "constant.numeric constant.language constant.character"),
              (P.l1, "", "keyword storage storage.type"), (P.ter(80), "", "entity.name.function support.function"),
              (P.l2, "", "entity.name.type entity.name.class support.type support.class"),
              (P.l3, "", "variable"), (P.sec(70), "", "variable.other.property meta.object-literal.key"),
              (P.l2, "", "keyword.operator"), (P.neu(70), "", "punctuation"),
              (P.l1, "", "entity.name.tag"), (P.ter(80), "", "entity.other.attribute-name")]
    theme = {"name": "YASB Accent", "type": "dark", "colors": colours,
             "tokenColors": [{"scope": s.split(), "settings": {"foreground": c, **({"fontStyle": f} if f else {})}}
                             for c, f, s in tokens]}
    package = {"name": "yasb-accent", "displayName": "YASB Accent", "publisher": "yasb", "version": "1.0.0",
               "engines": {"vscode": "^1.60.0"}, "categories": ["Themes"],
               "contributes": {"themes": [{"label": "YASB Accent", "uiTheme": "vs-dark",
                                           "path": "./themes/yasb-accent-color-theme.json"}]}}
    for d in folders("YASB_VSCODE_EXTENSIONS", *defaults("vscode")):
        (d / "themes").mkdir(exist_ok=True)
        write_if_changed(d / "package.json", json.dumps(package, indent=2))
        write_if_changed(d / "themes" / "yasb-accent-color-theme.json", json.dumps(theme, indent=2))


def write_nvim(P):
    """Neovim: yasb.lua, a colour scheme.
    Default:  %LOCALAPPDATA%/nvim/colors
    Variable: YASB_NVIM_COLORS
    Then:     :colorscheme yasb  (put it in init.lua to keep it)."""
    bg, float_bg, sel = P.t(.05), P.t(.11), P.t(.35)
    groups = {
        "Normal": dict(fg=P.l3, bg=bg), "NormalFloat": dict(fg=P.l3, bg=float_bg),
        "FloatBorder": dict(fg=P.t(.5), bg=float_bg), "CursorLine": dict(bg=P.t(.10)),
        "CursorLineNr": dict(fg=P.l1, bold=True), "LineNr": dict(fg=P.t(.75)),
        "SignColumn": dict(bg=bg), "ColorColumn": dict(bg=P.t(.08)), "Visual": dict(bg=sel),
        "Search": dict(fg=bg, bg=P.l2), "IncSearch": dict(fg=bg, bg=P.l1), "CurSearch": dict(fg=bg, bg=P.l1),
        "MatchParen": dict(fg=P.l1, bold=True, underline=True), "Pmenu": dict(fg=P.l3, bg=float_bg),
        "PmenuSel": dict(fg=P.l3, bg=sel), "PmenuSbar": dict(bg=P.t(.22)), "PmenuThumb": dict(bg=P.t(.5)),
        "StatusLine": dict(fg=P.l2, bg=P.t(.12)), "StatusLineNC": dict(fg=P.t(.75), bg=P.t(.08)),
        "WinSeparator": dict(fg=P.t(.22)), "VertSplit": dict(fg=P.t(.22)),
        "TabLine": dict(fg=P.t(.8), bg=P.t(.08)), "TabLineSel": dict(fg=P.l3, bg=sel, bold=True),
        "TabLineFill": dict(bg=P.t(.07)), "Folded": dict(fg=P.t(.8), bg=P.t(.08)),
        "NonText": dict(fg=P.t(.4)), "SpecialKey": dict(fg=P.t(.4)), "Whitespace": dict(fg=P.t(.3)),
        "Directory": dict(fg=P.l1), "Title": dict(fg=P.l1, bold=True), "Question": dict(fg=P.ter(80)),
        "ErrorMsg": dict(fg=P.ansi[0]), "WarningMsg": dict(fg=P.ansi[2]), "MoreMsg": dict(fg=P.ansi[1]),
        "Comment": dict(fg=P.neu(55), italic=True), "Constant": dict(fg=P.ter(70)),
        "String": dict(fg=P.sec(80)), "Character": dict(fg=P.sec(80)), "Number": dict(fg=P.ter(70)),
        "Boolean": dict(fg=P.ter(70)), "Identifier": dict(fg=P.l3), "Function": dict(fg=P.ter(80)),
        "Statement": dict(fg=P.l1), "Keyword": dict(fg=P.l1), "Operator": dict(fg=P.l2),
        "PreProc": dict(fg=P.neu(70)), "Type": dict(fg=P.l2), "Special": dict(fg=P.ter(80)),
        "Delimiter": dict(fg=P.neu(70)), "Underlined": dict(fg=P.l1, underline=True),
        "Error": dict(fg=P.ansi[0]), "Todo": dict(fg=bg, bg=P.l1, bold=True),
        "DiffAdd": dict(bg=shade(P.ansi[1], .30)), "DiffChange": dict(bg=shade(P.ansi[3], .25)),
        "DiffDelete": dict(bg=shade(P.ansi[0], .30)), "DiffText": dict(bg=shade(P.ansi[3], .45)),
        "DiagnosticError": dict(fg=P.ansi[0]), "DiagnosticWarn": dict(fg=P.ansi[2]),
        "DiagnosticInfo": dict(fg=P.ansi[3]), "DiagnosticHint": dict(fg=P.ansi[5]),
    }
    lua = ['vim.cmd("highlight clear")', 'if vim.g.syntax_on then vim.cmd("syntax reset") end',
           'vim.o.background = "dark"', 'vim.g.colors_name = "yasb"']
    for name, style in groups.items():
        lua.append(f'vim.api.nvim_set_hl(0, "{name}", {{ ' +
                   ", ".join(f"{k} = {json.dumps(v)}" for k, v in style.items()) + " })")
    save(folders("YASB_NVIM_COLORS", *defaults("nvim")), "yasb.lua", "\n".join(lua) + "\n")


def write_wt(P):
    """Windows Terminal: a JSON fragment with the colour scheme "YASB Accent".
    Default:  %LOCALAPPDATA%/Microsoft/Windows Terminal/Fragments/yasb  (Store, Preview or unpackaged)
    Variable: YASB_WT_FRAGMENTS
    Then:     pick "YASB Accent" under a profile's Appearance settings."""
    names = ("red", "green", "yellow", "blue", "purple", "cyan")
    scheme_ = {"name": "YASB Accent", "background": P.t(.05), "foreground": P.l3, "cursorColor": P.l1,
               "selectionBackground": P.t(.35), "black": P.t(.12), "white": P.neu(80),
               "brightBlack": P.neu(40), "brightWhite": P.neu(95)}
    for i, n in enumerate(names):
        scheme_[n], scheme_["bright" + n.capitalize()] = P.ansi[i], P.bright[i]
    save(folders("YASB_WT_FRAGMENTS", *defaults("wt")), "yasb-accent.json",
         json.dumps({"schemes": [scheme_]}, indent=2))


def write_browser(P, var, key):
    """Firefox and Zen: yasb-chrome.css (browser UI) and yasb-content.css (about: pages) in each
    profile's chrome folder. userChrome.css / userContent.css are created only if missing; if you
    already have them, add  @import url("yasb-chrome.css");  and  @import url("yasb-content.css");"""
    """Firefox and Zen: yasb-chrome.css (browser UI) and yasb-content.css (about: pages) in each
    profile's chrome folder. userChrome.css / userContent.css are created only if missing."""
    chrome = ":root {\n" + "\n".join(f"    {k}: {v} !important;" for k, v in {
        "--lwt-accent-color": P.t(.07), "--lwt-text-color": P.l3, "--toolbar-bgcolor": P.t(.08),
        "--toolbar-color": P.l3, "--toolbar-field-background-color": P.t(.12),
        "--toolbar-field-color": P.l3, "--toolbar-field-focus-background-color": P.t(.22),
        "--tab-selected-bgcolor": P.t(.35), "--tab-selected-textcolor": P.l3,
        "--arrowpanel-background": P.t(.11), "--arrowpanel-color": P.l3,
        "--arrowpanel-border-color": P.t(.32), "--sidebar-background-color": P.t(.07),
        "--sidebar-text-color": P.l3, "--urlbar-box-bgcolor": P.t(.12),
        "--urlbar-box-hover-bgcolor": P.t(.22), "--zen-primary-color": P.acc,
        "--zen-colors-primary": P.t(.35), "--zen-colors-primary-foreground": P.l3,
        "--zen-colors-secondary": P.t(.12), "--zen-colors-tertiary": P.t(.07),
        "--zen-colors-border": P.t(.32), "--zen-main-browser-background": P.t(.07),
    }.items()) + "\n}\n"
    content = '@-moz-document url-prefix("about:") {\n:root {\n' + "\n".join(f"    {k}: {v} !important;" for k, v in {
        "--in-content-page-background": P.t(.05), "--in-content-page-color": P.l3,
        "--in-content-box-background": P.t(.08), "--in-content-box-border-color": P.t(.32),
        "--in-content-accent-color": P.l1, "--in-content-primary-button-background": P.t(.45),
        "--newtab-background-color": P.t(.05), "--newtab-background-color-secondary": P.t(.08),
        "--newtab-text-primary-color": P.l3,
    }.items()) + "\n}\n}\n"
    for d in folders(var, *defaults(key)):
        write_if_changed(d / "yasb-chrome.css", chrome)
        write_if_changed(d / "yasb-content.css", content)
        for user, ours in (("userChrome.css", "yasb-chrome.css"), ("userContent.css", "yasb-content.css")):
            if not (d / user).exists():
                (d / user).write_text(f'@import url("{ours}");\n', encoding="utf-8")


def write_firefox(P):
    """Firefox.
    Default:  every profile in %APPDATA%/Mozilla/Firefox/Profiles  +  /chrome
    Variable: YASB_FIREFOX_PROFILES (the profile folders)
    Then:     in about:config set toolkit.legacyUserProfileCustomizations.stylesheets to true."""
    write_browser(P, "YASB_FIREFOX_PROFILES", "firefox")


def write_zen(P):
    """Zen Browser.
    Default:  every profile in %APPDATA%/zen/Profiles  +  /chrome
    Variable: YASB_ZEN_PROFILES (the profile folders)
    Then:     restart Zen."""
    write_browser(P, "YASB_ZEN_PROFILES", "zen")


# one icon per kind of file, all white. Font Awesome and Devicons glyphs, which every Nerd Font has.
YAZI_ICON_EXTS = {
    "md": "\ue73e", "markdown": "\ue73e", "json": "\ue60b", "js": "\ue74e", "mjs": "\ue74e", "ts": "\ue628", "tsx": "\ue7ba", "jsx": "\ue7ba",
    "py": "\ue73c", "rs": "\ue7a8", "go": "\ue627", "c": "\ue61e", "cpp": "\ue61d", "cs": "\uf81a", "java": "\ue738", "lua": "\ue620",
    "html": "\ue736", "css": "\ue749", "scss": "\ue749", "sh": "\uf489", "bash": "\uf489", "ps1": "\uf489", "bat": "\uf489", "cmd": "\uf489",
    "toml": "\ue615", "yaml": "\ue615", "yml": "\ue615", "ini": "\ue615", "conf": "\ue615", "cfg": "\ue615", "env": "\ue615",
    "txt": "\uf0f6", "log": "\uf0f6", "pdf": "\uf1c1", "doc": "\uf1c2", "docx": "\uf1c2", "xls": "\uf1c3", "xlsx": "\uf1c3", "csv": "\uf1c3",
    "ppt": "\uf1c4", "pptx": "\uf1c4", "zip": "\uf1c6", "7z": "\uf1c6", "rar": "\uf1c6", "tar": "\uf1c6", "gz": "\uf1c6",
    "png": "\uf1c5", "jpg": "\uf1c5", "jpeg": "\uf1c5", "gif": "\uf1c5", "webp": "\uf1c5", "bmp": "\uf1c5", "svg": "\uf1c5", "ico": "\uf1c5",
    "mp3": "\uf1c7", "wav": "\uf1c7", "flac": "\uf1c7", "ogg": "\uf1c7", "m4a": "\uf1c7",
    "mp4": "\uf1c8", "mkv": "\uf1c8", "avi": "\uf1c8", "mov": "\uf1c8", "webm": "\uf1c8",
    "exe": "\uf17a", "msi": "\uf17a", "dll": "\uf17a", "lnk": "\uf0c1", "iso": "\uf0a0",
}


def yazi_icons(colour="#ffffff"):
    """The [icon] section of the flavor: dirs, files and exts replace Yazi's own lists, so every icon is `colour`."""
    row = lambda name, glyph: f'    {{ name = "{name}", text = "{glyph}", fg = "{colour}" }},'
    cond = lambda test, glyph: f'    {{ if = "{test}", text = "{glyph}", fg = "{colour}" }},'
    lines = ["[icon]", "globs = []", "dirs = [", row(".git", "\ue5fb"), row(".config", "\ue5fc"), row("node_modules", "\ue5fa"), "]",
             "files = [", row(".gitignore", "\ue702"), row(".gitconfig", "\ue702"), row("Dockerfile", "\ue7b0"), row("LICENSE", "\uf0f6"), "]",
             "exts = [", *[row(ext, glyph) for ext, glyph in YAZI_ICON_EXTS.items()], "]",
             "conds = [", cond("orphan", "\uf127"), cond("link", "\uf0c1"), cond("hidden & dir", "\uf07b"), cond("dir", "\uf07b"),
             cond("exec", "\uf085"), cond("!(dir | link)", "\uf15b"), "]"]
    return "\n".join(lines)


def write_yazi(P):
    """Yazi: the flavor "yasb-accent" (flavor.toml). A theme.toml selecting it is created only if missing.
    Default:  %APPDATA%/yazi/config/flavors  +  /yasb-accent.yazi
    Variable: YASB_YAZI_FLAVORS
    Then:     if you have your own theme.toml, set  [flavor] dark = "yasb-accent"  in it."""
    q = lambda c: f'"{c}"'
    ed = P.t(.05)
    toml = f"""[mgr]
cwd = {{ fg = {q(P.l1)} }}
hovered = {{ fg = {q(ed)}, bg = {q(P.l1)} }}
preview_hovered = {{ underline = true }}
find_keyword = {{ fg = {q(P.ter(80))}, bold = true, italic = true, underline = true }}
find_position = {{ fg = {q(P.ter(80))}, bold = true, italic = true }}
symlink_target = {{ italic = true }}
marker_copied = {{ fg = {q(ed)}, bg = {q(P.ansi[1])} }}
marker_cut = {{ fg = {q(ed)}, bg = {q(P.ansi[0])} }}
marker_marked = {{ fg = {q(ed)}, bg = {q(P.sec(80))} }}
marker_selected = {{ fg = {q(ed)}, bg = {q(P.l1)} }}
count_copied = {{ fg = {q(ed)}, bg = {q(P.ansi[1])} }}
count_cut = {{ fg = {q(ed)}, bg = {q(P.ansi[0])} }}
count_selected = {{ fg = {q(ed)}, bg = {q(P.l1)} }}

[filetype]
prepend_rules = [
    {{ url = "*/", fg = "#ffffff" }},
]

{yazi_icons()}

[tabs]
active = {{ fg = {q(ed)}, bg = {q(P.l1)}, bold = true }}
inactive = {{ fg = {q(P.l1)}, bg = {q(P.t(.12))} }}

[mode]
normal_main = {{ fg = {q(ed)}, bg = {q(P.l1)}, bold = true }}
normal_alt = {{ fg = {q(P.l1)}, bg = {q(P.t(.22))} }}
select_main = {{ fg = {q(ed)}, bg = {q(P.ter(80))}, bold = true }}
select_alt = {{ fg = {q(P.ter(80))}, bg = {q(P.t(.22))} }}
unset_main = {{ fg = {q(ed)}, bg = {q(P.ansi[0])}, bold = true }}
unset_alt = {{ fg = {q(P.ansi[0])}, bg = {q(P.t(.22))} }}
"""
    dirs = folders("YASB_YAZI_FLAVORS", *defaults("yazi"))
    save(dirs, "flavor.toml", toml)
    for d in dirs:  # select the flavor, unless there already is a theme.toml
        theme = d.parent.parent / "theme.toml"
        if not theme.exists():
            theme.write_text('[flavor]\ndark = "yasb-accent"\nlight = "yasb-accent"\n', encoding="utf-8")


FILEPILOT_NAME = "YASB Accent"


def filepilot_scheme(P):
    """The colour scheme for File Pilot, like the Zed theme: black background, white text, the accent for icons, headings, the
    selection and matches. File Pilot writes colours as rrggbb, without the #."""
    mix = lambda a, b, t: _mix(a, b, t)
    colours = {
        "Clear": "#000000", "Caption": "#000000", "Background": P.t(.05), "Surface": P.t(.04), "Foreground": P.t(.10), "Inner": "#000000",
        "Border": P.t(.14), "Outline": P.t(.20), "Separator": P.t(.12), "AlternatingRow": P.t(.07), "IconTint": P.l1,
        "Text": "#ffffff", "Secondary": P.neu(70), "Group": P.l2, "File": "#e6e6e6", "Folder": "#ffffff",
        "Warning": P.l1, "Progress": P.l1, "Selection": mix(P.t(.10), P.l1, .30), "RectSelection": P.l1, "Match": P.d1,
        "Hidden": P.t(.30), "Hover": P.t(.14), "Disabled": P.t(.12),
        "ContentHover": "#ffffff", "ContentSelection": "#ffffff", "ContentDisabledSelection": "#e6e6e6",
        "OutlineHover": P.l2, "OutlineSelection": P.l1, "OutlineDisabledSelection": P.d1,
        "MatchHover": P.l2, "MatchSelection": P.l1, "MatchDisabledSelection": P.d1,
    }
    return {k: v.lstrip("#").upper() for k, v in colours.items()}


def filepilot_update(text, scheme):
    """FPilot-Config.json with the "YASB Accent" scheme in its "Colors" list. That file is not strict JSON (the list holds named
    objects), so it is edited as text: an existing "YASB Accent" is replaced where it stands, otherwise it is added at the top of the
    list. Returns (new text, whether the scheme was new)."""
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r'"Colors"\s*:\s*\[', text)
    if not m:
        raise ValueError('FPilot-Config.json has no "Colors" list yet: in File Pilot open Settings (Ctrl+,), hover a colour scheme and press its fork icon, then try again')
    block = nl.join(['\t\t"%s":' % FILEPILOT_NAME, "\t\t{"] + ['\t\t\t"%s": "%s"%s' % (k, v, "," if i < len(scheme) - 1 else "")
                                                         for i, (k, v) in enumerate(scheme.items())] + ["\t\t}"])
    old = re.search(r'[ \t]*"%s"\s*:\s*\{' % re.escape(FILEPILOT_NAME), text[m.end():])
    if old:
        start = m.end() + old.start()
        depth, i = 0, m.end() + old.end() - 1
        while i < len(text):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                break
            i += 1
        return text[:start] + block + text[i + 1:], False
    rest = text[m.end():]
    empty = rest.lstrip().startswith("]")
    return text[:m.end()] + nl + block + ("" if empty else ",") + rest, True


def filepilot_running():
    """Is File Pilot open? (It keeps its colour schemes in memory and writes FPilot-Config.json again when it closes, which wipes an edit
    made while it was open: that is why the old colours came back.)"""
    exe = env("YASB_FILEPILOT_EXE") or "FilePilot.exe"
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW if os.name == "nt" else 0).stdout
        return exe.lower() in out.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def restart_filepilot():
    """Close File Pilot (it saves its config), write the colour scheme, open it again. Returns what happened."""
    exe = env("YASB_FILEPILOT_EXE") or "FilePilot.exe"
    name = exe[:-4] if exe.lower().endswith(".exe") else exe
    flags = NO_WINDOW if os.name == "nt" else 0

    def run(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=15, creationflags=flags).stdout or ""
        except (OSError, subprocess.SubprocessError):
            return ""
    path = run(["powershell", "-NoProfile", "-Command", f"(Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Select-Object -First 1).Path"]).strip()
    if path:
        run(["taskkill", "/IM", exe])  # no /F: it is asked to close, and writes its config
        for _ in range(50):
            if exe.lower() not in run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"]).lower():
                break
            time.sleep(.2)
        else:
            return "File Pilot did not close: close it yourself, then press Apply now"
    write_filepilot(palette())
    if not path:
        return "File Pilot was not open: the colours are written"
    try:
        subprocess.Popen([path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=(flags | 0x00000008) if os.name == "nt" else 0)
    except OSError:
        return "File Pilot closed but could not be started again: open it yourself"
    return "File Pilot restarted with the new colours"


def write_filepilot(P):
    """File Pilot: the colour scheme "YASB Accent" in FPilot-Config.json (the first time it also becomes the selected scheme).
    Default:  %LOCALAPPDATA%/Voidstar/FilePilot (or %APPDATA%/Voidstar/FilePilot)   Variable: YASB_FILEPILOT_CONFIG
    Needs a "Colors" list in the file: fork any scheme in File Pilot's settings once to make it."""
    for d in folders("YASB_FILEPILOT_CONFIG", *defaults("filepilot")):
        path = d / "FPilot-Config.json"
        if not path.is_file():
            continue
        if filepilot_running():  # an edit now would be overwritten when it closes
            raise RuntimeError("File Pilot is open and would overwrite the colours when it closes: press Restart File Pilot (Templates) or close it first")
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        new, created = filepilot_update(text, filepilot_scheme(P))
        if created:  # the first time: use it (afterwards the scheme you pick stays yours)
            new = re.sub(r'("ColorScheme"\s*:\s*)"[^"]*"', r'\1"%s"' % FILEPILOT_NAME, new, count=1)
            new = re.sub(r'("SystemColorScheme"\s*:\s*)true', r'\1false', new, count=1)
        if new != text:
            path.write_bytes((b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + new.encode("utf-8"))


HELIUM_CACHE = "Cached Theme.pak"


def clear_helium_cache():
    """Chromium keeps a built copy of an unpacked theme in the theme folder ("Cached Theme.pak") and keeps using it: it only builds it
    again when the file is missing. Deleting it makes the browser read manifest.json again the next time it starts. A running browser
    holds the file open, so that case is left (it is cleared when Helium is restarted). Returns how many were deleted."""
    gone = 0
    for d in folders("YASB_HELIUM_THEME", *defaults("helium")):
        try:
            (d / HELIUM_CACHE).unlink()
            gone += 1
        except FileNotFoundError:
            pass
        except OSError:
            pass  # in use
    return gone


def helium_theme_dir():
    """The folder that holds the written theme (manifest.json), or None."""
    for d in folders("YASB_HELIUM_THEME", *defaults("helium")):
        if (d / "manifest.json").is_file():
            return d
    return None


def restart_helium():
    """Close Helium the polite way (so it saves its tabs) and open it again with the last session, so it reads the theme that was written.
    Helium is found by its window and its folder (the program is not always called helium.exe); only that one process is closed, by its id,
    so another Chromium browser is left alone. YASB_HELIUM_EXE names the program if that does not find it. Returns what happened."""
    flags = NO_WINDOW if os.name == "nt" else 0

    def run(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=20, creationflags=flags).stdout or ""
        except (OSError, subprocess.SubprocessError):
            return ""
    exe = (env("YASB_HELIUM_EXE") or "").strip()
    name = exe[:-4] if exe.lower().endswith(".exe") else exe
    pick = f"$_.ProcessName -eq '{name}'" if name else "$_.Path -like '*\\Helium\\*' -or $_.ProcessName -like '*helium*'"
    found = run(["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and (" + pick + ") } | Select-Object -First 1 | "
                 "ForEach-Object { '{0}|{1}' -f $_.Id, $_.Path }"]).strip()
    if "|" not in found:
        clear_helium_cache()
        return "Helium is not open (no window found): it will read the new theme when it starts"
    pid, path = found.split("|", 1)
    run(["taskkill", "/PID", pid])  # no /F: Helium is asked to close, and saves its session
    for _ in range(60):
        if pid not in run(["tasklist", "/FI", f"PID eq {pid}", "/NH"]):
            break
        time.sleep(.2)
    else:
        return "Helium did not close (is something unsaved?): close it yourself and open it again"
    time.sleep(1.0)  # its other processes finish
    clear_helium_cache()  # closed now: its cached copy of the theme can go, so it builds the theme from manifest.json as it starts
    try:
        subprocess.Popen([path, "--restore-last-session"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, creationflags=(flags | 0x00000008) if os.name == "nt" else 0)
    except OSError:
        return "Helium closed but could not be started again: open it yourself"
    return "Helium restarted with your tabs"


def write_helium(P):
    """Helium (and Chrome, Brave, Vivaldi, Edge): a theme extension "YASB Accent": manifest.json in a folder. The active tab and the
    toolbar are black, the accent is in the address bar and icons (YASB_HELIUM_TAB=accent: an accent toolbar and active tab; =#rrggbb: that colour;
    =dark: a near-black toolbar and a grey address bar).
    Default:  <config folder>/helium-theme, written when one of those browsers is installed
    Variable: YASB_HELIUM_THEME
    Once:     helium://extensions > Developer mode > Load unpacked > pick the folder. After that the colours follow your scheme, but
              Helium reads a changed theme only when it starts (its reload arrow is not reliable): ShellFlow > Templates > Helium >
              "Restart Helium" closes it and opens it again with your tabs."""
    c = lambda h: [int(h[i:i + 2], 16) for i in (1, 3, 5)]
    colours = {
        # the backgrounds are black, not tinted: the tab strip, the new-tab page. The accent is for the active tab and what sits on it.
        "frame": "#000000", "frame_inactive": "#000000", "frame_incognito": "#000000", "frame_incognito_inactive": "#000000",
        "toolbar": "#0d0d0d", "tab_text": "#ffffff", "tab_background_text": P.neu(70), "bookmark_text": P.l2,
        "toolbar_button_icon": P.l1, "omnibox_background": "#1a1a1a", "omnibox_text": "#ffffff", "button_background": "#0d0d0d",
        "ntp_background": "#000000", "ntp_text": "#ffffff", "ntp_link": P.l1, "ntp_section": "#0d0d0d", "ntp_header": "#000000",
    }
    mode = env("YASB_HELIUM_TAB")
    hexa = mode.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", mode or "") else ""
    if mode == "accent" or hexa:
        # Chromium draws the active tab in the toolbar's colour, so the toolbar is the active-tab colour: the capsule colour darkened 30%
        # (what a populated workspace is on the bar), with white text, and the address bar a darker pill inside it. YASB_HELIUM_TAB=#rrggbb
        # sets that colour exactly.
        tab = hexa or _mix(P.l1, "#000000", .30)
        pill = _mix(tab, "#000000", .35)
        colours.update({"toolbar": tab, "tab_text": "#ffffff", "bookmark_text": P.l3, "toolbar_button_icon": P.l3,
                        "omnibox_background": pill, "omnibox_text": "#ffffff", "button_background": pill})
    elif mode != "dark":
        # the default: black. Helium draws the tab strip and the toolbar as one surface in the toolbar's colour (the frame colour only
        # shows at the edges), so an accent toolbar made the whole top of the window accent-coloured. Black it is; the accent is in the
        # icons, the bookmarks and the links.
        colours.update({"toolbar": "#000000", "tab_text": "#ffffff", "bookmark_text": P.l2, "toolbar_button_icon": P.l1,
                        "omnibox_background": "#000000", "omnibox_text": "#ffffff", "button_background": "#0d0d0d"})
    version = "1.%d.0" % (zlib.crc32(json.dumps(colours, sort_keys=True).encode()) & 0xFFFF)  # changes only when a colour does
    manifest = {"manifest_version": 3, "name": "YASB Accent", "version": version,
                "description": "Colours from your ShellFlow / YASB colour scheme (written by theme.py)",
                "theme": {"colors": {k: c(v) for k, v in colours.items()}, "tints": {"buttons": [-1, -1, -1]}}}
    dirs = folders("YASB_HELIUM_THEME", *defaults("helium"))
    before = [(d / "manifest.json").read_text(encoding="utf-8") if (d / "manifest.json").is_file() else "" for d in dirs]
    save(dirs, "manifest.json", json.dumps(manifest, indent=2))
    changed = any(b and b != json.dumps(manifest, indent=2) for b in before)  # an installed theme whose colours just changed
    if changed:
        clear_helium_cache()  # so the browser builds the theme again from the new manifest (a running one keeps its copy until restarted)
    if changed and env("YASB_HELIUM_AUTORESTART") == "1":  # opt in: Helium reads a changed theme only when it starts
        import threading
        threading.Thread(target=lambda: watch_log("helium: " + restart_helium())).start()
    save(dirs, "README.txt", "YASB Accent: a Chromium theme written by ShellFlow (theme.py).\n\nLoad it once:\n"
         "  1. Open helium://extensions (chrome://extensions in other browsers)\n  2. Turn on Developer mode\n"
         "  3. Load unpacked, and pick this folder\n\nWhen your scheme changes, ShellFlow rewrites manifest.json. Helium reads a changed theme\n"
         "when it starts: restart it (ShellFlow > Templates > Helium > Restart Helium). ShellFlow deletes the 'Cached Theme.pak' file in\n"
         "this folder first: the browser keeps a built copy of the theme there and only reads manifest.json again when it is gone.\n"
         "If a restart still shows the old colours, remove the theme and Load unpacked again.\n")


def write_tacky(P):
    """Tacky Borders: sets global.active_color in config.yaml to the main accent colour.
    Default:  %USERPROFILE%/.config/tacky-borders  (config.yaml must exist; it is never created)
    Variable: YASB_TACKY_CONFIG
    Then:     nothing - Tacky Borders reloads its config by itself."""
    done = False
    for d in folders("YASB_TACKY_CONFIG", *defaults("tacky")):
        cfg = d / "config.yaml"
        if not cfg.exists():
            continue
        lines = cfg.read_text(encoding="utf-8").split("\n")
        g = next((i for i, l in enumerate(lines) if re.match(r"^global:\s*(#.*)?$", l)), None)
        if g is None:
            raise ValueError("no global: section in " + str(cfg))
        end = next((j for j in range(g + 1, len(lines)) if lines[j].strip() and not lines[j].startswith((" ", "\t", "#"))), len(lines))
        for i in range(g + 1, end):
            m = re.match(r"^(\s+active_color:\s*)(.*?)(\s+#.*)?$", lines[i])
            if m:
                if not m.group(2) or m.group(2).startswith(("{", "[", "|", ">")):
                    raise ValueError("active_color is a gradient/mapping, not a single colour: left alone")
                lines[i] = f'{m.group(1)}"{P.acc}"{m.group(3) or ""}'
                write_if_changed(cfg, "\n".join(lines))
                done = True
                break
        else:
            raise ValueError("no active_color under global: in " + str(cfg))
    return done


def find_yami():
    """OBS's own Yami theme: the base this variant extends. Looks where OBS is usually installed (and YASB_OBS_INSTALL)."""
    install = env("YASB_OBS_INSTALL")
    roots = [Path(install)] if install else []
    for var in ("PROGRAMFILES", "PROGRAMW6432", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = Path(os.environ.get(var) or "/not-set")
        roots += [base / "obs-studio", base / "Programs" / "obs-studio", base / "Steam" / "steamapps" / "common" / "OBS Studio"]
    roots += [Path("C:/obs-studio"), Path("C:/OBS-studio"), Path("D:/obs-studio")]
    for r in roots:
        p = r / "data" / "obs-studio" / "themes" / "Yami.obt"
        if p.exists():
            return p
    return None


def obs_variant(yami_text, P):
    """(the .ovt text, how many colours of Yami were read, how many variables the variant sets).
    Black backgrounds, accent buttons. Yami's own colour variables are read from the install (so the names match your
    version): greys become neutral and darker, the blues become the accent. The variables Yami uses for windows, inputs and
    buttons are then set outright, and a few rules make every button the accent colour whatever Yami calls its variables."""
    m = re.search(r"@OBSThemeVars\s*\{(.*?)\n\}", yami_text, re.S)
    if not m:
        raise ValueError("no @OBSThemeVars block in Yami.obt")
    block = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    accent = Hct.from_int(0xFF000000 | int(P.acc[1:], 16))
    out, seen = {}, 0
    for name, value in re.findall(r"(--\w+)\s*:\s*([^;]+);", block):  # every variable, whatever its value looks like
        col = parse_colour(value.strip().strip("'\""))  # #rgb, #rrggbb, rgb(), rgba()
        if col is None:
            continue
        seen += 1
        c = Hct.from_int(0xFF000000 | (col[0] << 16) | (col[1] << 8) | col[2])
        if c.chroma < 10:  # greys and whites: neutral (no accent tint), the dark ones darker
            new = Hct.from_hct(0, 0, c.tone * 0.45 if c.tone < 60 else c.tone)
        elif re.search("primary|blue", name):  # the accent family: the accent hue, same lightness
            new = Hct.from_hct(accent.hue, max(accent.chroma, 24), c.tone)
        else:  # reds, greens, ... keep their meaning
            continue
        out[name] = f"#{new.to_int() & 0xFFFFFF:06x}"
    if not seen:
        sample = " | ".join(l.strip() for l in block.splitlines() if l.strip())[:600]
        raise ValueError(f"no colour variables recognised (0 colours seen). Start of the variables: {sample}")
    out.update({  # the roles themselves, so it does not depend on how the greys are used
        "--bg_window": "#000000", "--bg_base": "#050505", "--bg_preview": "#000000", "--input_bg": "#121212",
        "--button_bg": P.acc, "--button_bg_hover": P.l1, "--button_bg_down": P.d1,
        "--primary": P.acc, "--primary_light": P.l1, "--primary_lighter": P.l2, "--primary_dark": P.d1,
    })
    ink = P.t(.07)
    rules = (f"QMainWindow, QDialog {{ background-color: #000000; }}\n"
             f"QPushButton {{ background-color: {P.acc}; color: {ink}; }}\n"
             f"QPushButton:hover {{ background-color: {P.l1}; }}\n"
             f"QPushButton:pressed {{ background-color: {P.d1}; }}\n"
             f"QPushButton:disabled {{ background-color: #1a1a1a; color: #777777; }}\n")
    return ("@OBSThemeMeta {\n    name: 'YASB Accent';\n    id: 'com.obsproject.Yami.YASBAccent';\n"
            "    extends: 'com.obsproject.Yami';\n    author: 'theme.py';\n    dark: 'true';\n}\n\n"
            "@OBSThemeVars {\n" + "\n".join(f"    {k}: {v};" for k, v in out.items()) + "\n}\n\n" + rules), seen, len(out)


def write_obs(P):
    """OBS: Yami_YASB_Accent.ovt, a variant of OBS's Yami theme recoloured with the accent.
    Reads Yami's colour variables from the OBS install, so the names always match your version.
    Default:  %APPDATA%/obs-studio/themes
    Variables: YASB_OBS_THEMES (output), YASB_OBS_INSTALL (default: Program Files/obs-studio)
    Then:     restart OBS, Settings > Appearance: Theme "Yami", Style "YASB Accent". Needs OBS 30.2+."""
    dirs = folders("YASB_OBS_THEMES", *defaults("obs"))
    if not dirs:
        return
    yami = find_yami()
    if yami is None:
        raise FileNotFoundError("Yami.obt not found - set YASB_OBS_INSTALL to your OBS folder (the one that contains data/obs-studio/themes)")
    body, _seen, _used = obs_variant(yami.read_text(encoding="utf-8", errors="ignore"), P)
    for d in dirs:  # LF line endings: OBS reads the blocks line by line; no BOM
        with open(d / "Yami_YASB_Accent.ovt", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)


# ============================================================================================
#  8. RUNNING THE APP THEMES
#  All apps in one list. One failing app never stops the others.
# ============================================================================================


def log(what):
    """Add the current exception to theme_error.log."""
    try:
        if LOG.exists() and LOG.stat().st_size > 20000:  # it never grows without limit: keep the newest part
            LOG.write_text(LOG.read_text(encoding="utf-8", errors="ignore")[-10000:], encoding="utf-8")
    except OSError:
        pass
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{what}:\n{traceback.format_exc()}\n")


# key, name, folder variable, several folders?, short description, writer
# ---- Windhawk ------------------------------------------------------------------------------
# Windhawk's styler mods (taskbar, start menu, notification centre) colour things with {ThemeResource SystemAccentColorLight1} and so on,
# which is always your Windows accent. ShellFlow swaps those references for the hex colours of the scheme you picked. The mods' settings
# live in the registry (HKLM\SOFTWARE\Windhawk\Engine\Mods\<mod>\Settings), which needs administrator rights to change:
# the first time, one UAC prompt sets up a scheduled task that does the writing, and after that it is silent.
WH_MODS = "windows-11-taskbar-styler,windows-11-start-menu-styler,windows-11-notification-center-styler"
WH_ROOT = r"SOFTWARE\Windhawk\Engine\Mods"
WH_TASK = "ShellFlowWindhawk"
WH_STATE = HERE / "windhawk_state.json"      # what the settings looked like before, and what was written
WH_PENDING = HERE / "windhawk_pending.json"  # changes waiting for the elevated task
ACCENT_REF = re.compile(r"\{ThemeResource (SystemAccentColor(?:Light|Dark)?[123]?)\}")


class Registry:
    """The Windhawk settings in the registry. (Tests use a stand-in with the same three methods.)"""

    def read(self, mod):
        import winreg
        out = {}
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{WH_ROOT}\\{mod}\\Settings", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    if isinstance(value, str):
                        out[name] = value
                    i += 1
        except OSError:
            pass
        return out

    def write(self, mod, values):
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{WH_ROOT}\\{mod}\\Settings", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            for name, value in values.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    def bump(self, mod):
        """The mod reloads its settings when this changes (any different number will do)."""
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{WH_ROOT}\\{mod}", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.SetValueEx(k, "SettingsChangeTime", 0, winreg.REG_DWORD, int(time.time()) & 0x7FFFFFFF)


def wh_mods():
    return [m.strip() for m in (env("YASB_WINDHAWK_MODS") or WH_MODS).split(",") if m.strip()]


def accent_colours(P, capsules=None):
    """What each {ThemeResource SystemAccentColor...} becomes. By default the base accent is the capsules' colour (the bar's capsules use
    the "light1" shade), so everything Windhawk draws in the accent matches the bar. YASB_WINDHAWK_MATCH=accent keeps Windows' own ladder."""
    capsules = (env("YASB_WINDHAWK_MATCH") != "accent") if capsules is None else capsules
    return {"SystemAccentColor": P.l1 if capsules else P.acc, "SystemAccentColorLight1": P.l1, "SystemAccentColorLight2": P.l2,
            "SystemAccentColorLight3": P.l3, "SystemAccentColorDark1": P.d1, "SystemAccentColorDark2": P.d2, "SystemAccentColorDark3": P.d3}


# Style constants whose colour ShellFlow sets by name, whatever they hold now (so a value you edited by hand still follows the scheme):
# the taskbar button in its states, as the bar's capsule and its darker states, and the clock button's dark ground.
WH_OWNED = ("buttonaccent", "buttonaccenthover", "buttonaccentactive", "buttonaccentpressed", "buttonclock")


def wh_const_name(text):
    """"ButtonAccentHover=<SolidColorBrush ... />" -> "buttonaccenthover" ("" when it is not a style constant)."""
    m = re.match(r"\s*(\w+)\s*=\s*<", text)
    return m.group(1).lower() if m else ""


def wh_owned_colour(key, P):
    """The colour of an owned style constant, for the scheme P (None for any other name)."""
    shade = lambda t: _mix(P.l1, "#000000", t)
    exact = env("YASB_WINDHAWK_ACTIVE")
    active = exact.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", exact or "") else shade(.30)
    return {"buttonaccent": P.l1, "buttonaccenthover": shade(.12), "buttonaccentactive": active, "buttonaccentpressed": shade(.33),
            "buttonclock": P.t(.16)}.get(key)


def wh_set_colour(text, colour, solid=True):
    """The setting's text with its brush colour replaced (and Opacity="1" when solid, as the bar's capsules are)."""
    new = re.sub(r'(\bColor\s*=\s*")[^"]*(")', lambda m: m.group(1) + colour + m.group(2), text, count=1)
    return re.sub(r'(\bOpacity\s*=\s*")[^"]*(")', lambda m: m.group(1) + "1" + m.group(2), new, count=1) if solid else new


ACCENT_BRUSH = re.compile(r"<SolidColorBrush\b[^>]*\{ThemeResource SystemAccentColor[^}]*\}[^>]*>")


def wh_render(template, P, colours, capsules):
    """The text of a setting with its accent references replaced. In capsule mode the accent brushes are also made solid (Opacity 1), as the
    bar's capsules are, and a style constant named for a state gets that state's colour: "...Hover" is the capsule darkened by 12%,
    "...Pressed" by 33%, "...Active" by 30% (what a populated workspace is on the bar). Everything that is not a state is the plain capsule colour. YASB_WINDHAWK_ACTIVE=#rrggbb sets the active colour exactly.
    The five button constants in WH_OWNED are set by name instead (hover 12%, active 30%, pressed 33% darker; the clock button a dark ground)."""
    if not capsules:
        return ACCENT_REF.sub(lambda m: colours[m.group(1)], template)
    owned = wh_owned_colour(wh_const_name(template), P)
    if owned:
        return wh_set_colour(template, owned, wh_const_name(template) != "buttonclock")
    text = ACCENT_BRUSH.sub(lambda m: re.sub(r'Opacity="[^"]*"', 'Opacity="1"', m.group(0)), template)
    name = re.match(r"\s*(\w+)\s*=", text)
    key = name.group(1).lower() if name else ""
    state = "pressed" if "pressed" in key else "hover" if ("hover" in key or "pointerover" in key) else \
        "active" if re.search(r"(?<!in)(active|selected|checked)", key) else None
    if state:
        exact = env("YASB_WINDHAWK_ACTIVE")
        active = exact.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", exact or "") else _mix(P.l1, "#000000", .30)
        tint = {"hover": _mix(P.l1, "#000000", .12), "pressed": _mix(P.l1, "#000000", .33), "active": active}[state]
        return ACCENT_REF.sub(lambda m: tint, text)
    return ACCENT_REF.sub(lambda m: colours[m.group(1)], text)


def wh_load_state():
    try:
        return json.loads(WH_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def wh_norm(text):
    """A setting's text with spaces and quotes removed, so a harmless reformatting by Windhawk does not make it look edited."""
    return re.sub(r"[\s\"']+", "", text)


def wh_plan(P, mods, reg, state):
    """What to change. For every setting that mentions an accent colour, the original text (with the {ThemeResource ...} references) is
    remembered, so the next scheme starts again from it. A setting counts as yours (and is left alone) only when it is none of the texts
    ShellFlow has written or seen there: a write that never arrived (the elevated task failed once) must not make it look edited.
    Returns ({mod: {setting: new text}}, new state). The state also lists, under "_skipped", what was left alone."""
    capsules = env("YASB_WINDHAWK_MATCH") != "accent"
    colours, plan, new_state, skipped = accent_colours(P, capsules), {}, {}, {}
    for mod in mods:
        mine, saved = {}, state.get(mod, {})
        for name, cur in reg.read(mod).items():
            rec = saved.get(name) if isinstance(saved.get(name), dict) else None
            if capsules and wh_const_name(cur) in WH_OWNED:  # ours by name, whatever it holds now (a hand-edited value included)
                template = rec["template"] if rec else cur
                new = wh_render(template, P, colours, capsules)
                history = [x for x in ((rec.get("history", []) if rec else []) + [cur, new]) if x][-8:]
                mine[name] = {"template": template, "written": new, "previous": cur, "history": list(dict.fromkeys(history))}
                if new != cur:
                    plan.setdefault(mod, {})[name] = new
                continue
            known = {wh_norm(x) for x in (rec.get("history", []) + [rec.get("written", ""), rec.get("previous", "")] if rec else [])}
            if ACCENT_REF.search(cur):
                template = cur  # an original (or one you changed back to a reference)
            elif rec and wh_norm(cur) in known:
                template = rec["template"]  # something ShellFlow wrote or found there before
            else:
                if rec:
                    skipped.setdefault(mod, []).append(name)  # we wrote here once, and you changed it since
                continue  # not an accent setting, or yours
            new = wh_render(template, P, colours, capsules)
            history = [x for x in ((rec.get("history", []) if rec else []) + [cur, new]) if x][-8:]
            mine[name] = {"template": template, "written": new, "previous": cur, "history": list(dict.fromkeys(history))}
            if new != cur:
                plan.setdefault(mod, {})[name] = new
        if mine:
            new_state[mod] = mine
    if skipped:
        new_state["_skipped"] = skipped
    return plan, new_state


def wh_apply_pending(reg=None):
    """Write the waiting changes into the registry (needs administrator rights). Returns how many settings were written."""
    reg = reg or Registry()
    try:
        pending = json.loads(WH_PENDING.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    n = 0
    for mod, values in pending.items():
        reg.write(mod, values)
        n += len(values)
    for mod in pending:  # only now: the mods all reload at the same moment, after every setting is in place (one flash, not three in a row)
        reg.bump(mod)
    WH_PENDING.unlink(missing_ok=True)
    watch_log(f"windhawk: wrote {n} settings")
    return n


def wh_task_exists():
    r = subprocess.run(["schtasks", "/Query", "/TN", WH_TASK], capture_output=True, creationflags=NO_WINDOW if os.name == "nt" else 0)
    return r.returncode == 0


def wh_run_task():
    """Ask the elevated scheduled task to write the waiting changes (silent: no prompt)."""
    r = subprocess.run(["schtasks", "/Run", "/TN", WH_TASK], capture_output=True, creationflags=NO_WINDOW if os.name == "nt" else 0)
    return r.returncode == 0


def wh_setup_task():
    """One UAC prompt: create the scheduled task that runs `theme.py windhawk-apply` with administrator rights."""
    cmd = HERE / "windhawk_setup.cmd"
    cmd.write_text(f'@echo off\r\nschtasks /Create /TN "{WH_TASK}" /TR "\\"{pythonw()}\\" \\"{Path(__file__).resolve()}\\" windhawk-apply" '
                   f'/SC ONCE /ST 00:00 /RL HIGHEST /F\r\n', encoding="utf-8")
    ps = f"Start-Process -FilePath cmd.exe -ArgumentList '/c','{cmd}' -Verb RunAs -Wait -WindowStyle Hidden"
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=NO_WINDOW if os.name == "nt" else 0)
    return wh_task_exists()


def write_windhawk(P, reg=None):
    """Windhawk: the styler mods follow your colour scheme instead of the Windows accent.
    Off by default (switch it on under Templates). Mods: YASB_WINDHAWK_MODS (comma separated mod ids).
    Needs administrator rights once: Templates > Windhawk > Set up."""
    reg = reg or Registry()
    plan, state = wh_plan(P, wh_mods(), reg, wh_load_state())
    WH_STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    if not plan:
        return False
    WH_PENDING.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    try:
        wh_apply_pending(reg)  # works when this process is allowed to write
    except OSError:
        if not (wh_task_exists() and wh_run_task()):
            raise PermissionError("Windhawk's settings need administrator rights: open ShellFlow > Templates > Windhawk and press Set up")
    return True


def wh_restore(reg=None):
    """Put the {ThemeResource ...} references back (so the mods follow the Windows accent again). Returns how many settings."""
    reg, state = reg or Registry(), wh_load_state()
    pending = {mod: {name: rec["template"] for name, rec in settings.items()} for mod, settings in state.items() if settings and not mod.startswith("_")}
    if not pending:
        return 0
    WH_PENDING.write_text(json.dumps(pending, indent=1), encoding="utf-8")
    try:
        n = wh_apply_pending(reg)
    except OSError:
        if not (wh_task_exists() and wh_run_task()):
            raise PermissionError("administrator rights are needed: Templates > Windhawk > Set up")
        n = sum(len(v) for v in pending.values())
    WH_STATE.unlink(missing_ok=True)
    return n


APP_TABLE = (
    ("discord", "Discord", "YASB_DISCORD_THEMES", True, "midnight colours (BetterDiscord, Vencord, Equicord)", write_discord),
    ("zed", "Zed", "YASB_ZED_THEMES", False, "dark theme \"YASB Accent\"", write_zed),
    ("obsidian", "Obsidian", "YASB_OBSIDIAN_VAULTS", True, "CSS snippet for every vault", write_obsidian),
    ("vscode", "VS Code", "YASB_VSCODE_EXTENSIONS", False, "theme extension \"YASB Accent\"", write_vscode),
    ("nvim", "Neovim", "YASB_NVIM_COLORS", False, "colour scheme \"yasb\"", write_nvim),
    ("wt", "Windows Terminal", "YASB_WT_FRAGMENTS", False, "colour scheme \"YASB Accent\"", write_wt),
    ("firefox", "Firefox", "YASB_FIREFOX_PROFILES", True, "userChrome / userContent styles", write_firefox),
    ("zen", "Zen Browser", "YASB_ZEN_PROFILES", True, "userChrome / userContent styles", write_zen),
    ("yazi", "Yazi", "YASB_YAZI_FLAVORS", False, "flavor \"yasb-accent\"", write_yazi),
    ("obs", "OBS Studio", "YASB_OBS_THEMES", False, "variant of the Yami theme", write_obs),
    ("tacky", "Tacky Borders", "YASB_TACKY_CONFIG", False, "active border colour", write_tacky),
    ("filepilot", "File Pilot", "YASB_FILEPILOT_CONFIG", False, "colour scheme \"YASB Accent\" in FPilot-Config.json", write_filepilot),
    ("helium", "Helium", "YASB_HELIUM_THEME", False, "theme extension for Helium and other Chromium browsers (load the folder once)", write_helium),
    ("windhawk", "Windhawk", "YASB_WINDHAWK_MODS", False, "taskbar, start menu and notification styler mods", write_windhawk),
)
MIDDLE_CLICK_TYPES = ("yasb.home.HomeWidget", "yasb.clock.ClockWidget", "yasb.power_menu.PowerMenuWidget", "yasb.notes.NotesWidget",
                      "yasb.control_center.ControlCenterWidget", "yasb.whkd.WhkdWidget", "yasb.wallpapers.WallpapersWidget")  # widgets that accept an `exec` callback
OPT_IN_APPS = {"windhawk"}  # changes settings outside your own folders: only when you switch it on


def enabled_apps():
    """The apps to write: the keys in YASB_APPS (e.g. "zed,obs"), or all of them when it is not set."""
    raw = env("YASB_APPS").strip().lower()
    if raw == "none":  # the installer's default: no app gets a theme until you switch it on
        return set()
    chosen = {k.strip() for k in raw.split(",") if k.strip()}
    return chosen or {row[0] for row in APP_TABLE if row[0] not in OPT_IN_APPS}


def write_apps():
    """Refresh every app theme from the colours in use (the applied scheme, else your Windows accent). Returns {app key: what went wrong} for the failures."""
    failures = {}
    try:
        P = palette()
    except Exception as e:
        log("palette")
        return {"palette": str(e)}
    on = enabled_apps()
    for key, *_, fn in APP_TABLE:  # one failing app must not stop the others
        if key in on:
            try:
                fn(P)
            except Exception as e:
                log(fn.__name__)
                failures[key] = f"{type(e).__name__}: {e}"
    return failures


# ============================================================================================
#  8a. SOUNDS  (soft Pixel-style UI sounds, synthesised here: no audio files)
#  Used by ShellFlow's window, and by the background helper for clicks on the YASB bar.
# ============================================================================================
try:
    import winsound  # Windows only
except ImportError:
    winsound = None
import array
import io
import math
import wave


class Sfx:
    """A glassy tick for clicks, a rising pair for on, a falling pair for off, a small chime for done.
    Each sound is a small WAV file in scripts/.sounds (the volume is baked in: winsound has no volume control) played
    with winsound. (Playing straight from memory is not allowed together with async playback, which is why the
    first version was silent.) volume is 0..100."""
    # name: [(frequency Hz, length ms, strength 0..1), ...]
    RECIPES = {"click": [(1318, 46, .95)], "tap": [(988, 38, .85)], "on": [(880, 56, .95), (1318, 90, 1.0)],
               "off": [(1318, 48, .9), (880, 84, .9)], "apply": [(784, 70, .95), (988, 70, .95), (1318, 150, 1.0)],
               "reset": [(660, 62, .9), (494, 100, .9)], "error": [(330, 100, .95), (262, 150, .95)]}
    # Pitch variation: every sound also exists a little higher and lower (up to two semitones: a hint of variety, not a different note),
    # and each time one that is not the one just played is chosen. Variant 0 is the sound as written. The error sound never varies.
    PITCHES = (0, 1, -1, 2, -2)
    DIR = HERE / ".sounds"

    def __init__(self, enabled=True, volume=10):
        self.enabled, self.volume, self.played, self.last_error = enabled, volume, [], ""
        self.last_variant = {}

    def configure(self, enabled=None, volume=None):
        self.enabled = self.enabled if enabled is None else enabled
        if volume is not None:
            self.volume = max(0, min(100, int(volume)))
            for old in self.DIR.glob("*.wav") if self.DIR.exists() else []:  # sounds made for another volume
                if not re.search(rf"_{self.volume}(_\d+)?$", old.stem):
                    try:
                        old.unlink()
                    except OSError:
                        pass

    def render(self, name, variant=0):
        """The sound as WAV bytes (16 bit mono), `variant` picking one of PITCHES (the same length, higher or lower)."""
        rate, amp = 44100, (self.volume / 100) ** 1.15 * 0.95
        shift = 2 ** (self.PITCHES[variant] / 12) if name != "error" else 1.0
        out = array.array("h")
        for freq, ms, strength in self.RECIPES[name]:
            freq *= shift
            decay = 4.5 / (ms / 1000)
            for i in range(int(rate * ms / 1000)):
                t = i / rate
                env = min(1.0, t / 0.003) * math.exp(-decay * t)
                v = math.sin(2 * math.pi * freq * t) + .26 * math.sin(4 * math.pi * freq * t) + .10 * math.sin(6 * math.pi * freq * t)
                out.append(int(max(-1.0, min(1.0, v * env * strength * amp / 1.25)) * 32767))
            out.extend([0] * int(rate * 0.004))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(out.tobytes())
        return buf.getvalue()

    def path(self, name, variant=0):
        """The file for this sound at the current volume and pitch (made the first time it is needed)."""
        p = self.DIR / (f"{name}_{self.volume}.wav" if not variant else f"{name}_{self.volume}_{variant}.wav")
        if not p.exists():
            self.DIR.mkdir(exist_ok=True)
            p.write_bytes(self.render(name, variant))
        return p

    def pick(self, name):
        """Which pitch to play this time: never the one used last for this sound (and always 0 when variation is off)."""
        if name == "error" or env("YASB_SOUND_VARY") == "0":
            return 0
        import random
        choices = [k for k in range(len(self.PITCHES)) if k != self.last_variant.get(name)]
        self.last_variant[name] = random.choice(choices)
        return self.last_variant[name]

    def play(self, name):
        if not name:
            return
        self.played = (self.played + [name])[-30:]
        if not self.enabled or self.volume <= 0 or winsound is None or name not in self.RECIPES:
            return
        try:
            winsound.PlaySound(str(self.path(name, self.pick(name))), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            self.last_error = ""
        except Exception as e:  # remembered, so the Preview button and the doctor can say why nothing is heard
            self.last_error = f"{type(e).__name__}: {e}"


def sound_settings():
    on = env("YASB_SOUNDS") not in ("0", "false", "off")
    try:
        vol = max(0, min(100, int(env("YASB_SOUND_VOLUME") or 10)))
    except ValueError:
        vol = 10
    return on, vol


def mouse_sample():
    """(left button down, right button down, x, y) on screen. Windows only."""
    from ctypes import wintypes
    u = ctypes.windll.user32
    pt = wintypes.POINT()
    u.GetCursorPos(ctypes.byref(pt))
    return bool(u.GetAsyncKeyState(1) & 0x8000), bool(u.GetAsyncKeyState(2) & 0x8000), pt.x, pt.y


_DLLS, _EXE_NAMES = None, {}


def _dlls():
    """Private copies of the Win32 functions with their prototypes set, so the prototypes do not touch the rest of the program."""
    global _DLLS
    if _DLLS is None:
        from ctypes import wintypes
        win = getattr(ctypes, "WinDLL", None)
        u, k = (win("user32"), win("kernel32")) if win else (ctypes.windll.user32, ctypes.windll.kernel32)
        try:
            u.WindowFromPoint.argtypes, u.WindowFromPoint.restype = [wintypes.POINT], ctypes.c_void_p
            u.GetAncestor.argtypes, u.GetAncestor.restype = [ctypes.c_void_p, ctypes.c_uint], ctypes.c_void_p
            u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            u.IsWindowVisible.argtypes = [ctypes.c_void_p]
            u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
            k.OpenProcess.argtypes, k.OpenProcess.restype = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong], ctypes.c_void_p
            k.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
            k.CloseHandle.argtypes = [ctypes.c_void_p]
        except (AttributeError, TypeError):
            pass
        _DLLS = (u, k)
    return _DLLS


def exe_of_pid(pid):
    """The program (lower-case file name, e.g. "yasb.exe") a process is running, or "". Remembered for 30 s. Windows only."""
    known = _EXE_NAMES.get(pid)
    if known and time.time() - known[1] < 30:
        return known[0]
    _, k = _dlls()
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    buf, size = ctypes.create_unicode_buffer(520), ctypes.c_ulong(520)
    ok = k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    k.CloseHandle(h)
    name = buf.value.replace("\\", "/").rsplit("/", 1)[-1].lower() if ok else ""
    _EXE_NAMES[pid] = (name, time.time())
    return name


def window_exe_at(x, y):
    """The program (lower-case file name, e.g. "yasb.exe") that owns the window under a screen point, or "". Windows only."""
    try:
        from ctypes import wintypes
        u, _ = _dlls()
        hwnd = u.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        if not hwnd:
            return ""
        top = u.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT: the program's top-level window (the bar, or a menu of it)
        pid = ctypes.c_ulong()
        u.GetWindowThreadProcessId(top, ctypes.byref(pid))
        return exe_of_pid(pid.value)
    except Exception:
        return ""


def window_shadow(root, on):
    """Switch Windows' drop shadow of a window on or off (an attached window must not have a dark band of shadow below it).
    DWMWA_NCRENDERING_POLICY: 1 = no frame rendering, no shadow; 0 = the window's own style."""
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 2, ctypes.byref(ctypes.c_int(0 if on else 1)), 4)
    except Exception:
        pass


def bar_pill_edge(rect, edge, expected, colour=(0, 0, 0)):
    """The y of the visible bar's edge that a window attached to it should touch, read off the screen: the first row below a top bar (above
    a bottom bar). The window rectangle Windows reports includes margins, and the capsules end a few pixels above the bar's own edge, so
    the edge is looked for in the pixels around `expected` (+-14): the bar is `colour` (black), the desktop is not. None if it cannot tell."""
    try:
        from PIL import ImageGrab
        l, t, r, b = rect
        lo, hi = expected - 14, expected + 14
        img = ImageGrab.grab(bbox=(l, lo, r, hi), all_screens=True).convert("RGB")
        w, h = img.size
        px = img.load()
        bar = lambda c: max(abs(c[i] - colour[i]) for i in range(3)) <= 12
        votes = {}
        for x in range(24, w - 24, 5):  # (not the rounded ends)
            rows = range(h - 2) if edge == "top" else range(h - 1, 1, -1)
            for y in rows:
                nxt = (1, 2) if edge == "top" else (-1, -2)
                if bar(px[x, y]) and all(not bar(px[x, y + d]) for d in nxt):
                    votes[lo + y + 1 if edge == "top" else lo + y] = votes.get(lo + y + 1 if edge == "top" else lo + y, 0) + 1
                    break
        best = max(votes, key=votes.get) if votes else None
        return best if best is not None and votes[best] >= 3 else None
    except Exception:
        return None


def pick_bars(windows, exe):
    """From [(visible, (left, top, right, bottom), program)] the rectangles of the bars: visible windows of `exe` that are strips (wide,
    and not tall: a menu or a preview is taller)."""
    return [r for visible, r, program in windows if visible and program == exe and r[2] - r[0] > 300 and 20 < r[3] - r[1] < 200]


def bar_rects(exe=None, windows=None):
    """The rectangles (left, top, right, bottom) of the YASB bar windows on screen right now, asked of Windows (every top-level window and
    the program it belongs to, not what is under one point). [] if none is found. `windows` replaces the asking (for tests)."""
    exe = (exe or env("YASB_BAR_EXE") or "yasb.exe").lower()
    if windows is None:
        windows = []
        try:
            from ctypes import wintypes
            u, _ = _dlls()
            proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def each(hwnd, _):
                r, pid, seen = wintypes.RECT(), ctypes.c_ulong(), wintypes.RECT()
                u.GetWindowRect(hwnd, ctypes.byref(r))
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:  # what you can SEE of the window: GetWindowRect also counts the invisible resize borders and shadow margins
                    if ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), 9, ctypes.byref(seen), ctypes.sizeof(seen)) == 0:  # DWMWA_EXTENDED_FRAME_BOUNDS
                        r = seen
                except Exception:
                    pass
                windows.append((bool(u.IsWindowVisible(hwnd)), (r.left, r.top, r.right, r.bottom), exe_of_pid(pid.value)))
                return True
            u.EnumWindows(proc(each), 0)
        except Exception:
            log("bar_rects")
            return []
    return pick_bars(windows, exe)


class BarSounds:
    """A soft tick when you click the YASB bar or one of its menus (any window of yasb.exe). YASB itself has no sounds, so
    this watches the mouse: a new left press plays "click", a right press plays "tap". The sound is the same one ShellFlow's
    buttons use, at the same volume. It cannot tell a widget from the empty part of the bar: both tick."""

    def __init__(self, fx, exe_at=None, sample=None):
        self.fx, self.exe_at, self.sample = fx, exe_at or window_exe_at, sample or mouse_sample
        self.was, self.enabled, self.exe, self.stamp, self.applied = (False, False), True, "yasb.exe", 0.0, None

    def reload(self, force=False):
        """Re-read the settings (the .env) every few seconds, so changes in ShellFlow apply without restarting."""
        if not force and time.time() - self.stamp < 3:
            return
        self.stamp = time.time()
        on, vol = sound_settings()
        self.enabled = on and env("YASB_BAR_SOUNDS") == "1"  # off unless switched on
        self.exe = (env("YASB_BAR_EXE") or "yasb.exe").lower()
        if (on, vol) != self.applied:
            self.applied = (on, vol)
            self.fx.configure(enabled=on, volume=vol)

    def tick(self):
        """One look at the mouse. Returns the sound that was played, if any."""
        left, right, x, y = self.sample()
        new_left, new_right = left and not self.was[0], right and not self.was[1]
        self.was = (left, right)
        if not (new_left or new_right) or not self.enabled:
            return None
        if self.exe_at(x, y) != self.exe:
            return None
        name = "click" if new_left else "tap"
        self.fx.play(name)
        return name

    def run(self):
        for name in ("click", "tap"):  # make the files now, so the first click is not late
            try:
                self.reload(force=True)
                self.fx.path(name)
            except Exception:
                pass
        while True:
            try:
                self.reload()
                self.tick()
            except Exception:
                pass
            time.sleep(0.012)


# ============================================================================================
#  8b. KEEPING THE APPS IN SYNC  (theme.py watch)
#  Runs in the background. When the wallpaper or the accent changes it re-applies the scheme you use (the
#  wallpaper is its seed) and rewrites the app themes, so Discord, Zed and the rest follow without you
#  opening anything. One copy runs at a time (theme_watch.pid); ShellFlow can start it with Windows.
# ============================================================================================
PIDFILE = HERE / "theme_watch.pid"
HELPER_VERSION = 4  # 1 = app sync only, 2 = also sounds on the YASB bar, 3 = reads its settings from the .env, 4 = pitch variation (an older helper is restarted by start_watcher)
WATCH_LOG = HERE / "theme_watch.log"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ShellFlowSync"
NO_WINDOW = 0x08000000


def mtime(path):
    try:
        return int(Path(path).stat().st_mtime_ns)
    except OSError:
        return 0


def wallpaper_path():
    buf = ctypes.create_unicode_buffer(520)
    ctypes.windll.user32.SystemParametersInfoW(0x73, 520, buf, 0)  # SPI_GETDESKWALLPAPER
    return buf.value


def theme_signature():
    """Changes whenever the wallpaper, the Windows accent or the colours YASB wrote change."""
    try:
        wp = wallpaper_path()
    except Exception:
        wp = ""
    transcoded = where("APPDATA") / "Microsoft" / "Windows" / "Themes" / "TranscodedWallpaper"
    try:
        accent = windows_accent_seed()
    except Exception:
        accent = 0
    try:  # the colours in yasb_colors.css, not its timestamp: YASB rewriting the same colours must not start a refresh
        colours = tuple(sorted(accent_shades().items()))
    except Exception:
        colours = ()
    return (wp, mtime(wp) if wp else 0, mtime(transcoded), accent, colours)


def refresh_all():
    """Re-apply the scheme in use (new wallpaper = new seed colour), then rewrite the app themes."""
    name = current_variant()
    if name not in dict(menu_items()) or name == "custom" and not custom_colours():
        name = "windows"
    for key, why in (apply(name) or {}).items():  # apply() ends with write_apps()
        watch_log(f"{key}: {why}")


def watcher_version():
    try:
        return int(PIDFILE.read_text().split()[2])
    except (OSError, ValueError, IndexError):
        return 1


def helper_wanted():
    """The helper runs while app sync or the sounds on the YASB bar are on."""
    return env("YASB_SYNC") != "0" or (env("YASB_BAR_SOUNDS") == "1" and sound_settings()[0])


def apply_helper_settings():
    """Make the helper match the settings: start it (and with Windows) when wanted, stop it when not."""
    wanted = helper_wanted()
    try:
        if not set_autostart(wanted):
            watch_log("could not " + ("add" if wanted else "remove") + " the start-with-Windows entry")
    except Exception:
        watch_log("start-with-Windows entry failed: " + traceback.format_exc().strip().splitlines()[-1])
        log("autostart")
    start_watcher() if wanted else stop_watcher()
    return wanted


def watcher_running():
    """Is a watcher running? The pid file holds "pid start-time"; a pid reused by another program after a restart does not count."""
    try:
        pid, born = PIDFILE.read_text().split()[:2]
        return proc_start(pid) == int(born)
    except (OSError, ValueError):
        return False


def watch_log(text):
    if env("YASB_LOGS") != "1":
        return
    try:
        lines = WATCH_LOG.read_text(encoding="utf-8").splitlines()[-60:] if WATCH_LOG.exists() else []
        WATCH_LOG.write_text("\n".join(lines + [time.strftime("%Y-%m-%d %H:%M:%S ") + text]) + "\n", encoding="utf-8")
    except OSError:
        pass


def watch():
    """The background helper. Every 1.5 s it checks the wallpaper and accent and, when they stop changing, refreshes the apps
    (unless app sync is off); in a thread of its own it plays the sounds for clicks on the YASB bar."""
    if watcher_running() and PIDFILE.read_text().split()[0] != str(os.getpid()):
        return  # already running
    PIDFILE.write_text(f"{os.getpid()} {proc_start(os.getpid()) or 0} {HELPER_VERSION}")
    watch_log(f"helper started (version {HELPER_VERSION})")
    try:
        if helper_wanted() and not autostart_enabled():
            set_autostart(True)
            watch_log("added the missing start-with-Windows entry")
    except Exception:
        pass
    try:
        import threading
        threading.Thread(target=BarSounds(Sfx(*sound_settings())).run, daemon=True).start()
    except Exception:
        watch_log("bar sounds could not start: " + traceback.format_exc().strip().splitlines()[-1])
    last, pending, since = theme_signature(), False, 0.0
    while True:
        time.sleep(1.5)
        try:
            if not helper_wanted():
                watch_log("sync and bar sounds are both off: the helper ends")
                PIDFILE.unlink(missing_ok=True)
                return
            now = theme_signature()
            if env("YASB_SYNC") == "0":  # app sync is off: only the sounds run
                last, pending = now, False
            elif now != last:
                last, pending, since = now, True, time.time()
            elif pending and time.time() - since >= 1.5:
                pending = False
                refresh_all()
                watch_log("refreshed after a wallpaper or accent change")
                last = theme_signature()
        except Exception:
            watch_log("error: " + traceback.format_exc().strip().splitlines()[-1])
            log("watch")


def pythonw():
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def start_watcher():
    """Start the background helper now. One that is already running stays; an older version of it is restarted."""
    if watcher_running():
        if watcher_version() == HELPER_VERSION:
            return True
        stop_watcher()
        time.sleep(0.4)
    extra = {"creationflags": NO_WINDOW | 0x00000008} if os.name == "nt" else {}
    env = {k: v for k, v in os.environ.items() if k not in CLEAN_ENV_DROP}
    subprocess.Popen([pythonw(), str(Path(__file__).resolve()), "watch"], stdin=subprocess.DEVNULL, env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **extra)
    return True


def stop_watcher():
    try:
        if watcher_running():
            subprocess.run(["taskkill", "/PID", PIDFILE.read_text().split()[0], "/F"], capture_output=True, creationflags=NO_WINDOW)
        PIDFILE.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except OSError:
        return False


def autostart_command():
    return f'"{pythonw()}" "{Path(__file__).resolve()}" watch'


def set_autostart(on):
    """Start the helper with Windows (a value in HKCU\\...\\Run). Returns True when the entry is really in the state asked
    for (it is read back), so a failure is never silent."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass
    return autostart_enabled() == bool(on)


def helper_status():
    """One sentence about the background helper, for ShellFlow's General page and the doctor."""
    running = watcher_running()
    try:
        auto = autostart_enabled()
    except Exception:
        auto = None
    text = f"Running (version {watcher_version()})" if running else "Not running"
    return text + ("" if auto is None else ", starts with Windows" if auto else ", does NOT start with Windows yet")


def restart_helper():
    stop_watcher()
    time.sleep(0.4)
    return start_watcher()


def setup():
    """One command that sets everything up: the Home menu entry, the helper now, and the helper with Windows."""
    lines = []
    try:
        lines.append("Home menu: " + install_menu())
    except Exception as e:
        lines.append(f"Home menu: not changed ({e})")
    try:
        lines.append(f"Helper: {'wanted' if apply_helper_settings() else 'switched off in the settings'}. {helper_status()}")
    except Exception:
        lines.append("Helper: " + traceback.format_exc().strip().splitlines()[-1])
    return "\n".join(lines)


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


def make_dpi_aware():
    """Draw sharply on scaled displays."""
    ctypes.windll.shcore.SetProcessDpiAwareness(2)


def monitor_info():
    """(work area, dpi scale) of the monitor under the cursor."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    mon = user32.MonitorFromPoint(pt, 2)  # nearest monitor
    mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(mon, ctypes.byref(mi))
    dpi = ctypes.c_uint()
    ctypes.windll.shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dpi), ctypes.byref(ctypes.c_uint()))
    w = mi.rcWork
    return (w.left, w.top, w.right, w.bottom), dpi.value / 96


def round_window(root):
    """Windows 11 rounded corners, no border (cosmetic, ignored where unsupported)."""
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(ctypes.c_uint(0xFFFFFFFE)), 4)
    except Exception:
        pass


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


# ============================================================================================
#  10. ENTRY POINT
#  Reads the command line. Any crash is written to theme_error.log.
# ============================================================================================


def keep_helper_running():
    """Any normal use of theme.py (the picker, apps, a scheme) also starts the background helper if it is wanted but not running,
    so the bar sounds and the app sync do not wait for ShellFlow to be opened."""
    try:
        if helper_wanted() and (not watcher_running() or watcher_version() != HELPER_VERSION):
            start_watcher()
    except Exception:
        pass


def main():
    """Run the command given on the command line."""
    name = (sys.argv[1] if len(sys.argv) > 1 else "windows").lower()
    if name not in ("watch", "doctor", "install-menu", "setup", "ensure", "settings", "windhawk", "windhawk-apply", "windhawk-setup", "windhawk-restore"):
        keep_helper_running()
    if name == "menu":
        show_picker()
    elif name == "apps":
        write_apps()
    elif name == "settings":
        import settings
        settings.main()
    elif name == "watch":
        watch()
    elif name == "windhawk":
        print("Windhawk: wrote settings" if write_windhawk(palette()) else "Windhawk: nothing to change", flush=True)
    elif name == "windhawk-apply":  # run by the elevated scheduled task
        print(f"Windhawk: {wh_apply_pending()} settings written", flush=True)
    elif name == "windhawk-setup":
        print("Windhawk: task ready" if wh_setup_task() else "Windhawk: the task was not created (was the prompt cancelled?)", flush=True)
    elif name == "windhawk-restore":
        print(f"Windhawk: {wh_restore()} settings put back", flush=True)
    elif name == "doctor":
        doctor()
    elif name == "setup":
        print(setup(), flush=True)
    elif name == "ensure":
        keep_helper_running()
    elif name == "install-menu":
        print(install_menu(), flush=True)
    else:
        apply(name)


HOME_ENTRY = re.compile(r'^(\s*)- \{ title: "(?:Settings|ShellFlow)"[^\n]*$', re.M)


def menu_entry():
    """The Home menu line that opens ShellFlow: this Python and this script, written out in full (no variables)."""
    py = pythonw().replace("\\", "/")
    script = str(Path(__file__).resolve()).replace("\\", "/")
    return f'- {{ title: "ShellFlow", command: "{py}", args: ["{script}", "settings"], show_window: false }}'


def install_menu(cfg_path=None):
    """Add (or repair) the ShellFlow entry in the Home widget's menu in config.yaml. Returns a sentence saying what happened."""
    path = Path(cfg_path) if cfg_path else CONFIG / "config.yaml"
    text = path.read_text(encoding="utf-8")
    entry = menu_entry()
    m = HOME_ENTRY.search(text)
    if m:
        new = text[:m.start()] + m.group(1) + entry + text[m.end():]
        said = "replaced the existing ShellFlow/Settings entry"
    else:
        t = re.search(r'^(\s*)- \{ title: "Theme"[^\n]*$', text, re.M)
        if not t:
            raise ValueError('no Home menu found: add a line like  - { title: "Theme", ... }  to the Home widget\'s menu_list first')
        new = text[:t.end()] + "\n" + t.group(1) + entry + text[t.end():]
        said = "added the entry below Theme"
    if new == text:
        return "the ShellFlow entry in config.yaml is already correct"
    write_if_changed(path, new)
    return f"{said}. YASB reloads the config by itself. (Use ShellFlow > Backup first if you want a copy.)"


def doctor():
    """Run from a terminal: checks everything ShellFlow needs on this PC, builds every page once, prints the result and
    writes shellflow_doctor.txt (send that file if ShellFlow still does not open)."""
    out = []

    def say(text=""):
        print(text, flush=True)
        out.append(text)

    def check(label, fn):
        t = time.time()
        try:
            r = fn()
            say(f"  OK    {label}" + (f": {r}" if r not in (None, True) else "") + f"   ({time.time() - t:.1f}s)")
        except Exception:
            say(f"  FAIL  {label}: {traceback.format_exc().strip().splitlines()[-1]}")

    say(f"ShellFlow doctor - {time.ctime()}")
    say(f"python      {sys.version.split()[0]}  {sys.executable}")
    say(f"script      {Path(__file__).resolve()}")
    say(f"settings.py {'found' if (HERE / 'settings.py').exists() else 'MISSING next to theme.py'}")
    say(f"config      {CONFIG}   config.yaml {'yes' if (CONFIG / 'config.yaml').exists() else 'NO'} | styles.css {'yes' if (CONFIG / 'styles.css').exists() else 'NO'} | yasb_colors.css {'yes' if (CONFIG / 'yasb_colors.css').exists() else 'NO'}")
    say(f"env         YASB_THEME_SCRIPT: environment={os.environ.get('YASB_THEME_SCRIPT')!r}  .env={env('YASB_THEME_SCRIPT')!r}   YASB_SYNC={env('YASB_SYNC')!r}")
    stale = {k: os.environ[k] for k in sorted(LIVE_KEYS | {row[2] for row in APP_TABLE}) if os.environ.get(k) and os.environ[k] != dotenv().get(k, "")}
    if stale:
        say(f"stale copies inherited from YASB (ignored; the .env wins): {stale}")
    inherited = {k: os.environ[k] for k in CLEAN_ENV_DROP if k in os.environ}
    say(f"inherited   {inherited or 'nothing odd (no PYTHONHOME / PYTHONPATH / TCL_LIBRARY / TK_LIBRARY)'}")
    say()
    say("Home menu (what YASB runs when you press ShellFlow)")
    try:
        cfg = (CONFIG / "config.yaml").read_text(encoding="utf-8")
        entries = HOME_ENTRY.findall(cfg) and [m.group(0).strip() for m in HOME_ENTRY.finditer(cfg)]
        if not entries:
            say("  FAIL  there is NO ShellFlow / Settings entry in the Home widget's menu_list in config.yaml.")
            say("        Fix: python theme.py install-menu")
        for line in entries or []:
            say("  entry: " + line)
            cmd = re.search(r'command: "([^"]+)"', line)
            args = re.findall(r'"([^"]*)"', line.split("args:")[1]) if "args:" in line else []

            def resolve(p):
                p = re.sub(r"\$env:(\w+)", lambda m: os.environ.get(m.group(1)) or env(m.group(1)) or "<NOT SET>", p)
                return p
            py = resolve(cmd.group(1)) if cmd else "<no command>"
            script = resolve(args[0]) if args else "<no script>"
            say(f"        python  -> {py}  [{'exists' if os.path.exists(py) else 'MISSING'}]")
            say(f"        script  -> {script}  [{'exists' if os.path.exists(script) else 'MISSING'}]")
            say(f"        argument-> {args[1] if len(args) > 1 else '<none>'}  [{'ok' if args[1:2] == ['settings'] else 'must be: settings'}]")
            if "<NOT SET>" in py + script or not os.path.exists(script):
                say("        >> YASB cannot start this. Fix: python theme.py install-menu   (writes full paths, no variables)")
    except OSError as e:
        say(f"  cannot read config.yaml: {e}")
    try:
        log = open(CONFIG / "yasb.log", encoding="utf-8", errors="ignore").read().splitlines()[-4000:]
        hits = [l for l in log if re.search(r"ShellFlow|theme\.py|settings\.py|pythonw", l, re.I)][-6:]
        say("  YASB's own log, lines about it: " + ("" if hits else "none (YASB logged nothing when the entry was pressed)"))
        for l in hits:
            say("    " + l[:200])
    except OSError:
        pass
    say()
    say("Packages")
    for mod in ("PIL", "materialyoucolor", "tkinter", "winsound", "winreg"):
        check(mod, lambda m=mod: getattr(importlib.import_module(m), "__version__", "") or None)
    say()
    say("Windows")
    import tkinter as tk
    check("Tk starts", lambda: (lambda r: (r.withdraw(), tk.TkVersion, r.destroy())[1])(tk.Tk()))
    check("monitor under the cursor", lambda: monitor_info())
    check("wallpaper path", wallpaper_path)
    check("Windows accent (registry)", lambda: "#%06x" % (windows_accent_seed() & 0xFFFFFF))
    check("seed colour from the wallpaper", lambda: "#%06x" % (get_seed() & 0xFFFFFF))
    check("palette", lambda: palette(effective=True).acc)
    say()
    say("Other copies and the background helper")
    try:
        pid, born, stamp = open(_PIDFILE, encoding="utf-8").read().split()
        alive = proc_start(pid) == int(born)
        wins = _windows_of(int(pid)) if alive else []
        say(f"  pid file: pid {pid}, {'RUNNING' if alive else 'not running (stale, harmless)'}, started {time.time() - float(stamp):.0f}s ago, windows titled ShellFlow: {wins or 'none'}")
        if alive and not any(v for _, v in wins):
            say("  >> a ShellFlow process is running WITHOUT a visible window. That blocks a new start for up to 45s; it is ended automatically after that.")
    except (OSError, ValueError):
        say("  no pid file (nothing running)")
    say(f"  background helper running: {watcher_running()} (version {watcher_version()}, current {HELPER_VERSION})   autostart entry: {autostart_enabled() if os.name == 'nt' else 'n/a'}")
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            cmd = winreg.QueryValueEx(k, RUN_NAME)[0]
        parts = re.findall(r'"([^"]+)"', cmd)
        say(f"    starts with Windows: {cmd}")
        for p in parts[:2]:
            say(f"      {p}  [{'exists' if os.path.exists(p) else 'MISSING - run: python theme.py setup'}]")
    except Exception:
        say("    starts with Windows: no entry yet (python theme.py setup adds it)")
    on, vol = sound_settings()
    say(f"  sounds {'on' if on else 'OFF'}, volume {vol}%   |   sounds on the YASB bar: {'on' if env('YASB_BAR_SOUNDS') == '1' else 'OFF'}   (program: {env('YASB_BAR_EXE') or 'yasb.exe'})")
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + (env("YASB_BAR_EXE") or "yasb.exe"), "/NH"], capture_output=True, text=True,
                             creationflags=NO_WINDOW).stdout
        say("  " + (env("YASB_BAR_EXE") or "yasb.exe") + (" is running" if "yasb" in out.lower() or (env("YASB_BAR_EXE") or "").lower() in out.lower() else " is NOT running (the click sounds only react to that program; set YASB_BAR_EXE if yours has another name)"))
    except Exception:
        pass
    say()
    say("OBS (only if you use the OBS theme)")
    try:
        obs_user = where("APPDATA") / "obs-studio"
        if not obs_user.is_dir():
            say("  OBS has never run here (no %APPDATA%\\obs-studio): nothing to theme")
        else:
            yami = find_yami()
            say(f"  Yami.obt: {yami or 'NOT FOUND (set YASB_OBS_INSTALL in the .env to your OBS folder)'}")
            if yami:
                text, seen, used = obs_variant(yami.read_text(encoding="utf-8", errors="ignore"), palette())
                say(f"  Yami's colours read: {seen}, recoloured with your accent: {used}")
            ovt = obs_user / "themes" / "Yami_YASB_Accent.ovt"
            say(f"  variant file: {ovt}  [{'exists' if ovt.exists() else 'MISSING: press Apply now in ShellFlow > Templates'}]")
            if ovt.exists():
                head = ovt.read_text(encoding="utf-8").splitlines()[:8]
                say("    " + " | ".join(l.strip() for l in head if l.strip()))
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"], capture_output=True, text=True, creationflags=NO_WINDOW).stdout
            say("  OBS is " + ("RUNNING: close it and open it again, OBS reads themes only at start-up" if "obs64" in out.lower() else "closed") )
            say("  In OBS: Settings > Appearance > Theme = Yami, then Style = YASB Accent")
    except Exception:
        say(f"  FAIL  {traceback.format_exc().strip().splitlines()[-1]}")
    say()
    say("The YASB bar window (ShellFlow attached to the bar takes its width from it)")
    try:
        rects = bar_rects()
        say(f"  bar windows found: {rects if rects else 'none (a bar with width auto then gets the normal ShellFlow width; a % or pixel width is read from config.yaml)'}")
    except Exception:
        say(f"  FAIL  {traceback.format_exc().strip().splitlines()[-1]}")
    say()
    say("Windhawk (only if you use its styler mods)")
    try:
        reg = Registry()
        found = {m: reg.read(m) for m in wh_mods()}
        installed = any(found.values())
        say(f"  Windhawk settings found in the registry: {'yes' if installed else 'no (or they cannot be read)'}")
        left = wh_load_state().get("_skipped", {})
        for m, values in found.items():
            refs = sum(1 for v in values.values() if ACCENT_REF.search(v))
            say(f"    {m}: {len(values)} settings, {refs} still use the Windows accent, {len(wh_load_state().get(m, {}))} are ours, "
                f"{len(left.get(m, []))} left alone because they were changed in Windhawk" + (f" ({', '.join(left[m][:3])}...)" if left.get(m) else ""))
        if "windhawk" not in enabled_apps():
            say("  >> Windhawk is OFF in ShellFlow, so nothing follows your colour scheme. Switch it on: Templates > Windhawk (it writes YASB_APPS to the .env).")
        say(f"  switched on in ShellFlow: {'windhawk' in enabled_apps()}   |   elevated task: {'ready' if wh_task_exists() else 'not set up (Templates > Windhawk > Set up)'}   |   waiting changes: {WH_PENDING.exists()}")
    except Exception:
        say(f"  FAIL  {traceback.format_exc().strip().splitlines()[-1]}")
    say()
    say("Building every ShellFlow page once (nothing is shown)")
    try:
        import settings as s
        root = tk.Tk()
        root.withdraw()
        app = s.App(root)
        for i, (name, *_rest) in enumerate(s.PAGES):
            check(f"page {name}", lambda i=i: (app.go(i), root.update())[0])
        app.closing = True
        root.destroy()
    except Exception:
        say(f"  FAIL  could not build the window: {traceback.format_exc().strip().splitlines()[-1]}")
        say(traceback.format_exc())
    say()
    say("Sounds")
    try:
        import settings as s
        on, vol = s.sound_settings()
        fx = s.Sfx(True, vol)
        fx.play("apply")
        time.sleep(0.9)
        say(f"  click sounds {'on' if on else 'OFF (General > Sounds)'}, volume {vol}%, file {fx.path('apply')}")
        say("  OK    played the done chime - if you heard nothing, raise the volume of 'Python' in the Windows volume mixer"
            if not fx.last_error else f"  FAIL  {fx.last_error}")
    except Exception:
        say(f"  FAIL  {traceback.format_exc().strip().splitlines()[-1]}")
    say()
    if not logs_on():
        say("(diagnostic logs are OFF, so there is no start log. Turn them on in ShellFlow > Backup > Log files, or put YASB_LOGS=1 in the .env, and try again.)")
    for title, path, n in (("shellflow_start.log", _STARTLOG, 14), ("theme_error.log", LOG, 12), ("settings_hang.log", HERE / "settings_hang.log", 12), ("theme_watch.log", HERE / "theme_watch.log", 6)):
        try:
            tail = open(path, encoding="utf-8", errors="ignore").read().splitlines()[-n:]
            say(f"--- {title} (last {len(tail)} lines)")
            out.extend(tail)
            print("\n".join(tail))
        except OSError:
            say(f"--- {title}: none")
    try:
        (HERE / "shellflow_doctor.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
        say(f"\nSaved to {HERE / 'shellflow_doctor.txt'} - send me that file if ShellFlow still does not open.")
    except OSError:
        pass


def show_error():
    """A message box with the error, for the windows you open yourself (pythonw has no console)."""
    try:
        if EARLY_ROOT is not None:
            EARLY_ROOT.destroy()  # the "starting" window must not hide the message
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)  # a message box behind other windows would look like a hang
        last = traceback.format_exc().strip().splitlines()[-1]
        messagebox.showerror("ShellFlow", f"Something went wrong:\n\n{last}\n\nThe details are in:\n{LOG}\n{_STARTLOG}", parent=root)
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("theme.py")
        if sys.argv[1:2] in (["menu"], ["settings"]):
            show_error()
        raise
