# Music and Calls

**Big Picture** mode includes a built-in mini-player for **Spotify**, system media key controls, and voice call management with **Discord**.

You can open or close the media panel using the icon in the top right or by clicking the controller's right thumbstick (`R3`). Once open:
- use the D-pad or left thumbstick to navigate;
- press **A (✕)** to select or toggle states;
- press **B (○)** to close the panel and return to the game.

The panel updates status in real time only while open (at most one Spotify request every 5 seconds to avoid straining PC resources). When Spotify is not connected, play/pause, next/previous track, and volume commands directly control Windows system media keys.

---

## Spotify

Spotify remote control lets you listen to your favorite playlists in the background during gaming sessions, view the currently playing track, and skip to the next track using the `Select + RB` controller shortcut:

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create a new application (it is free).
2. In the Spotify app configuration, add to **Redirect URIs** exactly:  
   `http://127.0.0.1:8765/api/spotify/callback`  
   *(if you changed the default port in `config.toml`, enter your active port).*
3. Copy your **Client ID** and paste it into **Settings › Integrations › Music and calls**.
4. Click **Log in with Spotify** to authorize the application.

> [!NOTE]
> Authentication uses the secure *Authorization Code with PKCE* protocol, without requiring a Client Secret. Remote playback control requires a Spotify Premium account and an active Spotify client running on your PC or local network. If you do not have Spotify Premium, Pozzo Launcher will use system media commands to control any active audio player (such as VLC, foobar2000, or a web browser).

---

## Discord (In-Game Voice Controls)

In addition to Rich Presence (*"Playing..."*, configurable separately), you can manage Discord voice channels directly from the in-game overlay without pressing Alt+Tab:

1. Create a personal application in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Enter the **Application ID** and **Client Secret** in **Settings › Integrations › Music and calls**.
3. Click **Test connection** and approve the requested scopes (`rpc`, `rpc.voice.read`, `rpc.voice.write`) in the Discord prompt window.

### What you can do with your controller during gameplay:
- **Mute or unmute microphone**: shortcut `Select + X (□)`.
- **Deafen or undeafen headset audio**: shortcut `Select + Y (△)`.
- **Adjust volume** or view active participants in the voice channel.

> [!TIP]
> Voice commands require the Discord desktop application to be running on the same PC. OAuth tokens and keys are stored exclusively in Pozzo Launcher's local settings and are never shared externally.
