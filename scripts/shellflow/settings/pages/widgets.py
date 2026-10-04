"""The Widgets page."""
from ..catalog import CATALOG, CATALOG_BY_TYPE
from ..config_yaml import add_catalog_widget, define_catalog_widget, delete_widget_def, get_zones, menu_gap, move_to_zone, move_widget, read_widgets, remove_widget, set_menu_gap, toggle_widget
from ..icons import widget_icon
from ..styles import current_colours

class WidgetsMixin:
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
