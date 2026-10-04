"""The About page."""
import platform
import sys
from ... import api as th
from ..constants import APP_NAME
from ..drawing import logo_img
from ..komorebi import komorebi_dir, list_monitors
from ..sysinfo import komorebi_version, yasb_version

class AboutMixin:
    # ---- About ------------------------------------------------------------------------------------
    def page_about(self):
        f, c = self.draw_main("About", "info"), self.c
        f.cv.logo = logo_img(96, c["accent"], c["ink"])
        f.cv.create_image(0, 14, image=f.cv.logo, anchor="nw")
        f.cv.create_text(124, 36, text=APP_NAME, anchor="w", fill=c["accent2"], font=self.f(22, "bold"))
        f.cv.create_text(124, 70, text="A settings window for YASB, komorebi and the apps that follow your accent", anchor="w", fill=c["muted"], font=self.f(10))
        f.cv.create_text(124, 94, text="YASB " + yasb_version(), anchor="w", fill=c["text"], font=self.f(11, "bold"))
        f.y = 132
        x = f.button(f.y + 18, "Open config folder", lambda: self.launch(th.CONFIG), glyph="folder", x=f.cw, name="about_open") - 10
        info = lambda: "\n".join(f"{k}: {v}" for k, v in self.system_info())
        f.button(f.y + 18, "Copy info", lambda: (self.root.clipboard_clear(), self.root.clipboard_append(info()), self.say("Copied")), glyph="copy", x=x, name="about_copy")
        f.y += 56
        f.heading("System information", "monitor")
        for k, v in self.system_info():
            f.kv(k, v)
        return f

    def system_info(self):
        if self._monitors is None:
            self._monitors = list_monitors()
        return [("Windows", platform.platform()), ("Python", sys.version.split()[0]), ("YASB", yasb_version()),
                ("komorebi", komorebi_version()), ("Monitors", ", ".join(self._monitors) or "not found (yasbc not on PATH)"),
                ("Accent", th.hx(th.accent_shades()["accent"])), ("Config folder", str(th.CONFIG)),
                ("komorebi folder", str(komorebi_dir()))]
