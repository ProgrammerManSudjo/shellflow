"""The Search page."""
import platform
import sys
import time
import tkinter as tk
from .. import api as th
from .backups import BACKUP_DIR, backup_title, list_backups, log_files, old_copies
from .catalog import CATALOG, CATALOG_BY_KEY, CATALOG_BY_TYPE
from .config_yaml import read_widgets
from .constants import PADX, PAGES
from .drawing import rounded
from .files import config_files
from .icons import icon
from .keybinds import keybind_title, parse_whkdrc
from .styles import COLOUR_VARS
from .sysinfo import komorebi_version, yasb_version

class SearchMixin:
    def toggle_search(self):
        """Attached window: show or hide the search box in the header (typing searches every setting, like the sidebar's box)."""
        self.search_open = not self.search_open
        if not self.search_open:
            return self.clear_search()
        self.go(self.current, keep=True)

    def draw_search_pop(self):
        """The search box of an attached window, in the header next to the close button."""
        if not self.attached or not self.search_open:
            return
        c, mw = self.c, self.mw
        w = mw - 2 * PADX
        if self.search_pop is None:
            e = self.search_pop = tk.Entry(self.main, bd=0, relief="flat", bg=c["input"], fg=c["text"], insertbackground=c["text"], font=self.f(10), highlightthickness=0)
            e.bind("<KeyRelease>", lambda ev: self.set_search(e.get()))
            e.bind("<Return>", lambda ev: self.open_first())
            e.bind("<Escape>", lambda ev: (self.toggle_search(), "break")[1])
            e.bind("<Button-1>", lambda ev: e.focus_force())
            if self.search:
                e.insert(0, self.search)
        self.main.create_image(PADX, 34, image=rounded(w, 38, 19, c["input"], c["accent_dark"], 2), anchor="w")
        self.main.create_window(PADX + 18, 34, window=self.search_pop, width=w - 36, height=24, anchor="w")
        self.search_pop.focus_set()
        self.search_pop.icursor("end")

    # search: the settings on every page, not only the page names -------------------------------
    def search_index(self):
        """Every searchable setting as (page, card, title, description, extra words). Built once, kept for two seconds (or until something
        is staged): typing in the search box asks for it on every key."""
        cached = getattr(self, "_index_cache", None)
        if cached and time.time() - cached[0] < 2.0:
            return cached[1]
        index = self.build_search_index()
        self._index_cache = (time.time(), index)
        return index

    def build_search_index(self):
        I = []
        add = lambda page, card, title, desc="", kw="": I.append((page, card, title, desc, kw))
        for name, _, words in PAGES:  # a page matches by its name only; its settings are listed under their own cards
            add(name, "Page", name, "Open the " + name + " page")
        add("General", "Profile", "Name", "Your name", "username")
        add("General", "Profile", "Profile picture", "A round picture of you", "avatar photo pfp image choose clear")
        add("General", "Quick actions", "Open the config folder", "Your YASB folder", "explorer")
        add("General", "Quick actions", "Write all the app themes", "Discord, Zed, Obsidian, VS Code and the others", "apply templates")
        add("General", "Quick actions", "Reload komorebi", "Runs komorebic reload-configuration", "restart tiling")
        add("General", "Window", "Attach to the bar", "Open ShellFlow flush against the bar, as wide as the bar, with square corners where it touches and a collapsed sidebar", "attached menu dock top bottom position width tooltip")
        if th.env("YASB_ATTACH") == "1":
            add("General", "Window", "Inset from the bar's ends", "How far in from each end of the bar the attached window starts", "attach margin edge gap")
            add("General", "Window", "Move up or down", "Nudges the attached window against the bar", "attach offset vertical position")
        add("General", "Window", "Motion", "Springy animations for buttons, switches, sections and pages", "animation expressive material spring")
        add("General", "Sounds", "Click sounds", "Pixel-style sounds for buttons and toggles", "audio sound effects mute")
        add("General", "Sounds", "Sound style", "Wood, pixel or smooth sounds", "wood pixel smooth osu click blocky audio sfx")
        add("General", "Sounds", "Vary the pitch", "Each click a little higher or lower than the last", "pitch variation random sound tone")
        add("General", "Sounds", "Sounds on the YASB bar", "A tick when you click the bar or its menus", "audio click yasb widgets buttons helper")
        add("General", "Sounds", "Volume", "How loud the sounds are", "audio loudness")
        add("General", "Sounds", "Preview", "Plays the sounds", "audio test")
        add("General", "Sync", "Keep app themes in sync", "Rewrites the app themes when the wallpaper or accent changes", "background watcher wallpaper discord startup auto")
        add("General", "Sync", "Background helper", "Whether the helper (app sync and bar sounds) is running and starts with Windows", "restart status autostart startup sounds")
        add("Wallpaper", "Folder", "Wallpapers folder", "The folder the YASB wallpapers widget uses", "wallpaper pictures images background")
        add("Display", "Bar placement", "Monitor", "Which screens show the bar", "screen display primary yasbc")
        add("Display", "Bar placement", "Position", "Top or bottom of the screen", "top bottom edge")
        add("Display", "Bar placement", "Bar height", "In pixels", "size thick")
        add("Display", "Bar placement", "Space above the bar", "Gap between the top screen edge and the bar", "margin padding")
        add("Display", "Bar placement", "Space below the bar", "Gap between the bar and the bottom screen edge", "margin padding bottom")
        add("Display", "Bar placement", "Background opacity", "How see-through the bar background is", "transparent transparency alpha")
        for t, d, k in (("Outer gap", "Space between the windows and the screen edge", "padding workspace"), ("Inner gap", "Space between tiled windows", "padding container"),
                        ("Border width", "Thickness of the focus border", "outline"), ("Border offset", "Moves the border in or out", "outline"),
                        ("Focus border", "Draw a border around the focused window", "outline highlight"), ("Border style", "System, rounded or square", "outline corners"),
                        ("New windows", "Create a new tile, or append to the focused one", "behaviour container"),
                        ("Mouse follows focus", "Move the pointer to the window you focus", "cursor"), ("Transparency", "Make unfocused windows see-through", "opacity alpha"),
                        ("Animations", "Animate windows when they tile", "animation motion")):
            add("Display", "Komorebi", t, d, "tiling window manager " + k)
        for n in ("Windows accent", "Content", "Fidelity", "Tonal Spot", "Monochrome", "Expressive", "Neutral", "Vibrant", "Fruit Salad", "Custom"):
            add("Colors", "Scheme", n, "A colour scheme for the bar", "theme palette material you")
        add("Colors", "Source", "Seed colour", "The dominant colour of your wallpaper", "wallpaper")
        add("Colors", "Source", "Windows accent", "The colour everything uses when the scheme is Windows accent", "")
        text = self.cfg_text()
        for name, typ in read_widgets(text).items():
            add("Widgets", "Layout", name, typ.split(".")[-1] if typ else "widget", "widget left center right order move alignment on off show hide")
        add("Widgets", "Hidden", "Hidden widgets", "Switched off, on no side of the bar, or not in config.yaml yet", "hidden disabled inactive off available add")
        defined = set(read_widgets(text).values())
        for key, title, desc, *_ in CATALOG:
            if CATALOG_BY_KEY[key][4] not in defined:
                add("Widgets", "Hidden", title, desc, "new widget add hidden available keyboard notes control center active window cava audio visualizer whkd hotkeys")
        if "yasb.active_window.ActiveWindowWidget" in defined:
            for t, d, k in (("Truncate title after", "Characters shown before the title is cut", "length max ellipsis"),
                            ("Show the app icon", "An icon in front of the title", "icon"), ("Icon size", "Only used when the icon is on", "")):
                add("Bar", "Active window title", t, d, "active window title " + k)
        if "yasb.cava.CavaWidget" in defined:
            for t, d, k in (("Cava bars", "How many bars", "number count"), ("Cava bar width", "Thickness of each bar", "thick"),
                            ("Cava bar spacing", "Space between the bars", "gap"), ("Cava bar height", "Tallest a bar can get", "size"),
                            ("Cava colour", "Hex colour of the bars", "color hex")):
                add("Bar", "Audio visualizer (Cava)", t, d, "cava audio visualizer music " + k)
        add("Bar", "Capsules", "Same spacing on both sides", "Off: set the left and right separately", "left right link")
        add("Bar", "Capsules", "Widget spacing", "Space between capsules, left and right", "gap margin between")
        add("Bar", "Capsules", "Same padding on both sides", "Off: set the left and right separately", "left right link")
        add("Bar", "Capsules", "Capsule padding", "Space inside a capsule", "size width inner")
        if defined & set(CATALOG_BY_TYPE):
            add("Bar", "Capsules", "Icon button padding", "Left and right padding of icon buttons and titles", "button size width space")
        add("Bar", "Capsules", "Capsule roundness", "Corner radius of the capsules", "radius corners rounded pill squircle size")
        for side in ("left", "right"):
            add("Bar", "Capsules", f"Spacing: {side}", f"Space between capsules, {side} side", "gap margin")
            add("Bar", "Capsules", f"Padding: {side}", f"Space inside a capsule, {side} side", "size width inner")
        add("Bar", "Capsules", "Capsule border width", "A line around every capsule", "outline stroke thickness")
        add("Bar", "Capsules", "Capsule border colour", "Black unless you set another", "outline stroke color hex rgba")
        add("Bar", "Shortcuts", "Middle-click opens ShellFlow", "Middle-click a bar widget (the Home button) to open ShellFlow", "middle click mouse home open settings shortcut exec")
        if len(read_widgets(text)) > 1:
            add("Bar", "Shortcuts", "On which widget", "The widget you middle-click to open ShellFlow", "middle click which widget home")
        add("Bar", "Menus", "Floating menus", "Menus and popups float below the bar instead of touching it", "popup attached detached separation offset")
        add("Bar", "Menus", "Menu roundness", "Corner radius of the menus; floating ones are round all over, attached ones are square where they touch the bar", "radius corners rounded popup border")
        add("Bar", "Menus", "Gap from the bar", "Distance between the bar and its menus, 10 px by default", "popup offset_top separation distance floating")
        add("Bar", "Bar", "Bar rounding", "Corner radius of the whole bar", "radius corners rounded")
        for t, d in (("Pill rounding", "Corner radius of each workspace pill"), ("Pill height", "Height of each pill"), ("Width: empty", "A workspace with no windows"),
                     ("Width: with windows", "A workspace that has windows"), ("Width: active", "The workspace you are on"), ("Space between pills", "Left and right of each pill")):
            add("Bar", "Workspace pills", t, d, "komorebi workspaces pills size width radius")
        add("Bar", "Workspaces", "Show workspace labels", "The number or name on each workspace button", "numbers names text komorebi")
        add("Bar", "Workspaces", "App icons on busy workspaces", "Show the icons of the apps running there", "komorebi")
        add("Bar", "Workspaces", "App icons on the active workspace", "Show the icons of the apps on the one you are on", "komorebi")
        add("Bar", "Workspaces", "Hide duplicate icons", "One icon per app", "komorebi")
        add("Bar", "Workspaces", "Hide the label when icons show", "Icons only", "komorebi")
        add("Bar", "Behaviour", "Auto hide", "Slide the bar away until the mouse reaches the screen edge", "hide slide")
        add("Bar", "Behaviour", "Hide on fullscreen", "Get out of the way of games and videos", "game video")
        add("Bar", "Behaviour", "Always on top", "Stay above other windows", "topmost")
        add("Bar", "Behaviour", "Reserve space", "Windows keeps other windows clear of the bar", "appbar work area")
        add("Bar", "Behaviour", "Animation", "Slide or fade the bar in and out", "motion")
        add("Bar", "Behaviour", "Animation style", "Slide or fade", "motion")
        add("Bar", "Behaviour", "Animation speed", "How long the animation takes", "duration ms")
        add("Templates", "Write now", "Write all the themes", "Every app that is switched on", "apply")
        for key, name, var, _, desc, _ in th.APP_TABLE:
            add("Templates", "Apps", name, desc, f"{var} folder path theme template")
        add("Edits", "Fonts", "Bar font", "Widget text and icons", "typeface family nerd poppins")
        add("Edits", "Fonts", "Menu and clock font", "Menus, tooltips and the clock", "typeface family poppins")
        for label, var in COLOUR_VARS:
            add("Edits", "Colours", label, f"--yasb-{var}", "colour color hex rgba custom override")
        for group, paths in config_files().items():
            for p in paths:
                add("Files", group, p.name, str(p.parent), "edit open file config")
        add("Keybinds", "Keyboard", "Keys", "Press keys, or click them, to see the keybinds that use them", "keyboard hold combination press")
        add("Keybinds", "Keybinds", "Add a keybind", "A new line at the end of your whkdrc", "whkd hotkey shortcut new")
        wtext = self.whkd_text()
        if wtext is None:
            add("Keybinds", "Keybinds", "Create a whkdrc", "An empty whkdrc", "whkd create")
        for b in parse_whkdrc(wtext or ""):
            add("Keybinds", "Keybinds", keybind_title(b), b["keys_text"] + "   " + b["cmd"], "whkd keybind hotkey " + b["group"])
        add("Templates", "Apps", "Restart File Pilot", "Close File Pilot, write its colours, open it again", "file pilot fpilot reload restart colors")
        add("Templates", "Apps", "Restart Helium", "Close Helium and open it again with your tabs so it reads the new theme", "browser chromium theme reload restart auto")
        add("Backup", "Back up", "Back up now", "Zip your config, styles, .env, edits, komorebi and whkd files", "backup save copy zip")
        add("Backup", "Back up", "Backups folder", str(BACKUP_DIR), "backup location open")
        if old_copies():
            add("Backup", "Back up", "Old automatic copies", "config.yaml.bak and styles.css.bak from older versions", "bak delete")
        for p, count, size in list_backups():
            add("Backup", "Your backups", backup_title(p), f"{count} files", "restore delete backup")
        add("Backup", "Log files", "Keep log files", "Write the start and helper logs", "logs logging debug off")
        add("Backup", "Log files", "Diagnostic report", "Save a full check as shellflow_doctor.txt", "doctor report support")
        for p in log_files():
            add("Backup", "Log files", p.name, str(p.parent), "log open")
        if not log_files():
            add("Backup", "Log files", "No log files", "Nothing has been written", "")
        else:
            add("Backup", "Log files", "Clear log files", "Deletes the logs", "delete remove")
        add("About", "System information", "Windows", platform.platform(), "version os system")
        add("About", "System information", "Python", sys.version.split()[0], "version system")
        add("About", "System information", "YASB", yasb_version(), "version system")
        add("About", "System information", "komorebi", komorebi_version(), "version system")
        add("About", "System information", "Monitors", "The screens YASB sees", "system display")
        add("About", "System information", "Config folder", str(th.CONFIG), "location path")
        add("About", "About", "Copy info", "Copy the system information", "clipboard")
        return I

    def find(self, query):
        """The index entries that contain every word of the query, best matches (title) first."""
        words = query.lower().split()
        scored = []
        for page, card, title, desc, kw in self.search_index():
            hay = " ".join((page, card, title, desc, kw)).lower()
            if all(w in hay for w in words):
                scored.append((0 if all(w in title.lower() for w in words) else 1 if card == "Page" else 2, (page, card, title, desc)))
        order = {n: i for i, (n, _, _) in enumerate(PAGES)}
        scored.sort(key=lambda t: (t[0], order[t[1][0]]))
        return [e for _, e in scored]

    def set_search(self, text):
        """Typing searches every setting. The results appear a moment after the last key."""
        self.search = text.strip().lower()
        if self.search_job:
            self.root.after_cancel(self.search_job)
        self.search_job = self.root.after(160, self.apply_search)

    def apply_search(self):
        self.search_job = None
        hits = self.find(self.search) if self.search else []
        self.counts = {}
        for page, card, *_ in hits:
            if card != "Page":
                self.counts[page] = self.counts.get(page, 0) + 1
        if self.search:
            self.view_results = True
            self.go(self.current, keep=True)
        else:
            self.view_results = False
            self.go(self.current)

    def clear_search(self):
        self.search_box.delete(0, "end")
        if self.search_pop is not None:  # the attached window's box: emptied and closed
            self.search_pop.delete(0, "end")
            self.search_pop.destroy()
            self.search_pop, self.search_open = None, False
        self.set_search("")
        self.root.after(200, self.search_box.master.focus_set)

    def open_first(self):
        hits = self.find(self.search) if self.search else []
        if hits:
            self.jump(*hits[0][:3])

    def jump(self, page, card, title):
        """Open the page a setting is on, scroll to it and flash a frame around it."""
        i = [n for n, *_ in PAGES].index(page)

        def go_there():
            if self.search_job:
                self.root.after_cancel(self.search_job)
                self.search_job = None
            self.search, self.counts, self.view_results = "", {}, False  # the search is done: clear it
            self.search_box.delete(0, "end")
            if self.search_pop is not None:
                self.search_pop.destroy()
                self.search_pop, self.search_open = None, False
            self.go(i)
            self.cv.focus_set()  # the cursor leaves the search box
            self.root.update_idletasks()
            self.locate(card, title)
        self.defer(go_there)

    def locate(self, card, title):
        cv = self.cv
        texts = [(i, cv.itemcget(i, "text")) for i in cv.find_all() if cv.type(i) == "text"]
        target = next((i for i, t in texts if t == title), None) or next((i for i, t in texts if t.startswith(card)), None)
        if target is None:
            return
        self.flow.reveal(target)  # it may be inside a closed section
        self.root.update_idletasks()
        total = float(cv.cget("scrollregion").split()[3])
        cv.yview_moveto(max(0.0, (cv.bbox(target)[1] - 90) / total))
        self.root.update_idletasks()
        x0, y0, x1, y1 = cv.bbox(target)
        frame = cv.create_image(-6, (y0 + y1) / 2 - 36, anchor="nw", image=rounded(self.flow.cw + 12, 72, 16, None, self.c["accent2"], 2.5))
        self.flash = frame

        def drop():
            try:
                cv.delete(frame)
            except tk.TclError:
                pass
        self.root.after(1800, drop)

    def page_search(self):
        f, c = self.draw_main("Search", "search"), self.c
        hits = self.find(self.search)
        pages = {n: g for n, g, _ in PAGES}
        if not hits:
            f.note(f'Nothing matches "{self.search}". Try another word, for example font, opacity, gap, border or auto hide.')
            return f
        cards = list(dict.fromkeys((p, cd) for p, cd, *_ in hits))
        f.note(f'{len(hits)} results in {len(cards)} cards for "{self.search}". Click one to jump to it (Enter opens the first).')
        for page, card in cards:
            f.heading(f"{page}   >   {card}" if card != "Page" else f"{page}", pages[page], collapsible=False)
            f.begin_card()
            for p, cd, title, desc in hits:
                if (p, cd) == (page, card):
                    yc = f.row(title, desc[:90], glyph=pages[page], click=lambda p=p, cd=cd, t=title: self.jump(p, cd, t))
                    f.cv.create_image(f.r, yc, image=icon("chev_right", 20, c["accent2"]), anchor="e")
            f.end_card()
        return f
