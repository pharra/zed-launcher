{
  pkgs,
}:

let
  python = pkgs.python3.withPackages (
    ps: with ps; [
      fastapi
      httpx
      icoextract
      platformdirs
      pytest
      pygobject3
      uvicorn
      websockets
    ]
  );
in
pkgs.runCommand "zed-launcher-backend-tests"
  {
    nativeBuildInputs = [
      python
      pkgs.dbus
    ];
  }
  ''
    cp -r ${../backend} source
    cd source
    export HOME=$(mktemp -d)
    export ZED_CONFIG_DIR=$(mktemp -d)
    export ZED_DATA_DIR=$(mktemp -d)
    export ZED_STATE_DIR=$(mktemp -d)
    export ZED_CACHE_DIR=$(mktemp -d)
    pytest -q -p no:cacheprovider
    touch $out
  ''
