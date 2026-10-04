"""themes.windhawk"""
import json
import os
import re
import subprocess
import time
from ..core import DATA, LAUNCHER, NO_WINDOW, _mix, env, pythonw, watch_log

# key, name, folder variable, several folders?, short description, writer
# ---- Windhawk ------------------------------------------------------------------------------
# Windhawk's styler mods (taskbar, start menu, notification centre) colour things with {ThemeResource SystemAccentColorLight1} and so on,
# which is always your Windows accent. ShellFlow swaps those references for the hex colours of the scheme you picked. The mods' settings
# live in the registry (HKLM\SOFTWARE\Windhawk\Engine\Mods\<mod>\Settings), which needs administrator rights to change:
# the first time, one UAC prompt sets up a scheduled task that does the writing, and after that it is silent.
WH_MODS = "windows-11-taskbar-styler,windows-11-start-menu-styler,windows-11-notification-center-styler"


WH_ROOT = r"SOFTWARE\Windhawk\Engine\Mods"


WH_TASK = "ShellFlowWindhawk"


WH_STATE = DATA / "windhawk_state.json"      # what the settings looked like before, and what was written


WH_PENDING = DATA / "windhawk_pending.json"  # changes waiting for the elevated task


ACCENT_REF = re.compile(r"\{ThemeResource (SystemAccentColor(?:Light|Dark)?[123]?)\}")


class Registry:
    """The Windhawk settings in the registry. (Tests use a stand-in with the same three methods.)"""

    def read(self, mod):
        import winreg
        out = {}
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{WH_ROOT}\\{mod}\\Settings", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    if isinstance(value, str):
                        out[name] = value
                    i += 1
        except OSError:
            pass
        return out

    def write(self, mod, values):
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{WH_ROOT}\\{mod}\\Settings", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            for name, value in values.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    def bump(self, mod):
        """The mod reloads its settings when this changes (any different number will do)."""
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{WH_ROOT}\\{mod}", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.SetValueEx(k, "SettingsChangeTime", 0, winreg.REG_DWORD, int(time.time()) & 0x7FFFFFFF)


def wh_mods():
    return [m.strip() for m in (env("YASB_WINDHAWK_MODS") or WH_MODS).split(",") if m.strip()]


def accent_colours(P, capsules=None):
    """What each {ThemeResource SystemAccentColor...} becomes. By default the base accent is the capsules' colour (the bar's capsules use
    the "light1" shade), so everything Windhawk draws in the accent matches the bar. YASB_WINDHAWK_MATCH=accent keeps Windows' own ladder."""
    capsules = (env("YASB_WINDHAWK_MATCH") != "accent") if capsules is None else capsules
    return {"SystemAccentColor": P.l1 if capsules else P.acc, "SystemAccentColorLight1": P.l1, "SystemAccentColorLight2": P.l2,
            "SystemAccentColorLight3": P.l3, "SystemAccentColorDark1": P.d1, "SystemAccentColorDark2": P.d2, "SystemAccentColorDark3": P.d3}


# Style constants whose colour ShellFlow sets by name, whatever they hold now (so a value you edited by hand still follows the scheme):
# the taskbar button in its states, as the bar's capsule and its darker states, and the clock button's dark ground.
WH_OWNED = ("buttonaccent", "buttonaccenthover", "buttonaccentactive", "buttonaccentpressed", "buttonclock")


def wh_const_name(text):
    """"ButtonAccentHover=<SolidColorBrush ... />" -> "buttonaccenthover" ("" when it is not a style constant)."""
    m = re.match(r"\s*(\w+)\s*=\s*<", text)
    return m.group(1).lower() if m else ""


def wh_owned_colour(key, P):
    """The colour of an owned style constant, for the scheme P (None for any other name)."""
    shade = lambda t: _mix(P.l1, "#000000", t)
    exact = env("YASB_WINDHAWK_ACTIVE")
    active = exact.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", exact or "") else shade(.30)
    return {"buttonaccent": P.l1, "buttonaccenthover": shade(.12), "buttonaccentactive": active, "buttonaccentpressed": shade(.33),
            "buttonclock": P.t(.16)}.get(key)


def wh_set_colour(text, colour, solid=True):
    """The setting's text with its brush colour replaced (and Opacity="1" when solid, as the bar's capsules are)."""
    new = re.sub(r'(\bColor\s*=\s*")[^"]*(")', lambda m: m.group(1) + colour + m.group(2), text, count=1)
    return re.sub(r'(\bOpacity\s*=\s*")[^"]*(")', lambda m: m.group(1) + "1" + m.group(2), new, count=1) if solid else new


ACCENT_BRUSH = re.compile(r"<SolidColorBrush\b[^>]*\{ThemeResource SystemAccentColor[^}]*\}[^>]*>")


def wh_render(template, P, colours, capsules):
    """The text of a setting with its accent references replaced. In capsule mode the accent brushes are also made solid (Opacity 1), as the
    bar's capsules are, and a style constant named for a state gets that state's colour: "...Hover" is the capsule darkened by 12%,
    "...Pressed" by 33%, "...Active" by 30% (what a populated workspace is on the bar). Everything that is not a state is the plain capsule colour. YASB_WINDHAWK_ACTIVE=#rrggbb sets the active colour exactly.
    The five button constants in WH_OWNED are set by name instead (hover 12%, active 30%, pressed 33% darker; the clock button a dark ground)."""
    if not capsules:
        return ACCENT_REF.sub(lambda m: colours[m.group(1)], template)
    owned = wh_owned_colour(wh_const_name(template), P)
    if owned:
        return wh_set_colour(template, owned, wh_const_name(template) != "buttonclock")
    text = ACCENT_BRUSH.sub(lambda m: re.sub(r'Opacity="[^"]*"', 'Opacity="1"', m.group(0)), template)
    name = re.match(r"\s*(\w+)\s*=", text)
    key = name.group(1).lower() if name else ""
    state = "pressed" if "pressed" in key else "hover" if ("hover" in key or "pointerover" in key) else \
        "active" if re.search(r"(?<!in)(active|selected|checked)", key) else None
    if state:
        exact = env("YASB_WINDHAWK_ACTIVE")
        active = exact.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", exact or "") else _mix(P.l1, "#000000", .30)
        tint = {"hover": _mix(P.l1, "#000000", .12), "pressed": _mix(P.l1, "#000000", .33), "active": active}[state]
        return ACCENT_REF.sub(lambda m: tint, text)
    return ACCENT_REF.sub(lambda m: colours[m.group(1)], text)


def wh_load_state():
    try:
        return json.loads(WH_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def wh_norm(text):
    """A setting's text with spaces and quotes removed, so a harmless reformatting by Windhawk does not make it look edited."""
    return re.sub(r"[\s\"']+", "", text)


def wh_plan(P, mods, reg, state):
    """What to change. For every setting that mentions an accent colour, the original text (with the {ThemeResource ...} references) is
    remembered, so the next scheme starts again from it. A setting counts as yours (and is left alone) only when it is none of the texts
    ShellFlow has written or seen there: a write that never arrived (the elevated task failed once) must not make it look edited.
    Returns ({mod: {setting: new text}}, new state). The state also lists, under "_skipped", what was left alone."""
    capsules = env("YASB_WINDHAWK_MATCH") != "accent"
    colours, plan, new_state, skipped = accent_colours(P, capsules), {}, {}, {}
    for mod in mods:
        mine, saved = {}, state.get(mod, {})
        for name, cur in reg.read(mod).items():
            rec = saved.get(name) if isinstance(saved.get(name), dict) else None
            if capsules and wh_const_name(cur) in WH_OWNED:  # ours by name, whatever it holds now (a hand-edited value included)
                template = rec["template"] if rec else cur
                new = wh_render(template, P, colours, capsules)
                history = [x for x in ((rec.get("history", []) if rec else []) + [cur, new]) if x][-8:]
                mine[name] = {"template": template, "written": new, "previous": cur, "history": list(dict.fromkeys(history))}
                if new != cur:
                    plan.setdefault(mod, {})[name] = new
                continue
            known = {wh_norm(x) for x in (rec.get("history", []) + [rec.get("written", ""), rec.get("previous", "")] if rec else [])}
            if ACCENT_REF.search(cur):
                template = cur  # an original (or one you changed back to a reference)
            elif rec and wh_norm(cur) in known:
                template = rec["template"]  # something ShellFlow wrote or found there before
            else:
                if rec:
                    skipped.setdefault(mod, []).append(name)  # we wrote here once, and you changed it since
                continue  # not an accent setting, or yours
            new = wh_render(template, P, colours, capsules)
            history = [x for x in ((rec.get("history", []) if rec else []) + [cur, new]) if x][-8:]
            mine[name] = {"template": template, "written": new, "previous": cur, "history": list(dict.fromkeys(history))}
            if new != cur:
                plan.setdefault(mod, {})[name] = new
        if mine:
            new_state[mod] = mine
    if skipped:
        new_state["_skipped"] = skipped
    return plan, new_state


def wh_apply_pending(reg=None):
    """Write the waiting changes into the registry (needs administrator rights). Returns how many settings were written."""
    reg = reg or Registry()
    try:
        pending = json.loads(WH_PENDING.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    n = 0
    for mod, values in pending.items():
        reg.write(mod, values)
        n += len(values)
    for mod in pending:  # only now: the mods all reload at the same moment, after every setting is in place (one flash, not three in a row)
        reg.bump(mod)
    WH_PENDING.unlink(missing_ok=True)
    watch_log(f"windhawk: wrote {n} settings")
    return n


def wh_task_exists():
    r = subprocess.run(["schtasks", "/Query", "/TN", WH_TASK], capture_output=True, creationflags=NO_WINDOW if os.name == "nt" else 0)
    return r.returncode == 0


def wh_run_task():
    """Ask the elevated scheduled task to write the waiting changes (silent: no prompt)."""
    r = subprocess.run(["schtasks", "/Run", "/TN", WH_TASK], capture_output=True, creationflags=NO_WINDOW if os.name == "nt" else 0)
    return r.returncode == 0


def wh_setup_task():
    """One UAC prompt: create the scheduled task that runs `theme.py windhawk-apply` with administrator rights."""
    cmd = DATA / "windhawk_setup.cmd"
    cmd.write_text(f'@echo off\r\nschtasks /Create /TN "{WH_TASK}" /TR "\\"{pythonw()}\\" \\"{LAUNCHER}\\" windhawk-apply" '
                   f'/SC ONCE /ST 00:00 /RL HIGHEST /F\r\n', encoding="utf-8")
    ps = f"Start-Process -FilePath cmd.exe -ArgumentList '/c','{cmd}' -Verb RunAs -Wait -WindowStyle Hidden"
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=NO_WINDOW if os.name == "nt" else 0)
    return wh_task_exists()


def write_windhawk(P, reg=None):
    """Windhawk: the styler mods follow your colour scheme instead of the Windows accent.
    Off by default (switch it on under Templates). Mods: YASB_WINDHAWK_MODS (comma separated mod ids).
    Needs administrator rights once: Templates > Windhawk > Set up."""
    reg = reg or Registry()
    plan, state = wh_plan(P, wh_mods(), reg, wh_load_state())
    WH_STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    if not plan:
        return False
    WH_PENDING.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    try:
        wh_apply_pending(reg)  # works when this process is allowed to write
    except OSError:
        if not (wh_task_exists() and wh_run_task()):
            raise PermissionError("Windhawk's settings need administrator rights: open ShellFlow > Templates > Windhawk and press Set up")
    return True


def wh_restore(reg=None):
    """Put the {ThemeResource ...} references back (so the mods follow the Windows accent again). Returns how many settings."""
    reg, state = reg or Registry(), wh_load_state()
    pending = {mod: {name: rec["template"] for name, rec in settings.items()} for mod, settings in state.items() if settings and not mod.startswith("_")}
    if not pending:
        return 0
    WH_PENDING.write_text(json.dumps(pending, indent=1), encoding="utf-8")
    try:
        n = wh_apply_pending(reg)
    except OSError:
        if not (wh_task_exists() and wh_run_task()):
            raise PermissionError("administrator rights are needed: Templates > Windhawk > Set up")
        n = sum(len(v) for v in pending.values())
    WH_STATE.unlink(missing_ok=True)
    return n
