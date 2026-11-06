import urllib.request
import re
import json

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# 1. Inspect StreamingCommunity
try:
    req = urllib.request.Request('https://streamingcommunityz.boo/it/archive', headers=headers)
    with urllib.request.urlopen(req, timeout=5) as r:
        html = r.read().decode('utf-8', 'ignore')
        m = re.search(r'data-page="([^"]+)"', html)
        if m:
            import html as html_mod
            raw = html_mod.unescape(m.group(1))
            data = json.loads(raw)
            print("SC Archive props keys:", list(data.get("props", {}).keys()))
            titles = data.get("props", {}).get("titles")
            print("titles type:", type(titles))
            if isinstance(titles, dict):
                print("titles dict keys:", list(titles.keys()))
                data_items = titles.get("data", [])
                print("titles['data'] count:", len(data_items))
                if data_items:
                    print("Sample item:", data_items[0].get("id"), data_items[0].get("name"), "images:", data_items[0].get("images"))
            elif isinstance(titles, list):
                print("titles list count:", len(titles))
except Exception as e:
    print("SC Archive error:", e)

# 2. Inspect Altadefinizione01
try:
    req = urllib.request.Request('https://altadefinizione-01.best/', headers=headers)
    with urllib.request.urlopen(req, timeout=5) as r:
        html = r.read().decode('utf-8', 'ignore')
        print("AD01 length:", len(html))
        # Find img tags
        imgs = re.findall(r'<img[^>]+>', html)[:5]
        for img in imgs:
            print("AD01 img:", img)
except Exception as e:
    print("AD01 error:", e)
