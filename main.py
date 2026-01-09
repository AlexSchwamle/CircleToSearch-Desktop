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
# Path to your Brave executable.
BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
# How long to wait for the browser to open/focus before hitting Ctrl+V
BROWSER_LOAD_WAIT_TIME = 1.0 
# The key combo your mouse button is mapped to to trigger the overlay
HOTKEY = 'ctrl+alt+end'       

class CircleToSearch:
    def __init__(self):
        # 1. FIX HIGH DPI SCALING
        # Crucial for 4K/250% zoom setups to ensure 1:1 screen mapping
        try:
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            windll.user32.SetProcessDPIAware()

        self.root = tk.Tk()
        
        # 2. Setup Screen Capture
        # Capture the screen immediately upon instantiation
        self.original_image = ImageGrab.grab(all_screens=True)
        
        # Create darkened version for the UI background
        enhancer = ImageEnhance.Brightness(self.original_image)
        self.dark_image = enhancer.enhance(0.4) 
        self.tk_image = ImageTk.PhotoImage(self.dark_image)

        # 3. Setup Fullscreen Window
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(background='black')
        
        # Force focus so keyboard/mouse events are captured immediately
        self.root.focus_force()

        # 4. Setup Canvas
        self.canvas = tk.Canvas(self.root, cursor="cross", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")

        # State variables for drawing
        self.points = []
        self.selection_rect = None # Will hold the canvas rectangle object

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        
        # Escape via keyboard OR Right Click (Button-3)
        self.root.bind("<Escape>", lambda e: self.quit_app())
        self.root.bind("<Button-3>", lambda e: self.quit_app())

    def start(self):
        self.root.mainloop()

    def quit_app(self):
        self.root.destroy()

    def on_button_press(self, event):
        # Reset points on new click
        self.points = [(event.x, event.y)]
        
        # Create the selection rectangle object once upon starting the click.
        # We use a bright cyan color and a dashed line pattern.
        # It starts as a 1x1 point and will expand on the first move event.
        self.selection_rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#00FFFF", # Cyan/Neon Blue
            width=2,
            dash=(4, 4) # Dashed line pattern (4px on, 4px off)
        )

    def on_move_press(self, event):
        # 1. Record path and draw the white "ink"
        self.points.append((event.x, event.y))
        if len(self.points) > 1:
            x1, y1 = self.points[-2]
            x2, y2 = self.points[-1]
            self.canvas.create_line(x1, y1, x2, y2, fill="white", width=4, capstyle=tk.ROUND, smooth=True)

        # 2. Update the dynamic bounding box visual feedback
        # We only calculate bounds if we have more than 1 point to define an area
        if self.selection_rect and len(self.points) > 1:
            # Calculate current bounds of everything drawn so far
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)

            # Update the existing rectangle coordinates instantly (no flickering)
            self.canvas.coords(self.selection_rect, min_x, min_y, max_x, max_y)

    def on_button_release(self, event):
        if len(self.points) < 2:
            self.quit_app()
            return

        # Final calculation of the bounding box for cropping
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        
        # Add slight padding to ensure edges of the drawing aren't cut off
        padding = 10
        box = (
            max(0, min(xs) - padding),
            max(0, min(ys) - padding),
            min(max(xs) + padding, self.original_image.width),
            min(max(ys) + padding, self.original_image.height)
        )

        # Crop from the original, full-brightness image
        cropped_image = self.original_image.crop(box)
        
        # Close the UI immediately so the user sees the browser opening
        self.quit_app()
        
        # Run automation
        self.automate_google_search(cropped_image)

    def send_to_clipboard(self, image):
        """Converts PIL image to DIB format and places it on Windows Clipboard."""
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:] # Strip BMP header to get DIB
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
        
        # Register Brave just in case, though usually 'open' grabs default
        try:
            webbrowser.register('brave', None, webbrowser.BackgroundBrowser(BRAVE_PATH))
            # We use the main google homepage as it now supports pasting images directly
            webbrowser.get('brave').open("https://google.com")
        except:
            webbrowser.open("https://google.com")

        # Wait for browser to initialize and focus input
        time.sleep(BROWSER_LOAD_WAIT_TIME)
        
        # Paste (Ctrl+V) and Submit (Enter)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5) # Brief pause to let the image render in the input box
        pyautogui.press('enter')

def main():
    print(f"--- Circle to Search V4 Started ---")
    print(f"Running in background. Waiting for hotkey: {HOTKEY}")
    print(f"Draw with Left Click. Cancel with Right Click or Esc.")
    
    while True:
        # This blocks the main thread silently until the key is pressed.
        # suppress=True prevents the keystroke from reaching the active application.
        try:
            keyboard.wait(HOTKEY, suppress=True)
        except ImportError:
             # Fallback if keyboard module isn't set up perfectly for suppression on some systems
             keyboard.wait(HOTKEY)

        print("Hotkey detected. Launching overlay...")
        
        # Instantiate fresh for every capture
        app = CircleToSearch()
        app.start()
        
        # Cleanup memory explicitly
        del app
        gc.collect()
        
        # Small buffer to prevent accidental rapid re-triggering
        time.sleep(0.5) 

if __name__ == "__main__":
    main()