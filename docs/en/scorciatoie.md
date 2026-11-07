# Keyboard Shortcuts

Pozzo Launcher can be navigated entirely without a mouse: using a keyboard on PC or a controller in Big Picture.
On macOS, **Cmd (⌘)** replaces **Ctrl**; the app automatically displays the appropriate symbol in menus, tooltips,
and the shortcuts modal (`?` or **Ctrl/Cmd + /**, or *Settings → General → Keyboard shortcuts*).

Shortcuts **do not trigger while typing** in a text field (except shortcuts specifically designed with Ctrl/Cmd, such as search).
Browser copy, paste, reload, and other native combinations remain unaffected.

## Keyboard

| Action | Windows / Linux | macOS |
|---|---|---|
| Search | `Ctrl+K` or `/` | `⌘K` or `/` |
| Settings | `Ctrl+,` | `⌘,` |
| Library | `Ctrl+1` | `⌘1` |
| Favorites | `Ctrl+2` | `⌘2` |
| Store | `Ctrl+3` | `⌘3` |
| Wishlist | `Ctrl+4` | `⌘4` |
| Statistics | `Ctrl+5` | `⌘5` |
| Toggle Explore sidebar | `Ctrl+B` | `⌘B` |
| Back / close | `Alt+←`, `Ctrl+[` or `Esc` | `⌥←`, `⌘[` or `Esc` |
| Scan for new games | `Ctrl+Shift+S` | `⌘⇧S` |
| Refresh library | `Ctrl+Shift+R` | `⌘⇧R` |
| Launch open game | `Enter` | `Enter` |
| Favorite (open game) | `F` | `F` |
| Hide/unhide (open game) | `H` | `H` |
| Random game | `R` | `R` |
| Big Picture (enter / exit) | `Ctrl+Shift+B` or `F11` | `⌘⇧B` or `F11` |
| Next artwork/graphics mode | `Ctrl+Shift+E` | `⌘⇧E` |
| Next theme | `Ctrl+Shift+T` | `⌘⇧T` |
| Switch user ("Who's playing?" screen, also in Big Picture) | `Ctrl+P` | `⌘P` |
| Shortcut list | `Ctrl+/` or `?` | `⌘/` or `?` |
| Show/hide key legend (Big Picture) | `Ctrl+Shift+H` | `⌘⇧H` |

Music and Discord (active only when media integration is enabled, otherwise inactive):

| Action | Windows / Linux | macOS |
|---|---|---|
| Play / pause | `Ctrl+Alt+P` | `⌘⌥P` |
| Next track | `Ctrl+Alt+→` | `⌘⌥→` |
| Previous track | `Ctrl+Alt+←` | `⌘⌥←` |
| Discord mute microphone | `Ctrl+Alt+M` | `⌘⌥M` |
| Discord deafen audio | `Ctrl+Alt+D` | `⌘⌥D` |

### Customizing Shortcuts

In the shortcuts panel, click **Change** next to an action to record a new key combination (Esc cancels); if it is already
bound to another action, the app alerts you and prevents overwriting. **Reset** restores the default key. Customizing an action
with multiple defaults (such as "Back") replaces both. The `/`, `Esc`, and `Enter` keys cannot be rebound.
Preferences are saved in the app's browser storage (`gs.shortcuts`).

## During a Game (Windows)

While a game is running these shortcuts work, even with the game in the foreground:

| Action | Keyboard | Controller |
|---|---|---|
| In-game overlay | `Ctrl+Shift+O` | Select + R3 |
| Pause / resume the game | `Ctrl+Shift+P` | Select + L1 |
| Screenshot | (see the screenshot settings) | Select + R1 |
| Close the game | | Select + Start (held 2 seconds) |

The two keyboard shortcuts can be changed in the screenshot settings. The overlay is not drawn over exclusive
fullscreen games. Details in [Playing Games](giocare.md#in-game-overlay) and
[Close Game, Job Object and Pause](giocare.md#close-game-job-object-and-pause).

## Controller (Big Picture)

Uses standard Gamepad API mappings: Xbox, PlayStation (✕ ○ □ △), and Switch Pro. Visual labels adapt automatically.
Controller polling initializes only when a controller is detected (press any button once) and throttles down when idle.

| Button | Action |
|---|---|
| A (✕) | Confirm / open |
| B (○) | Back |
| X (□) | Favorite |
| Y (△) | Search |
| LB / RB | Previous / next category |
| LT / RT, right stick | Page up / down |
| D-pad or left stick | Navigate (repeats when held) |
| Start | Screen menu |
| L3 | Return to Home |
| R3 | Show/hide bottom legend |
| Select / View (tap) | Quick action panel |
| Select held for 1 second | Exit Big Picture |
| Select + A | Music: play/pause |
| Select + RB / LB | Next / previous track |
| Select + X | Discord: mute microphone |
| Select + Y | Discord: deafen audio |
| Select + B | Exit Big Picture |
| Select + Start (held) | Close running game |

Thumbsticks include a deadzone, and multiple simultaneously connected controllers are supported. When a game is active,
interface navigation controls are suspended; Select + Start and music/Discord shortcuts remain active.

See also [Big Picture](bigpicture.md).
