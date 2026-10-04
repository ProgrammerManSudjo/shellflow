"""ShellFlow, the settings window (open it with `pythonw theme.py settings`)."""
import os
import sys
import time
import traceback
import tkinter as tk
from .. import api as th
from .config_yaml import bar_edge
from .constants import APP_NAME, HANG_LOG, NATIVE, SPLASH_MIN, STARTUP_TIMEOUT
from .motion import fade
from .state import say
from .window import dark_titlebar, to_front

def start_log(text):
    """One line in shellflow_start.log with the seconds since the process began (see theme.py, section 0)."""
    fn = getattr(sys.modules.get("__main__"), "start_log", None)
    if fn is None or fn is start_log:  # (settings.py run on its own: use theme.py's)
        fn = th.start_log
    fn(text)


def main():
    try:
        _main()
    except Exception:
        start_log("FAILED: " + traceback.format_exc().strip().splitlines()[-1])
        raise


def _main():
    holder = {}
    start_log(f"settings.py loaded; YASB_THEME_SCRIPT is {'set' if os.environ.get('YASB_THEME_SCRIPT') else 'not set'}")
    import faulthandler
    watchdog = None
    if th.logs_on():  # a start that hangs leaves a trace in settings_hang.log (only with logs on)
        watchdog = open(HANG_LOG, "w", encoding="utf-8")
        faulthandler.dump_traceback_later(STARTUP_TIMEOUT, file=watchdog)
    say(f"Opening {APP_NAME}...")
    try:
        __import__("ctypes").windll.shcore.SetProcessDpiAwareness(2)  # sharp on scaled displays
    except Exception:
        pass
    early = getattr(sys.modules.get("__main__"), "EARLY_ROOT", None)  # theme.py's hidden root, with the "starting" window
    root = early if early is not None else tk.Tk()
    root.update()  # lets the starting window's light run before the (busy) building of the window starts
    splash = getattr(root, "splash", None)
    root.withdraw()  # the real window stays hidden until it is built AND the splash has been up long enough
    if NATIVE:
        dark_titlebar(root)
    holder["app"] = App(root)
    start_log("window built")
    root.update()
    if watchdog:
        faulthandler.cancel_dump_traceback_later()  # built: nothing can be "stuck while opening" any more
        watchdog.close()
        HANG_LOG.unlink(missing_ok=True)
    try:
        minimum = float(th.env("YASB_SPLASH") or SPLASH_MIN)
    except ValueError:
        minimum = SPLASH_MIN
    began = getattr(sys.modules.get("__main__"), "_T0", time.time())
    wait_ms = int(max(0.0, minimum - (time.time() - began)) * 1000) if splash is not None else 0

    def reveal():
        root.attributes("-alpha", 0.0)  # starts invisible and fades in while the splash fades out
        win = holder["app"]
        to_front(root, win.attach_state(), bar_edge(win.cfg_text())[1], win.W, win.x0, win.y0, win.dy)
        root.update()
        if not NATIVE and not win.attach_state()[0]:
            th.round_window(root)  # Windows 11 rounded corners (an attached window is shaped by its own ring)
        fade(root, 0.0, 1.0, 220)
        if splash is not None:
            fade(splash, 1.0, 0.0, 220, done=splash.destroy)

        def solid():  # failsafe: the window can never stay see-through
            try:
                root.attributes("-alpha", 1.0)
            except tk.TclError:
                pass  # closed already
        root.after(900, solid)
        start_log("opened")
        root.after(1200, holder["app"].ensure_visible)  # (ignores a window that is already closed)
        holder["app"].born = time.time()
        holder["app"].watch()
        holder["app"].ensure_sync()
        say(f"{APP_NAME} is open. Close it to return to the prompt.")
    if wait_ms:
        start_log("built; keeping the splash up for %.1fs more" % (wait_ms / 1000))
        root.after(wait_ms, reveal)
    else:
        reveal()
    root.mainloop()


from .app import App  # noqa: E402,F401
from .constants import PAGES  # noqa: E402,F401
from ..system.sounds import Sfx, sound_settings  # noqa: E402,F401
