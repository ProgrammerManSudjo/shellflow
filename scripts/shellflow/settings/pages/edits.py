"""The Edits page."""
from ..constants import parse_colour
from ..drawing import rounded
from ..styles import BAR_FONT_SELECTORS, COLOUR_VARS, MENU_FONT_SELECTORS, css_font, current_colours

class EditsMixin:
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
