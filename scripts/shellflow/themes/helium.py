"""themes.helium"""
import json
import os
import re
import subprocess
import time
import zlib
from ..core import NO_WINDOW, _mix, defaults, env, folders, save, watch_log

HELIUM_CACHE = "Cached Theme.pak"


def clear_helium_cache():
    """Chromium keeps a built copy of an unpacked theme in the theme folder ("Cached Theme.pak") and keeps using it: it only builds it
    again when the file is missing. Deleting it makes the browser read manifest.json again the next time it starts. A running browser
    holds the file open, so that case is left (it is cleared when Helium is restarted). Returns how many were deleted."""
    gone = 0
    for d in folders("YASB_HELIUM_THEME", *defaults("helium")):
        try:
            (d / HELIUM_CACHE).unlink()
            gone += 1
        except FileNotFoundError:
            pass
        except OSError:
            pass  # in use
    return gone


def helium_theme_dir():
    """The folder that holds the written theme (manifest.json), or None."""
    for d in folders("YASB_HELIUM_THEME", *defaults("helium")):
        if (d / "manifest.json").is_file():
            return d
    return None


def restart_helium():
    """Close Helium the polite way (so it saves its tabs) and open it again with the last session, so it reads the theme that was written.
    Helium is found by its window and its folder (the program is not always called helium.exe); only that one process is closed, by its id,
    so another Chromium browser is left alone. YASB_HELIUM_EXE names the program if that does not find it. Returns what happened."""
    flags = NO_WINDOW if os.name == "nt" else 0

    def run(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=20, creationflags=flags).stdout or ""
        except (OSError, subprocess.SubprocessError):
            return ""
    exe = (env("YASB_HELIUM_EXE") or "").strip()
    name = exe[:-4] if exe.lower().endswith(".exe") else exe
    pick = f"$_.ProcessName -eq '{name}'" if name else "$_.Path -like '*\\Helium\\*' -or $_.ProcessName -like '*helium*'"
    found = run(["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and (" + pick + ") } | Select-Object -First 1 | "
                 "ForEach-Object { '{0}|{1}' -f $_.Id, $_.Path }"]).strip()
    if "|" not in found:
        clear_helium_cache()
        return "Helium is not open (no window found): it will read the new theme when it starts"
    pid, path = found.split("|", 1)
    run(["taskkill", "/PID", pid])  # no /F: Helium is asked to close, and saves its session
    for _ in range(60):
        if pid not in run(["tasklist", "/FI", f"PID eq {pid}", "/NH"]):
            break
        time.sleep(.2)
    else:
        return "Helium did not close (is something unsaved?): close it yourself and open it again"
    time.sleep(1.0)  # its other processes finish
    clear_helium_cache()  # closed now: its cached copy of the theme can go, so it builds the theme from manifest.json as it starts
    try:
        subprocess.Popen([path, "--restore-last-session"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, creationflags=(flags | 0x00000008) if os.name == "nt" else 0)
    except OSError:
        return "Helium closed but could not be started again: open it yourself"
    return "Helium restarted with your tabs"


def write_helium(P):
    """Helium (and Chrome, Brave, Vivaldi, Edge): a theme extension "YASB Accent": manifest.json in a folder. The active tab and the
    toolbar are black, the accent is in the address bar and icons (YASB_HELIUM_TAB=accent: an accent toolbar and active tab; =#rrggbb: that colour;
    =dark: a near-black toolbar and a grey address bar).
    Default:  <config folder>/themes/helium, written when one of those browsers is installed
    Variable: YASB_HELIUM_THEME
    Once:     helium://extensions > Developer mode > Load unpacked > pick the folder. After that the colours follow your scheme, but
              Helium reads a changed theme only when it starts (its reload arrow is not reliable): ShellFlow > Templates > Helium >
              "Restart Helium" closes it and opens it again with your tabs."""
    c = lambda h: [int(h[i:i + 2], 16) for i in (1, 3, 5)]
    colours = {
        # the backgrounds are black, not tinted: the tab strip, the new-tab page. The accent is for the active tab and what sits on it.
        "frame": "#000000", "frame_inactive": "#000000", "frame_incognito": "#000000", "frame_incognito_inactive": "#000000",
        "toolbar": "#0d0d0d", "tab_text": "#ffffff", "tab_background_text": P.neu(70), "bookmark_text": P.l2,
        "toolbar_button_icon": P.l1, "omnibox_background": "#1a1a1a", "omnibox_text": "#ffffff", "button_background": "#0d0d0d",
        "ntp_background": "#000000", "ntp_text": "#ffffff", "ntp_link": P.l1, "ntp_section": "#0d0d0d", "ntp_header": "#000000",
    }
    mode = env("YASB_HELIUM_TAB")
    hexa = mode.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", mode or "") else ""
    if mode == "accent" or hexa:
        # Chromium draws the active tab in the toolbar's colour, so the toolbar is the active-tab colour: the capsule colour darkened 30%
        # (what a populated workspace is on the bar), with white text, and the address bar a darker pill inside it. YASB_HELIUM_TAB=#rrggbb
        # sets that colour exactly.
        tab = hexa or _mix(P.l1, "#000000", .30)
        pill = _mix(tab, "#000000", .35)
        colours.update({"toolbar": tab, "tab_text": "#ffffff", "bookmark_text": P.l3, "toolbar_button_icon": P.l3,
                        "omnibox_background": pill, "omnibox_text": "#ffffff", "button_background": pill})
    elif mode != "dark":
        # the default: black. Helium draws the tab strip and the toolbar as one surface in the toolbar's colour (the frame colour only
        # shows at the edges), so an accent toolbar made the whole top of the window accent-coloured. Black it is; the accent is in the
        # icons, the bookmarks and the links.
        colours.update({"toolbar": "#000000", "tab_text": "#ffffff", "bookmark_text": P.l2, "toolbar_button_icon": P.l1,
                        "omnibox_background": "#000000", "omnibox_text": "#ffffff", "button_background": "#0d0d0d"})
    version = "1.%d.0" % (zlib.crc32(json.dumps(colours, sort_keys=True).encode()) & 0xFFFF)  # changes only when a colour does
    manifest = {"manifest_version": 3, "name": "YASB Accent", "version": version,
                "description": "Colours from your ShellFlow / YASB colour scheme (written by theme.py)",
                "theme": {"colors": {k: c(v) for k, v in colours.items()}, "tints": {"buttons": [-1, -1, -1]}}}
    dirs = folders("YASB_HELIUM_THEME", *defaults("helium"))
    before = [(d / "manifest.json").read_text(encoding="utf-8") if (d / "manifest.json").is_file() else "" for d in dirs]
    save(dirs, "manifest.json", json.dumps(manifest, indent=2))
    changed = any(b and b != json.dumps(manifest, indent=2) for b in before)  # an installed theme whose colours just changed
    if changed:
        clear_helium_cache()  # so the browser builds the theme again from the new manifest (a running one keeps its copy until restarted)
    if changed and env("YASB_HELIUM_AUTORESTART") == "1":  # opt in: Helium reads a changed theme only when it starts
        import threading
        threading.Thread(target=lambda: watch_log("helium: " + restart_helium())).start()
    save(dirs, "README.txt", "YASB Accent: a Chromium theme written by ShellFlow (theme.py).\n\nLoad it once:\n"
         "  1. Open helium://extensions (chrome://extensions in other browsers)\n  2. Turn on Developer mode\n"
         "  3. Load unpacked, and pick this folder\n\nWhen your scheme changes, ShellFlow rewrites manifest.json. Helium reads a changed theme\n"
         "when it starts: restart it (ShellFlow > Templates > Helium > Restart Helium). ShellFlow deletes the 'Cached Theme.pak' file in\n"
         "this folder first: the browser keeps a built copy of the theme there and only reads manifest.json again when it is gone.\n"
         "If a restart still shows the old colours, remove the theme and Load unpacked again.\n")
