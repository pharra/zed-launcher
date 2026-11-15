{
  pkgs,
}:

let
  python = pkgs.python3.withPackages (
    ps: with ps; [
      fastapi
      icoextract
      httpx
      platformdirs
      pytest
      pygobject3
      uvicorn
      websockets
    ]
  );
in
pkgs.mkShell {
  packages = [
    python
    pkgs.nodejs_22
    pkgs.umu-launcher
    pkgs.ruff
    pkgs.libnotify
    pkgs.dbus
    pkgs.gtk4
    pkgs.webkitgtk_6_0
    pkgs.glib-networking
    pkgs.gobject-introspection

    # extra tools for development
    pkgs.mangohud
    pkgs.gamemode
    pkgs.gamescope
  ];

  shellHook = ''
    export ZED_PROTON_PATH=${pkgs.proton-ge-bin.steamcompattool}
    echo "Zed Launcher development shell"
    echo "  backend: cd backend && python -m pytest"
    echo "  api:     python -m zed_launcher --serve --port 8765 --token dev"
    echo "  ui:      cd frontend && npm run dev"
  '';
}
