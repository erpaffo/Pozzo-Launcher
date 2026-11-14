"""Download BitTorrent: una sessione libtorrent per tutto il manager, solo i file scelti, ripresa dai resume data."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
import time
from pathlib import Path
from urllib.parse import urlsplit

from ..task import mb

try:
    import libtorrent as lt
except ImportError:  # senza libtorrent i torrent non entrano in coda (e il dettaglio gioco ripiega sul client di sistema)
    lt = None

log = logging.getLogger("pozzo.downloads.torrent")
POLL = 0.5
RESUME_EVERY = 30
FILES_EVERY = 3  # s: ogni quanto si rifa l'elenco file della vista (avanzamento per file)
META_TIMEOUT = 240  # secondi: un magnet senza peer non tiene occupato un posto della coda per sempre
STALL_AFTER = 60  # secondi senza seed e senza dati prima di dichiarare il download «in stallo»
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


_IP4 = r"\d{1,3}(?:\.\d{1,3}){3}"
_RANGE = re.compile(rf"({_IP4})\s*-\s*({_IP4})(?!.*{_IP4}\s*-)")  # PeerGuardian .dat/.p2p: l'ultimo intervallo della riga
_CIDR = re.compile(r"\s*([0-9a-fA-F:.]+/\d{1,3})\s*")


def _ip(a: str) -> str:
    return str(ipaddress.ip_address(".".join(str(int(x)) for x in a.split("."))))  # .dat scrive 001.002.003.004


def parse_ip_filter(path) -> list[tuple[str, str]]:
    """Intervalli (primo, ultimo) da un file PeerGuardian (.dat, .p2p) o da un elenco di CIDR, uno per riga.
    OSError se non si legge, ValueError (con la riga) se qualcosa non si capisce: il filtro non si applica a meta'."""
    out = []
    for n, line in enumerate(Path(path).read_text("utf-8", errors="replace").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(("#", "//")):
            continue
        try:
            if m := _RANGE.search(line):
                a, b = _ip(m[1]), _ip(m[2])
            elif m := _CIDR.fullmatch(line):
                net = ipaddress.ip_network(m[1], strict=False)
                a, b = str(net[0]), str(net[-1])
            else:
                raise ValueError("formato sconosciuto")
        except ValueError as e:
            raise ValueError(f"IP filter, riga {n}: {e}")
        out.append((a, b))
    return out


def check_magnet(source: str):
    """Errore subito (all'aggiunta) per un magnet illeggibile, non alla partenza."""
    if source.lower().startswith("magnet:"):
        try:
            lt.parse_magnet_uri(source)
        except RuntimeError as e:
            raise ValueError(f"Magnet non valido: {e}")


def _layout(ti):
    return ti.layout() if hasattr(ti, "layout") else ti.files()  # files() deprecato da libtorrent 2.1


_NXDOMAIN = {socket.EAI_NONAME, getattr(socket, "EAI_NODATA", socket.EAI_NONAME)}


async def _is_resolvable(url: str) -> bool | None:
    """True = il nome si risolve, False = il nome non esiste, None = non si sa (DNS lento, rete giu', IP, host di
    test): nel dubbio il tracker resta e decide libtorrent, che riprova da solo con attese crescenti."""
    host = urlsplit(url).hostname
    if not host:
        return False
    if host.endswith((".example", ".test", ".invalid", ".localhost")) or host in ("127.0.0.1", "::1"):
        return None
    try:
        socket.inet_aton(host)
        return None
    except OSError:
        pass
    try:
        await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo, host, None), timeout=5)
        return True
    except socket.gaierror as e:
        return False if e.errno in _NXDOMAIN else None
    except Exception:  # noqa: BLE001 - timeout o altro: non e' una prova che il tracker non esista
        return None


def _permanent(a) -> bool:
    """Errore del tracker che riprovare non risolve (annuncio sparito, protocollo non supportato). Timeout, rete giu',
    DNS che non risponde passano: quei tracker li riprova libtorrent con la sua attesa crescente."""
    cat, code = a.error.category().name(), a.error.value()
    return (cat == "http" and code in (404, 410)) or (cat == "libtorrent" and code == 24)  # 24: unsupported URL protocol


class Engine:
    """La sessione condivisa (creata al primo torrent) e i torrent attivi, per task id."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)  # resume data: <task id>.fastresume
        self.ses = None
        self.handles: dict = {}
        self._pack: dict = {}
        self._resume: dict = {}  # task id -> bytes appena arrivati dall'alert
        self.logs: dict = {}  # task id -> task.log: tracker e errori dei file arrivano come alert
        self._warned_trackers: set[tuple[str, str]] = set()  # (tid, tracker_key) gia' avvisati di errore
        # task id -> url tracker che non funzioneranno mai (nome inesistente, annuncio sparito): non si riprovano, neanche
        # dopo un riavvio (options["bad_trackers"]), e il loro errore non riempie il registro a ogni annuncio
        self.dead_trackers: dict[str, set[str]] = {}
        self.trackers: list[str] = []  # aggiunti a ogni torrent
        self.pex = True
        self.seed = (0.0, 0)  # (rapporto, minuti) di condivisione dopo la fine; (0, 0) = nessuna
        self.ip_path = ""  # file dei blocchi IP in uso; ip_error = perche' non e' applicato ("" se va)
        self.ip_error = ""
        self._ranges: list = []

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
                "announce_to_all_trackers": True, "announce_to_all_tiers": True,
                "tracker_completion_timeout": 15, "tracker_receive_timeout": 5,
                "alert_mask": lt.alert_category.status | lt.alert_category.storage | lt.alert_category.error | lt.alert_category.tracker}
        self.pex = bool(disc.get("pex"))  # per torrent (flag disable_pex): l'estensione non si toglie da una sessione aperta
        self.seed = (float(s.get("seed_ratio") or 0), int(s.get("seed_minutes") or 0))
        if pack != self._pack:
            self._pack = pack
            if self.ses:
                self.ses.apply_settings(pack)
        path = str(s.get("ip_filter_path") or "")
        if path != self.ip_path:
            self.ip_path, self._ranges, self.ip_error = path, [], ""
            if path:
                try:
                    self._ranges = parse_ip_filter(Path(path).expanduser())
                except (OSError, ValueError) as e:
                    self.ip_error = str(e)
                    log.warning("IP filter ignorato: %s", e)
            self._apply_ip_filter()
        trackers = list(s.get("trackers") or [])
        if trackers != self.trackers:
            self.trackers = trackers
            for h in list(self.handles.values()):
                try:
                    self.add_trackers(h)
                    h.force_reannounce()
                except RuntimeError:  # appena tolto dalla sessione
                    pass

    def _apply_ip_filter(self):
        if self.ses:
            f = lt.ip_filter()
            for a, b in self._ranges:
                f.add_rule(a, b, 1)  # 1 = bloccato
            self.ses.set_ip_filter(f)

    def add_trackers(self, h, task=None):
        tid = getattr(task, "id", "") or next((k for k, v in self.handles.items() if v == h), "")
        dead = self.dead_trackers.get(tid, set())
        have = {e["url"] for e in h.trackers()}
        for url in self.trackers:
            if url not in have and url not in dead:
                h.add_tracker({"url": url, "tier": 0})

    def blacklist_tracker(self, tid: str, url: str):
        self.dead_trackers.setdefault(tid, set()).add(url)
        h = self.handles.get(tid)
        if h and h.is_valid():
            try:
                tr = h.trackers()
                changed = False
                for t in tr:
                    if t["url"] == url and t.get("fail_limit") != 1:
                        t["fail_limit"] = 1
                        changed = True
                if changed:
                    h.replace_trackers(tr)
            except RuntimeError:
                pass

    def session(self):
        if self.ses is None:
            try:  # stato salvato (DHT ecc.); le impostazioni correnti si riapplicano subito dopo
                self.ses = lt.session(lt.read_session_params((self.folder / "session.dat").read_bytes()))
                self.ses.apply_settings(self._pack)
            except Exception:  # file assente/rovinato o libtorrent vecchio
                self.ses = lt.session(self._pack)
            self._apply_ip_filter()
        return self.ses

    def close(self):
        self.handles.clear()
        if self.ses:
            try:  # stato della sessione su disco, atomico
                self.folder.mkdir(parents=True, exist_ok=True)
                f = self.folder / "session.dat"
                tmp = f.with_suffix(".tmp")
                tmp.write_bytes(lt.write_session_params_buf(self.ses.session_state()))
                tmp.replace(f)
            except Exception:
                pass
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
                    err = a.error
                    msg = (a.error_message() or err.message()).strip()
                    if err.value() not in (180, 10051, 10065) and "unreachable" not in msg.lower() and "non raggiungibile" not in msg.lower():
                        url, perm = a.tracker_url(), _permanent(a)
                        key = (tid, host or url, perm)
                        if key not in self._warned_trackers:  # una riga per tracker, non una per tentativo
                            self._warned_trackers.add(key)
                            self.logs[tid](f"Tracker {host}: {msg} ({'non riprovato' if perm else 'riprovo più tardi'})", "warn")
                        if perm:
                            self.blacklist_tracker(tid, url)
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
        self._warned_trackers = {k for k in self._warned_trackers if k[0] != tid}
        self.dead_trackers.pop(tid, None)
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
        dead = set(task.options.get("bad_trackers") or [])
        urls = [u for u in dict.fromkeys(p.trackers) if u not in dead]
        found = await asyncio.gather(*(_is_resolvable(u) for u in urls))
        dns = True in found  # nessun nome risolto: rete o DNS giu', un «non esiste» ora non e' una prova
        valid = []
        for u, ok in zip(urls, found):
            if ok is False and dns:
                dead.add(u)
                task.log(f"Tracker {urlsplit(u).hostname or u}: il nome non esiste (escluso)", "warn")
            else:
                valid.append(u)
        eng.dead_trackers[task.id] = dead
        task.options["bad_trackers"] = list(dead)
        p.trackers = valid
        p.tracker_tiers = [0] * len(valid)
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


async def run(task, eng: Engine, client, on_complete=lambda: None, gate=None) -> None:
    """Scarica i file scelti di `task`, poi condivide finche' non arriva a eng.seed (rapporto o minuti; chiama on_complete
    alla fine dello scaricamento) e toglie il torrent dalla sessione. Lo stato sta in task.options. `gate`: attesa di un
    posto nella coda quando i metadati arrivano dopo l'attesa (nell'attesa il manager non conta il magnet tra i posti)."""
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
    dead = set(task.options.get("bad_trackers") or [])
    if dead:
        eng.dead_trackers.setdefault(task.id, set()).update(dead)
        current = h.trackers()
        new_tr = [t for t in current if t["url"] not in dead]
        if len(new_tr) != len(current):
            h.replace_trackers(new_tr)
    # elenco della 0.18 e prima: dentro anche tracker solo lenti o caduti per un momento. Si butta una volta e i
    # tracker del magnet tolti allora (spariti anche dai resume data) tornano
    if task.options.pop("dead_trackers", None) and task.source.strip().lower().startswith("magnet:"):
        have = {e["url"] for e in h.trackers()}
        for u in lt.parse_magnet_uri(task.source.strip()).trackers:
            if u not in have and u not in dead:
                h.add_tracker({"url": u, "tier": 0})
    try:
        tr = h.trackers()
        for e in tr:
            e["tier"] = 0  # tutti insieme; fail_limit resta 0: libtorrent riprova con attese crescenti
        h.replace_trackers(tr)
    except RuntimeError:
        pass
    eng.add_trackers(h, task)
    h.force_reannounce()
    task.log("Torrent aggiunto alla sessione" + (" (ripresa dai resume data)" if resumed else "") + f", {len(h.trackers())} tracker")
    if task.options.pop("recheck", None):
        h.force_recheck()
        task.log("Ricontrollo dei file su disco")
    ready, last_save, start, seeding = False, time.monotonic(), time.monotonic(), 0.0
    state, peers, meta, mile, idle_since, waited = None, False, False, None, None, False
    fcache = None  # (priorita', quando, indici dei file voluti, byte voluti, finito) dell'ultimo elenco file costruito
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
            waited = waited or not s.has_metadata
            task.options.update(metadata=s.has_metadata, peers=s.num_peers, seeds=s.num_seeds, upload_rate=s.upload_rate,
                                sequential=bool(task.options.get("sequential")), ratio=_ratio(s), trackers=len(h.trackers()),
                                bad_trackers=list(eng.dead_trackers.get(task.id, set())))
            # in stallo: scarica ma non c'e' nessun seed e non arriva un byte (i peer parziali non bastano)
            idle = st == "downloading" and not s.num_seeds and s.download_rate < 1
            idle_since = (idle_since or time.monotonic()) if idle else None
            stalled = bool(idle_since and time.monotonic() - idle_since > STALL_AFTER)
            if stalled != bool(task.options.get("stalled")):
                task.log("Download in stallo: nessun seed disponibile" if stalled else "Il download è ripartito", "warn" if stalled else "info")
            task.options["stalled"] = stalled
            if not s.has_metadata and time.monotonic() - start > META_TIMEOUT:
                raise ValueError("Nessun peer ha mandato l'elenco dei file del torrent in 4 minuti: riprova più tardi con «Riprendi»")
            if s.has_metadata:
                ti = h.torrent_file()
                fs = _layout(ti)
                if not meta:
                    if gate and waited:  # magnet: il posto lasciato nell'attesa dei metadati si riprende in coda
                        await gate()  # nessun byte intanto: i file hanno ancora priorita' 0 (default_dont_download)
                        task.phase = ""
                        task.options["metadata"] = True  # subito: col False di prima il tick lo terrebbe fuori dai posti
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
                # l'elenco file (con l'avanzamento di ognuno) si rifa ogni FILES_EVERY s, subito se cambiano le priorita' e
                # una volta a fine scarico: a ogni giro, con migliaia di file, era lavoro e dati per nulla. done/size restano esatti
                if fcache and fcache[0] == prio and time.monotonic() - fcache[1] < FILES_EVERY and \
                        (fcache[4] or sum(prog[i] for i in fcache[2]) < fcache[3]):
                    wanted, task.size = fcache[2], fcache[3]
                else:
                    files = [{"index": i, "name": fs.file_path(i), "size": fs.file_size(i), "priority": prio[i],
                              "progress": prog[i] / fs.file_size(i) if fs.file_size(i) else 1.0}
                             for i in range(fs.num_files()) if not fs.file_flags(i) & lt.file_storage.flag_pad_file]
                    task.options["files"] = files
                    wanted, task.size = [f["index"] for f in files if f["priority"]], sum(f["size"] for f in files if f["priority"])
                    fcache = (prio, time.monotonic(), wanted, task.size, sum(prog[i] for i in wanted) >= task.size)
                task.done = sum(prog[i] for i in wanted)
                if not task.size:
                    raise ValueError("Nessun file selezionato")
                m = task.done * 10 // task.size
                if mile is None or m < mile:
                    mile = m  # prima lettura (o ricontrollo): da qui in avanti si registra
                elif m > mile:
                    mile = m
                    task.log(f"Avanzamento {m * 10}% ({mb(task.done)} di {mb(task.size)})")
                if task.done >= task.size:
                    ratio, minutes = task.options.get("seed_limits") or eng.seed  # quelli della categoria prevalgono
                    if not seeding and (ratio or minutes):
                        await eng.save(task.id)
                        seeding = time.monotonic()
                        on_complete()  # completato per la coda; il torrent resta a condividere
                    if not (ratio or minutes) or (ratio and _ratio(s) >= ratio) or (minutes and time.monotonic() - seeding >= minutes * 60):
                        if seeding:
                            task.options["seed_reached"] = True  # il manager applica l'azione (pausa o rimuovi)
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
