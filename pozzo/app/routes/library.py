"""Libreria, scheda del gioco, azioni sul singolo gioco, collezioni, statistiche."""

from __future__ import annotations

import httpx
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse, Response

from ... import config as C, i18n as I, ownership as OW, platforms as P, profilecfg as PC, storelinks as SL, stores as STORES, webplay
from ...downloads.engines import torrent as TOR
from ...downloads.engines.http import safe_name as _safe_name
from ...library import automation as A, launcher as L
from ..icons import CREDIT
from ..server import STORE_NAMES, _hltb_main, _json, _players, _players_label


class ApiError(HTTPException):
    """HTTPException con un `code` stabile e `details` per l'interfaccia; `detail` resta il testo per la persona."""

    def __init__(self, status_code: int, detail: str, code: str, details: dict | None = None):
        super().__init__(status_code, detail)
        self.code, self.details = code, dict(details or {})


def launch_error(e: L.LaunchError, status: int = 409) -> HTTPException:
    """Errore di avvio come risposta: strutturato se ha un codice, come prima (solo testo) altrimenti."""
    return ApiError(status, str(e), e.code, e.details) if e.code else HTTPException(status, str(e))


def build_router(ctx) -> APIRouter:
    _media, _start_store_job, app, cfg, launcher, lib = ctx._media, ctx._start_store_job, ctx.app, ctx.cfg, ctx.launcher, ctx.lib
    lib_payloads, shots, user, view = ctx.lib_payloads, ctx.shots, ctx.user, ctx.view
    router = APIRouter()

    def _downloaded(ev):  # la pagina lo legge da /api/status (sincronizzazione ogni 3 s): avviso e scheda aggiornata
        ctx.state["downloaded"] = {**ev, "seq": (ctx.state.get("downloaded") or {}).get("seq", 0) + 1}
    ctx.events.on("game_downloaded", _downloaded)

    @app.exception_handler(ApiError)
    async def _api_error(request, exc: ApiError):
        return JSONResponse({"detail": exc.detail, "code": exc.code, "details": exc.details}, status_code=exc.status_code)

    # ------------------------------------------------------------ API
    @router.get("/api/library")
    def api_library(part: str = ""):
        """part='owned': solo i giochi posseduti (subito); 'online': solo il catalogo (dopo); vuoto: tutto."""
        if part != "owned":
            lib.full.wait()
        # la risposta dipende da libreria, dati utente e poche impostazioni: con le stesse, si restituisce quella gia' pronta
        ck = (lib.built_at, lib.meta_rev, user.rev, part, bool(cfg.app.get("skip_duplicates", True)),
              tuple(cfg.app.get("hide_dlc") or []),
              tuple(sorted((k, tuple(v or [])) for k, v in cfg.catalogs.items())),
              len(cfg.app.get("smart_collections") or []), PC.active(cfg))  # ultimo: il profilo (ognuno vede i suoi giochi)
        pid = ck[-1]
        hit = lib_payloads.get(ck)
        if hit is not None:
            return Response(content=hit, media_type="application/json")
        with lib.lock:
            sel = lib.games if not part else [g for g in lib.games if (g.get("store") == "online") == (part == "online")]
            if lib.has_owners:
                sel = [g for g in sel if OW.visible(g, pid)]
            grp_list = list(dict.fromkeys(g["grp"] for g in sel))
            v = view(grp_list)
            coll_list = sorted((c for c in v["colls"].values()), key=lambda c: c["name"].lower())
            coll_idx = {c["slug"]: i for i, c in enumerate(coll_list)}
            grp_colls: dict[str, list[int]] = defaultdict(list)
            for c in coll_list:
                for grp in c["groups"]:
                    grp_colls[grp].append(coll_idx[c["slug"]])
            grp_idx = {g: i for i, g in enumerate(grp_list)}
            groups = []
            for grp in grp_list:
                d = v["groups"][grp]
                groups.append([d["primary"], d["favorite"], d["hidden"], round(d["last_played"]), round(d["playtime"]),
                               d["play_count"], grp_colls.get(grp, []), len(OW.members(lib.groups[grp], pid)), d["status"]])
            del v  # i dati di 150.000 gruppi (~40 MB): non servono piu' mentre si scrive il JSON
            own = user.media_keys("cover")  # copertine scelte a mano: valgono anche per i giochi senza copertina dalle fonti
            rows = [[g["id"], g["title"], g["sort_title"], g["platform"], g["year"], int("cover" in g["media"] or g["key"] in own),
                     grp_idx[g["grp"]], g["rating"], g["developer"] or "", ", ".join(g["genres"]), g["found"],
                     g["region"] or "", g.get("store") or "", 1 if g.get("store") is None else g.get("installed") or 0,
                     g.get("size") or 0, g.get("rating_count") or 0, g.get("rating_critics"), _players(g.get("players"), g["platform"]),
                     round(sum(m.get("store_playtime") or 0 for m in lib.groups[g["grp"]]) / 60), _hltb_main(g.get("hltb")), g.get("content") or "game"]
                    for g in sel]
            plats = defaultdict(int)
            for members in lib.groups.values():
                m0 = (OW.members(members, pid) if lib.has_owners else members)[0]
                if OW.visible(m0, pid) and m0.get("store") != "online":  # i giochi solo online non contano come posseduti
                    plats[m0["platform"]] += 1
            for p, urls in cfg.catalogs.items():
                if urls:
                    plats[p] += 0  # console con uno store online ma senza giochi posseduti
            # JSON scritto qui: jsonable_encoder di FastAPI su ~150.000 righe costa secondi, json.dumps in un colpo ~200 MB
            body = _json({
                "built_at": lib.built_at, "user_rev": user.rev, "meta_rev": lib.meta_rev,
                "platforms": sorted(({"id": p, "name": P.PLATFORMS[p].name if p in P.PLATFORMS else p, "count": n}
                                     for p, n in plats.items()), key=lambda x: x["name"].lower()),
                "collections": [{"slug": c["slug"], "name": c["name"], "auto": c["auto"], "custom": c["custom"],
                                 "hidden": c.get("hidden", False), "count": len(c["groups"])} for c in coll_list],
                "skip_duplicates": cfg.app.get("skip_duplicates", True),
                "hide_dlc": cfg.app.get("hide_dlc") or [],
                "catalogs": {k: v for k, v in cfg.catalogs.items() if v}, "icons_credit": CREDIT,
                "games": {"cols": ["id", "title", "sort", "platform", "year", "cover", "group", "rating", "developer",
                                   "genres", "found", "region", "store", "installed", "size", "votes", "critics", "players", "store_minutes", "hltb", "content"],
                          "rows": rows},
                "stores": [{"id": p.id, "name": p.name} for p in STORES.PROVIDERS],
                "groups": {"cols": ["primary", "favorite", "hidden", "last_played", "playtime", "play_count",
                                    "collections", "versions", "status"], "rows": groups},
                "smart": cfg.app.get("smart_collections") or [],
            })
            # si tengono solo le parti (posseduti, catalogo, tutto) della libreria attuale: le vecchie sono ~26 MB l'una
            for k in [k for k in lib_payloads if k[:3] + k[4:-1] != ck[:3] + ck[4:-1]]:
                del lib_payloads[k]
            lib_payloads[ck] = body
            return Response(content=body, media_type="application/json")

    @router.get("/api/library/patches")
    def api_library_patches(since: int = 0):
        """Giochi cambiati dopo `since` senza ricostruire la libreria (copertine appena trovate o scaricate),
        nelle stesse colonne di /api/library: id, copertina, anno, sviluppatore, generi."""
        with lib.lock:
            if since < lib.patch_base:
                return {"rev": lib.meta_rev, "reset": True}
            ids = {i for rev, xs in lib.patches if rev > since for i in xs}
            pid = PC.active(cfg)
            own = user.media_keys("cover")
            rows = [[g["id"], int("cover" in g["media"] or g["key"] in own), g["year"], g["developer"] or "", ", ".join(g["genres"])]
                    for g in (lib.by_id.get(i) for i in ids) if g and OW.visible(g, pid)]
        return {"rev": lib.meta_rev, "games": rows}

    FIELD_LABELS = {"title": "s.library.field.title", "description": "s.library.field.description", "developer": "s.library.field.developer",
                    "publisher": "s.library.field.publisher", "genres": "s.library.field.genres", "release_date": "s.library.field.release_date",
                    "players": "s.library.field.players", "rating": "s.library.field.rating"}
    MEDIA_LABELS = {"cover": "s.library.media.cover", "screenshot": "s.library.media.screenshot", "title": "s.library.media.title",
                    "wheel": "s.library.media.wheel", "marquee": "s.library.media.marquee", "video": "s.library.media.video", "box3d": "s.library.media.box3d",
                    "fanart": "s.library.media.fanart"}

    def _missing(g: dict) -> list[str]:
        if not g["found"]:
            return [I.tr(FIELD_LABELS["title"])]
        out = [I.tr(FIELD_LABELS.get(f, f)) for f in cfg.fields
               if f != "title" and (g.get(f) in (None, "", []) if f in g else False)]
        out += [I.tr(MEDIA_LABELS.get(m, m)) for m in cfg.media if m not in g["media"]]
        return out

    @router.get("/api/home/resume")
    def api_home_resume():
        """«Riprendi»: i 3 giochi giocati di piu' di recente (non nascosti), con tempo giocato, ore di HowLongToBeat
        e ultimo salvataggio. Ogni dato sconosciuto e' null: la pagina non deve mai fallire per un gioco solo."""
        from ...library import saves as SV  # import locale come routes/saves.py
        pid, st, own = PC.active(cfg), user.games(), user.media_keys("cover")
        with lib.lock:
            keys = sorted((k for k, s in st.items() if s.get("last_played") and not s.get("hidden") and k in lib.by_key),
                          key=lambda k: -st[k]["last_played"])
            picks = []
            for k in keys:
                g = lib.by_key[k]
                if lib.has_owners and not OW.visible(g, pid):
                    continue
                picks.append((g, st[k]))
                if len(picks) == 3:
                    break
        items = []
        for g, s in picks:
            played = round(float(s.get("playtime") or 0))
            hours = _hltb_main(g.get("hltb"))  # ore: HowLongToBeat le da' in ore
            main = round(hours * 3600) if hours else None
            try:
                backups = SV.list_backups(cfg, g["key"])
                save = {"time": backups[0]["time"], "name": backups[0]["name"]} if backups else None
            except Exception:  # copia illeggibile o cartella mancante: la card resta senza salvataggio
                save = None
            items.append({"id": g["id"], "key": g["key"], "title": g["title"], "platform": g["platform"],
                          "cover": f"/img/{g['id']}/cover" if "cover" in g["media"] or g["key"] in own else None,
                          "played_secs": played, "hltb_main_secs": main,
                          "remaining_secs": max(0, main - played) if main is not None else None,
                          "last_played": s["last_played"], "save": save})
        return {"items": items}

    @router.get("/api/game/{gid}")
    def api_game(gid: int):
        g = lib.game(gid)
        v = view([g["grp"]])
        grp = v["groups"][g["grp"]]
        p = P.PLATFORMS.get(g["platform"])
        try:
            plan = L.plan(cfg, p, user.profile(g["key"])) if p else None
        except L.LaunchError:
            plan = None
        versions = [{"id": m["id"], "title": m["title"],
                     "file": (STORE_NAMES.get(m.get("store"), m.get("store")) if m.get("store")
                              else Path(m["files"][0]).name if m["files"] else m["title"]),
                     "region": m["region"], "store": m.get("store"), "installed": m.get("installed"),
                     "primary": m["id"] == grp["primary"]} for m in lib.groups[g["grp"]]]
        versions.sort(key=lambda x: (not x["primary"], x["file"].lower()))
        colls = [{"slug": c["slug"], "name": c["name"], "auto": c["auto"]}
                 for c in v["colls"].values() if g["grp"] in c["groups"]]
        return {**{k: g[k] for k in ("id", "key", "title", "platform", "year", "release_date", "developer", "publisher",
                                     "genres", "players", "rating", "description", "region", "files", "video_url",
                                     "canonical", "crc", "found")},
                "content": g.get("content") or "game",
                "platform_name": p.name if p else g["platform"],
                "media": {k: f"/img/{gid}/{k}" for k in _media(g)},
                "sources": json.loads(g["origin"] or "{}"),
                "user": grp, "versions": versions, "collections": sorted(colls, key=lambda c: c["name"].lower()),
                "missing": [] if g.get("store") else _missing(g),
                "rating_count": g.get("rating_count"), "rating_critics": g.get("rating_critics"),
                "players_local": _players_label(g.get("players"), g["platform"]),
                "profile": user.profile(g["key"]),
                "shots": len(shots.list([m["key"] for m in lib.groups[g["grp"]]])),
                "hltb": json.loads(g["hltb"]) if g.get("hltb") else None,
                "size": g.get("size"), "magnet": (g.get("launch") or {}).get("magnet") if g.get("store") == "online" else None,
                "download_sources": ((g.get("launch") or {}).get("sources") or []) if g.get("store") == "online" else [],
                "kind": (g.get("launch") or {}).get("kind") if g.get("store") == "online" else None,
                "file_name": g.get("canonical") if g.get("store") == "online" else None,
                "page_url": g.get("page") if g.get("store") == "online" else None,
                # pagine degli store online dove il gioco si puo' scaricare (anche se e' gia' in libreria)
                "store_pages": json.loads(g.get("store_pages") or "[]"),
                "ratings": json.loads(g.get("ratings") or "[]"),
                "store": g.get("store"), "store_name": STORE_NAMES.get(g.get("store"), ""),
                "installed": bool(g.get("installed")) if g.get("store") else True,
                # senza client: legendary/gogdl/nile (noclient.py)
                "can_install": bool(g.get("install_uri")) or g.get("store") in ("epic", "gog", "amazon"), "page": g.get("page"),
                "webplay": bool(webplay.plan(g)),
                "store_playtime": sum(m.get("store_playtime") or 0 for m in lib.groups[g["grp"]]),
                "ports": [] if g.get("store") else _port_links()["by_grp"].get(g["grp"], []),
                "emulator": (STORE_NAMES.get(g.get("store"), "PC") if g.get("store")
                             else (plan["emulator"] + (f" ({plan['core']})" if plan["core"] else "")) if plan else None)}

    def _member_keys(gid: int) -> list[str]:
        g = lib.get(gid)
        return [m["key"] for m in lib.groups[g["grp"]]]

    @router.post("/api/game/{gid}/flag")
    def api_flag(gid: int, body: dict = Body(...)):
        field, value = body.get("field"), body.get("value")
        if field not in ("favorite", "hidden", "status", "last_played", "note", "my_rating"):
            raise HTTPException(400, I.tr("s.library.badField"))
        if field == "note":
            value = str(value or "").strip()[:4000] or None
        elif field == "my_rating":
            if value not in (None, "", 0, 1, 2, 3, 4, 5):
                raise HTTPException(400, I.tr("s.library.badRating"))
            value = int(value) if value else None
        elif field == "last_played":  # "rimuovi da Giocati di recente": si azzera solo l'ultima partita, tempo e avvii restano
            value = None
        elif field == "status":
            if value not in ("", None, "backlog", "playing", "done", "dropped"):
                raise HTTPException(400, I.tr("s.library.badStatus"))
            value = value or None
        else:
            value = 1 if value else 0
        keys = _member_keys(gid)
        for k in keys:  # a livello di gioco: tutte le versioni
            user.set_flag(k, field, value)
        return {"ok": True}

    @router.post("/api/game/{gid}/preferred")
    def api_preferred(gid: int):
        g = lib.get(gid)
        for k in _member_keys(gid):
            user.set_flag(k, "preferred", "1" if k == g["key"] else None)
        return {"ok": True}

    @router.post("/api/game/{gid}/install")
    def api_install(gid: int):
        g = lib.game(gid)
        if not g.get("install_uri"):
            raise HTTPException(400, I.tr("s.library.noInstallLink"))
        if g["install_uri"].startswith("pozzo-netstore:"):  # cartella di rete: copia/estrazione/setup in background
            return ctx._netstore_install(g["install_uri"].split(":", 1)[1])
        try:
            L.open_uri(g["install_uri"])  # steam://install/<id>, com.epicgames.launcher://…?action=install: come il pulsante Installa del client
        except L.LaunchError as e:
            if not g.get("page"):
                raise HTTPException(409, str(e))
            try:  # client assente: almeno la pagina del gioco nello store
                L.open_uri(g["page"])
            except L.LaunchError:
                raise HTTPException(409, str(e))
        return {"ok": True}

    def _single_magnet(g: dict) -> str | None:
        """Magnet che scarica solo questo gioco da un torrent di set (Minerva), letto una volta dalla sua pagina."""
        from ... import catalog
        from ...cache import Cache
        pages = [s["url"] for s in (g.get("launch") or {}).get("sources") or [] if catalog.MINERVA_ROM.match(s.get("url") or "")]
        if not pages:
            return None
        c = Cache(cfg.cache)
        try:
            hit = c.kv_get("minerva:so:" + pages[0])
            if hit is None:
                try:
                    r = httpx.get(pages[0], timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
                    hit = catalog.single_file_magnet(r.text) if r.status_code == 200 else None
                except httpx.HTTPError:
                    return None  # rete giu': si riprova al prossimo clic
                c.kv_set("minerva:so:" + pages[0], hit or "")
            return hit or None
        finally:
            c.close()

    @router.post("/api/game/{gid}/torrent")
    def api_torrent(gid: int):
        g = lib.game(gid)
        mag = (g.get("launch") or {}).get("magnet")
        if not mag:
            raise HTTPException(400, I.tr("s.library.noMagnet"))
        single = _single_magnet(g)
        file = g.get("canonical") or g["title"]
        mgr = getattr(ctx, "downloads", None)  # costruito dopo questo modulo (ultimo in ORDER)
        if mgr and TOR.available():
            t = _game_task(gid)
            if t and t.status in ("paused", "error"):  # errore (es. nessun peer): si riprende, non un doppione
                mgr.resume(t.id)
            elif not t or t.status == "completed":
                dest = Path(mgr.settings()["dir"]) / re.sub(r'[<>:"/\\|?*]', "_", g.get("platform_name") or "Giochi")
                try:
                    t = mgr.add(single or mag, str(dest), name=file, wanted=g.get("file_name") or file, category="game", game_id=gid)
                except ValueError as e:
                    raise HTTPException(400, str(e))
            return {"ok": True, "single": True, "file": file, "internal": True, "dest": t.save_path, "task_id": t.id}
        try:
            L.open_uri(single or mag)
        except L.LaunchError:
            raise HTTPException(409, I.tr("s.library.noTorrentClient"))
        return {"ok": True, "single": bool(single) or "&so=" in mag or bool(re.search(r"dn=[^&]*\.", mag)),
                "file": g.get("canonical") or g["title"]}

    @router.get("/api/game/{gid}/torrent")
    def api_torrent_status(gid: int):
        t = _game_task(gid)
        if not t:
            return {"state": "idle"}
        state = {"completed": "done", "error": "error", "paused": "paused"}.get(t.status) or \
            ("downloading" if t.options.get("metadata") else "metadata")
        return {"state": state, "progress": t.progress, "error": t.error or None, "dest": t.save_path, "task_id": t.id}

    def _game_task(gid: int):
        mgr = getattr(ctx, "downloads", None)
        tasks = [t for t in (mgr.tasks.values() if mgr else []) if t.type == "torrent" and t.options.get("game_id") == gid]
        return max(tasks, key=lambda t: t.created, default=None)

    @router.post("/api/game/{gid}/store-page")
    def api_store_page(gid: int):
        g = lib.game(gid)
        if not g.get("page"):
            raise HTTPException(400, I.tr("s.library.noStorePage"))
        try:
            L.open_uri(g["page"])
        except L.LaunchError as e:
            raise HTTPException(409, str(e))
        return {"ok": True}

    def _download_pages(g: dict) -> list[str]:
        """Pagine degli store del gioco (una per sito), dove sono elencati i link di download."""
        urls = [s.get("url") for s in (g.get("launch") or {}).get("sources") or [] if isinstance(s, dict)]
        urls += [s.get("url") for s in json.loads(g.get("store_pages") or "[]") if isinstance(s, dict)]
        seen, out = set(), []
        for u in urls:
            if u and u.startswith("http") and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    @router.get("/api/game/{gid}/links")
    def api_game_links(gid: int, refresh: int = 0):
        """Tutti i link di download elencati nelle pagine del gioco: tipo (gioco/update/DLC), provider, parti."""
        g = lib.game(gid)
        pages = _download_pages(g)
        if not pages:
            raise HTTPException(404, I.tr("s.library.noDownloadPage"))
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            links, errors, fetched = [], [], 0
            for u in pages[:4]:
                data = None if refresh else SL.cached(c, u)
                if data is None:
                    if fetched >= 2:  # due pagine nuove per richiesta: le altre arrivano alla prossima apertura
                        continue
                    fetched += 1
                    try:
                        data = SL.put(c, u, SL.fetch(u))
                    except (httpx.HTTPError, ValueError, RuntimeError) as e:
                        errors.append(f"{SL.host(u)}: {type(e).__name__}")
                        continue
                site = data.get("site") or SL.host(u)
                links += [{**x, "page": u, "site": site} for x in data.get("links") or []]
            return {"pages": pages, "links": links, "error": "; ".join(errors),
                    "kind_labels": SL.KIND_LABELS, "kind_order": list(SL.KIND_ORDER)}
        finally:
            c.close()

    @router.get("/api/game/{gid}/paste")
    def api_game_paste(gid: int, url: str, refresh: int = 0):
        """Link contenuti in un paste dei filehoster (lo store linka il paste al posto dei file): si legge al clic."""
        if not url.startswith(("http://", "https://")):
            raise HTTPException(400, I.tr("s.library.badLink"))
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            data = None if refresh else SL.cached_paste(c, url)
            return data or SL.put_paste(c, url, SL.paste(url))
        except (httpx.HTTPError, ValueError, RuntimeError) as e:
            raise HTTPException(409, f"{SL.host(url)}: {e}" if str(e) else f"{SL.host(url)}: {type(e).__name__}")
        finally:
            c.close()

    @router.post("/api/game/{gid}/download")
    def api_game_download(gid: int, body: dict = Body(default={})):
        """Mette in coda i link scelti (anche più assieme). Accorciatore e pagina dell'host si risolvono
        all'avvio del download, quando c'è il browser nascosto dell'app a disposizione."""
        g = lib.game(gid)
        urls = [str(u) for u in body.get("links") or [] if str(u).startswith(("http", "magnet:"))][:80]
        if not urls:
            raise HTTPException(400, I.tr("s.library.noLinks"))
        mgr = getattr(ctx, "downloads", None)
        if not mgr:  # solo scansione da terminale: niente coda, si apre il browser
            try:
                for u in urls:
                    if u.startswith("http"):
                        L.open_uri(u)
            except (L.LaunchError, OSError) as e:
                raise HTTPException(409, str(e))
            return {"ok": True, "tasks": [], "failed": []}
        tasks, failed = [], []
        # più file (le parti di un archivio) in una cartella sola: l'estrazione parte quando ci sono tutte
        folder = str(Path(mgr.settings()["dir"]).expanduser() / _safe_name(g["title"])) if len(urls) > 1 else ""
        for u in urls:
            try:
                tasks.append(mgr.add(u, save_path=folder, category=g.get("platform") or "", game_id=gid).view())
            except ValueError as e:
                failed.append({"link": u, "error": str(e)})
        if not tasks:
            raise HTTPException(409, failed[0]["error"] if failed else I.tr("s.library.noLinkAdded"))
        return {"ok": True, "tasks": tasks, "failed": failed}

    @router.post("/api/game/{gid}/play")
    def api_play(gid: int, body: dict = Body(default={})):
        g = lib.game(gid)
        fast = isinstance(body, dict) and bool(body.get("fast"))  # chiamata diretta (API v1): body e' il default di Body  # «gioca da disco veloce»
        if g.get("store"):
            if not g.get("installed"):
                raise HTTPException(409, I.tr("s.library.notInstalledUseInstall"))
            launch = g["launch"]
            if g["store"] == "ports":  # i port chiedono come aprire la finestra, se non c'e' una scelta salvata
                from ... import ports as PT
                mode = PT.window_mode(cfg, g["key"].split("ports:", 1)[-1], body)
                if not mode:
                    return {"ask": "window"}
                launch = {**launch, "window": mode}
            try:
                launcher.launch_pc(g["key"], g["title"], launch, g.get("install_dir") or "",
                                   STORE_NAMES.get(g["store"], g["store"]), g["store"], fast=fast)
            except L.LaunchError as e:
                raise HTTPException(409, str(e))
            launcher.splash(gid, g["title"])
            return {"ok": True}
        p = P.PLATFORMS.get(g["platform"])
        path = next((Path(f) for f in g["files"] if Path(f).exists()), None)
        if not p or not path:
            folders = [str(Path(f).parent) for f in g["files"]]
            raise ApiError(404, I.tr("s.library.romMissing"), "rom_folder_missing",
                           {"path": folders[0] if folders else ""})
        try:
            fb = body.get("fallback") if isinstance(body, dict) else None  # candidato proposto dopo un crash
            launcher.launch(g["key"], g["title"], p, path, fast=fast, fallback=str(fb) if fb else None)
        except L.LaunchError as e:
            raise launch_error(e)
        launcher.splash(gid, g["title"])
        return {"ok": True}

    @router.post("/api/game/{gid}/shortcut")
    def api_shortcut(gid: int):
        """Collegamento sul desktop che avvia il gioco con PozzoLauncher (tempo di gioco, script, ecc.)."""
        from ...library import shortcut as SC
        from ...remote.sunshine import launcher_cmd
        g = lib.game(gid)  # serve "launch" (icona dell'exe), che non sta in memoria
        if g.get("store") == "online":
            raise HTTPException(400, I.tr("s.library.notInstalled"))
        launch = g.get("launch") or {}
        icon = launch.get("target") if g.get("store") and launch.get("type") != "uri" else None
        if not icon or not Path(icon).is_file():  # icona dalla copertina
            rel = lib.by_id[gid]["media"].get("cover") or lib.by_id[gid]["media"].get("header")
            src = Path(cfg.cache) / rel if rel and not rel.startswith("url:") else None
            icon = src and SC.make_icon(src, C.settings_path(cfg).parent / "shortcuts" / f"{gid}.ico")
        base, wd = launcher_cmd(cfg)
        try:
            lnk = SC.create(g["title"], base, wd, g["key"], str(icon) if icon else None)
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            raise HTTPException(500, str(e))
        return {"ok": True, "path": str(lnk)}

    # ------------------------------------------------------------ profilo di avvio del gioco
    @router.get("/api/game/{gid}/profile")
    def api_profile(gid: int):
        g = lib.get(gid)
        p = P.PLATFORMS.get(g["platform"])
        if g.get("store") == "online":
            raise HTTPException(400, I.tr("s.library.notInstalled"))
        if g.get("store"):  # giochi PC: solo gli script prima/dopo
            return {"profile": user.profile(g["key"]) or {}, "pc": True, "platform": STORE_NAMES.get(g["store"], "PC")}
        if not p:
            raise HTTPException(400, I.tr("s.library.unknownConsole"))
        base = L.plan(cfg, p)
        try:
            cur = L.plan(cfg, p, user.profile(g["key"]))
        except L.LaunchError as e:
            cur = {"error": str(e)}
        emus = [{"id": e, "configured": bool(cfg.emulators.get(e) and Path(cfg.emulators[e]).exists()),
                 "preset": any(x == e for x, _ in L.PRESETS.get(p.id, [])), "default_core": L.default_core(p.id, e),
                 "exe": cfg.emulators.get(e) or "",
                 "args": ["-L", "{core}", "{rom}"] if e == L.RA else L.STANDALONE_ARGS.get(e, ["{rom}"])}
                for e in L.EMULATOR_NAMES]
        cores = []
        if cfg.emulators.get(L.RA):
            cdir = L._core_path(cfg, "x").parent
            if cdir.is_dir():
                cores = sorted(f.name.split("_libretro")[0] for f in cdir.iterdir() if "_libretro" in f.name)
        return {"profile": user.profile(g["key"]) or {}, "default": base, "current": cur, "emulators": emus,
                "cores": cores, "platform": p.name}

    @router.post("/api/game/{gid}/profile")
    def api_profile_save(gid: int, body: dict = Body(...)):
        g = lib.get(gid)
        fields = (*L.SCRIPT_KEYS, *L.COMPANION_KEYS) if g.get("store") else \
            ("emulator", "core", "exe", "args", "extra", L.PRESET_KEY, *L.SCRIPT_KEYS, *L.COMPANION_KEYS)
        data = {k: str(body.get(k) or "").strip() for k in fields}
        if data.get("companion"):
            data["companion"] = data["companion"].strip('"')
            if not Path(data["companion"]).is_file():
                raise HTTPException(400, I.tr("s.library.companionMissing"))
        data = {k: v for k, v in data.items() if v}
        try:  # automazioni: solo da qui (API del desktop), mai dalle rotte del telefono
            if auto := A.clean(body.get(A.KEY)):
                data[A.KEY] = auto
        except ValueError:
            raise HTTPException(400, I.tr("s.library.badAuto"))
        if data.get("preset") not in (None, "inherit", "leave", "quality", "performance", "faithful"):
            raise HTTPException(400, I.tr("s.library.badPreset"))
        if data.get("emulator") and data["emulator"] not in L.EMULATOR_NAMES:
            raise HTTPException(400, I.tr("s.library.unknownEmu"))
        if data.get("exe") and not Path(data["exe"].strip('"')).is_file():
            raise HTTPException(400, I.tr("s.library.exeMissing"))
        if data.get("exe"):
            data["exe"] = data["exe"].strip('"')
        user.set_profile(_member_keys(gid), data or None)
        return api_profile(gid)

    @router.delete("/api/game/{gid}/profile")
    def api_profile_delete(gid: int):
        user.set_profile(_member_keys(gid), None)
        return api_profile(gid)

    @router.post("/api/game/{gid}/open-folder")
    def api_open_folder(gid: int):
        g = lib.get(gid)
        f = next((Path(x) for x in g["files"] if Path(x).exists()), None)
        if not f:
            raise HTTPException(404, I.tr("s.library.fileMissing"))
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(f)])
        else:
            subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(f.parent)])
        return {"ok": True}

    @router.post("/api/collections")
    def api_coll_create(body: dict = Body(...)):
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, I.tr("s.library.nameMissing"))
        slug = user.create_collection(name)
        if body.get("game"):
            for k in _member_keys(int(body["game"])):
                user.edit_membership(slug, k, "add")
        return {"slug": slug}

    @router.patch("/api/collections/{slug}")
    def api_coll_update(slug: str, body: dict = Body(...)):
        user.update_collection(slug, name=body.get("name"), hidden=body.get("hidden"))
        return {"ok": True}

    @router.delete("/api/collections/{slug}")
    def api_coll_delete(slug: str):
        if slug in lib.auto:  # le automatiche si nascondono, non si cancellano
            user.update_collection(slug, hidden=1)
        else:
            user.delete_collection(slug)
        return {"ok": True}

    @router.post("/api/collections/{slug}/members")
    def api_coll_members(slug: str, body: dict = Body(...)):
        action = body.get("action")
        if action not in ("add", "remove"):
            raise HTTPException(400, I.tr("s.library.badAction"))
        for k in _member_keys(int(body["game"])):
            user.edit_membership(slug, k, action)
        return {"ok": True}

    # ------------------------------------------------------------ port PC (ricompilazioni e decomp, catalogo di Quiver)
    from .. import ports_api
    _port_links = ports_api.register(app, cfg, lib, launcher, _start_store_job)

    # ------------------------------------------------------------ statistiche
    @router.get("/api/stats")
    def api_stats(year: int = 0):
        import datetime as _dt
        v = view()
        by_key = lib.by_key
        y = year or _dt.date.today().year
        start = _dt.datetime(y, 1, 1).timestamp()
        end = _dt.datetime(y + 1, 1, 1).timestamp()
        per_game: dict = defaultdict(float)
        months = [0.0] * 12
        years: dict = defaultdict(float)
        for key, st, sec in user.sessions():
            g = by_key.get(key)
            years[_dt.datetime.fromtimestamp(st).year] += sec
            if g and start <= st < end:
                per_game[g["grp"]] += sec
                months[_dt.datetime.fromtimestamp(st).month - 1] += sec
        top_year = []
        for grp, sec in sorted(per_game.items(), key=lambda x: -x[1])[:15]:
            d = v["groups"].get(grp) or {}
            g = lib.get(d.get("primary")) if d.get("primary") else None
            if g:
                top_year.append({"id": g["id"], "title": g["title"], "platform": g.get("store") or g["platform"], "seconds": sec})
        return {"year": y, "months": months, "years": dict(sorted(years.items())), "top_year": top_year}

    vars(ctx).update(_member_keys=_member_keys, _missing=_missing, api_play=api_play)
    return router
