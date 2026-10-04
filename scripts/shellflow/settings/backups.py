"""Backups and log files."""
import re
import time
import zipfile
from .. import api as th
from .constants import CONFIG_YAML, EDITS_JSON, ENV, STYLES
from .keybinds import whkdrc_path
from .komorebi import komorebi_dir

# ============================================================================================
#  BACKUPS and LOG FILES  (only ever done when you press a button on the Backup page)
# ============================================================================================
BACKUP_DIR = th.CONFIG / "backups"


LOG_NAMES = ("theme_error.log", "shellflow_start.log", "theme_watch.log", "settings_hang.log", "shellflow_doctor.txt")


OLD_COPIES = ("config.yaml.bak", "styles.css.bak")  # what older versions copied by themselves


def backup_targets():
    """{name inside the zip: where it lives}: the files that make up your setup."""
    kom = komorebi_dir()
    return {"yasb/config.yaml": CONFIG_YAML, "yasb/styles.css": STYLES, "yasb/.env": ENV, "yasb/theme_colors.css": th.OUT,
            "yasb/notes.json": th.CONFIG / "notes.json", "scripts/settings.json": EDITS_JSON,
            "komorebi/komorebi.json": kom / "komorebi.json", "komorebi/applications.json": kom / "applications.json",
            "whkd/whkdrc": whkdrc_path()}


def make_backup():
    """Zip the files that exist into backups/backup_<date>_<time>.zip. Returns the zip's path."""
    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / time.strftime("backup_%Y-%m-%d_%H-%M-%S.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src in backup_targets().items():
            if src.is_file():
                z.write(src, name)
    return path


def backup_title(path):
    """backup_2026-10-02_15-04-12.zip -> 2026-10-02  15:04:12"""
    m = re.match(r"backup_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})", path.name)
    return f"{m.group(1)}  {m.group(2)}:{m.group(3)}:{m.group(4)}" if m else path.stem


def list_backups():
    """[(path, number of files, size in bytes)], newest first."""
    out = []
    for p in sorted(BACKUP_DIR.glob("backup_*.zip"), reverse=True) if BACKUP_DIR.is_dir() else []:
        try:
            with zipfile.ZipFile(p) as z:
                out.append((p, len(z.namelist()), p.stat().st_size))
        except (OSError, zipfile.BadZipFile):
            out.append((p, 0, 0))
    return out


def restore_backup(path):
    """Put the files of a backup back where they belong. Only the known files are restored, never anything else in the zip.
    Returns the names that were restored."""
    targets, done = backup_targets(), []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name in targets:
                targets[name].parent.mkdir(parents=True, exist_ok=True)
                targets[name].write_bytes(z.read(name))
                done.append(name)
    return done


def log_files():
    """The log files that exist, as paths."""
    mine = [th.LOGS / n for n in LOG_NAMES if (th.LOGS / n).is_file()]
    yasb = th.CONFIG / "yasb.log"  # YASB's own log (it writes it next to config.yaml and cannot be told to write it elsewhere or not at all)
    return mine + ([yasb] if yasb.is_file() else [])


def old_copies():
    return [th.CONFIG / n for n in OLD_COPIES if (th.CONFIG / n).is_file()]


def size_text(n):
    return f"{n / 1024:.1f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"
