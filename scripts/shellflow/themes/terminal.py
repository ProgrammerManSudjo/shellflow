"""themes.terminal"""
import json
from ..core import defaults, folders, save

def write_wt(P):
    """Windows Terminal: a JSON fragment with the colour scheme "YASB Accent".
    Default:  %LOCALAPPDATA%/Microsoft/Windows Terminal/Fragments/yasb  (Store, Preview or unpackaged)
    Variable: YASB_WT_FRAGMENTS
    Then:     pick "YASB Accent" under a profile's Appearance settings."""
    names = ("red", "green", "yellow", "blue", "purple", "cyan")
    scheme_ = {"name": "YASB Accent", "background": P.t(.05), "foreground": P.l3, "cursorColor": P.l1,
               "selectionBackground": P.t(.35), "black": P.t(.12), "white": P.neu(80),
               "brightBlack": P.neu(40), "brightWhite": P.neu(95)}
    for i, n in enumerate(names):
        scheme_[n], scheme_["bright" + n.capitalize()] = P.ansi[i], P.bright[i]
    save(folders("YASB_WT_FRAGMENTS", *defaults("wt")), "yasb-accent.json",
         json.dumps({"schemes": [scheme_]}, indent=2))
