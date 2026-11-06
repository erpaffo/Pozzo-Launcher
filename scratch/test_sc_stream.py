import re
import urllib.parse

def _parse_vixcloud_playlist(vix_html: str, vix_url: str = "") -> str:
    if not vix_html:
        return ""
    m_url = re.search(r"""url\s*:\s*['"](https?://[^'"]+)['"]""", vix_html)
    if not m_url:
        return ""
    pl_base = m_url.group(1).strip()
    params: dict[str, str] = {}
    m_params = re.search(r"""params\s*:\s*\{([^}]+)\}""", vix_html, re.S)
    if m_params:
        for k, v in re.findall(r"""['"]?(\w+)['"]?\s*:\s*['"]([^'"]*)['"]""", m_params.group(1)):
            if v:
                params[k] = v
    if re.search(r"""window\.canPlayFHD\s*=\s*true\b""", vix_html, re.I):
        params["h"] = "1"
    if vix_url and "?" in vix_url:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(vix_url).query)
        for k, v in qs.items():
            if k not in params and v:
                params[k] = v[0]
    if params:
        sep = "&" if "?" in pl_base else "?"
        return f"{pl_base}{sep}{urllib.parse.urlencode(params)}"
    return pl_base

vix_html_sample = """
        params: {
            'token': '876ae6072019641e747344a01d12b611',
            'expires': '1799149876',
            'asn': '',
        },
        url: 'https://vixcloud.cc/playlist/799062',
    }
    window.canPlayFHD = false 
"""
vix_url_sample = "https://vixcloud.cc/embed/799062?token=1467c3476693905ada4e1488feb85c03&t=T25lIFllYXIgdG8gTGl2ZSwgQnV5IGEgTWFu&referer=1&expires=1793965884&lang=it&scz=1"

res = _parse_vixcloud_playlist(vix_html_sample, vix_url_sample)
print("Resolved URL:\n", res)
import urllib.request
req = urllib.request.Request(res, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://vixcloud.cc/'})
with urllib.request.urlopen(req) as r:
    print("HTTP Status:", r.status, "Length:", len(r.read()))
