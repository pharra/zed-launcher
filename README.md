# Zed Launcher

A game launcher for Linux that runs Windows games through
[UMU-Launcher](https://github.com/Open-Wine-Components/umu-launcher) and Proton,
built with **NixOS as a first-class target**.

The UI is a [HeroUI v3](https://www.heroui.com/) React application served by a small
Python/FastAPI backend and shown in a GTK4 + WebKitGTK window.

> **Status:** early development. Library management, per-game prefixes, launching,
> live logs, Proton discovery and downloads, desktop shortcuts and diagnostics work.

## Features

- **Library** — create, edit, remove, search and sort games; per-game covers.
- **English and Chinese** — the header language menu picks `English` or `中文`, Settings also offers
  `Follow system`; the choice is stored in the config file and desktop notifications follow it.
- **Create a game (guided wizard)** — a new, dedicated Wine prefix is always created inside your prefix folder:
  1. Choose **install from an installer** or **I already have the executable**.
  2. Pick the file, title, Proton build and prefix folder name (with a live path preview).
  3. For installers: run the setup inside the new prefix with live output, then the launcher
     reads the shortcuts the installer created (`.lnk` → target inside the prefix) and offers the
     installed program. If nothing is found you can pick the executable manually, start from a
     prefix scan, or re-run the installer.
  4. Add a cover, toggle MangoHud / GameMode / Gamescope / sleep inhibition / Wayland / WOW64, create.
- **Add existing game** — attach an executable to a Wine prefix that already exists (validated by `drive_c`).
- **Per-game tool arguments** — Gamescope and MangoHud can each be configured per game
  (gamescope defaults to `-f` when left empty); the switches stay disabled with an inline
  hint when the tool is missing.
- **Environment variables and game arguments are separate** — the Launch tab has a
  multi-line `KEY=VALUE` environment editor and a plain game-argument list. Old games that
  stored env assignments inside their arguments are migrated automatically.
- **Prefix tools** have their own environment editor (one `KEY=VALUE` per line, remembered for the
  session, default `LANG=C`). Tool runs deliberately drop the session's `LC_*` variables: otherwise
  pressure-vessel regenerates your desktop locale inside the container on every single run. The
  variables reach the container, as `setlocale "xx_YY.UTF-8": No such file or directory` in the tool
  log proves.
- **Registry import** — picking a `.reg` file (or the *Regedit* tool) runs Proton's own
  `regedit.exe /S` with the file converted to a DOS path (`Z:\home\…`). Passing a bare
  `regedit` made umu warn *Executable not found* and fall back to the prefix copy, and the
  console `reg.exe` never returns because wineconsole keeps its window open.
- **Prefix tools** — click the prefix name on a game card to run a file inside the prefix,
  open `winecfg`, import a `.reg`, run `winetricks` (with one-click presets such as
  vcrun2022 + corefonts, .NET 4.8, PhysX, XAudio), rescan for programs, see the prefix size,
  clean temporary files, clone the prefix and terminate leftover Wine processes that belong
  to that prefix only.
- **Scan picker** — while adding a game, scan the prefix for installed programs and pick one
  instead of typing a path.
- **Game details** — click a title for playtime, prefix/executable summary, recent runs with
  status, duration, exit code and a shortcut to the log file.
- **Running indicator** — the header shows how many games are running and can stop them all. A
  running game's card swaps *Play* for *Log* and *Stop*: the log drawer can be closed and
  reopened at any time, pressing play again opens the existing run instead of failing with
  "already running".
- **Reattach after a restart** — a game started earlier still shows as running with its log
  tailed from the log file, and can be stopped from the launcher; runs whose process is gone
  (crash, reboot) are closed automatically instead of lingering.
- **Failure hints** — when a run exits badly the log drawer explains likely causes
  (missing Vulkan driver, broken prefix, missing runtimes/DLLs, anti-cheat, full disk).
- **Single instance** — launching Zed Launcher again focuses the existing window.
- **Tray and autostart** — optionally keep the launcher in the system tray (StatusNotifierItem
  implemented directly, so no GTK3 dependency): closing the window hides it, the tray menu can
  reopen it, stop a running game or quit. The icon is published both as a theme name and as an
  `IconPixmap`, so it renders even when the app icon is not installed in the system icon theme.
  The toggle takes effect immediately, and the window only hides when the desktop really has a
  `StatusNotifierWatcher` — otherwise it closes normally instead of leaving an invisible app
  running, and Settings shows a warning explaining how to get one (KDE/XFCE panel, GNOME
  AppIndicator extension). A second toggle writes an XDG autostart entry.
- **Backups** — create/list/restore/delete zip backups of the library and covers from Settings,
  optionally including savegames (`My Games`, `Saved Games`, `AppData/Roaming`, `AppData/LocalLow`)
  with a size estimate. Backups are taken through a SQLite snapshot so they are never half-written,
  and a restore refuses a zip that does not contain a real library.
  Prefixes are never copied; their paths are recorded in the manifest. Restoring keeps the
  previous database as `library.db.before-restore`. Automatic daily/weekly backups run while
  the launcher is open.
- **Launch pipeline** — per-game prefix, Proton build, game arguments, environment variables,
  pre-launch/post-exit hooks, MangoHud, GameMode, Gamescope, SDL, Wayland driver, WOW64
  and sleep inhibition. The resolved command line is
  `[systemd-inhibit] [gamemoderun] [gamescope <args> --] [mangohud <args>] umu-run <exe> <game args>`:
  `umu-run` takes the executable as its first argument, so nothing is inserted in front of it.
  Tool-specific options live next to the matching switch (Gamescope/MangoHud), everything else
  that `umu-run` cannot accept as an argument belongs in the environment variables — this is
  exactly how `umu-launcher` is configured (`DXVK_*`, `PROTON_*`, `UMU_*`, `WINEDLLOVERRIDES`).
- **A curated game environment** — the launcher runs inside a Nix build environment, and passing
  that on to Proton breaks the container: pressure-vessel tries to capture the launcher's
  `LD_LIBRARY_PATH`/GTK/GObject paths as host libraries. Only the session variables a game needs are
  forwarded (`DISPLAY`, `WAYLAND_DISPLAY`, `XAUTHORITY`, `XDG_*`, D-Bus, locale, PulseAudio/PipeWire,
  GPU driver selection and the global `WINE*`/`DXVK_*`/`VKD3D_*`/`MANGOHUD`/`GAMESCOPE_*` knobs);
  `LD_*`, `PYTHON*`, `GI_*`, `GTK_*`, `QT_*`, `NIX_*`, `STEAM_*`, `PROTON_*`, `UMU_*` and anything
  from the editor are dropped, and `PATH` is the plain host path instead of the launcher's.
- **Proton's own log is opt-in** — Settings → *Verbose Proton log* also writes `steam-*.log` next to
  the run log; the last 20 are kept and older ones are pruned at startup.
- **Extra programs run in one container** — the Programs tab lists the game itself (read-only path)
  plus any number of extra executables, reorderable by dragging (or with the arrows). The launcher
  writes a `.bat` that starts every row in order and calls `umu-run` **once** for the whole run:

  ```bat
  @echo off
  start "" "z:/…/trainer.exe" --cfg …   :: before the game, keeps running
  ping -n 6 127.0.0.1 >nul              :: 5s delay of the next row
  start "" "z:/…/game.exe" -flag        :: the game
  start "" "z:/…/after.exe"             :: starts once the game is up
  exit
  ```

  The `.bat` is handed to `umu-run` **as the executable**, exactly like Faugus does: wine runs a
  batch file through the shell without allocating a console, so no `cmd` window appears (passing
  `cmd.exe /c script` opens one). No row uses `start /wait` — Proton keeps the session, and
  therefore the container, alive until the wine processes finish, so the rows below the game start
  as soon as the game is up. Rows use `z:/…` (forward slashes, always quoted) because that is the
  form wine's `start` parses most reliably.

  One invocation means one pressure-vessel container and one wineserver, so trainers and overlays
  share the game's wine session; separate `umu-run` calls would each get their own `/tmp` and
  therefore their own `wineserver`. Delays use `ping -n` (the only sleep a bare `cmd` offers) and a
  missing file is dropped from the script with a note in the log. Scripts live in
  `$XDG_STATE_HOME/zed-launcher/scripts/` and the last 200 are kept.

  pressure-vessel only exposes the target executable's directory, the prefix and Proton inside the
  container, so an extra program stored elsewhere (a deck tracker on another disk, for example) is
  invisible and `start` fails without a word. The launcher therefore adds the directory of every
  program in the script to `PRESSURE_VESSEL_FILESYSTEMS_RW`, which asks pressure-vessel to bind
  them read-write; a value set in the game's environment is kept and extended.
- **Live output** — stream stdout/stderr over WebSocket, keep a log file, stop the whole
  process group, track playtime.
- **Process ownership** — every launch exports `ZED_RUN_ID=<run id>`, so the launcher can find
  the whole tree again after `wineserver`, `services.exe` and the game itself call `setsid` and
  leave its process group. Stopping a game kills the group *and* everything carrying the marker,
  reaps wineserver when the game exits on its own, and keeps extra programs of one run from
  touching another. Runs record the pid **and** its `/proc/<pid>/stat` start time, so a recycled
  pid can never keep a finished run "running" or be signalled by mistake. The run also stops
  reading the game's output a couple of seconds after the process exits, because wineserver and
  any daemon the game started inherit that pipe and would otherwise keep it open forever - the
  reason a finished game could still look "running". The header badge polls the active runs, so
  it clears by itself while the window is open.
- **Prefix cleanup uses the prefix, not a guess** — a Wine process is matched by an exact
  `WINEPREFIX=` environment entry (or, for helpers that dropped it, a known wine binary whose
  working directory is inside the prefix). Unrelated processes that merely run inside the folder
  are left alone.
- **Runs outlive the window** — every launch spawns a detached watcher, so the exit code
  and playtime are still recorded after the launcher is closed.
- **Installer sessions are resumable** — the shortcut baseline is stored in SQLite, so detection
  still works after a restart, and the game is created on top of the prefix the installer used.
- **Proton manager**
  - Scans the Nix store, `~/.local/share/Steam/compatibilitytools.d`,
    `~/.steam/steam`, `~/.steam/root` and the Steam Flatpak directory.
  - Adds any Proton folder manually.
  - Lists and downloads GE-Proton releases with progress, transfer rate, ETA and cancellation;
    the downloaded archive is validated before it is accepted.
  - Shows the disk usage of each build, flags a newer release, and refuses to delete a build
    that a game still uses.
  - Optional GitHub API token raises the GitHub rate limit.
- **Artwork**
  - Cover images from a local file, or from **SteamGridDB** (search → grids → pick) using your
    own API key.
  - **Icon extraction** — the icon of the game `.exe` is pulled with `icoextract`, converted to
    PNG and shown on the game card when no cover is set.
- **Desktop notifications** — `notify-send` reports the exit status and playtime when a game
  finishes; toggled in Settings and disabled automatically when `notify-send` is missing.
- **Desktop shortcuts** — generated `.desktop` entries call `zed-launcher --run <id>`. The card
  button switches to *Remove shortcut* once the entry exists, so it can be deleted again.
- **Log retention** — finished runs are pruned per game (50 kept) together with their log files.
- **Diagnostics** — umu-run, MangoHud, GameMode, Gamescope, notify-send, icoextract, GPU,
  Proton sources and storage.
- **NixOS/Home Manager modules**, overlay, dev shell, checks and formatter.
- **HeroUI MCP wired in** — `.vscode/mcp.json` and `.mcp.json` point at `@heroui/react-mcp`
  so assistants generate HeroUI v3 code from the official component docs.

## Dependencies

Zed Launcher splits runtime dependencies into required and optional ones.

| Kind | Dependency | Behaviour when missing |
| --- | --- | --- |
| required | `umu-run` | Setup prompt at startup, games cannot be created or launched; the path is shown in Settings |
| required | Proton build | Setup prompt at startup with a shortcut to the Proton manager |
| optional | MangoHud | per-game switch disabled with "MangoHud is not installed" |
| optional | GameMode | per-game switch disabled |
| optional | Gamescope | per-game switch disabled |
| optional | `systemd-inhibit` | "Prevent sleep" switch disabled |
| optional | `notify-send` | desktop notification switch disabled with an inline hint |
| optional | `icoextract` | icon extraction button reports that it is unavailable |

Every dependency can point at an explicit binary: Settings has a path field next to each tool
(and for `umu-run`). A configured path wins over `PATH` lookup, is validated when saved, and
falls back to auto-detection if the file later disappears; empty means "detect automatically".
Proton builds are configured through the Proton manager (scan results + manual folders).

`umu-run` must be the **wrapped** launcher, not `umu-launcher-unwrapped`: pressure-vessel needs an
`ld.so.cache` and a `true` binary inside its container, and only the wrapper provides them on NixOS.
The package and the dev shell use `pkgs.umu-launcher`; pointing the override at an unwrapped build
fails with `bwrap: execvp true: No such file or directory` (or
`capsule-capture-libs: /var/cache/ldconfig/ld.so.cache: Permission denied`).

Detected paths are always shown instead of generic placeholders: Settings lists the resolved
`umu-run` path and every optional tool path (or "Not installed"), and only the override inputs
show a placeholder. The default Proton is the
first detected build unless you pick another one; a missing build is never silently replaced.

SteamGridDB is optional and needs an API key from
[steamgriddb.com/profile/preferences/api](https://www.steamgriddb.com/profile/preferences/api);
without a key the cover picker reports that a key is required and the rest of the app is
unaffected.

## Desktop client

The app ships as a native window, not a browser tab:

```
GTK4 + WebKitGTK window  →  http://127.0.0.1:<random port>/?token=…
        FastAPI backend  →  SQLite library, launch manager, Proton manager
```

`--browser` is available for debugging. The web layer is the UI technology only —
Tauri and Electron use the same pattern, but the GTK shell reuses the WebKit already
present on the system, needs no extra runtime, and packages cleanly with Nix. A Tauri
shell can be added later for Windows/macOS while keeping this backend and frontend.

## Installation

```bash
nix run github:pharra/zed-launcher
nix profile install github:pharra/zed-launcher
```

### NixOS module

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    zed-launcher.url = "github:pharra/zed-launcher";
  };

  outputs = { nixpkgs, zed-launcher, ... }: {
    nixosConfigurations.my-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        zed-launcher.nixosModules.default
        {
          services.zed-launcher.enable = true;

          # umu-launcher needs the Steam runtime for 32-bit graphics libraries
          programs.steam.enable = true;
        }
      ];
    };
  };
}
```

| Option | Default | Description |
| --- | --- | --- |
| `services.zed-launcher.enable` | `false` | Install the launcher system-wide. |
| `services.zed-launcher.package` | flake package | Package to install. |
| `services.zed-launcher.extraPackages` | `mangohud`, `gamemode`, `gamescope` | Tools placed on `PATH`. |

### Home Manager module

```nix
{
  imports = [ inputs.zed-launcher.homeManagerModules.default ];

  programs.zed-launcher.enable = true;

  programs.zed-launcher.settings = {
    prefix_root = "/home/you/Games/Zed";
    proton_default = "/home/you/Games/protons/GE-Proton9-20";
  };
}
```

The packaged wrapper sets `ZED_WEB_ROOT`, `ZED_PROTON_PATH`
(`proton-ge-bin.steamcompattool`) and a `PATH` containing `umu-launcher` and `xdg-utils`.
Additional Proton builds come from Steam folders or the Proton manager.

## Usage

```bash
zed-launcher                                   # open the GTK window
zed-launcher --browser                         # open in the default browser
zed-launcher --serve --port 8765 --token dev   # API/UI server only
zed-launcher --run <game-id>                   # headless launch (used by .desktop files)
zed-launcher --add /path/to/game.exe --title "My Game"
zed-launcher --add /path/to/game.exe --existing-prefix /path/to/prefix
zed-launcher --list
zed-launcher --diagnostics
```

The backend binds to `127.0.0.1` on a random port and requires a per-session token
(`X-Zed-Token` header or `?token=`). The GTK shell and browser mode receive the URL with
the token; the frontend stores it in `localStorage`.

## Development

```bash
nix develop

# Backend
cd backend
python -m pytest
ruff check src tests
python -m zed_launcher --serve --port 8765 --token dev

# Frontend (proxies /api to 127.0.0.1:8765)
cd frontend
npm install
npm run dev
# open http://localhost:5173/?token=dev
```

```bash
nix build .#default
nix flake check
nix fmt
```

### HeroUI MCP

```json
{
  "servers": {
    "heroui-react": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@heroui/react-mcp@latest"]
    }
  }
}
```

Development-time only: it exposes `list_components`, `get_component_docs`,
`get_component_source_code`, `get_theme_variables` and documentation lookup for HeroUI v3.
The runtime depends only on `@heroui/react` and `@heroui/styles`.

## Architecture

```
backend/        FastAPI + SQLite + launch manager
  src/zed_launcher/
    api/        REST + WebSocket endpoints
    services/   command builder, runner, prefixes, proton, shortcuts, artwork, system
    watch.py    detached run watcher
    shell/      GTK4 + WebKitGTK window
frontend/       React 19 + Vite + Tailwind CSS v4 + HeroUI v3
nix/            package, NixOS module, Home Manager module, overlay, dev shell, checks
```

Data model:

- `games` stores one row per game with its own `prefix_path`, `proton_path` and toggles.
- `owned_prefix` marks prefixes created by the launcher; only those can be deleted with the game.
- `runs` records every launch with status, exit code, duration, log path, plus `pid` and
  `pid_started` (the `/proc/<pid>/stat` start time) so the launcher can verify that a recorded
  process is still the one it started.
- Settings hold `language`, `notifications`, `tray`, `backup_schedule`, `steamgriddb_api_key`,
  `proton_log` and `tool_paths` (explicit binary overrides) alongside the runtime paths.
- Tool arguments (Gamescope, MangoHud) live on the game row, next to `env` and `launch_args`.

Launch flow:

1. `POST /api/v1/games/{id}/launch` resolves the prefix, Proton build and tools.
2. A pure command builder produces `argv`, environment variables and the working directory.
3. The run manager spawns the process in its own session, streams output to a buffer,
   a log file and WebSocket subscribers, and starts a detached watcher. The pid is stored on
   the run row so a restart can tell live runs from stale ones.
4. The watcher records the exit and playtime even if the launcher was closed. Closing a run
   is a conditional database update, so the watcher and the GUI cannot both credit playtime.

## Data

| Path | Contents |
| --- | --- |
| `$XDG_CONFIG_HOME/zed-launcher/config.json` | settings |
| `$XDG_DATA_HOME/zed-launcher/library.db` | SQLite library and runs |
| `$XDG_DATA_HOME/zed-launcher/artwork/` | `covers/` (local or SteamGridDB) and `icons/` (extracted from the `.exe`) |
| `$XDG_DATA_HOME/zed-launcher/backups/` | default backup folder |
| `$XDG_DATA_HOME/zed-launcher/protons/` | Proton builds downloaded in-app |
| `$XDG_STATE_HOME/zed-launcher/logs/` | per-run logs (plus Proton's `steam-*.log` when verbose logging is on) |
| `$XDG_STATE_HOME/zed-launcher/scripts/` | generated `.bat` of the last runs (launch order, deleted after 200) |
| `~/Games/Zed` | default prefix folder |

## Roadmap

- Categories, favourites and custom ordering
- Gamepad / big picture mode
- More languages — add an entry to `LANGUAGES` in `frontend/src/lib/i18n.tsx` and it appears in the
  header menu and the Settings picker (the `t(en, zh)` helper still needs a per-string translation)
- Anti-cheat runtimes (`PROTON_EAC_RUNTIME` / `PROTON_BATTLEYE_RUNTIME`) — without them games using
  EAC/BattlEye still refuse to start (Faugus bundles these runtimes)
- Per-game GPU selection (`DRI_PRIME`, `MESA_VK_DEVICE_SELECT`, `__NV_PRIME_RENDER_OFFLOAD`)

## License

MIT
