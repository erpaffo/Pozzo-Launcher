<a id="port-e-app"></a>
# Free Games, Wishlist, PC Ports

<a id="giochi-gratis"></a>
## Free Games

The **🎁 Free Games** view gathers current free promotional deals: keep-forever games, subscription perks,
free weekends, and complimentary DLCs.

| Source | What it provides |
|---|---|
| allkeyshop.com (*Daily game deals* box) | Primary source: free games across all stores, categorized by offer type |
| LootScraper (public feed) | Prime Gaming even without allkeyshop: direct claim links, box art, expiry, value |
| Steam Search | Games normally paid discounted by 100% (excluding free-to-play, DLCs, soundtracks) |
| GamerPower | Promotional giveaways with expiration dates |

![Free Games: current promotions with offer type, value, and Open and Claimed buttons](../images/giochi-gratis.jpg)

On this page:

- the **New** tag and the 🆕 counter in the sidebar indicate offers that appeared since your last visit;
- **✓ Claimed** marks an offer as already redeemed;
- sorting displays unredeemed offers first, ordered by closest expiration date;
- **♡** adds the game to your wishlist.

Network overhead is minimal: results are cached for 3 hours (12 hours for allkeyshop and Prime Gaming); after a
network failure, the source is left alone for 3 hours. If allkeyshop fails to respond (it rate-limits IPs
after a burst of requests), the last known good listing is retained. Remote covers use tight timeouts, preventing
slow web hosts from stalling the rest of the application.

<a id="lista-desideri"></a>
## Wishlist

The **♡ Wishlist** view tracks prices of games you want to buy and alerts you when discounts are favorable.

### Adding Games

- type a title into the *Search a game to add…* input field;
- **⬇ Import from Steam** imports your public Steam wishlist;
- **♡** from the Free Games page.

A game already present in your collection is marked as *already in library*.

![Wishlist: current price, discount percentage, historical low, and cheapest key per title](../images/lista-desideri.jpg)

### Price Tracking

| Price Type | Source | Requirements |
|---|---|---|
| Official stores (Steam, GOG, Epic, Humble…) | IsThereAnyDeal | Free API key (list ⚙); without key, Steam price for games with Steam AppIDs |
| Key stores | **allkeyshop** | None: each added game is automatically scraped from allkeyshop |
| Key stores (supplementary) | GG.deals | Free API key (list ⚙); PC games with Steam AppIDs only |

For every title, the wishlist displays current price, discount, **all-time historical low**, and the lowest key
reseller price, showing discount compared to official retail MSRP (e.g. €59.99 on Steam → €18.50 = −69%).
**🔑 ↗** opens the key shop price comparison, **Open ↗** visits the store page.

### All Deals for a Single Game

Clicking a game in the wishlist opens the detailed price breakdown from allkeyshop:

- **Steam**: current price and discount, with Steam's historical low;
- **Cheapest key**;
- **all listings**, detailing store, region, edition, coupon codes, and price (*account* offers are separated from
  digital keys);
- **historical low for digital keys**.

If allkeyshop matched the wrong title or found nothing, paste the direct allkeyshop URL into the details card.
**↻ Refresh** moves the game to the head of the queue. Quick links: **allkeyshop ↗** and
**Steam ↗**.

allkeyshop blocks aggressive scrapers, so the app paces requests conservatively: **one request per minute**,
each game checked at most once daily, historical data once a month, with a **6-hour backoff pause** if throttled.
The interface displays queued items (*🔑 keys: queued*) and estimated wait time; unrecognized games are labeled
*🔑 not found on allkeyshop*.

Prices refresh at most twice a day, or immediately with **↻ Check Prices**. In wishlist settings (⚙), configure
your **country/region** and the **minimum discount** threshold for notifications.

<a id="avvisi-di-windows"></a>
### Alerts and Price History

A notification alert (🔔) triggers when:

- discount exceeds the configured threshold;
- price — official **or** reseller key — drops below your *Notify me when cheaper than…* limit;
- price hits a **new all-time low** since you began tracking the title.

Every game includes a **price history graph** (one data point per day across stores and key sellers).

## Ports and Apps

The **🕹 Ports and Apps** view lists console games **recompiled or reconstructed natively for Windows** (Zelda64Recomp, Ship of
Harkinian, Banjo Recompiled…) alongside **standalone open-source games and emulators** distributed via GitHub/GitLab releases,
sourced from the Quiver Launcher catalog (~630 entries, updated every 24 hours).

![Ports and Apps: console filters and native ports showing ROM requirements](../images/port-pc.jpg)

### Finding a Port

Filter by type (ports, games, emulators) and console, full-text search, **🎮 I Have the ROM** (ports of games already
in your library), **Installed**, **Update Available**. A ROM's details card displays **Available as PC port** whenever a matching port exists.

### Installing and Launching

- **Install** downloads the latest release from GitHub, GitLab, or Codeberg (the appropriate Windows asset is selected automatically) into
  `Ports\<folder>`, creating `portable.txt` if supported.
- Downloads are **verified against the SHA-256 hash** published in the catalog release (or GitHub `digest`):
  mismatched payloads are rejected.
- The port becomes a first-class **PC game**: playtime tracking, Big Picture navigation, and remote phone launching operate identically to other titles.
  The **Play** button is available immediately in the port's card, even during ongoing library scans, and execution
  always routes through the launcher.
- **Update All** (and the **Auto-update** toggle in page settings) installs updates directly from the launcher:
  patches require no external tools.
- If a port contains multiple executables, you can choose which one to launch, and your selection is remembered.
- On first **Play**, choose how to open the window: **Windowed**, **Borderless** (stretched to screen size), or
  **Fullscreen** (sends Alt+Enter to game; falls back to borderless if unsupported). Checking **Remember choice** silences future prompts:
  window mode can be changed from the **Window on launch** menu on the port's page ("Always ask" restores the prompt). Pozzo
  prioritizes child processes; for other root processes, it waits 5 seconds for the game to start and applies the window mode only
  once the window is stable. File Explorer, recognized launchers, and standard ROM picker dialogs are never modified.
- **Uninstall** moves the port directory to the Recycle Bin.
- **Path Too Long**: certain ports (e.g. SMS Launcher) build games inside their own folder tree, causing Windows path
  character limits (MAX_PATH) to prevent launch. Pozzo automatically enforces short paths: if `Ports\<folder>` would be
  too long, it installs to a short path (`C:\PozzoPorts\<folder>`, or the first writable drive/`Public`), and
  existing long-path ports can be relocated via **📦 Move to short path** on their card (explaining the rationale and asking
  confirmation). Saves and settings are copied and a backup remains in `Ports\.backup`; future updates stay in the
  short folder. The short directory path can be customized in ports ⚙.
- **Add Manually**: specify a GitHub repository (`user/repo`) or select an already extracted local directory.

### Required ROM

Many ports require an original base ROM. For ports publishing an asset hash requirement, the app automatically inspects
your library upon download, validates the matching ROM by hash, and copies it into the port folder. **Copy from Library**
remains available to trigger this manually. Port settings (executable, base ROM, mods) are managed from its card in
the app; the card also provides access to the **Launch Profile** for custom scripts and extra CLI parameters.

### Updates

Update checks occur at most once every 12 hours. Before updating, a backup snapshot is saved to `Ports\.backup`;
saves, user configuration, and mods (files inside the folder not originating from the upstream release) are preserved.
**Skip This Version** ignores a specific release. An optional GitHub personal access token (⚙ on the page) raises
GitHub API rate limits.

### Mods and Saves

- **Mods** via Thunderstore: install and manage directly from the port page. GameBanana is linked externally.
- Port **saves** integrate seamlessly into per-game save versioning (see [Playing Games](giocare.md#salvataggi)).

## Windows Notifications

With **Settings › 🧩 Integrations › 🔔 Windows Notifications** enabled (on by default), Pozzo Launcher delivers native Windows
toast notifications — preserved in Action Center — when:

- a wishlisted game drops below your target price;
- a new free game becomes available (Steam, Epic, Prime Gaming, online stores);
- an installed PC port receives an update;
- a background scan or update concludes (new games, store catalogs, box art, durations, local databases…).

Free games and port updates are polled quietly in the background every 6 and 12 hours without requiring open
tabs. The same alert is never duplicated for the same deal or release.

## Shutdown or Sleep on Completion

**Settings › ⟳ New Games › 🌙 Upon Completion**: when all background tasks finish — scraping, store updates,
download of a port — the PC automatically enters **Sleep** or initiates **Shutdown**. A 60-second on-screen countdown
with an **✕ Cancel** button gives you time to abort. If a game is currently running, no action is taken until the game is closed:
active gameplay is never terminated by an automated shutdown.
