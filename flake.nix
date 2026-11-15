{
  description = "Zed Launcher — a NixOS-first game launcher";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    {
      self,
      nixpkgs,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
      pkgsFor = system: import nixpkgs { inherit system; };
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = pkgs.callPackage ./nix/package.nix { };
          zed-launcher = self.packages.${system}.default;
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/zed-launcher";
          meta.description = "Zed Launcher";
        };
      });

      devShells = forAllSystems (system: {
        default = import ./nix/devshell.nix { pkgs = pkgsFor system; };
      });

      checks = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          package = self.packages.${system}.default;
          backend = import ./nix/check.nix { inherit pkgs; };
        }
      );

      formatter = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        pkgs.writeShellApplication {
          name = "nix-fmt";
          runtimeInputs = [
            pkgs.findutils
            pkgs.git
            pkgs.nixfmt
          ];
          text = ''
            files=()
            for arg in "$@"; do
              case "$arg" in
                *.nix) files+=("$arg") ;;
              esac
            done
            if [ "''${#files[@]}" -eq 0 ]; then
              if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
                mapfile -t files < <(git ls-files '*.nix')
              else
                mapfile -t files < <(find . -name '*.nix' -not -path './.git/*')
              fi
            fi
            exec nixfmt "''${files[@]}"
          '';
        }
      );

      overlays.default = import ./nix/overlay.nix;

      nixosModules.default = import ./nix/module.nix { inherit self; };
      homeManagerModules.default = import ./nix/home-module.nix { inherit self; };
    };
}
