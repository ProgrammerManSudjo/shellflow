"""whkdrc: parsing, describing and editing keybinds."""
import os
import re
import subprocess
from pathlib import Path
from .. import api as th
from .constants import CREATE_NO_WINDOW
from .komorebi import run_quiet

# ============================================================================================
#  WHKD KEYBINDS  (whkdrc: `alt + h : komorebic focus left`)
# ============================================================================================
MODIFIERS = ("alt", "ctrl", "shift", "win")


KEY_ALIASES = {"control": "ctrl", "cmd": "win", "super": "win", "windows": "win", "lalt": "alt", "ralt": "alt", "lctrl": "ctrl", "rctrl": "ctrl",
               "lshift": "shift", "rshift": "shift", "lwin": "win", "rwin": "win", "enter": "return", "esc": "escape", "del": "delete", "ins": "insert",
               "pgup": "prior", "pgdn": "next", "pageup": "prior", "pagedown": "next"}


# what Tk calls a key -> what whkd calls it (letters and digits are the same in both)
TK_KEYS = {"Control_L": "ctrl", "Control_R": "ctrl", "Alt_L": "alt", "Alt_R": "alt", "Shift_L": "shift", "Shift_R": "shift", "Super_L": "win", "Super_R": "win",
           "Win_L": "win", "Win_R": "win", "Meta_L": "win", "Meta_R": "win", "Left": "left", "Right": "right", "Up": "up", "Down": "down", "space": "space",
           "Return": "return", "Escape": "escape", "Tab": "tab", "BackSpace": "backspace", "Delete": "delete", "Insert": "insert", "Home": "home", "End": "end",
           "Prior": "prior", "Next": "next", "minus": "oem_minus", "equal": "oem_plus", "plus": "oem_plus", "comma": "oem_comma", "period": "oem_period",
           "semicolon": "oem_1", "slash": "oem_2", "grave": "oem_3", "bracketleft": "oem_4", "backslash": "oem_5", "bracketright": "oem_6", "apostrophe": "oem_7"}


def whkdrc_path():
    return Path(th.env("WHKD_CONFIG_HOME") or Path.home() / ".config") / "whkdrc"


def norm_key(key):
    key = key.strip().lower()
    return KEY_ALIASES.get(key, key)


def tk_key(keysym):
    """A Tk key name (Alt_L, h, F5, Left ...) as whkd writes it (alt, h, f5, left ...). "" for a key that is not worth showing."""
    if keysym in TK_KEYS:
        return TK_KEYS[keysym]
    if re.fullmatch(r"[A-Za-z0-9]", keysym):
        return keysym.lower()
    if re.fullmatch(r"F\d{1,2}", keysym):
        return keysym.lower()
    return ""


def split_keys(keys_text):
    """"alt + shift + H" -> ["alt", "shift", "h"] (chords written with ; count too)."""
    return [norm_key(k) for k in re.split(r"\s*[+;]\s*", keys_text.strip()) if k.strip()]


def format_keys(keys):
    """Modifiers first (alt, ctrl, shift, win), then the other keys: ["h", "alt"] -> "alt + h"."""
    mods = [m for m in MODIFIERS if m in keys]
    return " + ".join(mods + [k for k in keys if k not in MODIFIERS])


def parse_whkdrc(text):
    """The keybinds of a whkdrc: [{"start", "end" (line range), "keys" (list), "keys_text", "cmd", "group"}]. Directives (.shell ...),
    comments and blank lines are not keybinds; a comment above a keybind names its group. A command can continue on the
    next line after a trailing backslash."""
    lines, out, group, i = text.split("\n"), [], "", 0
    while i < len(lines):
        raw = lines[i].rstrip("\r")
        s = raw.strip()
        if s.startswith("#"):
            text = re.sub(r"^[\s=\-*#~_/\\]+|[\s=\-*#~_/\\]+$", "", s)  # "# ===== FOCUS =====" -> "FOCUS"
            if re.search(r"[A-Za-z0-9]", text) and " : " not in text:  # not a divider line, not a keybind that is commented out
                group = text
            i += 1
            continue
        m = re.match(r"^(.+?)\s+:\s+(.*)$", raw) if s and not s.startswith(".") else None
        if m:
            cmd, end = m.group(2).strip(), i + 1
            while cmd.endswith("\\") and end < len(lines):
                cmd = cmd[:-1].rstrip() + " " + lines[end].strip()
                end += 1
            keys = split_keys(m.group(1))
            out.append({"start": i, "end": end, "keys": keys, "keys_text": format_keys(keys), "cmd": cmd, "group": group})
            i = end
        else:
            i += 1
    return out


NICE = {"toggle-float": "Toggle floating", "toggle-monocle": "Toggle monocle", "toggle-maximize": "Toggle maximize", "toggle-pause": "Pause tiling",
        "toggle-tiling": "Toggle tiling", "retile": "Retile", "reload-configuration": "Reload komorebi", "stop": "Stop komorebi", "start": "Start komorebi",
        "minimize": "Minimize window", "close": "Close window", "promote": "Promote window", "manage": "Manage window", "unmanage": "Unmanage window",
        "unstack": "Unstack window", "toggle-workspace-layer": "Toggle workspace layer", "toggle-window-container-behaviour": "Toggle window container behaviour"}


def describe_one(cmd):
    """One command in words: "komorebic focus left" -> "Focus left", "komorebic focus-workspace 0" -> "Go to workspace 1"."""
    cmd = cmd.strip().strip("&;").strip()
    m = re.match(r"^komorebic(?:\.exe)?\s+(\S+)\s*(.*)$", cmd, re.I)
    if m:
        verb, args = m.group(1).lower(), m.group(2).split()
        number = args[0] if args and args[0].isdigit() else None
        shown = str(int(number) + 1) if number is not None else ""  # komorebic counts from 0, the bar from 1
        by_number = {"focus-workspace": "Go to workspace", "send-to-workspace": "Send window to workspace", "move-to-workspace": "Move window to workspace",
                     "focus-monitor": "Focus monitor", "send-to-monitor": "Send window to monitor", "move-to-monitor": "Move window to monitor"}
        if verb in by_number and number is not None:
            return f"{by_number[verb]} {shown}"
        if verb in NICE:
            return NICE[verb]
        words = " ".join(args)
        if verb == "focus":
            return f"Focus {words}".strip()
        if verb == "move":
            return f"Move window {words}".strip()
        if verb == "stack":
            return f"Stack onto the window {words}".strip()
        if verb == "resize-axis":
            return f"Resize {args[0]} ({args[1]})" if len(args) > 1 else f"Resize {words}"
        if verb == "flip-layout":
            return f"Flip layout {words}".strip()
        if verb == "change-layout":
            return f"Layout: {words}".strip()
        return (verb.replace("-", " ").capitalize() + (" " + words if words else "")).strip()
    m = re.search(r"AppActivate\(['\"]([^'\"]+)['\"]\)", cmd)
    if m:
        return f"Open or focus {m.group(1)}"
    if re.search(r"taskkill.*whkd", cmd, re.I):
        return "Restart whkd"
    m = re.match(r"^(?:start\s+(?:/b\s+)?|Start-Process\s+)['\"]?([^\s'\";]+)", cmd, re.I)
    if m:
        return "Open " + Path(m.group(1)).stem
    first = re.match(r"^['\"]?([^\s'\"]+)", cmd)
    return ("Run " + Path(first.group(1)).stem) if first else cmd[:40]


def describe_command(cmd):
    """What a whkdrc command does, in words. Chained commands (&&, ;) are joined: "Toggle floating, Retile"."""
    if re.search(r"taskkill.*whkd", cmd, re.I):  # the usual "reload whkd" line stops it and starts it again: one thing
        return "Restart whkd"
    cmd = re.sub(r"\s+#.*$", "", cmd)  # a trailing comment is not part of the command
    parts = [describe_one(p) for p in re.split(r"\s*(?:&&|\|\||;)\s*", cmd) if p.strip()]
    title = ", ".join(dict.fromkeys(parts)) or cmd
    return title if len(title) <= 56 else title[:53].rstrip() + "..."


def replace_keybind(text, bind, keys_text, cmd):
    """The text with one keybind rewritten (all of its lines become one `keys : command` line)."""
    lines = text.split("\n")
    lines[bind["start"]:bind["end"]] = [f"{format_keys(split_keys(keys_text))} : {cmd.strip()}"]
    return "\n".join(lines)


def keybind_title(bind):
    """The title of a keybind in the list: what it does."""
    return describe_command(bind["cmd"])


def delete_keybind(text, bind):
    lines = text.split("\n")
    del lines[bind["start"]:bind["end"]]
    return "\n".join(lines)


def add_keybind(text, keys_text, cmd):
    """A new keybind at the end of the file."""
    return text.rstrip("\n") + f"\n{format_keys(split_keys(keys_text))} : {cmd.strip()}\n"


def restart_whkd():
    """whkd reads whkdrc when it starts. If it is running, stop it and start it again. Returns what happened."""
    if "whkd.exe" not in run_quiet(["tasklist", "/FI", "IMAGENAME eq whkd.exe", "/NH"]).lower():
        return "whkd is not running: it will use the new keybinds when it starts"
    run_quiet(["taskkill", "/F", "/IM", "whkd.exe"])
    env = dict(os.environ)
    if th.env("WHKD_CONFIG_HOME"):
        env["WHKD_CONFIG_HOME"] = th.env("WHKD_CONFIG_HOME")
    flags = {"creationflags": CREATE_NO_WINDOW | 0x00000008} if os.name == "nt" else {}
    try:
        subprocess.Popen(["whkd"], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **flags)
        return "whkd restarted with the new keybinds"
    except OSError:
        return "could not start whkd again (is it on your PATH?)"
