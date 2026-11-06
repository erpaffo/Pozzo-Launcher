from bs4 import BeautifulSoup
import urllib.request

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
req = urllib.request.Request('https://altadefinizione-01.best/', headers=headers)
html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8', 'ignore')
soup = BeautifulSoup(html, "html.parser")

containers = soup.select(
    ".boxgrid, .cover_kapsul, .ml-item, article, .movieItem, .post, .film-poster, .anime-card, .card, .TPost, .result-item, .blog-item, .item"
)
print("New containers count:", len(containers))
found_posters = 0
for el in containers:
    img = el.find("img") or (el.parent.find("img") if el.parent else None)
    if img:
        poster = img.get("data-src") or img.get("src")
        if poster:
            found_posters += 1

print("Found posters with new selector:", found_posters)
