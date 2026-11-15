{
  lib,
  stdenv,
  buildNpmPackage,
  nodejs_22,
  python3,
  makeWrapper,
  wrapGAppsHook4,
  gobject-introspection,
  gtk4,
  webkitgtk_6_0,
  glib-networking,
  librsvg,
  umu-launcher,
  proton-ge-bin,
  libnotify,
  xdg-utils,
  version ? "0.1.0",
}:

let
  frontend = buildNpmPackage {
    pname = "zed-launcher-frontend";
    inherit version;
    src = ../frontend;
    npmDepsHash = "sha256-0TL+jvR5ThPd94u8jNQfGiXwshAp2wXKZd+kuQvMr9U=";
    nodejs = nodejs_22;
    npmBuildScript = "build";
    installPhase = ''
      runHook preInstall
      mkdir -p $out
      cp -r dist/. $out/
      runHook postInstall
    '';
  };
in
python3.pkgs.buildPythonApplication {
  pname = "zed-launcher";
  inherit version;
  pyproject = true;
  src = ../backend;

  build-system = [ python3.pkgs.hatchling ];

  dependencies = with python3.pkgs; [
    fastapi
    icoextract
    httpx
    platformdirs
    pygobject3
    uvicorn
    websockets
  ];

  nativeBuildInputs = [
    makeWrapper
    wrapGAppsHook4
    gobject-introspection
  ];

  buildInputs = [
    glib-networking
    gtk4
    librsvg
    webkitgtk_6_0
  ];

  preFixup = ''
    makeWrapperArgs+=(
      --set ZED_WEB_ROOT "${frontend}"
      --set ZED_PROTON_PATH "${proton-ge-bin.steamcompattool}"
      --prefix PATH : "${
        lib.makeBinPath [
          libnotify
          umu-launcher
          xdg-utils
        ]
      }"
    )
  '';

  postInstall = ''
    install -Dm644 ${../data/zed-launcher.desktop} \
      $out/share/applications/zed-launcher.desktop
    install -Dm644 ${../assets/zed-launcher.svg} \
      $out/share/icons/hicolor/scalable/apps/zed-launcher.svg
  '';

  doCheck = false;

  passthru = {
    inherit frontend;
  };

  meta = {
    description = "A lightweight game launcher for Linux, built for NixOS";
    homepage = "https://github.com/pharra/zed-launcher";
    license = lib.licenses.mit;
    mainProgram = "zed-launcher";
    platforms = lib.platforms.linux;
    maintainers = [ ];
  };
}
