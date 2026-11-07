# Privacy

**English** · [Italiano](PRIVACY.it.md)

Pozzo Launcher has no server of its own, no accounts, and **does not collect usage data** (no telemetry, no statistics sent).

## Where your data lives

Everything stays on your PC, in the data folder (`%LOCALAPPDATA%\PozzoLauncher` on Windows, `~/Library/Application Support/PozzoLauncher` on macOS, `~/.local/share/PozzoLauncher` on Linux, or next to the executable in the portable version): library, favorites, playtime, notes, settings, downloaded covers.

Source keys and store logins are kept in `config.toml` and `settings.json` in that folder, **in plain text**: protect the folder as you would a password file, and do not share it.

They leave the PC only if you choose so:

- **Sync between PCs**: to your other paired PCs or the shared folder you specify.
- **Phone**: paired phones see the library on your home network; from outside the home only if you set a public address (tunnel).
- **Backups**: wherever you save them.

## Which services it contacts

The app connects to external services only for the features you use. Some checks run in the background: updates at startup, free games every 6 hours, PC ports every 12 hours, wishlist prices.

| Feature | Services |
|---|---|
| Game data and images | libretro, IGDB (Twitch), ScreenScraper, TheGamesDB, LaunchBox, ArcadeDB, RAWG, Wikipedia, HowLongToBeat, GameTDB, Steam reviews |
| PC games | Steam, Epic Games, GOG, Amazon, Battle.net, Xbox, Minecraft: installed launchers and, where needed, sign-in with your account |
| Achievements | RetroAchievements, with your credentials |
| Free games and prices | allkeyshop (free offers box), GamerPower, LootScraper feed, Epic Games Store, IsThereAnyDeal, GG.deals, Steam |
| Ports and apps | Quiver, GitHub, GitLab, Codeberg, Thunderstore |
| Online stores | only the sites you add |
| Updates and extensions store | GitHub |
| Discord | the Discord client on the PC (local channel, no server) |

These services receive the normal information of a web request (IP address, title of the game searched) and, for sources with an account, your key. Each has its own privacy policy.

Extensions you install may contact other services: they are listed in their description (for example SteamGridDB, RAWG for the release calendar).
