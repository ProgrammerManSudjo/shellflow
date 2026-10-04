"""themes.obsidian"""
from ..colors import al
from ..core import defaults, folders, save

def write_obsidian(P):
    """Obsidian: yasb-colors.css, a CSS snippet (works on top of any theme). The text you read and write is white; headings,
    bold, links, tags, list markers, quotes and the title bar carry the accent.
    Default:  every vault in %APPDATA%/obsidian/obsidian.json  +  /.obsidian/snippets
    Variable: YASB_OBSIDIAN_VAULTS (the vault folders themselves)
    Then:     Settings > Appearance > CSS snippets > turn on yasb-colors."""
    variables = {
        "--background-primary": P.t(.05), "--background-primary-alt": P.t(.07),
        "--background-secondary": P.t(.07), "--background-secondary-alt": P.t(.09),
        "--background-modifier-border": P.t(.20), "--background-modifier-hover": al(P.l1, .10),
        "--background-modifier-active-hover": al(P.l1, .16), "--background-modifier-form-field": P.t(.12),
        "--text-normal": "#ffffff", "--text-muted": "#bfbfbf", "--text-faint": "#8c8c8c",  # the text itself: white, like Zed
        "--text-accent": P.l1, "--text-accent-hover": P.l2, "--text-selection": al(P.l1, .28),
        "--text-highlight-bg": al(P.l1, .30),
        # titles and a few elements: the accent
        "--h1-color": P.l2, "--h2-color": P.l1, "--h3-color": P.l1, "--h4-color": P.l1, "--h5-color": P.l1, "--h6-color": P.l1,
        "--inline-title-color": P.l2, "--bold-color": P.l2, "--italic-color": "#ffffff",
        "--link-color": P.l1, "--link-color-hover": P.l2, "--link-external-color": P.l1, "--link-unresolved-color": P.d1,
        "--tag-color": P.l1, "--tag-background": al(P.l1, .14), "--tag-background-hover": al(P.l1, .24),
        "--list-marker-color": P.l1, "--blockquote-border-color": P.acc, "--hr-color": P.d1,
        "--code-normal": P.l3, "--code-background": P.t(.12),
        "--checkbox-color": P.acc, "--nav-item-color-active": P.l2, "--nav-item-background-active": al(P.l1, .16),
        "--tab-text-color-focused-active": P.l2, "--tab-text-color-focused-active-current": P.l2,
        "--titlebar-background": P.t(.12), "--titlebar-background-focused": P.t(.16),
        "--titlebar-text-color": P.l1, "--titlebar-text-color-focused": P.l2, "--titlebar-text-color-highlighted": P.l3,
        "--interactive-normal": P.t(.22), "--interactive-hover": P.t(.35),
        "--interactive-accent": P.acc, "--interactive-accent-hover": P.l1,
        "--color-accent": P.acc, "--color-accent-1": P.l1, "--color-accent-2": P.l2,
    }
    body = "\n".join(f"    {k}: {v} !important;" for k, v in variables.items())
    css = f"body.theme-dark,\n.theme-dark {{\n{body}\n}}\n"
    save(folders("YASB_OBSIDIAN_VAULTS", *defaults("obsidian")), "yasb-colors.css", css)
