import urllib.request

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
url = "https://cdn.streamingcommunityz.boo/images/be9f9969-0e79-425f-883a-7004f8faf9e9.webp"
req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=5) as r:
        print("Status:", r.status, "Content-Type:", r.headers.get("Content-Type"), "Length:", len(r.read()))
except Exception as e:
    print("Error:", e)
