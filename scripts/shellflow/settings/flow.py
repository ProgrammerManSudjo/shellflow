"""The content of a page, drawn top to bottom, and the controls that sit in it."""
import tkinter as tk
from .drawing import pill_button, rounded, slider_img, switch_at
from .icons import icon
from .motion import animate, soft, spring
from .state import COLLAPSE_BY_DEFAULT, save_ui_state, section_name

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
        font, room = self.app.f(9), self.r - self.l
        lines = 0
        for para in text.split("\n"):
            cur, n = "", 1
            for word in para.split(" "):
                trial = (cur + " " + word).strip()
                if font.measure(trial) <= room or not cur:
                    cur = trial
                else:
                    n, cur = n + 1, word
            lines += n
        t = self.cv.create_text(self.l, self.y + 4, text=text, anchor="nw", fill=colour or self.c["muted"], font=font, width=room)
        self.y += 24 + font.metrics("linespace") * lines
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
