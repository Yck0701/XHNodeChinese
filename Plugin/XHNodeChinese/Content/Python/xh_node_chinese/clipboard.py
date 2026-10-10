"""Windows clipboard used only by explicit plugin copy/import commands."""
import ctypes
from ctypes import wintypes
import time

def api():
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.OpenClipboard.argtypes = [wintypes.HWND]; user.OpenClipboard.restype = wintypes.BOOL
    user.CloseClipboard.argtypes = []; user.CloseClipboard.restype = wintypes.BOOL
    user.EmptyClipboard.argtypes = []; user.EmptyClipboard.restype = wintypes.BOOL
    user.GetClipboardData.argtypes = [wintypes.UINT]; user.GetClipboardData.restype = wintypes.HANDLE
    user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]; user.SetClipboardData.restype = wintypes.HANDLE
    user.GetActiveWindow.argtypes = []; user.GetActiveWindow.restype = wintypes.HWND
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]; kernel.GlobalAlloc.restype = wintypes.HANDLE
    kernel.GlobalLock.argtypes = [wintypes.HANDLE]; kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HANDLE]; kernel.GlobalUnlock.restype = wintypes.BOOL
    kernel.GlobalSize.argtypes = [wintypes.HANDLE]; kernel.GlobalSize.restype = ctypes.c_size_t
    kernel.GlobalFree.argtypes = [wintypes.HANDLE]; kernel.GlobalFree.restype = wintypes.HANDLE
    for _ in range(3):
        if user.OpenClipboard(user.GetActiveWindow()): return user, kernel
        time.sleep(0.02)
    raise RuntimeError('剪贴板正被其他程序使用，请稍后重试，也可从任务文本文件复制')

def copy(text):
    user, kernel = api()
    handle = None
    try:
        payload = (text+'\0').encode('utf-16-le')
        handle = kernel.GlobalAlloc(0x0002, len(payload))
        if not handle: raise RuntimeError('无法分配剪贴板内存')
        address = kernel.GlobalLock(handle)
        if not address: raise RuntimeError('无法写入剪贴板')
        try: ctypes.memmove(address, payload, len(payload))
        finally: kernel.GlobalUnlock(handle)
        if not user.EmptyClipboard() or not user.SetClipboardData(13, handle): raise RuntimeError('复制失败，请重新复制任务')
        handle = None  # clipboard owns this allocation now
    finally:
        if handle: kernel.GlobalFree(handle)
        user.CloseClipboard()

def paste():
    user, kernel = api()
    try:
        handle = user.GetClipboardData(13)
        if not handle: raise ValueError('剪贴板没有文本，请先复制工具返回的完整 JSON 译文')
        size = kernel.GlobalSize(handle)
        if size > 2000002: raise ValueError('剪贴板文本过大，请只复制当前批次的译文')
        address = kernel.GlobalLock(handle)
        if not address: raise RuntimeError('读取剪贴板失败')
        try: return ctypes.string_at(address, size).decode('utf-16-le').split('\0',1)[0]
        finally: kernel.GlobalUnlock(handle)
    finally: user.CloseClipboard()
