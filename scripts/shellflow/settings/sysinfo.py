"""Versions and the user name."""
import os
import re
from functools import lru_cache
from .. import api as th
from .komorebi import run_quiet

@lru_cache(maxsize=1)
def yasb_version():
    """The version YASB wrote to its log when it last started."""
    try:
        found = re.findall(r"YASB (v\d[\w.\-]*)", (th.CONFIG / "yasb.log").read_text(encoding="utf-8", errors="ignore"))
        return found[-1] if found else "not in yasb.log yet"
    except OSError:
        return "yasb.log not found"


@lru_cache(maxsize=1)
def komorebi_version():
    out = run_quiet(["komorebic", "--version"], 4).strip().splitlines()
    return out[0] if out else "komorebic not found"


def user_name():
    return th.env("YASB_USERNAME") or os.environ.get("USERNAME") or "You"
