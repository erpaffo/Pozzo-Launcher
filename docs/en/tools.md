# Tools

The **Tools** section gathers handy operations on game files: converting a disc to a smaller format, applying a patch,
checking that a dump is correct, building a playlist for multi-disc games, or copying a disc from your optical drive.
You do not need to know what happens underneath: Pozzo downloads the programs it needs and checks your disk space
before starting.

## Where to find it

- **Tools** entry in the sidebar: the list of all tools.
- **Game detail**: the **Tools** action shows only the ones that fit that game.
- **Right-click menu** on a game: the same entries, only the compatible ones.

!!! note "Big Picture"
    [Big Picture](bigpicture.md) mode does not include Tools: use them from the normal window.

## What is available

| Tool | What it does | What you need | What it produces |
|---|---|---|---|
| **Convert to CHD** | Compresses PlayStation, PS2, Saturn, Sega CD, Dreamcast, PC Engine CD, Neo Geo CD, 3DO, Amiga CD32 and PC-FX discs | A `.cue`, `.iso`, `.gdi` or `.img` file; the `chdman` program (downloaded automatically) | `Name.chd` next to the original |
| **Convert to RVZ** | Compresses GameCube and Wii discs | An `.iso`, `.gcm` or `.wbfs` file; **Dolphin** installed | `Name.rvz` |
| **Convert to CSO** | Compresses PSP ISOs | An `.iso` file; the `maxcso` program (downloaded automatically) | `Name.cso` |
| **Switch 2 → NUP** | Packs an unencrypted Switch 2 game (NSP or folder) into the compressed NUP format | A version of Eglantine that reads it (2.5.0 or newer). No keys: an encrypted NSP is refused | The `.nup` file (or an NSP) |
| **Apply IPS/BPS patch** | Applies a patch (translations, hacks) to a ROM | A cartridge ROM and an `.ips` or `.bps` file you choose | `Name (patched).ext`: the original ROM is not modified |
| **Verify disc (Redump)** | Checks whether the dump is identical to the one catalogued by Redump | A `.cue`, `.gdi`, `.iso`, `.bin` or `.img` file; the Redump list (downloaded once if missing) | Only a result: **ok**, **different** (looks like a known game but the hashes do not match) or **unknown**, with CRC, MD5 and SHA-1 of the tracks |
| **Multi-disc playlist (.m3u)** | Builds the playlist for multi-disc games so the emulator can swap discs from its menu | At least two discs with "(Disc 1)", "(Disc 2)"... in the name, in the same folder | `Title.m3u` with the discs in order. It never overwrites an existing playlist |
| **Dump from optical drive** | Copies one of your discs from the CD/DVD drive into a folder | A drive with the disc inside; the `redumper` program (downloaded automatically) | A folder named after the disc, containing the `.cue` and the tracks |

Verify and playlist do not change any game file. Dump does not start from a game: you pick the drive and the
destination folder from the **Tools** entry in the sidebar.

## The new file becomes the game's file

Conversions (CHD, RVZ, CSO, NUP) and the patcher produce a new file. When the job ends, Pozzo **links it to the game**:
notes, play time and favorites stay where they are. Then it asks whether to move **the old file to the Recycle Bin**.

The old file is **never permanently deleted**:

- on Windows fixed drives it goes to the Recycle Bin;
- on network drives, USB sticks, Linux and macOS it is moved to a **`.pozzo-trash`** folder at the root of the same
  disk. It takes no extra space, but it does not empty itself: when you are sure, delete it by hand.

If the produced file does not exist or is empty, the original is left untouched.

## Disk space check

Before starting, Pozzo estimates how much the result will take and adds a **10% margin** (at least **256 MB**) for
temporary files. The old file stays in place until the new one is ready, so you need room for **both**.

If there is not enough space the job **does not start** and a message tells you how much is needed and how much is
free. Free up space or pick another destination folder.

## External programs

| Program | For | From where |
|---|---|---|
| `chdman` | CHD | Official MAME release (only `chdman.exe` is extracted) |
| `maxcso` | CSO | Official GitHub release |
| `redumper` | Dump | Official GitHub release |
| `dolphin-tool` | RVZ | Not downloaded: it lives in the folder of the installed **Dolphin** |

The download starts by itself the first time it is needed and **requires a network connection**. Pozzo only downloads
from these fixed addresses, checks the checksum and rejects the file if it does not match. Programs are saved in the
`tools` folder next to Pozzo's settings and downloaded only once. Automatic download works on Windows (x64) only: on
Linux and macOS the program must already be installed and available to the system.

## One job at a time

Tools run **one job at a time**: starting another while one is running is refused. While it works you see the
progress as a percentage. **Cancel** stops everything and cleans up partial files (`.partial`, half-written dump
folders); no existing final file is overwritten.

## Known limits

- **Cartridges (patcher)**: the game is recognized by its content (CRC). After patching, notes and play time are
  re-linked at the next library scan, not immediately. For discs the link is immediate.
- **Dump**: only for discs you own. It makes a raw copy of the disc from the drive; nothing is downloaded from the
  internet.
- **Big Picture** does not include Tools.
