"""Windows calls: monitors, the bar window, window owners, DWM effects."""
import ctypes
import time
from ..core import env, log

def mouse_sample():
    """(left button down, right button down, x, y) on screen. Windows only."""
    from ctypes import wintypes
    u = ctypes.windll.user32
    pt = wintypes.POINT()
    u.GetCursorPos(ctypes.byref(pt))
    return bool(u.GetAsyncKeyState(1) & 0x8000), bool(u.GetAsyncKeyState(2) & 0x8000), pt.x, pt.y


_DLLS, _EXE_NAMES = None, {}


def _dlls():
    """Private copies of the Win32 functions with their prototypes set, so the prototypes do not touch the rest of the program."""
    global _DLLS
    if _DLLS is None:
        from ctypes import wintypes
        win = getattr(ctypes, "WinDLL", None)
        u, k = (win("user32"), win("kernel32")) if win else (ctypes.windll.user32, ctypes.windll.kernel32)
        try:
            u.WindowFromPoint.argtypes, u.WindowFromPoint.restype = [wintypes.POINT], ctypes.c_void_p
            u.GetAncestor.argtypes, u.GetAncestor.restype = [ctypes.c_void_p, ctypes.c_uint], ctypes.c_void_p
            u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            u.IsWindowVisible.argtypes = [ctypes.c_void_p]
            u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
            k.OpenProcess.argtypes, k.OpenProcess.restype = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong], ctypes.c_void_p
            k.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
            k.CloseHandle.argtypes = [ctypes.c_void_p]
        except (AttributeError, TypeError):
            pass
        _DLLS = (u, k)
    return _DLLS


def exe_of_pid(pid):
    """The program (lower-case file name, e.g. "yasb.exe") a process is running, or "". Remembered for 30 s. Windows only."""
    known = _EXE_NAMES.get(pid)
    if known and time.time() - known[1] < 30:
        return known[0]
    _, k = _dlls()
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    buf, size = ctypes.create_unicode_buffer(520), ctypes.c_ulong(520)
    ok = k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    k.CloseHandle(h)
    name = buf.value.replace("\\", "/").rsplit("/", 1)[-1].lower() if ok else ""
    _EXE_NAMES[pid] = (name, time.time())
    return name


def window_exe_at(x, y):
    """The program (lower-case file name, e.g. "yasb.exe") that owns the window under a screen point, or "". Windows only."""
    try:
        from ctypes import wintypes
        u, _ = _dlls()
        hwnd = u.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        if not hwnd:
            return ""
        top = u.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT: the program's top-level window (the bar, or a menu of it)
        pid = ctypes.c_ulong()
        u.GetWindowThreadProcessId(top, ctypes.byref(pid))
        return exe_of_pid(pid.value)
    except Exception:
        return ""


def window_shadow(root, on):
    """Switch Windows' drop shadow of a window on or off (an attached window must not have a dark band of shadow below it).
    DWMWA_NCRENDERING_POLICY: 1 = no frame rendering, no shadow; 0 = the window's own style."""
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 2, ctypes.byref(ctypes.c_int(0 if on else 1)), 4)
    except Exception:
        pass


def bar_pill_edge(rect, edge, expected, colour=(0, 0, 0)):
    """The y of the visible bar's edge that a window attached to it should touch, read off the screen: the first row below a top bar (above
    a bottom bar). The window rectangle Windows reports includes margins, and the capsules end a few pixels above the bar's own edge, so
    the edge is looked for in the pixels around `expected` (+-14): the bar is `colour` (black), the desktop is not. None if it cannot tell."""
    try:
        from PIL import ImageGrab
        l, t, r, b = rect
        lo, hi = expected - 14, expected + 14
        img = ImageGrab.grab(bbox=(l, lo, r, hi), all_screens=True).convert("RGB")
        w, h = img.size
        px = img.load()
        bar = lambda c: max(abs(c[i] - colour[i]) for i in range(3)) <= 12
        votes = {}
        for x in range(24, w - 24, 5):  # (not the rounded ends)
            rows = range(h - 2) if edge == "top" else range(h - 1, 1, -1)
            for y in rows:
                nxt = (1, 2) if edge == "top" else (-1, -2)
                if bar(px[x, y]) and all(not bar(px[x, y + d]) for d in nxt):
                    votes[lo + y + 1 if edge == "top" else lo + y] = votes.get(lo + y + 1 if edge == "top" else lo + y, 0) + 1
                    break
        best = max(votes, key=votes.get) if votes else None
        return best if best is not None and votes[best] >= 3 else None
    except Exception:
        return None


def pick_bars(windows, exe):
    """From [(visible, (left, top, right, bottom), program)] the rectangles of the bars: visible windows of `exe` that are strips (wide,
    and not tall: a menu or a preview is taller)."""
    return [r for visible, r, program in windows if visible and program == exe and r[2] - r[0] > 300 and 20 < r[3] - r[1] < 200]


def bar_rects(exe=None, windows=None):
    """The rectangles (left, top, right, bottom) of the YASB bar windows on screen right now, asked of Windows (every top-level window and
    the program it belongs to, not what is under one point). [] if none is found. `windows` replaces the asking (for tests)."""
    exe = (exe or env("YASB_BAR_EXE") or "yasb.exe").lower()
    if windows is None:
        windows = []
        try:
            from ctypes import wintypes
            u, _ = _dlls()
            proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def each(hwnd, _):
                r, pid, seen = wintypes.RECT(), ctypes.c_ulong(), wintypes.RECT()
                u.GetWindowRect(hwnd, ctypes.byref(r))
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:  # what you can SEE of the window: GetWindowRect also counts the invisible resize borders and shadow margins
                    if ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), 9, ctypes.byref(seen), ctypes.sizeof(seen)) == 0:  # DWMWA_EXTENDED_FRAME_BOUNDS
                        r = seen
                except Exception:
                    pass
                windows.append((bool(u.IsWindowVisible(hwnd)), (r.left, r.top, r.right, r.bottom), exe_of_pid(pid.value)))
                return True
            u.EnumWindows(proc(each), 0)
        except Exception:
            log("bar_rects")
            return []
    return pick_bars(windows, exe)


def wallpaper_path():
    buf = ctypes.create_unicode_buffer(520)
    ctypes.windll.user32.SystemParametersInfoW(0x73, 520, buf, 0)  # SPI_GETDESKWALLPAPER
    return buf.value


def make_dpi_aware():
    """Draw sharply on scaled displays."""
    ctypes.windll.shcore.SetProcessDpiAwareness(2)


def monitor_info():
    """(work area, dpi scale) of the monitor under the cursor."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    mon = user32.MonitorFromPoint(pt, 2)  # nearest monitor
    mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(mon, ctypes.byref(mi))
    dpi = ctypes.c_uint()
    ctypes.windll.shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dpi), ctypes.byref(ctypes.c_uint()))
    w = mi.rcWork
    return (w.left, w.top, w.right, w.bottom), dpi.value / 96


def round_window(root):
    """Windows 11 rounded corners, no border (cosmetic, ignored where unsupported)."""
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(ctypes.c_uint(0xFFFFFFFE)), 4)
    except Exception:
        pass
