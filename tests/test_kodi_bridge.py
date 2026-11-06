import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

_p = Path(__file__).resolve().parent.parent / "extensions" / "ricette-web" / "kodi_bridge.py"
_spec = importlib.util.spec_from_file_location("ricette_web_kodi_bridge", _p)
kb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kb)

ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="plugin.video.stream4me" name="Stream4me" version="1.0.4" provider-name="Stream4me">
  <requires>
    <import addon="xbmc.python" version="3.0.0"/>
  </requires>
  <extension point="xbmc.python.pluginsource" library="stream4me.py">
    <provides>video</provides>
  </extension>
  <extension point="xbmc.addon.metadata">
    <summary lang="it_IT">Film e serie in streaming</summary>
    <description lang="it_IT">Descrizione lunga del catalogo</description>
    <language>it</language>
    <platform>all</platform>
  </extension>
</addon>
"""

MINIMAL_ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="plugin.video.minimo" name="Minimo" version="0.1.0"/>
"""

STREAM_HTML = """
<html><body>
  <video src="/media/film.mp4" title="Film locale"></video>
  <video title="Serie">
    <source src="https://cdn.example/show/ep1.webm" type="video/webm"/>
    <source src="https://cdn.example/show/ep1.mp4" type="video/mp4"/>
  </video>
  <iframe src="https://player.example/embed/abc123" title="Player"></iframe>
  <iframe src="https://doubleclick.net/ad/banner"></iframe>
  <iframe data-src="//googlesyndication.com/pagead/x"></iframe>
  <script>
    var player = new Player({file: "https://cdn.example/live/master.m3u8", poster: "/p.jpg"});
    var cfg = {"sources": [{"file": "https://cdn.example/a.mp4"}, {"file": "chunk.m3u8"}],
               "title": "Config"};
    // fallback secco: https://cdn.example/trailer.mp4
  </script>
</body></html>
"""

CHANNEL_JSON = {
    "id": "cb01",
    "name": "CB01",
    "host": "https://cb01.example/",
    "categories": ["Film", "Serie TV"],
    "find_videos": {"pattern": "VIDEO", "url": "/search?q=%s"},
}

CHANNEL_PY = '''
NAME = "Alfa"
HOST = "https://alfa.example"
CATEGORIES = ["Film", "Sport"]
PATTERN = "/search/{query}"
'''

ADDON_SCRIPT = '''
import xbmc, xbmcaddon, xbmcgui, xbmcplugin

addon = xbmcaddon.Addon()
xbmc.log("handle=%s" % addon.getAddonInfo("id"))

episode = xbmcgui.ListItem(label="Episodio 1")
episode.setArt({"poster": "https://img.example/ep1.jpg"})
episode.setInfo("video", {
    "plot": "Trama episodio",
    "year": "2021",
    "duration": "00:42:10",
    "mediatype": "episode",
    "season": 1,
    "episode": 2,
})
xbmcplugin.addDirectoryItem(1, "plugin://plugin.video.test/play/1", episode, False)

folder = xbmcgui.ListItem(label="Film")
xbmcplugin.addDirectoryItem(1, "plugin://plugin.video.test/films", folder, True)

resolved = xbmcgui.ListItem(label="Canale live", path="https://cdn.example/live/master.m3u8")
resolved.setInfo("video", {"mediatype": "movie"})
xbmcplugin.setResolvedUrl(1, True, resolved)
xbmcplugin.endOfDirectory(1)
'''


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- parse_addon_xml
def test_parse_addon_xml_completo():
    meta = kb.parse_addon_xml(ADDON_XML)
    assert meta == {
        "id": "plugin.video.stream4me",
        "name": "Stream4me",
        "version": "1.0.4",
        "entrypoint": "stream4me.py",
        "summary": "Film e serie in streaming",
        "provides": ["video"],
    }


def test_parse_addon_xml_entrypoint_e_summary_di_default():
    meta = kb.parse_addon_xml(MINIMAL_ADDON_XML)
    assert meta["entrypoint"] == "default.py"
    assert meta["summary"] == ""
    assert meta["provides"] == []
    assert meta["version"] == "0.1.0"


def test_parse_addon_xml_usa_description_come_fallback():
    xml = MINIMAL_ADDON_XML.replace(
        'version="0.1.0"/>',
        'version="0.1.0"><extension point="xbmc.addon.metadata">'
        "<description>Griglia canali</description></extension></addon>",
    )
    assert kb.parse_addon_xml(xml)["summary"] == "Griglia canali"


@pytest.mark.parametrize(
    "xml",
    [
        "<addon id='x' name='y'>",
        "<notaddon id='x' name='y'/>",
        "<addon id='' name='y'/>",
        "<addon id='x'/>",
    ],
)
def test_parse_addon_xml_rifiuta_invalido(xml):
    with pytest.raises(ValueError):
        kb.parse_addon_xml(xml)


# ---------------------------------------------------------------- extract_stream_urls
def test_extract_stream_urls_tag_e_js():
    found = kb.extract_stream_urls(STREAM_HTML, base_url="https://site.example/watch/1")
    urls = [item["url"] for item in found]
    kinds = {item["url"]: item["kind"] for item in found}

    assert "https://site.example/media/film.mp4" in urls
    assert kinds["https://site.example/media/film.mp4"] == "direct"
    assert kinds["https://cdn.example/show/ep1.webm"] == "direct"
    assert kinds["https://cdn.example/show/ep1.mp4"] == "direct"
    assert kinds["https://cdn.example/live/master.m3u8"] == "hls"
    assert kinds["https://cdn.example/a.mp4"] == "direct"
    assert kinds["https://site.example/watch/chunk.m3u8"] == "hls"
    assert kinds["https://cdn.example/trailer.mp4"] == "direct"
    assert kinds["https://player.example/embed/abc123"] == "embed"
    assert found[0]["label"] == "Film locale"


def test_extract_stream_urls_ignora_banner_e_ordina_per_priorita():
    found = kb.extract_stream_urls(STREAM_HTML, base_url="https://site.example/watch/1")
    joined = " ".join(item["url"] for item in found)
    assert "doubleclick" not in joined
    assert "googlesyndication" not in joined

    ranks = [kb.PRIORITY[item["kind"]] for item in found]
    assert ranks == sorted(ranks)
    assert found[-1]["kind"] == "embed"


def test_extract_stream_urls_deduplica():
    html = '<video src="https://cdn.example/x.mp4"></video><iframe src="https://cdn.example/x.mp4"></iframe>'
    found = kb.extract_stream_urls(html)
    assert found == [{"url": "https://cdn.example/x.mp4", "kind": "direct", "label": "video"}]


def test_extract_stream_urls_pagina_vuota():
    assert kb.extract_stream_urls("", base_url="https://site.example/") == []
    assert kb.extract_stream_urls("<p>solo testo</p>") == []


def test_is_direct_stream():
    assert kb.is_direct_stream("https://cdn.example/a.mp4?token=1")
    assert kb.is_direct_stream("https://cdn.example/a.mp3")
    assert not kb.is_direct_stream("https://cdn.example/live.m3u8")
    assert not kb.is_direct_stream("https://player.example/embed/1")


# ---------------------------------------------------------------- parse_kodi_channel
def test_parse_kodi_channel_json_stream4me():
    ch = kb.parse_kodi_channel(json.dumps(CHANNEL_JSON))
    assert ch == {
        "id": "cb01",
        "name": "CB01",
        "host": "https://cb01.example/",
        "categories": ["Film", "Serie TV"],
        "search_url": "https://cb01.example/search?q=%s",
    }


def test_parse_kodi_channel_json_senza_id_usa_channel_id():
    data = dict(CHANNEL_JSON)
    data.pop("id")
    ch = kb.parse_kodi_channel(json.dumps(data), channel_id="cb02")
    assert ch["id"] == "cb02"
    assert ch["name"] == "CB01"


def test_parse_kodi_channel_python():
    ch = kb.parse_kodi_channel(CHANNEL_PY, channel_id="alfa")
    assert ch["id"] == "alfa"
    assert ch["name"] == "Alfa"
    assert ch["host"] == "https://alfa.example"
    assert ch["categories"] == ["Film", "Sport"]
    assert ch["search_url"] == "https://alfa.example/search/{query}"


def test_parse_kodi_channel_vuoto():
    with pytest.raises(ValueError):
        kb.parse_kodi_channel("   ")


def test_parse_kodi_channel_json_con_intestazione():
    raw = "Rev:0.2\nUpdate: 03-10-2019\n#####\nPromemoria\n\n" + json.dumps(CHANNEL_JSON)
    assert kb.parse_kodi_channel(raw)["id"] == "cb01"


def test_canali_ignorano_helper_resolver_e_inattivi(tmp):
    addon = tmp / "plugin.video.s4me"
    _write(addon / "addon.xml", ADDON_XML)
    _write(addon / "channels" / "__init__.py", "")
    _write(addon / "channels" / "_tools.py", "HOST = 'https://x.example'")
    _write(addon / "channels" / "cb01.json", json.dumps(CHANNEL_JSON))
    _write(addon / "channels" / "cb01.py", 'host = "https://cb01.example"\n')
    _write(addon / "channels" / "spento.json", json.dumps({**CHANNEL_JSON, "id": "spento", "name": "Spento", "active": False}))
    _write(addon / "channels" / "jsonc.json", "Rev:1.0\n###\n" + json.dumps({**CHANNEL_JSON, "id": "jsonc", "name": "JSONC", "host": ""}))
    _write(addon / "channels" / "jsonc.py", 'host = "https://cb01.example"\n')
    _write(addon / "channels" / "senzahost.json", json.dumps({**CHANNEL_JSON, "id": "senzahost", "name": "Senza host", "host": "", "find_videos": ""}))
    _write(addon / "channels" / "resolver.py", "def mainlist(item):\n    return locals()\n")

    items = kb.run_kodi_addon_directory(addon)
    assert sorted(i["title"] for i in items) == ["CB01", "JSONC"]
    per_canale = {i["title"]: i["url"] for i in items}
    assert per_canale["CB01"] == "https://cb01.example/search?q=%s"
    assert per_canale["JSONC"] == "https://cb01.example/search?q=%s"

    installati = kb.install_kodi_addon(addon, tmp / "addons")["channels"]
    assert sorted(c["name"] for c in installati) == ["CB01", "JSONC"]


# ---------------------------------------------------------------- run_kodi_addon_directory (canali)
def test_run_kodi_addon_directory_canali(tmp):
    addon = tmp / "plugin.video.stream4me"
    _write(addon / "addon.xml", ADDON_XML)
    _write(addon / "channels" / "cb01.json", json.dumps(CHANNEL_JSON))
    _write(addon / "channels" / "alfa.py", CHANNEL_PY)

    items = kb.run_kodi_addon_directory(addon)
    assert [item["title"] for item in items] == ["Alfa", "CB01"]
    assert all(item["source"] == "ricette-web" for item in items)
    assert all(item["kind"] == "film" for item in items)
    assert items[0]["id"] == "kodi:plugin.video.stream4me:alfa"
    assert items[0]["url"] == "https://alfa.example/search/{query}"
    assert items[0]["stream_url"] == ""
    assert "Sport" in items[0]["overview"]


def test_run_kodi_addon_directory_canali_filtra_query(tmp):
    addon = tmp / "plugin.video.stream4me"
    _write(addon / "addon.xml", ADDON_XML)
    _write(addon / "channels" / "cb01.json", json.dumps(CHANNEL_JSON))

    assert [i["title"] for i in kb.run_kodi_addon_directory(addon, query="serie")] == ["CB01"]
    assert kb.run_kodi_addon_directory(addon, query="inesistente") == []


# ---------------------------------------------------------------- run_kodi_addon_directory (shim xbmc)
def test_run_kodi_addon_directory_shim_xbmc(tmp):
    addon = tmp / "plugin.video.test"
    _write(addon / "addon.xml", MINIMAL_ADDON_XML)
    _write(addon / "default.py", ADDON_SCRIPT)

    items = kb.run_kodi_addon_directory(addon, handle_url="plugin://plugin.video.test/")

    assert len(items) == 3
    episode, folder, resolved = items

    assert episode["kind"] == "episodio"
    assert episode["title"] == "Episodio 1"
    assert episode["poster"] == "https://img.example/ep1.jpg"
    assert episode["overview"] == "Trama episodio"
    assert episode["year"] == 2021
    assert episode["duration"] == 2530
    assert episode["url"] == "plugin://plugin.video.test/play/1"
    assert episode["stream_url"] == "plugin://plugin.video.test/play/1"

    assert folder["stream_url"] == ""
    assert folder["url"] == "plugin://plugin.video.test/films"

    assert resolved["title"] == "Canale live"
    assert resolved["kind"] == "film"
    assert resolved["stream_url"] == "https://cdn.example/live/master.m3u8"
    assert all(item["source"] == "ricette-web" for item in items)
    assert [item["id"] for item in items] == [
        "kodi:plugin.video.minimo:0",
        "kodi:plugin.video.minimo:1",
        "kodi:plugin.video.minimo:2",
    ]


def test_run_kodi_addon_directory_ripristina_moduli_e_argv(tmp):
    addon = tmp / "plugin.video.test"
    _write(addon / "addon.xml", MINIMAL_ADDON_XML)
    _write(addon / "default.py", ADDON_SCRIPT)

    sentinel = type(sys)("xbmc")
    sys.modules["xbmc"] = sentinel
    argv = list(sys.argv)
    try:
        kb.run_kodi_addon_directory(addon)
        assert sys.modules["xbmc"] is sentinel
        assert "xbmcplugin" not in sys.modules
        assert "xbmcgui" not in sys.modules
        assert sys.argv == argv
    finally:
        sys.modules.pop("xbmc", None)


def test_run_kodi_addon_directory_entrypoint_fuori_cartella(tmp):
    addon = tmp / "plugin.video.evil"
    _write(addon / "addon.xml", ADDON_XML.replace('library="stream4me.py"', 'library="../evil.py"'))
    with pytest.raises(ValueError):
        kb.run_kodi_addon_directory(addon)


def test_run_kodi_addon_directory_senza_entrypoint(tmp):
    addon = tmp / "plugin.video.vuoto"
    _write(addon / "addon.xml", MINIMAL_ADDON_XML)
    assert kb.run_kodi_addon_directory(addon) == []


def test_run_kodi_addon_directory_cartella_inesistente(tmp):
    with pytest.raises(ValueError):
        kb.run_kodi_addon_directory(tmp / "nope")


# ---------------------------------------------------------------- normalize_github_zip_url
@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://github.com/Stream4me/addon",
            "https://github.com/Stream4me/addon/archive/refs/heads/master.zip",
        ),
        (
            "https://github.com/Stream4me/addon/",
            "https://github.com/Stream4me/addon/archive/refs/heads/master.zip",
        ),
        (
            "https://github.com/Stream4me/addon.git",
            "https://github.com/Stream4me/addon/archive/refs/heads/master.zip",
        ),
        (
            "https://github.com/Stream4me/addon/tree/main",
            "https://github.com/Stream4me/addon/archive/refs/heads/main.zip",
        ),
        (
            "https://github.com/Stream4me/addon/archive/refs/heads/dev.zip",
            "https://github.com/Stream4me/addon/archive/refs/heads/dev.zip",
        ),
        ("https://example.com/addon.zip", "https://example.com/addon.zip"),
    ],
)
def test_normalize_github_zip_url(url, expected):
    assert kb.normalize_github_zip_url(url) == expected


# ---------------------------------------------------------------- install_kodi_addon
def test_canali_usano_domini_da_channels_json(tmp):
    addon = tmp / "plugin.video.s4me"
    _write(addon / "addon.xml", ADDON_XML)
    _write(addon / "channels" / "cb01.json", json.dumps({"id": "cb01", "name": "CB01", "categories": ["movie"], "active": True}))
    _write(addon / "channels" / "spento.json", json.dumps({"id": "spento", "name": "Spento", "active": False}))
    _write(addon / "channels.json", json.dumps({"direct": {"cb01": "https://cb01.uno", "spento": "https://spento.example"}}))

    assert [(i["title"], i["url"]) for i in kb.run_kodi_addon_directory(addon)] == [("CB01", "https://cb01.uno")]
    installati = kb.install_kodi_addon(addon, tmp / "addons")["channels"]
    assert [(c["name"], c["host"]) for c in installati] == [("CB01", "https://cb01.uno")]


def test_install_da_url_github_con_fetcher(tmp):
    archive = _zip_bytes({
        "addon-master/addon.xml": ADDON_XML,
        "addon-master/stream4me.py": "print('ciao')",
        "addon-master/channels/cb01.json": json.dumps(CHANNEL_JSON),
    })
    chiamate = []

    def fetcher(url):
        chiamate.append(url)
        return archive

    result = kb.install_kodi_addon("https://github.com/Stream4me/addon", tmp / "addons", fetcher=fetcher)

    assert chiamate == ["https://github.com/Stream4me/addon/archive/refs/heads/master.zip"]
    assert result["id"] == "plugin.video.stream4me"
    assert result["name"] == "Stream4me"
    assert result["version"] == "1.0.4"
    dest = Path(result["path"])
    assert dest == tmp / "addons" / "plugin.video.stream4me"
    assert (dest / "addon.xml").is_file()
    assert (dest / "stream4me.py").is_file()
    assert [c["id"] for c in result["channels"]] == ["cb01"]
    assert result["channels"][0]["search_url"] == "https://cb01.example/search?q=%s"


def test_install_fallback_su_branch_main(tmp):
    archive = _zip_bytes({"addon-main/addon.xml": MINIMAL_ADDON_XML})
    chiamate = []

    def fetcher(url):
        chiamate.append(url)
        if url.endswith("master.zip"):
            raise RuntimeError("404")
        return archive

    result = kb.install_kodi_addon("https://github.com/tizio/addon", tmp / "addons", fetcher=fetcher)
    assert chiamate[-1].endswith("/main.zip")
    assert result["id"] == "plugin.video.minimo"
    assert result["channels"] == []


def test_install_da_cartella_locale(tmp):
    src = tmp / "src-plugin"
    _write(src / "addon.xml", ADDON_XML)
    _write(src / "stream4me.py", "")
    _write(src / "channels" / "alfa.py", CHANNEL_PY)

    result = kb.install_kodi_addon(src, tmp / "addons")
    assert result["id"] == "plugin.video.stream4me"
    assert [c["name"] for c in result["channels"]] == ["Alfa"]
    assert (Path(result["path"]) / "channels" / "alfa.py").is_file()


def test_install_da_zip_locale(tmp):
    src_zip = tmp / "addon.zip"
    src_zip.write_bytes(_zip_bytes({
        "addon-master/addon.xml": ADDON_XML,
        "addon-master/channels/cb01.json": json.dumps(CHANNEL_JSON),
    }))

    result = kb.install_kodi_addon(src_zip, tmp / "addons")
    assert result["id"] == "plugin.video.stream4me"
    assert [c["id"] for c in result["channels"]] == ["cb01"]


def test_install_reinstalla_sovrascrivendo(tmp):
    src = tmp / "src-plugin"
    _write(src / "addon.xml", MINIMAL_ADDON_XML)
    prima = kb.install_kodi_addon(src, tmp / "addons")
    _write(src / "extra.py", "")
    dopo = kb.install_kodi_addon(src, tmp / "addons")
    assert prima["path"] == dopo["path"]
    assert (Path(dopo["path"]) / "extra.py").is_file()


@pytest.mark.parametrize("member", ["../evil.txt", "addon/../../evil.txt", "/abs/evil.txt", "C:/evil.txt"])
def test_install_rifiuta_zipslip(tmp, member):
    src_zip = tmp / "addon.zip"
    src_zip.write_bytes(_zip_bytes({"addon-master/addon.xml": ADDON_XML, member: "pwned"}))
    addons = tmp / "addons"
    with pytest.raises(ValueError):
        kb.install_kodi_addon(src_zip, addons)
    assert not (tmp / "evil.txt").exists()
    assert not (addons / "plugin.video.stream4me").exists()


def test_install_senza_addon_xml(tmp):
    archive = _zip_bytes({"addon-master/readme.txt": "niente addon"})
    src_zip = tmp / "addon.zip"
    src_zip.write_bytes(archive)
    with pytest.raises(ValueError):
        kb.install_kodi_addon(src_zip, tmp / "addons")


def test_install_sorgente_non_valida(tmp):
    with pytest.raises(ValueError):
        kb.install_kodi_addon("not-a-path", tmp / "addons")
    with pytest.raises(ValueError):
        kb.install_kodi_addon(tmp / "vuoto.zip", tmp / "addons")
