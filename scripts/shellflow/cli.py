"""The command line: theme.py <command>."""
import sys
import traceback
from .colors import apply, palette
from .core import LOG, _STARTLOG
from .system.doctor import doctor
from .system.helper import HELPER_VERSION, helper_wanted, start_watcher, watch, watcher_running, watcher_version
from .system.install import install_menu, setup
from .system.picker import show_picker
from .themes import write_apps
from .themes.windhawk import wh_apply_pending, wh_restore, wh_setup_task, write_windhawk

def _early_root():
    """The hidden Tk root (with the "starting" window) that the launcher made."""
    return getattr(sys.modules.get("__main__"), "EARLY_ROOT", None)


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
        from .settings import main as settings_main
        settings_main()
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


def show_error():
    """A message box with the error, for the windows you open yourself (pythonw has no console)."""
    try:
        if _early_root() is not None:
            _early_root().destroy()  # the "starting" window must not hide the message
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
