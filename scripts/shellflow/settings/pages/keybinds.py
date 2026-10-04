"""The Keybinds page."""
import tkinter as tk
from ..constants import PAGES
from ..drawing import pill_button, rounded
from ..icons import ICONS
from ..keybinds import MODIFIERS, add_keybind, delete_keybind, format_keys, keybind_title, parse_whkdrc, replace_keybind, split_keys, tk_key, whkdrc_path

class KeybindsMixin:
    # ---- Keybinds (whkdrc) ------------------------------------------------------------------------
    KEY_ROWS = (
        [("esc", "escape", 1)] + [(f"F{i}", f"f{i}", 1) for i in range(1, 13)],
        [("`", "oem_3", 1)] + [(str(i % 10), str(i % 10), 1) for i in range(1, 11)] + [("-", "oem_minus", 1), ("=", "oem_plus", 1), ("back", "backspace", 2)],
        [("tab", "tab", 1.5)] + [(k, k, 1) for k in "qwertyuiop"] + [("[", "oem_4", 1), ("]", "oem_6", 1), ("\\", "oem_5", 1.5)],
        [("", None, 1.75)] + [(k, k, 1) for k in "asdfghjkl"] + [(";", "oem_1", 1), ("'", "oem_7", 1), ("enter", "return", 2.25)],
        [("shift", "shift", 2.25)] + [(k, k, 1) for k in "zxcvbnm"] + [(",", "oem_comma", 1), (".", "oem_period", 1), ("/", "oem_2", 1), ("shift", "shift", 2.75)],
        [("ctrl", "ctrl", 1.25), ("win", "win", 1.25), ("alt", "alt", 1.25), ("space", "space", 4.5), ("alt", "alt", 1), ("ctrl", "ctrl", 1),
         ("<", "left", 1), ("^", "up", 1), ("v", "down", 1), (">", "right", 1)],
    )

    def whkd_text(self):
        """The whkdrc as it is now (with your unapplied changes), or None if there is none."""
        if self.kb_text is not None:
            return self.kb_text
        try:
            return whkdrc_path().read_text(encoding="utf-8")
        except OSError:
            return None

    def kb_commit(self, text):
        self.kb_text = text
        self.stage("whkd")

    def kb_event(self, e):
        """Keys you press on the keyboard light up on the Keybinds page (not while you type in one of its boxes)."""
        if self.closing or self.view_results or PAGES[self.current][0] != "Keybinds":
            return
        try:
            if isinstance(self.root.focus_get(), tk.Entry):
                return
        except (KeyError, tk.TclError):
            return
        name = tk_key(e.keysym)
        if not name:
            return
        down = e.type == tk.EventType.KeyPress
        if down == (name in self.kb_down):
            return  # a key you hold repeats itself: nothing changed, so nothing is redrawn
        (self.kb_down.add if down else self.kb_down.discard)(name)
        self.kb_soon()

    def kb_soon(self):
        """Redraw the page a moment after the last key event."""
        if self.kb_job:
            self.root.after_cancel(self.kb_job)

        def redraw():
            self.kb_job = None
            if frozenset(self.kb_sel | self.kb_down) != getattr(self, "kb_drawn", None):  # only when the held keys are not what is shown
                self.go(self.current, keep=True)
        self.kb_job = self.root.after(60, redraw)

    def draw_keyboard(self, f, used, pressed, combo):
        """The keyboard: keys that are in a keybind are lit, the ones you hold are filled, and the ones that would complete a
        keybind with the keys you hold have an outline. Click a key to hold it. Returns {key name: its image item}."""
        c, cv, gap = self.c, f.cv, 5
        unit = (f.cw - gap * 14) / 15
        items = {}
        y = f.y
        for r, row in enumerate(self.KEY_ROWS):
            h = 30 if r == 0 else 42
            x = 0
            for label, name, units in row:
                w = units * unit + (units - 1) * gap if units > 1 else unit
                if name:
                    held, hint, lit = name in pressed, name in combo, name in used
                    fill = c["accent"] if held else c["hover"] if lit else c["input"]
                    outline = c["accent2"] if hint and not held else c["line"] if not held else None
                    ink = c["ink"] if held else c["accent2"] if hint else c["text"] if lit else c["muted"]
                    tag = f"kbd{name}"
                    img = cv.create_image(x, y, image=rounded(round(w), h, 9, fill, outline, 2 if hint else 1), anchor="nw", tags=tag)
                    cv.create_text(x + w / 2, y + h / 2, text=label, fill=ink, font=self.f(9 if len(label) > 2 else 11, "bold" if lit or held else "normal"), tags=tag)
                    cv.tag_bind(tag, "<Button-1>", lambda e, n=name: (self.sfx.play("tap"), self.kb_sel.symmetric_difference_update({n}), self.kb_soon()))
                    cv.tag_bind(tag, "<Enter>", lambda e: cv.config(cursor="hand2"))
                    cv.tag_bind(tag, "<Leave>", lambda e: cv.config(cursor=""))
                    items.setdefault(name, img)
                x += w + gap
            y += h + gap
        f.y = y + 10
        return items

    def page_keybinds(self):
        f, c = self.draw_main("Keybinds", "keyboard"), self.c
        text = self.whkd_text()
        if text is None:
            f.note(f"There is no whkdrc yet (it would be {whkdrc_path()}).")
            f.begin_card()
            yc = f.row("Create a whkdrc", "An empty one that uses PowerShell, ready for your keybinds", glyph="keyboard")
            f.button(yc, "Create", lambda: (self.kb_commit(".shell powershell\n\n"), self.defer_refresh()), glyph="plus", primary=True, name="kb_create")
            f.end_card()
            return f
        rows = parse_whkdrc(text)
        used = {k for r in rows for k in r["keys"]}
        pressed = self.kb_sel | self.kb_down
        self.kb_drawn = frozenset(pressed)
        shown = [r for r in rows if pressed <= set(r["keys"])]
        combo = {k for r in shown for k in r["keys"]} - pressed if pressed else set()
        f.note("Press keys on your keyboard, or click them below, to see every keybind that uses them. Keys that are lit are in a keybind; "
               "an outlined key would complete one with the keys you are holding. Changes wait for Apply; whkd restarts then.")
        f.heading("Keyboard", "keyboard")
        f.hits["kb_keys_items"] = self.draw_keyboard(f, used, pressed, combo)
        f.begin_card()
        status = ("Holding:  " + format_keys(sorted(pressed))) if pressed else "Nothing held. Press keys, or click them above."
        yc = f.row("Keys", status, glyph="keyboard")
        f.button(yc, "Clear", lambda: (self.kb_sel.clear(), self.kb_down.clear(), self.kb_soon()), glyph="x", name="kb_clear")
        f.end_card()
        f.heading(f"Keybinds   -   {len(shown)} of {len(rows)}", "list" if "list" in ICONS else "file_text")
        f.begin_card()
        yc = f.row("Add a keybind", "A new line at the end of your whkdrc", glyph="plus")
        f.button(yc, "Add", lambda: (setattr(self, "kb_edit", {"start": None, "keys": format_keys(sorted(pressed)), "cmd": ""}), self.defer_refresh()),
                 glyph="plus", primary=True, name="kb_add")
        edit = self.kb_edit
        if edit is not None:
            yc = f.row("Keys", "For example: alt + shift + h", glyph="keyboard")
            x = f.button(yc, "From keyboard", lambda: self.kb_fill(f), glyph="keyboard", name="kb_from")
            f.entry(yc, 230, edit["keys"], x=x - 10, name="kb_keys")
            yc = f.row("Command", "What runs, for example: komorebic focus left", glyph="terminal")
            f.entry(yc, 460, edit["cmd"], name="kb_cmd")
            yc = f.row("Editing" if edit["start"] is not None else "New keybind", "Save puts it in the list. It reaches whkdrc when you press Apply.", glyph="pen")
            x = f.button(yc, "Save", lambda: self.kb_save(f), glyph="check", primary=True, name="kb_save")
            f.button(yc, "Cancel", lambda: (setattr(self, "kb_edit", None), self.defer_refresh()), glyph="x", x=x - 8, name="kb_cancel")
        f.cv.photos = getattr(f.cv, "photos", [])
        for r in shown:
            desc = r["cmd"] + (f"   -   {r['group']}" if r["group"] else "")
            yc = f.row(keybind_title(r), desc, glyph="keyboard")
            x = f.ibutton(yc, "trash", lambda r=r: self.kb_delete(r), name=f"kb_del:{r['start']}")
            x = f.ibutton(yc, "pen", lambda r=r: (setattr(self, "kb_edit", {"start": r["start"], "keys": r["keys_text"], "cmd": r["cmd"]}), self.defer_refresh()),
                          x=x, name=f"kb_edit:{r['start']}")
            pw = int(self.f(10).measure(r["keys_text"]) + 40)  # the keys, as a pill
            pill = pill_button(r["keys_text"], pw, 30, c["input"], c["accent2"], c["line"], None, 12, None)
            f.cv.photos.append(pill)
            f.cv.create_image(x - 8 - pw, yc, image=pill, anchor="w")
            f.fit(x - 8 - pw)
        if not shown:
            f.row("No keybind uses these keys" if pressed else "No keybinds yet", "Add one above." if not pressed else "Press fewer keys, or Clear.", glyph="keyboard")
        f.end_card()
        return f

    def kb_fill(self, f):
        box = f.hits.get("kb_keys")
        if box is not None:
            box.delete(0, "end")
            box.insert(0, format_keys(sorted(self.kb_sel | self.kb_down)))

    def kb_save(self, f):
        edit, text = self.kb_edit, self.whkd_text()
        keys_text, cmd = f.hits["kb_keys"].get().strip(), f.hits["kb_cmd"].get().strip()
        keys = split_keys(keys_text)
        if not keys or all(k in MODIFIERS for k in keys):
            return self.say("A keybind needs a key besides alt, ctrl, shift and win")
        if not cmd:
            return self.say("Type the command that should run")
        rows = parse_whkdrc(text)
        clash = next((r for r in rows if set(r["keys"]) == set(keys) and r["start"] != edit["start"]), None)
        if clash:
            return self.say(f"{format_keys(keys)} is already used for: {clash['cmd'][:50]}")
        if edit["start"] is None:
            new = add_keybind(text, keys_text, cmd)
        else:
            new = replace_keybind(text, next(r for r in rows if r["start"] == edit["start"]), keys_text, cmd)
        self.kb_edit = None
        self.kb_commit(new)
        self.say("Keybind saved - press Apply")
        self.defer_refresh()

    def kb_delete(self, bind):
        self.kb_commit(delete_keybind(self.whkd_text(), bind))
        self.say(f"{bind['keys_text']} removed - press Apply")
        self.defer_refresh()
