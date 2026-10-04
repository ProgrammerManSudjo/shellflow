"""themes.zed"""
import json
from ..colors import al
from ..core import defaults, folders, save

def write_zed(P):
    """Zed: yasb-colors.json, a dark theme called "YASB Accent" (white text, accent-coloured UI).
    Default:  %APPDATA%/Zed/themes
    Variable: YASB_ZED_THEMES
    Then:     pick "YASB Accent" in Zed's theme selector."""
    t, clear, white = P.t, "#00000000", "#ffffff"
    bg, ed = t(.07), t(.05)
    style = {
        "background": bg, "background.appearance": "opaque",
        "surface.background": t(.08), "elevated_surface.background": t(.11),
        "border": t(.32), "border.variant": t(.20), "border.focused": P.acc,
        "border.selected": P.l1, "border.transparent": clear,
        "element.background": t(.22), "element.hover": t(.35), "element.active": t(.45),
        "element.selected": al(P.l1, .24),
        "ghost_element.background": clear, "ghost_element.hover": t(.20),
        "ghost_element.active": t(.30), "ghost_element.selected": al(P.l1, .20),
        "text": white, "text.muted": "#bfbfbf", "text.placeholder": "#8c8c8c",
        "text.disabled": "#6b6b6b", "text.accent": P.l1,
        "icon": white, "icon.muted": "#bfbfbf", "icon.disabled": "#6b6b6b", "icon.accent": P.l1,
        "status_bar.background": t(.12), "title_bar.background": t(.16), "title_bar.inactive_background": t(.10), "toolbar.background": ed,
        "tab_bar.background": t(.10), "tab.inactive_background": t(.10), "tab.active_background": t(.20),
        "panel.background": t(.08), "panel.focused_border": P.acc,
        "search.match_background": al(P.l1, .30),
        "scrollbar.thumb.background": al(P.l1, .25), "scrollbar.thumb.hover_background": al(P.l1, .40),
        "editor.foreground": white, "editor.background": ed, "editor.gutter.background": ed,
        "editor.active_line.background": al(P.l1, .10), "editor.highlighted_line.background": al(P.l1, .14),
        "editor.line_number": "#8c8c8c", "editor.active_line_number": "#e6e6e6",
        "editor.wrap_guide": al(P.l1, .12), "editor.active_wrap_guide": al(P.l1, .25),
        "editor.indent_guide": al(P.l1, .10), "editor.indent_guide_active": al(P.l1, .30),
        "editor.document_highlight.read_background": al(P.l1, .16),
        "terminal.background": ed, "terminal.foreground": white, "link_text.hover": P.l2,
        "players": [{"cursor": P.l1, "background": P.l1, "selection": al(P.l1, .28)}],
    }
    groups = [  # syntax colour -> the syntax keys that use it
        (P.l1, "keyword tag label string.escape variable.special title emphasis emphasis.strong"),
        (P.l2, "type constructor enum variant"),
        ("#e6e6e6", "operator punctuation.list_marker punctuation.special"),
        (white, "variable embedded primary"),
        (P.sec(80), "string link_text text.literal"), (P.sec(70), "property"),
        (P.ter(80), "function attribute string.regex string.special string.special.symbol"),
        (P.ter(70), "number boolean constant link_uri"),
        (P.neu(70), "punctuation punctuation.bracket punctuation.delimiter preproc"), (P.neu(60), "hint"),
    ]
    syntax = {k: {"color": colour} for colour, keys in groups for k in keys.split()}
    for k in ("comment", "comment.doc", "predictive"):
        syntax[k] = {"color": P.neu(55), "font_style": "italic"}
    syntax["emphasis"]["font_style"] = "italic"
    syntax["title"]["font_weight"] = syntax["emphasis.strong"]["font_weight"] = 700
    style["syntax"] = syntax
    save(folders("YASB_ZED_THEMES", *defaults("zed")), "yasb-colors.json",
         json.dumps({"$schema": "https://zed.dev/schema/themes/v0.2.0.json", "name": "YASB Accent",
                     "author": "theme.py", "themes": [{"name": "YASB Accent", "appearance": "dark",
                                                       "style": style}]}, indent=2))
