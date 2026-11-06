from pathlib import Path
cache = Path.home() / "AppData" / "Local" / "PozzoLauncher" / "ricette-web-cache"
p = cache / "kodi-addons" / "plugin.video.s4me" / "servers" / "streamingcommunityws.py"
if p.exists():
    print(p.read_text("utf-8", errors="replace")[:3000])
else:
    print("Not found")
