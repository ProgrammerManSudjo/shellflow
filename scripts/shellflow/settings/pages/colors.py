"""The Colors page."""
from PIL import ImageTk
from ... import api as th
from ..constants import PAGES
from ..drawing import rounded

class ColorsMixin:
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
