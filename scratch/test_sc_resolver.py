import urllib.request
import urllib.parse
import re
import json
import html as html_mod

def test_resolve_sc(u):
    sc_origin = "https://streamingcommunityz.boo"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': sc_origin + '/'}
    
    def _get_text(url, referer=sc_origin + '/'):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': referer})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read().decode('utf-8', 'ignore')

    m_tid = re.search(r'/titles/(\d+)', u)
    tid = m_tid.group(1) if m_tid else ''
    iframe_url = f"{sc_origin}/it/iframe/{tid}"
    print("iframe_url:", iframe_url)
    if_html = _get_text(iframe_url)
    m_vix = re.search(r'<iframe[^>]+src="([^"]+)"', if_html)
    if m_vix:
        vix_url = html_mod.unescape(m_vix.group(1))
        print("vix_url:", vix_url)
        vix_html = _get_text(vix_url, referer=sc_origin + '/')
        # Parse vixcloud playlist
        m_url = re.search(r"""url\s*:\s*['"](https?://[^'"]+)['"]""", vix_html)
        pl_base = m_url.group(1).strip()
        params = {}
        m_params = re.search(r"""params\s*:\s*\{([^}]+)\}""", vix_html, re.S)
        if m_params:
            for k, v in re.findall(r"""['"]?(\w+)['"]?\s*:\s*['"]([^'"]*)['"]""", m_params.group(1)):
                if v: params[k] = v
        if '?' in vix_url:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(vix_url).query)
            for k, v in qs.items():
                if k not in params and v:
                    params[k] = v[0]
        final_url = f"{pl_base}?{urllib.parse.urlencode(params)}"
        print("Final stream URL:", final_url)
        # Test fetch
        req_st = urllib.request.Request(final_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://vixcloud.cc/'})
        with urllib.request.urlopen(req_st, timeout=5) as r_st:
            print("Status stream:", r_st.status, "Length:", len(r_st.read()))

test_resolve_sc('https://streamingcommunityz.boo/it/titles/66508-one-year-to-live-buy-a-man')
