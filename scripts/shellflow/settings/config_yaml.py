"""Editing config.yaml as text: bars, widgets, zones, menus, popups. Comments and layout of the rest of the file are never touched."""
import re
from .. import api as th
from .catalog import CATALOG, NOTES_ICONS, catalog_lines
from .constants import CONFIG_YAML, ZONES, parse_colour
from .state import load_edits

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
    return "exec " + q(str(th.pythonw()).replace("\\", "/")) + " " + q(str(th.LAUNCHER).replace("\\", "/")) + " settings"


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
