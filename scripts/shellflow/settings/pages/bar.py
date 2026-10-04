"""The Bar page."""
from ... import api as th
from ..catalog import CATALOG_BY_TYPE
from ..config_yaml import find_key, menu_gap, middle_open_widget, read_widgets, set_menu_gap, set_middle_open, yaml_get
from ..constants import parse_colour

class BarMixin:
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
