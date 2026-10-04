"""themes.browsers"""
from ..core import defaults, folders, write_if_changed

def write_browser(P, var, key):
    """Firefox and Zen: yasb-chrome.css (browser UI) and yasb-content.css (about: pages) in each
    profile's chrome folder. userChrome.css / userContent.css are created only if missing; if you
    already have them, add  @import url("yasb-chrome.css");  and  @import url("yasb-content.css");"""
    """Firefox and Zen: yasb-chrome.css (browser UI) and yasb-content.css (about: pages) in each
    profile's chrome folder. userChrome.css / userContent.css are created only if missing."""
    chrome = ":root {\n" + "\n".join(f"    {k}: {v} !important;" for k, v in {
        "--lwt-accent-color": P.t(.07), "--lwt-text-color": P.l3, "--toolbar-bgcolor": P.t(.08),
        "--toolbar-color": P.l3, "--toolbar-field-background-color": P.t(.12),
        "--toolbar-field-color": P.l3, "--toolbar-field-focus-background-color": P.t(.22),
        "--tab-selected-bgcolor": P.t(.35), "--tab-selected-textcolor": P.l3,
        "--arrowpanel-background": P.t(.11), "--arrowpanel-color": P.l3,
        "--arrowpanel-border-color": P.t(.32), "--sidebar-background-color": P.t(.07),
        "--sidebar-text-color": P.l3, "--urlbar-box-bgcolor": P.t(.12),
        "--urlbar-box-hover-bgcolor": P.t(.22), "--zen-primary-color": P.acc,
        "--zen-colors-primary": P.t(.35), "--zen-colors-primary-foreground": P.l3,
        "--zen-colors-secondary": P.t(.12), "--zen-colors-tertiary": P.t(.07),
        "--zen-colors-border": P.t(.32), "--zen-main-browser-background": P.t(.07),
    }.items()) + "\n}\n"
    content = '@-moz-document url-prefix("about:") {\n:root {\n' + "\n".join(f"    {k}: {v} !important;" for k, v in {
        "--in-content-page-background": P.t(.05), "--in-content-page-color": P.l3,
        "--in-content-box-background": P.t(.08), "--in-content-box-border-color": P.t(.32),
        "--in-content-accent-color": P.l1, "--in-content-primary-button-background": P.t(.45),
        "--newtab-background-color": P.t(.05), "--newtab-background-color-secondary": P.t(.08),
        "--newtab-text-primary-color": P.l3,
    }.items()) + "\n}\n}\n"
    for d in folders(var, *defaults(key)):
        write_if_changed(d / "yasb-chrome.css", chrome)
        write_if_changed(d / "yasb-content.css", content)
        for user, ours in (("userChrome.css", "yasb-chrome.css"), ("userContent.css", "yasb-content.css")):
            if not (d / user).exists():
                (d / user).write_text(f'@import url("{ours}");\n', encoding="utf-8")


def write_firefox(P):
    """Firefox.
    Default:  every profile in %APPDATA%/Mozilla/Firefox/Profiles  +  /chrome
    Variable: YASB_FIREFOX_PROFILES (the profile folders)
    Then:     in about:config set toolkit.legacyUserProfileCustomizations.stylesheets to true."""
    write_browser(P, "YASB_FIREFOX_PROFILES", "firefox")


def write_zen(P):
    """Zen Browser.
    Default:  every profile in %APPDATA%/zen/Profiles  +  /chrome
    Variable: YASB_ZEN_PROFILES (the profile folders)
    Then:     restart Zen."""
    write_browser(P, "YASB_ZEN_PROFILES", "zen")
