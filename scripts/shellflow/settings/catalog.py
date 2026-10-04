"""Widgets that can be added from the Widgets page."""

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
