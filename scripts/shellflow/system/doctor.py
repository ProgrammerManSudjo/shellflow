"""theme.py doctor: checks everything ShellFlow needs and writes shellflow_doctor.txt."""
import importlib
import os
import re
import subprocess
import sys
import time
import traceback
from ..colors import get_seed, palette, windows_accent_seed
from ..core import CLEAN_ENV_DROP, CONFIG, DATA, LOGS, LAUNCHER, LIVE_KEYS, LOG, NO_WINDOW, PKG, _STARTLOG, dotenv, env, logs_on, proc_start, where
from ..early import _PIDFILE, _windows_of
from .helper import HELPER_VERSION, RUN_KEY, RUN_NAME, autostart_enabled, watcher_running, watcher_version
from .install import HOME_ENTRY
from .sounds import sound_settings
from .winapi import bar_rects, monitor_info, wallpaper_path
from ..themes import APP_TABLE, enabled_apps
from ..themes.obs import find_yami, obs_variant
from ..themes.windhawk import ACCENT_REF, Registry, WH_PENDING, wh_load_state, wh_mods, wh_task_exists

def doctor():
    """Run from a terminal: checks everything ShellFlow needs on this PC, builds every page once, prints the result and
    writes shellflow_doctor.txt (send that file if ShellFlow still does not open)."""
    out = []

    def say(text=""):
        print(text, flush=True)
        out.append(text)

    def check(label, fn):
        t = time.time()
        try:
            r = fn()
            say(f"  OK    {label}" + (f": {r}" if r not in (None, True) else "") + f"   ({time.time() - t:.1f}s)")
        except Exception:
            say(f"  FAIL  {label}: {traceback.format_exc().strip().splitlines()[-1]}")

    say(f"ShellFlow doctor - {time.ctime()}")
    say(f"python      {sys.version.split()[0]}  {sys.executable}")
    say(f"script      {LAUNCHER}")
    say(f"package     {'found' if (PKG / 'settings' / '__init__.py').exists() else 'MISSING: the shellflow folder next to theme.py'}")
    say(f"config      {CONFIG}   config.yaml {'yes' if (CONFIG / 'config.yaml').exists() else 'NO'} | styles.css {'yes' if (CONFIG / 'styles.css').exists() else 'NO'} | yasb_colors.css {'yes' if (CONFIG / 'yasb_colors.css').exists() else 'NO'}")
    say(f"env         YASB_THEME_SCRIPT: environment={os.environ.get('YASB_THEME_SCRIPT')!r}  .env={env('YASB_THEME_SCRIPT')!r}   YASB_SYNC={env('YASB_SYNC')!r}")
    stale = {k: os.environ[k] for k in sorted(LIVE_KEYS | {row[2] for row in APP_TABLE}) if os.environ.get(k) and os.environ[k] != dotenv().get(k, "")}
    if stale:
        say(f"stale copies inherited from YASB (ignored; the .env wins): {stale}")
    inherited = {k: os.environ[k] for k in CLEAN_ENV_DROP if k in os.environ}
    say(f"inherited   {inherited or 'nothing odd (no PYTHONHOME / PYTHONPATH / TCL_LIBRARY / TK_LIBRARY)'}")
    say()
    say("Home menu (what YASB runs when you press ShellFlow)")
    try:
        cfg = (CONFIG / "config.yaml").read_text(encoding="utf-8")
        entries = HOME_ENTRY.findall(cfg) and [m.group(0).strip() for m in HOME_ENTRY.finditer(cfg)]
        if not entries:
            say("  FAIL  there is NO ShellFlow / Settings entry in the Home widget's menu_list in config.yaml.")
            say("        Fix: python theme.py install-menu")
        for line in entries or []:
            say("  entry: " + line)
            cmd = re.search(r'command: "([^"]+)"', line)
            args = re.findall(r'"([^"]*)"', line.split("args:")[1]) if "args:" in line else []

            def resolve(p):
                p = re.sub(r"\$env:(\w+)", lambda m: os.environ.get(m.group(1)) or env(m.group(1)) or "<NOT SET>", p)
                return p
            py = resolve(cmd.group(1)) if cmd else "<no command>"
            script = resolve(args[0]) if args else "<no script>"
            say(f"        python  -> {py}  [{'exists' if os.path.exists(py) else 'MISSING'}]")
            say(f"        script  -> {script}  [{'exists' if os.path.exists(script) else 'MISSING'}]")
            say(f"        argument-> {args[1] if len(args) > 1 else '<none>'}  [{'ok' if args[1:2] == ['settings'] else 'must be: settings'}]")
            if "<NOT SET>" in py + script or not os.path.exists(script):
                say("        >> YASB cannot start this. Fix: python theme.py install-menu   (writes full paths, no variables)")
    except OSError as e:
        say(f"  cannot read config.yaml: {e}")
    try:
        log = open(CONFIG / "yasb.log", encoding="utf-8", errors="ignore").read().splitlines()[-4000:]
        hits = [l for l in log if re.search(r"ShellFlow|theme\.py|settings\.py|pythonw", l, re.I)][-6:]
        say("  YASB's own log, lines about it: " + ("" if hits else "none (YASB logged nothing when the entry was pressed)"))
        for l in hits:
            say("    " + l[:200])
    except OSError:
        pass
    say()
    say("Packages")
    for mod in ("PIL", "materialyoucolor", "tkinter", "winsound", "winreg"):
        check(mod, lambda m=mod: getattr(importlib.import_module(m), "__version__", "") or None)
    say()
    say("Windows")
    import tkinter as tk
    check("Tk starts", lambda: (lambda r: (r.withdraw(), tk.TkVersion, r.destroy())[1])(tk.Tk()))
    check("monitor under the cursor", lambda: monitor_info())
    check("wallpaper path", wallpaper_path)
    check("Windows accent (registry)", lambda: "#%06x" % (windows_accent_seed() & 0xFFFFFF))
    check("seed colour from the wallpaper", lambda: "#%06x" % (get_seed() & 0xFFFFFF))
    check("palette", lambda: palette(effective=True).acc)
    say()
    say("Other copies and the background helper")
    try:
        pid, born, stamp = open(_PIDFILE, encoding="utf-8").read().split()
        alive = proc_start(pid) == int(born)
        wins = _windows_of(int(pid)) if alive else []
        say(f"  pid file: pid {pid}, {'RUNNING' if alive else 'not running (stale, harmless)'}, started {time.time() - float(stamp):.0f}s ago, windows titled ShellFlow: {wins or 'none'}")
        if alive and not any(v for _, v in wins):
            say("  >> a ShellFlow process is running WITHOUT a visible window. That blocks a new start for up to 45s; it is ended automatically after that.")
    except (OSError, ValueError):
        say("  no pid file (nothing running)")
    say(f"  background helper running: {watcher_running()} (version {watcher_version()}, current {HELPER_VERSION})   autostart entry: {autostart_enabled() if os.name == 'nt' else 'n/a'}")
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            cmd = winreg.QueryValueEx(k, RUN_NAME)[0]
        parts = re.findall(r'"([^"]+)"', cmd)
        say(f"    starts with Windows: {cmd}")
        for p in parts[:2]:
            say(f"      {p}  [{'exists' if os.path.exists(p) else 'MISSING - run: python theme.py setup'}]")
    except Exception:
        say("    starts with Windows: no entry yet (python theme.py setup adds it)")
    on, vol = sound_settings()
    say(f"  sounds {'on' if on else 'OFF'}, volume {vol}%   |   sounds on the YASB bar: {'on' if env('YASB_BAR_SOUNDS') == '1' else 'OFF'}   (program: {env('YASB_BAR_EXE') or 'yasb.exe'})")
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + (env("YASB_BAR_EXE") or "yasb.exe"), "/NH"], capture_output=True, text=True,
                             creationflags=NO_WINDOW).stdout
        say("  " + (env("YASB_BAR_EXE") or "yasb.exe") + (" is running" if "yasb" in out.lower() or (env("YASB_BAR_EXE") or "").lower() in out.lower() else " is NOT running (the click sounds only react to that program; set YASB_BAR_EXE if yours has another name)"))
    except Exception:
        pass
    say()
    say("OBS (only if you use the OBS theme)")
    try:
        obs_user = where("APPDATA") / "obs-studio"
        if not obs_user.is_dir():
            say("  OBS has never run here (no %APPDATA%\\obs-studio): nothing to theme")
        else:
            yami = find_yami()
            say(f"  Yami.obt: {yami or 'NOT FOUND (set YASB_OBS_INSTALL in the .env to your OBS folder)'}")
            if yami:
                text, seen, used = obs_variant(yami.read_text(encoding="utf-8", errors="ignore"), palette())
                say(f"  Yami's colours read: {seen}, recoloured with your accent: {used}")
            ovt = obs_user / "themes" / "Yami_YASB_Accent.ovt"
            say(f"  variant file: {ovt}  [{'exists' if ovt.exists() else 'MISSING: press Apply now in ShellFlow > Templates'}]")
            if ovt.exists():
                head = ovt.read_text(encoding="utf-8").splitlines()[:8]
                say("    " + " | ".join(l.strip() for l in head if l.strip()))
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"], capture_output=True, text=True, creationflags=NO_WINDOW).stdout
            say("  OBS is " + ("RUNNING: close it and open it again, OBS reads themes only at start-up" if "obs64" in out.lower() else "closed") )
            say("  In OBS: Settings > Appearance > Theme = Yami, then Style = YASB Accent")
    except Exception:
        say(f"  FAIL  {traceback.format_exc().strip().splitlines()[-1]}")
    say()
    say("The YASB bar window (ShellFlow attached to the bar takes its width from it)")
    try:
        rects = bar_rects()
        say(f"  bar windows found: {rects if rects else 'none (a bar with width auto then gets the normal ShellFlow width; a % or pixel width is read from config.yaml)'}")
    except Exception:
        say(f"  FAIL  {traceback.format_exc().strip().splitlines()[-1]}")
    say()
    say("Windhawk (only if you use its styler mods)")
    try:
        reg = Registry()
        found = {m: reg.read(m) for m in wh_mods()}
        installed = any(found.values())
        say(f"  Windhawk settings found in the registry: {'yes' if installed else 'no (or they cannot be read)'}")
        left = wh_load_state().get("_skipped", {})
        for m, values in found.items():
            refs = sum(1 for v in values.values() if ACCENT_REF.search(v))
            say(f"    {m}: {len(values)} settings, {refs} still use the Windows accent, {len(wh_load_state().get(m, {}))} are ours, "
                f"{len(left.get(m, []))} left alone because they were changed in Windhawk" + (f" ({', '.join(left[m][:3])}...)" if left.get(m) else ""))
        if "windhawk" not in enabled_apps():
            say("  >> Windhawk is OFF in ShellFlow, so nothing follows your colour scheme. Switch it on: Templates > Windhawk (it writes YASB_APPS to the .env).")
        say(f"  switched on in ShellFlow: {'windhawk' in enabled_apps()}   |   elevated task: {'ready' if wh_task_exists() else 'not set up (Templates > Windhawk > Set up)'}   |   waiting changes: {WH_PENDING.exists()}")
    except Exception:
        say(f"  FAIL  {traceback.format_exc().strip().splitlines()[-1]}")
    say()
    say("Building every ShellFlow page once (nothing is shown)")
    try:
        from .. import settings as s
        root = tk.Tk()
        root.withdraw()
        app = s.App(root)
        for i, (name, *_rest) in enumerate(s.PAGES):
            check(f"page {name}", lambda i=i: (app.go(i), root.update())[0])
        app.closing = True
        root.destroy()
    except Exception:
        say(f"  FAIL  could not build the window: {traceback.format_exc().strip().splitlines()[-1]}")
        say(traceback.format_exc())
    say()
    say("Sounds")
    try:
        from .. import settings as s
        on, vol = s.sound_settings()
        fx = s.Sfx(True, vol)
        fx.play("apply")
        time.sleep(0.9)
        say(f"  click sounds {'on' if on else 'OFF (General > Sounds)'}, volume {vol}%, file {fx.path('apply')}")
        say("  OK    played the done chime - if you heard nothing, raise the volume of 'Python' in the Windows volume mixer"
            if not fx.last_error else f"  FAIL  {fx.last_error}")
    except Exception:
        say(f"  FAIL  {traceback.format_exc().strip().splitlines()[-1]}")
    say()
    if not logs_on():
        say("(diagnostic logs are OFF, so there is no start log. Turn them on in ShellFlow > Backup > Log files, or put YASB_LOGS=1 in the .env, and try again.)")
    for title, path, n in (("shellflow_start.log", _STARTLOG, 14), ("theme_error.log", LOG, 12), ("settings_hang.log", LOGS / "settings_hang.log", 12), ("theme_watch.log", DATA / "theme_watch.log", 6)):
        try:
            tail = open(path, encoding="utf-8", errors="ignore").read().splitlines()[-n:]
            say(f"--- {title} (last {len(tail)} lines)")
            out.extend(tail)
            print("\n".join(tail))
        except OSError:
            say(f"--- {title}: none")
    try:
        (LOGS / "shellflow_doctor.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
        say(f"\nSaved to {LOGS / 'shellflow_doctor.txt'} - send me that file if ShellFlow still does not open.")
    except OSError:
        pass
