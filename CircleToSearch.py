import Config 

import tkinter as tk
from PIL import Image, ImageTk, ImageGrab, ImageEnhance, ImageDraw
import webbrowser
import io
import time
from ctypes import windll
import win32clipboard
import pyautogui
import keyboard
import gc
import threading
import pystray
import os    

# Global flag to control the main loop
APP_RUNNING = True

class CircleToSearch:
    def __init__(self):
        # 1. FIX HIGH DPI SCALING
        try:
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            windll.user32.SetProcessDPIAware()

        self.root = tk.Tk()
        
        # 2. Setup Screen Capture
        self.original_image = ImageGrab.grab(all_screens=True)
        enhancer = ImageEnhance.Brightness(self.original_image)
        self.dark_image = enhancer.enhance(0.4) 
        self.tk_image = ImageTk.PhotoImage(self.dark_image)

        # 3. Setup Fullscreen Window
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(background='black')
        self.root.focus_force()

        # 4. Setup Canvas
        self.canvas = tk.Canvas(self.root, cursor="cross", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")

        self.points = []
        self.selection_rect = None

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", lambda e: self.quit_app())
        self.root.bind("<Button-3>", lambda e: "break") # suppress right click entirely 
        self.root.bind("<ButtonRelease-3>", lambda e: self.quit_app())

    def start(self):
        self.root.mainloop()

    def quit_app(self):
        self.root.destroy()

    def on_button_press(self, event):
        self.points = [(event.x, event.y)]
        # Create the visual feedback box (Cyan, Dashed)
        self.selection_rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#00FFFF", width=2, dash=(4, 4)
        )

    def on_move_press(self, event):
        self.points.append((event.x, event.y))
        
        # Draw the white squiggly line
        if len(self.points) > 1:
            x1, y1 = self.points[-2]
            x2, y2 = self.points[-1]
            self.canvas.create_line(x1, y1, x2, y2, fill="white", width=4, capstyle=tk.ROUND, smooth=True)

        # Update the bounding box
        if self.selection_rect and len(self.points) > 1:
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            self.canvas.coords(self.selection_rect, min(xs), min(ys), max(xs), max(ys))

    def on_button_release(self, event):
        if len(self.points) < 2:
            self.quit_app()
            return

        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        
        box = (
            max(0, min(xs)),
            max(0, min(ys)),
            min(max(xs), self.original_image.width),
            min(max(ys), self.original_image.height)
        )

        cropped_image = self.original_image.crop(box)
        self.quit_app()
        self.automate_google_search(cropped_image)

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
        self.send_to_clipboard(image)
        try:
            webbrowser.register('browsa', None, webbrowser.BackgroundBrowser(Config.BROWSER_PATH))
            webbrowser.get('browsa').open("https://google.com")
        except:
            webbrowser.open("https://google.com")

        time.sleep(Config.BROWSER_LOAD_WAIT_TIME)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        pyautogui.press('enter')

# --- SYSTEM TRAY FUNCTIONS ---

def create_tray_icon():
    # Draw a simple 64x64 blue circle icon in memory
    width = 64
    height = 64
    color = (0, 255, 255) # Cyan
    
    image = Image.new('RGB', (width, height), (0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse((10, 10, 54, 54), fill=color)
    
    return image

def quit_program(icon, item):
    """Callback for the Exit button in the tray."""
    global APP_RUNNING
    icon.stop()
    APP_RUNNING = False
    # Force kill the script because keyboard.wait() blocks the main thread hard
    os._exit(0)

def run_tray_icon():
    """Runs the pystray icon in a background thread."""
    image = create_tray_icon()
    icon = pystray.Icon("CircleSearch", image, "Circle to Search", menu=pystray.Menu(
        pystray.MenuItem("Exit", quit_program)
    ))
    icon.run()

# --- MAIN ---

def main():
    # 1. Start System Tray in a separate thread
    tray_thread = threading.Thread(target=run_tray_icon)
    tray_thread.daemon = True
    tray_thread.start()

    print(f"Circle to Search is running.")
    print(f"Check your system tray to exit.")

    # 2. Main Loop for Hotkey
    while APP_RUNNING:
        try:
            # We use a short timeout loop so we can check APP_RUNNING occasionally
            if keyboard.is_pressed(Config.HOTKEY):
                # Debounce: wait until key is released so we don't trigger 50 times
                while keyboard.is_pressed(Config.HOTKEY):
                    time.sleep(0.1)
                
                # Launch App
                app = CircleToSearch()
                app.start()
                del app
                gc.collect()
            
            time.sleep(0.05) # Low CPU usage wait
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()