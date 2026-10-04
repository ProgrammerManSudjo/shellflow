"""Springs and fades for the window."""
import math
import time
import tkinter as tk

def spring(t):
    """0..1 -> a value that overshoots by about 13% and settles: the springy "spatial" motion of Material 3 expressive."""
    return 1.0 if t >= 1 else 1 - math.exp(-6.2 * t) * math.cos(9.5 * t)


def soft(t):
    """0..1 -> a gentler spring (overshoot about 3%), for things that should not swing far."""
    return 1.0 if t >= 1 else 1 - math.exp(-7.0 * t) * math.cos(6.0 * t)


def animate(widget, ms, step, done=None):
    """Call step(t) with t going 0 -> 1 over `ms` milliseconds (it follows the clock, so a slow frame does not make it longer).
    Returns a function that stops it. The caller applies spring() or soft() to t."""
    t0, state = time.time(), {"on": True, "job": None}

    def tick():
        if not state["on"]:
            return
        t = min(1.0, (time.time() - t0) * 1000 / ms)
        try:
            step(t)
            if t < 1.0:
                state["job"] = widget.after(14, tick)
            elif done:
                done()
        except tk.TclError:
            state["on"] = False  # the page was redrawn under it
    tick()

    def stop():
        state["on"] = False
        if state["job"]:
            try:
                widget.after_cancel(state["job"])
            except tk.TclError:
                pass
    return stop


def fade(root, start, end, ms=180, done=None):
    """Fade the whole window from alpha `start` to `end` (0..1), then call done(). done() runs even if the fade
    itself fails, so closing can never leave an invisible window behind."""
    steps = max(1, ms // 15)

    def finish():
        if done:
            try:
                done()
            except tk.TclError:
                pass  # already destroyed

    def tick(i=0):
        try:
            root.attributes("-alpha", start + (end - start) * i / steps)
        except tk.TclError:
            return finish()
        if i < steps:
            try:
                root.after(15, lambda: tick(i + 1))
            except tk.TclError:
                return
        else:
            finish()
    tick()
