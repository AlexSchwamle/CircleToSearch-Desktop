import Config 

import tkinter as tk
from PIL import Image, ImageTk, ImageGrab, ImageEnhance, ImageDraw
import webbrowser
import io
import time
from ctypes import windll, wintypes, byref, Structure, POINTER, c_int
import ctypes
import win32clipboard
import pyautogui
import keyboard
import gc
import threading
import pystray
import os    

# Global flag to control the main loop
APP_RUNNING = True


# ---------------------------------------------------------------------------
# Multi-monitor helpers
# ---------------------------------------------------------------------------

class RECT(Structure):
    _fields_ = [("left", c_int), ("top", c_int), ("right", c_int), ("bottom", c_int)]

def get_all_monitors():
    """
    Return a list of dicts describing each monitor:
        { 'left': int, 'top': int, 'width': int, 'height': int }
    Coordinates are in *virtual-desktop* space (can be negative for monitors
    left-of / above the primary).
    """
    monitors = []

    def _callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        r = lprcMonitor.contents
        monitors.append({
            'left':   r.left,
            'top':    r.top,
            'width':  r.right  - r.left,
            'height': r.bottom - r.top,
        })
        return True  # continue enumeration

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_ulong,   # HMONITOR
        ctypes.c_ulong,   # HDC
        POINTER(RECT),    # LPRECT
        ctypes.c_double,  # LPARAM
    )
    callback = MonitorEnumProc(_callback)
    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback, 0)
    return monitors

def get_virtual_desktop_rect():
    """
    Return (left, top, width, height) of the bounding box that covers
    every monitor – i.e. the full virtual desktop.
    """
    mons = get_all_monitors()
    if not mons:
        # Fallback: single-monitor via GetSystemMetrics
        return (0, 0,
                ctypes.windll.user32.GetSystemMetrics(0),
                ctypes.windll.user32.GetSystemMetrics(1))

    min_x = min(m['left'] for m in mons)
    min_y = min(m['top']  for m in mons)
    max_x = max(m['left'] + m['width']  for m in mons)
    max_y = max(m['top']  + m['height'] for m in mons)
    return (min_x, min_y, max_x - min_x, max_y - min_y)


class CircleToSearch:
    def __init__(self):
        # 1. FIX HIGH DPI SCALING - Use per-monitor awareness (2) so
        #    EnumDisplayMonitors returns real pixel coordinates that match
        #    the screenshot, even when monitors have different scale %.
        try:
            windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                windll.user32.SetProcessDPIAware()

        self.root = tk.Tk()
        
        # 2. Get virtual desktop bounds and capture ALL monitors
        vd_left, vd_top, vd_w, vd_h = get_virtual_desktop_rect()
        self.vd_left = vd_left
        self.vd_top  = vd_top

        self.original_image = ImageGrab.grab(
            bbox=(vd_left, vd_top, vd_left + vd_w, vd_top + vd_h),
            all_screens=True,
        )
        enhancer = ImageEnhance.Brightness(self.original_image)
        self.dark_image = enhancer.enhance(0.4) 
        self.tk_image = ImageTk.PhotoImage(self.dark_image)

        # 3. Fullscreen window that spans ALL monitors
        self.root.overrideredirect(True)
        self.root.geometry(f"{vd_w}x{vd_h}+{vd_left}+{vd_top}")
        self.root.attributes('-topmost', True)
        self.root.configure(background='black')
        self.root.update_idletasks()

        # Force the window to cover the full virtual desktop via Win32 API,
        # because Tk may silently clamp geometry to the primary monitor.
        hwnd = windll.user32.GetParent(self.root.winfo_id())
        SWP_NOZORDER = 0x0004
        windll.user32.SetWindowPos(hwnd, None, vd_left, vd_top, vd_w, vd_h, SWP_NOZORDER)

        self.root.focus_force()

        # 4. Setup Canvas
        self.canvas = tk.Canvas(self.root, cursor="cross", highlightthickness=0)
        self.canvas.configure(scrollregion=(0, 0, vd_w, vd_h))
        self.canvas.pack(fill="both", expand=True)
        # Store background ID so we can stack things above it if needed
        self.bg_id = self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")

        # 5. BOX mode vars
        self.starting_x, self.starting_y = None, None

        # --- MODE SWITCHING SETUP ---
        self.modes = list(Config.SEARCH_MODES.keys())
        self.urls  = list(Config.SEARCH_MODES.values())
        self.current_mode_index = 0
        self.hide_timer = None

        # Build per-monitor label overlay windows (Toplevel) because Tk's
        # canvas silently stops rendering items beyond ~4096px.
        monitors = get_all_monitors()
        if not monitors:
            monitors = [{'left': 0, 'top': 0, 'width': vd_w, 'height': vd_h}]

        self.label_overlays = []  # list of { 'win': Toplevel, 'label': Label, 'cx': int, 'cy': int }
        for m in monitors:
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes('-topmost', True)
            win.attributes('-transparentcolor', 'black')
            win.configure(background='black')
            
            lbl = tk.Label(win, text=self.modes[self.current_mode_index],
                           font=("Segoe UI", 24, "bold"), fg=Config.TEXT_COLOR,
                           bg='black')
            lbl.pack()

            # Position: centered horizontally on this monitor, 30px from top
            label_w = 400  # generous width for text
            label_h = 60
            cx = m['left'] + m['width'] // 2 - label_w // 2
            cy = m['top'] + 30
            win.geometry(f"{label_w}x{label_h}+{cx}+{cy}")

            self.label_overlays.append({
                'win': win, 'label': lbl,
                'mon_cx': m['left'] + m['width'] // 2,
                'mon_top': m['top'],
                'label_w': label_w, 'label_h': label_h,
            })

        self.reset_hide_timer()

        self.points        = []
        self.selection_rect = None
        self.highlight_id  = -1
        self.tk_highlight  = None

        # Bindings
        self.canvas.bind("<ButtonPress-1>",   self.on_button_press)
        self.canvas.bind("<B1-Motion>",        self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>",  self.on_button_release)
        self.root.bind("<Escape>",             lambda e: self.quit_app())
        self.root.bind("<MouseWheel>",         self.on_scroll)
        self.root.bind("<Button-3>",           lambda e: "break")
        self.root.bind("<ButtonRelease-3>",    lambda e: self.quit_app())

    def start(self):
        self.root.mainloop()

    def quit_app(self):
        for ov in self.label_overlays:
            ov['win'].destroy()
        self.root.destroy()

    # --- MODE SWITCHING & ANIMATION ---

    def show_mode_label(self):
        text = self.modes[self.current_mode_index]
        for ov in self.label_overlays:
            ov['label'].config(text=text)
            ov['win'].deiconify()
        self.reset_hide_timer()

    def reset_hide_timer(self):
        if self.hide_timer:
            self.root.after_cancel(self.hide_timer)
        self.hide_timer = self.root.after(2000, self.hide_label)

    def hide_label(self):
        for ov in self.label_overlays:
            ov['win'].withdraw()

    def on_scroll(self, event):
        self.reset_hide_timer()
        direction = 1 if event.delta > 0 else -1
        self.current_mode_index = (self.current_mode_index - direction) % len(self.modes)
        self.animate_roulette(self.current_mode_index, direction)

    def animate_roulette(self, new_idx, direction):
        new_text = self.modes[new_idx]
        offset = 80 * direction
        steps = 10
        delay = 5

        # Ensure overlays are visible
        for ov in self.label_overlays:
            ov['win'].deiconify()

        def step_anim(step=0):
            if step > steps:
                # Settle at final position with new text
                for ov in self.label_overlays:
                    ov['label'].config(text=new_text)
                    final_x = ov['mon_cx'] - ov['label_w'] // 2
                    final_y = ov['mon_top'] + 30
                    ov['win'].geometry(f"+{final_x}+{final_y}")
                return
            t = step / steps
            # Slide the label upward/downward
            for ov in self.label_overlays:
                shift = int(-offset * t)
                x = ov['mon_cx'] - ov['label_w'] // 2
                y = ov['mon_top'] + 30 + shift
                ov['win'].geometry(f"+{x}+{y}")
            self.root.after(delay, lambda: step_anim(step + 1))

        step_anim()
        # Update text partway (swap at the midpoint)
        def swap_text():
            for ov in self.label_overlays:
                ov['label'].config(text=new_text)
        self.root.after(delay * steps // 2, swap_text)

    # --- DRAWING LOGIC ---

    def on_button_press(self, event):
        self.points = [(event.x, event.y)]
        self.highlight_id = self.canvas.create_image(event.x, event.y, anchor="nw")
        self.selection_rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline=Config.BOX_COLOR, width=2, dash=(4, 4),
        )
        self.starting_x, self.starting_y = event.x, event.y

    def on_move_press(self, event):
        if self.selection_rect is None or self.starting_x is None:
            return

        if Config.MODE.upper() == "BOX":
            cur_x, cur_y = event.x, event.y
            min_x = min(self.starting_x, cur_x)
            min_y = min(self.starting_y, cur_y)
            max_x = max(self.starting_x, cur_x)
            max_y = max(self.starting_y, cur_y)
            self.points = [(min_x, min_y), (max_x, max_y)]
        else:  # CIRCLE mode
            self.points.append((event.x, event.y))
            if len(self.points) > 1:
                x1, y1 = self.points[-2]
                x2, y2 = self.points[-1]
                self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill="white", width=4, capstyle=tk.ROUND, smooth=True,
                )
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            min_x, min_y = min(xs), min(ys)
            max_x, max_y = max(xs), max(ys)

        self.canvas.coords(self.selection_rect, min_x, min_y, max_x, max_y)

        if max_x <= min_x or max_y <= min_y:
            return

        crop = self.original_image.crop((min_x, min_y, max_x, max_y))
        self.tk_highlight = ImageTk.PhotoImage(crop)
        self.canvas.itemconfig(self.highlight_id, image=self.tk_highlight)
        self.canvas.coords(self.highlight_id, min_x, min_y)

    def on_button_release(self, event):
        if len(self.points) < 2:
            self.quit_app()
            return

        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]

        # Canvas coords map 1-to-1 to the screenshot pixels because the
        # screenshot was taken with the same virtual-desktop origin.
        box = (
            max(0, min(xs)),
            max(0, min(ys)),
            min(max(xs), self.original_image.width),
            min(max(ys), self.original_image.height),
        )

        cropped_image = self.original_image.crop(box)
        self.quit_app()
        self.automate_google_search(cropped_image)

    # --- CLIPBOARD & SEARCH ---

    def send_to_clipboard(self, image):
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()

        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()
        except Exception as e:
            print(f"Clipboard error: {e}")

    def automate_google_search(self, image):
        target_url = self.urls[self.current_mode_index]
        
        self.send_to_clipboard(image)
        webbrowser.open(target_url)

        time.sleep(Config.BROWSER_LOAD_WAIT_TIME)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        pyautogui.press('enter')


# ---------------------------------------------------------------------------
# System Tray
# ---------------------------------------------------------------------------

def create_tray_icon():
    width, height = 64, 64
    color = (66, 135, 244)
    image = Image.new('RGB', (width, height), (0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse((10, 10, 54, 54), fill=color)
    return image

def quit_program(icon, item):
    global APP_RUNNING
    icon.stop()
    APP_RUNNING = False
    os._exit(0)

def run_tray_icon():
    image = create_tray_icon()
    icon  = pystray.Icon(
        "CircleSearch", image, "Circle to Search",
        menu=pystray.Menu(pystray.MenuItem("Exit", quit_program)),
    )
    icon.run()

def display_user_error(message):
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Circle to Search - Error", message)
    root.destroy()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if Config.MODE not in ("BOX", "CIRCLE"):
        display_user_error(
            f"Error: Invalid MODE '{Config.MODE}' in Config.py. Must be 'BOX' or 'CIRCLE'."
        )
        exit(1)

    tray_thread = threading.Thread(target=run_tray_icon)
    tray_thread.daemon = True
    tray_thread.start()

    print("Circle to Search is running.")
    print("Check your system tray to exit.")

    while APP_RUNNING:
        try:
            if keyboard.is_pressed(Config.HOTKEY):
                while keyboard.is_pressed(Config.HOTKEY):
                    time.sleep(0.1)

                app = CircleToSearch()
                app.start()
                del app
                gc.collect()

            time.sleep(0.05)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()