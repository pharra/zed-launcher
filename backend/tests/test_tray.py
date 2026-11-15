"""Tray icon protocol tests.

They run against a private session bus and are skipped when gi/dbus are missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

gi = pytest.importorskip("gi")

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio  # noqa: E402

from zed_launcher.shell import tray  # noqa: E402


def test_xml_is_valid() -> None:
    sni = Gio.DBusNodeInfo.new_for_xml(tray.SNI_XML)
    menu = Gio.DBusNodeInfo.new_for_xml(tray.MENU_XML)
    assert [entry.name for entry in sni.interfaces] == [
        "org.kde.StatusNotifierItem",
        "org.freedesktop.DBus.Properties",
    ]
    assert [entry.name for entry in menu.interfaces] == [
        "com.canonical.dbusmenu",
        "org.freedesktop.DBus.Properties",
    ]


def test_icon_pixmap_matches_the_expected_size() -> None:
    pixmap = tray.icon_pixmap()
    assert pixmap is not None, "the bundled tray icon payload is missing"
    assert len(pixmap) == tray.PIXMAP_SIZE * tray.PIXMAP_SIZE * 4


def test_menu_lists_running_games() -> None:
    icon = tray.TrayIcon(on_open=lambda: None, on_quit=lambda: None)
    icon.update([("run-1", "Celeste")])
    ids = [item["id"] for item in icon._menu_items()]
    assert tray.OPEN_ID in ids
    assert tray.QUIT_ID in ids
    assert tray.FIRST_GAME_ID in ids

    stopped: list[str] = []
    icon.on_stop = stopped.append
    by_id = {item["id"]: item for item in icon._menu_items()}
    icon._dispatch(tray.FIRST_GAME_ID, "clicked", by_id)
    assert stopped == ["run-1"]


SCRIPT = textwrap.dedent(
    """
    import sys
    import threading
    import gi
    gi.require_version("Gio", "2.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import Gio, GLib

    sys.path.insert(0, {src!r})
    from zed_launcher.shell import tray

    opened = []
    stopped = []
    icon = tray.TrayIcon(
        on_open=lambda: opened.append(True),
        on_quit=lambda: None,
        on_stop=stopped.append,
    )
    assert icon.register(), "tray registration failed"
    icon.update([("run-1", "Celeste")])

    loop = GLib.MainLoop()
    threading.Thread(target=loop.run, daemon=True).start()

    # A second connection, otherwise call_sync would block our own handlers.
    address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
    connection = Gio.DBusConnection.new_for_address_sync(
        address,
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None,
        None,
    )
    name = icon.sni_registered

    result = connection.call_sync(
        name,
        tray.SNI_PATH,
        "org.freedesktop.DBus.Properties",
        "GetAll",
        GLib.Variant("(s)", ("org.kde.StatusNotifierItem",)),
        GLib.VariantType("(a{{sv}})"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    props = result.get_child_value(0)
    assert props.lookup_value("Title", None).get_string() == "Zed Launcher"
    assert props.lookup_value("Menu", None).get_string() == tray.MENU_PATH
    pixmaps = props.lookup_value("IconPixmap", None)
    assert pixmaps.n_children() == 1, "IconPixmap must be provided for hosts without the icon theme"
    width, height, data = pixmaps.get_child_value(0).unpack()
    assert (width, height) == (tray.PIXMAP_SIZE, tray.PIXMAP_SIZE)
    assert len(data) == tray.PIXMAP_SIZE * tray.PIXMAP_SIZE * 4
    tooltip = props.lookup_value("ToolTip", None)
    assert tooltip.get_child_value(2).get_string() == "Zed Launcher"

    layout = connection.call_sync(
        name,
        tray.MENU_PATH,
        "com.canonical.dbusmenu",
        "GetLayout",
        GLib.Variant("(iias)", (0, -1, [])),
        GLib.VariantType("(u(ia{{sv}}av))"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    revision, item = layout.get_child_value(0).get_uint32(), layout.get_child_value(1)
    assert revision >= 2

    connection.call_sync(
        name,
        tray.SNI_PATH,
        "org.kde.StatusNotifierItem",
        "Activate",
        GLib.Variant("(ii)", (0, 0)),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    assert opened == [True]

    connection.call_sync(
        name,
        tray.MENU_PATH,
        "com.canonical.dbusmenu",
        "Event",
        GLib.Variant("(isvu)", (tray.FIRST_GAME_ID, "clicked", GLib.Variant("i", 0), 0)),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    assert stopped == ["run-1"]
    loop.quit()
    print("tray-ok")
    """
)


def test_tray_registers_on_a_session_bus(tmp_path: Path) -> None:
    if not os.environ.get("DBUS_RUN_SESSION_TESTED") and shutil.which("dbus-run-session") is None:
        pytest.skip("dbus-run-session is not available")

    package_src = str(Path(__file__).resolve().parents[1] / "src")
    script = tmp_path / "tray_probe.py"
    script.write_text(SCRIPT.format(src=package_src), encoding="utf-8")

    env = dict(os.environ, DBUS_RUN_SESSION_TESTED="1", PYTHONPATH=package_src)
    completed = subprocess.run(
        ["dbus-run-session", "--", "python", str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if "Failed to start message bus" in completed.stderr:
        pytest.skip("no D-Bus machine id in this sandbox")
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "tray-ok" in completed.stdout
