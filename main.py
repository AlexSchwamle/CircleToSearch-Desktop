import tkinter as tk
from PIL import Image, ImageTk, ImageGrab, ImageEnhance
import webbrowser
import io
import time
import ctypes
from ctypes import windll
import win32clipboard
import pyautogui
import keyboard
import gc

# --- CONFIGURATION ---
BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
BROWSER_LOAD_WAIT_TIME = 1.0  # Tweak this based on how fast Brave opens
HOTKEY = 'ctrl+alt+end'       # The key combo your mouse button is mapped to

class CircleToSearch:
    def __init__(self):
        # 1. FIX HIGH DPI SCALING (Crucial for 4K/250% zoom)
        try:
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            windll.user32.SetProcessDPIAware()

        self.root = tk.Tk()
        
        # 2. Setup Screen Capture
        # Capture immediately upon instantiation
        self.original_image = ImageGrab.grab(all_screens=True)
        
        # Darken for UI
        enhancer = ImageEnhance.Brightness(self.original_image)
        self.dark_image = enhancer.enhance(0.4) 
        self.tk_image = ImageTk.PhotoImage(self.dark_image)

        # 3. Setup Fullscreen Window
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(background='black')
        
        # Force focus so Esc key and drawing works immediately
        self.root.focus_force()

        # 4. Setup Canvas
        self.canvas = tk.Canvas(self.root, cursor="cross", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")

        self.points = []

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", lambda e: self.quit_app())

    def start(self):
        self.root.mainloop()

    def quit_app(self):
        self.root.destroy()

    def on_button_press(self, event):
        self.points = [(event.x, event.y)]

    def on_move_press(self, event):
        self.points.append((event.x, event.y))
        if len(self.points) > 1:
            x1, y1 = self.points[-2]
            x2, y2 = self.points[-1]
            self.canvas.create_line(x1, y1, x2, y2, fill="white", width=4, capstyle=tk.ROUND, smooth=True)

    def on_button_release(self, event):
        if len(self.points) < 2:
            return

        # Calculate bounding box
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        
        padding = 10
        box = (
            max(0, min(xs) - padding),
            max(0, min(ys) - padding),
            min(max(xs) + padding, self.original_image.width),
            min(max(ys) + padding, self.original_image.height)
        )

        cropped_image = self.original_image.crop(box)
        
        # Close the UI immediately so the user sees the browser opening
        self.root.destroy()
        
        # Run automation
        self.automate_google_search(cropped_image)

    def send_to_clipboard(self, image):
        # Convert to DIB for Windows Clipboard compatibility
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
        
        # Register and open Brave
        try:
            webbrowser.register('brave', None, webbrowser.BackgroundBrowser(BRAVE_PATH))
            webbrowser.get('brave').open("https://google.com")
        except:
            webbrowser.open("https://google.com")

        # Wait for browser to initialize
        time.sleep(BROWSER_LOAD_WAIT_TIME)
        
        # Paste and Enter
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5) # Brief pause to let the image render in the input box
        pyautogui.press('enter')

def main():
    print(f"Circle to Search is running...")
    print(f"Waiting for hotkey: {HOTKEY}")
    
    while True:
        # This blocks the main thread until the key is pressed, 
        # saving CPU resources.
        keyboard.wait(HOTKEY)
        
        # Instantiate fresh
        app = CircleToSearch()
        app.start()
        
        # Explicit cleanup just to be safe
        del app
        gc.collect()
        
        # Small buffer to prevent accidental double-triggering if key is held
        time.sleep(1) 

if __name__ == "__main__":
    main()