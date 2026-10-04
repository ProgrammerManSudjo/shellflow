"""Sizes, paths and the list of pages."""
from .. import api as th

EDITS_JSON = th.DATA / "settings.json"
HANG_LOG = th.LOGS / "settings_hang.log"  # only exists if the last start got stuck
UI_STATE = th.DATA / "ui_state.json"      # which sections are open (window state only: nothing here reloads YASB)
THUMBS = th.DATA / "thumbs"
Sfx = th.Sfx  # the sound engine lives in system/sounds.py: the background helper plays the YASB bar clicks with it too
sound_settings = th.sound_settings
parse_colour = th.parse_colour


APP_NAME = "ShellFlow"


W, H = 1150, 790                   # window size


MARGIN = 15                        # the accent border sits this far inside the window edge


BORDER = 2                         # thickness of that border


RING_R = 30                        # its corner radius


GAP = 10                           # space between the panels, and between them and the border


EDGE = MARGIN + BORDER + GAP       # where the panels start


SIDE_FULL, SIDE_COMPACT = 252, 76  # sidebar width: with labels, icons only


HEAD = 76                          # height of the panel header (title, close button)


FOOT = 64                          # height of the footer (Reset, Apply)


PADX = 28                          # space left and right of the page content


CONFIG_YAML = th.CONFIG / "config.yaml"


STYLES = th.CONFIG / "styles.css"


ENV = th.CONFIG / ".env"


SPLASH_MIN = 0.35                         # seconds the "starting" window stays up at least (YASB_SPLASH=0 turns the wait off)


STARTUP_TIMEOUT = 12                      # seconds before a stuck start is written to HANG_LOG


NATIVE = th.env("YASB_SETTINGS_TITLEBAR").lower() == "native"


CREATE_NO_WINDOW = 0x08000000


ZONES = ("left", "center", "right")


HOVER_SCALE, PRESS_SCALE = 1.05, 0.93  # how big a control is under the mouse, and while it is pressed


# ============================================================================================
#  8. THE WINDOW  (frame, sidebar, header, tabs, scrolling, saving)
# ============================================================================================
# (name, icon, words the sidebar search matches)
PAGES = (("General", "sliders", "profile name picture avatar actions"),
         ("Display", "monitor", "monitor top bottom opacity komorebi gaps border"),
         ("Colors", "palette", "scheme theme accent wallpaper seed custom"),
         ("Wallpaper", "image", "wallpapers folder picture background desktop picker"),
         ("Widgets", "grid", "layout left center right order alignment"),
         ("Bar", "bar", "spacing capsule workspaces auto hide animation"),
         ("Keybinds", "keyboard", "whkd whkdrc keybinds hotkeys shortcuts keys keyboard komorebi bindings"),
         ("Templates", "layers", "apps discord zed obsidian vscode neovim terminal firefox zen yazi obs folders"),
         ("Edits", "pen", "font colour color hex rgba override"),
         ("Files", "folder", "config yaml css env komorebi whkd edit"),
         ("Backup", "archive", "backup restore zip copy logs log files diagnostic report"),
         ("About", "info", "version system"))
