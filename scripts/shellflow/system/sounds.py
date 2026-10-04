"""The UI sounds (synthesised: wood, pixel, smooth) and the click sounds on the YASB bar."""
import array
import io
import math
import re
import time
import wave
from ..core import DATA, env
from .winapi import mouse_sample, window_exe_at

# ============================================================================================
#  8a. SOUNDS  (soft Pixel-style UI sounds, synthesised here: no audio files)
#  Used by ShellFlow's window, and by the background helper for clicks on the YASB bar.
# ============================================================================================
try:
    import winsound  # Windows only
except ImportError:
    winsound = None


class Sfx:
    """The UI sounds, synthesised (no audio files), in three styles you pick in ShellFlow > General > Sounds:
      wood    soft low wooden tocks, like the keys of a phone keyboard (the default)
      pixel   the original high, glassy blips
      smooth  rounded sine pops with a soft attack, like the menu sounds of an osu! skin
    Each sound is a small WAV file in scripts/.sounds (the volume is baked in: winsound has no volume control) played with winsound.
    volume is 0..100. A click, a rising pair for on, a falling pair for off, a run of notes for done."""
    # name: [(frequency Hz, length ms, strength 0..1), ...] for each style
    RECIPES_SETS = {
        "wood": {"click": [(240, 50, .95)], "tap": [(180, 44, .85)], "on": [(210, 55, .9), (310, 70, 1.0)],
                 "off": [(310, 50, .85), (210, 65, .85)], "apply": [(200, 55, .85), (250, 55, .9), (330, 110, 1.0)],
                 "reset": [(270, 55, .85), (190, 80, .85)], "error": [(150, 80, .95), (120, 120, .95)]},
        "pixel": {"click": [(1318, 46, .95)], "tap": [(988, 38, .85)], "on": [(880, 56, .95), (1318, 90, 1.0)],
                  "off": [(1318, 48, .9), (880, 84, .9)], "apply": [(784, 70, .95), (988, 70, .95), (1318, 150, 1.0)],
                  "reset": [(660, 62, .9), (494, 100, .9)], "error": [(330, 100, .95), (262, 150, .95)]},
        "smooth": {"click": [(740, 70, .9)], "tap": [(560, 60, .8)], "on": [(620, 70, .85), (930, 110, .9)],
                   "off": [(930, 60, .8), (620, 100, .8)], "apply": [(523, 70, .8), (659, 70, .85), (784, 150, .9)],
                   "reset": [(700, 60, .8), (520, 100, .8)], "error": [(220, 100, .9), (185, 160, .9)]},
    }
    SETS = tuple(RECIPES_SETS)
    RECIPES = RECIPES_SETS["wood"]  # (names of the sounds; every style has the same ones)
    # Pitch variation: every sound also exists a little higher and lower (up to two semitones: a hint of variety, not a different note),
    # and each time one that is not the one just played is chosen. Variant 0 is the sound as written. The error sound never varies.
    PITCHES = (0, 1, -1, 2, -2)
    DIR = DATA / "sounds"

    def __init__(self, enabled=True, volume=10):
        self.enabled, self.volume, self.played, self.last_error = enabled, volume, [], ""
        self.last_variant = {}

    @property
    def style(self):
        """The style in use now (YASB_SOUND_SET in the .env: wood, pixel or smooth). Read every time, so a change applies at once."""
        value = (env("YASB_SOUND_SET") or "wood").strip().lower()
        return value if value in self.SETS else "wood"

    def configure(self, enabled=None, volume=None):
        self.enabled = self.enabled if enabled is None else enabled
        if volume is not None:
            self.volume = max(0, min(100, int(volume)))
            keep = rf"_(?:{'|'.join(self.SETS)})_{self.volume}(_\d+)?$"
            for old in self.DIR.glob("*.wav") if self.DIR.exists() else []:  # sounds made for another volume (or an older version)
                if not re.search(keep, old.stem):
                    try:
                        old.unlink()
                    except OSError:
                        pass

    def render(self, name, variant=0, style=None):
        """The sound as WAV bytes (16 bit mono), `variant` picking one of PITCHES (the same length, higher or lower)."""
        style = style or self.style
        rate, amp = 44100, (self.volume / 100) ** 1.15 * 0.95
        shift = 2 ** (self.PITCHES[variant] / 12) if name != "error" else 1.0
        out = array.array("h")
        import random
        rng = random.Random(7)
        for freq, ms, strength in self.RECIPES_SETS[style][name]:
            freq *= shift
            n = int(rate * ms / 1000)
            if style == "wood":
                low = 0.0
                for i in range(n):
                    t = i / rate
                    # a wooden block: a low body that dies quickly, partials that are not multiples of it (wood), and a dull click of noise at the start
                    body = (math.sin(2 * math.pi * freq * t) * math.exp(-t / 0.016) + 0.45 * math.sin(2 * math.pi * freq * 2.31 * t) * math.exp(-t / 0.007)
                            + 0.2 * math.sin(2 * math.pi * freq * 3.7 * t) * math.exp(-t / 0.004))
                    low += 0.3 * (rng.uniform(-1, 1) - low)  # noise, low-passed: dull, not hissy
                    tick = low * math.exp(-t / 0.0012) * 1.4
                    edge = min(1.0, t / 0.0004) * min(1.0, (n - i) / (rate * 0.003))
                    out.append(int(max(-1.0, min(1.0, (body * 0.8 + tick) * edge * strength * amp)) * 32767))
            elif style == "smooth":
                phase, tau = 0.0, max(0.02, ms / 1000 / 3.8)
                for i in range(n):
                    t = i / rate
                    phase += 2 * math.pi * freq * (1 + 0.08 * math.exp(-t / 0.015)) / rate  # starts a little high and settles: a soft "bloop"
                    rise = min(1.0, t / 0.006)
                    env = (0.5 - 0.5 * math.cos(math.pi * rise)) * math.exp(-t / tau) * min(1.0, (n - i) / (rate * 0.004))  # a rounded attack
                    v = (math.sin(phase) + 0.18 * math.sin(2 * phase) * math.exp(-t / 0.02)) * env * strength * amp
                    out.append(int(max(-1.0, min(1.0, v)) * 32767))
            else:  # pixel
                decay = 4.5 / (ms / 1000)
                for i in range(n):
                    t = i / rate
                    env = min(1.0, t / 0.003) * math.exp(-decay * t)
                    v = math.sin(2 * math.pi * freq * t) + .26 * math.sin(4 * math.pi * freq * t) + .10 * math.sin(6 * math.pi * freq * t)
                    out.append(int(max(-1.0, min(1.0, v * env * strength * amp / 1.25)) * 32767))
            out.extend([0] * int(rate * 0.004))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(out.tobytes())
        return buf.getvalue()

    def path(self, name, variant=0):
        """The file for this sound in the style in use, at the current volume and pitch (made the first time it is needed)."""
        style = self.style
        p = self.DIR / (f"{name}_{style}_{self.volume}.wav" if not variant else f"{name}_{style}_{self.volume}_{variant}.wav")
        if not p.exists():
            self.DIR.mkdir(exist_ok=True)
            p.write_bytes(self.render(name, variant, style))
        return p

    def pick(self, name):
        """Which pitch to play this time: never the one used last for this sound (and always 0 when variation is off)."""
        if name == "error" or env("YASB_SOUND_VARY") == "0":
            return 0
        import random
        choices = [k for k in range(len(self.PITCHES)) if k != self.last_variant.get(name)]
        self.last_variant[name] = random.choice(choices)
        return self.last_variant[name]

    def play(self, name):
        if not name:
            return
        self.played = (self.played + [name])[-30:]
        if not self.enabled or self.volume <= 0 or winsound is None or name not in self.RECIPES:
            return
        try:
            winsound.PlaySound(str(self.path(name, self.pick(name))), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            self.last_error = ""
        except Exception as e:  # remembered, so the Preview button and the doctor can say why nothing is heard
            self.last_error = f"{type(e).__name__}: {e}"


def sound_settings():
    on = env("YASB_SOUNDS") not in ("0", "false", "off")
    try:
        vol = max(0, min(100, int(env("YASB_SOUND_VOLUME") or 10)))
    except ValueError:
        vol = 10
    return on, vol


class BarSounds:
    """A soft tick when you click the YASB bar or one of its menus (any window of yasb.exe). YASB itself has no sounds, so
    this watches the mouse: a new left press plays "click", a right press plays "tap". The sound is the same one ShellFlow's
    buttons use, at the same volume. It cannot tell a widget from the empty part of the bar: both tick."""

    def __init__(self, fx, exe_at=None, sample=None):
        self.fx, self.exe_at, self.sample = fx, exe_at or window_exe_at, sample or mouse_sample
        self.was, self.enabled, self.exe, self.stamp, self.applied = (False, False), True, "yasb.exe", 0.0, None

    def reload(self, force=False):
        """Re-read the settings (the .env) every few seconds, so changes in ShellFlow apply without restarting."""
        if not force and time.time() - self.stamp < 3:
            return
        self.stamp = time.time()
        on, vol = sound_settings()
        self.enabled = on and env("YASB_BAR_SOUNDS") == "1"  # off unless switched on
        self.exe = (env("YASB_BAR_EXE") or "yasb.exe").lower()
        if (on, vol) != self.applied:
            self.applied = (on, vol)
            self.fx.configure(enabled=on, volume=vol)

    def tick(self):
        """One look at the mouse. Returns the sound that was played, if any."""
        left, right, x, y = self.sample()
        new_left, new_right = left and not self.was[0], right and not self.was[1]
        self.was = (left, right)
        if not (new_left or new_right) or not self.enabled:
            return None
        if self.exe_at(x, y) != self.exe:
            return None
        name = "click" if new_left else "tap"
        self.fx.play(name)
        return name

    def run(self):
        for name in ("click", "tap"):  # make the files now, so the first click is not late
            try:
                self.reload(force=True)
                self.fx.path(name)
            except Exception:
                pass
        while True:
            try:
                self.reload()
                self.tick()
            except Exception:
                pass
            time.sleep(0.012)
