# Phone and Streaming

Your phone (or tablet) can do four things with Pozzo Launcher:

1. **library remote control**: browse games, launch and close them on your PC;
2. **controller**: on-screen buttons, gyroscope, up to 4 phones for 4 players;
3. **screen**: play on your phone, TV, or another PC using Sunshine + Moonlight streaming;
4. **remote friend**: let a friend join your game as a second player, using their phone as a controller.

Everything is configured in **Settings › 📱 Phone and streaming**.

## The Phone App

### Activating It and Pairing Your Phone

1. **Enable phone access**. The app serves a HTTPS web app across your local home network.
2. **Install the PC certificate once** (see below): without it, your phone warns "connection not private" and the
   browser **refuses to install the app**.
3. Scan the pairing **QR code** with your phone. The code has 6 digits, is valid for 10 minutes, and is single-use.
4. Tap **⬇ Install** at the top (on iPhone/iPad: *Share › Add to Home Screen*): the app launches in full-screen
   mode and your **library remains browsable even when Wi-Fi drops** (including box art); commands that modify
   anything (launching, favorites, controller) require an active connection.

Windows might ask you to allow the app on private networks: answer Yes.

![Settings › Phone and streaming: activation, PC certificate, pairing QR code, and paired phones](../images/impostazioni-telefono.jpg)

### Installing the App: The HTTPS Certificate

The phone server speaks HTTPS, but using a **self-signed certificate**. An untrusted certificate causes two issues:
the "connection not private" warning and, above all, the browser **rejecting the service worker** — meaning no
installation and no offline usage. The solution is to trust the PC once.

Note what the profile actually does: **it does not enable HTTPS** (it is already active; the page is
`https://<ip>:8766/m/`), it simply tells your phone "this certificate is legitimate". HTTPS consists of two parts:
an encrypted connection and the **identity** of the server certified by an authority. A public website gets certified
by a public CA (which requires a domain and internet access); here, you are the authority on your PC, and installing
`PozzoLauncher-CA.crt` once on your phone makes it recognized. With a trusted certificate, the service worker is
accepted and the app installs. Without a profile, on iPhone you can still use *Share › Add to Home Screen*, but it
remains a simple bookmark: no offline use and no gyroscope (sensors also require a connection considered secure).

On the PC: **Settings › 📱 Phone and streaming › 🔒 PC Certificate**. Scan the QR code (or open
`https://<pc-ip>:8766/m/ca.crt`) and install the `PozzoLauncher-CA.crt` file:

- **Android**: Settings › Security › Encryption & credentials › Install a certificate › *CA certificate* ›
  "Install anyway" › choose the downloaded file. Chrome trusts user-installed CAs.
- **iPhone/iPad**: Settings › General › VPN & Device Management › install the profile; then Settings ›
  General › About › *Certificate Trust Settings* › turn on the switch for "Pozzo Launcher CA" (without this step,
  the certificate is not trusted).

Then close and reopen your browser tabs: the warning disappears and the app can be installed. Useful notes:

- **Instant load**: once installed, the page and library load from the phone's cached copy and update in the background;
  on the PC, the latest library response remains pre-built, so it isn't reconstructed on every open. With tens of
  thousands of games, the difference is noticeable (from a few seconds down to a few hundred milliseconds).
- The CA remains the **same for 10 years**: if the PC's IP address changes, only the server certificate changes (regenerated
  and auto-signed), and the phone continues to trust it — no reinstallation needed.
- The `ca.key` file in the `certs` folder next to your settings is the key that makes the PC trusted: never copy it to
  other PCs or share it. To revoke trust, simply remove the CA in your phone's settings.
- On iPhone, installing web apps (PWAs) is **only possible through Safari**, not Chrome or Firefox.
- If the phone keeps saying "not private": trust activation is missing (iOS), the CA was installed as a "Wi-Fi/VPN"
  certificate instead of "CA" (Android), or the tab is still open: close all tabs and reopen.
- If the phone **blocks downloading** the certificate (which can happen while the page is flagged as insecure), in
  Settings › Phone and streaming there is a link to save `PozzoLauncher-CA.crt` **on the PC**: transfer it to your phone
  via cable, email, cloud, or AirDrop, then install it as described above.
- If you lost the `certs` folder (or restored a backup on a new PC), a new CA is generated: phones must be trusted
  again once.
- As an alternative to a local CA, you can use a public domain with a valid certificate (for example via a Cloudflare
  Tunnel or Tailscale, see [Playing with a Remote Friend](#playing-with-a-remote-friend)): however, this requires an
  internet connection and an external service.

### Security

Without pairing, the phone cannot access anything. Even when paired, it can only browse the library, launch and
close games, take screenshots, act as a controller, and press **remote control** buttons (a strictly closed list:
no arbitrary typed text): PC settings and files remain completely out of reach. A **remote guest** only has access
to the controller.

### What You Can Do from Your Phone

- Home tab with *Now Playing*, *Recently Played*, *Favorites*, and installed PC games; search and filter by console.
- **Library** with sorting by title, year, rating, play time, and last played, plus filters for *All*, *Recent*,
  *★ Favorites*, *▶ Now Playing*, and *📋 Backlog*.
- **⏳ Tasks**: ongoing PC background operations — scanning for new games, official and online stores, cover art and
  descriptions, play durations, top games, collection artwork, local databases, library rebuilds — with progress
  percentage, plus action buttons: **Update stores**, **Scan for new games**, **Rebuild library**, **Close game**,
  and, while a scan is active, **Stop scan**. Finished tasks can be cleared from the Tasks window individually or via
  bulk cleanup buttons. The **🎛 PC Remote Control** is also located in this tab.
- Game details with **Play**, status, favorite toggle, and **Remove from Recently Played**.
- **Screenshots** of the running game.
- **🎛 PC Remote Control**: volume, mute, play/pause, and next track, plus Esc, Enter, Back, Alt+Tab, fullscreen, and
  Start menu. Each tap presses and releases a key on the PC (no typed text: the list is fixed).
- **📱 Play on this phone**: starts the game on the PC and explains how to connect via Moonlight with a single tap,
  through the **▶ Now Playing** app published in Sunshine. Opening Moonlight directly to a game from a web page is
  not possible (neither on iOS nor on Android).

![The phone web app: Home tab with Now Playing, Recently Played, and installed PC games](../images/telefono.jpg)

## The Phone as a Controller

The on-screen controller becomes a **virtual Xbox controller** on the PC: requires the **ViGEmBus** driver. Up to 4
phones = 4 players.

The **🏠** button at the top closes the controller and returns to Home, even when holding the phone vertically; long titles
are shortened so the top action bar does not overflow the screen.

### Controller Layouts

Under ⚙ › **Controller layout**:

| Layout | Purpose |
|---|---|
| **Xbox** | The default layout |
| **PlayStation** | D-pad top-left, thumbsticks at the bottom, △ ○ ✕ □ with authentic colors, L1/L2/R1/R2 |
| **Nintendo Switch** | Pro Controller: X at top, A on the right, B at the bottom, Y on the left |
| **GameCube** | Large A button, yellow C-stick, letter-mapped buttons |
| **Arcade** | 6 action buttons, for fighting games |
| **Buzz!** | Large red buzzer button and 4 colors, phone held vertically; one phone per player |
| **Wii Remote** | Held vertically or horizontally (like a NES pad), also with **Nunchuk**: buttons, thumbstick, tilt, shake, and IR pointer pass through to Dolphin |
| **Steering Wheel** | Steer by tilting your phone, analog touch pedals, *Center* button |
| **Guitar** | Guitar Hero / Rock Band: 5 colored frets, strum bar, whammy bar, Star Power |
| **Light Gun / Touchpad** | Phone acts as PC mouse pointer (GunCon, Zapper, DS stylus). Must be enabled on the PC |
| **Microphone** | SingStar: voice routes into a PC virtual audio cable (e.g., VB-Cable) used as a microphone in PCSX2 |

With the Switch layout, the buttons send the same **physical positions** of an Xbox controller to the PC (retaining the
mappings your emulator already configured for real controllers); an optional setting lets you send the **letter**
instead (Nintendo A = Xbox A).

**Automatic layout**: when a PlayStation game is running, the phone automatically switches to the PlayStation layout,
with a Switch game to the Switch layout, and likewise for GameCube, Wii, and Buzz!, Guitar Hero/Rock Band, and SingStar games.
Can be disabled in ⚙.

### Customizable Buttons

⚙ › **Move and resize buttons**: drag any button group (thumbsticks, D-pad, action buttons, bumpers/triggers, center buttons)
and resize them. Positions are saved per layout as percentages of screen dimensions; **Reset** restores default layout.

These settings — layout, sensitivity, axis inversion, and button positions — are saved **on the PC**, not in the phone's
browser: they apply to all paired phones, are included in backups, and are preserved when reconnecting. Conversely, button
scale and touch vibration remain local to each specific phone, tailored to its individual screen.

### Gyroscope

- **Motion**: DSU protocol (cemuhook) on `127.0.0.1:26760` for Cemu, Ryujinx, Dolphin, Azahar/Citra.
  In your emulator, select DSU motion source.
- **🎯 Aiming**: tilting moves the right stick, designed for games without native gyro support.

### Vibration

When the game triggers rumble on the virtual controller, the phone vibrates, with longer pulses for heavier rumbles.
Supported on Android; Safari on iPhone and iPad does not allow haptics/vibration for web pages.

### Bluetooth Controller Connected to Phone

If a Bluetooth controller (PS5, PS4, Xbox, Switch Pro, MFi) is paired to your phone or tablet, the app routes its inputs
as the PC controller instead of displaying on-screen controls. The 🎮 button toggles between *Auto*, *On-screen*, or *Physical*.

### Player Lobby

Each phone is assigned a **player number and color**, visible on both the phone and the PC. Phones can swap positions
without reconnecting. The player index matches what games and emulators see (XInput slot).

### Controller Test

On the PC, **Settings › 📱 Phone and streaming › 🎮 Controller test** displays real-time input from each phone: pressed
buttons, triggers (LT/RT), both analog sticks, and active gyro data. **📳 Vibrate** triggers haptic feedback on that phone.
This lets you check at a glance whether a button is responsive, an analog stick is drifting off-center, or vibration works,
without having to launch a game or emulator.

### Automatic Emulator Configuration

Certain specialized controllers require specific emulator settings. The app can configure them automatically:

- **PCSX2** for Buzz! or Guitar Hero;
- **Dolphin** for the Wii Remote: DSU server, "Pozzo Launcher Phone N" profiles, Wii Remote 1…N.

Original configuration files are backed up first; **Revert** restores emulator settings to their previous state.

## DS and 3DS Games: Phone as a Second Screen

For DS and 3DS games, a connected phone acts as the **bottom screen**: it displays the bottom touchscreen output and
transmits touches to the PC, while the PC displays the top screen in fullscreen. Supported with melonDS, Citra, Azahar,
and Lime3DS (Windows only). The phone must be connected **before** launching the game: this allows the app to configure
the emulator into separate windows, and restore the original configuration when gameplay ends.

- In **portrait mode**, the touchscreen sits at the top with D-pad and buttons below; in **landscape mode**, the touchscreen
  fills the entire height with semi-transparent controls overlaid on top.
- While the phone is connected, the second screen **does not appear on the PC**. It reappears in a picture-in-picture window
  behind the top screen if the phone disconnects or remains untouched for a period of time: configurable in
  **Settings › 📱 Phone and streaming** (*If phone is idle for… seconds*; default 30s, range 5 to 600s).
- The option **Use phone as touchscreen in DS and 3DS games** on the same settings page disables this feature: when turned off,
  the PC always displays both screens.

## Streaming with Sunshine and Moonlight

To play **away from your PC** (phone, tablet, TV, or another PC), use
[Sunshine](https://app.lizardbyte.dev/Sunshine) on your PC, and [Moonlight](https://moonlight-stream.org) on the client device.

### Publishing Games to Moonlight

**Publish to Moonlight** adds the "Pozzo Launcher Big Picture" entry and your main games with their cover art to Sunshine;
any existing Sunshine apps remain untouched. Moonlight launches `pozzo-cli play --key …`, which stays open for the duration
of your session: streaming shuts down automatically when you finish playing.

### Sunshine Always Ready

If Sunshine is stopped or set to manual startup, Moonlight cannot find your PC. **▶ Start Sunshine** launches it and
configures it to start with Windows, requiring only a single administrator prompt. The settings tab notifies you if it is set
to manual startup, and the **Health** page reports when it is offline.

### Optimize Streaming

**⚡ Optimize streaming** inspects:

- Sunshine process status and Windows startup configuration;
- NVIDIA encoder preset, two-pass mode, and error correction;
- Whether the PC is connected via Ethernet cable or Wi-Fi.

For any identified issue, it provides step-by-step resolution instructions, along with recommendations for TVs, streaming boxes,
and phones: TV Game Mode, Ethernet cabling, frame pacing, bitrate, Moonlight performance overlay stats, and using a dedicated
streaming box (Nvidia Shield, Apple TV 4K, Google TV Streamer) rather than a built-in TV app, which decodes video significantly faster.

### How to Play: TV, Phone, iPad

- **TV**: connect your controller via Bluetooth to the TV (or streaming box); inputs route to the PC as a virtual Xbox
  controller via Moonlight → Sunshine → ViGEmBus.
- **Phone or iPad**: use Moonlight's on-screen controls or a paired Bluetooth controller.
- **Phone as controller** for a game displayed on your TV or monitor: using the phone web app detailed above.

## Playing with a Remote Friend

A friend can join your game session from their home: their phone becomes a **player 2 controller** and video streams via
**Moonlight**. Your PC remains secure — the guest cannot see your library, cannot touch settings, and cannot move your mouse.

1. In **Settings › 📱 Phone and streaming › 🎮 Play with a remote friend**, choose how to expose your PC externally and paste
   your **public address**: a Cloudflare Tunnel (`cloudflared tunnel --url https://localhost:8766`), ngrok, or Tailscale Funnel.
   Leaving this blank restricts invitations to your local home network.
2. Click **Create friend invite** and send them the **link** and **6-digit code**. The invitation is valid for 10 minutes,
   single-use, and for one guest only; allowing them back in later requires generating a new invite.
3. Your friend opens the link, enters the code and their name, and immediately sees the active controller: their phone is
   registered as **Player 2** (or the next available player slot).
4. **Video**: your friend installs [Moonlight](https://moonlight-stream.org), adds your PC address (remote access requires
   a private network such as Tailscale), and enters the **4-digit PIN** displayed by Moonlight into the invite page: the PC
   pairs automatically, without needing to open Sunshine's management interface.

The **Guests** list provides a **Remove** action, identical to paired phones: the guest is instantly disconnected from controller access.
