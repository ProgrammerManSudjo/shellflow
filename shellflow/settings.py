"""ShellFlow - the settings window for the YASB setup (open it with `pythonw theme.py settings`).

PAGES
  General    your name and profile picture, quick actions
  Colors     the colour scheme (the same grid as the picker)
  Widgets    where each widget sits on a bar (left / centre / right), order, and on or off
  Bar        widget spacing, capsule size, workspaces, auto hide and animation
  Templates  which apps get a theme, and the folder each one goes in
  Edits      your own font faces and colours
  Files      every YASB, komorebi and whkd file, with an Edit button
  Backup     back up, restore and delete your setup when YOU press it; the log files
  About      versions and system information
  Display    where the bar sits (monitor, top or bottom, opacity) and komorebi's settings

WHAT IT WRITES
  .env             next to styles.css (apps, folders, name, picture)
  config.yaml      widgets and bar options. A widget you switch off is commented out, never deleted,
                   so switching it on again puts it back in the same place.
  styles.css       one generated block at the very end (fonts, colours, spacing, bar opacity)
  komorebi.json    komorebi's settings (komorebic reload-configuration runs afterwards)
Nothing that makes YASB or komorebi reload is written until you press Apply (bottom right); Reset throws the
unapplied changes away. One Apply = one reload. (YASB has no way to swap a single widget without a reload.)
The .env settings (apps, folders, profile) are saved at once; they reload nothing.

Optional settings (environment or .env): YASB_EDITOR (editor for the Edit buttons), YASB_PFP and
YASB_USERNAME (profile), YASB_CLI (path to yasbc.exe), YASB_SETTINGS_TITLEBAR=native (normal title bar).
YASB_SPLASH (seconds the "starting" window stays up at least; default 1.5, 0 = no extra wait).
"""
import array
import hashlib
import io
import json
import math
import os
import platform
import queue
import threading
import time
import traceback
import wave
import zipfile
import re
import shutil
import subprocess
import sys
import tkinter as tk
from functools import lru_cache
from pathlib import Path
from tkinter import filedialog, font as tkfont

from PIL import Image, ImageDraw, ImageOps, ImageTk

import theme as th

if not hasattr(th, "defaults"):  # theme.py next to this file is an older version
    raise RuntimeError("theme.py is out of date - copy the new theme.py next to settings.py")

APP_NAME = "ShellFlow"
W, H = 1150, 790                   # window size
MARGIN = 15                        # the accent border sits this far inside the window edge
BORDER = 2                         # thickness of that border
RING_R = 30                        # its corner radius
GAP = 10                           # space between the panels, and between them and the border
EDGE = MARGIN + BORDER + GAP       # where the panels start
SIDE_FULL, SIDE_COMPACT = 252, 76  # sidebar width: with labels, icons only
HEAD = 76                          # height of the panel header (title, close button)
FOOT = 64                          # height of the footer (Reset, Apply)
PADX = 28                          # space left and right of the page content
CONFIG_YAML = th.CONFIG / "config.yaml"
STYLES = th.CONFIG / "styles.css"
ENV = th.CONFIG / ".env"
EDITS_JSON = th.HERE / "settings.json"
HANG_LOG = th.HERE / "settings_hang.log"  # only exists if the last start got stuck
SPLASH_MIN = 0.35                         # seconds the "starting" window stays up at least (YASB_SPLASH=0 turns the wait off)
STARTUP_TIMEOUT = 12                      # seconds before a stuck start is written to HANG_LOG
NATIVE = th.env("YASB_SETTINGS_TITLEBAR").lower() == "native"
CREATE_NO_WINDOW = 0x08000000
ZONES = ("left", "center", "right")


# ============================================================================================
#  SOUNDS  (soft Pixel-style UI sounds, synthesised here: no audio files)
# ============================================================================================
Sfx = th.Sfx  # the sound engine lives in theme.py: the background helper plays the YASB bar clicks with it too



sound_settings = th.sound_settings


HOVER_SCALE, PRESS_SCALE = 1.05, 0.93  # how big a control is under the mouse, and while it is pressed


def spring(t):
    """0..1 -> a value that overshoots by about 13% and settles: the springy "spatial" motion of Material 3 expressive."""
    return 1.0 if t >= 1 else 1 - math.exp(-6.2 * t) * math.cos(9.5 * t)


def soft(t):
    """0..1 -> a gentler spring (overshoot about 3%), for things that should not swing far."""
    return 1.0 if t >= 1 else 1 - math.exp(-7.0 * t) * math.cos(6.0 * t)


def animate(widget, ms, step, done=None):
    """Call step(t) with t going 0 -> 1 over `ms` milliseconds (it follows the clock, so a slow frame does not make it longer).
    Returns a function that stops it. The caller applies spring() or soft() to t."""
    t0, state = time.time(), {"on": True, "job": None}

    def tick():
        if not state["on"]:
            return
        t = min(1.0, (time.time() - t0) * 1000 / ms)
        try:
            step(t)
            if t < 1.0:
                state["job"] = widget.after(14, tick)
            elif done:
                done()
        except tk.TclError:
            state["on"] = False  # the page was redrawn under it
    tick()

    def stop():
        state["on"] = False
        if state["job"]:
            try:
                widget.after_cancel(state["job"])
            except tk.TclError:
                pass
    return stop


def fade(root, start, end, ms=180, done=None):
    """Fade the whole window from alpha `start` to `end` (0..1), then call done(). done() runs even if the fade
    itself fails, so closing can never leave an invisible window behind."""
    steps = max(1, ms // 15)

    def finish():
        if done:
            try:
                done()
            except tk.TclError:
                pass  # already destroyed

    def tick(i=0):
        try:
            root.attributes("-alpha", start + (end - start) * i / steps)
        except tk.TclError:
            return finish()
        if i < steps:
            try:
                root.after(15, lambda: tick(i + 1))
            except tk.TclError:
                return
        else:
            finish()
    tick()


UI_STATE = th.HERE / "ui_state.json"  # which sections are open (window state only: nothing here reloads YASB)
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


# ============================================================================================
#  2. config.yaml  (text edits: comments and layout of the rest of the file are never touched)
# ============================================================================================
def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _content(line):
    s = line.strip()
    return bool(s) and not s.startswith("#")


def find_key(lines, path):
    """Index of the line `key:` at the end of `path` (["bars", "status-bar", "screens"]), or None."""
    lo, hi, parent, found = 0, len(lines), -1, None
    for key in path:
        child, found = None, None
        for i in range(lo, hi):
            if not _content(lines[i]):
                continue
            ind = _indent(lines[i])
            if ind <= parent:
                break
            child = ind if child is None else child
            if ind < child:
                break
            if ind == child and re.match(rf"\s*{re.escape(key)}\s*:", lines[i]):
                found = i
                break
        if found is None:
            return None
        parent, lo = _indent(lines[found]), found + 1
        hi = next((j for j in range(lo, len(lines)) if _content(lines[j]) and _indent(lines[j]) <= parent), len(lines))
    return found


def parse_scalar(raw):
    raw = re.sub(r"\s+#.*$", "", raw.strip())
    if raw in ("true", "True"):
        return True
    if raw in ("false", "False"):
        return False
    if raw in ("", "null", "None", "~"):
        return None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw[1:-1] if len(raw) > 1 and raw[0] == raw[-1] and raw[0] in "\"'" else raw


def yaml_get(text, path, default=None):
    """The value of a plain `key: value` line, or `default` when it is not there."""
    lines = text.split("\n")
    i = find_key(lines, path)
    if i is None:
        return default
    value = parse_scalar(lines[i].split(":", 1)[1])
    return default if value is None else value


def yaml_fmt(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return '"%s"' % str(value).replace('"', '\\"')


def yaml_set(text, path, value):
    """Set a plain `key: value` line (its trailing comment stays). A missing key is added at the end of its
    parent block. Anything that is not a plain value, or has no parent, is left alone."""
    lines = text.split("\n")
    i = find_key(lines, path)
    if i is not None:
        head, rest = lines[i].split(":", 1)
        if not rest.strip() or rest.strip().startswith(("[", "{")):
            return text
        comment = re.search(r"(\s+#.*)$", rest)
        lines[i] = f"{head}: {yaml_fmt(value)}{comment.group(1) if comment else ''}"
        return "\n".join(lines)
    p = find_key(lines, path[:-1]) if len(path) > 1 else None
    if p is None:
        return text
    end = next((j for j in range(p + 1, len(lines)) if _content(lines[j]) and _indent(lines[j]) <= _indent(lines[p])), len(lines))
    while end > p + 1 and not _content(lines[end - 1]):
        end -= 1
    child = next((_indent(lines[j]) for j in range(p + 1, end) if _content(lines[j])), _indent(lines[p]) + 2)
    lines.insert(end, " " * child + f"{path[-1]}: {yaml_fmt(value)}")
    return "\n".join(lines)


def bar_names(text):
    """The bars in config.yaml, in order."""
    lines, names, in_bars = text.split("\n"), [], False
    for line in lines:
        if not _content(line):
            continue
        if _indent(line) == 0:
            in_bars = line.startswith("bars:")
        elif in_bars and _indent(line) == 2 and re.match(r"^  ([\w.-]+):\s*$", line):
            names.append(line.strip()[:-1])
    return names


def read_widgets(text):
    """{widget: type} from the top-level `widgets:` part of config.yaml."""
    out, inside, name = {}, False, None
    for line in text.split("\n"):
        if not _content(line):
            continue
        if _indent(line) == 0:
            inside, name = line.startswith("widgets:"), None
            continue
        m = inside and re.match(r"^  ([\w.-]+):\s*$", line)
        if m:
            name = m.group(1)
            out[name] = ""
        elif inside and name and not out[name]:
            m = re.match(r"^    type:\s*[\"']?([\w.]+)", line)
            if m:
                out[name] = m.group(1)
    return out


# The notes popup's icons: plain copy, trash, close, and a window maximize / restore pair for floating.
NOTES_ICONS = ("  icons:", '    note: "\\udb82\\udd0c"', '    delete: "\\uf1f8"', '    copy: "\\uf0c5"', '    float_on: "\\uf2d0"',
               '    float_off: "\\uf2d2"', '    close: "\\uf00d"')

# Widgets that can be added from the Widgets page even when config.yaml does not define them yet.
# (key, title, description, icon, YASB type, bar class, popup class, the definition (YAML under the widget name))
CATALOG = (
    ("whkd", "Hotkeys (whkd)", "A keyboard button that opens your whkd shortcut list", "keyboard", "yasb.whkd.WhkdWidget",
     ".whkd-widget", ".whkd-popup",
     ['type: "yasb.whkd.WhkdWidget"', "options:", '  label: "<span>\\uf11c</span>"']),
    ("notes", "Notes", "A button that opens a notes scratchpad (no note count)", "file_text", "yasb.notes.NotesWidget",
     ".notes-widget", ".notes-menu",
     ['type: "yasb.notes.NotesWidget"', "options:", '  label: "<span>\\udb82\\udd0c</span>"', '  label_alt: "<span>\\udb82\\udd0c</span>"',
      "  menu:", "    blur: false", "    round_corners: true", '    round_corners_type: "normal"', '    border_color: "None"',
      '    alignment: "right"', '    direction: "down"', "    offset_top: 0", "    offset_left: 0",
      *NOTES_ICONS,
      "  callbacks:", '    on_left: "toggle_menu"', '    on_middle: "do_nothing"', '    on_right: "do_nothing"']),
    ("control_center", "Control Center", "A button that opens quick settings: volume, brightness, power plan, media", "sliders",
     "yasb.control_center.ControlCenterWidget", ".control-center-widget", ".control-center-menu",
     ['type: "yasb.control_center.ControlCenterWidget"', "options:", '  label: "<span>\\uf1de</span>"', "  tooltip: false",
      "  popup:", "    blur: false", "    round_corners: true", '    round_corners_type: "normal"', '    border_color: "None"',
      '    alignment: "right"', '    direction: "down"', "    offset_top: 0",
      "  callbacks:", '    on_left: "toggle_menu"']),
    ("active_window", "Active window title", "The title of the window you are using, cut short, text only", "title",
     "yasb.active_window.ActiveWindowWidget", ".active-window-widget", None,
     ['type: "yasb.active_window.ActiveWindowWidget"', "options:", '  label: "{win[title]}"', '  label_alt: "{win[title]}"',
      '  label_no_window: ""', "  label_icon: false", "  label_icon_size: 16", "  max_length: 40", '  max_length_ellipsis: "..."',
      "  monitor_exclusive: true", "  callbacks:", '    on_left: "do_nothing"', '    on_middle: "do_nothing"', '    on_right: "do_nothing"']),
    ("cava", "Audio visualizer (Cava)", "Four thick bars that move with your music (needs cava installed)", "audio", "yasb.cava.CavaWidget",
     ".cava-widget", None,
     ['type: "yasb.cava.CavaWidget"', "options:", "  bars_number: 4", "  bar_width: 4", "  bar_spacing: 3", "  bar_height: 16",
      '  bar_type: "bars"', "  gradient: 0", '  foreground: "__COLOUR__"', "  framerate: 60"]),
)
CATALOG_BY_TYPE = {e[4]: e for e in CATALOG}
CATALOG_BY_KEY = {e[0]: e for e in CATALOG}


def catalog_lines(entry, colour="#ffffff"):
    return [l.replace("__COLOUR__", colour) for l in entry[7]]


def insert_widget_def(text, name, body):
    """Add `name: <body>` to the end of the top-level `widgets:` section of config.yaml."""
    lines = text.split("\n")
    block = [f"  {name}:"] + ["    " + l for l in body]
    w = next((i for i, l in enumerate(lines) if l.startswith("widgets:")), None)
    if w is None:
        return text.rstrip("\n") + "\n\nwidgets:\n" + "\n".join(block) + "\n"
    end = next((j for j in range(w + 1, len(lines)) if _content(lines[j]) and _indent(lines[j]) == 0), len(lines))
    last = max((j for j in range(w + 1, end) if _content(lines[j])), default=w)
    lines[last + 1:last + 1] = [""] + block
    return "\n".join(lines)


def define_catalog_widget(text, key, colour="#ffffff"):
    """Define a catalog widget in config.yaml if it is not defined yet (it is on no bar). Returns (text, name)."""
    entry = next(e for e in CATALOG if e[0] == key)
    types = read_widgets(text)
    name = next((n for n, t in types.items() if t == entry[4]), None)
    if name is None:
        name, i = key, 2
        while name in types:
            name, i = f"{key}_{i}", i + 1
        text = insert_widget_def(text, name, catalog_lines(entry, colour))
    return text, name


def add_catalog_widget(text, key, bar, zone, colour="#ffffff"):
    """Define a catalog widget (if needed) and put it on a bar. Returns (text, name)."""
    text, name = define_catalog_widget(text, key, colour)
    return toggle_widget(text, bar, name, True, zone), name


def zone_spans(lines, bar):
    """{zone: (start, end, indent)}: the lines of each widget list of a bar (end is exclusive).
    Both `left: ["a", "b"]` and the multi-line form (one item per line) are understood."""
    w = find_key(lines, ["bars", bar, "widgets"])
    if w is None:
        return {}
    base, spans, i = _indent(lines[w]), {}, w + 1
    while i < len(lines):
        if _content(lines[i]) and _indent(lines[i]) <= base:
            break
        m = re.match(r"^(\s+)(left|center|right):\s*(.*)$", lines[i])
        if m:
            rest = m.group(3).strip()
            if rest.startswith("[") and not re.search(r"\]\s*(#.*)?$", rest):
                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith("]"):
                    j += 1
                spans[m.group(2)] = (i, min(j + 1, len(lines)), len(m.group(1)))
                i = j
            elif rest.startswith("["):
                spans[m.group(2)] = (i, i + 1, len(m.group(1)))
        i += 1
    return spans


def zone_items(lines, span):
    """[(widget, enabled)] of one list. A commented-out line (# "name",) is a widget that is switched off."""
    start, end, _ = span
    if end - start == 1:
        inner = re.search(r"\[(.*)\]", lines[start]).group(1)
        return [(n, True) for n in re.findall(r"[\"']([^\"']+)[\"']", inner)]
    items = []
    for line in lines[start + 1:end]:
        m = re.match(r"^(#\s*)?[\"']([^\"']+)[\"']\s*,?\s*(#.*)?$", line.strip())
        if m:
            items.append((m.group(2), m.group(1) is None))
    return items


def zone_lines(indent, zone, items):
    pad = " " * indent
    return [f"{pad}{zone}: ["] + [f'{pad}  {"" if on else "# "}"{name}",' for name, on in items] + [f"{pad}]"]


def get_zones(text, bar):
    """{zone: [(widget, enabled), ...]} for one bar."""
    lines = text.split("\n")
    spans = zone_spans(lines, bar)
    return {z: zone_items(lines, spans[z]) for z in ZONES if z in spans}


def put_zones(text, bar, zones):
    """The text with the given zones of a bar rewritten (in the multi-line form, so items can be commented)."""
    lines = text.split("\n")
    spans = zone_spans(lines, bar)
    for z, (s, e, ind) in sorted(spans.items(), key=lambda kv: -kv[1][0]):
        if z in zones:
            lines[s:e] = zone_lines(ind, z, zones[z])
    missing = [z for z in zones if z not in spans]
    if missing and spans:  # a zone the bar did not have yet goes after the last one
        spans = zone_spans(lines, bar)
        at, ind = max(e for _, e, _ in spans.values()), next(iter(spans.values()))[2]
        for z in reversed(missing):
            lines[at:at] = zone_lines(ind, z, zones[z])
    return "\n".join(lines)


def usual_zone(text, widget):
    """Where a widget sits in the other bars, else the right side."""
    for bar in bar_names(text):
        for zone, items in get_zones(text, bar).items():
            if any(n == widget for n, _ in items):
                return zone
    return "right"


def toggle_widget(text, bar, widget, on, zone=None):
    """Switch a widget on or off in a bar. Off comments it out (it keeps its place); on uncomments it.
    A widget the bar never had is added to `zone` (default: where the other bars have it)."""
    zones = get_zones(text, bar)
    for z, items in zones.items():
        for k, (name, _) in enumerate(items):
            if name == widget:
                items[k] = (name, on)
                return put_zones(text, bar, {z: items})
    if not on:
        return text
    zone = zone or usual_zone(text, widget)
    zones.setdefault(zone, []).append((widget, True))
    return put_zones(text, bar, {zone: zones[zone]})


def move_widget(text, bar, widget, step):
    """Move a widget one place up (-1) or down (+1) inside its list."""
    zones = get_zones(text, bar)
    for z, items in zones.items():
        names = [n for n, _ in items]
        if widget in names:
            i, j = names.index(widget), names.index(widget) + step
            if 0 <= j < len(items):
                items[i], items[j] = items[j], items[i]
                return put_zones(text, bar, {z: items})
    return text


def move_to_zone(text, bar, widget, zone):
    """Move a widget to the end of another list (left, center or right); its on/off state is kept."""
    zones = get_zones(text, bar)
    for z, items in zones.items():
        for item in items:
            if item[0] == widget and z != zone:
                items.remove(item)
                zones.setdefault(zone, []).append(item)
                return put_zones(text, bar, {z: items, zone: zones[zone]})
    return text


def delete_key(text, path):
    """Remove a `key:` line and everything nested under it."""
    lines = text.split("\n")
    i = find_key(lines, path)
    if i is None:
        return text
    indent, end = _indent(lines[i]), i + 1
    while end < len(lines) and (not _content(lines[end]) or _indent(lines[end]) > indent):
        end += 1
    while end > i + 1 and not _content(lines[end - 1]):  # keep the blank lines that separated it from the next entry
        end -= 1
    del lines[i:end]
    return "\n".join(lines)


def repair_config(text):
    """Fix settings YASB rejects. Returns (text, [what was fixed]). whkd has no `callbacks` option: an earlier ShellFlow
    wrote one, and YASB answers "Extra inputs are not permitted"."""
    fixed = []
    in_line = set_menu_round(text, menu_gap(text)[0])
    if in_line != text:
        text = in_line
        fixed.append("menus: Windows' own corner rounding set to match (on while they float, off while they are stuck to the bar)")
    synced = sync_preview_margin(text, menu_gap(text)[1])
    if synced != text:
        text = synced
        fixed.append("taskbar preview: offset by the menu gap like the menus")
    for name, typ in read_widgets(text).items():
        if typ == "yasb.whkd.WhkdWidget" and find_key(text.split("\n"), ["widgets", name, "options", "callbacks"]) is not None:
            text = delete_key(text, ["widgets", name, "options", "callbacks"])
            fixed.append(f"{name}: removed the callbacks block YASB does not accept")
    for name, typ in read_widgets(text).items():
        lines = text.split("\n")
        opts = find_key(lines, ["widgets", name, "options"])
        if typ == "yasb.notes.NotesWidget" and opts is not None and find_key(lines, ["widgets", name, "options", "icons"]) is None:
            end = next((j for j in range(opts + 1, len(lines)) if _content(lines[j]) and _indent(lines[j]) <= _indent(lines[opts])), len(lines))
            while end > opts + 1 and not _content(lines[end - 1]):
                end -= 1
            pad = next((_indent(lines[j]) for j in range(opts + 1, end) if _content(lines[j])), _indent(lines[opts]) + 2) - 2
            lines[end:end] = [" " * pad + l for l in NOTES_ICONS]
            text = "\n".join(lines)
            fixed.append(f"{name}: normal icons for copy, delete, close and float")
    return text, fixed


MENU_OFFSET = re.compile(r"^(\s+offset_top:\s*)(-?\d+)(\s*(?:#.*)?)$")


def open_command():
    """The YASB callback that starts ShellFlow: exec <pythonw> <theme.py> settings (arguments are split on spaces, so a path with
    a space is put in quotes)."""
    q = lambda p: f'"{p}"' if " " in p else p
    return "exec " + q(str(th.pythonw()).replace("\\", "/")) + " " + q(str(th.HERE / "theme.py").replace("\\", "/")) + " settings"


def set_callback(text, widget, key, value):
    """Set callbacks.<key> of a widget in config.yaml, adding the callbacks block when the widget has none."""
    lines = text.split("\n")
    opts = find_key(lines, ["widgets", widget, "options"])
    if opts is None:
        return text
    if find_key(lines, ["widgets", widget, "options", "callbacks"]) is not None:
        return yaml_set(text, ["widgets", widget, "options", "callbacks", key], value)
    end = next((j for j in range(opts + 1, len(lines)) if _content(lines[j]) and _indent(lines[j]) <= _indent(lines[opts])), len(lines))
    while end > opts + 1 and not _content(lines[end - 1]):
        end -= 1
    pad = next((_indent(lines[j]) for j in range(opts + 1, end) if _content(lines[j])), _indent(lines[opts]) + 2)
    lines[end:end] = [" " * pad + "callbacks:", " " * (pad + 2) + f"{key}: {yaml_fmt(value)}"]
    return "\n".join(lines)


def middle_open_widget(text):
    """The widget whose middle click opens ShellFlow, or None."""
    for name in read_widgets(text):
        if str(yaml_get(text, ["widgets", name, "options", "callbacks", "on_middle"], "")).strip("\"'").endswith(" theme.py settings") or \
                "theme.py settings" in str(yaml_get(text, ["widgets", name, "options", "callbacks", "on_middle"], "")):
            return name
    return None


def set_middle_open(text, widget):
    """Middle click on `widget` opens ShellFlow (None = on none). The widget that had it before gets "do_nothing" back."""
    old = middle_open_widget(text)
    if old and old != widget:
        text = set_callback(text, old, "on_middle", "do_nothing")
    return set_callback(text, widget, "on_middle", open_command()) if widget else text


def bar_edge(text):
    """(edge, pad) of the first enabled bar: the screen edge it sits on ("top" or "bottom") and its padding on the side that faces the
    screen (so a window can touch the visible bar, not the empty margin around it)."""
    lines = text.split("\n")
    for bar in bar_names(text):
        if str(yaml_get(text, ["bars", bar, "enabled"], True)).lower() == "false":
            continue
        edge = "bottom" if str(yaml_get(text, ["bars", bar, "alignment", "position"], "top")).strip("\"'") == "bottom" else "top"
        pad = yaml_get(text, ["bars", bar, "padding", "top" if edge == "bottom" else "bottom"], 0)
        return edge, int(pad) if isinstance(pad, (int, float)) else 0
    return "top", 0


MIN_ATTACHED = 560  # px: the narrowest the attached window may be (only a very small bar gets more than "its width - 20")


def bar_box(text, work):
    """(x, width, edge) of the visible bar the window attaches to, in screen pixels, or None when it cannot be known. `edge` is the y of
    the visible bar's edge that the window touches (the bottom of a top bar, the top of a bottom bar), when Windows could be asked.
    Asked of Windows when the bar is on screen; otherwise worked out from config.yaml: a width in % or pixels is known, "auto" (as wide
    as the widgets) is not."""
    left, right = work[0], work[2]
    edge = bar_edge(text)[0]
    name = next((b for b in bar_names(text) if str(yaml_get(text, ["bars", b, "enabled"], True)).lower() != "false"), None)

    def pad(side, bar=None):
        v = yaml_get(text, ["bars", bar or name, "padding", side], 0) if (bar or name) else 0
        return int(v) if isinstance(v, (int, float)) else 0
    pad_l, pad_r = pad("left"), pad("right")
    seen = [r for r in th.bar_rects() if left <= (r[0] + r[2]) // 2 < right]
    if seen:  # the real bar: the one at the screen edge the window attaches to
        r = min(seen, key=lambda r: r[1]) if edge == "top" else max(seen, key=lambda r: r[3])
        # which bar of config.yaml is this? (the monitors have bars of their own, with their own padding): the one whose height plus
        # padding is the height of the window Windows found
        mine = next((b for b in bar_names(text) if str(yaml_get(text, ["bars", b, "enabled"], True)).lower() != "false"
                     and abs(int(yaml_get(text, ["bars", b, "dimensions", "height"], 0) or 0) + pad("top", b) + pad("bottom", b) - (r[3] - r[1])) <= 3), name)
        guess = r[3] - pad("bottom", mine) if edge == "top" else r[1] + pad("top", mine)
        ed = load_edits()
        solid = int(ed.get("opacity", 100)) >= 100  # a see-through bar has no one colour to look for
        col = parse_colour(str(ed.get("bar_colour", "#000000")))
        seen_edge = th.bar_pill_edge(r, edge, guess, col[:3] if col else (0, 0, 0)) if solid else None
        return r[0] + pad("left", mine), r[2] - r[0] - pad("left", mine) - pad("right", mine), (seen_edge if seen_edge is not None else guess)
    spec = str(yaml_get(text, ["bars", name, "dimensions", "width"], "auto")).strip("\"' ") if name else "auto"
    full = right - left
    if spec.endswith("%") and spec[:-1].replace(".", "", 1).isdigit():
        base = round(full * float(spec[:-1]) / 100)
    elif spec.isdigit():
        base = int(spec)
    else:
        return None  # "auto": the bar is as wide as its widgets, which only Windows can tell
    align = str(yaml_get(text, ["bars", name, "alignment", "align"], "center")).strip("\"'") if name else "center"
    x0 = left if align == "left" else right - base if align == "right" else left + (full - base) // 2
    return x0 + pad_l, base - pad_l - pad_r, None


def bar_span(text, work):
    """(x, width) of the visible bar, or None (see bar_box)."""
    box = bar_box(text, work)
    return box[:2] if box else None


def menu_gap(text):
    """(floating, gap): the distance every menu and popup of the widgets keeps from the bar. 0 = attached. If the widgets
    disagree, the most common non-zero value counts."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith("widgets:")), len(lines))
    values = [int(m.group(2)) for l in lines[start:] if (m := MENU_OFFSET.match(l))]
    nonzero = [v for v in values if v > 0]
    return (True, max(set(nonzero), key=nonzero.count)) if nonzero else (False, 0)


MENU_ROUND = re.compile(r"^(\s+round_corners:\s*)(true|false)(\s*(?:#.*)?)$", re.I)


def set_menu_round(text, on):
    """Windows' own rounding of the menu windows (`round_corners` under widgets). It must be off while a menu is stuck to the bar, because it
    would round the corners that touch the bar (the clock's calendar and the power menu are the ones that showed it)."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith("widgets:")), len(lines))
    for i in range(start, len(lines)):
        m = MENU_ROUND.match(lines[i])
        if m:
            lines[i] = f"{m.group(1)}{'true' if on else 'false'}{m.group(3)}"
    return "\n".join(lines)


PREVIEW_MARGIN = re.compile(r"^(\s+margin:\s*)(-?\d+)(\s*(?:#.*)?)$")


def sync_preview_margin(text, gap):
    """The taskbar widget's preview window hangs `margin` px below its button. It is offset by the menu gap like the menus are: margin =
    the distance you tuned (remembered in a comment on the line, "[ShellFlow base 12]") + the gap."""
    for name, typ in read_widgets(text).items():
        if typ != "yasb.taskbar.TaskbarWidget":
            continue
        lines = text.split("\n")
        i = find_key(lines, ["widgets", name, "options", "preview", "margin"])
        m = PREVIEW_MARGIN.match(lines[i]) if i is not None else None
        if not m:
            continue
        mark = re.search(r"\[ShellFlow base (-?\d+)\]", m.group(3) or "")
        if not mark and gap == 0:
            continue  # attached and never touched: leave your line alone
        base = int(mark.group(1)) if mark else int(m.group(2))  # the first time, the margin you tuned is the base
        orig = re.sub(r"\s*\[ShellFlow base -?\d+\]", "", m.group(3) or "").strip()
        lines[i] = f"{m.group(1)}{base + gap}   {orig if orig.startswith('#') else '#'} [ShellFlow base {base}]"
        text = "\n".join(lines)
    return text


def set_menu_gap(text, gap):
    """Give every menu and popup (calendar, power menu, layout menu, control center, notes, ...) the same distance from the bar, and Windows'
    own rounding of their windows what suits it: on while they float, off while they are stuck to the bar. A trailing comment stays."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith("widgets:")), len(lines))
    for i in range(start, len(lines)):
        m = MENU_OFFSET.match(lines[i])
        if m:
            lines[i] = f"{m.group(1)}{gap}{m.group(3)}"
    return sync_preview_margin(set_menu_round("\n".join(lines), gap > 0), gap)


def remove_widget(text, bar, widget):
    """Take a widget out of one bar's lists (on or off, commented or not). Its definition stays in `widgets:`."""
    zones = get_zones(text, bar)
    changed = {z: [it for it in items if it[0] != widget] for z, items in zones.items() if any(it[0] == widget for it in items)}
    return put_zones(text, bar, changed) if changed else text


def delete_widget_def(text, widget):
    """Remove a widget everywhere: from every bar and its definition in `widgets:`."""
    for bar in bar_names(text):
        text = remove_widget(text, bar, widget)
    return delete_key(text, ["widgets", widget])


def get_screens(text, bar):
    lines = text.split("\n")
    i = find_key(lines, ["bars", bar, "screens"])
    return re.findall(r"[\"']([^\"']+)[\"']", lines[i]) if i is not None else []


def set_screens(text, bar, names):
    lines = text.split("\n")
    i = find_key(lines, ["bars", bar, "screens"])
    if i is None:
        return text
    lines[i] = "%s: [%s]" % (lines[i].split(":", 1)[0], ", ".join(f'"{n}"' for n in names))
    return "\n".join(lines)


def save_config(text):
    """Write config.yaml. (No automatic copy: use the Backup page when you want one.)"""
    CONFIG_YAML.write_text(text, encoding="utf-8")


# ============================================================================================
#  3. EDITS  (fonts, colours, spacing, bar opacity -> one block at the end of styles.css)
# ============================================================================================
BLOCK_START = "/* >>> ShellFlow (written by the settings window - change it there, not here) >>> */"
BLOCK_END = "/* <<< ShellFlow <<< */"
# (label, css variable) of the colours that can be overridden
COLOUR_VARS = (("Accent", "accent"), ("Dark 1", "accent-dark1"), ("Dark 2", "accent-dark2"),
               ("Dark 3", "accent-dark3"), ("Light 1", "accent-light1"), ("Light 2", "accent-light2"),
               ("Light 3", "accent-light3"), ("Background", "background"), ("Foreground", "foreground"))
# the groups of styles.css: widget text and icons, menus / tooltips / clock, and the capsules
BAR_FONT_SELECTORS = (".widget .label", ".komorebi-active-layout .label", ".komorebi-control-widget .label",
                      ".power-menu-widget .label", ".systray .button", ".context-menu .menu-checkbox .checkbox")
MENU_FONT_SELECTORS = (".context-menu", ".context-menu *", ".home-menu", ".home-menu *", ".komorebi-layout-menu *",
                       ".power-menu-compact", ".power-menu-compact *", ".power-menu-popup .button",
                       ".power-menu-popup .button .label", ".taskbar-preview .header .title", ".tooltip",
                       ".clock-widget .label")
CAPSULES = (".home-widget", ".komorebi-workspaces", ".komorebi-active-layout", ".komorebi-control-widget",
            ".taskbar-widget .widget-container", ".systray", ".wallpapers-widget", ".clock-widget", ".power-menu-widget")
NERD = '"JetBrainsMono Nerd Font Propo", "JetBrainsMono NFP"'  # fallback, so icon glyphs keep working


parse_colour = th.parse_colour


def load_edits():
    try:
        return json.loads(EDITS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# the popups of the catalog widgets, in your theme: black, rounded, accent buttons, light text. __FONT__ = the menu font
NOTES_CSS = """.notes-menu {
    background-color: #000000;
    border: none;
    border-radius: 20px;
    min-width: 380px;
    max-width: 380px;
}
.notes-menu .notes-header {
    background-color: transparent;
    padding: 6px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.notes-menu .notes-header .header-title {
    font-family: __FONT__;
    font-size: 15px;
    font-weight: 700;
    color: var(--yasb-accent-light2);
}
.notes-menu .notes-header .float-button,
.notes-menu .notes-header .close-button {
    background-color: transparent;
    border: none;
    color: var(--yasb-accent-light2);
    font-family: __ICONFONT__;
    font-size: 15px;
    padding: 4px 6px;
    border-radius: 8px;
}
.notes-menu .notes-header .float-button:hover,
.notes-menu .notes-header .close-button:hover {
    background-color: rgba(255, 255, 255, 0.10);
}
.notes-menu .note-input {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--yasb-accent-dark1);
    border-radius: 14px;
    padding: 10px;
    margin: 8px 12px 4px 12px;
    min-height: 110px;
    color: #ffffff;
    font-family: __FONT__;
    font-size: 13px;
}
.notes-menu .note-input:focus {
    border: 1px solid var(--yasb-accent-light1);
}
.notes-menu .input-copy-button {
    color: var(--yasb-accent-light2);
    background: transparent;
    border: none;
    font-family: __ICONFONT__;
    font-size: 14px;
    padding: 2px 4px;
    border-radius: 6px;
}
.notes-menu .input-copy-button:hover {
    background-color: rgba(255, 255, 255, 0.10);
}
.notes-menu .add-button,
.notes-menu .cancel-button {
    background-color: var(--yasb-accent-light1);
    color: var(--yasb-accent-dark3);
    border: none;
    border-radius: 14px;
    padding: 8px 16px;
    margin: 4px 12px;
    font-family: __FONT__;
    font-size: 13px;
    font-weight: 600;
}
.notes-menu .add-button:hover,
.notes-menu .cancel-button:hover {
    background-color: var(--yasb-accent-light2);
}
.notes-menu .scroll-area {
    background: transparent;
    border: none;
    border-radius: 0;
}
.notes-menu .note-item {
    background-color: transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 0.10);
}
.notes-menu .note-item:hover {
    background-color: rgba(255, 255, 255, 0.06);
}
.notes-menu .note-item .title {
    font-family: __FONT__;
    font-size: 13px;
    color: #ffffff;
}
.notes-menu .note-item .date {
    font-family: __FONT__;
    font-size: 11px;
    color: rgba(255, 255, 255, 0.45);
}
.notes-menu .empty-list {
    font-family: __FONT__;
    font-size: 15px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.35);
    padding: 12px 0 18px 0;
}
.notes-menu .copy-button,
.notes-menu .delete-button {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 4px 8px;
    color: var(--yasb-accent-light2);
    font-family: __ICONFONT__;
    font-size: 14px;
}
.notes-menu .delete-button {
    color: #ff7a8a;
}
.notes-menu .copy-button:hover,
.notes-menu .delete-button:hover {
    background-color: rgba(255, 255, 255, 0.10);
}"""

CONTROL_CENTER_CSS = """.control-center-menu {
    background-color: #000000;
    border: none;
    border-radius: 20px;
    min-width: 400px;
    color: #ffffff;
}
.control-center-menu .section {
    background: transparent;
    margin: 0;
    padding: 14px 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.10);
}
.control-center-menu .section.system-controls {
    padding: 14px 16px 6px 16px;
}
.control-center-menu .section.sliders {
    padding: 14px 16px;
}
.control-center-menu .section.media,
.control-center-menu .section.power,
.control-center-menu .section.system-controls {
    border-bottom: 1px solid rgba(255, 255, 255, 0);
}
.control-center-menu .section.system-controls .button,
.control-center-menu .section.quick-actions .button .icon,
.control-center-menu .section.sliders .slider .icon,
.control-center-menu .section.sliders .slider .source-selector,
.control-center-menu .section.power .plan-name .icon,
.control-center-menu .section.power .mode-name .icon,
.control-center-menu .section.media .button {
    font-family: "Segoe Fluent Icons";
    font-weight: 400;
}
.control-center-menu .section.system-controls .button {
    background-color: rgba(255, 255, 255, 0.08);
    color: var(--yasb-accent-light2);
    border-radius: 16px;
    min-height: 32px;
    max-height: 32px;
    min-width: 32px;
    max-width: 32px;
    font-size: 14px;
}
.control-center-menu .section.system-controls .button:hover {
    background-color: rgba(255, 255, 255, 0.18);
}
.control-center-menu .section.quick-actions .button {
    margin: 0 4px;
}
.control-center-menu .section.quick-actions .button .icon {
    font-size: 17px;
    background-color: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    min-height: 50px;
    color: var(--yasb-accent-light2);
}
.control-center-menu .section.quick-actions .button .icon:hover {
    background-color: rgba(255, 255, 255, 0.12);
}
.control-center-menu .section.quick-actions .button.active .icon {
    background-color: var(--yasb-accent-light1);
    border: 1px solid var(--yasb-accent-light1);
    color: var(--yasb-accent-dark3);
}
.control-center-menu .section.quick-actions .button .title {
    font-family: __FONT__;
    font-size: 11px;
    font-weight: 600;
    margin: 4px 0 8px 0;
    padding: 0;
    color: #ffffff;
}
.control-center-menu .section.sliders .slider {
    background: transparent;
    border: none;
    min-height: 34px;
    margin: 0 4px;
}
.control-center-menu .section.sliders .slider .icon {
    font-size: 16px;
    min-width: 36px;
    color: var(--yasb-accent-light2);
}
.control-center-menu .section.sliders .slider .value {
    font-family: __FONT__;
    min-width: 42px;
    font-size: 12px;
    font-weight: 600;
    color: #ffffff;
}
.control-center-menu .section.sliders .slider .source-selector {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.65);
    width: 24px;
    height: 24px;
    border-radius: 8px;
    background-color: rgba(255, 255, 255, 0);
    margin-left: 4px;
}
.control-center-menu .section.sliders .slider .source-selector:hover {
    background-color: rgba(255, 255, 255, 0.12);
}
.control-center-menu .section.power .plan-name,
.control-center-menu .section.power .mode-name {
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    min-height: 38px;
    margin: 0 4px;
    padding: 6px 12px;
}
.control-center-menu .section.power .plan-name:hover,
.control-center-menu .section.power .mode-name:hover {
    background: rgba(255, 255, 255, 0.12);
}
.control-center-menu .section.power .plan-name .title,
.control-center-menu .section.power .mode-name .title {
    font-family: __FONT__;
    font-size: 11px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.60);
}
.control-center-menu .section.power .plan-name .subtext,
.control-center-menu .section.power .mode-name .subtext {
    font-family: __FONT__;
    font-size: 12px;
    font-weight: 600;
    color: #ffffff;
}
.control-center-menu .section.power .plan-name .icon,
.control-center-menu .section.power .mode-name .icon {
    color: rgba(255, 255, 255, 0.60);
    font-size: 14px;
}
.control-center-menu .section.media {
    background-color: rgba(255, 255, 255, 0.04);
    padding: 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.10);
}
.control-center-menu .section.media .title {
    font-family: __FONT__;
    font-size: 13px;
    font-weight: 600;
    color: #ffffff;
}
.control-center-menu .section.media .subtext {
    font-family: __FONT__;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.55);
}
.control-center-menu .section.media .button {
    font-size: 14px;
    color: var(--yasb-accent-light2);
    background-color: rgba(255, 255, 255, 0);
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
    border-radius: 10px;
    margin: 0 0 0 4px;
}
.control-center-menu .section.media .button:hover {
    background-color: rgba(255, 255, 255, 0.10);
}
.control-center-menu .context-menu {
    background-color: #111111;
    padding: 4px 0;
    font-family: __FONT__;
    font-size: 12px;
    font-weight: 600;
    color: #ffffff;
}
.control-center-menu .context-menu::item {
    background-color: transparent;
    padding: 6px 12px;
    margin: 2px 6px;
    border-radius: 8px;
    min-width: 100px;
}
.control-center-menu .context-menu::item:selected {
    background-color: rgba(255, 255, 255, 0.12);
}"""

WHKD_CSS = """.whkd-popup {
    background-color: #000000;
    border: none;
    border-radius: 20px;
}
.whkd-popup .edit-config-button {
    background-color: var(--yasb-accent-light1);
    color: var(--yasb-accent-dark3);
    padding: 4px 12px 6px 12px;
    font-family: __FONT__;
    font-size: 13px;
    font-weight: 600;
    border-radius: 12px;
}
.whkd-popup .keybind-button {
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
    padding: 4px 10px 6px 10px;
    font-size: 13px;
    font-weight: 600;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px;
}
.whkd-popup .keybind-button.special {
    background-color: rgba(255, 255, 255, 0.14);
}
.whkd-popup .keybind-row:hover {
    background-color: rgba(255, 255, 255, 0.06);
    border-radius: 10px;
}
.whkd-popup .plus-separator {
    border: none;
    color: rgba(255, 255, 255, 0.5);
    background-color: transparent;
}
.whkd-popup .filter-input {
    padding: 0 10px 2px 10px;
    font-family: __FONT__;
    font-size: 13px;
    border: 1px solid var(--yasb-accent-dark1);
    border-radius: 12px;
    color: #ffffff;
    background-color: rgba(255, 255, 255, 0.06);
    min-height: 32px;
}
.whkd-popup .filter-input:focus {
    border: 1px solid var(--yasb-accent-light1);
}
.whkd-popup .keybind-command {
    font-family: __FONT__;
    font-size: 13px;
    color: #ffffff;
}
.whkd-popup .keybind-header {
    font-family: __FONT__;
    font-size: 15px;
    font-weight: 600;
    color: var(--yasb-accent-light2);
    padding: 8px 0;
    margin-top: 16px;
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 12px;
}"""
POPUP_CSS = {"notes": NOTES_CSS, "control_center": CONTROL_CENTER_CSS, "whkd": WHKD_CSS}


ICON_BUTTONS = ("whkd", "notes", "control_center")  # one glyph in a capsule
TEXT_CAPSULES = ("active_window",)                  # a title in a capsule


def catalog_css(cfg_text, font="Poppins", icon_pad=14):
    """Capsule and popup styling for the catalog widgets that config.yaml defines (same look as the other capsules).
    The buttons get even padding left and right (icon_pad px). The rules start with .yasb-bar so they win over the
    general `.widget` padding, which is meant for the other capsules."""
    used = [e for e in CATALOG if e[4] in read_widgets(cfg_text).values()]
    if not used:
        return "", ()
    ff = f'"{font or "Poppins"}", "Segoe UI", sans-serif'
    caps = ",\n".join(e[5] for e in used)
    out = [caps + " {\n    background-color: var(--yasb-accent-light1);\n    border-radius: 14px;\n    margin: 5px;\n}"]
    buttons = [e[5] for e in used if e[0] in ICON_BUTTONS]
    titles = [e[5] for e in used if e[0] in TEXT_CAPSULES]
    if buttons or titles:
        out.append(",\n".join(f".yasb-bar {s}" for s in buttons + titles) + f" {{\n    padding: 0 {icon_pad}px;\n}}")
    if buttons:
        out.append(",\n".join(f".yasb-bar {s} {part}" for s in buttons for part in (".icon", ".label")) +
                   " {\n    font-size: 18px;\n    color: var(--yasb-accent-dark3);\n    padding: 0 0 2px 0;\n}")
    if titles:
        out.append(",\n".join(f".yasb-bar {s} .label" for s in titles) +
                   " {\n    font-size: 13px;\n    font-weight: 600;\n    color: var(--yasb-accent-dark3);\n    padding: 0 0 2px 0;\n}")
    out += [POPUP_CSS[e[0]].replace("__FONT__", ff).replace("__ICONFONT__", NERD) for e in used if e[0] in POPUP_CSS]
    return "\n\n".join(out), tuple(e[5] for e in used)


def px(value):
    return f"{value}px"


# every menu's root element. Newer YASB gives the clock's popup two classes (.clock-popup.calendar), so a rule for plain .calendar is weaker
# than the menu's own. Each root is therefore written twice, the second time with one class repeated (which counts for more).
MENU_ROOTS = (".context-menu", ".home-menu", ".komorebi-layout-menu", ".komorebi-control-menu", ".calendar", ".power-menu-popup",
              ".power-menu-compact", ".taskbar-preview", ".wallpapers-gallery-window",
              ".clock-popup", ".clock-popup.calendar", ".clock-popup.alarm", ".clock-popup.timer", ".notes-menu", ".control-center-menu", ".whkd-popup")


def menu_selectors():
    out = []
    for root in MENU_ROOTS:
        first = root.split(".")[1]
        out += [root, "." + first + root]  # the same element, with its first class repeated: stronger than a rule that names it once
    return out


def menu_corners(cfg_text, edits):
    """CSS for the corners of every menu, from whether they float: round all over when they float; stuck to the bar, the two corners that
    touch it are square (the top ones for a bar at the top, the bottom ones for a bar at the bottom). The radius is the Menu roundness
    (20 px unless set). Written one corner at a time: Qt's style sheets ignore the four-value form of border-radius (the corners came out
    square), and a single-value border-radius does not reliably beat a menu's own per-corner rules."""
    r = f"{int(edits.get('menu_radius', 20))}px"
    if menu_gap(cfg_text)[0]:
        tl = tr = bl = br = r
    elif bar_edge(cfg_text)[0] == "bottom":
        tl, tr, bl, br = r, r, "0px", "0px"
    else:
        tl, tr, bl, br = "0px", "0px", r, r
    menus = ",\n".join(menu_selectors()) + (f" {{\n    border-top-left-radius: {tl};\n    border-top-right-radius: {tr};\n"
                                           f"    border-bottom-left-radius: {bl};\n    border-bottom-right-radius: {br};\n}}")
    return menus


def style_block(edits, cfg_text=""):
    """The CSS for fonts, capsules, the bar and the workspace pills. A value that is not set produces nothing (styles.css stays as it is)."""
    out = []
    for key, selectors in (("font_bar", BAR_FONT_SELECTORS), ("font_menu", MENU_FONT_SELECTORS)):
        face = str(edits.get(key, "")).strip().strip("\"'")
        if face:
            out.append(",\n".join(selectors) + " {\n    font-family: \"%s\", %s;\n}" % (face, NERD))
    types = set(read_widgets(cfg_text).values())
    offline = [sel for typ, sel in (("komorebi.workspaces.WorkspaceWidget", ".komorebi-workspaces .offline-status"),
                                    ("komorebi.stack.StackWidget", ".komorebi-stack .offline-status")) if typ in types]
    if offline:  # "Komorebi Offline" is white until it is given the capsule's text colour
        out.append(",\n".join(offline) + " {\n    color: var(--yasb-accent-dark3);\n    font-weight: 600;\n}")
    base, extra = catalog_css(cfg_text, str(edits.get("font_menu", "")).strip().strip("\"'") or css_font(MENU_FONT_SELECTORS),
                              edits.get("icon_pad", 14))
    if base:
        out.insert(0, base)
    # capsules: spacing on the left and right only (never above or below), roundness, an optional border
    left, right = edits.get("spacing_l", edits.get("spacing")), edits.get("spacing_r", edits.get("spacing"))
    caps = []
    if left is not None:
        caps.append(f"    margin-left: {px(left)};")
    if right is not None:
        caps.append(f"    margin-right: {px(right)};")
    if "radius" in edits:
        caps.append(f"    border-radius: {px(edits['radius'])};")
    if edits.get("border_w"):
        r, g, b, a = parse_colour(str(edits.get("border_c", "#000000"))) or (0, 0, 0, 1.0)
        caps.append(f"    border: {px(edits['border_w'])} solid " + (f"rgb({r}, {g}, {b});" if a >= 1 else f"rgba({r}, {g}, {b}, {a:g});"))
    if caps:
        out.append(",\n".join(CAPSULES + extra) + " {\n" + "\n".join(caps) + "\n}")
    pad_l, pad_r = edits.get("pad_l", edits.get("pad")), edits.get("pad_r", edits.get("pad"))
    pads = [f"    padding-{side}: {px(v)};" for side, v in (("left", pad_l), ("right", pad_r)) if v is not None]
    if pads:
        out.append(".widget {\n" + "\n".join(pads) + "\n}")
    bar = []
    if "opacity" in edits:
        r, g, b, _ = parse_colour(edits.get("bar_colour", "#000000")) or (0, 0, 0, 1)
        bar.append(f"    background-color: rgba({r}, {g}, {b}, {edits['opacity'] / 100:.2f});")
    if "bar_radius" in edits:
        bar.append(f"    border-radius: {px(edits['bar_radius'])};")
    if bar:
        out.append(".yasb-bar {\n" + "\n".join(bar) + "\n}")
    # the workspace pills inside the komorebi workspaces capsule
    ws = ".komorebi-workspaces .ws-btn"
    pill = [f"    {css}: {value};" for key, css, value in (("ws_radius", "border-radius", px(edits.get("ws_radius"))),
                                                         ("ws_h", "height", px(edits.get("ws_h"))),
                                                         ("ws_w_empty", "width", px(edits.get("ws_w_empty"))),
                                                         ("ws_gap", "margin", f"0 {edits.get('ws_gap')}px")) if key in edits]
    if pill:
        out.append(ws + " {\n" + "\n".join(pill) + "\n}")
    if "ws_w_pop" in edits:
        out.append(ws + f".populated {{\n    width: {px(edits['ws_w_pop'])};\n}}")
    if "ws_w_active" in edits:
        out.append(ws + f".active {{\n    width: {px(edits['ws_w_active'])};\n}}")
    if types:  # last, so it wins over the radius each menu's own rule has
        out.append(menu_corners(cfg_text, edits))
    return "\n\n".join(out)


def css_font(selectors):
    """The font face your styles.css gives one of the font groups (first family of the last matching rule)."""
    try:
        css = STYLES.read_text(encoding="utf-8")
    except OSError:
        return ""
    css = re.sub(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), "", css, flags=re.S)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = ""
    for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        names = [n.strip() for n in rule.group(1).split(",")]
        m = re.search(r"font-family\s*:\s*([^;]+);", rule.group(2))
        if m and any(n in selectors for n in names):
            found = m.group(1).split(",")[0].strip().strip("\"'")
    return found


def current_colours(base_only=False):
    """{variable: "#rrggbb"} as the bar uses them now (theme_colors.css over yasb_colors.css), or only the
    Windows accent ones (base_only)."""
    out = {}
    for name in ("yasb_colors.css",) if base_only else ("yasb_colors.css", "theme_colors.css"):
        try:
            text = (th.CONFIG / name).read_text(encoding="utf-8")
        except OSError:
            continue
        for var, r, g, b in re.findall(r"--yasb-([\w-]+?)-rgb:\s*(\d+),\s*(\d+),\s*(\d+)", text):
            out[var] = "#%02x%02x%02x" % (int(r), int(g), int(b))
    return out


def save_edits(edits, cfg_text=None):
    """Save the settings and rewrite the ShellFlow block at the end of styles.css."""
    EDITS_JSON.write_text(json.dumps(edits, indent=2), encoding="utf-8")
    if not STYLES.exists():
        return
    css = STYLES.read_text(encoding="utf-8")
    css = re.sub(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\n?", "", css, flags=re.S).rstrip("\n") + "\n"
    if cfg_text is None:
        try:
            cfg_text = CONFIG_YAML.read_text(encoding="utf-8")
        except OSError:
            cfg_text = ""
    block = style_block(edits, cfg_text)
    if block:
        css += f"\n{BLOCK_START}\n{block}\n{BLOCK_END}\n"
    STYLES.write_text(css, encoding="utf-8")


def style_block_is_current(edits, cfg_text=None):
    """True when the ShellFlow block at the end of styles.css is exactly what the current settings would write."""
    try:
        css = STYLES.read_text(encoding="utf-8").replace("\r\n", "\n")
        cfg_text = CONFIG_YAML.read_text(encoding="utf-8") if cfg_text is None else cfg_text
    except OSError:
        return True  # nothing to refresh
    m = re.search(re.escape(BLOCK_START) + r"\n(.*?)\n" + re.escape(BLOCK_END), css, re.S)
    return (m.group(1) if m else "") == style_block(edits, cfg_text)


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


def yasbc():
    exe = th.env("YASB_CLI") or shutil.which("yasbc") or str(th.where("PROGRAMFILES") / "YASB" / "yasbc.exe")
    return exe if Path(exe).exists() or shutil.which(exe) else None


def list_monitors():
    """The monitor names YASB uses in `screens:` (from `yasbc monitor-information`)."""
    exe = yasbc()
    text = run_quiet([exe, "monitor-information"]) if exe else ""
    return list(dict.fromkeys(m.strip() for m in re.findall(r"Name:\s*(.+?)(?=\s+Resolution:|\r?\n|$)", text)))


def config_files():
    """{category: [paths]}: YASB's own files, its scripts, komorebi's and whkd's."""
    root = th.CONFIG
    yasb = [p for p in sorted(root.iterdir()) if p.is_file() and p.suffix != ".bak"] if root.is_dir() else []
    scripts = root / "scripts"
    mine = [p for p in sorted(scripts.iterdir()) if p.is_file() and p.suffix in (".py", ".json", ".txt")] if scripts.is_dir() else []
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


# ============================================================================================
#  BACKUPS and LOG FILES  (only ever done when you press a button on the Backup page)
# ============================================================================================
BACKUP_DIR = th.CONFIG / "backups"
LOG_NAMES = ("theme_error.log", "shellflow_start.log", "theme_watch.log", "settings_hang.log", "shellflow_doctor.txt")
OLD_COPIES = ("config.yaml.bak", "styles.css.bak")  # what older versions copied by themselves


def backup_targets():
    """{name inside the zip: where it lives}: the files that make up your setup."""
    kom = komorebi_dir()
    return {"yasb/config.yaml": CONFIG_YAML, "yasb/styles.css": STYLES, "yasb/.env": ENV, "yasb/theme_colors.css": th.OUT,
            "yasb/notes.json": th.CONFIG / "notes.json", "scripts/settings.json": EDITS_JSON,
            "komorebi/komorebi.json": kom / "komorebi.json", "komorebi/applications.json": kom / "applications.json",
            "whkd/whkdrc": whkdrc_path()}


def make_backup():
    """Zip the files that exist into backups/backup_<date>_<time>.zip. Returns the zip's path."""
    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / time.strftime("backup_%Y-%m-%d_%H-%M-%S.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src in backup_targets().items():
            if src.is_file():
                z.write(src, name)
    return path


def backup_title(path):
    """backup_2026-10-02_15-04-12.zip -> 2026-10-02  15:04:12"""
    m = re.match(r"backup_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})", path.name)
    return f"{m.group(1)}  {m.group(2)}:{m.group(3)}:{m.group(4)}" if m else path.stem


def list_backups():
    """[(path, number of files, size in bytes)], newest first."""
    out = []
    for p in sorted(BACKUP_DIR.glob("backup_*.zip"), reverse=True) if BACKUP_DIR.is_dir() else []:
        try:
            with zipfile.ZipFile(p) as z:
                out.append((p, len(z.namelist()), p.stat().st_size))
        except (OSError, zipfile.BadZipFile):
            out.append((p, 0, 0))
    return out


def restore_backup(path):
    """Put the files of a backup back where they belong. Only the known files are restored, never anything else in the zip.
    Returns the names that were restored."""
    targets, done = backup_targets(), []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name in targets:
                targets[name].parent.mkdir(parents=True, exist_ok=True)
                targets[name].write_bytes(z.read(name))
                done.append(name)
    return done


def log_files():
    """The log files that exist, as paths."""
    return [th.HERE / n for n in LOG_NAMES if (th.HERE / n).is_file()]


def old_copies():
    return [th.CONFIG / n for n in OLD_COPIES if (th.CONFIG / n).is_file()]


def size_text(n):
    return f"{n / 1024:.1f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
THUMBS = th.HERE / ".thumbs"


def expand_path(p):
    """$env:NAME, %NAME% and ~ in a path from config.yaml."""
    p = re.sub(r"\$env:(\w+)", lambda m: os.environ.get(m.group(1)) or th.env(m.group(1)) or "", str(p).strip(), flags=re.I)
    return os.path.expandvars(os.path.expanduser(p))


def wallpaper_dirs(text):
    """The folders the YASB wallpapers widget picks from (its image_path), else YASB_WALLPAPERS."""
    lines = text.split("\n")
    name = next((n for n, t in read_widgets(text).items() if t == "yasb.wallpapers.WallpapersWidget"), None)
    found = []
    i = find_key(lines, ["widgets", name, "options", "image_path"]) if name else None
    if i is not None:
        rest = lines[i].split(":", 1)[1].strip()
        if rest.startswith("["):
            found = re.findall(r"[\"']([^\"']+)[\"']", rest)
        elif rest and not rest.startswith("#"):
            found = [parse_scalar(rest)]
        else:  # a list of folders, one `- path` per line
            for l in lines[i + 1:]:
                m = re.match(r"^\s*-\s*[\"']?(.+?)[\"']?\s*(#.*)?$", l)
                if m:
                    found.append(m.group(1))
                elif l.strip() and not l.strip().startswith("#"):
                    break
    if not found and th.env("YASB_WALLPAPERS"):
        found = [th.env("YASB_WALLPAPERS")]
    return [Path(expand_path(p.replace("\\\\", "\\"))) for p in found]


def list_wallpapers(dirs, limit=60):
    out = []
    for d in dirs:
        try:
            out += sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXT and p.is_file())
        except OSError:
            pass
    return out[:limit]


def make_thumb(path, size=(240, 135)):
    """A 16:9 thumbnail of a wallpaper, cached in scripts/.thumbs so the next visit is instant."""
    st = path.stat()
    cache = THUMBS / (hashlib.md5(f"{path}|{st.st_mtime_ns}|{st.st_size}|{size}".encode()).hexdigest() + ".png")
    if cache.exists():
        return Image.open(cache).convert("RGBA")
    im = Image.open(path)
    im.draft("RGB", (size[0] * 2, size[1] * 2))
    im = ImageOps.fit(im.convert("RGB"), size, Image.LANCZOS)
    try:
        THUMBS.mkdir(exist_ok=True)
        im.save(cache)
    except OSError:
        pass
    return im.convert("RGBA")


def set_wallpaper(path):
    """Set the desktop wallpaper (Windows)."""
    try:
        import ctypes
        return bool(ctypes.windll.user32.SystemParametersInfoW(0x14, 0, str(path), 3))  # SPI_SETDESKWALLPAPER, update + broadcast
    except Exception:
        return False


def same_file(a, b):
    try:
        return bool(a) and bool(b) and os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))
    except OSError:
        return False


@lru_cache(maxsize=1)
def yasb_version():
    """The version YASB wrote to its log when it last started."""
    try:
        found = re.findall(r"YASB (v\d[\w.\-]*)", (th.CONFIG / "yasb.log").read_text(encoding="utf-8", errors="ignore"))
        return found[-1] if found else "not in yasb.log yet"
    except OSError:
        return "yasb.log not found"


@lru_cache(maxsize=1)
def komorebi_version():
    out = run_quiet(["komorebic", "--version"], 4).strip().splitlines()
    return out[0] if out else "komorebic not found"


def user_name():
    return th.env("YASB_USERNAME") or os.environ.get("USERNAME") or "You"


# ============================================================================================
#  5. ICONS  (monochrome line icons, drawn here - no emoji, no icon font needed)
# ============================================================================================
# Each icon is a list of shapes on a 24 x 24 grid: line (a path), circle, dot (filled), rect, arc.
_FILE = [("line", [(6, 3), (14, 3), (19, 8), (19, 21), (6, 21), (6, 3)]), ("line", [(14, 3), (14, 8), (19, 8)])]
ICONS = {
    "panel": [("rect", 3, 4, 21, 20, 3), ("line", [(9, 4), (9, 20)])],
    "search": [("circle", 10.5, 10.5, 6.5), ("line", [(15.3, 15.3), (20.5, 20.5)])],
    "sliders": [("line", [(4, 7), (6.6, 7)]), ("line", [(11.4, 7), (20, 7)]), ("circle", 9, 7, 2.4),
                ("line", [(4, 17), (12.6, 17)]), ("line", [(17.4, 17), (20, 17)]), ("circle", 15, 17, 2.4)],
    "palette": [("circle", 12, 12, 9), ("dot", 8, 10.5, 1.2), ("dot", 11.5, 7.2, 1.2), ("dot", 16, 9, 1.2), ("dot", 16.5, 14, 1.2)],
    "grid": [("rect", 4, 4, 10.5, 10.5, 2), ("rect", 13.5, 4, 20, 10.5, 2), ("rect", 4, 13.5, 10.5, 20, 2), ("rect", 13.5, 13.5, 20, 20, 2)],
    "bar": [("rect", 3, 4, 21, 10, 3), ("dot", 7.5, 7, 1.1), ("dot", 12, 7, 1.1), ("dot", 16.5, 7, 1.1), ("line", [(3, 20), (21, 20)])],
    "layers": [("line", [(12, 3), (21, 8), (12, 13), (3, 8), (12, 3)]), ("line", [(3, 12.5), (12, 17.5), (21, 12.5)]), ("line", [(3, 16.5), (12, 21.5), (21, 16.5)])],
    "pen": [("line", [(4, 20), (4.8, 15.6), (15.5, 4.9), (19.1, 8.5), (8.4, 19.2), (4, 20)]), ("line", [(13.5, 6.9), (17.1, 10.5)])],
    "folder": [("line", [(3, 7), (3, 18.5), (21, 18.5), (21, 9), (11.5, 9), (9.5, 6), (4, 6), (3, 7)])],
    "info": [("circle", 12, 12, 9), ("line", [(12, 11), (12, 16.5)]), ("dot", 12, 7.8, 1.2)],
    "tiles": [("rect", 3, 4, 21, 20, 2.5), ("line", [(12, 4), (12, 20)]), ("line", [(12, 12), (21, 12)])],
    "monitor": [("rect", 3, 4, 21, 16, 2.5), ("line", [(8, 20), (16, 20)]), ("line", [(12, 16), (12, 20)])],
    "x": [("line", [(6, 6), (18, 18)]), ("line", [(18, 6), (6, 18)])],
    "user": [("circle", 12, 8, 4), ("arc", 12, 21, 8, 190, 350)],
    "file": _FILE,
    "file_text": _FILE + [("line", [(9, 13), (16, 13)]), ("line", [(9, 17), (16, 17)])],
    "file_code": _FILE + [("line", [(10.5, 12), (8.5, 14.5), (10.5, 17)]), ("line", [(14.5, 12), (16.5, 14.5), (14.5, 17)])],
    "terminal": [("rect", 3, 5, 21, 19, 2.5), ("line", [(7, 10), (10, 12), (7, 14)]), ("line", [(12, 15), (17, 15)])],
    "reset": [("arc", 12, 12, 8, 40, 330), ("line", [(19.5, 3.5), (19.5, 8.5), (14.5, 8.5)])],
    "up": [("line", [(12, 19), (12, 5)]), ("line", [(6, 11), (12, 5), (18, 11)])],
    "down": [("line", [(12, 5), (12, 19)]), ("line", [(6, 13), (12, 19), (18, 13)])],
    "left": [("line", [(19, 12), (5, 12)]), ("line", [(11, 6), (5, 12), (11, 18)])],
    "right": [("line", [(5, 12), (19, 12)]), ("line", [(13, 6), (19, 12), (13, 18)])],
    "eye": [("circle", 12, 12, 3), ("line", [(2, 12), (6, 7.5), (12, 5.5), (18, 7.5), (22, 12), (18, 16.5), (12, 18.5), (6, 16.5), (2, 12)])],
    "eye_off": [("circle", 12, 12, 3), ("line", [(2, 12), (6, 7.5), (12, 5.5), (18, 7.5), (22, 12), (18, 16.5), (12, 18.5), (6, 16.5), (2, 12)]), ("line", [(4, 4), (20, 20)])],
    "plus": [("line", [(12, 5), (12, 19)]), ("line", [(5, 12), (19, 12)])],
    "check": [("line", [(5, 12.5), (10, 17.5), (19, 7)])],
    "chev_down": [("line", [(6, 9), (12, 15), (18, 9)])],
    "chev_right": [("line", [(9, 6), (15, 12), (9, 18)])],
    "clock": [("circle", 12, 12, 9), ("line", [(12, 7), (12, 12), (15.5, 14)])],
    "home": [("line", [(3, 11), (12, 3), (21, 11)]), ("line", [(5.5, 9.5), (5.5, 20), (18.5, 20), (18.5, 9.5)])],
    "power": [("arc", 12, 13, 7.5, 310, 230), ("line", [(12, 3.5), (12, 11.5)])],
    "image": [("rect", 3, 4, 21, 20, 2.5), ("circle", 9, 9.5, 1.7), ("line", [(3, 17), (9, 12.5), (14, 17), (17, 14.5), (21, 18)])],
    "window": [("rect", 3, 4, 21, 20, 2.5), ("line", [(3, 9), (21, 9)])],
    "dots": [("dot", 6, 12, 1.5), ("dot", 12, 12, 1.5), ("dot", 18, 12, 1.5)],
    "pill_dots": [("rect", 3, 8, 21, 16, 4), ("dot", 8, 12, 1.1), ("dot", 12, 12, 1.1), ("dot", 16, 12, 1.1)],
    "zone_left": [("rect", 2.5, 6, 21.5, 18, 3), ("rect", 5.5, 9, 10.5, 15, 1.2)],
    "zone_center": [("rect", 2.5, 6, 21.5, 18, 3), ("rect", 9.5, 9, 14.5, 15, 1.2)],
    "zone_right": [("rect", 2.5, 6, 21.5, 18, 3), ("rect", 13.5, 9, 18.5, 15, 1.2)],
    "cpu": [("rect", 6, 6, 18, 18, 2), ("rect", 9.5, 9.5, 14.5, 14.5, 1), ("line", [(9, 3), (9, 6)]), ("line", [(15, 3), (15, 6)]), ("line", [(9, 18), (9, 21)]), ("line", [(15, 18), (15, 21)])],
    "battery": [("rect", 3, 8, 19, 16, 2.5), ("line", [(21.5, 11), (21.5, 13)])],
    "wifi": [("arc", 12, 17, 12, 235, 305), ("arc", 12, 17, 7.5, 230, 310), ("dot", 12, 18, 1.3)],
    "volume": [("line", [(4, 9.5), (8, 9.5), (13, 5.5), (13, 18.5), (8, 14.5), (4, 14.5), (4, 9.5)]), ("arc", 13, 12, 5, 300, 60), ("arc", 13, 12, 8.5, 300, 60)],
    "bell": [("line", [(6, 16), (6, 11), (12, 4.5), (18, 11), (18, 16), (20, 18), (4, 18), (6, 16)]), ("line", [(10, 21), (14, 21)])],
    "cloud": [("line", [(7, 18), (17, 18), (20, 15), (17.5, 11.5), (14.5, 12), (12, 8.5), (8.5, 9.5), (7.5, 13), (4, 14.5), (7, 18)])],
    "music": [("line", [(9, 18), (9, 6), (19, 4), (19, 16)]), ("circle", 6.5, 18, 2.5), ("circle", 16.5, 16, 2.5)],
    "code": [("line", [(8, 7), (3, 12), (8, 17)]), ("line", [(16, 7), (21, 12), (16, 17)]), ("line", [(14, 5), (10, 19)])],
    "globe": [("circle", 12, 12, 9), ("line", [(3, 12), (21, 12)]), ("arc", 12, 12, 9, 120, 240), ("arc", 12, 12, 9, -60, 60), ("line", [(12, 3), (12, 21)])],
    "video": [("rect", 3, 6, 15, 18, 3), ("line", [(15, 11), (21, 7.5), (21, 16.5), (15, 13)])],
    "message": [("line", [(4, 5), (20, 5), (20, 16), (11, 16), (7, 20), (7, 16), (4, 16), (4, 5)])],
    "copy": [("rect", 8, 8, 20, 20, 2.5), ("line", [(16, 8), (16, 5.5), (13.5, 3.5), (5.5, 3.5), (4, 5), (4, 14), (5.5, 16), (8, 16)])],
    "box": [("rect", 5, 5, 19, 19, 4)],
    "link": [("line", [(10, 14), (14, 10)]), ("line", [(9, 10), (6.5, 10), (4, 12), (6.5, 14), (9, 14)]), ("line", [(15, 10), (17.5, 10), (20, 12), (17.5, 14), (15, 14)])],
    "arrow_ur": [("line", [(7, 17), (17, 7)]), ("line", [(8, 7), (17, 7), (17, 16)])],
    "keyboard": [("rect", 2.5, 6.5, 21.5, 17.5, 3), ("dot", 6.5, 10.5, 1), ("dot", 10, 10.5, 1), ("dot", 14, 10.5, 1), ("dot", 17.5, 10.5, 1), ("line", [(7, 14.5), (17, 14.5)])],
    "audio": [("line", [(5, 15), (5, 10)]), ("line", [(9, 19), (9, 6)]), ("line", [(13, 16), (13, 9)]), ("line", [(17, 18), (17, 12)]), ("line", [(21, 14), (21, 11)])],
    "title": [("rect", 3, 5, 21, 19, 3), ("line", [(7, 10), (17, 10)]), ("line", [(7, 14), (13, 14)])],
    "trash": [("line", [(4, 7), (20, 7)]), ("line", [(9, 7), (9, 4.5), (15, 4.5), (15, 7)]), ("line", [(6, 7), (7, 20), (17, 20), (18, 7)]), ("line", [(10, 11), (10, 16)]), ("line", [(14, 11), (14, 16)])],
    "archive": [("rect", 3, 4, 21, 9, 2), ("rect", 5, 9, 19, 20, 2), ("line", [(10, 13), (14, 13)])],
    "camera": [("rect", 3, 7, 21, 19, 3), ("circle", 12, 13, 3.5), ("line", [(8.5, 7), (10, 4.5), (14, 4.5), (15.5, 7)])],
}
# the icon of a widget, by its type or name (the first word that matches)
WIDGET_ICONS = (("whkd", "keyboard"), ("notes", "file_text"), ("cava", "audio"), ("active_window", "title"), ("activewindow", "title"),
                ("clock", "clock"), ("workspace", "pill_dots"), ("layout", "tiles"), ("control", "sliders"),
                ("taskbar", "window"), ("systray", "dots"), ("power", "power"), ("home", "home"),
                ("wallpaper", "image"), ("battery", "battery"), ("wifi", "wifi"), ("network", "wifi"),
                ("volume", "volume"), ("media", "music"), ("weather", "cloud"), ("meteo", "cloud"),
                ("cpu", "cpu"), ("memory", "cpu"), ("disk", "cpu"), ("notif", "bell"), ("bell", "bell"),
                ("obs", "video"), ("custom", "code"), ("app", "grid"))


def widget_icon(name, wtype=""):
    key = (name + " " + wtype).lower()
    return next((icon for word, icon in WIDGET_ICONS if word in key), "box")


def file_icon(path):
    ext = Path(path).suffix.lower()
    if ext in (".py", ".css", ".json", ".yaml", ".yml", ".toml", ".lua", ".ahk"):
        return "file_code"
    if ext in (".log", ".txt", ".md", ".env", ""):
        return "file_text"
    return "file"


def icon_pil(name, size, colour, stroke=1.9):
    ss = 8
    S, k = size * ss, size * ss / 24
    w = max(1, round(stroke * k))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for kind, *a in ICONS[name]:
        if kind == "line":
            pts = [(x * k, y * k) for x, y in a[0]]
            d.line(pts, fill=colour, width=w, joint="curve")
            for px, py in (pts[0], pts[-1]):
                d.ellipse([px - w / 2, py - w / 2, px + w / 2, py + w / 2], fill=colour)
        elif kind == "circle":
            cx, cy, r = a
            d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], outline=colour, width=w)
        elif kind == "dot":
            cx, cy, r = a
            d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=colour)
        elif kind == "rect":
            x0, y0, x1, y1, r = a
            d.rounded_rectangle([x0 * k, y0 * k, x1 * k, y1 * k], r * k, outline=colour, width=w)
        elif kind == "arc":
            cx, cy, r, s, e = a
            d.arc([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], s, e, fill=colour, width=w)
    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=None)
def icon(name, size, colour):
    return ImageTk.PhotoImage(icon_pil(name, size, colour))


# ============================================================================================
#  6. DRAWING PARTS  (rounded shapes, toggle, buttons, slider, avatar - smooth, via Pillow)
# ============================================================================================
def _rounded_pil(w, h, r, fill, outline, bw, corners, ss):
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], r * ss, fill=fill, outline=outline, width=round(bw * ss), corners=corners)
    return img.resize((w, h), Image.LANCZOS)


def rounded_big_pil(w, h, r, fill, outline, bw, corners):
    """A big rounded rectangle built from one small, smooth one: its four corners are copied to the corners, and a one pixel slice of each
    edge is stretched along that edge (the straight parts of a rounded rectangle are the same all along). The same picture as drawing it
    big, in a fraction of the time (a card on a wide window used to take 30 ms)."""
    half = r + 3
    S = 2 * half + 2
    small = _rounded_pil(S, S, r, fill, outline, bw, corners, 4)
    big = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for box, at in (((0, 0, half, half), (0, 0)), ((S - half, 0, S, half), (w - half, 0)), ((0, S - half, half, S), (0, h - half)),
                    ((S - half, S - half, S, S), (w - half, h - half))):
        big.paste(small.crop(box), at)
    big.paste(small.crop((half, 0, half + 1, half)).resize((w - 2 * half, half), Image.NEAREST), (half, 0))
    big.paste(small.crop((half, S - half, half + 1, S)).resize((w - 2 * half, half), Image.NEAREST), (half, h - half))
    big.paste(small.crop((0, half, half, half + 1)).resize((half, h - 2 * half), Image.NEAREST), (0, half))
    big.paste(small.crop((S - half, half, S, half + 1)).resize((half, h - 2 * half), Image.NEAREST), (w - half, half))
    big.paste(Image.new("RGBA", (w - 2 * half, h - 2 * half), small.getpixel((half, half))), (half, half))
    return big


@lru_cache(maxsize=None)
def rounded(w, h, r, fill, outline=None, bw=0, corners=None):
    """A rounded rectangle. corners=(top left, top right, bottom right, bottom left) as True/False picks which corners are round."""
    half = r + 3
    if w * h >= 30_000 and w > 2 * half + 2 and h > 2 * half + 2:
        return ImageTk.PhotoImage(rounded_big_pil(w, h, r, fill, outline, bw, corners))
    return ImageTk.PhotoImage(_rounded_pil(w, h, r, fill, outline, bw, corners, 4 if w * h < 150_000 else 2))


@lru_cache(maxsize=None)
def switch(on, accent, ink, track, line, scale=1.0):
    """Noctalia-style toggle: on = accent track with a dark knob, off = dark track with an accent knob."""
    ss = 4
    w, h = round(48 * scale), round(26 * scale)
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], h * ss // 2, fill=accent if on else track, outline=None if on else line, width=round(2 * scale * ss))
    cx = (w - 13 * scale) * ss if on else 13 * scale * ss
    r = 8 * scale * ss
    d.ellipse([cx - r, h * ss / 2 - r, cx + r, h * ss / 2 + r], fill=ink if on else accent)
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=512)
def switch_at(pos, accent, ink, track, line, scale=1.0):
    """The toggle with its knob at pos (0 = off, 1 = on; a spring can push it a little past either end). The knob stretches while
    it moves, the track blends from one colour to the other."""
    ss = 4
    w, h = round(48 * scale), round(26 * scale)
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    mix = max(0.0, min(1.0, pos))
    blend = lambda a, b: "#%02x%02x%02x" % tuple(round(int(a[i:i + 2], 16) * (1 - mix) + int(b[i:i + 2], 16) * mix) for i in (1, 3, 5))
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], h * ss // 2, fill=blend(track, accent), outline=None if mix > .98 else line, width=round(2 * scale * ss * (1 - mix)))
    x = (13 + 22 * pos) * scale * ss
    stretch = 1 + 0.55 * math.sin(math.pi * max(0.0, min(1.0, pos)))  # longest in the middle of the move
    r = 8 * scale * ss
    d.rounded_rectangle([x - r * stretch, h * ss / 2 - r, x + r * stretch, h * ss / 2 + r], r, fill=blend(accent, ink))
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=None)
def pill_button(text, w, h, fill, ink, outline, glyph, font_px, hover, scale=1.0):
    """A button: optional icon, then text. `outline` draws a coloured border instead of a fill."""
    ss = 3
    w, h, font_px = round(w * scale), round(h * scale), font_px * scale
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], int(min(14 * scale, h // 2) * ss), fill=hover if hover else fill,
                        outline=outline, width=2 * ss if outline else 0)
    f = th.font(int(font_px * ss))
    tw = d.textlength(text, font=f) if text else 0
    gs = int(18 * ss * scale) if glyph else 0
    gap = int(8 * ss * scale) if glyph and text else 0
    x = (w * ss - (gs + gap + tw)) / 2
    if glyph:
        g = icon_pil(glyph, 18, ink, 2.0).resize((gs, gs), Image.LANCZOS)
        img.alpha_composite(g, (int(x), int((h * ss - gs) / 2)))
    if text:
        d.text((x + gs + gap, h * ss / 2), text, font=f, fill=ink, anchor="lm")
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=None)
def slider_img(w, frac, accent, track, ink):
    ss, h = 3, 26
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy, x = h * ss / 2, 12 * ss + frac * (w - 24) * ss
    d.rounded_rectangle([0, cy - 3 * ss, w * ss, cy + 3 * ss], 3 * ss, fill=track)
    d.rounded_rectangle([0, cy - 3 * ss, x, cy + 3 * ss], 3 * ss, fill=accent)
    d.ellipse([x - 10 * ss, cy - 10 * ss, x + 10 * ss, cy + 10 * ss], fill=accent)
    d.ellipse([x - 4 * ss, cy - 4 * ss, x + 4 * ss, cy + 4 * ss], fill=ink)
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=None)
def logo_img(size, accent, ink):
    """The ShellFlow mark: a rounded square with three bars that flow."""
    ss = 3
    S = size * ss
    k = S / 96
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S - 1, S - 1], int(S * .27), fill=accent)
    for y, x0, x1 in ((28, 20, 76), (46, 20, 58), (64, 38, 76)):
        d.rounded_rectangle([x0 * k, y * k, x1 * k, (y + 10) * k], 5 * k, fill=ink)
    return ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))


def wall_tile(thumb, picked, current, accent, ink, panel):
    """A wallpaper tile: the thumbnail with rounded corners; a ring when picked, a small "Current" badge when it is the wallpaper."""
    ss = 2
    w, h = thumb.size
    big = thumb.resize((w * ss, h * ss), Image.LANCZOS)
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, big.size[0] - 1, big.size[1] - 1], 16 * ss, fill=255)
    img = Image.new("RGBA", big.size, (0, 0, 0, 0))
    img.paste(big, (0, 0), mask)
    d = ImageDraw.Draw(img)
    if picked:
        d.rounded_rectangle([0, 0, big.size[0] - 1, big.size[1] - 1], 16 * ss, outline=accent, width=5 * ss)
    if current:
        f = th.font(13 * ss)
        tw = d.textlength("Current", font=f)
        d.rounded_rectangle([10 * ss, 10 * ss, 10 * ss + tw + 22 * ss, 36 * ss], 13 * ss, fill=accent)
        d.text((21 * ss, 23 * ss), "Current", font=f, fill=ink, anchor="lm")
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@lru_cache(maxsize=32)
def avatar(path, size, ring, fill, mtime=0):
    """A round profile picture (the file's centre, cropped square), or an empty round placeholder."""
    ss = 3
    S = size * ss
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.ellipse([0, 0, S - 1, S - 1], fill=fill)
    try:
        pic = ImageOps.fit(Image.open(path).convert("RGBA"), (S - 8 * ss, S - 8 * ss), Image.LANCZOS)
        mask = Image.new("L", pic.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, pic.size[0] - 1, pic.size[1] - 1], fill=255)
        base.paste(pic, (4 * ss, 4 * ss), mask)
    except Exception:
        u = icon_pil("user", size // 2, ring, 1.7).resize((S // 2, S // 2), Image.LANCZOS)
        base.alpha_composite(u, (S // 4, S // 4))
    d.ellipse([0, 0, S - 1, S - 1], outline=ring, width=3 * ss)
    return ImageTk.PhotoImage(base.resize((size, size), Image.LANCZOS))


# ============================================================================================
#  7. PAGE LAYOUT  (headings, rows and the controls that sit in them)
# ============================================================================================
class Flow:
    """The content of one page, drawn top to bottom on a scrolling canvas. Controls are placed from the
    right edge inwards and return their left edge, so the next control can sit beside them."""

    def __init__(self, app, cv):
        self.app, self.cv, self.c = app, cv, app.c
        self.cw = int(cv.cget("width"))
        self.y, self.l, self.r, self.first, self.sep = 8, 0, self.cw, True, False
        self.card_y = None
        self.section, self.rows = "", []  # the heading we are under, and every (heading, row title)
        self.sections = []  # collapsible sections: header items, content range, state
        self.glide = None  # lands the section that is still moving
        self.page_name = app.page_name()
        self.hits = {}  # name -> canvas item (the tests click these)

    # structure -------------------------------------------------------------------------
    def heading(self, text, glyph=None, collapsible=True):
        """A section title. A collapsible one is a clickable bar (Noctalia style): click it to open or close the card below."""
        gap_start = self.y
        if not self.first:
            self.y += 24
        self.first, self.sep = False, False
        self.section = text
        if not collapsible:
            x = self.l
            if glyph:
                self.cv.create_image(x, self.y + 16, image=icon(glyph, 22, self.c["accent2"]), anchor="w")
                x += 32
            self.cv.create_text(x, self.y + 16, text=text, anchor="w", fill=self.c["accent2"], font=self.app.f(15, "bold"))
            self.y += 46
            return
        c, cv, top = self.c, self.cv, self.y
        if self.sections:
            self.sections[-1]["bottom"] = gap_start
        key = f"{self.page_name}/{section_name(text)}"
        first = not self.sections
        wanted = self.app.section_open.get(key)
        sec = {"key": key, "top": top, "content_top": top + 56, "bottom": None, "items": [], "header": [], "hidden": {},
               "open": wanted if wanted is not None else (first or not COLLAPSE_BY_DEFAULT), "text": text}
        tag = f"hdr{len(self.sections)}"
        make = lambda hov: rounded(self.cw, 48, 14, c["hover"] if hov else c["card"], c["accent"], 1.5)
        bg = cv.create_image(0, top, image=make(False), anchor="nw", tags=tag)
        x = 18
        if glyph:
            cv.create_image(x, top + 24, image=icon(glyph, 22, c["accent2"]), anchor="w", tags=tag)
            x += 34
        cv.create_text(x, top + 24, text=text, anchor="w", fill=c["accent2"], font=self.app.f(14, "bold"), tags=tag)
        sec["chev"] = cv.create_image(self.cw - 30, top + 24, image=icon("chev_down" if sec["open"] else "chev_right", 22, c["accent2"]), tags=tag)
        sec["header"] = list(cv.find_withtag(tag))
        cv.tag_bind(tag, "<Enter>", lambda e: (cv.itemconfig(bg, image=make(True)), cv.config(cursor="hand2")))
        cv.tag_bind(tag, "<Leave>", lambda e: (cv.itemconfig(bg, image=make(False)), cv.config(cursor="")))
        cv.tag_bind(tag, "<Button-1>", lambda e, s=sec: self.toggle_section(s, sound=True, instant=False))
        self.hits[f"section:{section_name(text)}"] = sec
        self.sections.append(sec)
        self.y += 56

    def toggle_section(self, sec, sound=False, open_=None, instant=True):
        """Open or close one section: its card is hidden and everything below moves up (or back down). With instant=False the
        things below glide with a spring; a click on a header does that, the page setting itself up does not."""
        want = (not sec["open"]) if open_ is None else open_
        if want == sec["open"]:
            return
        if getattr(self, "glide", None):
            self.glide()  # a section is still moving: let it land first
        if sound:
            self.app.sfx.play("tap")
        height = (sec["bottom"] or self.y) - sec["content_top"]
        k = self.sections.index(sec)
        dy = height if want else -height

        def show(on):
            for it in sec["items"]:
                if on:
                    self.cv.itemconfig(it, state=sec["hidden"].get(it, "normal"))
                else:
                    sec["hidden"][it] = self.cv.itemcget(it, "state") or "normal"
                    self.cv.itemconfig(it, state="hidden")
        moving = []
        for later in self.sections[k + 1:]:
            moving += later["header"] + later["items"]
            later["top"] += dy
            later["content_top"] += dy
            if later["bottom"] is not None:
                later["bottom"] += dy
        if instant:
            show(want)
            for it in moving:
                self.cv.move(it, 0, dy)
        else:
            run = {"moved": 0.0, "shown": not want}
            if not want:
                show(False)  # closing: the card goes at once, what is below rises into its place
            view_top, view_bottom, reach = self.cv.canvasy(0), self.cv.canvasy(self.cv.winfo_height()), abs(dy)
            self.cv.dtag("glide")
            for it in moving:  # only what can be seen while it moves is animated; the rest just jumps to where it ends
                bb = self.cv.bbox(it)
                if bb and bb[3] + reach >= view_top and bb[1] - reach <= view_bottom:
                    self.cv.addtag_withtag("glide", it)
                else:
                    self.cv.move(it, 0, dy)

            def step(t):
                goal = dy * soft(t)
                self.cv.move("glide", 0, goal - run["moved"])
                run["moved"] = goal
                if want and not run["shown"] and t > 0.22:  # opening: the card appears as the room opens
                    run["shown"] = True
                    show(True)

            def finish():
                self.cv.dtag("glide")
                self.glide = None

            def land():
                stop()
                self.cv.move("glide", 0, dy - run["moved"])
                run["moved"] = dy
                if not run["shown"]:
                    run["shown"] = True
                    show(True)
                finish()
            stop = animate(self.cv, 300, step, done=finish)
            self.glide = land
        self.total += dy
        sec["bottom"] = (sec["bottom"] or self.y) if sec["bottom"] is None else sec["bottom"]
        sec["open"] = want
        self.cv.itemconfig(sec["chev"], image=icon("chev_down" if want else "chev_right", 22, self.c["accent2"]))
        self.app.section_open[sec["key"]] = want
        save_ui_state(self.app.section_open)
        self.cv.config(scrollregion=(0, 0, self.cw, max(self.total + 24, int(self.cv.cget("height")))))
        self.app.on_scroll(*self.cv.yview())

    def reveal(self, item):
        """Make sure a canvas item is visible: open the section it is in."""
        for sec in self.sections:
            if item in sec["items"] and not sec["open"]:
                self.toggle_section(sec, open_=True)
                return True
        return False

    def note(self, text, colour=None):
        t = self.cv.create_text(self.l, self.y + 4, text=text, anchor="nw", fill=colour or self.c["muted"],
                                font=self.app.f(9), width=self.r - self.l)
        self.y += 22 + 15 * (1 + text.count("\n") + len(text) // 95)
        return t

    def gap(self, n=12):
        self.y += n

    def begin_card(self):
        """Rows after this sit on a rounded card (until end_card)."""
        self.card_y, self.l, self.r, self.sep = self.y, 20, self.cw - 20, False
        self.y += 6

    def end_card(self):
        top, self.y = self.card_y, self.y + 6
        h = self.y - top
        item = self.cv.create_image(0, top, image=rounded(self.cw, h, 18, self.c["card"], self.c["accent"], 1.5), anchor="nw")
        self.cv.tag_lower(item)
        self.card_y, self.l, self.r, self.sep = None, 0, self.cw, False
        self.y += 10

    def row(self, title, desc="", glyph=None, h=56, dim=False, click=None, top=False):
        c = self.c
        if self.sep:
            self.cv.create_line(self.l, self.y, self.r, self.y, fill=c["line"])
        self.sep = True
        self.rows.append((self.section, title))
        yc, x = (self.y + 30 if top else self.y + h / 2), self.l
        if click:
            rect = self.cv.create_rectangle(self.l - 8, self.y + 2, self.r + 8, self.y + h - 2, fill=c["card"] if self.card_y is not None else c["panel"], outline="")
            tag = f"click{rect}"
            self.cv.addtag_withtag(tag, rect)
            fill = c["card"] if self.card_y is not None else c["panel"]
            self.cv.tag_bind(tag, "<Enter>", lambda e: (self.cv.itemconfig(rect, fill=c["hover"]), self.cv.config(cursor="hand2")))
            self.cv.tag_bind(tag, "<Leave>", lambda e: (self.cv.itemconfig(rect, fill=fill), self.cv.config(cursor="")))
            self.cv.tag_bind(tag, "<Button-1>", lambda e: click())
        tags = (tag,) if click else ()
        if glyph:
            self.cv.create_image(x, yc, image=icon(glyph, 22, c["muted"] if dim else c["accent2"]), anchor="w", tags=tags)
            x += 38
        self.cv.create_text(x, yc - (10 if desc else 0), text=title, anchor="w", font=self.app.f(11, "bold"),
                            fill=c["muted"] if dim else c["text"], tags=tags)
        self.last_desc = self.cv.create_text(x, yc + 11, text=desc, anchor="w", fill=c["muted"], font=self.app.f(9), tags=tags) if desc else None
        self.last_desc_x, self.last_row_y = x, yc
        self.y += h
        return yc

    def fit(self, left, yc=None):
        """Shorten the row's description (with an ellipsis) so it never runs under a control that starts at `left`. Only controls
        on the description's own line count: a path box on the line below must not eat it."""
        item = getattr(self, "last_desc", None)
        if item is None or (yc is not None and abs(yc - self.last_row_y) > 24):
            return
        font, text, room = self.app.f(9), self.cv.itemcget(item, "text"), left - self.last_desc_x - 24
        if font.measure(text) <= room:
            return
        while text and font.measure(text + "...") > room:
            text = text[:-1]
        self.cv.itemconfig(item, text=text.rstrip(" ,.;:-") + "...")

    def kv(self, label, value):
        """A small label / value line (system information)."""
        yc = self.y + 14
        self.cv.create_text(self.l, yc, text=label, anchor="w", fill=self.c["muted"], font=self.app.f(10))
        self.cv.create_text(self.l + 170, yc, text=value, anchor="w", fill=self.c["text"], font=self.app.f(10), width=self.r - self.l - 180)
        self.y += 30

    # controls --------------------------------------------------------------------------
    def toggle(self, yc, on, cb, x=None, name=None):
        c, state = self.c, {"on": on, "pos": 1.0 if on else 0.0, "stop": None}
        right = x or self.r
        self.fit(right - 48, yc)
        item = self.cv.create_image(right - 24, yc, image=switch_at(state["pos"], c["accent"], c["ink"], c["input"], c["line"], 1.0), anchor="center")
        render = lambda hov, s: switch_at(round(state["pos"], 2), c["accent"], c["ink"], c["input"], c["line"], s)
        draw = self.app.interact(self.cv, item, render, lambda: click(), sound=None)

        def click():
            state["on"] = not state["on"]
            self.app.sfx.play("on" if state["on"] else "off")
            if state["stop"]:
                state["stop"]()
            start, goal = state["pos"], 1.0 if state["on"] else 0.0

            def step(t):
                state["pos"] = start + (goal - start) * spring(t)  # swings a little past the end, then settles
                draw()
            state["stop"] = animate(self.cv, 340, step)
            cb(state["on"])
        if name:
            self.hits[name] = item
        return right - 48

    def button(self, yc, text, cb, glyph=None, primary=False, x=None, name=None):
        c = self.c
        w = int(self.app.f(10).measure(text) + (18 if glyph else 0) + 46 if text else 40)
        look = (c["accent"], c["ink"], None) if primary else (c["card"], c["accent2"], c["accent"])
        right = x or self.r
        self.fit(right - w, yc)
        render = lambda hov, s: pill_button(text, w, 36, look[0], look[1], look[2], glyph, 13, c["hover"] if hov else None, s)
        item = self.cv.create_image(right - w / 2, yc, image=render(False, 1.0), anchor="center")
        self.app.interact(self.cv, item, render, cb, sound="apply" if primary else "click")
        if name:
            self.hits[name] = item
        return right - w

    def ibutton(self, yc, glyph, cb, x=None, active=False, name=None):
        """A 36 px square icon button (arrows, alignment, folder ...)."""
        c = self.c
        fill, ink = (c["accent"], c["ink"]) if active else (c["input"], c["text"])
        right = x or self.r
        self.fit(right - 38, yc)
        render = lambda hov, s: pill_button("", 38, 36, fill, ink, None, glyph, 13, c["hover"] if hov else None, s)
        item = self.cv.create_image(right - 19, yc, image=render(False, 1.0), anchor="center")
        self.app.interact(self.cv, item, render, cb, sound="click")
        if name:
            self.hits[name] = item
        return right - 38 - 6

    def entry(self, yc, w, text="", x=None, name=None, colour=None):
        c = self.c
        right = x or self.r
        self.fit(right - w, yc)
        self.cv.create_image(right - w, yc, image=rounded(w, 38, 12, c["input"], c["line"], 1), anchor="w")
        box = tk.Entry(self.cv, bd=0, relief="flat", bg=c["input"], fg=colour or c["text"], insertbackground=c["text"],
                       font=self.app.f(10), highlightthickness=0)
        box.insert(0, text)
        self.cv.create_window(right - w + 14, yc, window=box, width=w - 28, height=24, anchor="w")
        box.bind("<Button-1>", lambda e: box.focus_force())
        if name:
            self.hits[name] = box
        return box

    def slider(self, yc, value, lo, hi, cb, unit="px", default=None, w=240, x=None, name=None):
        """A slider with its value; cb(value) runs when you let go, cb(None) when you press reset."""
        c = self.c
        right = x or self.r
        label = self.cv.create_text(right - 36, yc, text="", anchor="e", fill=c["muted"], font=self.app.f(10))
        reset = self.cv.create_image(right, yc, image=icon("reset", 20, c["muted"]), anchor="e")
        left = right - 36 - 64 - w
        self.fit(left, yc)
        state = {"v": value}
        shown = lambda: "default" if state["v"] is None else f"{state['v']} {unit}".strip()
        frac = lambda: 0.0 if hi == lo else ((default if state["v"] is None else state["v"]) - lo) / (hi - lo)
        img = self.cv.create_image(left, yc, anchor="w")

        def draw():
            f = max(0.0, min(1.0, frac())) if (state["v"] is not None or default is not None) else 0.0
            self.cv.itemconfig(img, image=slider_img(w, round(f, 4), c["accent"], c["input"], c["ink"]))
            self.cv.itemconfig(label, text=shown())

        def drag(e):
            f = max(0.0, min(1.0, (e.x - left - 12) / (w - 24)))
            state["v"] = int(round(lo + f * (hi - lo)))
            draw()
        self.cv.tag_bind(img, "<Button-1>", drag)
        self.cv.tag_bind(img, "<B1-Motion>", drag)
        self.cv.tag_bind(img, "<ButtonRelease-1>", lambda e: (self.app.sfx.play("tap"), cb(state["v"])))
        self.cv.tag_bind(img, "<Enter>", lambda e: self.cv.config(cursor="hand2"))
        self.cv.tag_bind(img, "<Leave>", lambda e: self.cv.config(cursor=""))
        self.cv.tag_bind(reset, "<Button-1>", lambda e: (self.app.sfx.play("reset"), state.update(v=None), draw(), cb(None)))
        self.cv.tag_bind(reset, "<Enter>", lambda e: self.cv.config(cursor="hand2"))
        self.cv.tag_bind(reset, "<Leave>", lambda e: self.cv.config(cursor=""))
        draw()
        if name:
            self.hits[name] = img
            self.hits[name + ":reset"] = reset
            self.hits[name + ":set"] = lambda v: (state.update(v=v), draw(), cb(v))
        return left

    def segmented(self, yc, options, current, cb, x=None, name=None):
        """One choice out of a few, as joined buttons."""
        c, state, draws = self.c, {"v": current}, []
        widths = [int(self.app.f(10).measure(o) + 40) for o in options]
        right = x or self.r
        left = right - sum(widths) - 6 * (len(options) - 1)
        self.fit(left, yc)

        def pick(o):
            state["v"] = o
            for d in draws:
                d()
            cb(o)
        xx = left
        for o, wd in zip(options, widths):
            def render(hov, s, o=o, wd=wd):
                on = o == state["v"]
                return pill_button(o, wd, 36, c["accent"] if on else c["input"], c["ink"] if on else c["text"], None, None, 13,
                                   c["hover"] if hov and not on else None, s)
            it = self.cv.create_image(xx + wd / 2, yc, image=render(False, 1.0), anchor="center")
            draws.append(self.app.interact(self.cv, it, render, lambda o=o: pick(o), sound="click"))
            if name:
                self.hits[f"{name}:{o}"] = it
            xx += wd + 6
        return left

    def chips(self, options, selected, cb, name=None):
        """Wrapped chips you can switch on and off (monitors). cb gets the set of selected options."""
        c, state, draws, x, y = self.c, set(selected), [], self.l, self.y
        widths = {o: int(self.app.f(10).measure(o) + 44) for o in options}

        def flip(o):
            state.symmetric_difference_update({o})
            for d in draws:
                d()
            cb(set(state))
        for o in options:
            if x + widths[o] > self.r:
                x, y = self.l, y + 44

            def render(hov, s, o=o):
                on = o in state
                return pill_button(o, widths[o], 36, c["accent"] if on else c["input"], c["ink"] if on else c["text"], None,
                                   "check" if on else None, 13, c["hover"] if hov and not on else None, s)
            it = self.cv.create_image(x + widths[o] / 2, y + 22, image=render(False, 1.0), anchor="center")
            draws.append(self.app.interact(self.cv, it, render, lambda o=o: flip(o), sound="click"))
            if name:
                self.hits[f"{name}:{o}"] = it
            x += widths[o] + 8
        self.y = y + 62

    def finish(self):
        self.total = self.y
        if self.sections:
            self.sections[-1]["bottom"] = self.y
            for it in self.cv.find_all():  # which section each item belongs to (by where it sits)
                bb = self.cv.bbox(it)
                if not bb:
                    continue
                for sec in self.sections:
                    if it not in sec["header"] and sec["content_top"] - 2 <= bb[1] < (sec["bottom"] or self.y):
                        sec["items"].append(it)
                        break
            for sec in list(self.sections):  # sections that start closed
                if not sec["open"]:
                    sec["open"] = True
                    self.toggle_section(sec, open_=False)
        self.cv.config(scrollregion=(0, 0, self.cw, max(self.total + 24, int(self.cv.cget("height")))))
        self.app.on_scroll(*self.cv.yview())


# ============================================================================================
#  8. THE WINDOW  (frame, sidebar, header, tabs, scrolling, saving)
# ============================================================================================
# (name, icon, words the sidebar search matches)
PAGES = (("General", "sliders", "profile name picture avatar actions"),
         ("Display", "monitor", "monitor top bottom opacity komorebi gaps border"),
         ("Colors", "palette", "scheme theme accent wallpaper seed custom"),
         ("Wallpaper", "image", "wallpapers folder picture background desktop picker"),
         ("Widgets", "grid", "layout left center right order alignment"),
         ("Bar", "bar", "spacing capsule workspaces auto hide animation"),
         ("Keybinds", "keyboard", "whkd whkdrc keybinds hotkeys shortcuts keys keyboard komorebi bindings"),
         ("Templates", "layers", "apps discord zed obsidian vscode neovim terminal firefox zen yazi obs folders"),
         ("Edits", "pen", "font colour color hex rgba override"),
         ("Files", "folder", "config yaml css env komorebi whkd edit"),
         ("Backup", "archive", "backup restore zip copy logs log files diagnostic report"),
         ("About", "info", "version system"))


def short_failure(why):
    """A failure from an app theme, short enough for the status line (the administrator-rights one says what to press)."""
    return "needs administrator rights once: Templates > Windhawk > Set up" if "administrator rights" in why else why[:80]


class App:
    def __init__(self, root):
        self.root, self.compact, self.current, self.page = root, False, 0, None
        self.tip_job, self.tip_win, self.tip_mute, self.search_open, self.search_pop = None, None, False, False, None
        self.c = self.make_colors(th.palette(effective=True))  # the colours the bar uses right now
        on, vol = sound_settings()
        self.sfx = Sfx(on, vol)
        self.wall_pick, self.last_sig, self.sig_pending, self.sig_since, self.poll_job = None, None, False, 0.0, None
        self.face = "Poppins" if "Poppins" in set(tkfont.families()) else "Segoe UI"
        self._fonts, self.dirty, self.edits, self.bar, self.note_id, self._monitors = {}, set(), load_edits(), 0, None, None
        self.raw, self.warned, self.footer_hits, self.scheme_pick = {}, False, {}, None
        self.view_results, self.search_job, self.counts, self.menu_gap_last = False, None, {}, 10
        self.kb_text, self.kb_sel, self.kb_down, self.kb_edit, self.kb_job = None, set(), set(), None, None
        self.modal, self.closing, self.born, self.was_down, self.quiet_until = 0, False, time.time(), False, 0.0
        self.section_open = load_ui_state()
        self.cfg, self.kom, self.search = "", None, ""
        self.W, self.x0 = self.window_geometry()  # attached to the bar the window is as wide as the bar, and its sidebar is collapsed
        self.compact = self.attached = self.attach_state()[0] is not None  # attached: it stays where the bar is (no dragging, no moving)
        root.title(APP_NAME)
        root.geometry(f"{self.W}x{H}")
        root.resizable(False, False)
        root.configure(bg=self.c["outer"])
        root.overrideredirect(not NATIVE)  # no Windows title bar: a floating window that komorebi does not tile
        self.inner = tk.Canvas(root, bg=self.c["outer"], bd=0, highlightthickness=0)
        self.inner.place(x=0, y=0, width=self.W, height=H)
        self.draw_ring()
        self.PH = H - 2 * EDGE
        self.side = tk.Canvas(self.inner, bg=self.c["win"], bd=0, highlightthickness=0)
        self.main = tk.Canvas(self.inner, bg=self.c["win"], bd=0, highlightthickness=0)
        self.search_box = tk.Entry(self.side, bd=0, relief="flat", bg=self.c["input"], fg=self.c["text"],
                                   insertbackground=self.c["text"], font=self.f(10), highlightthickness=0)
        self.search_box.bind("<KeyRelease>", lambda e: self.set_search(self.search_box.get()))
        self.search_box.bind("<Return>", lambda e: self.open_first())
        self.search_box.bind("<Escape>", lambda e: self.clear_search())
        self.search_box.bind("<Button-1>", lambda e: self.search_box.focus_force())
        self.drag_on(self.inner, H)  # the margin around the panels drags the window too
        self.drag_on(self.side, 74)
        self.drag_on(self.main, HEAD - 6)
        self.watch_job = self.focus_job = None
        root.bind("<Destroy>", lambda e: setattr(self, "closing", True) if e.widget is root else None, add="+")
        root.bind_all("<MouseWheel>", self.wheel)
        root.bind("<KeyPress>", self.kb_event, add="+")  # the Keybinds page watches your keyboard
        root.bind("<KeyRelease>", self.kb_event, add="+")
        root.bind("<FocusOut>", lambda e: self.kb_down.clear() if e.widget is root else None, add="+")
        root.bind_all("<Button-4>", lambda e: self.wheel(e, 120))
        root.bind_all("<Button-5>", lambda e: self.wheel(e, -120))
        try:  # a quick seed now (the Windows accent); the wallpaper's colour is read in the background below
            self.seed = th.windows_accent_seed()
        except Exception:
            self.seed = 0xFF6B8CCF
        say("Building the first page...")
        self.go(0)
        self.load_seed()
        self.repair_config()
        if not style_block_is_current(self.edits):  # a newer ShellFlow writes better CSS: refresh it (only when it differs)
            save_edits(self.edits)
        self.last_sig, self.wp_sig = self.theme_sig(), th.theme_signature()[:3]
        self.poll_job = root.after(1000, self.poll_theme)

    def page_name(self):
        return "Search" if getattr(self, "view_results", False) else PAGES[self.current][0]

    def tip_later(self, text, yc):
        """Show the page's name next to the collapsed sidebar after a short hover (not again after a click, until the mouse has left)."""
        self.tip_hide()
        if not self.tip_mute:
            self.tip_job = self.root.after(300, lambda: self.tip_show(text, yc))

    def tip_show(self, text, yc):
        self.tip_hide()
        c = self.c
        try:
            font = self.f(10, "bold")
            w, h, key = font.measure(text) + 34, 34, "#010101"  # a rounded pill: the corners are see-through (the key colour)
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=key)
            try:
                win.attributes("-transparentcolor", key)
            except tk.TclError:
                pass
            pill = tk.Canvas(win, width=w, height=h, bg=key, bd=0, highlightthickness=0)
            pill.pack()
            pill.photo = rounded(w, h, 15, c["accent"])
            pill.create_image(0, 0, image=pill.photo, anchor="nw")
            pill.create_text(w / 2, h / 2, text=text, fill=c["ink"], font=font)
            win.geometry(f"+{self.side.winfo_rootx() + self.sw + 8}+{self.side.winfo_rooty() + int(yc) - 18}")
            self.tip_win = win
        except tk.TclError:
            self.tip_win = None

    def tip_hide(self):
        if self.tip_job:
            try:
                self.root.after_cancel(self.tip_job)
            except tk.TclError:
                pass
            self.tip_job = None
        if self.tip_win is not None:
            try:
                self.tip_win.destroy()
            except tk.TclError:
                pass
            self.tip_win = None

    def interact(self, canvas, item, render, cb, sound="click", hide_idle=False, bind_to=None, tip=None):
        """Make a centred image item a control, Material 3 expressive: it swells under the mouse, squashes when pressed and springs
        back, changes colour, makes a sound and runs cb. render(hover, scale) -> PhotoImage. Returns a redraw function."""
        st = {"hover": False, "down": False, "scale": 1.0, "stop": None}

        def draw():
            try:
                canvas.itemconfig(item, image=render(st["hover"], round(st["scale"], 2)))
            except tk.TclError:
                pass

        def aim(target, ms, ease):
            """Move the scale to `target` over ms milliseconds."""
            if st["stop"]:
                st["stop"]()
            start = st["scale"]

            def step(t):
                st["scale"] = start + (target - start) * ease(t)
                draw()

            def done():
                if hide_idle and abs(st["scale"] - 1.0) < 0.002 and not st["hover"]:
                    canvas.itemconfig(item, state="hidden")
            st["stop"] = animate(canvas, ms, step, done)

        def rest():
            return PRESS_SCALE if st["down"] else HOVER_SCALE if st["hover"] else 1.0
        target = bind_to or item  # a tag lets a whole row (icon, text, background) react as one control

        def enter(_):
            st["hover"] = True
            if tip:
                self.tip_later(*tip)
            canvas.config(cursor="hand2")
            canvas.itemconfig(item, state="normal")
            aim(rest(), 260, soft)

        def leave(_):
            st["hover"], st["down"] = False, False
            if tip:
                self.tip_hide()
                self.tip_mute = False
            canvas.config(cursor="")
            if hide_idle:  # a hover highlight (the sidebar's) goes the moment the mouse leaves
                if st["stop"]:
                    st["stop"]()
                st["scale"] = 1.0
                canvas.itemconfig(item, state="hidden")
            else:
                aim(1.0, 140, lambda t: 1 - (1 - t) ** 3)  # quick and without a bounce

        def press(_):
            st["down"] = True
            if tip:
                self.tip_hide()
                self.tip_mute = True
            self.sfx.play(sound)
            aim(PRESS_SCALE, 80, soft)
            cb()
            draw()

        def release(_):
            if st["down"]:
                st["down"] = False
                aim(rest(), 320, spring)  # back with a bounce
        canvas.tag_bind(target, "<Enter>", enter)
        canvas.tag_bind(target, "<Leave>", leave)
        canvas.tag_bind(target, "<ButtonPress-1>", press)
        canvas.tag_bind(target, "<ButtonRelease-1>", release)
        return draw

    def attach_state(self):
        """(edge, "center"): the screen edge ShellFlow is attached to ("top" / "bottom" = flush against the bar) or None."""
        if th.env("YASB_ATTACH") != "1":
            return None, "center"
        return bar_edge(self.cfg_text())[0], "center"

    def window_geometry(self):
        """(window width, window x or None). Normally W wide in the middle of the screen. Attached to the bar, the visible window is as
        wide as the bar minus 10 px on each side (so it never covers the bar's rounded ends), and sits there."""
        self.y0, self.dy = None, 0
        if not self.attach_state()[0]:
            return W, None
        inset = int(th.env("YASB_ATTACH_INSET") or 15) if (th.env("YASB_ATTACH_INSET") or "15").lstrip("-").isdigit() else 15
        self.dy = int(th.env("YASB_ATTACH_DY") or 0) if (th.env("YASB_ATTACH_DY") or "0").lstrip("-").isdigit() else 0
        work, _ = th.monitor_info()
        box = bar_box(self.cfg_text(), work)
        if box is None:  # the bar's width is not known: the normal width, in the middle of the screen, against the bar
            inner = W - 2 * MARGIN
            return W, work[0] + (work[2] - work[0] - inner) // 2 - MARGIN
        x, width, edge_y = box
        inner = min(max(MIN_ATTACHED, width - 2 * inset), work[2] - work[0] - 2 * inset)
        left = x + inset if width - 2 * inset >= inner else x + (width - inner) // 2  # a bar narrower than the minimum: centred on it
        self.y0 = edge_y  # where the visible bar ends: the window's top (a top bar) or bottom (a bottom bar) is exactly there
        return inner + 2 * MARGIN, left - MARGIN  # the ring is MARGIN in from the window's edge

    def relaunch(self):
        """Close this window and open a new one (the width and the sidebar of an attached window are decided when it starts)."""
        env = dict(os.environ, SHELLFLOW_REPLACE=str(os.getpid()))
        flags = {"creationflags": CREATE_NO_WINDOW | 0x00000008} if os.name == "nt" else {}
        try:
            subprocess.Popen([str(th.pythonw()), str(th.HERE / "theme.py"), "settings"], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True, **flags)
        except OSError as e:
            return self.say(f"Could not reopen ShellFlow: {e}")
        self.say("Reopening...")
        self.root.after(150, self.force_destroy)

    def draw_ring(self):
        """The accent ring around the window. Attached to the bar, the two corners against the bar are square and the ring touches the
        window's edge there (the rest of the window is see-through)."""
        self.inner.delete("ring")
        edge = self.attach_state()[0]
        top, bottom = (0 if edge == "top" else MARGIN), (H if edge == "bottom" else H - MARGIN)
        corners = (edge != "top", edge != "top", edge != "bottom", edge != "bottom") if edge else None
        self.inner.create_image(MARGIN, top, anchor="nw", tags="ring", image=rounded(
            self.W - 2 * MARGIN, bottom - top, RING_R, self.c["win"], self.c["border"], BORDER, corners))
        self.inner.tag_lower("ring")
        try:  # Windows: everything outside the ring is see-through, so the shape is exactly the ring
            self.root.attributes("-transparentcolor", self.c["outer"] if edge else "")
        except tk.TclError:
            pass
        th.window_shadow(self.root, not edge)  # and no drop shadow: it showed as a dark band below the ring


    def make_colors(self, P):
        return {"border": P.l1, "outer": P.t(.035), "win": P.t(.06), "panel": P.t(.15), "card": P.t(.21), "input": P.t(.27),
                "hover": P.t(.36), "line": P.t(.34), "accent": P.l1, "accent_dark": P.d1, "accent2": P.l2, "ink": P.t(.07),
                "text": "#ffffff", "muted": "#b3b3b3"}

    # sizes and fonts ------------------------------------------------------------------------
    @property
    def sw(self):
        return SIDE_COMPACT if self.compact else SIDE_FULL

    @property
    def mw(self):
        return self.W - 2 * EDGE - GAP - self.sw

    def f(self, size, weight="normal"):
        key = (size, weight)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(family=self.face, size=-round(size * 1.35), weight=weight)
        return self._fonts[key]

    # staging: changes wait here until you press Apply ---------------------------------------
    LABELS = {"scheme": "colour scheme", "wall": "wallpaper", "whkd": "keybinds", "cfg": "bar layout and options", "style": "fonts, spacing, opacity",
              "colours": "custom colours", "kom": "komorebi"}

    def stage(self, key):
        self._index_cache = None
        self.dirty.add(key)
        self.warned = False
        self.draw_footer()

    def cfg_text(self):
        if "cfg" not in self.dirty:
            try:
                self.cfg = CONFIG_YAML.read_text(encoding="utf-8")
            except OSError:
                self.cfg = ""
        return self.cfg

    def cfg_change(self, text):
        self.cfg = text
        self.stage("cfg")

    def style_change(self, **changes):
        for k, v in changes.items():
            if v is None or v == "":
                self.edits.pop(k, None)
            else:
                self.edits[k] = v
        self.stage("style")

    def kom_data(self):
        if "kom" not in self.dirty:
            self.kom = load_komorebi()
        return self.kom

    def apply_all(self):
        """Write everything that is waiting. One write per file, so YASB and komorebi reload once."""
        if not self.dirty:
            return self.say("Nothing to apply")
        wrong = [v for v, t in self.raw.items() if t and parse_colour(t) is None]
        if wrong:
            return self.say("Not a colour: " + ", ".join(wrong))
        fails = {}
        try:
            if "colours" in self.dirty:
                cols, base = dict(self.edits.get("colours", {})), current_colours(base_only=True)
                for var, text in self.raw.items():
                    cols.pop(var, None) if not text else cols.update({var: text})
                cols = {v: t for v, t in cols.items() if t.lower() != base.get(v, "")}
                self.edits = {k: v for k, v in self.edits.items() if k != "colours"}
                if cols:
                    self.edits["colours"] = cols
            if "cfg" in self.dirty:
                save_config(self.cfg)
            if self.dirty & {"style", "colours", "cfg"}:
                save_edits(self.edits)
            if "colours" in self.dirty:  # the custom scheme is on while you have custom colours, off otherwise
                if th.custom_colours():
                    fails.update(th.apply("custom", self.seed) or {})
                elif th.current_variant() == "custom":
                    fails.update(th.apply("windows") or {})
            if "kom" in self.dirty:
                save_komorebi(self.kom)
                reload_komorebi()
            if "whkd" in self.dirty and self.kb_text is not None:
                whkdrc_path().parent.mkdir(parents=True, exist_ok=True)
                whkdrc_path().write_text(self.kb_text, encoding="utf-8")
                self.whkd_note = restart_whkd()
                self.kb_text = None
            if "wall" in self.dirty and self.wall_pick:
                if not set_wallpaper(self.wall_pick):
                    return self.say("Could not set the wallpaper")
                threading.Timer(2.5, th.refresh_all).start()  # once Windows has settled: new seed colour -> apps follow
            if "scheme" in self.dirty and self.scheme_pick:  # an explicit choice wins over custom colours
                fails.update(th.apply(self.scheme_pick, self.seed) or {})
        except Exception as e:
            th.log("settings apply")
            return self.say(f"Could not apply: {e}")
        self.dirty.clear()
        self.raw.clear()
        self.scheme_pick = self.wall_pick = None
        names = {r[0]: r[1] for r in th.APP_TABLE}
        problem = ("   -   but " + "; ".join(f"{names.get(k, k)} {short_failure(v)}" for k, v in fails.items())) if fails else ""
        if fails:
            self.sfx.play("error")
        self.say("Applied  -  YASB reloads once" + (f"; {self.whkd_note}" if getattr(self, "whkd_note", "") else "") + problem)
        self.whkd_note = ""
        self.defer_refresh()

    def reset_all(self):
        """Throw the unapplied changes away: everything goes back to what is on disk."""
        self.dirty.clear()
        self.raw.clear()
        self.cfg, self.kom, self.edits, self.warned, self.scheme_pick, self.wall_pick = "", None, load_edits(), False, None, None
        self.kb_text = self.kb_edit = None
        if not getattr(self, "quiet_reset", False):
            self.say("Unapplied changes discarded")
        self.defer_refresh()

    def say(self, text):
        """The little status text in the header."""
        self.note_text, self.note_time = text, time.time()
        if self.note_id is not None:
            self.main.itemconfig(self.note_id, text=text)

    def draw_footer(self):
        """The bar at the bottom of the page: what is waiting, then Reset and Apply."""
        c, cv = self.c, self.main
        cv.delete("footer")
        y = self.PH - FOOT / 2 - 4
        waiting = [self.LABELS[k] for k in ("scheme", "wall", "whkd", "cfg", "style", "colours", "kom") if k in self.dirty]
        cv.create_line(PADX, y - FOOT / 2 + 2, self.mw - PADX, y - FOOT / 2 + 2, fill=c["line"], tags="footer")
        cv.create_text(PADX, y, text=("Not applied yet: " + ", ".join(waiting)) if waiting else "Everything is applied",
                       anchor="w", fill=c["accent2"] if waiting else c["muted"], font=self.f(10, "bold" if waiting else "normal"), tags="footer")
        x = self.mw - PADX
        for name, label, w, glyph, cb, look in (("apply", "Apply", 112, "check", self.apply_all, (c["accent"], c["ink"], None)),
                                                ("reset", "Reset", 104, "reset", self.reset_all, (c["card"], c["accent2"], c["accent"]))):
            render = lambda hov, s, label=label, w=w, glyph=glyph, look=look: pill_button(label, w, 40, look[0], look[1], look[2], glyph, 13, c["hover"] if hov and look[2] else None, s)
            it = cv.create_image(x - w / 2, y, image=render(False, 1.0), anchor="center", tags=("footer", "btn"))
            self.interact(cv, it, render, cb, sound="apply" if name == "apply" else "reset")
            self.footer_hits[name] = it
            x -= w + 10

    def footer_images(self):
        c = self.c
        return (pill_button("Apply", 112, 40, c["accent"], c["ink"], None, "check", 13, None),
                pill_button("Reset", 104, 40, c["card"], c["accent2"], c["accent"], "reset", 13, None))

    # frame -------------------------------------------------------------------------------------
    def layout(self):
        self.side.place(x=EDGE, y=EDGE, width=self.sw, height=self.PH)
        self.main.place(x=EDGE + self.sw + GAP, y=EDGE, width=self.mw, height=self.PH)

    def draw_side(self):
        c, cv, sw = self.c, self.side, self.sw
        cv.delete("all")
        cv.create_image(0, 0, image=rounded(sw, self.PH, 22, c["panel"], c["accent"], 1.5), anchor="nw")
        self.tip_hide()
        if self.attached:  # attached: the sidebar cannot be opened, so its top button is search (it opens a search box in the header)
            burger = cv.create_image(sw / 2, 38, image=icon("search", 24, c["accent2"] if self.search_open else c["text"]), tags="searchbtn")
            cv.tag_bind("searchbtn", "<Button-1>", lambda e: self.toggle_search())
            cv.tag_bind("searchbtn", "<Enter>", lambda e: (cv.config(cursor="hand2"), self.tip_later("Search", 38)))
            cv.tag_bind("searchbtn", "<Leave>", lambda e: (cv.config(cursor=""), self.tip_hide()))
        else:
            burger = cv.create_image(sw / 2 if self.compact else 36, 38, image=icon("panel", 24, c["text"]))
            cv.tag_bind(burger, "<Button-1>", lambda e: self.toggle_side())
            cv.tag_bind(burger, "<Enter>", lambda e: cv.config(cursor="hand2"))
            cv.tag_bind(burger, "<Leave>", lambda e: cv.config(cursor=""))
        if not self.compact:
            cv.create_image(80, 38, image=logo_img(32, c["accent"], c["ink"]))
            cv.create_text(104, 38, text=APP_NAME, anchor="w", fill=c["accent2"], font=self.f(15, "bold"))
        y = 84
        if not self.compact:
            cv.create_image(18, y + 22, image=rounded(sw - 36, 44, 22, c["input"], c["line"], 1), anchor="w")
            cv.create_image(40, y + 22, image=icon("search", 20, c["muted"]))
            cv.create_window(60, y + 22, window=self.search_box, width=sw - 100, height=26, anchor="w")
            y += 58
        else:
            self.search_box.place_forget()
        self.nav_hits = {}
        for i, (name, glyph, _) in enumerate(PAGES):
            pos = i
            yc, tag, on = y + 24 + pos * 48, f"nav{i}", i == self.current and not self.view_results
            hits = self.counts.get(name, 0)
            ink = c["ink"] if on else (c["muted"] if self.search and not hits else c["text"])
            cv.create_rectangle(14, yc - 21, sw - 14, yc + 21, fill=c["panel"], outline="", tags=tag)  # the whole row is clickable
            if on:
                bg = cv.create_image(sw / 2, yc, image=rounded(sw - 28, 42, 21, c["accent"]), tags=tag)
                self.sel_bg = bg
            else:
                bg = cv.create_image(sw / 2, yc, image=rounded(sw - 28, 42, 21, c["hover"], c["accent"], 1.5), tags=tag, state="hidden")
                self.interact(cv, bg, lambda hov, s, sw=sw: rounded(round((sw - 28) * s), round(42 * s), round(21 * s), c["hover"], c["accent"], 1.5),
                              lambda i=i: self.nav(i), sound="tap", hide_idle=True, bind_to=tag, tip=(name, yc) if self.compact else None)
            cv.create_image(sw / 2 if self.compact else 42, yc, image=icon(glyph, 22, ink), tags=tag)
            if not self.compact:
                cv.create_text(66, yc, text=name, anchor="w", fill=ink, font=self.f(11, "bold" if on else "normal"), tags=tag)
            if self.search and hits and not self.compact:  # how many settings on this page match
                cv.create_image(sw - 44, yc, image=rounded(30, 24, 12, c["accent"]), tags=tag)
                cv.create_text(sw - 44, yc, text=str(hits), fill=c["ink"], font=self.f(9, "bold"), tags=tag)
            if on:
                cv.tag_bind(tag, "<Button-1>", lambda e, i=i: self.nav(i))
                if self.compact:
                    cv.tag_bind(tag, "<Enter>", lambda e, n=name, y=yc: self.tip_later(n, y), add="+")
                    cv.tag_bind(tag, "<Leave>", lambda e: (self.tip_hide(), setattr(self, "tip_mute", False)), add="+")
            self.nav_hits[name] = bg
        if self.search and not self.attached:
            self.search_box.focus_set()
            self.search_box.icursor("end")

    def toggle_search(self):
        """Attached window: show or hide the search box in the header (typing searches every setting, like the sidebar's box)."""
        self.search_open = not self.search_open
        if not self.search_open:
            return self.clear_search()
        self.go(self.current, keep=True)

    def draw_search_pop(self):
        """The search box of an attached window, in the header next to the close button."""
        if not self.attached or not self.search_open:
            return
        c, mw = self.c, self.mw
        w = max(180, min(340, mw - 330))
        if self.search_pop is None:
            e = self.search_pop = tk.Entry(self.main, bd=0, relief="flat", bg=c["input"], fg=c["text"], insertbackground=c["text"], font=self.f(10), highlightthickness=0)
            e.bind("<KeyRelease>", lambda ev: self.set_search(e.get()))
            e.bind("<Return>", lambda ev: self.open_first())
            e.bind("<Escape>", lambda ev: self.toggle_search())
            e.bind("<Button-1>", lambda ev: e.focus_force())
            if self.search:
                e.insert(0, self.search)
        self.main.create_image(mw - 84 - w, 40, image=rounded(w, 38, 19, c["input"], c["accent_dark"], 2), anchor="w")
        self.main.create_window(mw - 84 - w + 18, 40, window=self.search_pop, width=w - 36, height=24, anchor="w")
        self.search_pop.focus_set()
        self.search_pop.icursor("end")

    def drag_on(self, cv, height):
        """Dragging the top of a panel moves the window (the header is the title bar)."""
        drag = {}

        def press(e):
            current = cv.find_withtag("current")
            drag.clear()
            if self.attached:  # attached to the bar: the window cannot be dragged away from it
                return
            if e.y < height and not any(t.startswith(("nav", "btn", "tab")) for it in current for t in cv.gettags(it)):
                drag.update(x=e.x_root - self.root.winfo_x(), y=e.y_root - self.root.winfo_y())
        cv.bind("<ButtonPress-1>", press, add="+")
        cv.bind("<B1-Motion>", lambda e: self.root.geometry(f"+{e.x_root - drag['x']}+{e.y_root - drag['y']}") if drag else None, add="+")

    def draw_main(self, title, glyph, tabs=None, current=0, on_tab=None):
        c, cv, mw = self.c, self.main, self.mw
        cv.delete("all")
        if getattr(self, "cv", None) is not None:
            self.cv.destroy()  # the old page (only ever called outside a click on it: see defer)
        cv.create_image(0, 0, image=rounded(mw, self.PH, 22, c["panel"], c["accent"], 1.5), anchor="nw")
        cv.create_image(34, 40, image=icon(glyph, 26, c["accent2"]))
        cv.create_text(60, 40, text=title, anchor="w", fill=c["accent2"], font=self.f(20, "bold"))
        recent = getattr(self, "redraw", False) and time.time() - getattr(self, "note_time", 0) < 3  # same page redrawn: keep what was just said
        self.note_id = cv.create_text(mw - 92, 40, text=self.note_text if recent else "", anchor="e", fill=c["muted"], font=self.f(9))
        close = cv.create_image(mw - 40, 40, image=self.close_img(False, 1.0), tags="btn")
        self.interact(cv, close, lambda hov, s: self.close_img(hov, s), self.close, sound="reset")
        self.close_item = close
        top = HEAD
        self.tab_hits = {}
        if tabs:
            n, total = len(tabs), mw - 2 * PADX
            seg = (total - 8 * (n - 1)) / n
            for i, label in enumerate(tabs):
                on = i == current
                x = PADX + i * (seg + 8)
                render = lambda hov, s, label=label, on=on: pill_button(
                    label, int(seg), 38, c["accent"] if on else c["card"], c["ink"] if on else c["text"], None if on else c["line"], None, 13,
                    c["hover"] if hov and not on else None, s)
                it = cv.create_image(x + seg / 2, top + 18, anchor="center", tags="tab", image=render(False, 1.0))
                self.interact(cv, it, render, lambda i=i: on_tab(i), sound="tap")
                self.tab_hits[label] = it
            top += 54
        self.top = top + 6
        self.cv = tk.Canvas(cv, bg=c["panel"], bd=0, highlightthickness=0, yscrollincrement=26,
                            width=mw - 2 * PADX - 10, height=self.PH - self.top - FOOT - 14)
        self.cv.config(yscrollcommand=self.on_scroll)
        cv.create_window(PADX, self.top, window=self.cv, anchor="nw")
        self.sb_x, self.sb_w = mw - 30, 12
        self.track = cv.create_image(self.sb_x, self.top, image=rounded(self.sb_w, 40, 6, c["input"]), anchor="nw", state="hidden", tags="scroll")
        self.thumb = cv.create_image(self.sb_x, self.top, image=rounded(self.sb_w, 40, 6, c["accent"]), anchor="nw", state="hidden", tags="scroll")
        self.sb_grab = None
        cv.tag_bind(self.thumb, "<ButtonPress-1>", self.sb_press)
        cv.tag_bind(self.thumb, "<B1-Motion>", self.sb_drag)
        cv.tag_bind(self.thumb, "<ButtonRelease-1>", lambda e: setattr(self, "sb_grab", None))
        cv.tag_bind(self.track, "<Button-1>", self.sb_track_click)
        for it in (self.thumb, self.track):
            cv.tag_bind(it, "<Enter>", lambda e: cv.config(cursor="hand2"))
            cv.tag_bind(it, "<Leave>", lambda e: cv.config(cursor=""))
        self.footer_hits = {}
        self.draw_footer()
        self.draw_search_pop()
        return Flow(self, self.cv)

    @lru_cache(maxsize=16)
    def close_img(self, hover, scale=1.0):
        c, S = self.c, round(40 * scale)
        img = Image.new("RGBA", (S * 4, S * 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([4, 4, S * 4 - 5, S * 4 - 5], outline=c["accent"], fill=c["input"] if hover else None, width=8)
        x = icon_pil("x", round(20 * scale), c["accent2"], 2.2).resize((round(20 * scale) * 4, round(20 * scale) * 4), Image.LANCZOS)
        img.alpha_composite(x, ((S * 4 - x.size[0]) // 2, (S * 4 - x.size[1]) // 2))
        return ImageTk.PhotoImage(img.resize((S, S), Image.LANCZOS))

    def sb_track_height(self):
        return self.PH - self.top - FOOT - 14

    def on_scroll(self, first, last):
        """The scrollbar at the right edge: a track and a thumb that follows the page (and can be dragged)."""
        first, last = float(first), float(last)
        if not hasattr(self, "thumb"):
            return
        if last - first >= 0.999:
            self.main.itemconfig(self.thumb, state="hidden")
            self.main.itemconfig(self.track, state="hidden")
            return
        track = self.sb_track_height()
        h = max(44, int(track * (last - first)))
        self.main.itemconfig(self.track, image=rounded(self.sb_w, track, 6, self.c["input"]), state="normal")
        self.main.itemconfig(self.thumb, image=rounded(self.sb_w, h, 6, self.c["accent"]), state="normal")
        self.main.coords(self.thumb, self.sb_x, self.top + (track - h) * (first / max(1e-6, 1 - (last - first))))
        self.thumb_h = h

    def sb_press(self, e):
        self.sb_grab = e.y - self.main.coords(self.thumb)[1]

    def sb_drag(self, e):
        if self.sb_grab is None:
            return
        track, h = self.sb_track_height(), getattr(self, "thumb_h", 44)
        top = max(self.top, min(self.top + track - h, e.y - self.sb_grab))
        span = max(1.0, track - h)
        first, last = self.cv.yview()
        self.cv.yview_moveto((top - self.top) / span * (1 - (last - first)))

    def sb_track_click(self, e):
        thumb_y = self.main.coords(self.thumb)[1]
        self.cv.yview_scroll(-1 if e.y < thumb_y else 1, "pages")

    def wheel(self, event, delta=None):
        cv = getattr(self, "cv", None)
        if cv is not None and cv.winfo_exists():
            first, last = cv.yview()
            if first > 0 or last < 1:
                cv.yview_scroll(-int((delta or event.delta) / 120), "units")

    # navigation --------------------------------------------------------------------------------
    def toggle_side(self):
        if self.attach_state()[0]:
            return  # attached to the bar the sidebar stays collapsed
        self.compact = not self.compact
        self.root.after(15, lambda: self.go(self.current))

    # search: the settings on every page, not only the page names -------------------------------
    def search_index(self):
        """Every searchable setting as (page, card, title, description, extra words). Built once, kept for two seconds (or until something
        is staged): typing in the search box asks for it on every key."""
        cached = getattr(self, "_index_cache", None)
        if cached and time.time() - cached[0] < 2.0:
            return cached[1]
        index = self.build_search_index()
        self._index_cache = (time.time(), index)
        return index

    def build_search_index(self):
        I = []
        add = lambda page, card, title, desc="", kw="": I.append((page, card, title, desc, kw))
        for name, _, words in PAGES:  # a page matches by its name only; its settings are listed under their own cards
            add(name, "Page", name, "Open the " + name + " page")
        add("General", "Profile", "Name", "Your name", "username")
        add("General", "Profile", "Profile picture", "A round picture of you", "avatar photo pfp image choose clear")
        add("General", "Quick actions", "Open the config folder", "Your YASB folder", "explorer")
        add("General", "Quick actions", "Write all the app themes", "Discord, Zed, Obsidian, VS Code and the others", "apply templates")
        add("General", "Quick actions", "Reload komorebi", "Runs komorebic reload-configuration", "restart tiling")
        add("General", "Window", "Attach to the bar", "Open ShellFlow flush against the bar, as wide as the bar, with square corners where it touches and a collapsed sidebar", "attached menu dock top bottom position width tooltip")
        if th.env("YASB_ATTACH") == "1":
            add("General", "Window", "Inset from the bar's ends", "How far in from each end of the bar the attached window starts", "attach margin edge gap")
            add("General", "Window", "Move up or down", "Nudges the attached window against the bar", "attach offset vertical position")
        add("General", "Window", "Motion", "Springy animations for buttons, switches, sections and pages", "animation expressive material spring")
        add("General", "Sounds", "Click sounds", "Pixel-style sounds for buttons and toggles", "audio sound effects mute")
        add("General", "Sounds", "Vary the pitch", "Each click a little higher or lower than the last", "pitch variation random sound tone")
        add("General", "Sounds", "Sounds on the YASB bar", "A tick when you click the bar or its menus", "audio click yasb widgets buttons helper")
        add("General", "Sounds", "Volume", "How loud the sounds are", "audio loudness")
        add("General", "Sounds", "Preview", "Plays the sounds", "audio test")
        add("General", "Sync", "Keep app themes in sync", "Rewrites the app themes when the wallpaper or accent changes", "background watcher wallpaper discord startup auto")
        add("General", "Sync", "Background helper", "Whether the helper (app sync and bar sounds) is running and starts with Windows", "restart status autostart startup sounds")
        add("Wallpaper", "Folder", "Wallpapers folder", "The folder the YASB wallpapers widget uses", "wallpaper pictures images background")
        add("Display", "Bar placement", "Monitor", "Which screens show the bar", "screen display primary yasbc")
        add("Display", "Bar placement", "Position", "Top or bottom of the screen", "top bottom edge")
        add("Display", "Bar placement", "Bar height", "In pixels", "size thick")
        add("Display", "Bar placement", "Space above the bar", "Gap between the top screen edge and the bar", "margin padding")
        add("Display", "Bar placement", "Space below the bar", "Gap between the bar and the bottom screen edge", "margin padding bottom")
        add("Display", "Bar placement", "Background opacity", "How see-through the bar background is", "transparent transparency alpha")
        for t, d, k in (("Outer gap", "Space between the windows and the screen edge", "padding workspace"), ("Inner gap", "Space between tiled windows", "padding container"),
                        ("Border width", "Thickness of the focus border", "outline"), ("Border offset", "Moves the border in or out", "outline"),
                        ("Focus border", "Draw a border around the focused window", "outline highlight"), ("Border style", "System, rounded or square", "outline corners"),
                        ("New windows", "Create a new tile, or append to the focused one", "behaviour container"),
                        ("Mouse follows focus", "Move the pointer to the window you focus", "cursor"), ("Transparency", "Make unfocused windows see-through", "opacity alpha"),
                        ("Animations", "Animate windows when they tile", "animation motion")):
            add("Display", "Komorebi", t, d, "tiling window manager " + k)
        for n in ("Windows accent", "Content", "Fidelity", "Tonal Spot", "Monochrome", "Expressive", "Neutral", "Vibrant", "Fruit Salad", "Custom"):
            add("Colors", "Scheme", n, "A colour scheme for the bar", "theme palette material you")
        add("Colors", "Source", "Seed colour", "The dominant colour of your wallpaper", "wallpaper")
        add("Colors", "Source", "Windows accent", "The colour everything uses when the scheme is Windows accent", "")
        text = self.cfg_text()
        for name, typ in read_widgets(text).items():
            add("Widgets", "Layout", name, typ.split(".")[-1] if typ else "widget", "widget left center right order move alignment on off show hide")
        add("Widgets", "Hidden", "Hidden widgets", "Switched off, on no side of the bar, or not in config.yaml yet", "hidden disabled inactive off available add")
        defined = set(read_widgets(text).values())
        for key, title, desc, *_ in CATALOG:
            if CATALOG_BY_KEY[key][4] not in defined:
                add("Widgets", "Hidden", title, desc, "new widget add hidden available keyboard notes control center active window cava audio visualizer whkd hotkeys")
        if "yasb.active_window.ActiveWindowWidget" in defined:
            for t, d, k in (("Truncate title after", "Characters shown before the title is cut", "length max ellipsis"),
                            ("Show the app icon", "An icon in front of the title", "icon"), ("Icon size", "Only used when the icon is on", "")):
                add("Bar", "Active window title", t, d, "active window title " + k)
        if "yasb.cava.CavaWidget" in defined:
            for t, d, k in (("Cava bars", "How many bars", "number count"), ("Cava bar width", "Thickness of each bar", "thick"),
                            ("Cava bar spacing", "Space between the bars", "gap"), ("Cava bar height", "Tallest a bar can get", "size"),
                            ("Cava colour", "Hex colour of the bars", "color hex")):
                add("Bar", "Audio visualizer (Cava)", t, d, "cava audio visualizer music " + k)
        add("Bar", "Capsules", "Same spacing on both sides", "Off: set the left and right separately", "left right link")
        add("Bar", "Capsules", "Widget spacing", "Space between capsules, left and right", "gap margin between")
        add("Bar", "Capsules", "Same padding on both sides", "Off: set the left and right separately", "left right link")
        add("Bar", "Capsules", "Capsule padding", "Space inside a capsule", "size width inner")
        if defined & set(CATALOG_BY_TYPE):
            add("Bar", "Capsules", "Icon button padding", "Left and right padding of icon buttons and titles", "button size width space")
        add("Bar", "Capsules", "Capsule roundness", "Corner radius of the capsules", "radius corners rounded pill squircle size")
        for side in ("left", "right"):
            add("Bar", "Capsules", f"Spacing: {side}", f"Space between capsules, {side} side", "gap margin")
            add("Bar", "Capsules", f"Padding: {side}", f"Space inside a capsule, {side} side", "size width inner")
        add("Bar", "Capsules", "Capsule border width", "A line around every capsule", "outline stroke thickness")
        add("Bar", "Capsules", "Capsule border colour", "Black unless you set another", "outline stroke color hex rgba")
        add("Bar", "Shortcuts", "Middle-click opens ShellFlow", "Middle-click a bar widget (the Home button) to open ShellFlow", "middle click mouse home open settings shortcut exec")
        if len(read_widgets(text)) > 1:
            add("Bar", "Shortcuts", "On which widget", "The widget you middle-click to open ShellFlow", "middle click which widget home")
        add("Bar", "Menus", "Floating menus", "Menus and popups float below the bar instead of touching it", "popup attached detached separation offset")
        add("Bar", "Menus", "Menu roundness", "Corner radius of the menus; floating ones are round all over, attached ones are square where they touch the bar", "radius corners rounded popup border")
        add("Bar", "Menus", "Gap from the bar", "Distance between the bar and its menus, 10 px by default", "popup offset_top separation distance floating")
        add("Bar", "Bar", "Bar rounding", "Corner radius of the whole bar", "radius corners rounded")
        for t, d in (("Pill rounding", "Corner radius of each workspace pill"), ("Pill height", "Height of each pill"), ("Width: empty", "A workspace with no windows"),
                     ("Width: with windows", "A workspace that has windows"), ("Width: active", "The workspace you are on"), ("Space between pills", "Left and right of each pill")):
            add("Bar", "Workspace pills", t, d, "komorebi workspaces pills size width radius")
        add("Bar", "Workspaces", "Show workspace labels", "The number or name on each workspace button", "numbers names text komorebi")
        add("Bar", "Workspaces", "App icons on busy workspaces", "Show the icons of the apps running there", "komorebi")
        add("Bar", "Workspaces", "App icons on the active workspace", "Show the icons of the apps on the one you are on", "komorebi")
        add("Bar", "Workspaces", "Hide duplicate icons", "One icon per app", "komorebi")
        add("Bar", "Workspaces", "Hide the label when icons show", "Icons only", "komorebi")
        add("Bar", "Behaviour", "Auto hide", "Slide the bar away until the mouse reaches the screen edge", "hide slide")
        add("Bar", "Behaviour", "Hide on fullscreen", "Get out of the way of games and videos", "game video")
        add("Bar", "Behaviour", "Always on top", "Stay above other windows", "topmost")
        add("Bar", "Behaviour", "Reserve space", "Windows keeps other windows clear of the bar", "appbar work area")
        add("Bar", "Behaviour", "Animation", "Slide or fade the bar in and out", "motion")
        add("Bar", "Behaviour", "Animation style", "Slide or fade", "motion")
        add("Bar", "Behaviour", "Animation speed", "How long the animation takes", "duration ms")
        add("Templates", "Write now", "Write all the themes", "Every app that is switched on", "apply")
        for key, name, var, _, desc, _ in th.APP_TABLE:
            add("Templates", "Apps", name, desc, f"{var} folder path theme template")
        add("Edits", "Fonts", "Bar font", "Widget text and icons", "typeface family nerd poppins")
        add("Edits", "Fonts", "Menu and clock font", "Menus, tooltips and the clock", "typeface family poppins")
        for label, var in COLOUR_VARS:
            add("Edits", "Colours", label, f"--yasb-{var}", "colour color hex rgba custom override")
        for group, paths in config_files().items():
            for p in paths:
                add("Files", group, p.name, str(p.parent), "edit open file config")
        add("Keybinds", "Keyboard", "Keys", "Press keys, or click them, to see the keybinds that use them", "keyboard hold combination press")
        add("Keybinds", "Keybinds", "Add a keybind", "A new line at the end of your whkdrc", "whkd hotkey shortcut new")
        wtext = self.whkd_text()
        if wtext is None:
            add("Keybinds", "Keybinds", "Create a whkdrc", "An empty whkdrc", "whkd create")
        for b in parse_whkdrc(wtext or ""):
            add("Keybinds", "Keybinds", keybind_title(b), b["keys_text"] + "   " + b["cmd"], "whkd keybind hotkey " + b["group"])
        add("Templates", "Apps", "Restart File Pilot", "Close File Pilot, write its colours, open it again", "file pilot fpilot reload restart colors")
        add("Templates", "Apps", "Restart Helium", "Close Helium and open it again with your tabs so it reads the new theme", "browser chromium theme reload restart auto")
        add("Backup", "Back up", "Back up now", "Zip your config, styles, .env, edits, komorebi and whkd files", "backup save copy zip")
        add("Backup", "Back up", "Backups folder", str(BACKUP_DIR), "backup location open")
        if old_copies():
            add("Backup", "Back up", "Old automatic copies", "config.yaml.bak and styles.css.bak from older versions", "bak delete")
        for p, count, size in list_backups():
            add("Backup", "Your backups", backup_title(p), f"{count} files", "restore delete backup")
        add("Backup", "Log files", "Keep log files", "Write the start and helper logs", "logs logging debug off")
        add("Backup", "Log files", "Diagnostic report", "Save a full check as shellflow_doctor.txt", "doctor report support")
        for p in log_files():
            add("Backup", "Log files", p.name, str(p.parent), "log open")
        if not log_files():
            add("Backup", "Log files", "No log files", "Nothing has been written", "")
        else:
            add("Backup", "Log files", "Clear log files", "Deletes the logs", "delete remove")
        add("About", "System information", "Windows", platform.platform(), "version os system")
        add("About", "System information", "Python", sys.version.split()[0], "version system")
        add("About", "System information", "YASB", yasb_version(), "version system")
        add("About", "System information", "komorebi", komorebi_version(), "version system")
        add("About", "System information", "Monitors", "The screens YASB sees", "system display")
        add("About", "System information", "Config folder", str(th.CONFIG), "location path")
        add("About", "About", "Copy info", "Copy the system information", "clipboard")
        return I

    def find(self, query):
        """The index entries that contain every word of the query, best matches (title) first."""
        words = query.lower().split()
        scored = []
        for page, card, title, desc, kw in self.search_index():
            hay = " ".join((page, card, title, desc, kw)).lower()
            if all(w in hay for w in words):
                scored.append((0 if all(w in title.lower() for w in words) else 1 if card == "Page" else 2, (page, card, title, desc)))
        order = {n: i for i, (n, _, _) in enumerate(PAGES)}
        scored.sort(key=lambda t: (t[0], order[t[1][0]]))
        return [e for _, e in scored]

    def set_search(self, text):
        """Typing searches every setting. The results appear a moment after the last key."""
        self.search = text.strip().lower()
        if self.search_job:
            self.root.after_cancel(self.search_job)
        self.search_job = self.root.after(160, self.apply_search)

    def apply_search(self):
        self.search_job = None
        hits = self.find(self.search) if self.search else []
        self.counts = {}
        for page, card, *_ in hits:
            if card != "Page":
                self.counts[page] = self.counts.get(page, 0) + 1
        if self.search:
            self.view_results = True
            self.go(self.current, keep=True)
        else:
            self.view_results = False
            self.go(self.current)

    def clear_search(self):
        self.search_box.delete(0, "end")
        if self.search_pop is not None:  # the attached window's box: emptied and closed
            self.search_pop.delete(0, "end")
            self.search_pop.destroy()
            self.search_pop, self.search_open = None, False
        self.set_search("")
        self.root.after(200, self.search_box.master.focus_set)

    def open_first(self):
        hits = self.find(self.search) if self.search else []
        if hits:
            self.jump(*hits[0][:3])

    def jump(self, page, card, title):
        """Open the page a setting is on, scroll to it and flash a frame around it."""
        i = [n for n, *_ in PAGES].index(page)

        def go_there():
            if self.search_job:
                self.root.after_cancel(self.search_job)
                self.search_job = None
            self.search, self.counts, self.view_results = "", {}, False  # the search is done: clear it
            self.search_box.delete(0, "end")
            if self.search_pop is not None:
                self.search_pop.destroy()
                self.search_pop, self.search_open = None, False
            self.go(i)
            self.cv.focus_set()  # the cursor leaves the search box
            self.root.update_idletasks()
            self.locate(card, title)
        self.defer(go_there)

    def locate(self, card, title):
        cv = self.cv
        texts = [(i, cv.itemcget(i, "text")) for i in cv.find_all() if cv.type(i) == "text"]
        target = next((i for i, t in texts if t == title), None) or next((i for i, t in texts if t.startswith(card)), None)
        if target is None:
            return
        self.flow.reveal(target)  # it may be inside a closed section
        self.root.update_idletasks()
        total = float(cv.cget("scrollregion").split()[3])
        cv.yview_moveto(max(0.0, (cv.bbox(target)[1] - 90) / total))
        self.root.update_idletasks()
        x0, y0, x1, y1 = cv.bbox(target)
        frame = cv.create_image(-6, (y0 + y1) / 2 - 36, anchor="nw", image=rounded(self.flow.cw + 12, 72, 16, None, self.c["accent2"], 2.5))
        self.flash = frame

        def drop():
            try:
                cv.delete(frame)
            except tk.TclError:
                pass
        self.root.after(1800, drop)

    def page_search(self):
        f, c = self.draw_main("Search", "search"), self.c
        hits = self.find(self.search)
        pages = {n: g for n, g, _ in PAGES}
        if not hits:
            f.note(f'Nothing matches "{self.search}". Try another word, for example font, opacity, gap, border or auto hide.')
            return f
        cards = list(dict.fromkeys((p, cd) for p, cd, *_ in hits))
        f.note(f'{len(hits)} results in {len(cards)} cards for "{self.search}". Click one to jump to it (Enter opens the first).')
        for page, card in cards:
            f.heading(f"{page}   >   {card}" if card != "Page" else f"{page}", pages[page], collapsible=False)
            f.begin_card()
            for p, cd, title, desc in hits:
                if (p, cd) == (page, card):
                    yc = f.row(title, desc[:90], glyph=pages[page], click=lambda p=p, cd=cd, t=title: self.jump(p, cd, t))
                    f.cv.create_image(f.r, yc, image=icon("chev_right", 20, c["accent2"]), anchor="e")
            f.end_card()
        return f

    def go(self, i, keep=False, enter=False):
        """Show page i. keep=True redraws the same page and keeps your scroll position. enter=True (you clicked the page in the
        sidebar) lets the page rise into place and the sidebar's pill swell, with a spring."""
        pixels = self.cv.canvasy(0) if keep and getattr(self, "cv", None) is not None else 0.0
        results = self.view_results and keep
        self.view_results, self.redraw = results, keep
        self.current = i
        self.layout()
        self.draw_side()
        name = "Search" if results else PAGES[i][0]
        self.flow = getattr(self, "page_" + name.lower())()
        self.flow.finish()
        self.root.update_idletasks()
        total = max(1, int(float(self.cv.cget("scrollregion").split()[3]))) if self.cv.cget("scrollregion") else 1
        self.cv.yview_moveto(min(1.0, pixels / total))  # the same pixel row stays at the top
        self.on_scroll(*self.cv.yview())
        if enter and not self.compact_motion():
            self.enter_motion()

    def compact_motion(self):
        """Motion can be switched off with YASB_MOTION=0 (and is off for a window that is closing)."""
        return self.closing or th.env("YASB_MOTION") == "0"

    def enter_motion(self):
        """The page rises 20 px into place, and the selected sidebar pill swells from a smaller size, both with a spring."""
        cv, offset, run = self.cv, 20, {"moved": 0.0}
        top = cv.canvasy(0)
        cv.dtag("rise")
        cv.addtag_overlapping("rise", -20, top - offset, cv.winfo_width() + 40, top + cv.winfo_height() + offset)  # what is in view
        cv.move("rise", 0, offset)

        def rise(t):
            goal = -offset * soft(t)
            cv.move("rise", 0, goal - run["moved"])
            run["moved"] = goal
        animate(cv, 280, rise, done=lambda: cv.dtag("rise"))
        bg = getattr(self, "sel_bg", None)
        if bg is not None and not self.compact:
            w, c = self.sw - 28, self.c["accent"]
            animate(self.side, 320, lambda t: self.side.itemconfig(bg, image=rounded(round(w * (0.55 + 0.45 * spring(t))), round(42 * (0.6 + 0.4 * spring(t))),
                                                                                       round(21 * (0.6 + 0.4 * spring(t))), c)))

    def refresh(self):
        self.go(self.current, keep=True)

    # following the wallpaper and the colour scheme ---------------------------------------------
    def theme_sig(self):
        return th.theme_signature() + (th.fhash(th.OUT),)

    def poll_theme(self):
        """Every second: has the wallpaper, the accent or the applied scheme changed? Then follow it."""
        try:
            sig = self.theme_sig()
            if sig != self.last_sig:
                self.last_sig, self.sig_pending, self.sig_since = sig, True, time.time()
            elif self.sig_pending and time.time() - self.sig_since > 1.2:
                self.sig_pending = False
                self.theme_changed()
            if not self.closing:
                self.poll_job = self.root.after(1000, self.poll_theme)
        except tk.TclError:
            pass

    def load_seed(self):
        """Read the wallpaper's dominant colour off the main thread (a big wallpaper can take seconds after a restart),
        then redraw the pages that show it."""
        box = {}

        def work():
            try:
                box["seed"] = th.get_seed()
            except Exception:
                pass
        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def done():
            try:
                if thread.is_alive():
                    return self.root.after(150, done)
                if "seed" in box and box["seed"] != self.seed:
                    self.seed = box["seed"]
                    if PAGES[self.current][0] in ("Colors", "Wallpaper") and not self.view_results and not self.typing():
                        self.go(self.current, keep=True)
                start_log("seed read")
            except tk.TclError:
                pass
        self.root.after(150, done)

    def typing(self):
        """True while you are typing in one of the page's text boxes (a redraw would drop the cursor)."""
        try:
            w = self.root.focus_get()
        except (KeyError, tk.TclError):
            return False
        return isinstance(w, tk.Entry) and w is not self.search_box

    def theme_changed(self):
        if self.typing():  # not while you type: look again in a second
            self.sig_pending, self.sig_since = True, time.time() - 0.2
            return
        wp = th.theme_signature()[:3]
        if wp == self.wp_sig:
            return self.recolor()
        self.wp_sig = wp  # a new wallpaper: read its seed colour off the main thread, then recolour
        box = {}

        def work():
            try:
                box["seed"] = th.get_seed()
            except Exception:
                pass
        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def done():
            if thread.is_alive():
                return self.root.after(150, done)
            self.seed = box.get("seed", self.seed)
            self.recolor(force=True)
        self.root.after(150, done)

    def recolor(self, force=False):
        """Re-theme the window with the bar's current colours and redraw (the Colors page gets the new seed)."""
        try:
            new = self.make_colors(th.palette(effective=True))
        except Exception:
            return
        same = new == self.c
        if same and not (force and PAGES[self.current][0] in ("Colors", "Wallpaper")):
            return
        if not same:
            self.c.clear()
            self.c.update(new)
            for fn in (rounded, switch, pill_button, slider_img, icon, logo_img, avatar, App.close_img):
                fn.cache_clear()
            c = self.c
            self.root.configure(bg=c["outer"])
            for w in (self.inner,):
                w.configure(bg=c["outer"])
            for w in (self.side, self.main):
                w.configure(bg=c["win"])
            self.search_box.configure(bg=c["input"], fg=c["text"], insertbackground=c["text"])
            self.draw_ring()
        self.go(self.current, keep=True)
        self.say("Colours updated")

    # click away to close ----------------------------------------------------------------------
    def autoclose_ok(self):
        """A click outside may close the window: not while a file dialog is open, not in the first second, and not in
        the few seconds after you opened a file or folder (a dialog like "Open with" may appear then)."""
        return not self.modal and not self.closing and time.time() - self.born > 1.0 and time.time() > self.quiet_until

    def launch(self, path):
        """Open a file or folder in another program (Open / Edit buttons). ShellFlow stays open: only a click outside closes it."""
        self.quiet_until = time.time() + 4.0
        open_file(path)

    def click_away(self):
        if not self.autoclose_ok():
            return
        if self.dirty:  # never throw unapplied changes away by accident
            return self.say("Unapplied changes - press Apply (or the X to discard) before clicking away")
        self.close()

    def mouse_state(self):
        """(x, y, any mouse button down) on screen. Windows only; elsewhere the focus check does the work."""
        try:
            import ctypes
            from ctypes import wintypes
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            down = any(ctypes.windll.user32.GetAsyncKeyState(k) & 0x8000 for k in (1, 2, 4))
            return pt.x, pt.y, bool(down)
        except Exception:
            return 0, 0, False

    def inside(self, x, y):
        r = self.root
        return r.winfo_rootx() <= x < r.winfo_rootx() + r.winfo_width() and r.winfo_rooty() <= y < r.winfo_rooty() + r.winfo_height()

    def watch(self):
        """Every 40 ms: a new mouse press outside the window closes it (also on windows that never take focus,
        like the YASB bar). Switching to another app without clicking (Alt+Tab, a program that opens) does not."""
        if self.closing:
            return
        try:
            x, y, down = self.mouse_state()
            if down and not self.was_down and not self.inside(x, y):
                self.click_away()
            self.was_down = down
            if not self.closing:  # (closing: the timers were just cancelled; do not start a new one)
                self.watch_job = self.root.after(40, self.watch)
        except tk.TclError:
            pass  # the window is gone

    def ask_dir(self, **kw):
        return self.dialog(filedialog.askdirectory, **kw)

    def ask_file(self, **kw):
        return self.dialog(filedialog.askopenfilename, **kw)

    def dialog(self, fn, **kw):
        """Open a Windows dialog; clicking in it must not count as clicking away."""
        self.modal += 1
        try:
            return fn(parent=self.root, **kw)
        finally:
            self.modal -= 1
            self.born = max(self.born, time.time() - 0.5)  # a short pause after it closes

    def force_destroy(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def ensure_visible(self):
        """A second after opening: if the window is not really on screen (hidden, see-through, off every monitor), fix it."""
        try:
            r = self.root
            r.attributes("-alpha", 1.0)
            off = r.winfo_rootx() + self.W < 40 or r.winfo_rooty() + H < 40 or r.winfo_rootx() > r.winfo_screenwidth() - 40 \
                or r.winfo_rooty() > r.winfo_screenheight() - 40
            if not r.winfo_viewable() or off:
                start_log("window was not visible/on screen: showing it again")
                to_front(r, self.attach_state(), bar_edge(self.cfg_text())[1], self.W, self.x0, self.y0, self.dy)
        except tk.TclError:
            pass

    def close(self):
        if self.closing:
            return
        if self.dirty and not self.warned:  # the first click only warns
            self.warned = True
            return self.say("Unapplied changes - press Apply, or close again to discard them")
        self.closing = True
        for job in (self.watch_job, self.focus_job, self.poll_job):  # no timers left behind when the window is destroyed
            if job:
                self.root.after_cancel(job)
        self.watch_job = self.focus_job = self.poll_job = None
        self.root.after(20, lambda: fade(self.root, 1.0, 0.0, 160, self.root.destroy))  # not inside the click itself: Tk can crash
        self.root.after(900, self.force_destroy)  # failsafe: whatever happens, the window goes away


    # ========================================================================================
    #  9. THE PAGES
    # ========================================================================================
    APP_ICONS = {"discord": "message", "zed": "code", "obsidian": "file_text", "vscode": "code", "nvim": "terminal",
                 "wt": "terminal", "firefox": "globe", "zen": "globe", "yazi": "folder", "obs": "video", "tacky": "box", "windhawk": "layers", "helium": "globe", "filepilot": "folder"}

    def repair_config(self):
        """Fix settings YASB would reject (staged: it takes effect when you press Apply)."""
        try:
            text, fixed = repair_config(self.cfg_text())
        except Exception:
            return
        if fixed:
            self.cfg_change(text)
            self.say("Fixed " + "; ".join(fixed) + " - press Apply")

    def apply_apps(self):
        """Write every app theme now and say which ones failed (and why)."""
        fails = th.write_apps()
        names = {r[0]: r[1] for r in th.APP_TABLE}
        if not fails:
            return self.say("App themes written")
        self.sfx.play("error")
        self.say("Failed: " + "; ".join(f"{names.get(k, k)} - {short_failure(v)}" for k, v in fails.items()))

    def defer(self, fn):
        """Run fn after the current click has finished (a page must not be rebuilt inside its own click)."""
        self.root.after(15, fn)

    def nav(self, i):
        self.defer(lambda: self.go(i, enter=True))

    def defer_refresh(self):
        self.defer(self.refresh)

    def cfg_set(self, path, value):
        self.cfg_change(yaml_set(self.cfg_text(), path, value))

    def pick_bar(self, i):
        self.bar = i
        self.defer_refresh()

    def bar_tabs(self, title, glyph):
        """A page with one tab per bar in config.yaml. Returns (flow, bar name or None)."""
        text = self.cfg_text()
        names = bar_names(text)
        if not names:
            f = self.draw_main(title, glyph)
            f.note("config.yaml was not found, or it has no bars.\nLooked in " + str(th.CONFIG))
            return f, None
        self.bar = min(self.bar, len(names) - 1)
        return self.draw_main(title, glyph, tabs=names, current=self.bar, on_tab=self.pick_bar), names[self.bar]

    def swatch(self, f, yc, colour, x=None):
        f.cv.create_image(x or f.r, yc, image=rounded(30, 30, 9, colour, self.c["line"], 1), anchor="e")

    # ---- General ----------------------------------------------------------------------------------
    def page_general(self):
        f, c = self.draw_main("General", "sliders"), self.c
        f.heading("Profile", "user")
        top, size = f.y, 112
        shown = {"path": th.env("YASB_PFP")}

        def pic():
            p = shown["path"]
            return avatar(p, size, c["accent"], c["input"], os.path.getmtime(p) if p and os.path.exists(p) else 0)
        av = f.cv.create_image(0, top + 4, image=pic(), anchor="nw")
        x = size + 30
        f.cv.create_text(x, top + 12, text="Name", anchor="w", fill=c["muted"], font=self.f(10))
        name = f.entry(top + 44, f.cw - x, user_name(), x=f.cw, name="name")
        f.cv.create_text(x, top + 84, text="Profile picture", anchor="w", fill=c["muted"], font=self.f(10))
        y = top + 116
        edge = f.button(y, "Clear", lambda: set_pfp(""), x=f.cw, name="pfp_clear") - 10
        edge = f.button(y, "Choose image", lambda: choose(), glyph="camera", x=edge, name="pfp_choose") - 10
        path = f.entry(y, edge - x, shown["path"], x=edge, name="pfp")

        def save_name(_=None):
            v = name.get().strip()
            if v and v != os.environ.get("USERNAME", ""):
                env_set("YASB_USERNAME", v)
            else:
                env_unset("YASB_USERNAME")
            self.say("Saved")

        def set_pfp(p):
            p = p.strip().strip('"')
            if p and not os.path.isfile(p):
                return self.say("That file does not exist")
            (env_set("YASB_PFP", p.replace("\\", "/")) if p else env_unset("YASB_PFP"))
            shown["path"] = p
            path.delete(0, "end")
            path.insert(0, p)
            f.cv.itemconfig(av, image=pic())
            self.say("Saved")

        def choose():
            p = self.ask_file(title="Choose a profile picture", initialdir=str(Path(shown["path"]).parent) if shown["path"] else str(Path.home()),
                                           filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All files", "*.*")])
            if p:
                set_pfp(p)
        for box, fn in ((name, save_name), (path, lambda _=None: set_pfp(path.get()))):
            box.bind("<Return>", fn)
            box.bind("<FocusOut>", fn)
        f.y = top + size + 40
        f.heading("Quick actions", "sliders")
        f.begin_card()
        yc = f.row("Open the config folder", str(th.CONFIG), glyph="folder")
        f.button(yc, "Open", lambda: self.launch(th.CONFIG), glyph="arrow_ur", name="open_config")
        yc = f.row("Write all the app themes", "Discord, Zed, Obsidian, VS Code and the others you switched on", glyph="layers")
        f.button(yc, "Apply now", self.apply_apps, primary=True, name="apply_apps")
        yc = f.row("Reload komorebi", "Runs komorebic reload-configuration", glyph="tiles")
        f.button(yc, "Reload", lambda: (reload_komorebi(), self.say("komorebi reloaded")), glyph="reset", name="reload_kom")
        f.end_card()
        on, vol = sound_settings()
        f.heading("Window", "panel")
        f.begin_card()

        yc = f.row("Attach to the bar", "ShellFlow sits flush against the bar, as wide as the bar (15 px in from each end), square where it touches, "
                   "with its sidebar collapsed to icons (hover for the names). It reopens to apply this", glyph="panel")
        f.toggle(yc, th.env("YASB_ATTACH") == "1", lambda v: (env_set("YASB_ATTACH", "1" if v else "0"), self.relaunch()), name="attach")
        if th.env("YASB_ATTACH") == "1":  # fine tuning, because only you can see how it sits against your bar
            yc = f.row("Inset from the bar's ends", "How far in from each end of the bar the window starts. It reopens to apply this")
            f.slider(yc, int(th.env("YASB_ATTACH_INSET")) if th.env("YASB_ATTACH_INSET").isdigit() else None, 0, 30,
                     lambda v: (env_set("YASB_ATTACH_INSET", str(15 if v is None else v)), self.relaunch()), default=15, name="attach_inset")
            yc = f.row("Move up or down", "Nudges the window against the bar (negative = up). It reopens to apply this")
            f.slider(yc, int(th.env("YASB_ATTACH_DY")) if th.env("YASB_ATTACH_DY").lstrip("-").isdigit() else None, -20, 20,
                     lambda v: (env_set("YASB_ATTACH_DY", str(0 if v is None else v)), self.relaunch()), default=0, name="attach_dy")
        yc = f.row("Motion", "Springy motion for buttons, switches, sections and pages (Material 3 expressive)", glyph="sliders")
        f.toggle(yc, th.env("YASB_MOTION") != "0", lambda v: (env_set("YASB_MOTION", "1" if v else "0"), self.say("Motion " + ("on" if v else "off"))), name="motion")
        f.end_card()
        f.heading("Sounds", "volume")
        f.begin_card()

        def set_sound(on=None, vol=None):
            if on is not None:
                env_set("YASB_SOUNDS", "1" if on else "0")
            if vol is not None:
                env_set("YASB_SOUND_VOLUME", str(vol))
            self.sfx.configure(enabled=on, volume=vol)
            if vol is not None:
                self.sfx.play("click")
            self.say("Saved")

        def preview():
            for ms, name in ((0, "click"), (420, "on"), (900, "off"), (1350, "apply")):
                self.root.after(ms, lambda n=name: self.sfx.play(n))
            self.root.after(1500, lambda: self.say("Sound problem: " + self.sfx.last_error + "  (check the Windows volume mixer)")
                            if self.sfx.last_error else None)
        yc = f.row("Click sounds", "Soft Pixel-style taps, ticks and chimes for the buttons and toggles in this window", glyph="volume")
        f.toggle(yc, on, lambda v: set_sound(on=v), name="sounds_on")
        def set_bar_sounds(v):
            try:
                env_set("YASB_BAR_SOUNDS", "1" if v else "0")
                th.apply_helper_settings()
                self.say("Sounds on the YASB bar " + ("on" if v else "off"))
            except Exception as e:
                th.log("bar sounds")
                self.say(f"Could not change it: {e}")
        yc = f.row("Sounds on the YASB bar", "A tick when you click the bar or one of its menus (the background helper plays it)", glyph="bar")
        f.toggle(yc, th.env("YASB_BAR_SOUNDS") == "1", set_bar_sounds, name="bar_sounds")
        yc = f.row("Vary the pitch", "Each click is a little higher or lower than the last, in tune with each other, for some variety", glyph="volume")
        f.toggle(yc, th.env("YASB_SOUND_VARY") != "0", lambda v: (env_set("YASB_SOUND_VARY", "1" if v else "0"), self.say("Pitch varies" if v else "Always the same pitch")), name="sound_vary")
        yc = f.row("Volume", "How loud the sounds are")
        f.slider(yc, vol, 0, 100, lambda v: set_sound(vol=10 if v is None else v), unit="%", default=10, name="sound_volume")
        yc = f.row("Preview", "Plays the click, on, off and done sounds")
        f.button(yc, "Play", preview, glyph="volume", name="sound_preview")
        f.end_card()
        f.heading("Sync", "reset")
        f.begin_card()

        def set_sync(v):
            try:
                env_set("YASB_SYNC", "1" if v else "0")
                th.apply_helper_settings()
                self.say("Background sync " + ("on - it starts with Windows" if v else "off"))
            except Exception as e:
                th.log("sync")
                self.say(f"Could not change it: {e}")
        yc = f.row("Keep app themes in sync", "Rewrites Discord, Zed and the rest when the wallpaper changes", glyph="reset")
        f.toggle(yc, th.env("YASB_SYNC") != "0", set_sync, name="sync")
        yc = f.row("Background helper", th.helper_status(), glyph="bar")
        status = f.last_desc

        def restart():
            try:
                th.restart_helper()
                self.root.after(1500, lambda: self.cv.itemconfig(status, text=th.helper_status()) if self.cv.winfo_exists() else None)
                self.say("Helper restarted")
            except Exception as e:
                th.log("helper")
                self.say(f"Could not restart it: {e}")
        f.button(yc, "Restart", restart, glyph="reset", name="helper_restart")
        f.end_card()
        return f

    def ensure_sync(self):
        """First run: switch the background helper on (app sync and the sounds on the YASB bar), and make sure it is running."""
        try:
            for key, default in (("YASB_SYNC", "1"), ("YASB_BAR_SOUNDS", "0")):  # the sounds on the bar are off until you switch them on
                if th.env(key) == "":
                    env_set(key, default)
            th.apply_helper_settings()
        except Exception:
            th.log("sync")

    def page_colors(self):
        f, c = self.draw_main("Colors", "palette"), self.c
        f.note("Pick a colour scheme, then press Apply (bottom right). The bar and the apps (Discord, Zed, Obsidian, Yazi and the others you switched on) all take its colours.")
        f.heading("Scheme", "palette")
        applied = th.current_variant()
        items, state = th.build_items(self.seed), {"hover": -1, "active": self.scheme_pick or applied}
        scale = min(1.0, (f.cw - 24) / (5 * th.TILE_W + 4 * th.GAP + 2 * th.PAD))
        rects, size = th.layout(len(items), scale)
        bg = tuple(int(c["win"][i:i + 2], 16) for i in (1, 3, 5))
        top, gx = f.y + 10, (f.cw - size[0]) // 2  # the grid sits centred inside its card
        f.cv.create_image(0, top - 10, image=rounded(f.cw, size[1] + 20, 18, c["win"], c["accent"], 1.5), anchor="nw")
        grid = f.cv.create_image(gx, top, anchor="nw")

        def draw():
            hv = [1.0 if k == state["hover"] else 0.0 for k in range(len(items))]
            f.cv.photo = ImageTk.PhotoImage(th.render(items, rects, size, scale, hv, state["active"], bg))
            f.cv.itemconfig(grid, image=f.cv.photo)

        def which(e):
            x, y = e.x - gx, f.cv.canvasy(e.y) - f.cv.coords(grid)[1]
            return next((i for i, (x0, y0, x1, y1) in enumerate(rects) if x0 <= x < x1 and y0 <= y < y1), -1)

        def motion(e):
            i = which(e)
            if i != state["hover"]:
                state["hover"] = i
                f.cv.config(cursor="hand2" if i >= 0 else "")
                draw()

        def click(e):
            i = which(e)
            if i >= 0:  # selecting only; it is applied with the Apply button
                key = items[i]["key"]
                if key == "custom" and not th.custom_colours():
                    self.say("No custom colours yet - set them on the Edits page")
                    return self.nav([n for n, *_ in PAGES].index("Edits"))
                self.scheme_pick = None if key == applied else key
                state["active"] = key
                self.dirty.discard("scheme") if self.scheme_pick is None else self.dirty.add("scheme")
                self.warned = False
                self.draw_footer()
                self.say(f"{items[i]['label']} selected  -  press Apply" if self.scheme_pick else f"{items[i]['label']} is already applied")
                draw()
        f.cv.tag_bind(grid, "<Motion>", motion)
        f.cv.tag_bind(grid, "<Button-1>", click)
        f.cv.tag_bind(grid, "<Leave>", lambda e: motion(type("E", (), {"x": -1, "y": -1})()))
        f.hits["grid"], f.hits["grid_rects"], f.hits["grid_top"], f.hits["grid_x"] = grid, rects, top, gx
        draw()
        f.y = top + size[1] + 14
        f.heading("Source", "image")
        f.begin_card()
        yc = f.row("Seed colour", "The dominant colour of your wallpaper (or your Windows accent)")
        self.swatch(f, yc, "#%06x" % (self.seed & 0xFFFFFF))
        f.cv.create_text(f.r - 42, yc, text="#%06x" % (self.seed & 0xFFFFFF), anchor="e", fill=c["text"], font=self.f(10))
        yc = f.row("Windows accent", "Used when the scheme is Windows accent")
        self.swatch(f, yc, th.hx(th.accent_shades()["accent"]))
        f.end_card()
        return f

    # ---- Wallpaper --------------------------------------------------------------------------------
    def page_wallpaper(self):
        f, c = self.draw_main("Wallpaper", "image"), self.c
        dirs = wallpaper_dirs(self.cfg_text())
        f.note("Pick a wallpaper from the folder the YASB wallpapers widget uses (its image_path in config.yaml, or YASB_WALLPAPERS in .env), "
               "then press Apply (bottom right). The colour scheme and the apps follow the new wallpaper.")
        f.heading("Folder", "folder")
        f.begin_card()
        yc = f.row("Wallpapers folder", "From the wallpapers widget" if dirs else "Not found - see the note above")
        edge = f.button(yc, "Open", lambda: dirs and self.launch(dirs[0]), glyph="folder", name="wall_open") - 10
        box = f.entry(yc, max(200, edge - f.l - 330), "; ".join(str(d) for d in dirs), x=edge, name="wall_folder", colour=c["muted"])
        box.config(state="readonly", readonlybackground=c["input"])
        f.end_card()
        files = list_wallpapers(dirs)
        f.heading(f"Wallpapers   -   {len(files)}", "image")
        if not files:
            f.note("No pictures (png, jpg, webp, bmp) in that folder.")
            return f
        cols, gap, cap = 3, 14, 30
        tw = (f.cw - gap * (cols - 1)) // cols
        th_ = tw * 9 // 16
        current = th.wallpaper_path() if sys.platform == "win32" else ""
        base, items = {}, {}
        top = f.y
        photos = f.cv.photos = {}

        def draw(i):
            p = files[i]
            if i in base:
                photos[i] = wall_tile(base[i], same_file(self.wall_pick, p), same_file(current, p), c["accent"], c["ink"], c["panel"])
                f.cv.itemconfig(items[i], image=photos[i])

        def pick(i):
            p = files[i]
            self.wall_pick = None if same_file(p, current) else p
            self.dirty.discard("wall") if self.wall_pick is None else self.dirty.add("wall")
            self.warned = False
            self.draw_footer()
            self.say(f"{p.stem} selected  -  press Apply" if self.wall_pick else f"{p.stem} is the current wallpaper")
            for j in base:
                draw(j)
        for i, p in enumerate(files):
            x, y = (i % cols) * (tw + gap), top + (i // cols) * (th_ + cap + 10)
            ph = rounded(tw, th_, 16, c["input"])
            it = f.cv.create_image(x, y, image=ph, anchor="nw")
            photos[("ph", i)] = ph
            items[i] = it
            f.cv.create_text(x + 6, y + th_ + 14, text=p.stem[:34], anchor="w", fill=c["muted"], font=self.f(9))
            f.cv.tag_bind(it, "<Button-1>", lambda e, i=i: (self.sfx.play("tap"), pick(i)))
            f.cv.tag_bind(it, "<Enter>", lambda e: f.cv.config(cursor="hand2"))
            f.cv.tag_bind(it, "<Leave>", lambda e: f.cv.config(cursor=""))
            f.hits[f"wall:{p.name}"] = it
        f.y = top + ((len(files) + cols - 1) // cols) * (th_ + cap + 10)
        f.hits["wall_files"] = files
        # thumbnails are made in the background and appear one by one
        results = queue.Queue()
        canvas = f.cv

        def work():
            for i, p in enumerate(files):
                try:
                    results.put((i, make_thumb(p, (tw, th_))))
                except Exception:
                    results.put((i, None))
        threading.Thread(target=work, daemon=True).start()

        def drain():
            try:
                if not canvas.winfo_exists() or getattr(self, "cv", None) is not canvas:
                    return
                for _ in range(6):
                    i, im = results.get_nowait()
                    if im is not None:
                        base[i] = im
                        draw(i)
                canvas.after(40, drain)
            except queue.Empty:
                canvas.after(60, drain)
            except tk.TclError:
                pass
        f.hits["wall_draw"] = draw
        f.hits["wall_base"] = base
        drain()
        return f

    # ---- Widgets ----------------------------------------------------------------------------------
    def page_widgets(self):
        f, bar = self.bar_tabs("Widgets", "grid")
        if bar is None:
            return f
        text = self.cfg_text()
        zones, types = get_zones(text, bar), read_widgets(text)
        f.note("The widgets on the bar are listed by side. Switch one off and it moves to Hidden (it is commented out in "
               "config.yaml, never deleted, so it comes back in the same place). Change their order, or send them to another side.")
        tail = lambda t: ".".join(t.split(".")[-2:]) if t else "widget"
        placed, switched_off = set(), []
        for zone, label in (("left", "Left"), ("center", "Center"), ("right", "Right")):
            items = zones.get(zone, [])
            placed.update(name for name, _ in items)
            switched_off += [(name, zone) for name, on in items if not on]
            items = [(name, on) for name, on in items if on]
            f.heading(f"{label}   -   {len(items)} on", "zone_" + zone)
            if not items:
                f.note("Nothing on this side. Put a widget here from Hidden at the bottom.")
                continue
            f.begin_card()
            for name, on in items:
                yc = f.row(name, tail(types.get(name, "")), glyph=widget_icon(name, types.get(name, "")), dim=not on)
                x = f.toggle(yc, on, lambda v, n=name: (self.cfg_change(toggle_widget(self.cfg_text(), bar, n, v)), self.defer_refresh()),
                             name=f"toggle:{name}") - 16
                for other in ("right", "center", "left"):
                    if other != zone:
                        x = f.ibutton(yc, "zone_" + other, lambda n=name, o=other: (self.cfg_change(move_to_zone(self.cfg_text(), bar, n, o)), self.defer_refresh()),
                                      x=x, name=f"to_{other}:{name}")
                x -= 10
                x = f.ibutton(yc, "down", lambda n=name: (self.cfg_change(move_widget(self.cfg_text(), bar, n, 1)), self.defer_refresh()), x=x, name=f"down:{name}")
                x = f.ibutton(yc, "up", lambda n=name: (self.cfg_change(move_widget(self.cfg_text(), bar, n, -1)), self.defer_refresh()), x=x, name=f"up:{name}") - 10
                f.ibutton(yc, "trash", lambda n=name: (self.cfg_change(remove_widget(self.cfg_text(), bar, n)), self.say(f"{n} removed from {bar} - press Apply"), self.defer_refresh()), x=x, name=f"remove:{name}")
            f.end_card()
        spare = [w for w in types if w not in placed]
        defined = set(types.values())
        new = [e for e in CATALOG if e[4] not in defined]
        if switched_off or spare or new:
            f.heading(f"Hidden   -   {len(switched_off) + len(spare) + len(new)}", "layers")
            f.note("Everything that is not showing: widgets you switched off (the switch brings them back where they were), widgets in "
                   "config.yaml that are on no side of this bar, and YASB widgets config.yaml does not have yet (the plus button adds them hidden).")
            f.begin_card()
            for name, zone in switched_off:
                yc = f.row(name, f"{tail(types.get(name, ''))}   -   switched off, was on the {zone}", glyph=widget_icon(name, types.get(name, "")), dim=True)
                f.toggle(yc, False, lambda v, n=name: (self.cfg_change(toggle_widget(self.cfg_text(), bar, n, v)), self.defer_refresh()), name=f"toggle:{name}")
            for name in spare:
                yc = f.row(name, tail(types.get(name, "")), glyph=widget_icon(name, types.get(name, "")), dim=True)
                x = f.r
                for zone in ("right", "center", "left"):
                    x = f.ibutton(yc, "zone_" + zone, lambda n=name, z=zone: (self.cfg_change(toggle_widget(self.cfg_text(), bar, n, True, z)), self.defer_refresh()),
                                  x=x, name=f"add_{zone}:{name}")
                if types.get(name) in CATALOG_BY_TYPE:  # one ShellFlow can add again: its definition can be deleted for good
                    f.ibutton(yc, "trash", lambda n=name: (self.cfg_change(delete_widget_def(self.cfg_text(), n)), self.say(f"{n} deleted from config.yaml - press Apply"), self.defer_refresh()),
                              x=x - 10, name=f"delete:{name}")
            for key, title, desc, glyph, *_ in new:  # YASB widgets config.yaml does not have yet
                yc = f.row(title, desc, glyph=glyph, dim=True)
                x = f.r
                for zone in ("right", "center", "left"):
                    x = f.ibutton(yc, "zone_" + zone, lambda k=key, z=zone: self.add_new(bar, k, z), x=x, name=f"new_{zone}:{key}")
                f.ibutton(yc, "plus", lambda k=key: self.add_hidden(k), x=x - 10, name=f"hide:{key}")
            f.end_card()
        return f

    def add_hidden(self, key):
        """Define a catalog widget in config.yaml without putting it on any bar: it appears under Hidden (staged until Apply)."""
        before = self.cfg_text()
        text, name = define_catalog_widget(before, key, current_colours().get("accent-dark3", "#ffffff"))
        self.cfg_change(set_menu_gap(text, menu_gap(before)[1]))
        self.say(f"{name} added hidden - press Apply")
        self.defer_refresh()

    def add_new(self, bar, key, zone):
        """Define a catalog widget in config.yaml and put it on `bar` (staged until Apply)."""
        colour = current_colours().get("accent-dark3", "#ffffff")
        before = self.cfg_text()
        text, name = add_catalog_widget(before, key, bar, zone, colour)
        self.cfg_change(set_menu_gap(text, menu_gap(before)[1]))  # the new widget's menu is attached or floating like the rest
        self.say(f"{name} added - press Apply")
        self.defer_refresh()

    # ---- Bar --------------------------------------------------------------------------------------
    def page_bar(self):
        f, bar = self.bar_tabs("Bar", "bar")
        text, e = self.cfg_text(), self.edits
        def both(key_l, key_r, legacy):
            """One slider sets left and right together; the old single value is retired."""
            return lambda v: self.style_change(**{key_l: v, key_r: v, legacy: None})

        f.heading("Capsules", "grid")
        f.begin_card()
        for title, desc, link, kl, kr, legacy, lo, hi, dflt, nm in (
                ("spacing", "Space between capsules, on the left and right only (never above or below)", "link_spacing", "spacing_l", "spacing_r", "spacing", 0, 24, 5, "spacing"),
                ("padding", "Space inside a capsule, on the left and right", "link_pad", "pad_l", "pad_r", "pad", 0, 24, 8, "pad")):
            yc = f.row(f"Same {title} on both sides", "Off: set the left and right separately")
            f.toggle(yc, e.get(link, True), lambda v, link=link: (self.style_change(**{link: v}), self.defer_refresh()), name=link)
            cur_l, cur_r = e.get(kl, e.get(legacy)), e.get(kr, e.get(legacy))
            if e.get(link, True):
                yc = f.row(f"Widget {title}" if title == "spacing" else "Capsule padding", desc)
                f.slider(yc, cur_l, lo, hi, both(kl, kr, legacy), default=dflt, name=nm)
            else:
                for side, key, cur in (("left", kl, cur_l), ("right", kr, cur_r)):
                    yc = f.row(f"{title.capitalize()}: {side}", desc if side == "left" else "")
                    f.slider(yc, cur, lo, hi, lambda v, key=key, legacy=legacy: self.style_change(**{key: v, legacy: None}), default=dflt, name=f"{nm}_{side[0]}")
        if any(typ in CATALOG_BY_TYPE for typ in read_widgets(text).values()):
            yc = f.row("Icon button padding", "Left and right padding of icon buttons and titles")
            f.slider(yc, e.get("icon_pad"), 0, 30, lambda v: self.style_change(icon_pad=v), default=14, name="icon_pad")
        yc = f.row("Capsule roundness", "Corner radius of the capsules (the border follows it)")
        f.slider(yc, e.get("radius"), 0, 30, lambda v: self.style_change(radius=v), default=14, name="radius")
        yc = f.row("Capsule border width", "A line around every capsule (0 = none)")
        f.slider(yc, e.get("border_w"), 0, 8, lambda v: self.style_change(border_w=v), default=0, name="border_w")
        yc = f.row("Capsule border colour", "Black unless you set another: hex or rgba")
        box = f.entry(yc, 200, e.get("border_c", "#000000"), name="border_c", colour=self.c["text"] if "border_c" in e else self.c["muted"])

        def border_typed(_=None, box=box):
            col = parse_colour(box.get())
            if col:
                self.style_change(border_c=box.get().strip() if box.get().strip().lower() != "#000000" else None)
                box.config(fg=self.c["text"])
        box.bind("<KeyRelease>", border_typed)
        f.end_card()
        names = [n for n in read_widgets(text) if read_widgets(text)[n] in th.MIDDLE_CLICK_TYPES] or list(read_widgets(text))[:1]
        current = middle_open_widget(text)
        target = current or getattr(self, "mid_target", None) or ("home" if "home" in names else (names[0] if names else None))
        f.heading("Shortcuts", "keyboard")
        f.begin_card()
        yc = f.row("Middle-click opens ShellFlow", "Middle-click a widget on the bar (the Home button by default) to open this window", glyph="keyboard")
        f.toggle(yc, current is not None, lambda v: (self.cfg_change(set_middle_open(self.cfg_text(), target if v else None)), self.defer_refresh()), name="middle_open")
        if len(names) > 1:
            yc = f.row("On which widget", "The one you middle-click", glyph="keyboard")
            f.segmented(yc, names[:5], target, lambda v: (setattr(self, "mid_target", v), current and self.cfg_change(set_middle_open(self.cfg_text(), v)), self.defer_refresh()),
                        name="middle_widget")
        f.end_card()
        floating, gap = menu_gap(text)
        f.heading("Menus", "layers")
        f.begin_card()
        yc = f.row("Floating menus", "Off: menus open attached to the bar (square where they touch it). On: every menu floats a little below it, round all over")
        f.toggle(yc, floating, lambda v: (self.cfg_change(set_menu_gap(self.cfg_text(), self.menu_gap_last if v else 0)), self.defer_refresh()), name="menus_floating")
        yc = f.row("Menu roundness", "Corner radius of the menus: floating ones are round all over, ones stuck to the bar keep square corners where they touch it", glyph="layers")
        f.slider(yc, e.get("menu_radius"), 0, 40, lambda v: self.style_change(menu_radius=v), default=20, name="menu_radius")
        yc = f.row("Gap from the bar", "Distance between the bar and its menus, for every widget at once")
        f.slider(yc, gap if floating else None, 0, 40, lambda v: (setattr(self, "menu_gap_last", v or 10), self.cfg_change(set_menu_gap(self.cfg_text(), 10 if v is None else v)),
                                                                   self.defer_refresh()), default=10, name="menu_gap")
        f.end_card()
        f.heading("Bar", "bar")
        f.begin_card()
        yc = f.row("Bar rounding", "Corner radius of the whole bar")
        f.slider(yc, e.get("bar_radius"), 0, 40, lambda v: self.style_change(bar_radius=v), default=20, name="bar_radius")
        f.end_card()
        f.heading("Workspace pills", "pill_dots")
        f.begin_card()
        for key, title, desc, lo, hi, dflt in (("ws_radius", "Pill rounding", "Corner radius of each workspace pill", 0, 20, 9),
                                               ("ws_h", "Pill height", "Height of each pill", 12, 36, 24),
                                               ("ws_w_empty", "Width: empty", "A workspace with no windows", 8, 60, 24),
                                               ("ws_w_pop", "Width: with windows", "A workspace that has windows", 8, 60, 28),
                                               ("ws_w_active", "Width: active", "The workspace you are on", 8, 80, 40),
                                               ("ws_gap", "Space between pills", "Left and right of each pill", 0, 14, 5)):
            yc = f.row(title, desc)
            f.slider(yc, e.get(key), lo, hi, lambda v, k=key: self.style_change(**{k: v}), default=dflt, name=key)
        f.end_card()
        ws = ["widgets", "komorebi_workspaces", "options"]
        f.heading("Workspaces", "pill_dots")
        if find_key(text.split("\n"), ws) is None:
            f.note("The komorebi_workspaces widget is not in config.yaml, so there is nothing to set here.")
        else:
            f.begin_card()
            labels = lambda: yaml_get(self.cfg_text(), ws + ["label_workspace_btn"], "{name}") != ""

            def set_labels(on):
                for k in ("label_workspace_btn", "label_workspace_active_btn", "label_workspace_populated_btn"):
                    self.cfg_set(ws + [k], "{name}" if on else "")
            yc = f.row("Show workspace labels", "The number or name on each workspace button", glyph="pill_dots")
            f.toggle(yc, labels(), set_labels, name="ws_labels")
            for key, title, desc in (("enabled_populated", "App icons on busy workspaces", "Show the icons of the apps running there"),
                                     ("enabled_active", "App icons on the active workspace", "Show the icons of the apps on the one you are on"),
                                     ("hide_duplicates", "Hide duplicate icons", "One icon per app, even with several windows"),
                                     ("hide_label", "Hide the label when icons show", "Icons only")):
                yc = f.row(title, desc, glyph="window")
                f.toggle(yc, bool(yaml_get(text, ws + ["app_icons", key], False)), lambda v, k=key: self.cfg_set(ws + ["app_icons", k], v), name="ws_" + key)
            f.end_card()
        types = read_widgets(text)
        find = lambda t: next((n for n, ty in types.items() if ty == t), None)
        aw = find("yasb.active_window.ActiveWindowWidget")
        if aw:
            ao = ["widgets", aw, "options"]
            f.heading("Active window title", "title")
            f.begin_card()
            yc = f.row("Truncate title after", "Characters shown before the title is cut with an ellipsis")
            f.slider(yc, yaml_get(text, ao + ["max_length"], None), 5, 120,
                     lambda v: self.cfg_set(ao + ["max_length"], 40 if v is None else v), unit="chars", default=40, name="aw_len")
            yc = f.row("Show the app icon", "An icon in front of the title (off = text only)")
            f.toggle(yc, bool(yaml_get(text, ao + ["label_icon"], False)), lambda v: self.cfg_set(ao + ["label_icon"], v), name="aw_icon")
            yc = f.row("Icon size", "Only used when the icon is on")
            f.slider(yc, yaml_get(text, ao + ["label_icon_size"], None), 12, 24,
                     lambda v: self.cfg_set(ao + ["label_icon_size"], 16 if v is None else v), default=16, name="aw_icon_size")
            f.end_card()
        cava = find("yasb.cava.CavaWidget")
        if cava:
            co = ["widgets", cava, "options"]
            f.heading("Audio visualizer (Cava)", "audio")
            f.begin_card()
            for key, title, desc, lo, hi, dflt, nm in (("bars_number", "Cava bars", "How many bars", 1, 24, 4, "cava_bars"),
                                                       ("bar_width", "Cava bar width", "Thickness of each bar (3 to 5 looks chunky)", 1, 10, 4, "cava_width"),
                                                       ("bar_spacing", "Cava bar spacing", "Space between the bars", 0, 10, 3, "cava_spacing"),
                                                       ("bar_height", "Cava bar height", "Tallest a bar can get, in pixels", 4, 40, 16, "cava_height")):
                yc = f.row(title, desc)
                f.slider(yc, yaml_get(text, co + [key], None), lo, hi, lambda v, k=key, d=dflt: self.cfg_set(co + [k], d if v is None else v), default=dflt, name=nm)
            yc = f.row("Cava colour", "Hex colour of the bars, for example #44381f")
            box = f.entry(yc, 180, str(yaml_get(text, co + ["foreground"], "#ffffff")), name="cava_colour")

            def colour_typed(_=None, box=box):
                c = th.parse_colour(box.get())
                if c:
                    self.cfg_set(co + ["foreground"], "#%02x%02x%02x" % c[:3])
            box.bind("<KeyRelease>", colour_typed)
            f.end_card()
        if bar is None:
            return f
        f.heading(f"Behaviour  -  {bar}", "bar")
        f.begin_card()
        for key, title, desc in (("auto_hide", "Auto hide", "Slide the bar away until the mouse reaches the screen edge"),
                                 ("hide_on_fullscreen", "Hide on fullscreen", "Get out of the way of games and videos"),
                                 ("always_on_top", "Always on top", "Stay above other windows"),
                                 ("windows_app_bar", "Reserve space", "Windows keeps other windows clear of the bar")):
            yc = f.row(title, desc)
            f.toggle(yc, bool(yaml_get(text, ["bars", bar, "window_flags", key], False)), lambda v, k=key: self.cfg_set(["bars", bar, "window_flags", k], v), name="flag_" + key)
        yc = f.row("Animation", "Slide or fade the bar in and out")
        f.toggle(yc, bool(yaml_get(text, ["bars", bar, "animation", "enabled"], False)), lambda v: self.cfg_set(["bars", bar, "animation", "enabled"], v), name="anim_on")
        yc = f.row("Animation style", "How the bar appears when it auto hides")
        f.segmented(yc, ["slide", "fade"], yaml_get(text, ["bars", bar, "animation", "type"], "slide"),
                    lambda v: self.cfg_set(["bars", bar, "animation", "type"], v), name="anim_type")
        yc = f.row("Animation speed", "How long it takes")
        f.slider(yc, yaml_get(text, ["bars", bar, "animation", "duration"], None), 50, 1000,
                 lambda v: self.cfg_set(["bars", bar, "animation", "duration"], v if v is not None else 300), unit="ms", default=300, name="anim_ms")
        f.end_card()
        return f

    # ---- Templates ----------------------------------------------------------------------------------
    def page_templates(self):
        f, c = self.draw_main("Templates", "layers"), self.c
        f.note("Choose which apps get a theme from your colour scheme, and the folder each one is written to. "
               "The box shows where it goes now; change it to use another folder (several folders: separate them with ;).")
        f.heading("Write now", "layers")
        f.begin_card()
        yc = f.row("Write all the themes", "Every app below that is switched on")
        f.button(yc, "Apply now", self.apply_apps, primary=True, name="apply_now")
        f.end_card()
        f.heading("Apps", "grid")
        on_now = set(th.enabled_apps())
        keys = [r[0] for r in th.APP_TABLE]
        default_on = {k for k in keys if k not in th.OPT_IN_APPS}

        def flip(key, on):
            on_now.add(key) if on else on_now.discard(key)
            env_unset("YASB_APPS") if on_now == default_on else env_set("YASB_APPS", ",".join(k for k in keys if k in on_now) or "none")
            self.say("Saved")
            if key == "windhawk":
                self.defer_refresh()
        for key, name, var, many, desc, _ in th.APP_TABLE:
            if key == "windhawk":
                self.windhawk_card(f, key, name, desc, key in on_now, flip)
                continue
            pairs, _sub = th.defaults(key)
            found = [folder for marker, folder in pairs if marker.is_dir()] or [folder for _, folder in pairs]
            default = ";".join(str(folder).replace("\\", "/") for folder in found) or "(none found yet - use the folder button)"
            custom = th.env(var)
            f.begin_card()
            yc = f.row(name, desc, glyph=self.APP_ICONS[key], h=212 if key == "helium" else 162 if key == "filepilot" else 112, top=True)
            f.toggle(yc, key in on_now, lambda v, k=key: flip(k, v), name=f"app:{key}")
            y2 = yc + 56
            box = {}

            def commit(_=None, var=var, default=default, box=box):
                v = box["e"].get().strip()
                if not v or v == default:
                    env_unset(var)
                    box["e"].config(fg=c["muted"])
                else:
                    env_set(var, v)
                    box["e"].config(fg=c["text"])
                self.say("Saved")

            def reset(var=var, default=default, box=box):
                env_unset(var)
                box["e"].delete(0, "end")
                box["e"].insert(0, default)
                box["e"].config(fg=c["muted"])
                self.say("Back to the default folder")

            def pick(var=var, many=many, default=default, box=box, name=name, commit=commit):  # commit=commit: bind this row's own
                now = box["e"].get().strip().split(";")[-1]
                folder = self.ask_dir(title=f"{name} folder", initialdir=now if now and Path(now).is_dir() else str(Path.home()))
                if folder:
                    old = th.env(var)
                    new = (old + ";" + folder) if (many and old and folder not in old.split(";")) else folder
                    box["e"].delete(0, "end")
                    box["e"].insert(0, new)
                    commit()
            x = f.ibutton(y2, "reset", reset, x=f.r, name=f"reset:{key}")
            x = f.ibutton(y2, "folder", pick, x=x, name=f"pick:{key}")
            box["e"] = f.entry(y2, x - (f.l + 38), custom or default, x=x, name=f"path:{key}", colour=c["text"] if custom else c["muted"])
            box["e"].bind("<Return>", commit)
            box["e"].bind("<FocusOut>", commit)
            if key == "filepilot":  # it rewrites its config when it closes: the colours are written while it is closed
                f.cv.create_text(f.l, y2 + 50, text="File Pilot overwrites its colours when it closes, so they are written while it is closed", anchor="w",
                                 fill=c["muted"], font=self.f(9))
                f.button(y2 + 50, "Sure?" if self.armed("filepilot") else "Restart File Pilot", self.do_restart_filepilot, glyph="reset", x=f.r,
                         primary=self.armed("filepilot"), name="filepilot_restart")
            if key == "helium":  # a browser reads its theme when it starts: a button that restarts it
                f.cv.create_text(f.l, y2 + 50, text="Helium reads a changed theme when it starts (its reload arrow is not reliable)", anchor="w",
                                 fill=c["muted"], font=self.f(9))
                x = f.button(y2 + 50, "Sure?" if self.armed("helium") else "Restart Helium", self.do_restart_helium, glyph="reset", x=f.r,
                             primary=self.armed("helium"), name="helium_restart")
                f.cv.create_text(f.l, y2 + 100, text="Restart it by itself when the theme changes (closes it, reopens it with your tabs)", anchor="w",
                                 fill=c["muted"], font=self.f(9))
                f.toggle(y2 + 100, th.env("YASB_HELIUM_AUTORESTART") == "1", lambda v: (env_set("YASB_HELIUM_AUTORESTART", "1" if v else "0"),
                         self.say("Helium restarts by itself after a theme change" if v else "Helium is left alone")), x=f.r, name="helium_auto")
            f.end_card()
            f.y -= 4
        return f

    def do_restart_filepilot(self):
        if not self.confirm("filepilot", "Click again to close File Pilot and open it again with the new colours"):
            return
        self.say("Restarting File Pilot...")
        box = {}

        def work():
            box["text"] = th.restart_filepilot()
        threading.Thread(target=work, daemon=True).start()

        def check():
            if "text" not in box:
                return self.root.after(400, check)
            self.say(box["text"])
            self.defer_refresh()
        self.root.after(400, check)

    def do_restart_helium(self):
        if not self.confirm("helium", "Click again to close Helium and open it again (your tabs come back)"):
            return
        self.say("Restarting Helium...")
        box = {}

        def work():
            box["text"] = th.restart_helium()
        threading.Thread(target=work, daemon=True).start()

        def check():
            if "text" not in box:
                return self.root.after(400, check)
            self.say(box["text"])
            self.defer_refresh()
        self.root.after(400, check)

    def windhawk_card(self, f, key, name, desc, on, flip):
        """Windhawk is not a folder: its card shows whether the elevated task is set up, and offers Set up and Restore."""
        task = wh_task_cached() if on else False
        f.begin_card()
        yc = f.row(name, desc, glyph="layers", h=162 if on else 112, top=True)
        f.toggle(yc, on, lambda v: flip(key, v), name=f"app:{key}")
        y2 = yc + 56
        if not on:
            f.cv.create_text(f.l, y2, text="Off. Switch it on to colour Windhawk's styler mods with your scheme.", anchor="w", fill=self.c["muted"], font=self.f(9))
        else:
            state = th.wh_load_state()
            n = len([k for k in state if not k.startswith("_")])
            left = sum(len(v) for v in state.get("_skipped", {}).values())
            status = ("Ready: changes are written silently." if task else "Needs one UAC prompt, once, to be allowed to write Windhawk's settings.")
            f.cv.create_text(f.l, y2, text=status + (f"   Recoloured mods: {n}." if n else "") + (f"   {left} settings you changed in Windhawk are left alone." if left else ""), anchor="w", fill=self.c["muted"], font=self.f(9))

            def setup():
                self.say("Waiting for the Windows prompt...")
                self.quiet_until = time.time() + 20
                self.root.after(100, lambda: (th.wh_setup_task(), wh_task_cached(True), self.say("Windhawk is set up" if wh_task_cached() else "Not set up (prompt cancelled?)"), self.defer_refresh()))

            def restore():
                try:
                    self.say(f"Put back {th.wh_restore()} settings")
                except Exception as e:
                    self.say(str(e)[:90])
            x = f.button(y2, "Put back", restore, glyph="reset", x=f.r, name="wh_restore")
            if not task:
                f.button(y2, "Set up", setup, glyph="check", primary=True, x=x - 8, name="wh_setup")
            y3 = y2 + 50
            f.cv.create_text(f.l, y3, text="Colours  -  Capsules: the capsule colour, active = a running app on the bar", anchor="w", fill=self.c["muted"], font=self.f(9))
            f.segmented(y3, ["Capsules", "Accent shades"], "Accent shades" if th.env("YASB_WINDHAWK_MATCH") == "accent" else "Capsules",
                        lambda v: (env_set("YASB_WINDHAWK_MATCH", "accent" if v == "Accent shades" else "capsules"),
                                   self.say("Applies the next time the themes are written (Apply now)")), x=f.r, name="wh_match")
        f.end_card()
        f.y -= 4

    # ---- Edits ------------------------------------------------------------------------------------
    def page_edits(self):
        f, c = self.draw_main("Edits", "pen"), self.c
        e = self.edits
        f.note("The boxes show what is set now. Type another font or colour, then press Apply (bottom right). "
               "Colours you change become the Custom scheme at the end of the Colors grid.")
        f.heading("Fonts", "pen")
        f.begin_card()
        for key, title, desc, selectors in (("font_bar", "Bar font", "Widget text and icons (a Nerd Font stays as the fallback for the glyphs)", BAR_FONT_SELECTORS),
                                            ("font_menu", "Menu and clock font", "Menus, tooltips and the clock", MENU_FONT_SELECTORS)):
            current = css_font(selectors)
            yc = f.row(title, desc)
            box = f.entry(yc, 280, e.get(key) or current, name=key, colour=c["text"] if e.get(key) else c["muted"])

            def changed(_=None, key=key, box=box, current=current):
                v = box.get().strip()
                if v and v != current:
                    e[key] = v
                else:
                    e.pop(key, None)
                box.config(fg=c["text"] if key in e else c["muted"])
                self.stage("style")
            box.bind("<KeyRelease>", changed)
        f.end_card()
        f.heading("Colours", "palette")
        f.note("Hex (#a48e5e) or rgba(164, 142, 94, 0.9). The arrow puts a colour back to your Windows accent.")
        f.begin_card()
        now, base, mine = current_colours(), current_colours(base_only=True), e.get("colours", {})
        for label, var in COLOUR_VARS:
            yc = f.row(label, f"--yasb-{var}")
            if var in self.raw:  # changed on this page earlier (an empty string = put back to Windows)
                text, set_by_me = self.raw[var] or base.get(var, ""), bool(self.raw[var])
            else:
                text, set_by_me = mine.get(var) or now.get(var, ""), var in mine
            sw = f.cv.create_image(0, yc, anchor="e")
            box = f.entry(yc, 230, text, x=f.r - 90, name="col:" + var, colour=c["text"] if set_by_me else c["muted"])

            def update(_=None, var=var, box=box, sw=sw, base=base):
                col = parse_colour(box.get())
                shown = "#%02x%02x%02x" % col[:3] if col else base.get(var, c["input"])
                f.cv.itemconfig(sw, image=rounded(30, 30, 9, shown, c["accent"] if col else c["line"], 1))
                f.cv.coords(sw, f.r - 48, yc)

            def typed(_=None, var=var, box=box, update=update):
                self.raw[var] = box.get().strip()  # emptied by hand = put back to Windows
                box.config(fg=c["text"])
                update()
                self.stage("colours")

            def back(var=var, box=box, update=update, base=base):
                self.raw[var] = ""
                box.delete(0, "end")
                box.insert(0, base.get(var, ""))
                box.config(fg=c["muted"])
                update()
                self.stage("colours")
            box.bind("<KeyRelease>", typed)
            f.ibutton(yc, "reset", back, x=f.r, name="colreset:" + var)
            update()
        f.end_card()
        return f

    # ---- Files ------------------------------------------------------------------------------------
    def page_files(self):
        f = self.draw_main("Files", "folder")
        f.note("Every config file of YASB, komorebi and whkd. Click a file, or its Edit button, to open it in your editor.")
        groups = config_files()
        for group, glyph, files in (("YASB", "folder", "YASB"), ("Scripts", "file_code", "Scripts"), ("komorebi", "tiles", "komorebi"), ("whkd", "terminal", "whkd")):
            paths = groups[files]
            f.heading(f"{group}   -   {len(paths)} files", glyph)
            if not paths:
                f.note("Nothing found here.")
                continue
            f.begin_card()
            for p in paths[:80]:
                try:
                    size = f"{p.stat().st_size / 1024:.1f} KB"
                except OSError:
                    size = ""
                yc = f.row(p.name, f"{size}    {p.parent}", glyph=file_icon(p), click=lambda p=p: (self.launch(p), self.say(f"Opening {p.name}")))
                f.button(yc, "Edit", lambda p=p: (self.launch(p), self.say(f"Opening {p.name}")), glyph="pen", name=f"edit:{p.name}")
            f.end_card()
        return f

    # ---- Keybinds (whkdrc) ------------------------------------------------------------------------
    KEY_ROWS = (
        [("esc", "escape", 1)] + [(f"F{i}", f"f{i}", 1) for i in range(1, 13)],
        [("`", "oem_3", 1)] + [(str(i % 10), str(i % 10), 1) for i in range(1, 11)] + [("-", "oem_minus", 1), ("=", "oem_plus", 1), ("back", "backspace", 2)],
        [("tab", "tab", 1.5)] + [(k, k, 1) for k in "qwertyuiop"] + [("[", "oem_4", 1), ("]", "oem_6", 1), ("\\", "oem_5", 1.5)],
        [("", None, 1.75)] + [(k, k, 1) for k in "asdfghjkl"] + [(";", "oem_1", 1), ("'", "oem_7", 1), ("enter", "return", 2.25)],
        [("shift", "shift", 2.25)] + [(k, k, 1) for k in "zxcvbnm"] + [(",", "oem_comma", 1), (".", "oem_period", 1), ("/", "oem_2", 1), ("shift", "shift", 2.75)],
        [("ctrl", "ctrl", 1.25), ("win", "win", 1.25), ("alt", "alt", 1.25), ("space", "space", 4.5), ("alt", "alt", 1), ("ctrl", "ctrl", 1),
         ("<", "left", 1), ("^", "up", 1), ("v", "down", 1), (">", "right", 1)],
    )

    def whkd_text(self):
        """The whkdrc as it is now (with your unapplied changes), or None if there is none."""
        if self.kb_text is not None:
            return self.kb_text
        try:
            return whkdrc_path().read_text(encoding="utf-8")
        except OSError:
            return None

    def kb_commit(self, text):
        self.kb_text = text
        self.stage("whkd")

    def kb_event(self, e):
        """Keys you press on the keyboard light up on the Keybinds page (not while you type in one of its boxes)."""
        if self.closing or self.view_results or PAGES[self.current][0] != "Keybinds":
            return
        try:
            if isinstance(self.root.focus_get(), tk.Entry):
                return
        except (KeyError, tk.TclError):
            return
        name = tk_key(e.keysym)
        if not name:
            return
        down = e.type == tk.EventType.KeyPress
        if down == (name in self.kb_down):
            return  # a key you hold repeats itself: nothing changed, so nothing is redrawn
        (self.kb_down.add if down else self.kb_down.discard)(name)
        self.kb_soon()

    def kb_soon(self):
        """Redraw the page a moment after the last key event."""
        if self.kb_job:
            self.root.after_cancel(self.kb_job)

        def redraw():
            self.kb_job = None
            if frozenset(self.kb_sel | self.kb_down) != getattr(self, "kb_drawn", None):  # only when the held keys are not what is shown
                self.go(self.current, keep=True)
        self.kb_job = self.root.after(60, redraw)

    def draw_keyboard(self, f, used, pressed, combo):
        """The keyboard: keys that are in a keybind are lit, the ones you hold are filled, and the ones that would complete a
        keybind with the keys you hold have an outline. Click a key to hold it. Returns {key name: its image item}."""
        c, cv, gap = self.c, f.cv, 5
        unit = (f.cw - gap * 14) / 15
        items = {}
        y = f.y
        for r, row in enumerate(self.KEY_ROWS):
            h = 30 if r == 0 else 42
            x = 0
            for label, name, units in row:
                w = units * unit + (units - 1) * gap if units > 1 else unit
                if name:
                    held, hint, lit = name in pressed, name in combo, name in used
                    fill = c["accent"] if held else c["hover"] if lit else c["input"]
                    outline = c["accent2"] if hint and not held else c["line"] if not held else None
                    ink = c["ink"] if held else c["accent2"] if hint else c["text"] if lit else c["muted"]
                    tag = f"kbd{name}"
                    img = cv.create_image(x, y, image=rounded(round(w), h, 9, fill, outline, 2 if hint else 1), anchor="nw", tags=tag)
                    cv.create_text(x + w / 2, y + h / 2, text=label, fill=ink, font=self.f(9 if len(label) > 2 else 11, "bold" if lit or held else "normal"), tags=tag)
                    cv.tag_bind(tag, "<Button-1>", lambda e, n=name: (self.sfx.play("tap"), self.kb_sel.symmetric_difference_update({n}), self.kb_soon()))
                    cv.tag_bind(tag, "<Enter>", lambda e: cv.config(cursor="hand2"))
                    cv.tag_bind(tag, "<Leave>", lambda e: cv.config(cursor=""))
                    items.setdefault(name, img)
                x += w + gap
            y += h + gap
        f.y = y + 10
        return items

    def page_keybinds(self):
        f, c = self.draw_main("Keybinds", "keyboard"), self.c
        text = self.whkd_text()
        if text is None:
            f.note(f"There is no whkdrc yet (it would be {whkdrc_path()}).")
            f.begin_card()
            yc = f.row("Create a whkdrc", "An empty one that uses PowerShell, ready for your keybinds", glyph="keyboard")
            f.button(yc, "Create", lambda: (self.kb_commit(".shell powershell\n\n"), self.defer_refresh()), glyph="plus", primary=True, name="kb_create")
            f.end_card()
            return f
        rows = parse_whkdrc(text)
        used = {k for r in rows for k in r["keys"]}
        pressed = self.kb_sel | self.kb_down
        self.kb_drawn = frozenset(pressed)
        shown = [r for r in rows if pressed <= set(r["keys"])]
        combo = {k for r in shown for k in r["keys"]} - pressed if pressed else set()
        f.note("Press keys on your keyboard, or click them below, to see every keybind that uses them. Keys that are lit are in a keybind; "
               "an outlined key would complete one with the keys you are holding. Changes wait for Apply; whkd restarts then.")
        f.heading("Keyboard", "keyboard")
        f.hits["kb_keys_items"] = self.draw_keyboard(f, used, pressed, combo)
        f.begin_card()
        status = ("Holding:  " + format_keys(sorted(pressed))) if pressed else "Nothing held. Press keys, or click them above."
        yc = f.row("Keys", status, glyph="keyboard")
        f.button(yc, "Clear", lambda: (self.kb_sel.clear(), self.kb_down.clear(), self.kb_soon()), glyph="x", name="kb_clear")
        f.end_card()
        f.heading(f"Keybinds   -   {len(shown)} of {len(rows)}", "list" if "list" in ICONS else "file_text")
        f.begin_card()
        yc = f.row("Add a keybind", "A new line at the end of your whkdrc", glyph="plus")
        f.button(yc, "Add", lambda: (setattr(self, "kb_edit", {"start": None, "keys": format_keys(sorted(pressed)), "cmd": ""}), self.defer_refresh()),
                 glyph="plus", primary=True, name="kb_add")
        edit = self.kb_edit
        if edit is not None:
            yc = f.row("Keys", "For example: alt + shift + h", glyph="keyboard")
            x = f.button(yc, "From keyboard", lambda: self.kb_fill(f), glyph="keyboard", name="kb_from")
            f.entry(yc, 230, edit["keys"], x=x - 10, name="kb_keys")
            yc = f.row("Command", "What runs, for example: komorebic focus left", glyph="terminal")
            f.entry(yc, 460, edit["cmd"], name="kb_cmd")
            yc = f.row("Editing" if edit["start"] is not None else "New keybind", "Save puts it in the list. It reaches whkdrc when you press Apply.", glyph="pen")
            x = f.button(yc, "Save", lambda: self.kb_save(f), glyph="check", primary=True, name="kb_save")
            f.button(yc, "Cancel", lambda: (setattr(self, "kb_edit", None), self.defer_refresh()), glyph="x", x=x - 8, name="kb_cancel")
        f.cv.photos = getattr(f.cv, "photos", [])
        for r in shown:
            desc = r["cmd"] + (f"   -   {r['group']}" if r["group"] else "")
            yc = f.row(keybind_title(r), desc, glyph="keyboard")
            x = f.ibutton(yc, "trash", lambda r=r: self.kb_delete(r), name=f"kb_del:{r['start']}")
            x = f.ibutton(yc, "pen", lambda r=r: (setattr(self, "kb_edit", {"start": r["start"], "keys": r["keys_text"], "cmd": r["cmd"]}), self.defer_refresh()),
                          x=x, name=f"kb_edit:{r['start']}")
            pw = int(self.f(10).measure(r["keys_text"]) + 40)  # the keys, as a pill
            pill = pill_button(r["keys_text"], pw, 30, c["input"], c["accent2"], c["line"], None, 12, None)
            f.cv.photos.append(pill)
            f.cv.create_image(x - 8 - pw, yc, image=pill, anchor="w")
            f.fit(x - 8 - pw)
        if not shown:
            f.row("No keybind uses these keys" if pressed else "No keybinds yet", "Add one above." if not pressed else "Press fewer keys, or Clear.", glyph="keyboard")
        f.end_card()
        return f

    def kb_fill(self, f):
        box = f.hits.get("kb_keys")
        if box is not None:
            box.delete(0, "end")
            box.insert(0, format_keys(sorted(self.kb_sel | self.kb_down)))

    def kb_save(self, f):
        edit, text = self.kb_edit, self.whkd_text()
        keys_text, cmd = f.hits["kb_keys"].get().strip(), f.hits["kb_cmd"].get().strip()
        keys = split_keys(keys_text)
        if not keys or all(k in MODIFIERS for k in keys):
            return self.say("A keybind needs a key besides alt, ctrl, shift and win")
        if not cmd:
            return self.say("Type the command that should run")
        rows = parse_whkdrc(text)
        clash = next((r for r in rows if set(r["keys"]) == set(keys) and r["start"] != edit["start"]), None)
        if clash:
            return self.say(f"{format_keys(keys)} is already used for: {clash['cmd'][:50]}")
        if edit["start"] is None:
            new = add_keybind(text, keys_text, cmd)
        else:
            new = replace_keybind(text, next(r for r in rows if r["start"] == edit["start"]), keys_text, cmd)
        self.kb_edit = None
        self.kb_commit(new)
        self.say("Keybind saved - press Apply")
        self.defer_refresh()

    def kb_delete(self, bind):
        self.kb_commit(delete_keybind(self.whkd_text(), bind))
        self.say(f"{bind['keys_text']} removed - press Apply")
        self.defer_refresh()

    # ---- Backup -----------------------------------------------------------------------------------
    def armed(self, key):
        """A button that asks twice (restore, delete): the first click arms it for a few seconds."""
        return getattr(self, "arm", None) is not None and self.arm[0] == key and time.time() - self.arm[1] < 6

    def confirm(self, key, question):
        """True on the second click within 6 seconds; the first click only asks."""
        if self.armed(key):
            self.arm = None
            return True
        self.arm = (key, time.time())
        self.say(question)
        self.defer_refresh()
        return False

    def do_backup(self):
        try:
            path = make_backup()
            self.say(f"Backed up: {path.name}")
        except OSError as e:
            self.sfx.play("error")
            self.say(f"Could not back up: {e}")
        self.defer_refresh()

    def do_restore(self, path):
        if not self.confirm(("restore", path), "Click Restore again to replace your current files with this backup"):
            return
        try:
            done = restore_backup(path)
        except (OSError, zipfile.BadZipFile) as e:
            self.sfx.play("error")
            return self.say(f"Could not restore: {e}")
        self.quiet_reset = True
        self.reset_all()  # what is on screen now comes from the restored files; anything staged is dropped
        self.quiet_reset = False
        on, vol = sound_settings()
        self.sfx.configure(enabled=on, volume=vol)
        if "komorebi/komorebi.json" in done:
            reload_komorebi()
        self.say(f"Restored {len(done)} files - YASB reloads by itself")

    def do_delete(self, path):
        if self.confirm(("delete", path), "Click Delete again to remove this backup for good"):
            path.unlink(missing_ok=True)
            self.say("Backup deleted")
            self.defer_refresh()

    def do_clear_logs(self):
        for p in log_files():
            try:
                p.unlink()
            except OSError:
                pass
        self.say("Log files deleted")
        self.defer_refresh()

    def do_report(self):
        """Run `theme.py doctor` (it checks everything and writes shellflow_doctor.txt), then open the report."""
        exe = Path(sys.executable).with_name("python.exe")
        exe = exe if exe.exists() else Path(sys.executable)
        flags = {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}
        box = {}

        def work():
            try:
                subprocess.run([str(exe), str(th.HERE / "theme.py"), "doctor"], capture_output=True, timeout=180, **flags)
            except (OSError, subprocess.SubprocessError):
                pass
            box["done"] = True
        threading.Thread(target=work, daemon=True).start()
        self.say("Writing the report - a few seconds")

        def check():
            if not box.get("done"):
                return self.root.after(400, check)
            report = th.HERE / "shellflow_doctor.txt"
            self.say("Report saved - opening it" if report.exists() else "The report could not be written")
            if report.exists():
                self.launch(report)
        self.root.after(400, check)

    def page_backup(self):
        f = self.draw_main("Backup", "archive")
        f.note("Backups and logs only happen when you press a button here. ShellFlow never copies or logs things on its own "
               "(errors are the one exception: they are noted in theme_error.log).")
        f.heading("Back up", "archive")
        f.begin_card()
        yc = f.row("Back up now", "config.yaml, styles.css, .env, your edits, notes, komorebi.json and whkdrc, in one zip", glyph="archive")
        f.button(yc, "Back up now", self.do_backup, glyph="archive", primary=True, name="backup_now")
        yc = f.row("Backups folder", str(BACKUP_DIR), glyph="folder")
        f.button(yc, "Open", lambda: (BACKUP_DIR.mkdir(exist_ok=True), self.launch(BACKUP_DIR)), glyph="folder", name="backup_open")
        olds = old_copies()
        if olds:
            yc = f.row("Old automatic copies", ", ".join(p.name for p in olds) + " - older versions made these; nothing uses them", glyph="file")
            f.button(yc, "Delete", lambda: ([p.unlink(missing_ok=True) for p in olds], self.say("Old copies deleted"), self.defer_refresh()),
                     glyph="trash", name="delete_old")
        f.end_card()
        backups = list_backups()
        f.heading(f"Your backups   -   {len(backups)}", "layers")
        if not backups:
            f.note("No backups yet. Press Back up now before a big change.")
        else:
            f.begin_card()
            for path, count, size in backups[:30]:
                yc = f.row(backup_title(path), f"{count} files, {size_text(size)}", glyph="archive")
                x = f.button(yc, "Sure?" if self.armed(("delete", path)) else "Delete", lambda p=path: self.do_delete(p), glyph="trash", name=f"delete:{path.name}")
                f.button(yc, "Click again" if self.armed(("restore", path)) else "Restore", lambda p=path: self.do_restore(p), glyph="reset",
                         primary=self.armed(("restore", path)), x=x - 8, name=f"restore:{path.name}")
            f.end_card()
        f.heading("Log files", "file_text")
        f.begin_card()

        def set_logs(v):
            env_set("YASB_LOGS", "1" if v else "0")
            th._LOGS = None  # this window reads the setting again
            self.say("Log files on" if v else "Log files off (the ones already written stay until you clear them)")
        yc = f.row("Keep log files", "Off: no start or helper logs are written. Turn it on while you track down a problem.", glyph="file_text")
        f.toggle(yc, th.env("YASB_LOGS") == "1", set_logs, name="logs_on")
        for p in log_files():
            yc = f.row(p.name, f"{size_text(p.stat().st_size)}    {p.parent}", glyph="file_text", click=lambda p=p: self.launch(p))
            f.button(yc, "Open", lambda p=p: self.launch(p), glyph="arrow_ur", name=f"log:{p.name}")
        if not log_files():
            f.row("No log files", "Nothing has been written.", glyph="file_text")
        yc = f.row("Diagnostic report", "Checks Python, Windows, YASB, the helper and every page, and saves it as shellflow_doctor.txt", glyph="info")
        f.button(yc, "Create", self.do_report, glyph="pen", name="report")
        if log_files():
            yc = f.row("Clear log files", "Deletes the logs listed above", glyph="trash")
            f.button(yc, "Clear", self.do_clear_logs, glyph="trash", name="logs_clear")
        f.end_card()
        return f

    # ---- About ------------------------------------------------------------------------------------
    def page_about(self):
        f, c = self.draw_main("About", "info"), self.c
        f.cv.logo = logo_img(96, c["accent"], c["ink"])
        f.cv.create_image(0, 14, image=f.cv.logo, anchor="nw")
        f.cv.create_text(124, 36, text=APP_NAME, anchor="w", fill=c["accent2"], font=self.f(22, "bold"))
        f.cv.create_text(124, 70, text="A settings window for YASB, komorebi and the apps that follow your accent", anchor="w", fill=c["muted"], font=self.f(10))
        f.cv.create_text(124, 94, text="YASB " + yasb_version(), anchor="w", fill=c["text"], font=self.f(11, "bold"))
        f.y = 132
        x = f.button(f.y + 18, "Open config folder", lambda: self.launch(th.CONFIG), glyph="folder", x=f.cw, name="about_open") - 10
        info = lambda: "\n".join(f"{k}: {v}" for k, v in self.system_info())
        f.button(f.y + 18, "Copy info", lambda: (self.root.clipboard_clear(), self.root.clipboard_append(info()), self.say("Copied")), glyph="copy", x=x, name="about_copy")
        f.y += 56
        f.heading("System information", "monitor")
        for k, v in self.system_info():
            f.kv(k, v)
        return f

    def system_info(self):
        if self._monitors is None:
            self._monitors = list_monitors()
        return [("Windows", platform.platform()), ("Python", sys.version.split()[0]), ("YASB", yasb_version()),
                ("komorebi", komorebi_version()), ("Monitors", ", ".join(self._monitors) or "not found (yasbc not on PATH)"),
                ("Accent", th.hx(th.accent_shades()["accent"])), ("Config folder", str(th.CONFIG)),
                ("komorebi folder", str(komorebi_dir()))]

    # ---- Display ----------------------------------------------------------------------------------
    def page_display(self):
        f, bar = self.bar_tabs("Display", "monitor")
        text, e = self.cfg_text(), self.edits
        if bar is not None:
            f.heading(f"Bar placement  -  {bar}", "bar")
            if self._monitors is None:
                self._monitors = list_monitors()
            current = get_screens(text, bar)
            options = list(dict.fromkeys(self._monitors + current + ["primary", "*"]))
            f.note("Monitor: pick one or more. primary = your main screen, * = every screen without its own bar.")
            f.chips(options, set(current), lambda s: (self.cfg_change(set_screens(self.cfg_text(), bar, [o for o in options if o in s] or ["*"]))), name="screen")
            f.begin_card()
            yc = f.row("Position", "Top or bottom of the screen")
            f.segmented(yc, ["top", "bottom"], yaml_get(text, ["bars", bar, "alignment", "position"], "top"),
                        lambda v: self.cfg_set(["bars", bar, "alignment", "position"], v), name="position")
            yc = f.row("Bar height", "In pixels")
            f.slider(yc, yaml_get(text, ["bars", bar, "dimensions", "height"], None), 30, 100,
                     lambda v: self.cfg_set(["bars", bar, "dimensions", "height"], v if v is not None else 58), default=58, name="height")
            yc = f.row("Space above the bar", "Gap between the top screen edge and the bar")
            f.slider(yc, yaml_get(text, ["bars", bar, "padding", "top"], None), 0, 40,
                     lambda v: self.cfg_set(["bars", bar, "padding", "top"], v if v is not None else 12), default=12, name="padding_top")
            yc = f.row("Space below the bar", "Gap between the bar and the bottom screen edge (matters most for a bottom bar)")
            f.slider(yc, yaml_get(text, ["bars", bar, "padding", "bottom"], None), 0, 40,
                     lambda v: self.cfg_set(["bars", bar, "padding", "bottom"], v if v is not None else 0), default=0, name="padding_bottom")
            yc = f.row("Background opacity", "How see-through the bar background is (every bar)")
            f.slider(yc, e.get("opacity"), 0, 100, lambda v: self.style_change(opacity=v), unit="%", default=100, name="opacity")
            f.end_card()
        f.heading("Komorebi", "tiles")
        k = self.kom_data()
        if k is None:
            f.note(f"komorebi.json was not found in {komorebi_dir()}, or it is not plain JSON (comments are not allowed). "
                   "Set KOMOREBI_CONFIG_HOME in your .env if it lives elsewhere.")
            return f

        def get(path, default=None):
            d = k
            for p in path.split("."):
                d = d.get(p) if isinstance(d, dict) else None
            return default if d is None else d

        def put(path, value):
            d, parts = k, path.split(".")
            for p in parts[:-1]:
                d = d.setdefault(p, {}) if isinstance(d.get(p, {}), dict) else d
            d[parts[-1]] = value
            self.kom = k
            self.stage("kom")
        f.begin_card()
        for path, title, desc, lo, hi, dflt in (("default_workspace_padding", "Outer gap", "Space between the windows and the screen edge", 0, 60, 10),
                                                ("default_container_padding", "Inner gap", "Space between tiled windows", 0, 60, 10),
                                                ("border_width", "Border width", "Thickness of the focus border", 0, 20, 8),
                                                ("border_offset", "Border offset", "Moves the border in (negative) or out (positive)", -10, 10, -1)):
            yc = f.row(title, desc)
            f.slider(yc, get(path), lo, hi, lambda v, p=path, d=dflt: put(p, d if v is None else v), default=dflt, name=path)
        yc = f.row("Focus border", "Draw a border around the focused window")
        f.toggle(yc, bool(get("border", False)), lambda v: put("border", v), name="border")
        yc = f.row("Border style", "System follows Windows 11 rounding")
        f.segmented(yc, ["System", "Rounded", "Square"], get("border_style", "System"), lambda v: put("border_style", v), name="border_style")
        yc = f.row("New windows", "Create a new tile, or append to the focused one")
        f.segmented(yc, ["Create", "Append"], get("window_container_behaviour", "Create"), lambda v: put("window_container_behaviour", v), name="behaviour")
        yc = f.row("Mouse follows focus", "Move the pointer to the window you focus")
        f.toggle(yc, bool(get("mouse_follows_focus", False)), lambda v: put("mouse_follows_focus", v), name="mouse_follows")
        yc = f.row("Transparency", "Make unfocused windows slightly see-through")
        f.toggle(yc, bool(get("transparency", False)), lambda v: put("transparency", v), name="transparency")
        if not isinstance(k.get("animation", {}), bool):
            yc = f.row("Animations", "Animate windows when they tile")
            f.toggle(yc, bool(get("animation.enabled", False)), lambda v: put("animation.enabled", v), name="kom_anim")
        f.end_card()
        return f


# ============================================================================================
#  10. ENTRY POINT
# ============================================================================================
def dark_titlebar(root):
    """A dark title bar on Windows 10/11 (only with YASB_SETTINGS_TITLEBAR=native)."""
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
    except Exception:
        pass


def to_front(root, attach=(None, "center"), bar_pad=0, width=W, x=None, edge_y=None, dy=0):
    """Put the window on the monitor under the cursor and bring it to the front: in the middle, or attached to the bar (touching it, at
    the x it is given: the left end of the bar plus 10 px)."""
    try:
        work, _ = th.monitor_info()
        left = work[0] + max(0, (work[2] - work[0] - width) // 2)
        y = work[1] + max(0, (work[3] - work[1] - H) // 2)
        edge, _ = attach
        if edge:
            left = left if x is None else x
            y = work[1] - bar_pad if edge == "top" else work[3] - H + bar_pad  # the work area starts where the bar's space ends
            if edge_y is not None:  # the visible bar's real edge, asked of Windows
                y = edge_y if edge == "top" else edge_y - H
            y += dy  # your own nudge (Window > Move up or down)
        root.geometry(f"{width}x{H}+{left}+{y}")
    except Exception:
        pass
    root.deiconify()
    root.lift()
    root.attributes("-topmost", True)  # only for a moment, so it cannot open behind other windows
    root.after(500, lambda: root.attributes("-topmost", False))
    root.focus_force()


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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        th.log("settings.py")
        start_log("FAILED: " + traceback.format_exc().strip().splitlines()[-1])
        th.show_error()
        raise
