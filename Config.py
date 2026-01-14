# --- CONFIGURATION ---
# The hotkey to activate circle to search mode 
HOTKEY = 'ctrl+alt+print screen' 

# What happens when you hold left click while in circle to search mode
# Options: 
## "BOX" - Draws a rectangle from where you first clicked to where your mouse goes, like dragging on the desktop
## "CIRCLE" - Draws a white line where you drag the mouse to create a rectangle encompassing that entire area 
MODE = "BOX" 

# Define your modes here. 
# Key = Text displayed on screen
# Value = URL to open
SEARCH_MODES = {
    "AI Mode": "https://google.com",
    "Lens": "https://lens.google.com"
}

# The color of the rectangle drawn on the screen
BOX_COLOR = "#4287f4" # A familiar blue 

# Default text color for the mode label
TEXT_COLOR = "#4287f4" # A familiar blue to match the box


BROWSER_LOAD_WAIT_TIME = 1.0 # Seconds to wait for browser+Google to load