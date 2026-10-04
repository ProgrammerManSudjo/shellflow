"""themes.obs"""
import os
import re
from pathlib import Path
from materialyoucolor.hct import Hct
from ..core import defaults, env, folders, parse_colour

def find_yami():
    """OBS's own Yami theme: the base this variant extends. Looks where OBS is usually installed (and YASB_OBS_INSTALL)."""
    install = env("YASB_OBS_INSTALL")
    roots = [Path(install)] if install else []
    for var in ("PROGRAMFILES", "PROGRAMW6432", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = Path(os.environ.get(var) or "/not-set")
        roots += [base / "obs-studio", base / "Programs" / "obs-studio", base / "Steam" / "steamapps" / "common" / "OBS Studio"]
    roots += [Path("C:/obs-studio"), Path("C:/OBS-studio"), Path("D:/obs-studio")]
    for r in roots:
        p = r / "data" / "obs-studio" / "themes" / "Yami.obt"
        if p.exists():
            return p
    return None


def obs_variant(yami_text, P):
    """(the .ovt text, how many colours of Yami were read, how many variables the variant sets).
    Black backgrounds, accent buttons. Yami's own colour variables are read from the install (so the names match your
    version): greys become neutral and darker, the blues become the accent. The variables Yami uses for windows, inputs and
    buttons are then set outright, and a few rules make every button the accent colour whatever Yami calls its variables."""
    m = re.search(r"@OBSThemeVars\s*\{(.*?)\n\}", yami_text, re.S)
    if not m:
        raise ValueError("no @OBSThemeVars block in Yami.obt")
    block = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    accent = Hct.from_int(0xFF000000 | int(P.acc[1:], 16))
    out, seen = {}, 0
    for name, value in re.findall(r"(--\w+)\s*:\s*([^;]+);", block):  # every variable, whatever its value looks like
        col = parse_colour(value.strip().strip("'\""))  # #rgb, #rrggbb, rgb(), rgba()
        if col is None:
            continue
        seen += 1
        c = Hct.from_int(0xFF000000 | (col[0] << 16) | (col[1] << 8) | col[2])
        if c.chroma < 10:  # greys and whites: neutral (no accent tint), the dark ones darker
            new = Hct.from_hct(0, 0, c.tone * 0.45 if c.tone < 60 else c.tone)
        elif re.search("primary|blue", name):  # the accent family: the accent hue, same lightness
            new = Hct.from_hct(accent.hue, max(accent.chroma, 24), c.tone)
        else:  # reds, greens, ... keep their meaning
            continue
        out[name] = f"#{new.to_int() & 0xFFFFFF:06x}"
    if not seen:
        sample = " | ".join(l.strip() for l in block.splitlines() if l.strip())[:600]
        raise ValueError(f"no colour variables recognised (0 colours seen). Start of the variables: {sample}")
    out.update({  # the roles themselves, so it does not depend on how the greys are used
        "--bg_window": "#000000", "--bg_base": "#050505", "--bg_preview": "#000000", "--input_bg": "#121212",
        "--button_bg": P.acc, "--button_bg_hover": P.l1, "--button_bg_down": P.d1,
        "--primary": P.acc, "--primary_light": P.l1, "--primary_lighter": P.l2, "--primary_dark": P.d1,
    })
    ink = P.t(.07)
    rules = (f"QMainWindow, QDialog {{ background-color: #000000; }}\n"
             f"QPushButton {{ background-color: {P.acc}; color: {ink}; }}\n"
             f"QPushButton:hover {{ background-color: {P.l1}; }}\n"
             f"QPushButton:pressed {{ background-color: {P.d1}; }}\n"
             f"QPushButton:disabled {{ background-color: #1a1a1a; color: #777777; }}\n")
    return ("@OBSThemeMeta {\n    name: 'YASB Accent';\n    id: 'com.obsproject.Yami.YASBAccent';\n"
            "    extends: 'com.obsproject.Yami';\n    author: 'theme.py';\n    dark: 'true';\n}\n\n"
            "@OBSThemeVars {\n" + "\n".join(f"    {k}: {v};" for k, v in out.items()) + "\n}\n\n" + rules), seen, len(out)


def write_obs(P):
    """OBS: Yami_YASB_Accent.ovt, a variant of OBS's Yami theme recoloured with the accent.
    Reads Yami's colour variables from the OBS install, so the names always match your version.
    Default:  %APPDATA%/obs-studio/themes
    Variables: YASB_OBS_THEMES (output), YASB_OBS_INSTALL (default: Program Files/obs-studio)
    Then:     restart OBS, Settings > Appearance: Theme "Yami", Style "YASB Accent". Needs OBS 30.2+."""
    dirs = folders("YASB_OBS_THEMES", *defaults("obs"))
    if not dirs:
        return
    yami = find_yami()
    if yami is None:
        raise FileNotFoundError("Yami.obt not found - set YASB_OBS_INSTALL to your OBS folder (the one that contains data/obs-studio/themes)")
    body, _seen, _used = obs_variant(yami.read_text(encoding="utf-8", errors="ignore"), P)
    for d in dirs:  # LF line endings: OBS reads the blocks line by line; no BOM
        with open(d / "Yami_YASB_Accent.ovt", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
