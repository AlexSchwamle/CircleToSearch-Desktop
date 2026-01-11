# Circle To Search For Windows
I have been using the circle to search feature on my Android phone for a while and really wanted to have that on my Windows PC. So I\* made it! 

## How To Run
### Before Running
- Install the prerequisites via `pip install -r requirements.txt` 
- Edit `Config.py` to your own hotkey liking 
### After Configurating
- Double click `start.bat` to open it silently in the background (closeable via the blue icon in the taskbar icons)
- Press the hotkey `ctrl + alt + print screen` by default (I have a mouse macro using Logitech's G Hub)
- Left click to draw a circle around the area you want to send to Google's AI Mode
    - The blue rectangle is what will be sent
- Done!

If you don't want to send it, either press `escape` or `right click`.

I would recommend putting it in `shell:startup` 

---

\*Yes, it's vibe coded - Gemini made most of it, was close to an MVP one shot honestly other than several bugfixes, refinements, and other features.