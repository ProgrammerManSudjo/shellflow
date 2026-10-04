"""The Templates page."""
import threading
import time
from pathlib import Path
from ... import api as th
from ..state import env_set, env_unset, wh_task_cached

class TemplatesMixin:
    # ========================================================================================
    #  9. THE PAGES
    # ========================================================================================
    APP_ICONS = {"discord": "message", "zed": "code", "obsidian": "file_text", "vscode": "code", "nvim": "terminal",
                 "wt": "terminal", "firefox": "globe", "zen": "globe", "yazi": "folder", "obs": "video", "tacky": "box", "windhawk": "layers", "helium": "globe", "filepilot": "folder"}

    # ---- Templates ----------------------------------------------------------------------------------
    def page_templates(self):
        f, c = self.draw_main("Templates", "layers"), self.c
        f.note("Choose which apps get a theme from your colour scheme, and the folder each one is written to. "
               "The box shows where it goes now; change it to use another folder (several folders: separate them with ;).")
        f.heading("Write now", "layers")
        f.begin_card()
        yc = f.row("Write all the themes", "Every app below that is switched on")
        f.button(yc, "Apply now", self.apply_apps, primary=True, name="apply_now")
        f.end_card()
        f.heading("Apps", "grid")
        on_now = set(th.enabled_apps())
        keys = [r[0] for r in th.APP_TABLE]
        default_on = {k for k in keys if k not in th.OPT_IN_APPS}

        def flip(key, on):
            on_now.add(key) if on else on_now.discard(key)
            env_unset("YASB_APPS") if on_now == default_on else env_set("YASB_APPS", ",".join(k for k in keys if k in on_now) or "none")
            self.say("Saved")
            if key == "windhawk":
                self.defer_refresh()
        for key, name, var, many, desc, _ in th.APP_TABLE:
            if key == "windhawk":
                self.windhawk_card(f, key, name, desc, key in on_now, flip)
                continue
            pairs, _sub = th.defaults(key)
            found = [folder for marker, folder in pairs if marker.is_dir()] or [folder for _, folder in pairs]
            default = ";".join(str(folder).replace("\\", "/") for folder in found) or "(none found yet - use the folder button)"
            custom = th.env(var)
            f.begin_card()
            yc = f.row(name, desc, glyph=self.APP_ICONS[key], h=212 if key == "helium" else 162 if key == "filepilot" else 112, top=True)
            f.toggle(yc, key in on_now, lambda v, k=key: flip(k, v), name=f"app:{key}")
            y2 = yc + 56
            box = {}

            def commit(_=None, var=var, default=default, box=box):
                v = box["e"].get().strip()
                if not v or v == default:
                    env_unset(var)
                    box["e"].config(fg=c["muted"])
                else:
                    env_set(var, v)
                    box["e"].config(fg=c["text"])
                self.say("Saved")

            def reset(var=var, default=default, box=box):
                env_unset(var)
                box["e"].delete(0, "end")
                box["e"].insert(0, default)
                box["e"].config(fg=c["muted"])
                self.say("Back to the default folder")

            def pick(var=var, many=many, default=default, box=box, name=name, commit=commit):  # commit=commit: bind this row's own
                now = box["e"].get().strip().split(";")[-1]
                folder = self.ask_dir(title=f"{name} folder", initialdir=now if now and Path(now).is_dir() else str(Path.home()))
                if folder:
                    old = th.env(var)
                    new = (old + ";" + folder) if (many and old and folder not in old.split(";")) else folder
                    box["e"].delete(0, "end")
                    box["e"].insert(0, new)
                    commit()
            x = f.ibutton(y2, "reset", reset, x=f.r, name=f"reset:{key}")
            x = f.ibutton(y2, "folder", pick, x=x, name=f"pick:{key}")
            box["e"] = f.entry(y2, x - (f.l + 38), custom or default, x=x, name=f"path:{key}", colour=c["text"] if custom else c["muted"])
            box["e"].bind("<Return>", commit)
            box["e"].bind("<FocusOut>", commit)
            if key == "filepilot":  # it rewrites its config when it closes: the colours are written while it is closed
                f.cv.create_text(f.l, y2 + 50, text="File Pilot overwrites its colours when it closes, so they are written while it is closed", anchor="w",
                                 fill=c["muted"], font=self.f(9))
                f.button(y2 + 50, "Sure?" if self.armed("filepilot") else "Restart File Pilot", self.do_restart_filepilot, glyph="reset", x=f.r,
                         primary=self.armed("filepilot"), name="filepilot_restart")
            if key == "helium":  # a browser reads its theme when it starts: a button that restarts it
                f.cv.create_text(f.l, y2 + 50, text="Helium reads a changed theme when it starts (its reload arrow is not reliable)", anchor="w",
                                 fill=c["muted"], font=self.f(9))
                x = f.button(y2 + 50, "Sure?" if self.armed("helium") else "Restart Helium", self.do_restart_helium, glyph="reset", x=f.r,
                             primary=self.armed("helium"), name="helium_restart")
                f.cv.create_text(f.l, y2 + 100, text="Restart it by itself when the theme changes (closes it, reopens it with your tabs)", anchor="w",
                                 fill=c["muted"], font=self.f(9))
                f.toggle(y2 + 100, th.env("YASB_HELIUM_AUTORESTART") == "1", lambda v: (env_set("YASB_HELIUM_AUTORESTART", "1" if v else "0"),
                         self.say("Helium restarts by itself after a theme change" if v else "Helium is left alone")), x=f.r, name="helium_auto")
            f.end_card()
            f.y -= 4
        return f

    def do_restart_filepilot(self):
        if not self.confirm("filepilot", "Click again to close File Pilot and open it again with the new colours"):
            return
        self.say("Restarting File Pilot...")
        box = {}

        def work():
            box["text"] = th.restart_filepilot()
        threading.Thread(target=work, daemon=True).start()

        def check():
            if "text" not in box:
                return self.root.after(400, check)
            self.say(box["text"])
            self.defer_refresh()
        self.root.after(400, check)

    def do_restart_helium(self):
        if not self.confirm("helium", "Click again to close Helium and open it again (your tabs come back)"):
            return
        self.say("Restarting Helium...")
        box = {}

        def work():
            box["text"] = th.restart_helium()
        threading.Thread(target=work, daemon=True).start()

        def check():
            if "text" not in box:
                return self.root.after(400, check)
            self.say(box["text"])
            self.defer_refresh()
        self.root.after(400, check)

    def windhawk_card(self, f, key, name, desc, on, flip):
        """Windhawk is not a folder: its card shows whether the elevated task is set up, and offers Set up and Restore."""
        task = wh_task_cached() if on else False
        f.begin_card()
        yc = f.row(name, desc, glyph="layers", h=162 if on else 112, top=True)
        f.toggle(yc, on, lambda v: flip(key, v), name=f"app:{key}")
        y2 = yc + 56
        if not on:
            f.cv.create_text(f.l, y2, text="Off. Switch it on to colour Windhawk's styler mods with your scheme.", anchor="w", fill=self.c["muted"], font=self.f(9))
        else:
            state = th.wh_load_state()
            n = len([k for k in state if not k.startswith("_")])
            left = sum(len(v) for v in state.get("_skipped", {}).values())
            status = ("Ready: changes are written silently." if task else "Needs one UAC prompt, once, to be allowed to write Windhawk's settings.")
            f.cv.create_text(f.l, y2, text=status + (f"   Recoloured mods: {n}." if n else "") + (f"   {left} settings you changed in Windhawk are left alone." if left else ""), anchor="w", fill=self.c["muted"], font=self.f(9))

            def setup():
                self.say("Waiting for the Windows prompt...")
                self.quiet_until = time.time() + 20
                self.root.after(100, lambda: (th.wh_setup_task(), wh_task_cached(True), self.say("Windhawk is set up" if wh_task_cached() else "Not set up (prompt cancelled?)"), self.defer_refresh()))

            def restore():
                try:
                    self.say(f"Put back {th.wh_restore()} settings")
                except Exception as e:
                    self.say(str(e)[:90])
            x = f.button(y2, "Put back", restore, glyph="reset", x=f.r, name="wh_restore")
            if not task:
                f.button(y2, "Set up", setup, glyph="check", primary=True, x=x - 8, name="wh_setup")
            y3 = y2 + 50
            f.cv.create_text(f.l, y3, text="Colours  -  Capsules: the capsule colour, active = a running app on the bar", anchor="w", fill=self.c["muted"], font=self.f(9))
            f.segmented(y3, ["Capsules", "Accent shades"], "Accent shades" if th.env("YASB_WINDHAWK_MATCH") == "accent" else "Capsules",
                        lambda v: (env_set("YASB_WINDHAWK_MATCH", "accent" if v == "Accent shades" else "capsules"),
                                   self.say("Applies the next time the themes are written (Apply now)")), x=f.r, name="wh_match")
        f.end_card()
        f.y -= 4
