"""Sostituisce le stringhe italiane di pozzo/app/routes/{appsettings,scan,stores,gameinfo,mods,verify,shots,stream}.py con I.tr(...)
e scrive il catalogo scratch/i18n/sq.it.json. Ogni sostituzione richiede il numero atteso di occorrenze."""

import json
import re
from pathlib import Path

ROOT = Path("C:/Users/paffe/OneDrive/Desktop/GameScraper")
ROUTES = ROOT / "pozzo/app/routes"
CATALOG = ROOT / "scratch/i18n/sq.it.json"

# file ||| testo esatto nel sorgente ||| sostituzione ||| occorrenze ||| chiave ||| testo italiano del catalogo
DATA = r'''
appsettings ||| "L'indirizzo del webhook deve iniziare con http:// o https://" ||| I.tr("s.appsettings.webhookScheme") ||| 1 ||| s.appsettings.webhookScheme ||| L'indirizzo del webhook deve iniziare con http:// o https://
appsettings ||| "I webhook devono essere una lista" ||| I.tr("s.appsettings.webhooksNotList") ||| 1 ||| s.appsettings.webhooksNotList ||| I webhook devono essere una lista
appsettings ||| f"Al massimo {WEBHOOK_MAX} webhook" ||| I.tr("s.appsettings.webhookMax", n=WEBHOOK_MAX) ||| 1 ||| s.appsettings.webhookMax ||| Al massimo {n} webhook
appsettings ||| "Webhook non valido" ||| I.tr("s.appsettings.webhookInvalid") ||| 1 ||| s.appsettings.webhookInvalid ||| Webhook non valido
appsettings ||| "Evento webhook sconosciuto" ||| I.tr("s.appsettings.webhookEventUnknown") ||| 1 ||| s.appsettings.webhookEventUnknown ||| Evento webhook sconosciuto
appsettings ||| "Scegli una cartella dedicata: la radice di un disco non è ammessa" ||| I.tr("s.appsettings.fastcopyRoot") ||| 1 ||| s.appsettings.fastcopyRoot ||| Scegli una cartella dedicata: la radice di un disco non è ammessa
appsettings ||| "Scegli una cartella dedicata: la home non è ammessa" ||| I.tr("s.appsettings.fastcopyHome") ||| 1 ||| s.appsettings.fastcopyHome ||| Scegli una cartella dedicata: la home non è ammessa
appsettings ||| "La cartella non può stare dentro la libreria né contenerla" ||| I.tr("s.appsettings.fastcopyInLibrary") ||| 1 ||| s.appsettings.fastcopyInLibrary ||| La cartella non può stare dentro la libreria né contenerla
appsettings ||| "Il percorso esiste ed è un file" ||| I.tr("s.appsettings.pathIsFile") ||| 1 ||| s.appsettings.pathIsFile ||| Il percorso esiste ed è un file
appsettings ||| "La cartella non è vuota: scegli una cartella vuota o dedicata" ||| I.tr("s.appsettings.folderNotEmpty") ||| 1 ||| s.appsettings.folderNotEmpty ||| La cartella non è vuota: scegli una cartella vuota o dedicata
appsettings ||| f"Cartella non utilizzabile: {e.strerror or e}" ||| I.tr("s.appsettings.folderUnusable", err=e.strerror or e) ||| 1 ||| s.appsettings.folderUnusable ||| Cartella non utilizzabile: {err}
appsettings ||| "delete_after deve essere true o false" ||| I.tr("s.appsettings.deleteAfterBool") ||| 1 ||| s.appsettings.deleteAfterBool ||| delete_after deve essere true o false
appsettings ||| "Cartella non valida" ||| I.tr("s.appsettings.folderInvalid") ||| 1 ||| s.appsettings.folderInvalid ||| Cartella non valida
appsettings ||| "Notifiche attive: prezzi, giochi gratis e lavori finiti." ||| I.tr("s.appsettings.notifyOn") ||| 1 ||| s.appsettings.notifyOn ||| Notifiche attive: prezzi, giochi gratis e lavori finiti.
appsettings ||| "Scelta non valida" ||| I.tr("s.appsettings.choiceInvalid") ||| 1 ||| s.appsettings.choiceInvalid ||| Scelta non valida
appsettings ||| "Piattaforma mancante" ||| I.tr("s.appsettings.platformMissing") ||| 1 ||| s.appsettings.platformMissing ||| Piattaforma mancante
appsettings ||| "Tema non trovato" ||| I.tr("s.appsettings.themeNotFound") ||| 1 ||| s.appsettings.themeNotFound ||| Tema non trovato
appsettings ||| "Profilo di esperienza non valido" ||| I.tr("s.appsettings.expInvalid") ||| 2 ||| s.appsettings.expInvalid ||| Profilo di esperienza non valido
appsettings ||| "Nome non valido" ||| I.tr("s.appsettings.nameInvalid") ||| 1 ||| s.appsettings.nameInvalid ||| Nome non valido
appsettings ||| "Tema non valido" ||| I.tr("s.appsettings.themeInvalid") ||| 1 ||| s.appsettings.themeInvalid ||| Tema non valido
appsettings ||| "Impostazione animazioni non valida" ||| I.tr("s.appsettings.animInvalid") ||| 1 ||| s.appsettings.animInvalid ||| Impostazione animazioni non valida
appsettings ||| "Id profilo non valido" ||| I.tr("s.appsettings.profileIdInvalid") ||| 2 ||| s.appsettings.profileIdInvalid ||| Id profilo non valido
appsettings ||| "Preset non trovato" ||| I.tr("s.appsettings.presetNotFound") ||| 2 ||| s.appsettings.presetNotFound ||| Preset non trovato
appsettings ||| "Lo store delle estensioni resta sempre attivo" ||| I.tr("s.appsettings.extStoreAlwaysOn") ||| 1 ||| s.appsettings.extStoreAlwaysOn ||| Lo store delle estensioni resta sempre attivo
appsettings ||| "Sono ammessi solo link web" ||| I.tr("s.appsettings.onlyWebLinks") ||| 1 ||| s.appsettings.onlyWebLinks ||| Sono ammessi solo link web
scan ||| f"Impostazione non valida: {key}" ||| I.tr("s.scan.settingInvalid", name=key) ||| 1 ||| s.scan.settingInvalid ||| Impostazione non valida: {name}
scan ||| "ROM non trovata", "ROM non trovate" ||| I.tr("s.scan.romOne"), I.tr("s.scan.romMany") ||| 1 ||| s.scan.romOne ||| ROM non trovata
scan ||| "ROM non trovata", "ROM non trovate" ||| I.tr("s.scan.romOne"), I.tr("s.scan.romMany") ||| 0 ||| s.scan.romMany ||| ROM non trovate
scan ||| "BIOS non valido", "BIOS non validi" ||| I.tr("s.scan.biosOne"), I.tr("s.scan.biosMany") ||| 1 ||| s.scan.biosOne ||| BIOS non valido
scan ||| "BIOS non valido", "BIOS non validi" ||| I.tr("s.scan.biosOne"), I.tr("s.scan.biosMany") ||| 0 ||| s.scan.biosMany ||| BIOS non validi
scan ||| "copertina in più mancante", "copertine in più mancanti" ||| I.tr("s.scan.coverOne"), I.tr("s.scan.coverMany") ||| 1 ||| s.scan.coverOne ||| copertina in più mancante
scan ||| "copertina in più mancante", "copertine in più mancanti" ||| I.tr("s.scan.coverOne"), I.tr("s.scan.coverMany") ||| 0 ||| s.scan.coverMany ||| copertine in più mancanti
scan ||| f"{size.replace('.', ',')} in più di doppioni" ||| I.tr("s.scan.dupesSpace", size=size.replace('.', ',')) ||| 1 ||| s.scan.dupesSpace ||| {size} in più di doppioni
scan ||| "Manutenzione: " + (", ".join(parts) or "un controllo non è riuscito, apri il rapporto") ||| I.tr("s.scan.maintSummary", parts=", ".join(parts) or I.tr("s.scan.maintCheckFailed")) ||| 1 ||| s.scan.maintSummary ||| Manutenzione: {parts}
scan ||| "Manutenzione notturna" ||| I.tr("s.scan.maintTitle") ||| 1 ||| s.scan.maintTitle ||| Manutenzione notturna
scan ||| "Manutenzione interrotta" ||| I.tr("s.scan.maintInterrupted") ||| 1 ||| s.scan.maintInterrupted ||| Manutenzione interrotta
scan ||| "Identificazione per CRC/nome (No-Intro, Redump), franchise, immagini libretro" ||| I.tr("s.scan.srcLibretro") ||| 1 ||| s.scan.srcLibretro ||| Identificazione per CRC/nome (No-Intro, Redump), franchise, immagini libretro
scan ||| "Valutazioni della community, descrizioni, generi, ESRB, video, immagini e loghi" ||| I.tr("s.scan.srcLaunchbox") ||| 1 ||| s.scan.srcLaunchbox ||| Valutazioni della community, descrizioni, generi, ESRB, video, immagini e loghi
scan ||| "Copia completa di TheGamesDB: descrizioni, giocatori, copertine (nessuna quota)" ||| I.tr("s.scan.srcTgdb") ||| 1 ||| s.scan.srcTgdb ||| Copia completa di TheGamesDB: descrizioni, giocatori, copertine (nessuna quota)
scan ||| "Solo arcade (MAME): dati, immagini, video" ||| I.tr("s.scan.srcArcadedb") ||| 1 ||| s.scan.srcArcadedb ||| Solo arcade (MAME): dati, immagini, video
scan ||| "Descrizioni, valutazioni utenti e critica, franchise, copertine" ||| I.tr("s.scan.srcIgdb") ||| 1 ||| s.scan.srcIgdb ||| Descrizioni, valutazioni utenti e critica, franchise, copertine
scan ||| "Ricerca per checksum, descrizioni in italiano, wheel, video (quota del tuo account)" ||| I.tr("s.scan.srcScreenscraper") ||| 1 ||| s.scan.srcScreenscraper ||| Ricerca per checksum, descrizioni in italiano, wheel, video (quota del tuo account)
scan ||| "Valutazioni utenti e voto Metacritic (chiave gratuita, 20.000 richieste/mese)" ||| I.tr("s.scan.srcRawg") ||| 1 ||| s.scan.srcRawg ||| Valutazioni utenti e voto Metacritic (chiave gratuita, 20.000 richieste/mese)
scan ||| "API di TheGamesDB (quota mensile molto bassa: meglio la copia completa)" ||| I.tr("s.scan.srcThegamesdb") ||| 1 ||| s.scan.srcThegamesdb ||| API di TheGamesDB (quota mensile molto bassa: meglio la copia completa)
scan ||| f"{sid}: il ritmo deve essere maggiore di zero" ||| I.tr("s.scan.rateMin", sid=sid) ||| 1 ||| s.scan.rateMin ||| {sid}: il ritmo deve essere maggiore di zero
scan ||| f"Errore: {e}" ||| I.tr("s.scan.errorPrefix", err=e) ||| 1 ||| s.scan.errorPrefix ||| Errore: {err}
scan ||| "Aggiornamento gia' in corso" ||| I.tr("s.scan.bulkBusy") ||| 1 ||| s.scan.bulkBusy ||| Aggiornamento gia' in corso
scan ||| "Uno scraping o un aggiornamento e' gia' in corso: riprova dopo" ||| I.tr("s.scan.scrapeBusyRetry") ||| 1 ||| s.scan.scrapeBusyRetry ||| Uno scraping o un aggiornamento e' gia' in corso: riprova dopo
scan ||| "Uno scraping o un aggiornamento e' gia' in corso" ||| I.tr("s.scan.scrapeUpdateBusy") ||| 2 ||| s.scan.scrapeUpdateBusy ||| Uno scraping o un aggiornamento e' gia' in corso
scan ||| "Manutenzione gia' in corso" ||| I.tr("s.scan.maintBusy") ||| 1 ||| s.scan.maintBusy ||| Manutenzione gia' in corso
scan ||| "Servono nome e identificativo" ||| I.tr("s.scan.nameIdRequired") ||| 1 ||| s.scan.nameIdRequired ||| Servono nome e identificativo
scan ||| f"«{pid}» esiste gia' tra le console incluse" ||| I.tr("s.scan.platformExists", pid=pid) ||| 1 ||| s.scan.platformExists ||| «{pid}» esiste gia' tra le console incluse
scan ||| "Indica almeno un'estensione dei file (es. iso chd)" ||| I.tr("s.scan.extRequired") ||| 1 ||| s.scan.extRequired ||| Indica almeno un'estensione dei file (es. iso chd)
scan ||| "Nessun abbinamento da applicare (le cartelle sono cambiate?)" ||| I.tr("s.scan.relinkNone") ||| 1 ||| s.scan.relinkNone ||| Nessun abbinamento da applicare (le cartelle sono cambiate?)
scan ||| "dati non validi" ||| I.tr("s.scan.dataInvalid") ||| 1 ||| s.scan.dataInvalid ||| dati non validi
scan ||| "Console o cartella non valida" ||| I.tr("s.scan.consoleFolderInvalid") ||| 1 ||| s.scan.consoleFolderInvalid ||| Console o cartella non valida
stores ||| "Aggiornamento degli store gia' in corso" ||| I.tr("s.stores.storeUpdateBusy") ||| 1 ||| s.stores.storeUpdateBusy ||| Aggiornamento degli store gia' in corso
stores ||| "Attendi la fine dell'aggiornamento degli store" ||| I.tr("s.stores.waitStoreUpdate") ||| 1 ||| s.stores.waitStoreUpdate ||| Attendi la fine dell'aggiornamento degli store
stores ||| "Ricerca dei metadati degli store gia' in corso" ||| I.tr("s.stores.metaBusy") ||| 1 ||| s.stores.metaBusy ||| Ricerca dei metadati degli store gia' in corso
stores ||| "Console sconosciuta" ||| I.tr("s.stores.consoleUnknown") ||| 2 ||| s.stores.consoleUnknown ||| Console sconosciuta
stores ||| "Indirizzo non valido (serve http:// o https://)" ||| I.tr("s.stores.addressInvalid") ||| 1 ||| s.stores.addressInvalid ||| Indirizzo non valido (serve http:// o https://)
stores ||| f"Pagina non raggiungibile: {type(e).__name__}: {e}" ||| I.tr("s.stores.pageUnreachable", err=f"{type(e).__name__}: {e}") ||| 1 ||| s.stores.pageUnreachable ||| Pagina non raggiungibile: {err}
stores ||| "Nessuno store PC aggiunto" ||| I.tr("s.stores.noPcStore") ||| 1 ||| s.stores.noPcStore ||| Nessuno store PC aggiunto
stores ||| "Nessuno di questi store è configurato" ||| I.tr("s.stores.noneConfigured") ||| 1 ||| s.stores.noneConfigured ||| Nessuno di questi store è configurato
stores ||| "Nessuno store configurato" ||| I.tr("s.stores.noStoreConfigured") ||| 1 ||| s.stores.noStoreConfigured ||| Nessuno store configurato
stores ||| "Nessuno store online configurato per questa console" ||| I.tr("s.stores.noOnlineStore") ||| 1 ||| s.stores.noOnlineStore ||| Nessuno store online configurato per questa console
gameinfo ||| "formato non valido (esde, pegasus o html)" ||| I.tr("s.gameinfo.formatInvalid") ||| 1 ||| s.gameinfo.formatInvalid ||| formato non valido (esde, pegasus o html)
gameinfo ||| "Esportazione gia' in corso" ||| I.tr("s.gameinfo.exportBusy") ||| 1 ||| s.gameinfo.exportBusy ||| Esportazione gia' in corso
gameinfo ||| f"Cartella non scrivibile: {e}" ||| I.tr("s.gameinfo.folderNotWritable", err=e) ||| 1 ||| s.gameinfo.folderNotWritable ||| Cartella non scrivibile: {err}
mods ||| "Gioco non trovato" ||| I.tr("s.mods.gameNotFound") ||| 1 ||| s.mods.gameNotFound ||| Gioco non trovato
mods ||| "Port non installato" ||| I.tr("s.mods.portNotInstalled") ||| 1 ||| s.mods.portNotInstalled ||| Port non installato
mods ||| "Mod non trovata" ||| I.tr("s.mods.notFound") ||| 1 ||| s.mods.notFound ||| Mod non trovata
mods ||| f"Mod non installata: {error}" ||| I.tr("s.mods.notInstalledErr", err=error) ||| 1 ||| s.mods.notInstalledErr ||| Mod non installata: {err}
mods ||| "Indica enabled come valore booleano" ||| I.tr("s.mods.enabledBool") ||| 1 ||| s.mods.enabledBool ||| Indica enabled come valore booleano
mods ||| "Mod non installata" ||| I.tr("s.mods.notInstalled") ||| 2 ||| s.mods.notInstalled ||| Mod non installata
verify ||| "Gioco non trovato" ||| I.tr("s.mods.gameNotFound") ||| 1 ||| s.mods.gameNotFound ||| Gioco non trovato
shots ||| "Steam non trovato su questo computer" ||| I.tr("s.shots.steamNotFound") ||| 1 ||| s.shots.steamNotFound ||| Steam non trovato su questo computer
shots ||| "Scorciatoia non valida (es. ctrl+shift+s, f10, alt+f12)" ||| I.tr("s.shots.hotkeyInvalid") ||| 1 ||| s.shots.hotkeyInvalid ||| Scorciatoia non valida (es. ctrl+shift+s, f10, alt+f12)
stream ||| "Gioco non trovato in libreria" ||| I.tr("s.stream.gameNotInLibrary") ||| 1 ||| s.stream.gameNotInLibrary ||| Gioco non trovato in libreria
stream ||| f"Sunshine non risponde ({type(e).__name__})" ||| I.tr("s.stream.sunshineDown", kind=type(e).__name__) ||| 1 ||| s.stream.sunshineDown ||| Sunshine non risponde ({kind})
stream ||| "Servono utente e password dell'interfaccia web di Sunshine" ||| I.tr("s.stream.credsRequired") ||| 1 ||| s.stream.credsRequired ||| Servono utente e password dell'interfaccia web di Sunshine
stream ||| f"Sunshine non risponde: avvialo e riprova ({type(e).__name__}: {e})" ||| I.tr("s.stream.sunshineStart", err=f"{type(e).__name__}: {e}") ||| 1 ||| s.stream.sunshineStart ||| Sunshine non risponde: avvialo e riprova ({err})
stream ||| "Controllo non riuscito" ||| I.tr("s.stream.checkFailed") ||| 1 ||| s.stream.checkFailed ||| Controllo non riuscito
stream ||| "Avvio annullato o non possibile" ||| I.tr("s.stream.startFailed") ||| 1 ||| s.stream.startFailed ||| Avvio annullato o non possibile
'''

# testo del catalogo senza una riga propria nel DATA (il secondo pezzo di una stringa composta)
EXTRA_CATALOG = {
    "s.scan.maintCheckFailed": "un controllo non è riuscito, apri il rapporto",
}

# import da aggiungere dopo la riga di ancoraggio (senza fine riga)
IMPORTS = {
    "appsettings": "from ...library import fastcopy as FC, launcher as L",
    "scan": "from ... import config as C, platforms as P, profilecfg as PC, relink as RL",
    "stores": "from ... import config as C, platforms as P, profilecfg as PC, storerefresh as SR, stores as STORES",
    "gameinfo": "from ... import profilecfg as PC",
    "mods": "from ... import ports as PT",
    "verify": "from fastapi import APIRouter, HTTPException",
    "shots": "from ... import config as C, stores as STORES",
    "stream": "from ... import config as C",
}

WIKI_RE = re.compile(
    r'"Descrizioni, sviluppatori, editori, generi e anno da Wikipedia \(italiano, poi inglese\): "\r?\n\s*'
    r'"gratuita, senza chiave, solo per i dati ancora mancanti"'
)
WIKI_TEXT = ("Descrizioni, sviluppatori, editori, generi e anno da Wikipedia (italiano, poi inglese): "
             "gratuita, senza chiave, solo per i dati ancora mancanti")


def main():
    rows = [[c.strip() for c in line.split(" ||| ")] for line in DATA.strip().splitlines() if line.strip()]
    catalog = {}
    per_file = {}
    texts = {}
    for f, old, new, count, key, text in rows:
        count = int(count)
        if count == 0:  # stessa chiave gia' inserita da una riga precedente (secondo pezzo di _n)
            texts.setdefault(key, text)
            continue
        per_file.setdefault(f, []).append((old, new, count, key, text))
    for key, text in [(r[4], r[5]) for r in rows]:
        assert catalog.get(key, text) == text, key
        catalog[key] = text
    catalog.update(EXTRA_CATALOG)
    catalog["s.scan.maintCheckFailed"] = EXTRA_CATALOG["s.scan.maintCheckFailed"]

    # secondo pezzo di _n: il testo e' gia' coperto dalla riga con count 1 e la sostituzione e' una sola
    done = {"appsettings"}  # gia' convertito in un giro precedente
    for f, items in per_file.items():
        if f in done:
            continue
        path = ROUTES / f"{f}.py"
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw
        # riga con le due stringhe _n: si sostituiscono insieme, una sola volta per coppia
        for old, new, count, key, _t in items:
            n = text.count(old)
            assert n == count, (f, old, n, count)
            text = text.replace(old, new)
        if f == "scan":
            text, n = WIKI_RE.subn('I.tr("s.scan.srcWikipedia")', text)
            assert n == 1, ("wiki", n)
            catalog["s.scan.srcWikipedia"] = WIKI_TEXT
        imp = IMPORTS[f]
        assert text.count(imp + nl) == 1, (f, "import anchor")
        text = text.replace(imp + nl, imp + nl + "from ... import i18n as I" + nl, 1)
        path.write_bytes(text.encode("utf-8"))
        print(f, "ok", sum(c for _o, _n2, c, _k, _t in items))

    # catalogo: stesse chiavi usate nei sorgenti
    CATALOG.write_bytes((json.dumps(dict(sorted(catalog.items())), ensure_ascii=False, indent=1).replace("\n", "\r\n") + "\r\n").encode("utf-8"))
    print("chiavi", len(catalog))


if __name__ == "__main__":
    main()
