"""The Home menu entry that opens ShellFlow, and the one-command setup."""
import re
import traceback
from pathlib import Path
from ..core import CONFIG, LAUNCHER, pythonw, write_if_changed
from .helper import apply_helper_settings, helper_status

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


HOME_ENTRY = re.compile(r'^(\s*)- \{ title: "(?:Settings|ShellFlow)"[^\n]*$', re.M)


def menu_entry():
    """The Home menu line that opens ShellFlow: this Python and this script, written out in full (no variables)."""
    py = pythonw().replace("\\", "/")
    script = str(LAUNCHER).replace("\\", "/")
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
