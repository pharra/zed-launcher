from __future__ import annotations

from zed_launcher.services.gameenv import game_env

PARENT = {
    "DISPLAY": ":0",
    "WAYLAND_DISPLAY": "wayland-1",
    "XDG_RUNTIME_DIR": "/run/user/1000",
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
    "HOME": "/home/wf",
    "LANG": "zh_CN.UTF-8",
    "LC_TIME": "en_US.UTF-8",
    "PULSE_SERVER": "unix:/run/pulse",
    "DXVK_HUD": "fps",
    "PATH": "/nix/store/devshell/bin:/run/current-system/sw/bin",
}


def test_session_variables_are_kept() -> None:
    env = game_env(parent=PARENT)
    assert env["DISPLAY"] == ":0"
    assert env["WAYLAND_DISPLAY"] == "wayland-1"
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"
    assert env["DBUS_SESSION_BUS_ADDRESS"].startswith("unix:path=")
    assert env["LANG"] == "zh_CN.UTF-8"
    assert env["LC_TIME"] == "en_US.UTF-8"
    assert env["PULSE_SERVER"] == "unix:/run/pulse"
    assert env["DXVK_HUD"] == "fps"


def test_launcher_environment_is_not_forwarded() -> None:
    parent = {
        **PARENT,
        "LD_LIBRARY_PATH": "/nix/store/dbusmenu/lib",
        "LD_PRELOAD": "/nix/store/x/libx.so",
        "GI_TYPELIB_PATH": "/nix/store/gtk/lib/girepository",
        "GDK_PIXBUF_MODULE_FILE": "/nix/store/librsvg/loaders.cache",
        "QT_PLUGIN_PATH": "/nix/store/fcitx/lib/qt-6/plugins",
        "GTK_PATH": "/home/wf/.local/share/flatpak/exports/lib/gtk-4.0",
        "PYTHONNOUSERSITE": "true",
        "VSCODE_INJECTION": "1",
        "COPILOT_DEBUG_NONCE": "abc",
        "ZED_WEB_ROOT": "/nix/store/web",
        "ZED_PROTON_PATH": "/nix/store/proton",
        "NIX_LD": "/run/current-system/sw/share/nix-ld/lib/ld.so",
        "RUST_LOG": "deniald=info",
        "PAGER": "less",
        "PROTON_LOG": "1",
        "STEAM_COMPAT_DATA_PATH": "/stale",
        "UMU_LOG": "1",
    }
    env = game_env(parent=parent)
    for dropped in (
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "GI_TYPELIB_PATH",
        "GDK_PIXBUF_MODULE_FILE",
        "QT_PLUGIN_PATH",
        "GTK_PATH",
        "PYTHONNOUSERSITE",
        "VSCODE_INJECTION",
        "COPILOT_DEBUG_NONCE",
        "ZED_WEB_ROOT",
        "ZED_PROTON_PATH",
        "NIX_LD",
        "RUST_LOG",
        "PAGER",
        "PROTON_LOG",
        "STEAM_COMPAT_DATA_PATH",
        "UMU_LOG",
    ):
        assert dropped not in env, dropped


def test_host_directories_come_first_on_path() -> None:
    env = game_env(parent=PARENT)
    parts = env["PATH"].split(":")
    assert parts[0] in {"/usr/local/bin", "/usr/bin", "/bin", "/run/current-system/sw/bin"}
    if "/nix/store/devshell/bin" in parts:
        assert parts.index("/nix/store/devshell/bin") > 0


def test_overrides_win_and_are_stringified() -> None:
    env = game_env({"WINEPREFIX": "/prefix", "GAMEID": "umu-1", "DXVK_HUD": "0"}, parent=PARENT)
    assert env["WINEPREFIX"] == "/prefix"
    assert env["GAMEID"] == "umu-1"
    assert env["DXVK_HUD"] == "0"
