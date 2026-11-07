# PC Games from Stores

The **PC** section of the sidebar gathers games from official stores installed on this computer. It includes both
**installed** games and **owned but not installed** games: uninstalled games appear grayed out with an
**⬇ Install** button, which opens the store client directly on the game's page.

![PC games from stores: installed and owned, with store badges and the Install button](../images/store-pc.jpg)

## Supported Stores

| Store | Installed | Not Installed | Requirements |
|---|---|---|---|
| Steam | local files | yes | Free Web API key |
| Epic Games | local files | yes | **Connect Account**: sign in via official Epic page |
| GOG.com | Windows Registry | yes | **Connect Account**: sign in via official GOG page |
| Amazon Games / Prime Gaming | yes | yes | Automatic, read from Amazon Games app |
| Battle.net | yes | free and previously played games | Blizzard does not provide an owned games list |
| Windows / Xbox | yes | no | Would require Xbox Live login |
| Minecraft | Java and Bedrock | yes (Microsoft Store) | Automatic |

Stores are enabled and disabled in **Settings › Stores**; this is also where accounts are connected. Changing a
setting takes effect on the next library refresh.

### Steam

To see **uninstalled** games as well, a free Web API key is required
(steamcommunity.com/dev/apikey). Without a key, the app still detects installed games from local files. The SteamID used
is that of the account used most recently on the PC, or specified in `[stores.steam] steamid`.

### Epic Games and GOG

**Connect Account** opens the store's official login page in an app window; upon completion, the app receives
the authorization code and from that point on reads the list of owned games. Your password never passes
through the app.

### Epic, GOG and Amazon Without the Official Client

In the game details, the **Without the official client** section lets you install, update, verify and uninstall games,
see and install DLC and, for Epic only, sync saves with the cloud (GOG and Amazon: no cloud). Pozzo uses `legendary`,
`gogdl` and `nile`, the same open source utilities as Heroic: they are downloaded from GitHub on first use and are not
bundled with Pozzo (third-party programs, GPL). They use the account already connected in **Settings › Account** (for
Amazon there is a dedicated sign-in there). Downloads go through the queue, with pause and resume, and games installed
this way appear as installed and start without opening any launcher.

### Steam Without the Client (SteamCMD)

On owned but not installed games, **Download with SteamCMD** downloads the game without opening Steam. SteamCMD
downloads itself; sign-in, with the Steam Guard code, is done once in **Settings › Stores** (Pozzo does not store the
password). The download is in the Downloads queue, with pause and resume, and the game enters the library when it
finishes. **Limit**: games with Steam DRM still need the Steam client running to start.

### Network Folder as a Store

In **Settings › Account** enter one or more **network folders**, one per line (`\\NAS\Games`, a mapped drive or a
local folder) containing installers, archives (`.zip`, `.7z`, `.rar`) and game folders. Games appear as owned and
ready to install: **Install** copies with progress, then extracts or runs the setup (silent for GOG/Inno installers,
if you want); at the end the game enters the library and starts like the others. A `pozzo.json` file in the game
folder can fix the title, executable and arguments. WebDAV is not supported; SMB needs your Windows credentials.

## Adding Any Game

Clicking **＋** next to *PC* lets you select an `.exe`: the game enters the library under PC games. Cover art and images
are searched on Steam and IGDB. Manually added games are saved in your user data and are never touched by
library rebuilds.

In the **Type** field, choose **Game** or **Application**: applications (a program that is not a game) end up
in the **🧩 Applications** view instead of among games, and launch in the same way. Entries added twice
by mistake can be removed with **🧹 Remove Manual Duplicates** in the *Library Cleanup* extension.

### Browser Games (URL)

In the same dialog, choose **Type › Browser / URL** (e.g. `https://www.chess.com`), enter the URL and optionally a
title; **Add** saves the game. **Play** opens the URL in the default browser (playtime is not
tracked). Title (if left blank), description, and cover image are extracted from static page tags
(`og:title`, `og:description`, `og:image`, falling back to `<title>` and `meta description`), without JavaScript
or extra dependencies, and are saved: they appear in the library and on the game details card.

For security, the URL is treated as untrusted input: only `http` and `https` are allowed; local hosts
(`localhost`, `.local`, domainless names) and private, loopback, or link-local IP addresses are rejected, even
after redirects. This check also applies to cover image fetching and each redirect, and is performed against the actual resolved IP address
used for the connection (mitigating DNS rebinding); system proxies are not used for these requests.
Requests have limits: 8-second timeout, 1 MB HTML limit, maximum 5 redirects. If the website does not
respond, the game is still added and the app displays the error (e.g. "Timed out contacting site").
The workflow for `.exe` games and applications remains unchanged.

Adding a game is instantaneous and does not trigger a store update: the entry appears immediately, while cover art
and images arrive in the background.

## Exporting to Steam

**Settings › Stores › Export to Steam** adds Pozzo's games (all, favorites only, or some platforms) to your Steam
library as non-Steam games, with cover art, so Steam Input, Steam Deck and Big Picture work. Games always start
through Pozzo, so playtime and automations stay active. Entries already in Steam are not touched, a copy of
`shortcuts.vdf` is made before writing, and **Remove Pozzo entries** removes only the ones Pozzo created. **Steam must
be closed** (also from the tray icon).

## Same Game on Multiple Stores

A game owned across multiple stores (for example, Steam and Epic) is merged into **a single card** with multiple versions.
The primary version is the installed one. Favorites, completion status, and playtime apply across all versions (playtime is the sum). The game starts from your
preferred store, in the order you choose. To keep separate cards, untick **Merge games owned on multiple stores** in
**Settings › Library** (on by default); it applies from the next library rebuild and deletes nothing.

## Store Game Metadata

Descriptions, genres, images, and ratings come from the stores themselves when provided (for example, Steam
reviews), then from IGDB and other sources. The **📚 Store Game Metadata** dialog fills in missing metadata
for PC games.

## Playtime

Playtime is recorded even for games launched through a launcher, by tracking the game's executable process
within its directory. Steam also supplies its own total playtime.

## Scripts, Launchers, and Shortcuts

PC games also benefit from **pre-launch and post-exit scripts** (globally or per-game in the **⚙ Launch Profile**
of the individual game), **automatic launcher exit** when closing a game, and the **🖥 Desktop Shortcut**:
these are explained in [Playing Games](giocare.md#script-prima-e-dopo-il-gioco).

## Non-Official Stores

Lists of PC games that are **not** official stores (repack sites or direct download repositories) are added in
the same tab, under **Other PC Stores**: these are explained in the chapter [Adding Stores](store-online.md#altri-store-pc).
