"""Sicurezza delle rotte media: percorsi, permesso media:lettura, id inventati, segreti.

Ogni test corrisponde a un punto dell'audit; dove il backend era già sicuro il test lo dimostra, dove non lo era
c'è la correzione (indicata nel commento).

Esegui: python -m pytest tests/test_media_sicurezza.py -q
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).parent / "fixtures_media"
TOKEN = "TOKEN-SEGRETO"
PASSWORD = "Password-Segreta"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"ext_{name.replace('-', '_')}", ROOT / "extensions" / name / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ML = load("media-locale")
MS = load("media-server")


class FakeGS:
    """PluginAPI minimo: rotte per metodo, impostazioni in memoria, log raccolti."""

    def __init__(self, cfg, pid):
        self.cfg, self.id, self.routes, self.settings, self.logs = cfg, pid, {}, {}, []
        self.log = self.logs.append

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.routes[(path.lstrip("/"), methods[0])] = fn
            return fn
        return deco

    def get(self, path, **kw):
        return self.routes[(path, "GET")](**kw)

    def post(self, path, body=None, **kw):
        if body is None:
            return self.routes[(path, "POST")](**kw)
        return self.routes[(path, "POST")](body=body, **kw)

    def add_library_kind(self, kind):
        pass

    def add_player(self, player):
        pass

    def save_settings(self, values):
        self.settings.update(values)

    def job(self, *a, **k):
        pass


def cfg_for(tmp: Path):
    return SimpleNamespace(config_path=tmp / "config.toml", app={})


def locale(tmp: Path):
    lib = tmp / "media"
    (lib / "Serie").mkdir(parents=True)
    (lib / "Film (2020).mp4").write_bytes(b"0123456789")
    (lib / "Serie" / "S01E01 - Pilota.mkv").write_bytes(b"x")
    gs = FakeGS(cfg_for(tmp), "media-locale")
    ML.register(gs)
    gs.post("roots", {"add": str(lib)})
    gs.post("scan")
    return gs, lib


def metti_item_fuori(tmp: Path, root: Path, path: str) -> str:
    """Inserisce nel database un item che punta a `path`, come se il file fosse stato spostato."""
    db_file = next((tmp / "media-locale-cache").glob("media.db"))
    conn = sqlite3.connect(db_file)
    conn.execute("INSERT OR REPLACE INTO items(id, kind, title, path, poster, root, seen, pos)"
                 " VALUES('x1','film','Intruso',?,?,?,0,0)", (path, path, str(root)))
    conn.commit()
    conn.close()
    return "x1"


def senza_stack(detail: str) -> bool:
    testo = str(detail)
    return "Traceback" not in testo and "File \"" not in testo and "\\" not in testo and "/" not in testo


# ---------------------------------------------------------------- (a) path traversal
def test_percorso_con_due_punti_fuori_dalla_cartella(tmp):
    gs, lib = locale(tmp)
    segreto = tmp / "segreto.mp4"
    segreto.write_bytes(b"x")
    item = metti_item_fuori(tmp, lib, str(lib / ".." / "segreto.mp4"))  # dentro la cartella solo "sulla carta"
    for rotta in ("stream", "play_target", "artwork"):
        with pytest.raises(HTTPException) as err:
            gs.get(rotta, id=item)
        assert err.value.status_code == 404 and senza_stack(err.value.detail)


def test_percorso_assoluto_fuori_dalla_cartella(tmp):
    gs, lib = locale(tmp)
    item = metti_item_fuori(tmp, lib, str(tmp / "Altro posto" / "film.mp4"))
    with pytest.raises(HTTPException) as err:
        gs.get("stream", id=item)
    assert err.value.status_code == 404
    with pytest.raises(HTTPException):
        gs.post("external", {"id": item})  # il lettore esterno non riceve mai quel percorso


def test_symlink_fuori_dalla_cartella(tmp):
    gs, lib = locale(tmp)
    fuori = tmp / "fuori.mp4"
    fuori.write_bytes(b"x")
    collegamento = lib / "collegamento.mp4"
    try:
        os.symlink(fuori, collegamento)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlink non consentiti su questo sistema")
    item = metti_item_fuori(tmp, lib, str(collegamento))
    with pytest.raises(HTTPException) as err:
        gs.get("stream", id=item)
    assert err.value.status_code == 404  # il percorso si risolve fuori dalla cartella scelta


def test_rotte_accettano_solo_id_non_percorsi(tmp):
    """Nessuna rotta prende un percorso: quello che sembra un percorso è solo un id sconosciuto."""
    gs, _ = locale(tmp)
    for finto in ("../../etc/passwd", "C:\\Windows\\win.ini", "..", "?id=../../x", "%2e%2e%2fsegreto"):
        for rotta in ("detail", "stream", "play_target", "artwork"):
            with pytest.raises(HTTPException) as err:
                gs.get(rotta, id=finto)
            assert err.value.status_code == 404 and senza_stack(err.value.detail)


# ---------------------------------------------------------------- (b) permesso media:lettura
def test_fuori_dalle_cartelle_scelte_non_si_legge(tmp):
    """Fuori dal permesso «media:lettura» (le cartelle scelte) non si serve niente, in nessuna forma."""
    gs, lib = locale(tmp)
    estraneo = tmp / "estraneo"
    estraneo.mkdir()
    (estraneo / "privato.mp4").write_bytes(b"x")
    item = metti_item_fuori(tmp, lib, str(estraneo / "privato.mp4"))
    for rotta in ("stream", "play_target", "artwork"):
        with pytest.raises(HTTPException) as err:
            gs.get(rotta, id=item)
        assert err.value.status_code == 404
    # togliendo la cartella il contenuto sparisce dall'elenco
    gs.post("roots", {"remove": str(lib)})
    assert gs.get("list") == []


def test_radice_di_un_disco_rifiutata(tmp):
    """La radice del disco non è una cartella da scansionare: bloccherebbe l'app per ore."""
    gs, _ = locale(tmp)
    with pytest.raises(HTTPException) as err:
        gs.post("roots", {"add": "C:\\" if os.name == "nt" else "/"})
    assert err.value.status_code == 400


def test_cartelle_rifiutate(tmp):
    gs, lib = locale(tmp)
    for cattiva in ("relativa/cartella", str(lib / "Film (2020).mp4"), str(tmp / "non-esiste"), "", "x" * 2000):
        with pytest.raises(HTTPException) as err:
            gs.post("roots", {"add": cattiva})
        assert err.value.status_code == 400 and senza_stack(err.value.detail)


# ---------------------------------------------------------------- (c) id inventati
def test_id_inventati_danno_404_pulito(tmp):
    gs, _ = locale(tmp)
    with pytest.raises(HTTPException) as err:
        gs.get("detail", id="inventato")
    assert err.value.status_code == 404
    assert err.value.detail == "contenuto non trovato"
    with pytest.raises(HTTPException) as err:
        gs.post("set_progress", {"id": "inventato", "pos": 10, "seen": False})
    assert err.value.status_code == 404 and senza_stack(err.value.detail)


def test_id_lunghissimi_non_rompono(tmp):
    gs, _ = locale(tmp)
    with pytest.raises(HTTPException) as err:
        gs.get("stream", id="a" * 5000)
    assert err.value.status_code == 404


# ---------------------------------------------------------------- (d) segreti
def jellyfin_http(tmp: Path):
    """Server finto: login valido, una libreria, un item con copertina."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/Users/AuthenticateByName":
            return httpx.Response(200, json={"AccessToken": TOKEN, "User": {"Id": "U1"}})
        if path.startswith("/Users/U1/Items/"):
            return httpx.Response(200, json={"Id": "jf1", "Type": "Movie", "Name": "Film", "ImageTags": {"Primary": "a"},
                                             "Container": "mkv", "UserData": {}})
        if path == "/Items/jf1":
            return httpx.Response(200, json={"Id": "jf1", "Type": "Movie", "Name": "Film", "ImageTags": {"Primary": "a"},
                                             "Container": "mkv", "UserData": {}})
        if path == "/Items":
            return httpx.Response(200, json={"Items": [{"Id": "jf1", "Type": "Movie", "Name": "Film",
                                                        "ImageTags": {"Primary": "a"}, "UserData": {}}]})
        if path.startswith("/Items/jf1/Images"):
            return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})
        return httpx.Response(200, json={})

    real = httpx.Client
    handler_client = lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)})  # noqa: E731
    return handler_client


def server_gs(tmp: Path, monkeypatch):
    monkeypatch.setattr(httpx, "Client", jellyfin_http(tmp))
    MS.Http = MS.Http  # il modulo usa httpx.Client, già sostituito
    gs = FakeGS(cfg_for(tmp), "media-server")
    MS.register(gs)
    gs.post("config", {"source": "jellyfin", "base_url": "http://jf.local:8096", "username": "pozzo",
                       "password": PASSWORD})
    return gs


def test_token_mai_nelle_risposte(tmp, monkeypatch):
    gs = server_gs(tmp, monkeypatch)
    for risposta in (gs.get("config"), gs.post("config", {"source": "jellyfin", "base_url": "http://jf.local:8096",
                                                          "api_key": TOKEN}),
                     gs.get("list", source="jellyfin"), gs.get("detail", id="jf1", source="jellyfin")):
        testo = json.dumps(risposta)
        assert TOKEN not in testo and PASSWORD not in testo
    assert TOKEN not in json.dumps(gs.get("test", source="jellyfin"))


def test_token_in_play_target_solo_nell_url_del_player(tmp, monkeypatch):
    """Il token sta nell'URL solo dove serve al player esterno: niente token negli altri campi né nei log."""
    gs = server_gs(tmp, monkeypatch)
    target = gs.get("play_target", id="jf1", source="jellyfin")
    assert TOKEN in target["url"]  # necessario: mpv/VLC non mandano header
    assert TOKEN not in json.dumps({k: v for k, v in target.items() if k != "url"})


def test_token_mai_nei_log(tmp, monkeypatch):
    gs = server_gs(tmp, monkeypatch)
    gs.get("list", source="jellyfin")
    gs.get("detail", id="jf1", source="jellyfin")
    gs.get("play_target", id="jf1", source="jellyfin")
    gs.post("set_progress", {"id": "jf1", "pos": 10, "seen": False}, source="jellyfin")
    gs.get("artwork", src="/Items/jf1/Images/Primary", source="jellyfin")
    gs.get("test", source="jellyfin")
    testo = " ".join(str(x) for x in gs.logs)
    assert TOKEN not in testo and PASSWORD not in testo
    assert "api_key" not in testo and "X-Plex-Token" not in testo


def test_errori_del_server_senza_segreti(tmp, monkeypatch):
    """Server irraggiungibile e token scaduto: messaggi brevi, senza URL e senza credenziali."""

    def rotto(request):
        raise httpx.ConnectError(f"{request.url}?api_key={TOKEN}")

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(rotto)}))
    gs = FakeGS(cfg_for(tmp), "media-server")
    MS.register(gs)
    gs.settings["servers"] = {"jellyfin": {"base_url": "http://jf.local:8096", "token": TOKEN, "user_id": "U1"}}
    with pytest.raises(HTTPException) as err:
        gs.get("list", source="jellyfin")
    assert err.value.status_code == 502
    assert TOKEN not in err.value.detail and "http" not in err.value.detail

    def scaduto(request):
        return httpx.Response(401, json={"errore": "token scaduto"})

    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(scaduto)}))
    gs2 = FakeGS(cfg_for(tmp), "media-server")
    MS.register(gs2)
    gs2.settings["servers"] = {"plex": {"base_url": "http://plex.local:32400", "token": TOKEN}}
    with pytest.raises(HTTPException) as err:
        gs2.get("list", source="plex")
    assert err.value.status_code == 401 and TOKEN not in err.value.detail
    assert gs2.get("test", source="plex")["ok"] is False
    assert TOKEN not in gs2.get("test", source="plex")["error"]


# ---------------------------------------------------------------- (e) immagini e URL
def test_url_di_immagine_arbitrario_rifiutato(tmp, monkeypatch):
    gs = server_gs(tmp, monkeypatch)
    for cattivo in ("http://evil.local/x.jpg", "file:///c:/windows/win.ini", "//evil.local/x.jpg",
                    "/../../windows/win.ini", "", "x" * 600):
        with pytest.raises(HTTPException) as err:
            gs.get("artwork", src=cattivo, source="jellyfin")
        assert err.value.status_code == 400 and senza_stack(err.value.detail)


def test_plex_token_non_finisce_nelle_immagini(tmp, monkeypatch):
    """L'immagine è servita da Pozzo: nell'URL che vede la UI non c'è il token."""
    def handler(request):
        return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}))
    gs = FakeGS(cfg_for(tmp), "media-server")
    MS.register(gs)
    gs.post("config", {"source": "plex", "base_url": "http://plex.local:32400", "token": TOKEN})
    item = {"poster": f"/plugin-api/media-server/artwork?source=plex&src=/library/metadata/1/thumb"}
    assert TOKEN not in json.dumps(item)
    out = gs.get("artwork", src="/library/metadata/1/thumb", source="plex")
    assert out.body == b"img"
