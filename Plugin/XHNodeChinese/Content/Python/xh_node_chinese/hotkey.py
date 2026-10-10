"""An edge-triggered shortcut restricted to the current editor process."""
import ctypes
import os


class ForegroundHotkey:
    def __init__(self, user32=None, pid=None):
        self._down = False
        self.pid = os.getpid() if pid is None else pid
        self.api = user32
        if self.api is None and os.name == 'nt':
            from ctypes import wintypes
            self.api = ctypes.WinDLL('user32', use_last_error=True)
            self.api.GetForegroundWindow.restype = wintypes.HWND
            self.api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            self.api.GetAsyncKeyState.argtypes = [ctypes.c_int]
            self.api.GetAsyncKeyState.restype = ctypes.c_short

    def pressed(self):
        if self.api is None:
            return False
        from ctypes import wintypes
        pid = wintypes.DWORD()
        self.api.GetWindowThreadProcessId(self.api.GetForegroundWindow(), ctypes.byref(pid))
        # Always track the chord, even while unfocused, so focusing a held chord
        # cannot fire it. Ignore autorepeat and require release before another press.
        down = all(self.api.GetAsyncKeyState(k) & 0x8000 for k in (0x11, 0x12, 0x4C))
        fire = down and not self._down and pid.value == self.pid
        self._down = down
        return fire
