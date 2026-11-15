from __future__ import annotations

import json
import sys
import urllib.request


def _api(base_url: str, token: str, path: str, method: str = "GET") -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    request = urllib.request.Request(url, method=method)
    request.add_header("X-Zed-Token", token)
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - local URL
        payload = response.read()
    return json.loads(payload or b"{}")


def watcher_available() -> bool:
    """Is there a StatusNotifierWatcher (KDE panel, XFCE, AppIndicator host) around?"""

    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            GLib.Variant("(s)", ("org.kde.StatusNotifierWatcher",)),
            GLib.VariantType("(b)"),
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )
    except Exception:
        return False
    return bool(reply.get_child_value(0).get_boolean())


def run_window(url: str, token: str = "", keep_in_tray: bool = False) -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Gio, GLib, Gtk, WebKit

    from .tray import TrayIcon

    base_url = url.split("?", 1)[0]

    class LauncherWindow(Gtk.ApplicationWindow):
        def __init__(self, application: Gtk.Application) -> None:
            super().__init__(application=application, title="Zed Launcher")
            self.set_default_size(1280, 820)
            self.set_size_request(900, 600)
            self.tray = None

            webview = WebKit.WebView()
            webview.set_hexpand(True)
            webview.set_vexpand(True)
            settings = webview.get_settings()
            settings.set_enable_developer_extras(True)
            webview.load_uri(url)
            self.set_child(webview)

        def do_close_request(self) -> bool:
            # Hide only when something can actually show the icon again; otherwise a
            # missing/broken tray host would leave the app running with no way back.
            if self.tray is not None and watcher_available():
                self.set_visible(False)
                return True
            if self.tray is not None:
                print(
                    "Zed Launcher: closing the window because the desktop has no "
                    "StatusNotifierWatcher to host the tray icon.",
                    file=sys.stderr,
                )
            return False

    class LauncherApplication(Gtk.Application):
        """Single-instance shell: a second launch focuses the existing window."""

        def __init__(self) -> None:
            super().__init__(
                application_id="io.github.pharra.ZedLauncher",
                flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            )
            self.tray: TrayIcon | None = None
            self.window: LauncherWindow | None = None
            self.tray_timer: int | None = None
            self.tray_pending = False

        def do_activate(self) -> None:
            window = self.get_active_window()
            if window is None:
                window = self.window or self.build_window()
                self.window = window
            window.set_visible(True)
            window.present()

        def build_window(self) -> LauncherWindow:
            window = LauncherWindow(self)
            window.tray = self.tray
            return window

        def do_startup(self) -> None:
            Gtk.Application.do_startup(self)
            self.tray_wanted = keep_in_tray
            if keep_in_tray:
                self.enable_tray()
            # Settings can switch the tray on or off while the app is running.
            self.tray_timer = GLib.timeout_add_seconds(2, self.sync_tray)

        def enable_tray(self) -> bool:
            if self.tray is not None or self.tray_pending:
                return self.tray is not None
            self.tray_pending = True
            # Register from the main loop: the watcher queries our properties while
            # handling the registration call, which cannot be answered during startup.
            GLib.idle_add(self._register_tray)
            return True

        def _register_tray(self) -> bool:
            self.tray_pending = False
            if self.tray is not None:
                return False
            tray = TrayIcon(
                on_open=self.show_window,
                on_quit=self.quit_app,
                running_titles=self.running_games,
                on_stop=self.stop_run,
            )
            if not tray.register():
                return False
            self.tray = tray
            if self.window is not None:
                self.window.tray = tray
            if not watcher_available():
                print(
                    "Zed Launcher: no StatusNotifierWatcher on the session bus — "
                    "the tray icon needs a host such as the KDE panel, XFCE panel or "
                    "the GNOME AppIndicator extension.",
                    file=sys.stderr,
                )
            self.refresh_tray()
            return False

        def disable_tray(self) -> None:
            if self.tray is None:
                return
            self.tray.close()
            self.tray = None
            if self.window is not None:
                self.window.tray = None
                # Never leave the user with a hidden window and no tray entry.
                self.window.set_visible(True)

        def sync_tray(self) -> bool:
            wanted = self.tray_wanted
            if token:
                try:
                    config = _api(base_url, token, "/api/v1/settings")
                    wanted = bool(config.get("tray", wanted))
                except Exception:
                    wanted = self.tray_wanted
            if wanted:
                self.enable_tray()
            else:
                self.disable_tray()
            self.tray_wanted = wanted
            if self.tray is not None:
                self.refresh_tray()
            return True

        def do_shutdown(self) -> None:
            self.stop_tray()
            Gtk.Application.do_shutdown(self)

        def stop_tray(self) -> None:
            if self.tray_timer is not None:
                GLib.source_remove(self.tray_timer)
                self.tray_timer = None
            self.disable_tray()

        def quit_app(self) -> None:
            self.stop_tray()
            self.quit()

        def show_window(self) -> None:
            self.activate()

        def running_games(self) -> list[tuple[str, str]]:
            if not token:
                return []
            try:
                runs = _api(base_url, token, "/api/v1/runs")
            except Exception:
                return []
            return [(run["run_id"], run.get("title") or "Game") for run in runs]

        def stop_run(self, run_id: str) -> None:
            if not token:
                return
            try:
                _api(base_url, token, f"/api/v1/runs/{run_id}/stop", method="POST")
            except Exception:
                return
            self.refresh_tray()

        def refresh_tray(self) -> bool:
            if self.tray is None:
                return False
            self.tray.update(self.running_games())
            return True

    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-application-prefer-dark-theme", True)

    return LauncherApplication().run([])
