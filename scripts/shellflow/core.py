"""Paths, the .env, logging and small file helpers. Standard library only (the "starting" window needs it before anything heavy loads)."""
import ctypes
import hashlib
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

PKG = Path(__file__).resolve().parent      # .../scripts/shellflow
HERE = PKG.parent                            # .../scripts (theme.py, the launcher, is here)
CONFIG = HERE.parent if HERE.name.lower() == "scripts" else HERE  # the folder with styles.css
DATA = HERE / "data"                         # what ShellFlow remembers while it runs: settings, state, caches
LOGS = HERE / "logs"                         # every log and the doctor report
THEMES = CONFIG / "themes"                   # what ShellFlow writes for the bar and the apps: theme_colors.css, the Helium theme
for _d in (DATA, LOGS, THEMES):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
LAUNCHER = HERE / "theme.py"                 # what YASB, the autostart entry and the scheduled task run
OUT = THEMES / "theme_colors.css"           # imported by styles.css (YASB itself writes yasb_colors.css next to styles.css)
LOG = LOGS / "theme_error.log"
_T0 = time.time()
_STARTLOG = str(LOGS / "shellflow_start.log")
APP_VARS = set()                             # the folder variables of the app themes (filled in by themes/__init__)


def reset_logs_cache():
    """Read YASB_LOGS from the .env again."""
    global _LOGS
    _LOGS = None


def migrate_data():
    """Files an older ShellFlow put in other places move to where they belong now (once): state to data/, logs to logs/, the colour file and
    the Helium theme to themes/ (and styles.css imports the colour file from there)."""
    def move(old, new):
        if old.exists() and not new.exists():
            try:
                new.parent.mkdir(parents=True, exist_ok=True)
                old.rename(new)
            except OSError:
                pass
    for name in ("settings.json", "ui_state.json", "windhawk_state.json", "windhawk_pending.json", "theme_watch.pid", "shellflow.pid", ".thumbs"):
        move(HERE / name, DATA / name.lstrip("."))
    for name in ("theme_error.log", "theme_watch.log", "shellflow_start.log", "settings_hang.log", "shellflow_doctor.txt"):
        move(HERE / name, LOGS / name)
        move(DATA / name, LOGS / name)
    move(CONFIG / "theme_colors.css", OUT)
    move(CONFIG / "helium-theme", THEMES / "helium")
    if not OUT.exists():
        try:
            OUT.write_text("/* Windows accent in use - no override */\n", encoding="utf-8")
        except OSError:
            pass
    css = CONFIG / "styles.css"
    try:
        text = css.read_bytes().decode("utf-8")  # as bytes: the line endings of your file stay as they are
        new = re.sub(r'(@import\s+["\'])theme_colors\.css', r'\1themes/theme_colors.css', text)
        if new != text:
            css.write_bytes(new.encode("utf-8"))
    except OSError:
        pass
    old = HERE / "settings.py"  # the old single-file settings window: it is the settings/ folder now
    try:
        if old.exists() and "ShellFlow" in old.read_text(encoding="utf-8", errors="ignore")[:400]:
            old.unlink()
    except OSError:
        pass


CLEAN_ENV_DROP = ("PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY")  # not passed on to helpers we start


_LOGS = None


def logs_on():
    """The diagnostic logs (start, helper, hang) are written only when the .env has YASB_LOGS=1 (ShellFlow > Backup > Log files).
    Read once per process; set th.reset_logs_cache() to read it again. Errors still go to theme_error.log either way."""
    global _LOGS
    if _LOGS is None:
        _LOGS = False
        conf = str(CONFIG)
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


def _mix(a, b, t):
    """Blend two #rrggbb colours (t = 0 gives a)."""
    pa, pb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x * (1 - t) + y * t) for x, y in zip(pa, pb))


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
LIVE_KEYS = {"YASB_SOUND_SET", "YASB_FILEPILOT_EXE", "YASB_HELIUM_AUTORESTART", "YASB_HELIUM_EXE", "YASB_HELIUM_TAB", "YASB_SOUND_VARY", "YASB_WINDHAWK_ACTIVE", "YASB_WINDHAWK_MATCH", "YASB_ATTACH", "YASB_ATTACH_ALIGN", "YASB_MOTION", "YASB_LOGS", "YASB_SOUNDS", "YASB_SOUND_VOLUME", "YASB_BAR_SOUNDS", "YASB_SYNC", "YASB_APPS", "YASB_USERNAME", "YASB_PFP", "YASB_SPLASH"}


def env(name):
    """A setting. Normally the environment variable, else the same key in the .env next to styles.css; the settings ShellFlow
    writes itself (LIVE_KEYS and the app folders) come from the .env only, so a change you make is the change that is used."""
    live = name in LIVE_KEYS or name in APP_VARS
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
        folder = THEMES / "helium"
        return [(local / "imput" / "Helium", folder), (local / "Google" / "Chrome", folder), (local / "BraveSoftware", folder),
                (local / "Vivaldi", folder), (local / "Microsoft" / "Edge", folder)], ""
    raise KeyError(key)


def save(dirs, name, text):
    """Write one file into every folder."""
    for d in dirs:
        write_if_changed(d / name, text)


def log(what):
    """Add the current exception to theme_error.log."""
    try:
        if LOG.exists() and LOG.stat().st_size > 20000:  # it never grows without limit: keep the newest part
            LOG.write_text(LOG.read_text(encoding="utf-8", errors="ignore")[-10000:], encoding="utf-8")
    except OSError:
        pass
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{what}:\n{traceback.format_exc()}\n")


WATCH_LOG = LOGS / "theme_watch.log"


NO_WINDOW = 0x08000000


def mtime(path):
    try:
        return int(Path(path).stat().st_mtime_ns)
    except OSError:
        return 0


def watch_log(text):
    if env("YASB_LOGS") != "1":
        return
    try:
        lines = WATCH_LOG.read_text(encoding="utf-8").splitlines()[-60:] if WATCH_LOG.exists() else []
        WATCH_LOG.write_text("\n".join(lines + [time.strftime("%Y-%m-%d %H:%M:%S ") + text]) + "\n", encoding="utf-8")
    except OSError:
        pass


def pythonw():
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)
