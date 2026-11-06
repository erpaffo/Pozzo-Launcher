import urllib.request
import ssl
from bs4 import BeautifulSoup

ctx = ssl._create_unverified_context()
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
req = urllib.request.Request('https://www.animeworld.ac/', headers=headers)
html = urllib.request.urlopen(req, timeout=5, context=ctx).read().decode('utf-8', 'ignore')

soup = BeautifulSoup(html, "html.parser")
for a in soup.find_all("a", href=True):
    t = a.get_text(strip=True)
    if any(k in t.lower() for k in ["telegram", "instagram", "anime casuale", "sfondi", "aggiornamenti"]):
        print("Menu link:", t, "href:", a.get("href"), "parent:", a.parent.name, a.parent.get("class"))
