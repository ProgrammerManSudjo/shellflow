"""themes.neovim"""
import json
from ..colors import shade
from ..core import defaults, folders, save

def write_nvim(P):
    """Neovim: yasb.lua, a colour scheme.
    Default:  %LOCALAPPDATA%/nvim/colors
    Variable: YASB_NVIM_COLORS
    Then:     :colorscheme yasb  (put it in init.lua to keep it)."""
    bg, float_bg, sel = P.t(.05), P.t(.11), P.t(.35)
    groups = {
        "Normal": dict(fg=P.l3, bg=bg), "NormalFloat": dict(fg=P.l3, bg=float_bg),
        "FloatBorder": dict(fg=P.t(.5), bg=float_bg), "CursorLine": dict(bg=P.t(.10)),
        "CursorLineNr": dict(fg=P.l1, bold=True), "LineNr": dict(fg=P.t(.75)),
        "SignColumn": dict(bg=bg), "ColorColumn": dict(bg=P.t(.08)), "Visual": dict(bg=sel),
        "Search": dict(fg=bg, bg=P.l2), "IncSearch": dict(fg=bg, bg=P.l1), "CurSearch": dict(fg=bg, bg=P.l1),
        "MatchParen": dict(fg=P.l1, bold=True, underline=True), "Pmenu": dict(fg=P.l3, bg=float_bg),
        "PmenuSel": dict(fg=P.l3, bg=sel), "PmenuSbar": dict(bg=P.t(.22)), "PmenuThumb": dict(bg=P.t(.5)),
        "StatusLine": dict(fg=P.l2, bg=P.t(.12)), "StatusLineNC": dict(fg=P.t(.75), bg=P.t(.08)),
        "WinSeparator": dict(fg=P.t(.22)), "VertSplit": dict(fg=P.t(.22)),
        "TabLine": dict(fg=P.t(.8), bg=P.t(.08)), "TabLineSel": dict(fg=P.l3, bg=sel, bold=True),
        "TabLineFill": dict(bg=P.t(.07)), "Folded": dict(fg=P.t(.8), bg=P.t(.08)),
        "NonText": dict(fg=P.t(.4)), "SpecialKey": dict(fg=P.t(.4)), "Whitespace": dict(fg=P.t(.3)),
        "Directory": dict(fg=P.l1), "Title": dict(fg=P.l1, bold=True), "Question": dict(fg=P.ter(80)),
        "ErrorMsg": dict(fg=P.ansi[0]), "WarningMsg": dict(fg=P.ansi[2]), "MoreMsg": dict(fg=P.ansi[1]),
        "Comment": dict(fg=P.neu(55), italic=True), "Constant": dict(fg=P.ter(70)),
        "String": dict(fg=P.sec(80)), "Character": dict(fg=P.sec(80)), "Number": dict(fg=P.ter(70)),
        "Boolean": dict(fg=P.ter(70)), "Identifier": dict(fg=P.l3), "Function": dict(fg=P.ter(80)),
        "Statement": dict(fg=P.l1), "Keyword": dict(fg=P.l1), "Operator": dict(fg=P.l2),
        "PreProc": dict(fg=P.neu(70)), "Type": dict(fg=P.l2), "Special": dict(fg=P.ter(80)),
        "Delimiter": dict(fg=P.neu(70)), "Underlined": dict(fg=P.l1, underline=True),
        "Error": dict(fg=P.ansi[0]), "Todo": dict(fg=bg, bg=P.l1, bold=True),
        "DiffAdd": dict(bg=shade(P.ansi[1], .30)), "DiffChange": dict(bg=shade(P.ansi[3], .25)),
        "DiffDelete": dict(bg=shade(P.ansi[0], .30)), "DiffText": dict(bg=shade(P.ansi[3], .45)),
        "DiagnosticError": dict(fg=P.ansi[0]), "DiagnosticWarn": dict(fg=P.ansi[2]),
        "DiagnosticInfo": dict(fg=P.ansi[3]), "DiagnosticHint": dict(fg=P.ansi[5]),
    }
    lua = ['vim.cmd("highlight clear")', 'if vim.g.syntax_on then vim.cmd("syntax reset") end',
           'vim.o.background = "dark"', 'vim.g.colors_name = "yasb"']
    for name, style in groups.items():
        lua.append(f'vim.api.nvim_set_hl(0, "{name}", {{ ' +
                   ", ".join(f"{k} = {json.dumps(v)}" for k, v in style.items()) + " })")
    save(folders("YASB_NVIM_COLORS", *defaults("nvim")), "yasb.lua", "\n".join(lua) + "\n")
