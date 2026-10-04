"""themes.tacky"""
import re
from ..core import defaults, folders, write_if_changed

def write_tacky(P):
    """Tacky Borders: sets global.active_color in config.yaml to the main accent colour.
    Default:  %USERPROFILE%/.config/tacky-borders  (config.yaml must exist; it is never created)
    Variable: YASB_TACKY_CONFIG
    Then:     nothing - Tacky Borders reloads its config by itself."""
    done = False
    for d in folders("YASB_TACKY_CONFIG", *defaults("tacky")):
        cfg = d / "config.yaml"
        if not cfg.exists():
            continue
        lines = cfg.read_text(encoding="utf-8").split("\n")
        g = next((i for i, l in enumerate(lines) if re.match(r"^global:\s*(#.*)?$", l)), None)
        if g is None:
            raise ValueError("no global: section in " + str(cfg))
        end = next((j for j in range(g + 1, len(lines)) if lines[j].strip() and not lines[j].startswith((" ", "\t", "#"))), len(lines))
        for i in range(g + 1, end):
            m = re.match(r"^(\s+active_color:\s*)(.*?)(\s+#.*)?$", lines[i])
            if m:
                if not m.group(2) or m.group(2).startswith(("{", "[", "|", ">")):
                    raise ValueError("active_color is a gradient/mapping, not a single colour: left alone")
                lines[i] = f'{m.group(1)}"{P.acc}"{m.group(3) or ""}'
                write_if_changed(cfg, "\n".join(lines))
                done = True
                break
        else:
            raise ValueError("no active_color under global: in " + str(cfg))
    return done
