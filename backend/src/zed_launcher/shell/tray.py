"""A StatusNotifierItem tray icon that works with GTK4.

libayatana-appindicator still drags in GTK3, so this module speaks the
freedesktop StatusNotifierItem + DBusMenu protocols directly over Gio.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <method name="ContextMenu">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="Activate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="Scroll">
      <arg name="delta" type="i" direction="in"/>
      <arg name="orientation" type="s" direction="in"/>
    </method>
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
  </interface>
  <interface name="org.freedesktop.DBus.Properties">
    <method name="Get">
      <arg name="interface" type="s" direction="in"/>
      <arg name="property" type="s" direction="in"/>
      <arg name="value" type="v" direction="out"/>
    </method>
    <method name="GetAll">
      <arg name="interface" type="s" direction="in"/>
      <arg name="properties" type="a{sv}" direction="out"/>
    </method>
    <method name="Set">
      <arg name="interface" type="s" direction="in"/>
      <arg name="property" type="s" direction="in"/>
      <arg name="value" type="v" direction="in"/>
    </method>
  </interface>
</node>
"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <method name="GetLayout">
      <arg name="parentId" type="i" direction="in"/>
      <arg name="recursionDepth" type="i" direction="in"/>
      <arg name="propertyNames" type="as" direction="in"/>
      <arg name="revision" type="u" direction="out"/>
      <arg name="layout" type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg name="ids" type="ai" direction="in"/>
      <arg name="propertyNames" type="as" direction="in"/>
      <arg name="properties" type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg name="id" type="i" direction="in"/>
      <arg name="name" type="s" direction="in"/>
      <arg name="value" type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg name="id" type="i" direction="in"/>
      <arg name="eventId" type="s" direction="in"/>
      <arg name="data" type="v" direction="in"/>
      <arg name="timestamp" type="u" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg name="events" type="a(isvu)" direction="in"/>
      <arg name="idErrors" type="ai" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg name="id" type="i" direction="in"/>
      <arg name="needUpdate" type="b" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg name="updatedProps" type="a(ia{sv})"/>
      <arg name="removedProps" type="a(ias)"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg name="revision" type="u"/>
      <arg name="parent" type="i"/>
    </signal>
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
  </interface>
  <interface name="org.freedesktop.DBus.Properties">
    <method name="Get">
      <arg name="interface" type="s" direction="in"/>
      <arg name="property" type="s" direction="in"/>
      <arg name="value" type="v" direction="out"/>
    </method>
    <method name="GetAll">
      <arg name="interface" type="s" direction="in"/>
      <arg name="properties" type="a{sv}" direction="out"/>
    </method>
    <method name="Set">
      <arg name="interface" type="s" direction="in"/>
      <arg name="property" type="s" direction="in"/>
      <arg name="value" type="v" direction="in"/>
    </method>
  </interface>
</node>
"""

SNI_NAME = "org.kde.StatusNotifierItem"
SNI_PATH = "/StatusNotifierItem"
MENU_NAME = "com.canonical.dbusmenu"
MENU_PATH = "/MenuBar"
WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"

PIXMAP_FILE = Path(__file__).with_name("tray-icon.argb")
PIXMAP_SIZE = 64

OPEN_ID = 1
QUIT_ID = 2
FIRST_GAME_ID = 100


def _variant(value: Any, signature: str) -> Any:
    from gi.repository import GLib

    return GLib.Variant(signature, value)


_pixmap_cache: bytes | None = None


def icon_pixmap() -> bytes | None:
    """Raw ARGB32 pixels for the tray icon, independent of the icon theme.

    Hosts that ignore `IconName` (because the app icon is not installed in the
    system theme) still render `IconPixmap`.
    """

    global _pixmap_cache
    if _pixmap_cache is None:
        try:
            _pixmap_cache = PIXMAP_FILE.read_bytes()
        except OSError:
            return None
    expected = PIXMAP_SIZE * PIXMAP_SIZE * 4
    if len(_pixmap_cache) != expected:
        return None
    return _pixmap_cache


class TrayIcon:
    """Tray icon with an "Open" entry, one "Stop <game>" entry per run, and "Quit"."""

    def __init__(
        self,
        *,
        icon_name: str = "zed-launcher",
        title: str = "Zed Launcher",
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
        running_titles: Callable[[], list[tuple[str, str]]] | None = None,
        on_stop: Callable[[str], None] | None = None,
    ) -> None:
        self.icon_name = icon_name
        self.title = title
        self.on_open = on_open
        self.on_quit = on_quit
        self.running_titles = running_titles or (lambda: [])
        self.on_stop = on_stop or (lambda run_id: None)
        self.pid = os.getpid()
        self.sni_registered = f"{SNI_NAME}-{self.pid}-1"
        self.menu_registered = "org.zedlauncher.Menu"
        self.revision = 1
        self.connection: Any = None
        self._sni_id = 0
        self._menu_id = 0
        self._runs: list[tuple[str, str]] = []
        self.registered_with_host = False

    def register(self) -> bool:
        from gi.repository import Gio

        try:
            self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception:
            return False
        if self.connection is None:
            return False

        for name in (self.sni_registered, self.menu_registered):
            self.connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "RequestName",
                _variant((name, 0,), "(su)"),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )

        sni_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML)
        menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML)
        self._sni_id = self.connection.register_object(
            SNI_PATH, sni_info.interfaces[0], self._on_sni_call, None, None
        )
        self._menu_id = self.connection.register_object(
            MENU_PATH, menu_info.interfaces[0], self._on_menu_call, None, None
        )
        self.connection.register_object(
            MENU_PATH, menu_info.interfaces[1], self._on_menu_props, None, None
        )

        # Async: the watcher introspects the item while handling this call, and a
        # blocking call_sync would stall it until it gives up on us.
        with safe_call():
            self.connection.call(
                WATCHER_NAME,
                WATCHER_PATH,
                WATCHER_NAME,
                "RegisterStatusNotifierItem",
                _variant((SNI_PATH,), "(s)"),
                None,
                Gio.DBusCallFlags.NONE,
                5000,
                None,
                self._on_registered,
                None,
            )
        return True

    def _on_registered(self, connection, result, _user_data) -> None:
        try:
            connection.call_finish(result)
            self.registered_with_host = True
        except Exception:
            self.registered_with_host = False

    def update(self, runs: list[tuple[str, str]]) -> None:
        self._runs = runs
        self.revision += 1
        with safe_call():
            self.connection.emit_signal(
                None, MENU_PATH, MENU_NAME, "LayoutUpdated", _variant((self.revision, 0), "(ui)")
            )

    def close(self) -> None:
        if self.connection is None:
            return
        for object_id in (self._sni_id, self._menu_id):
            if object_id:
                with safe_call():
                    self.connection.unregister_object(object_id)
        self.connection = None

    # -- StatusNotifierItem -------------------------------------------------
    def _on_sni_call(self, _conn, _sender, path, interface, method, params, invocation):
        if method == "Activate" or method == "SecondaryActivate":
            self.on_open()
            invocation.return_value(None)
        elif method == "ContextMenu":
            invocation.return_value(None)
        elif method in ("Get", "GetAll", "Set"):
            self._handle_props(method, params, invocation, self._sni_props())
        else:
            invocation.return_value(None)

    def _sni_props(self) -> dict[str, Any]:
        pixmap = icon_pixmap()
        pixmaps = [(PIXMAP_SIZE, PIXMAP_SIZE, pixmap)] if pixmap else []
        return {
            "Category": _variant("ApplicationStatus", "s"),
            "Id": _variant(self.sni_registered, "s"),
            "Title": _variant(self.title, "s"),
            "Status": _variant("Active", "s"),
            "IconName": _variant(self.icon_name, "s"),
            "IconPixmap": _variant(pixmaps, "a(iiay)"),
            "IconThemePath": _variant("", "s"),
            "Menu": _variant(MENU_PATH, "o"),
            "ItemIsMenu": _variant(True, "b"),
            "ToolTip": _variant((self.icon_name, pixmaps, self.title, "Zed Launcher"), "(sa(iiay)ss)"),
        }

    # -- DBusMenu -----------------------------------------------------------
    def _on_menu_props(self, _conn, _sender, path, interface, method, params, invocation):
        self._handle_props(method, params, invocation, self._menu_props())

    def _menu_props(self) -> dict[str, Any]:
        return {
            "Version": _variant(3, "u"),
            "TextDirection": _variant("ltr", "s"),
            "Status": _variant("normal", "s"),
            "IconThemePath": _variant([], "as"),
        }

    def _menu_items(self) -> list[dict[str, Any]]:
        items = [
            {"id": OPEN_ID, "label": "Open Zed Launcher", "enabled": True, "type": "standard"},
        ]
        for index, (run_id, title) in enumerate(self._runs):
            items.append(
                {
                    "id": FIRST_GAME_ID + index,
                    "label": f"Stop {title}",
                    "enabled": True,
                    "type": "standard",
                    "run_id": run_id,
                }
            )
        if self._runs:
            items.append({"id": 3, "type": "separator"})
        items.append({"id": QUIT_ID, "label": "Quit", "enabled": True, "type": "standard"})
        return items

    def _item_props(self, item: dict[str, Any]) -> dict[str, tuple[Any, str]]:
        props: dict[str, tuple[Any, str]] = {}
        if item["type"] != "separator":
            props["label"] = (item["label"], "s")
            props["enabled"] = (item["enabled"], "b")
            props["visible"] = (True, "b")
        props["type"] = (item["type"], "s")
        return props

    def _on_menu_call(self, _conn, _sender, path, interface, method, params, invocation):

        try:
            self._handle_menu(method, params, invocation)
        except Exception:  # never leave the client hanging
            invocation.return_value(None)

    def _handle_menu(self, method, params, invocation):
        from gi.repository import GLib

        items = self._menu_items()
        by_id = {item["id"]: item for item in items}

        if method == "GetLayout":
            parent_id = params.get_child_value(0).get_int32()

            def build(item: dict[str, Any]) -> Any:
                props = {
                    key: _variant(value, signature)
                    for key, (value, signature) in self._item_props(item).items()
                }
                if "run_id" in item:
                    props["zed.run"] = _variant(item["run_id"], "s")
                return GLib.Variant("(ia{sv}av)", (item["id"], props, []))

            if parent_id == 0:
                root: Any = (
                    0,
                    {
                        "children-display": _variant("submenu", "s"),
                        "label": _variant("Zed Launcher", "s"),
                    },
                    [build(item) for item in self._menu_items()],
                )
            else:
                target = by_id.get(parent_id)
                root = (parent_id, {}, []) if target is None else (
                    target["id"],
                    {
                        key: _variant(value, signature)
                        for key, (value, signature) in self._item_props(target).items()
                    },
                    [],
                )
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self.revision, root)))
        elif method == "GetGroupProperties":
            ids = list(params.get_child_value(0).unpack())
            selected = [by_id[item_id] for item_id in ids if item_id in by_id] or items
            payload = [
                (
                    item["id"],
                    {
                        key: _variant(value, signature)
                        for key, (value, signature) in self._item_props(item).items()
                    },
                )
                for item in selected
            ]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (payload,)))
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "EventGroup":
            for entry in params.get_child_value(0).unpack():
                self._dispatch(int(entry[0]), str(entry[1]), by_id)
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "Event":
            item_id = params.get_child_value(0).get_int32()
            event_id = params.get_child_value(1).get_string()
            self._dispatch(item_id, event_id, by_id)
            invocation.return_value(None)
        elif method in ("Get", "GetAll", "Set"):
            self._handle_props(method, params, invocation, self._menu_props())
        else:
            invocation.return_value(None)

    def _dispatch(self, item_id: int, event_id: str, by_id: dict[int, dict[str, Any]]) -> None:
        if event_id != "clicked":
            return
        item = by_id.get(item_id)
        if item is None:
            return
        if item_id == OPEN_ID:
            self.on_open()
        elif item_id == QUIT_ID:
            self.on_quit()
        elif "run_id" in item:
            self.on_stop(item["run_id"])

    def _handle_props(self, method: str, params, invocation, props: dict[str, Any]):
        from gi.repository import GLib

        if method == "Get":
            name = params.get_child_value(1).get_string()
            value = props.get(name) or _variant("", "s")
            invocation.return_value(GLib.Variant("(v)", (value,)))
        elif method == "GetAll":
            invocation.return_value(GLib.Variant("(a{sv})", (dict(props),)))
        else:
            invocation.return_value(None)


class safe_call:
    """Swallow DBus failures: a missing tray must never break the app."""

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return exception_type is not None
