"""The Backup page."""
import os
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from ... import api as th
from ..backups import BACKUP_DIR, backup_title, list_backups, log_files, make_backup, old_copies, restore_backup, size_text
from ..constants import CREATE_NO_WINDOW, sound_settings
from ..komorebi import reload_komorebi
from ..state import env_set

class BackupMixin:
    # ---- Backup -----------------------------------------------------------------------------------
    def armed(self, key):
        """A button that asks twice (restore, delete): the first click arms it for a few seconds."""
        return getattr(self, "arm", None) is not None and self.arm[0] == key and time.time() - self.arm[1] < 6

    def confirm(self, key, question):
        """True on the second click within 6 seconds; the first click only asks."""
        if self.armed(key):
            self.arm = None
            return True
        self.arm = (key, time.time())
        self.say(question)
        self.defer_refresh()
        return False

    def do_backup(self):
        try:
            path = make_backup()
            self.say(f"Backed up: {path.name}")
        except OSError as e:
            self.sfx.play("error")
            self.say(f"Could not back up: {e}")
        self.defer_refresh()

    def do_restore(self, path):
        if not self.confirm(("restore", path), "Click Restore again to replace your current files with this backup"):
            return
        try:
            done = restore_backup(path)
        except (OSError, zipfile.BadZipFile) as e:
            self.sfx.play("error")
            return self.say(f"Could not restore: {e}")
        self.quiet_reset = True
        self.reset_all()  # what is on screen now comes from the restored files; anything staged is dropped
        self.quiet_reset = False
        on, vol = sound_settings()
        self.sfx.configure(enabled=on, volume=vol)
        if "komorebi/komorebi.json" in done:
            reload_komorebi()
        self.say(f"Restored {len(done)} files - YASB reloads by itself")

    def do_delete(self, path):
        if self.confirm(("delete", path), "Click Delete again to remove this backup for good"):
            path.unlink(missing_ok=True)
            self.say("Backup deleted")
            self.defer_refresh()

    def do_clear_logs(self):
        for p in log_files():
            try:
                p.unlink()
            except OSError:
                try:
                    p.write_text("", encoding="utf-8")  # a file YASB has open: emptied instead
                except OSError:
                    pass
        self.say("Log files deleted")
        self.defer_refresh()

    def do_report(self):
        """Run `theme.py doctor` (it checks everything and writes shellflow_doctor.txt), then open the report."""
        exe = Path(sys.executable).with_name("python.exe")
        exe = exe if exe.exists() else Path(sys.executable)
        flags = {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}
        box = {}

        def work():
            try:
                subprocess.run([str(exe), str(th.LAUNCHER), "doctor"], capture_output=True, timeout=180, **flags)
            except (OSError, subprocess.SubprocessError):
                pass
            box["done"] = True
        threading.Thread(target=work, daemon=True).start()
        self.say("Writing the report - a few seconds")

        def check():
            if not box.get("done"):
                return self.root.after(400, check)
            report = th.LOGS / "shellflow_doctor.txt"
            self.say("Report saved - opening it" if report.exists() else "The report could not be written")
            if report.exists():
                self.launch(report)
        self.root.after(400, check)

    def page_backup(self):
        f = self.draw_main("Backup", "archive")
        f.note("Backups and logs only happen when you press a button here. ShellFlow never copies or logs things on its own "
               "(errors are the one exception: they are noted in theme_error.log).")
        f.heading("Back up", "archive")
        f.begin_card()
        yc = f.row("Back up now", "config.yaml, styles.css, .env, your edits, notes, komorebi.json and whkdrc, in one zip", glyph="archive")
        f.button(yc, "Back up now", self.do_backup, glyph="archive", primary=True, name="backup_now")
        yc = f.row("Backups folder", str(BACKUP_DIR), glyph="folder")
        f.button(yc, "Open", lambda: (BACKUP_DIR.mkdir(exist_ok=True), self.launch(BACKUP_DIR)), glyph="folder", name="backup_open")
        olds = old_copies()
        if olds:
            yc = f.row("Old automatic copies", ", ".join(p.name for p in olds) + " - older versions made these; nothing uses them", glyph="file")
            f.button(yc, "Delete", lambda: ([p.unlink(missing_ok=True) for p in olds], self.say("Old copies deleted"), self.defer_refresh()),
                     glyph="trash", name="delete_old")
        f.end_card()
        backups = list_backups()
        f.heading(f"Your backups   -   {len(backups)}", "layers")
        if not backups:
            f.note("No backups yet. Press Back up now before a big change.")
        else:
            f.begin_card()
            for path, count, size in backups[:30]:
                yc = f.row(backup_title(path), f"{count} files, {size_text(size)}", glyph="archive")
                x = f.button(yc, "Sure?" if self.armed(("delete", path)) else "Delete", lambda p=path: self.do_delete(p), glyph="trash", name=f"delete:{path.name}")
                f.button(yc, "Click again" if self.armed(("restore", path)) else "Restore", lambda p=path: self.do_restore(p), glyph="reset",
                         primary=self.armed(("restore", path)), x=x - 8, name=f"restore:{path.name}")
            f.end_card()
        f.heading("Log files", "file_text")
        f.begin_card()

        def set_logs(v):
            env_set("YASB_LOGS", "1" if v else "0")
            th.reset_logs_cache()  # this window reads the setting again
            self.say("Log files on" if v else "Log files off (the ones already written stay until you clear them)")
        yc = f.row("Keep log files", "Off: no start or helper logs are written. Turn it on while you track down a problem.", glyph="file_text")
        f.toggle(yc, th.env("YASB_LOGS") == "1", set_logs, name="logs_on")
        for p in log_files():
            yc = f.row(p.name, f"{size_text(p.stat().st_size)}    {p.parent}", glyph="file_text", click=lambda p=p: self.launch(p))
            f.button(yc, "Open", lambda p=p: self.launch(p), glyph="arrow_ur", name=f"log:{p.name}")
        if not log_files():
            f.row("No log files", "Nothing has been written.", glyph="file_text")
        yc = f.row("Diagnostic report", "Checks Python, Windows, YASB, the helper and every page, and saves it as shellflow_doctor.txt", glyph="info")
        f.button(yc, "Create", self.do_report, glyph="pen", name="report")
        if log_files():
            yc = f.row("Clear log files", "Deletes the logs listed above", glyph="trash")
            f.button(yc, "Clear", self.do_clear_logs, glyph="trash", name="logs_clear")
        f.end_card()
        return f
