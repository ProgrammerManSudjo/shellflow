"""The Wallpaper page."""
import queue
import sys
import threading
import tkinter as tk
from ... import api as th
from ..drawing import rounded, wall_tile
from ..wallpapers import list_wallpapers, make_thumb, same_file, wallpaper_dirs

class WallpaperMixin:
    # ---- Wallpaper --------------------------------------------------------------------------------
    def page_wallpaper(self):
        f, c = self.draw_main("Wallpaper", "image"), self.c
        dirs = wallpaper_dirs(self.cfg_text())
        f.note("Pick a wallpaper from the folder the YASB wallpapers widget uses (its image_path in config.yaml, or YASB_WALLPAPERS in .env), "
               "then press Apply (bottom right). The colour scheme and the apps follow the new wallpaper.")
        f.heading("Folder", "folder")
        f.begin_card()
        yc = f.row("Wallpapers folder", "From the widget" if dirs else "Not found")
        edge = f.button(yc, "Open", lambda: dirs and self.launch(dirs[0]), glyph="folder", name="wall_open") - 10
        box = f.entry(yc, max(130, min(edge - f.l - 330, edge - f.l - 190)), "; ".join(str(d) for d in dirs), x=edge, name="wall_folder", colour=c["muted"])
        box.config(state="readonly", readonlybackground=c["input"])
        f.end_card()
        files = list_wallpapers(dirs)
        f.heading(f"Wallpapers   -   {len(files)}", "image")
        if not files:
            f.note("No pictures (png, jpg, webp, bmp) in that folder.")
            return f
        cols, gap, cap = 3, 14, 30
        tw = (f.cw - gap * (cols - 1)) // cols
        th_ = tw * 9 // 16
        current = th.wallpaper_path() if sys.platform == "win32" else ""
        base, items = {}, {}
        top = f.y
        photos = f.cv.photos = {}

        def draw(i):
            p = files[i]
            if i in base:
                photos[i] = wall_tile(base[i], same_file(self.wall_pick, p), same_file(current, p), c["accent"], c["ink"], c["panel"])
                f.cv.itemconfig(items[i], image=photos[i])

        def pick(i):
            p = files[i]
            self.wall_pick = None if same_file(p, current) else p
            self.dirty.discard("wall") if self.wall_pick is None else self.dirty.add("wall")
            self.warned = False
            self.draw_footer()
            self.say(f"{p.stem} selected  -  press Apply" if self.wall_pick else f"{p.stem} is the current wallpaper")
            for j in base:
                draw(j)
        for i, p in enumerate(files):
            x, y = (i % cols) * (tw + gap), top + (i // cols) * (th_ + cap + 10)
            ph = rounded(tw, th_, 16, c["input"])
            it = f.cv.create_image(x, y, image=ph, anchor="nw")
            photos[("ph", i)] = ph
            items[i] = it
            name = p.stem
            while len(name) > 4 and self.f(9).measure(name) > tw - 12:
                name = name[:-1]
            f.cv.create_text(x + 6, y + th_ + 14, text=name + ("..." if name != p.stem else ""), anchor="w", fill=c["muted"], font=self.f(9))
            f.cv.tag_bind(it, "<Button-1>", lambda e, i=i: (self.sfx.play("tap"), pick(i)))
            f.cv.tag_bind(it, "<Enter>", lambda e: f.cv.config(cursor="hand2"))
            f.cv.tag_bind(it, "<Leave>", lambda e: f.cv.config(cursor=""))
            f.hits[f"wall:{p.name}"] = it
        f.y = top + ((len(files) + cols - 1) // cols) * (th_ + cap + 10)
        f.hits["wall_files"] = files
        # thumbnails are made in the background and appear one by one
        results = queue.Queue()
        canvas = f.cv

        def work():
            for i, p in enumerate(files):
                try:
                    results.put((i, make_thumb(p, (tw, th_))))
                except Exception:
                    results.put((i, None))
        threading.Thread(target=work, daemon=True).start()

        def drain():
            try:
                if not canvas.winfo_exists() or getattr(self, "cv", None) is not canvas:
                    return
                for _ in range(6):
                    i, im = results.get_nowait()
                    if im is not None:
                        base[i] = im
                        draw(i)
                canvas.after(40, drain)
            except queue.Empty:
                canvas.after(60, drain)
            except tk.TclError:
                pass
        f.hits["wall_draw"] = draw
        f.hits["wall_base"] = base
        drain()
        return f
