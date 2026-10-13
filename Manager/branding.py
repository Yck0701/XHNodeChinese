"""One visual identity for Explorer, the taskbar, dialogs and the header."""
import ctypes
import os
from pathlib import Path
import tkinter as tk

ASSETS = Path(__file__).resolve().parent / 'assets'
APP_ID = 'XHNodeChinese.TranslationManager'


def set_process_identity():
    # Set before Tk creates a window so Windows does not group us with Python.
    if os.name == 'nt':
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError):
            pass


def set_window_icon(app):
    # Keep references: Tk image objects are released when Python collects them.
    images = []
    for size in (16, 32, 48, 256):
        try:
            images.append(tk.PhotoImage(master=app, file=str(ASSETS/f'translate-{size}.png')))
        except tk.TclError:
            pass
    app._brand_icons = images
    if images:
        app.iconphoto(True, *images)
    ico = ASSETS / 'translate.ico'
    if os.name == 'nt' and ico.is_file():
        app.iconbitmap(default=str(ico))


def logo(parent, background):
    canvas = tk.Canvas(parent, width=64, height=64, bg=background, highlightthickness=0)
    try:
        canvas._brand_image = tk.PhotoImage(master=canvas, file=str(ASSETS/'translate-64.png'))
        canvas.create_image(32, 32, image=canvas._brand_image)
    except tk.TclError:
        canvas.create_rectangle(3, 3, 43, 43, fill='#55dcf4', outline='')
        canvas.create_text(20, 20, text='U', fill='#102239', font=('Segoe UI', 24, 'bold'))
        canvas.create_rectangle(26, 28, 60, 60, fill='#8aafff', outline=background, width=2)
        canvas.create_text(43, 43, text='文', fill='#102239', font=('Microsoft YaHei UI', 18, 'bold'))
    return canvas
