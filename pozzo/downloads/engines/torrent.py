"""Download BitTorrent: una sessione libtorrent per tutto il manager, solo i file scelti, ripresa dai resume data."""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from ..task import mb

try:
    import libtorrent as lt
except ImportError:  # senza libtorrent i torrent non entrano in coda (e il dettaglio gioco ripiega sul client di sistema)
    lt = None

POLL = 0.5
RESUME_EVERY = 30
META_TIMEOUT = 240  # secondi: un magnet senza peer non tiene occupato un posto della coda per sempre
PRIORITIES = (0, 1, 4, 7)  # salta, normale, alta, massima
ENCRYPTION = {"prefer": (1, 3), "require": (0, 2), "disable": (2, 1)}  # -> (in/out_enc_policy, allowed_enc_level)


STATES = {"checking_files": "controllo dei file", "downloading_metadata": "scarico i metadati", "downloading": "download",
          "finished": "scaricato", "seeding": "condivisione", "checking_resume_data": "controllo dei dati di ripresa"}


def available() -> bool:
    return lt is not None


def is_torrent(source: str) -> bool:
    s = source.strip().lower()
    return s.startswith("magnet:") or s.split("?", 1)[0].endswith(".torrent")


def _so_indexes(magnet: str) -> set[int]:
    out: set[int] = set()
    m = re.search(r"[?&]so=([\d,-]+)", magnet)
    for part in (m.group(1).split(",") if m else []):
        a, _, b = part.partition("-")
        if a.isdigit():
            out.update(range(int(a), int(b or a) + 1))
    return out


def pick_files(names: list[str], magnet: str, wanted: str) -> set[int]:
    """Indici dei file da scaricare: quelli di so=<indice> (BEP 53), altrimenti quelli il cui nome contiene `wanted`."""
    so = {i for i in _so_indexes(magnet) if i < len(names)}
    if so:
        return so
    w = wanted.lower().strip()
    return {i for i, n in enumerate(names) if w and w in Path(n).name.lower()}


def check_magnet(source: str):
    """Errore subito (all'aggiunta) per un magnet illeggibile, non alla partenza."""
    if source.lower().startswith("magnet:"):
        try:
            lt.parse_magnet_uri(source)
        except RuntimeError as e:
            raise ValueError(f"Magnet non valido: {e}")


def _layout(ti):
    return ti.layout() if hasattr(ti, "layout") else ti.files()  # files() deprecato da libtorrent 2.1


class Engine:
    """La sessione condivisa (creata al primo torrent) e i torrent attivi, per task id."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)  # resume data: <task id>.fastresume
        self.ses = None
        self.handles: dict = {}
        self._pack: dict = {}
        self._resume: dict = {}  # task id -> bytes appena arrivati dall'alert
        self.logs: dict = {}  # task id -> task.log: tracker e errori dei file arrivano come alert
        self.trackers: list[str] = []  # aggiunti a ogni torrent
        self.pex = True
        self.seed = (0.0, 0)  # (rapporto, minuti) di condivisione dopo la fine; (0, 0) = nessuna

    def configure(self, s: dict):
        """Impostazioni del manager (limiti gia' scelti tra normali e «lenti»)."""
        disc = s.get("discovery") or {}
        pol, lvl = ENCRYPTION.get(s.get("encryption"), ENCRYPTION["prefer"])
        pack = {"listen_interfaces": f"0.0.0.0:{int(s.get('port') or 0)},[::]:{int(s.get('port') or 0)}",
                "enable_dht": bool(disc.get("dht")), "enable_lsd": bool(disc.get("lsd")),
                "enable_upnp": bool(disc.get("upnp")), "enable_natpmp": bool(disc.get("upnp")),
                "in_enc_policy": pol, "out_enc_policy": pol, "allowed_enc_level": lvl,
                "download_rate_limit": int(s.get("limit_down") or 0) * 1024,
                "upload_rate_limit": int(s.get("limit_up") or 0) * 1024,
                "alert_mask": lt.alert_category.status | lt.alert_category.storage | lt.alert_category.error | lt.alert_category.tracker}
        self.pex = bool(disc.get("pex"))  # per torrent (flag disable_pex): l'estensione non si toglie da una sessione aperta
        self.seed = (float(s.get("seed_ratio") or 0), int(s.get("seed_minutes") or 0))
        if pack != self._pack:
            self._pack = pack
            if self.ses:
                self.ses.apply_settings(pack)
        trackers = list(s.get("trackers") or [])
        if trackers != self.trackers:
            self.trackers = trackers
            for h in list(self.handles.values()):
                try:
                    self.add_trackers(h)
                except RuntimeError:  # appena tolto dalla sessione
                    pass

    def add_trackers(self, h):
        have = {e["url"] for e in h.trackers()}
        for url in self.trackers:
            if url not in have:
                h.add_tracker({"url": url, "tier": 100})  # dopo quelli del torrent

    def session(self):
        if self.ses is None:
            self.ses = lt.session(self._pack)
        return self.ses

    def close(self):
        self.handles.clear()
        self.ses = None  # il distruttore chiude la sessione (pochi istanti: annunci di stop ai tracker)

    def resume_file(self, tid: str) -> Path:
        return self.folder / f"{tid}.fastresume"

    def _pump(self):
        for a in self.ses.pop_alerts():
            tid = next((k for k, h in self.handles.items() if h == getattr(a, "handle", None)), None)
            if not tid:
                continue
            if isinstance(a, (lt.save_resume_data_alert, lt.save_resume_data_failed_alert)):
                self._resume[tid] = lt.write_resume_data_buf(a.params) if isinstance(a, lt.save_resume_data_alert) else b""
            elif tid in self.logs:  # del tracker solo l'host: il percorso puo' contenere la passkey
                host = urlsplit(a.tracker_url()).hostname if isinstance(a, (lt.tracker_error_alert, lt.tracker_reply_alert)) else ""
                if isinstance(a, lt.tracker_error_alert):
                    self.logs[tid](f"Tracker {host}: {a.error_message() or a.error.message()}", "warn")
                elif isinstance(a, lt.tracker_reply_alert):
                    self.logs[tid](f"Tracker {host}: {a.num_peers} peer")
                elif isinstance(a, (lt.file_error_alert, lt.torrent_error_alert)):
                    self.logs[tid](a.message(), "error")

    async def save(self, tid: str):
        """Chiede i resume data e li scrive su disco (con i metadati: un magnet riparte senza riscaricarli)."""
        h = self.handles.get(tid)
        if not h or not h.status().has_metadata:
            return
        self._resume.pop(tid, None)
        h.save_resume_data(lt.torrent_handle.save_info_dict | lt.torrent_handle.flush_disk_cache)
        for _ in range(100):
            self._pump()
            if tid in self._resume:
                buf = self._resume.pop(tid)
                if buf:
                    self.folder.mkdir(parents=True, exist_ok=True)
                    tmp = self.resume_file(tid).with_suffix(".tmp")
                    tmp.write_bytes(buf)
                    tmp.replace(self.resume_file(tid))
                return
            await asyncio.sleep(0.02)

    async def remove(self, tid: str):
        h = self.handles.pop(tid, None)
        if not h or not self.ses:
            return
        self.ses.remove_torrent(h)  # i file restano
        for _ in range(100):  # la rimozione e' asincrona: un «riprendi» immediato troverebbe il torrent ancora li'
            if not h.is_valid():
                return
            self._pump()
            await asyncio.sleep(0.02)


async def _params(task, eng: Engine, client):
    rf = eng.resume_file(task.id)
    if rf.exists():
        try:
            return lt.read_resume_data(rf.read_bytes())
        except RuntimeError:
            rf.unlink(missing_ok=True)  # rovinato: si riparte dal magnet/.torrent (libtorrent ricontrolla i file)
    src = task.source.strip()
    if src.lower().startswith("magnet:"):
        p = lt.parse_magnet_uri(src)
        p.flags |= lt.torrent_flags.default_dont_download  # niente byte prima di aver scelto i file
        return p
    if src.lower().startswith(("http://", "https://")):
        r = await client.get(src)
        r.raise_for_status()
        data = r.content
    else:
        data = await asyncio.to_thread(Path(src).expanduser().read_bytes)
    p = lt.add_torrent_params()
    try:
        p.ti = lt.torrent_info(data)
    except RuntimeError as e:
        raise ValueError(f"File .torrent non valido: {e}")
    p.file_priorities = [0] * p.ti.num_files()
    return p


def _select(task, h) -> list[int]:
    """Priorita' per file: quelle salvate (scelte dalla persona) oppure la scelta iniziale (wanted / so=)."""
    fs = _layout(h.torrent_file())
    n = fs.num_files()
    saved = task.options.get("priorities")
    if saved:
        return [int(saved.get(str(i), 0)) for i in range(n)]
    names = [fs.file_path(i) for i in range(n)]
    wanted = str(task.options.get("wanted") or "")
    if wanted or _so_indexes(task.source):
        chosen = pick_files(names, task.source, wanted)
        if not chosen:
            raise ValueError(f"File «{wanted}» non trovato nel torrent")
        return [4 if i in chosen else 0 for i in range(n)]
    return [4] * n


def _ratio(s) -> float:
    return round(s.all_time_upload / max(s.total_wanted_done, 1), 3)


async def run(task, eng: Engine, client, on_complete=lambda: None) -> None:
    """Scarica i file scelti di `task`, poi condivide finche' non arriva a eng.seed (rapporto o minuti; chiama on_complete
    alla fine dello scaricamento) e toglie il torrent dalla sessione. Lo stato sta in task.options."""
    dest = Path(task.save_path).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    resumed = eng.resume_file(task.id).exists()
    p = await _params(task, eng, client)
    p.save_path = str(dest)
    p.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)  # la coda la fa il manager, non libtorrent
    ses = eng.session()
    try:
        h = ses.add_torrent(p)
    except RuntimeError as e:
        raise ValueError(f"Torrent non aggiunto: {e}")
    eng.handles[task.id] = h
    eng.logs[task.id] = task.log
    eng.add_trackers(h)
    task.log("Torrent aggiunto alla sessione" + (" (ripresa dai resume data)" if resumed else "") + f", {len(h.trackers())} tracker")
    if task.options.pop("recheck", None):
        h.force_recheck()
        task.log("Ricontrollo dei file su disco")
    ready, last_save, start, seeding = False, time.monotonic(), time.monotonic(), 0.0
    state, peers, meta, mile = None, False, False, None
    try:
        while True:
            eng._pump()
            for flag, on in ((lt.torrent_flags.sequential_download, task.options.get("sequential")),
                             (lt.torrent_flags.disable_pex, not eng.pex)):
                h.set_flags(flag) if on else h.unset_flags(flag)
            s = h.status()
            if s.errc.value():
                raise OSError(s.errc.message())
            st = str(s.state).rsplit(".", 1)[-1]
            if st != state:
                state = st
                task.log(f"Stato: {STATES.get(st, st)}")
            if bool(s.num_peers) != peers:
                peers = bool(s.num_peers)
                task.log(f"{s.num_peers} peer connessi ({s.num_seeds} seed)" if peers else "Nessun peer connesso", "info" if peers else "warn")
            if not s.num_peers:
                for peer in task.options.get("connect") or []:  # peer noti "ip:porta" (test, rete locale)
                    ip, _, port = str(peer).rpartition(":")
                    h.connect_peer((ip, int(port)))
            task.options.update(metadata=s.has_metadata, peers=s.num_peers, seeds=s.num_seeds, upload_rate=s.upload_rate,
                                sequential=bool(task.options.get("sequential")), ratio=_ratio(s), trackers=len(h.trackers()))
            if not s.has_metadata and time.monotonic() - start > META_TIMEOUT:
                raise ValueError("Nessun peer ha mandato l'elenco dei file del torrent in 4 minuti: riprova più tardi con «Riprendi»")
            if s.has_metadata:
                ti = h.torrent_file()
                fs = _layout(ti)
                if not meta:
                    meta = True
                    real = [i for i in range(fs.num_files()) if not fs.file_flags(i) & lt.file_storage.flag_pad_file]
                    task.log(f"Metadati ricevuti: {ti.name()}, {len(real)} file, {mb(ti.total_size())}")
                if not ready:
                    prio = _select(task, h)
                    task.log(f"File scelti: {sum(1 for i in real if prio[i])} di {len(real)}")
                    task.options["priorities"] = {str(i): v for i, v in enumerate(prio)}
                    h.prioritize_files(prio)
                    if not task.name:  # il nome del set («Minerva_Myrient») non dice niente: con un file solo vale il suo nome
                        chosen = [i for i in real if prio[i]]
                        task.name = Path(fs.file_path(chosen[0])).stem if len(chosen) == 1 else ti.name()
                    ready = True
                prio = [int(task.options["priorities"].get(str(i), 0)) for i in range(fs.num_files())]
                prog = h.file_progress()
                files = [{"index": i, "name": fs.file_path(i), "size": fs.file_size(i), "priority": prio[i],
                          "progress": prog[i] / fs.file_size(i) if fs.file_size(i) else 1.0}
                         for i in range(fs.num_files()) if not fs.file_flags(i) & lt.file_storage.flag_pad_file]
                task.options["files"] = files
                task.size = sum(f["size"] for f in files if f["priority"])
                task.done = sum(prog[f["index"]] for f in files if f["priority"])
                if not task.size:
                    raise ValueError("Nessun file selezionato")
                m = task.done * 10 // task.size
                if mile is None or m < mile:
                    mile = m  # prima lettura (o ricontrollo): da qui in avanti si registra
                elif m > mile:
                    mile = m
                    task.log(f"Avanzamento {m * 10}% ({mb(task.done)} di {mb(task.size)})")
                if task.done >= task.size:
                    ratio, minutes = eng.seed
                    if not seeding and (ratio or minutes):
                        await eng.save(task.id)
                        seeding = time.monotonic()
                        on_complete()  # completato per la coda; il torrent resta a condividere
                    if not (ratio or minutes) or (ratio and _ratio(s) >= ratio) or (minutes and time.monotonic() - seeding >= minutes * 60):
                        break
            if time.monotonic() - last_save > RESUME_EVERY:
                await eng.save(task.id)
                last_save = time.monotonic()
            await asyncio.sleep(POLL)
        await eng.save(task.id)  # completato: altri file scelti dopo ripartono senza ricontrollare
    except asyncio.CancelledError:
        task.log("Sospeso: salvo i dati per riprendere")
        await eng.save(task.id)
        raise
    finally:
        eng.logs.pop(task.id, None)
        await eng.remove(task.id)
