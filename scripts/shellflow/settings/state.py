"""Window state, .env writing, small shared helpers."""
import json
import re
import time
from .. import api as th
from .constants import EDITS_JSON, ENV, UI_STATE

COLLAPSE_BY_DEFAULT = True            # sections you have not opened or closed yourself: first one open, the rest closed


def load_ui_state():
    try:
        return dict(json.loads(UI_STATE.read_text(encoding="utf-8")).get("open", {}))
    except (OSError, ValueError, AttributeError):
        return {}


def save_ui_state(open_sections):
    try:
        UI_STATE.write_text(json.dumps({"open": open_sections}, indent=2), encoding="utf-8")
    except OSError:
        pass


def section_name(text):
    """A section's stable name: its heading without the changing part ("Left   -   3 of 3 on" -> "Left")."""
    return re.split(r"\s+-\s+", text)[0].strip()


_TASK = {"at": 0.0, "value": False}


def wh_task_cached(force=False):
    """Does Windhawk's scheduled task exist? Asking Windows takes a moment, so the answer is kept for 30 seconds."""
    if force or time.time() - _TASK["at"] > 30:
        _TASK["value"], _TASK["at"] = th.wh_task_exists(), time.time()
    return _TASK["value"]


def say(message):
    """A progress line. Visible when run with python.exe from a terminal (pythonw has no console)."""
    print(message, flush=True)


# ============================================================================================
#  1. .ENV
# ============================================================================================
def env_set(key, value):
    """Set KEY=value in the .env (every other line, comments included, is kept)."""
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    for i, line in enumerate(lines):
        if re.match(rf"^\s*{re.escape(key)}\s*=", line):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def env_unset(key):
    """Remove KEY from the .env (the default is used again)."""
    if ENV.exists():
        keep = [l for l in ENV.read_text(encoding="utf-8").splitlines() if not re.match(rf"^\s*{re.escape(key)}\s*=", l)]
        ENV.write_text("\n".join(keep) + "\n", encoding="utf-8")


def load_edits():
    try:
        return json.loads(EDITS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
