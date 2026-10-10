import ctypes
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese.hotkey import ForegroundHotkey

class API:
    pid=42
    keys=set()
    def GetForegroundWindow(self): return 1
    def GetWindowThreadProcessId(self, hwnd, ptr): ptr._obj.value=self.pid
    def GetAsyncKeyState(self, key): return 0x8000 if key in self.keys else 0

class HotkeyTests(unittest.TestCase):
    def test_press_hold_release(self):
        api=API();h=ForegroundHotkey(api,42)
        api.keys={0x11,0x12};self.assertFalse(h.pressed())
        api.keys.add(0x4C);self.assertTrue(h.pressed());self.assertFalse(h.pressed())
        api.keys.clear();self.assertFalse(h.pressed())
        api.keys={0x11,0x12,0x4C};self.assertTrue(h.pressed())
    def test_background_and_focus_held_chord(self):
        api=API();h=ForegroundHotkey(api,42)
        api.pid=99;api.keys={0x11,0x12,0x4C};self.assertFalse(h.pressed())
        api.pid=42;self.assertFalse(h.pressed())
        api.keys=set();self.assertFalse(h.pressed())
        api.keys={0x11,0x12,0x4C};self.assertTrue(h.pressed())
    def test_plain_l_is_not_shortcut(self):
        api=API();h=ForegroundHotkey(api,42);api.keys={0x4C}
        self.assertFalse(h.pressed())

if __name__=='__main__':unittest.main()
