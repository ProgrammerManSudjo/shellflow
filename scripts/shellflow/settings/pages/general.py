"""The General page."""
import os
from pathlib import Path
from ... import api as th
from ..constants import sound_settings
from ..drawing import avatar
from ..komorebi import reload_komorebi
from ..state import env_set, env_unset
from ..sysinfo import user_name

class GeneralPage:
    # ---- General ----------------------------------------------------------------------------------
    def page_general(self):
        f, c = self.draw_main("General", "sliders"), self.c
        f.heading("Profile", "user")
        top, size = f.y, 112
        shown = {"path": th.env("YASB_PFP")}

        def pic():
            p = shown["path"]
            return avatar(p, size, c["accent"], c["input"], os.path.getmtime(p) if p and os.path.exists(p) else 0)
        av = f.cv.create_image(0, top + 4, image=pic(), anchor="nw")
        x = size + 30
        f.cv.create_text(x, top + 12, text="Name", anchor="w", fill=c["muted"], font=self.f(10))
        name = f.entry(top + 44, f.cw - x, user_name(), x=f.cw, name="name")
        f.cv.create_text(x, top + 84, text="Profile picture", anchor="w", fill=c["muted"], font=self.f(10))
        y = top + 116
        edge = f.button(y, "Clear", lambda: set_pfp(""), x=f.cw, name="pfp_clear") - 10
        edge = f.button(y, "Choose image", lambda: choose(), glyph="camera", x=edge, name="pfp_choose") - 10
        path = f.entry(y, edge - x, shown["path"], x=edge, name="pfp")

        def save_name(_=None):
            v = name.get().strip()
            if v and v != os.environ.get("USERNAME", ""):
                env_set("YASB_USERNAME", v)
            else:
                env_unset("YASB_USERNAME")
            self.say("Saved")

        def set_pfp(p):
            p = p.strip().strip('"')
            if p and not os.path.isfile(p):
                return self.say("That file does not exist")
            (env_set("YASB_PFP", p.replace("\\", "/")) if p else env_unset("YASB_PFP"))
            shown["path"] = p
            path.delete(0, "end")
            path.insert(0, p)
            f.cv.itemconfig(av, image=pic())
            self.say("Saved")

        def choose():
            p = self.ask_file(title="Choose a profile picture", initialdir=str(Path(shown["path"]).parent) if shown["path"] else str(Path.home()),
                                           filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All files", "*.*")])
            if p:
                set_pfp(p)
        for box, fn in ((name, save_name), (path, lambda _=None: set_pfp(path.get()))):
            box.bind("<Return>", fn)
            box.bind("<FocusOut>", fn)
        f.y = top + size + 40
        f.heading("Quick actions", "sliders")
        f.begin_card()
        yc = f.row("Open the config folder", str(th.CONFIG), glyph="folder")
        f.button(yc, "Open", lambda: self.launch(th.CONFIG), glyph="arrow_ur", name="open_config")
        yc = f.row("Write all the app themes", "Discord, Zed, Obsidian, VS Code and the others you switched on", glyph="layers")
        f.button(yc, "Apply now", self.apply_apps, primary=True, name="apply_apps")
        yc = f.row("Reload komorebi", "Runs komorebic reload-configuration", glyph="tiles")
        f.button(yc, "Reload", lambda: (reload_komorebi(), self.say("komorebi reloaded")), glyph="reset", name="reload_kom")
        f.end_card()
        on, vol = sound_settings()
        f.heading("Window", "panel")
        f.begin_card()

        yc = f.row("Attach to the bar", "ShellFlow sits flush against the bar, as wide as the bar (15 px in from each end), square where it touches, "
                   "with its sidebar collapsed to icons (hover for the names). It reopens to apply this", glyph="panel")
        f.toggle(yc, th.env("YASB_ATTACH") == "1", lambda v: (env_set("YASB_ATTACH", "1" if v else "0"), self.relaunch()), name="attach")
        if th.env("YASB_ATTACH") == "1":  # fine tuning, because only you can see how it sits against your bar
            yc = f.row("Inset from the bar's ends", "How far in from each end of the bar the window starts. It reopens to apply this")
            f.slider(yc, int(th.env("YASB_ATTACH_INSET")) if th.env("YASB_ATTACH_INSET").isdigit() else None, 0, 30,
                     lambda v: (env_set("YASB_ATTACH_INSET", str(15 if v is None else v)), self.relaunch()), default=15, name="attach_inset")
            yc = f.row("Move up or down", "Nudges the window against the bar (negative = up). It reopens to apply this")
            f.slider(yc, int(th.env("YASB_ATTACH_DY")) if th.env("YASB_ATTACH_DY").lstrip("-").isdigit() else None, -20, 20,
                     lambda v: (env_set("YASB_ATTACH_DY", str(0 if v is None else v)), self.relaunch()), default=0, name="attach_dy")
        yc = f.row("Motion", "Springy motion for buttons, switches, sections and pages (Material 3 expressive)", glyph="sliders")
        f.toggle(yc, th.env("YASB_MOTION") != "0", lambda v: (env_set("YASB_MOTION", "1" if v else "0"), self.say("Motion " + ("on" if v else "off"))), name="motion")
        f.end_card()
        f.heading("Sounds", "volume")
        f.begin_card()

        def set_sound(on=None, vol=None):
            if on is not None:
                env_set("YASB_SOUNDS", "1" if on else "0")
            if vol is not None:
                env_set("YASB_SOUND_VOLUME", str(vol))
            self.sfx.configure(enabled=on, volume=vol)
            if vol is not None:
                self.sfx.play("click")
            self.say("Saved")

        def preview():
            for ms, name in ((0, "click"), (420, "on"), (900, "off"), (1350, "apply")):
                self.root.after(ms, lambda n=name: self.sfx.play(n))
            self.root.after(1500, lambda: self.say("Sound problem: " + self.sfx.last_error + "  (check the Windows volume mixer)")
                            if self.sfx.last_error else None)
        yc = f.row("Click sounds", "Soft Pixel-style taps, ticks and chimes for the buttons and toggles in this window", glyph="volume")
        f.toggle(yc, on, lambda v: set_sound(on=v), name="sounds_on")
        def set_bar_sounds(v):
            try:
                env_set("YASB_BAR_SOUNDS", "1" if v else "0")
                th.apply_helper_settings()
                self.say("Sounds on the YASB bar " + ("on" if v else "off"))
            except Exception as e:
                th.log("bar sounds")
                self.say(f"Could not change it: {e}")
        yc = f.row("Sounds on the YASB bar", "A tick when you click the bar or one of its menus (the background helper plays it)", glyph="bar")
        f.toggle(yc, th.env("YASB_BAR_SOUNDS") == "1", set_bar_sounds, name="bar_sounds")
        yc = f.row("Sound style", "Wood: soft wooden tocks. Pixel: high glassy blips. Smooth: rounded pops, like an osu! skin", glyph="volume")
        f.segmented(yc, ["Wood", "Pixel", "Smooth"], (th.env("YASB_SOUND_SET") or "wood").capitalize(),
                    lambda v: (env_set("YASB_SOUND_SET", v.lower()), preview()), name="sound_set")
        yc = f.row("Vary the pitch", "Each click is a little higher or lower than the last, in tune with each other, for some variety", glyph="volume")
        f.toggle(yc, th.env("YASB_SOUND_VARY") != "0", lambda v: (env_set("YASB_SOUND_VARY", "1" if v else "0"), self.say("Pitch varies" if v else "Always the same pitch")), name="sound_vary")
        yc = f.row("Volume", "How loud the sounds are")
        f.slider(yc, vol, 0, 100, lambda v: set_sound(vol=10 if v is None else v), unit="%", default=10, name="sound_volume")
        yc = f.row("Preview", "Plays the click, on, off and done sounds")
        f.button(yc, "Play", preview, glyph="volume", name="sound_preview")
        f.end_card()
        f.heading("Sync", "reset")
        f.begin_card()

        def set_sync(v):
            try:
                env_set("YASB_SYNC", "1" if v else "0")
                th.apply_helper_settings()
                self.say("Background sync " + ("on - it starts with Windows" if v else "off"))
            except Exception as e:
                th.log("sync")
                self.say(f"Could not change it: {e}")
        yc = f.row("Keep app themes in sync", "Rewrites Discord, Zed and the rest when the wallpaper changes", glyph="reset")
        f.toggle(yc, th.env("YASB_SYNC") != "0", set_sync, name="sync")
        yc = f.row("Background helper", th.helper_status(), glyph="bar")
        status = f.last_desc

        def restart():
            try:
                th.restart_helper()
                self.root.after(1500, lambda: self.cv.itemconfig(status, text=th.helper_status()) if self.cv.winfo_exists() else None)
                self.say("Helper restarted")
            except Exception as e:
                th.log("helper")
                self.say(f"Could not restart it: {e}")
        f.button(yc, "Restart", restart, glyph="reset", name="helper_restart")
        f.end_card()
        return f

    def ensure_sync(self):
        """First run: switch the background helper on (app sync and the sounds on the YASB bar), and make sure it is running."""
        try:
            for key, default in (("YASB_SYNC", "1"), ("YASB_BAR_SOUNDS", "0")):  # the sounds on the bar are off until you switch them on
                if th.env(key) == "":
                    env_set(key, default)
            th.apply_helper_settings()
        except Exception:
            th.log("sync")
