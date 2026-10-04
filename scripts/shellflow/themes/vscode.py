"""themes.vscode"""
import json
from ..colors import al
from ..core import defaults, folders, write_if_changed

def write_vscode(P):
    """VS Code: a small theme extension, "YASB Accent" (colours + syntax).
    Default:  %USERPROFILE%/.vscode, .vscode-insiders or .vscode-oss  +  /extensions
    Variable: YASB_VSCODE_EXTENSIONS
    Then:     restart VS Code and pick "YASB Accent" (Reload Window after later changes)."""
    colours = {
        "foreground": P.l3, "descriptionForeground": P.t(.8), "focusBorder": P.acc,
        "editor.background": P.t(.05), "editor.foreground": P.l3,
        "editor.lineHighlightBackground": al(P.l1, .10), "editor.selectionBackground": al(P.l1, .28),
        "editorCursor.foreground": P.l1, "editorLineNumber.foreground": P.t(.75),
        "editorLineNumber.activeForeground": P.l2, "editorWhitespace.foreground": P.t(.30),
        "editorIndentGuide.background1": al(P.l1, .10), "editorIndentGuide.activeBackground1": al(P.l1, .30),
        "editorWidget.background": P.t(.11), "editorSuggestWidget.background": P.t(.11),
        "editorSuggestWidget.selectedBackground": P.t(.35),
        "activityBar.background": P.t(.07), "activityBar.foreground": P.l1,
        "activityBar.inactiveForeground": P.t(.75), "activityBarBadge.background": P.acc,
        "activityBarBadge.foreground": P.t(.05),
        "sideBar.background": P.t(.08), "sideBar.foreground": P.l3, "sideBarTitle.foreground": P.l2,
        "sideBarSectionHeader.background": P.t(.07),
        "titleBar.activeBackground": P.t(.07), "titleBar.activeForeground": P.l3,
        "titleBar.inactiveBackground": P.t(.06),
        "statusBar.background": P.t(.07), "statusBar.foreground": P.l2,
        "statusBar.noFolderBackground": P.t(.07),
        "tab.activeBackground": P.t(.05), "tab.inactiveBackground": P.t(.07),
        "tab.activeForeground": P.l3, "tab.inactiveForeground": P.t(.8),
        "tab.activeBorderTop": P.acc, "editorGroupHeader.tabsBackground": P.t(.07),
        "panel.background": P.t(.05), "panel.border": P.t(.20), "panelTitle.activeForeground": P.l2,
        "terminal.background": P.t(.05), "terminal.foreground": P.l3,
        "button.background": P.t(.35), "button.foreground": P.l3, "button.hoverBackground": P.t(.45),
        "input.background": P.t(.12), "input.foreground": P.l3, "input.border": P.t(.20),
        "dropdown.background": P.t(.12), "badge.background": P.acc, "badge.foreground": P.t(.05),
        "list.activeSelectionBackground": P.t(.35), "list.activeSelectionForeground": P.l3,
        "list.inactiveSelectionBackground": P.t(.22), "list.hoverBackground": P.t(.20),
        "menu.background": P.t(.11), "menu.selectionBackground": P.t(.35),
        "progressBar.background": P.acc, "textLink.foreground": P.l1,
        "scrollbarSlider.background": al(P.l1, .20), "scrollbarSlider.hoverBackground": al(P.l1, .35),
    }
    for i, name in enumerate(("Red", "Green", "Yellow", "Blue", "Magenta", "Cyan")):
        colours[f"terminal.ansi{name}"], colours[f"terminal.ansiBright{name}"] = P.ansi[i], P.bright[i]
    tokens = [(P.neu(55), "italic", "comment"), (P.sec(80), "", "string"),
              (P.ter(70), "", "constant.numeric constant.language constant.character"),
              (P.l1, "", "keyword storage storage.type"), (P.ter(80), "", "entity.name.function support.function"),
              (P.l2, "", "entity.name.type entity.name.class support.type support.class"),
              (P.l3, "", "variable"), (P.sec(70), "", "variable.other.property meta.object-literal.key"),
              (P.l2, "", "keyword.operator"), (P.neu(70), "", "punctuation"),
              (P.l1, "", "entity.name.tag"), (P.ter(80), "", "entity.other.attribute-name")]
    theme = {"name": "YASB Accent", "type": "dark", "colors": colours,
             "tokenColors": [{"scope": s.split(), "settings": {"foreground": c, **({"fontStyle": f} if f else {})}}
                             for c, f, s in tokens]}
    package = {"name": "yasb-accent", "displayName": "YASB Accent", "publisher": "yasb", "version": "1.0.0",
               "engines": {"vscode": "^1.60.0"}, "categories": ["Themes"],
               "contributes": {"themes": [{"label": "YASB Accent", "uiTheme": "vs-dark",
                                           "path": "./themes/yasb-accent-color-theme.json"}]}}
    for d in folders("YASB_VSCODE_EXTENSIONS", *defaults("vscode")):
        (d / "themes").mkdir(exist_ok=True)
        write_if_changed(d / "package.json", json.dumps(package, indent=2))
        write_if_changed(d / "themes" / "yasb-accent-color-theme.json", json.dumps(theme, indent=2))
