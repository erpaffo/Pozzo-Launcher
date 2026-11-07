# Big Picture

Big Picture is the **full-screen controller interface**, designed for a PC connected to a TV.

![Big Picture: Shelves Home with featured game and controller commands at the bottom](../images/bigpicture.jpg)

## Opening Big Picture

- Click the **🎮 Big Picture** button at the top of the main window;
- Run `python -m pozzo app --bigpicture` to start the app directly in full-screen;
- Run `pozzo bigpicture`, which reuses the existing window if already open;
- From Moonlight, using the "Pozzo Launcher Big Picture" app published in Sunshine (see
  [Phone and streaming](telefono-streaming.md#streaming-with-sunshine-and-moonlight)).

## Views and Screens

- **Shelves Home**: *Continue Playing*, *Favorites*, *Installed PC games*, largest collections,
  consoles, recommendations, and smart collections. Background and logo change dynamically with the selected game.
- **Library, Consoles, Collections, Favorites** presented as navigable grids.
- Big Picture is designed strictly for playing: it only displays **launchable** games (ROMs present and installed PC games)
  and hides online store catalogs or uninstalled games. No Store or Free Games views.
- The navigation bar scrolls horizontally (scroll wheel, arrow keys, LB/RB) if it exceeds window width; **Exit**
  remains permanently pinned and visible on the right.
- **Search** with an on-screen virtual keyboard.
- **Game details page** with Play or Install, Favorite toggle, Status, Versions, and **Remove from Recently Played**.
- The **What do you want to play?** questionnaire, identical to the *For You* view.

## Controls

| Controller | Keyboard | Action |
|---|---|---|
| D-pad or stick | Arrow keys | Navigate / Move |
| A | Enter | Confirm |
| B | Esc | Back |
| Y | `/` | Search |
| X | `F` | Favorite |
| LB / RB | | Quick scroll |
| Select + Start held for 2 seconds | | Close running game |

Compatible with Xbox, PlayStation, Switch Pro, and other controllers recognized by the operating system. The shortcut to
close running games also works while the game is focused in the foreground, with XInput (Xbox) controllers.

## Accessibility

In the **Appearance** tab of Big Picture:

- **color blindness palettes**: deuteranopia, protanopia, tritanopia;
- **high contrast** mode;
- three **text size options**;
- **interface sound effects** for navigation, confirmation, back, and error actions;
- **screen reader voice narration** for the currently focused item (`aria-live` region): works with Windows Narrator
  and standard screen readers.

Settings are saved locally on the PC.

## Theme

Big Picture uses the theme selected in **Settings › Appearance**. A theme can include a dedicated stylesheet for
Big Picture (see [Themes and plugins](ESTENSIONI.md#themes)).

### Animations

Animations (staggered cover entrances, hover lift, dialogs, notifications, controller focus ring) feature distinct
characteristics per theme: smooth and luminous in Night Blue, crisp in OLED, soft elevation shadows in Light, and
stepped in Retro. They automatically disable if Windows has "Show animations" turned off (`prefers-reduced-motion`).
Alternatively, you can set them from the browser console: `GSMotion.set("reduced")`, `"off"`, or `"normal"`.
