"""ShellFlow launcher: what YASB's Home menu, the start-with-Windows entry and the Windhawk scheduled task run (pythonw theme.py <command>).

USAGE
  pythonw theme.py menu      open the scheme picker
  pythonw theme.py <name>    apply a scheme: windows, content, fidelity, tonal_spot, monochrome, expressive, neutral, vibrant, fruit_salad, custom
  pythonw theme.py apps      refresh the app themes only
  pythonw theme.py settings  open ShellFlow, the settings window
  pythonw theme.py watch     keep the app themes in sync when the wallpaper or the accent changes (the background helper)
  python  theme.py doctor    check why ShellFlow will not open and write logs/shellflow_doctor.txt (run it from a terminal)
  python  theme.py install-menu   (re)write the Home menu entry that opens ShellFlow, with full paths
  python  theme.py setup     do everything once: the Home menu entry, and the background helper
  python  theme.py windhawk  recolour the Windhawk styler mods with the current scheme

The program itself is the folder next to this file (shellflow/); what it remembers is in data/, its logs in logs/. Errors are written to
logs/theme_error.log (pythonw hides them).
"""
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.simplefilter("ignore")

# 1. standard library only: one copy at a time, and the "ShellFlow is starting" window at once
from shellflow import early  # noqa: E402
EARLY_ROOT = early.run()  # the settings window reads EARLY_ROOT, _T0 and start_log from this module

from shellflow.core import _T0, log, migrate_data, start_log  # noqa: E402,F401
migrate_data()  # files an older ShellFlow kept in this folder move to data/

# 2. the heavy part
try:
    from shellflow import cli  # noqa: E402
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

if __name__ == "__main__":
    try:
        cli.main()
    except Exception:
        log("theme.py")
        if sys.argv[1:2] in (["menu"], ["settings"]):
            cli.show_error()
        raise
