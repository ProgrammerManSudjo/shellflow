"""The app themes: one module per app, and the list that runs them (APP_TABLE, write_apps)."""
from ..colors import palette
from ..core import APP_VARS, env, log
from .browsers import write_firefox, write_zen
from .discord import write_discord
from .filepilot import write_filepilot
from .helium import write_helium
from .neovim import write_nvim
from .obs import write_obs
from .obsidian import write_obsidian
from .tacky import write_tacky
from .terminal import write_wt
from .vscode import write_vscode
from .windhawk import write_windhawk
from .yazi import write_yazi
from .zed import write_zed

APP_TABLE = (
    ("discord", "Discord", "YASB_DISCORD_THEMES", True, "midnight colours (BetterDiscord, Vencord, Equicord)", write_discord),
    ("zed", "Zed", "YASB_ZED_THEMES", False, "dark theme \"YASB Accent\"", write_zed),
    ("obsidian", "Obsidian", "YASB_OBSIDIAN_VAULTS", True, "CSS snippet for every vault", write_obsidian),
    ("vscode", "VS Code", "YASB_VSCODE_EXTENSIONS", False, "theme extension \"YASB Accent\"", write_vscode),
    ("nvim", "Neovim", "YASB_NVIM_COLORS", False, "colour scheme \"yasb\"", write_nvim),
    ("wt", "Windows Terminal", "YASB_WT_FRAGMENTS", False, "colour scheme \"YASB Accent\"", write_wt),
    ("firefox", "Firefox", "YASB_FIREFOX_PROFILES", True, "userChrome / userContent styles", write_firefox),
    ("zen", "Zen Browser", "YASB_ZEN_PROFILES", True, "userChrome / userContent styles", write_zen),
    ("yazi", "Yazi", "YASB_YAZI_FLAVORS", False, "flavor \"yasb-accent\"", write_yazi),
    ("obs", "OBS Studio", "YASB_OBS_THEMES", False, "variant of the Yami theme", write_obs),
    ("tacky", "Tacky Borders", "YASB_TACKY_CONFIG", False, "active border colour", write_tacky),
    ("filepilot", "File Pilot", "YASB_FILEPILOT_CONFIG", False, "colour scheme \"YASB Accent\" in FPilot-Config.json", write_filepilot),
    ("helium", "Helium", "YASB_HELIUM_THEME", False, "theme extension for Helium and other Chromium browsers (load the folder once)", write_helium),
    ("windhawk", "Windhawk", "YASB_WINDHAWK_MODS", False, "taskbar, start menu and notification styler mods", write_windhawk),
)


MIDDLE_CLICK_TYPES = ("yasb.home.HomeWidget", "yasb.clock.ClockWidget", "yasb.power_menu.PowerMenuWidget", "yasb.notes.NotesWidget",
                      "yasb.control_center.ControlCenterWidget", "yasb.whkd.WhkdWidget", "yasb.wallpapers.WallpapersWidget")  # widgets that accept an `exec` callback


OPT_IN_APPS = {"windhawk"}  # changes settings outside your own folders: only when you switch it on


def enabled_apps():
    """The apps to write: the keys in YASB_APPS (e.g. "zed,obs"), or all of them when it is not set."""
    raw = env("YASB_APPS").strip().lower()
    if raw == "none":  # the installer's default: no app gets a theme until you switch it on
        return set()
    chosen = {k.strip() for k in raw.split(",") if k.strip()}
    return chosen or {row[0] for row in APP_TABLE if row[0] not in OPT_IN_APPS}


def write_apps():
    """Refresh every app theme from the colours in use (the applied scheme, else your Windows accent). Returns {app key: what went wrong} for the failures."""
    failures = {}
    try:
        P = palette()
    except Exception as e:
        log("palette")
        return {"palette": str(e)}
    on = enabled_apps()
    for key, *_, fn in APP_TABLE:  # one failing app must not stop the others
        if key in on:
            try:
                fn(P)
            except Exception as e:
                log(fn.__name__)
                failures[key] = f"{type(e).__name__}: {e}"
    return failures


APP_VARS.update(row[2] for row in APP_TABLE)
