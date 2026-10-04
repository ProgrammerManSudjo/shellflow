"""themes.yazi"""
from ..core import defaults, folders, save

# one icon per kind of file, all white. Font Awesome and Devicons glyphs, which every Nerd Font has.
YAZI_ICON_EXTS = {
    "md": "\ue73e", "markdown": "\ue73e", "json": "\ue60b", "js": "\ue74e", "mjs": "\ue74e", "ts": "\ue628", "tsx": "\ue7ba", "jsx": "\ue7ba",
    "py": "\ue73c", "rs": "\ue7a8", "go": "\ue627", "c": "\ue61e", "cpp": "\ue61d", "cs": "\uf81a", "java": "\ue738", "lua": "\ue620",
    "html": "\ue736", "css": "\ue749", "scss": "\ue749", "sh": "\uf489", "bash": "\uf489", "ps1": "\uf489", "bat": "\uf489", "cmd": "\uf489",
    "toml": "\ue615", "yaml": "\ue615", "yml": "\ue615", "ini": "\ue615", "conf": "\ue615", "cfg": "\ue615", "env": "\ue615",
    "txt": "\uf0f6", "log": "\uf0f6", "pdf": "\uf1c1", "doc": "\uf1c2", "docx": "\uf1c2", "xls": "\uf1c3", "xlsx": "\uf1c3", "csv": "\uf1c3",
    "ppt": "\uf1c4", "pptx": "\uf1c4", "zip": "\uf1c6", "7z": "\uf1c6", "rar": "\uf1c6", "tar": "\uf1c6", "gz": "\uf1c6",
    "png": "\uf1c5", "jpg": "\uf1c5", "jpeg": "\uf1c5", "gif": "\uf1c5", "webp": "\uf1c5", "bmp": "\uf1c5", "svg": "\uf1c5", "ico": "\uf1c5",
    "mp3": "\uf1c7", "wav": "\uf1c7", "flac": "\uf1c7", "ogg": "\uf1c7", "m4a": "\uf1c7",
    "mp4": "\uf1c8", "mkv": "\uf1c8", "avi": "\uf1c8", "mov": "\uf1c8", "webm": "\uf1c8",
    "exe": "\uf17a", "msi": "\uf17a", "dll": "\uf17a", "lnk": "\uf0c1", "iso": "\uf0a0",
}


def yazi_icons(colour="#ffffff"):
    """The [icon] section of the flavor: dirs, files and exts replace Yazi's own lists, so every icon is `colour`."""
    row = lambda name, glyph: f'    {{ name = "{name}", text = "{glyph}", fg = "{colour}" }},'
    cond = lambda test, glyph: f'    {{ if = "{test}", text = "{glyph}", fg = "{colour}" }},'
    lines = ["[icon]", "globs = []", "dirs = [", row(".git", "\ue5fb"), row(".config", "\ue5fc"), row("node_modules", "\ue5fa"), "]",
             "files = [", row(".gitignore", "\ue702"), row(".gitconfig", "\ue702"), row("Dockerfile", "\ue7b0"), row("LICENSE", "\uf0f6"), "]",
             "exts = [", *[row(ext, glyph) for ext, glyph in YAZI_ICON_EXTS.items()], "]",
             "conds = [", cond("orphan", "\uf127"), cond("link", "\uf0c1"), cond("hidden & dir", "\uf07b"), cond("dir", "\uf07b"),
             cond("exec", "\uf085"), cond("!(dir | link)", "\uf15b"), "]"]
    return "\n".join(lines)


def write_yazi(P):
    """Yazi: the flavor "yasb-accent" (flavor.toml). A theme.toml selecting it is created only if missing.
    Default:  %APPDATA%/yazi/config/flavors  +  /yasb-accent.yazi
    Variable: YASB_YAZI_FLAVORS
    Then:     if you have your own theme.toml, set  [flavor] dark = "yasb-accent"  in it."""
    q = lambda c: f'"{c}"'
    ed = P.t(.05)
    toml = f"""[mgr]
cwd = {{ fg = {q(P.l1)} }}
hovered = {{ fg = {q(ed)}, bg = {q(P.l1)} }}
preview_hovered = {{ underline = true }}
find_keyword = {{ fg = {q(P.ter(80))}, bold = true, italic = true, underline = true }}
find_position = {{ fg = {q(P.ter(80))}, bold = true, italic = true }}
symlink_target = {{ italic = true }}
marker_copied = {{ fg = {q(ed)}, bg = {q(P.ansi[1])} }}
marker_cut = {{ fg = {q(ed)}, bg = {q(P.ansi[0])} }}
marker_marked = {{ fg = {q(ed)}, bg = {q(P.sec(80))} }}
marker_selected = {{ fg = {q(ed)}, bg = {q(P.l1)} }}
count_copied = {{ fg = {q(ed)}, bg = {q(P.ansi[1])} }}
count_cut = {{ fg = {q(ed)}, bg = {q(P.ansi[0])} }}
count_selected = {{ fg = {q(ed)}, bg = {q(P.l1)} }}

[filetype]
prepend_rules = [
    {{ url = "*/", fg = "#ffffff" }},
]

{yazi_icons()}

[tabs]
active = {{ fg = {q(ed)}, bg = {q(P.l1)}, bold = true }}
inactive = {{ fg = {q(P.l1)}, bg = {q(P.t(.12))} }}

[mode]
normal_main = {{ fg = {q(ed)}, bg = {q(P.l1)}, bold = true }}
normal_alt = {{ fg = {q(P.l1)}, bg = {q(P.t(.22))} }}
select_main = {{ fg = {q(ed)}, bg = {q(P.ter(80))}, bold = true }}
select_alt = {{ fg = {q(P.ter(80))}, bg = {q(P.t(.22))} }}
unset_main = {{ fg = {q(ed)}, bg = {q(P.ansi[0])}, bold = true }}
unset_alt = {{ fg = {q(P.ansi[0])}, bg = {q(P.t(.22))} }}
"""
    dirs = folders("YASB_YAZI_FLAVORS", *defaults("yazi"))
    save(dirs, "flavor.toml", toml)
    for d in dirs:  # select the flavor, unless there already is a theme.toml
        theme = d.parent.parent / "theme.toml"
        if not theme.exists():
            theme.write_text('[flavor]\ndark = "yasb-accent"\nlight = "yasb-accent"\n', encoding="utf-8")
