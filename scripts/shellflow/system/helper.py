"""The background helper (theme.py watch): keeps the app themes in step with the wallpaper, plays the bar sounds, starts with Windows."""
import os
import subprocess
import time
import traceback
from ..colors import accent_shades, apply, current_variant, custom_colours, menu_items, windows_accent_seed
from ..core import CLEAN_ENV_DROP, DATA, LAUNCHER, NO_WINDOW, env, log, mtime, proc_start, pythonw, watch_log, where
from .sounds import BarSounds, Sfx, sound_settings
from .winapi import wallpaper_path

# ============================================================================================
#  8b. KEEPING THE APPS IN SYNC  (theme.py watch)
#  Runs in the background. When the wallpaper or the accent changes it re-applies the scheme you use (the
#  wallpaper is its seed) and rewrites the app themes, so Discord, Zed and the rest follow without you
#  opening anything. One copy runs at a time (theme_watch.pid); ShellFlow can start it with Windows.
# ============================================================================================
PIDFILE = DATA / "theme_watch.pid"


HELPER_VERSION = 6  # 6 = sound styles, 5 = the wooden sounds,  1 = app sync only, 2 = also sounds on the YASB bar, 3 = reads its settings from the .env, 4 = pitch variation (an older helper is restarted by start_watcher)


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


RUN_NAME = "ShellFlowSync"


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


def start_watcher():
    """Start the background helper now. One that is already running stays; an older version of it is restarted."""
    if watcher_running():
        if watcher_version() == HELPER_VERSION:
            return True
        stop_watcher()
        time.sleep(0.4)
    extra = {"creationflags": NO_WINDOW | 0x00000008} if os.name == "nt" else {}
    env = {k: v for k, v in os.environ.items() if k not in CLEAN_ENV_DROP}
    subprocess.Popen([pythonw(), str(LAUNCHER), "watch"], stdin=subprocess.DEVNULL, env=env,
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
    return f'"{pythonw()}" "{LAUNCHER}" watch'


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
