# Strumenti

La sezione **Strumenti** raccoglie le operazioni utili sui file dei giochi: convertire un disco in un formato più
piccolo, applicare una patch, controllare che un dump sia corretto, creare una playlist per i giochi a più dischi o
copiare un disco dal lettore ottico. Si usa anche senza sapere cosa c'è sotto: Pozzo scarica da solo i programmi che
servono e controlla lo spazio prima di iniziare.

## Dove si trova

- Voce **Strumenti** nella barra laterale: l'elenco di tutti gli strumenti.
- **Dettaglio del gioco**: l'azione **Strumenti** mostra solo quelli adatti a quel gioco.
- **Menu con il tasto destro** su un gioco: stesse voci, solo quelle compatibili.

!!! note "Big Picture"
    La modalità [Big Picture](bigpicture.md) non include gli Strumenti: si usano dalla finestra normale.

## Cosa c'è

| Strumento | A cosa serve | Cosa serve | Cosa produce |
|---|---|---|---|
| **Converti in CHD** | Comprime i dischi di PlayStation, PS2, Saturn, Sega CD, Dreamcast, PC Engine CD, Neo Geo CD, 3DO, Amiga CD32 e PC-FX | File `.cue`, `.iso`, `.gdi` o `.img`; il programma `chdman` (scaricato in automatico) | `Nome.chd` accanto all'originale |
| **Converti in RVZ** | Comprime i dischi di GameCube e Wii | File `.iso`, `.gcm` o `.wbfs`; **Dolphin** installato | `Nome.rvz` |
| **Converti in CSO** | Comprime le ISO di PSP | File `.iso`; il programma `maxcso` (scaricato in automatico) | `Nome.cso` |
| **Switch 2 → NUP** | Impacchetta un gioco Switch 2 in chiaro (NSP o cartella) nel formato compresso NUP | Una versione di Eglantine che lo legge (2.5.0 o più recente). Niente chiavi: un NSP cifrato viene rifiutato | Il file `.nup` (o un NSP) |
| **Applica patch IPS/BPS** | Applica una patch (traduzioni, hack) a una ROM | La ROM di una cartuccia e un file `.ips` o `.bps` scelto da te | `Nome (patched).ext`: la ROM originale non viene modificata |
| **Verifica disco (Redump)** | Controlla se il dump è identico a quello catalogato da Redump | Un file `.cue`, `.gdi`, `.iso`, `.bin` o `.img`; l'elenco Redump (scaricato una volta se manca) | Solo un esito: **ok**, **diverso** (assomiglia a un gioco noto ma gli hash non coincidono) o **sconosciuto**, con CRC, MD5 e SHA-1 delle tracce |
| **Playlist multi-disco (.m3u)** | Crea la playlist per i giochi con più dischi, così l'emulatore li cambia da menu | Almeno due dischi con «(Disc 1)», «(Disc 2)»… nel nome, nella stessa cartella | `Titolo.m3u` con i dischi in ordine. Non sovrascrive mai una playlist esistente |
| **Dump da lettore ottico** | Copia un disco tuo dal lettore CD/DVD in una cartella | Un lettore con il disco dentro; il programma `redumper` (scaricato in automatico) | Una cartella con il nome del disco, con dentro il `.cue` e le tracce |

La verifica e la playlist non cambiano nessun file del gioco. Il dump non parte da un gioco: si sceglie il lettore e la
cartella di destinazione dalla voce **Strumenti** nella barra laterale.

## Il file nuovo diventa il file del gioco

Le conversioni (CHD, RVZ, CSO, NUP) e la patch producono un file nuovo. Quando il lavoro finisce, Pozzo lo
**collega al gioco**: note, ore di gioco e preferiti restano dove sono. Poi ti chiede se spostare **il vecchio file nel
Cestino**.

Il vecchio file **non viene mai cancellato in modo definitivo**:

- sui dischi fissi di Windows va nel Cestino;
- sui dischi di rete, sulle chiavette USB e su Linux e macOS viene spostato in una cartella **`.pozzo-trash`** alla
  radice dello stesso disco. Non occupa spazio in più, ma non si svuota da sola: quando sei sicuro, cancellala a mano.

Se il file prodotto non esiste o è vuoto, l'originale non viene toccato.

## Controllo dello spazio

Prima di partire Pozzo stima quanto occuperà il risultato e aggiunge un **margine del 10%** (almeno **256 MB**) per i
file temporanei. Il vecchio file resta dov'è finché il nuovo non è pronto, quindi serve spazio **per entrambi**.

Se lo spazio non basta il lavoro **non parte** e un messaggio dice quanto serve e quanto è libero. Libera spazio o scegli
un'altra cartella di destinazione.

## Programmi esterni

| Programma | Per | Da dove |
|---|---|---|
| `chdman` | CHD | Release ufficiale di MAME (si estrae solo `chdman.exe`) |
| `maxcso` | CSO | Release ufficiale su GitHub |
| `redumper` | Dump | Release ufficiale su GitHub |
| `dolphin-tool` | RVZ | Non si scarica: sta nella cartella di **Dolphin** installato |

Il download parte da solo la prima volta che serve e **richiede la rete**. Pozzo scarica solo da questi indirizzi
fissi, controlla il checksum e rifiuta il file se non corrisponde. I programmi si salvano nella cartella `tools` accanto
alle impostazioni di Pozzo e si scaricano una volta sola. Il download automatico vale solo su Windows (x64): su Linux e
macOS il programma deve essere già installato e raggiungibile dal sistema.

## Un lavoro alla volta

Gli Strumenti eseguono **un solo lavoro per volta**: se ne avvii un altro mentre uno è in corso, viene rifiutato.
Durante il lavoro vedi l'avanzamento in percentuale. **Annulla** ferma tutto e ripulisce i file parziali
(`.partial`, cartelle del dump a metà); nessun file definitivo esistente viene sovrascritto.

## Limiti noti

- **Cartucce (patcher)**: il gioco è riconosciuto dal contenuto (CRC). Dopo la patch, note e ore si riassociano al
  prossimo aggiornamento della libreria, non subito. Per i dischi il collegamento è immediato.
- **Dump**: solo per dischi che possiedi. Fa una copia grezza del disco dal lettore, non scarica nulla da internet.
- **Big Picture** non include gli Strumenti.
