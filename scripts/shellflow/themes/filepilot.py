"""themes.filepilot"""
import os
import re
import subprocess
import time
from ..colors import palette
from ..core import NO_WINDOW, _mix, defaults, env, folders

FILEPILOT_NAME = "YASB Accent"


def filepilot_scheme(P):
    """The colour scheme for File Pilot, like the Zed theme: black background, white text, the accent for icons, headings, the
    selection and matches. File Pilot writes colours as rrggbb, without the #."""
    mix = lambda a, b, t: _mix(a, b, t)
    colours = {
        "Clear": "#000000", "Caption": "#000000", "Background": P.t(.05), "Surface": P.t(.04), "Foreground": P.t(.10), "Inner": "#000000",
        "Border": P.t(.14), "Outline": P.t(.20), "Separator": P.t(.12), "AlternatingRow": P.t(.07), "IconTint": P.l1,
        "Text": "#ffffff", "Secondary": P.neu(70), "Group": P.l2, "File": "#e6e6e6", "Folder": "#ffffff",
        "Warning": P.l1, "Progress": P.l1, "Selection": mix(P.t(.10), P.l1, .30), "RectSelection": P.l1, "Match": P.d1,
        "Hidden": P.t(.30), "Hover": P.t(.14), "Disabled": P.t(.12),
        "ContentHover": "#ffffff", "ContentSelection": "#ffffff", "ContentDisabledSelection": "#e6e6e6",
        "OutlineHover": P.l2, "OutlineSelection": P.l1, "OutlineDisabledSelection": P.d1,
        "MatchHover": P.l2, "MatchSelection": P.l1, "MatchDisabledSelection": P.d1,
    }
    return {k: v.lstrip("#").upper() for k, v in colours.items()}


def filepilot_update(text, scheme):
    """FPilot-Config.json with the "YASB Accent" scheme in its "Colors" list. That file is not strict JSON (the list holds named
    objects), so it is edited as text: an existing "YASB Accent" is replaced where it stands, otherwise it is added at the top of the
    list. Returns (new text, whether the scheme was new)."""
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r'"Colors"\s*:\s*\[', text)
    if not m:
        raise ValueError('FPilot-Config.json has no "Colors" list yet: in File Pilot open Settings (Ctrl+,), hover a colour scheme and press its fork icon, then try again')
    block = nl.join(['\t\t"%s":' % FILEPILOT_NAME, "\t\t{"] + ['\t\t\t"%s": "%s"%s' % (k, v, "," if i < len(scheme) - 1 else "")
                                                         for i, (k, v) in enumerate(scheme.items())] + ["\t\t}"])
    old = re.search(r'[ \t]*"%s"\s*:\s*\{' % re.escape(FILEPILOT_NAME), text[m.end():])
    if old:
        start = m.end() + old.start()
        depth, i = 0, m.end() + old.end() - 1
        while i < len(text):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                break
            i += 1
        return text[:start] + block + text[i + 1:], False
    rest = text[m.end():]
    empty = rest.lstrip().startswith("]")
    return text[:m.end()] + nl + block + ("" if empty else ",") + rest, True


def filepilot_running():
    """Is File Pilot open? (It keeps its colour schemes in memory and writes FPilot-Config.json again when it closes, which wipes an edit
    made while it was open: that is why the old colours came back.)"""
    exe = env("YASB_FILEPILOT_EXE") or "FilePilot.exe"
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW if os.name == "nt" else 0).stdout
        return exe.lower() in out.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def restart_filepilot():
    """Close File Pilot (it saves its config), write the colour scheme, open it again. Returns what happened."""
    exe = env("YASB_FILEPILOT_EXE") or "FilePilot.exe"
    name = exe[:-4] if exe.lower().endswith(".exe") else exe
    flags = NO_WINDOW if os.name == "nt" else 0

    def run(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=15, creationflags=flags).stdout or ""
        except (OSError, subprocess.SubprocessError):
            return ""
    path = run(["powershell", "-NoProfile", "-Command", f"(Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Select-Object -First 1).Path"]).strip()
    if path:
        run(["taskkill", "/IM", exe])  # no /F: it is asked to close, and writes its config
        for _ in range(50):
            if exe.lower() not in run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"]).lower():
                break
            time.sleep(.2)
        else:
            return "File Pilot did not close: close it yourself, then press Apply now"
    write_filepilot(palette())
    if not path:
        return "File Pilot was not open: the colours are written"
    try:
        subprocess.Popen([path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=(flags | 0x00000008) if os.name == "nt" else 0)
    except OSError:
        return "File Pilot closed but could not be started again: open it yourself"
    return "File Pilot restarted with the new colours"


def write_filepilot(P):
    """File Pilot: the colour scheme "YASB Accent" in FPilot-Config.json (the first time it also becomes the selected scheme).
    Default:  %LOCALAPPDATA%/Voidstar/FilePilot (or %APPDATA%/Voidstar/FilePilot)   Variable: YASB_FILEPILOT_CONFIG
    Needs a "Colors" list in the file: fork any scheme in File Pilot's settings once to make it."""
    for d in folders("YASB_FILEPILOT_CONFIG", *defaults("filepilot")):
        path = d / "FPilot-Config.json"
        if not path.is_file():
            continue
        if filepilot_running():  # an edit now would be overwritten when it closes
            raise RuntimeError("File Pilot is open and would overwrite the colours when it closes: press Restart File Pilot (Templates) or close it first")
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        new, created = filepilot_update(text, filepilot_scheme(P))
        if created:  # the first time: use it (afterwards the scheme you pick stays yours)
            new = re.sub(r'("ColorScheme"\s*:\s*)"[^"]*"', r'\1"%s"' % FILEPILOT_NAME, new, count=1)
            new = re.sub(r'("SystemColorScheme"\s*:\s*)true', r'\1false', new, count=1)
        if new != text:
            path.write_bytes((b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + new.encode("utf-8"))
