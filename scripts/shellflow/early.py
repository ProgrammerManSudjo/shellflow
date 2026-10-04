"""The first moments of `theme.py settings`: one ShellFlow at a time, and the "ShellFlow is starting" window. Standard library only."""
import ctypes
import os
import re
import subprocess
import sys
import time
from .core import CONFIG, DATA, _mix, proc_start, start_log

# YASB is a bundled app. A program it starts can inherit its Tcl/Tk folders, and Tk then fails to start with no window and no message.
# These two variables are dropped when they point outside this Python's own folder.
for _v, _f in (("TCL_LIBRARY", "init.tcl"), ("TK_LIBRARY", "tk.tcl")):
    _p = os.environ.get(_v)
    if _p and not os.path.abspath(_p).lower().startswith(os.path.abspath(sys.base_prefix).lower()):
        os.environ.pop(_v, None)
_PIDFILE = str(DATA / "shellflow.pid")


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
    conf = str(CONFIG)
    shades = {}
    for name in ("yasb_colors.css", os.path.join("themes", "theme_colors.css")):  # the applied scheme wins over the Windows accent
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


def run():
    if sys.argv[1:2] != ["settings"]:
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
