"""The Display page."""
from ..config_yaml import get_screens, set_screens, yaml_get
from ..komorebi import komorebi_dir, list_monitors

class DisplayMixin:
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
