"""komorebi.json, monitors and running commands."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from .. import api as th
from .constants import CREATE_NO_WINDOW

# ============================================================================================
#  4. KOMOREBI, MONITORS, FILES AND VERSIONS
# ============================================================================================
def komorebi_dir():
    return Path(th.env("KOMOREBI_CONFIG_HOME") or Path.home())


def load_komorebi():
    """komorebi.json as a dict, or None (missing, or not plain JSON)."""
    try:
        return json.loads((komorebi_dir() / "komorebi.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_komorebi(data):
    (komorebi_dir() / "komorebi.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_quiet(args, timeout=6):
    try:
        flags = {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, **flags)
        return (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return ""


def reload_komorebi():
    run_quiet(["komorebic", "reload-configuration"])


def yasbc():
    exe = th.env("YASB_CLI") or shutil.which("yasbc") or str(th.where("PROGRAMFILES") / "YASB" / "yasbc.exe")
    return exe if Path(exe).exists() or shutil.which(exe) else None


def list_monitors():
    """The monitor names YASB uses in `screens:` (from `yasbc monitor-information`)."""
    exe = yasbc()
    text = run_quiet([exe, "monitor-information"]) if exe else ""
    return list(dict.fromkeys(m.strip() for m in re.findall(r"Name:\s*(.+?)(?=\s+Resolution:|\r?\n|$)", text)))
