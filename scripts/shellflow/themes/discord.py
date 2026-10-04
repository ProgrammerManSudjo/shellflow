"""themes.discord"""
from ..colors import al
from ..core import defaults, folders, save

def write_discord(P):
    """Discord (midnight): yasb-colors.theme.css, overriding midnight's colours.
    Default:  %APPDATA%/BetterDiscord, Vencord or Equicord  +  /themes
    Variable: YASB_DISCORD_THEMES
    Then:     enable "yasb-colors" next to "midnight" in the client's theme settings."""
    # backgrounds: the accent over black (35% = the taskbar pills)
    v = {"--bg-1": P.t(.22), "--bg-2": P.t(.35), "--bg-3": P.t(.05), "--bg-4": P.t(.09),
         "--hover": al(P.l1, .12), "--active": al(P.l1, .20), "--active-2": al(P.l1, .30),
         "--button-border": al(P.l3, .12), "--accent-1": P.l3, "--accent-2": P.l2,
         "--accent-3": P.l1, "--accent-4": P.acc, "--accent-5": P.d1}
    body = "\n".join(f"    {k}: {x} !important;" for k, x in v.items())
    controls = f"""
/* window controls, in the accent colours. midnight's own --custom-window-controls setting is left exactly as you have it:
   off = Discord's own buttons (icons tinted below), on = midnight's three dots (coloured by the three variables below) */
[class*="winButtons_"] {{
    --red-2: {P.d1} !important;
    --yellow-2: {P.l1} !important;
    --green-2: {P.l2} !important;
}}
[class*="winButton_"] {{
    color: {P.l1} !important;
}}
[class*="winButton_"]:hover {{
    color: {P.l3} !important;
}}

/* video and clip player: only the seek bar is touched (the accent); the rest of the player is left to Discord and midnight */
[class*="mediaBarProgress_"] {{
    background-color: {P.l1} !important;
}}
[class*="mediaBarGrabber_"] {{
    background-color: {P.l3} !important;
}}
"""
    dirs = folders("YASB_DISCORD_THEMES", *defaults("discord"))
    save(dirs, "yasb-colors.theme.css",
         "/**\n * @name yasb-colors\n * @description Windows accent colour for midnight (written by theme.py)\n"
         " * @author theme.py\n * @version 1.4\n */\n:root {\n" + body + "\n}\n" + controls)
