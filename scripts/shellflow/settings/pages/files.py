"""The Files page."""
from ..files import config_files
from ..icons import file_icon

class FilesMixin:
    # ---- Files ------------------------------------------------------------------------------------
    def page_files(self):
        f = self.draw_main("Files", "folder")
        f.note("Every config file of YASB, komorebi and whkd. Click a file, or its Edit button, to open it in your editor.")
        groups = config_files()
        for group, glyph, files in (("YASB", "folder", "YASB"), ("Scripts", "file_code", "Scripts"), ("komorebi", "tiles", "komorebi"), ("whkd", "terminal", "whkd")):
            paths = groups[files]
            f.heading(f"{group}   -   {len(paths)} files", glyph)
            if not paths:
                f.note("Nothing found here.")
                continue
            f.begin_card()
            for p in paths[:80]:
                try:
                    size = f"{p.stat().st_size / 1024:.1f} KB"
                except OSError:
                    size = ""
                yc = f.row(p.name, f"{size}    {p.parent}", glyph=file_icon(p), click=lambda p=p: (self.launch(p), self.say(f"Opening {p.name}")))
                f.button(yc, "Edit", lambda p=p: (self.launch(p), self.say(f"Opening {p.name}")), glyph="pen", name=f"edit:{p.name}")
            f.end_card()
        return f
