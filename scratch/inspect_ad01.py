import httpx
from bs4 import BeautifulSoup

r = httpx.get('https://altadefinizione-01.best', headers={'User-Agent': 'Mozilla/5.0'}, follow_redirects=True)
soup = BeautifulSoup(r.text, 'html.parser')
imgs = soup.find_all('img')
for img in imgs[2:8]:
    print('Attrs:', img.attrs)
