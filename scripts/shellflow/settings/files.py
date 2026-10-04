"""The config files listed on the Files page."""
import os
import subprocess
from .. import api as th
from .keybinds import whkdrc_path
from .komorebi import komorebi_dir

def config_files():
    """{category: [paths]}: YASB's own files, its scripts, komorebi's and whkd's."""
    root = th.CONFIG
    yasb = [p for p in sorted(root.iterdir()) if p.is_file() and p.suffix != ".bak"] if root.is_dir() else []
    mine = [th.LAUNCHER] + [p for d in (th.DATA, th.LOGS) if d.is_dir() for p in sorted(d.iterdir()) if p.is_file() and p.suffix in (".json", ".txt", ".log")]
    themes = [p for p in sorted(th.THEMES.iterdir()) if p.is_file()] if th.THEMES.is_dir() else []
    mine += themes
    kom = komorebi_dir()
    komorebi = sorted({p for pat in ("komorebi*", "applications*") for p in kom.glob(pat) if p.is_file()}) if kom.is_dir() else []
    whkd = whkdrc_path()
    return {"YASB": yasb, "Scripts": mine, "komorebi": komorebi, "whkd": [whkd] if whkd.is_file() else []}


def open_file(path):
    """Open a file in your editor (YASB_EDITOR), else the default editor, else Notepad."""
    editor = th.env("YASB_EDITOR")
    if editor:
        return subprocess.Popen([editor, str(path)])
    for verbs in (("edit",), ()):
        try:
            return os.startfile(str(path), *verbs)
        except (OSError, AttributeError):
            pass
    subprocess.Popen(["notepad", str(path)])
