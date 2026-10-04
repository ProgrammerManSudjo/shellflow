"""The window itself: frame, sidebar, header, scrolling, saving, following the colour scheme."""
import os
import subprocess
import threading
import time
import tkinter as tk
from functools import lru_cache
from tkinter import filedialog, font as tkfont
from PIL import Image, ImageDraw, ImageTk
from .. import api as th
from .config_yaml import MIN_ATTACHED, bar_box, bar_edge, bar_names, repair_config, save_config, yaml_set
from .constants import APP_NAME, BORDER, CONFIG_YAML, CREATE_NO_WINDOW, EDGE, FOOT, GAP, H, HEAD, HOVER_SCALE, MARGIN, NATIVE, PADX, PAGES, PRESS_SCALE, RING_R, SIDE_COMPACT, SIDE_FULL, Sfx, W, parse_colour, sound_settings
from .drawing import avatar, logo_img, pill_button, rounded, slider_img, switch
from .files import open_file
from .flow import Flow
from .icons import icon, icon_pil
from .keybinds import restart_whkd, whkdrc_path
from .komorebi import load_komorebi, reload_komorebi, save_komorebi
from .motion import animate, fade, soft, spring
from .state import load_edits, load_ui_state, say
from .styles import current_colours, save_edits, style_block_is_current
from .wallpapers import set_wallpaper

def short_failure(why):
    """A failure from an app theme, short enough for the status line (the administrator-rights one says what to press)."""
    return "needs administrator rights once: Templates > Windhawk > Set up" if "administrator rights" in why else why[:80]


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


class WindowBase:
    """The window: frame, sidebar, header, scrolling, saving, following the colour scheme. The pages are mixins."""

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
        edge_ = self.attach_state()[0]
        self.pt = BORDER + GAP if edge_ == "top" else EDGE       # the space above the panels (small where the window touches the bar)
        self.pb = BORDER + GAP if edge_ == "bottom" else EDGE    # and below them
        root.title(APP_NAME)
        root.geometry(f"{self.W}x{H}")
        root.resizable(False, False)
        root.configure(bg=self.c["outer"])
        root.overrideredirect(not NATIVE)  # no Windows title bar: a floating window that komorebi does not tile
        self.inner = tk.Canvas(root, bg=self.c["outer"], bd=0, highlightthickness=0)
        self.inner.place(x=0, y=0, width=self.W, height=H)
        self.draw_ring()
        self.PH = H - self.pt - self.pb
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
        root.bind("<Escape>", lambda e: self.close() if self.attached and not self.search_open and not self.typing() else None, add="+")
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
            subprocess.Popen([str(th.pythonw()), str(th.LAUNCHER), "settings"], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
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
            self.W - 2 * MARGIN, bottom - top, RING_R, self.c["win"], None if edge else self.c["border"], 0 if edge else BORDER, corners))
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
        if self.attached:
            self.draw_footer()
            self.root.after(3600, self.draw_footer)
            return
        if self.note_id is not None:
            self.main.itemconfig(self.note_id, text=text)

    def draw_footer(self):
        """The bar at the bottom of the page: what is waiting, then Reset and Apply."""
        c, cv = self.c, self.main
        cv.delete("footer")
        y = self.PH - FOOT / 2 - 4
        waiting = [self.LABELS[k] for k in ("scheme", "wall", "whkd", "cfg", "style", "colours", "kom") if k in self.dirty]
        cv.create_line(PADX, y - FOOT / 2 + 2, self.mw - PADX, y - FOOT / 2 + 2, fill=c["line"], tags="footer")
        said = self.attached and getattr(self, "note_text", "") and time.time() - getattr(self, "note_time", 0) < 3.5
        cv.create_text(PADX, y, text=self.note_text if said else (("Not applied yet: " + ", ".join(waiting)) if waiting else "Everything is applied"),
                       anchor="w", fill=c["text"] if said else (c["accent2"] if waiting else c["muted"]),
                       font=self.f(10, "bold" if waiting and not said else "normal"), tags="footer", width=max(120, self.mw - 2 * PADX - 240))
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
        self.side.place(x=EDGE, y=self.pt, width=self.sw, height=self.PH)
        self.main.place(x=EDGE + self.sw + GAP, y=self.pt, width=self.mw, height=self.PH)

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
        if self.attached:
            self.note_id = self.close_item = None
            top = 64 if self.search_open else 14
        else:
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
                th.start_log("seed read")
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
            for fn in (rounded, switch, pill_button, slider_img, icon, logo_img, avatar, WindowBase.close_img):
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
                th.start_log("window was not visible/on screen: showing it again")
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
