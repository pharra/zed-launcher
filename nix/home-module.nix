{
  self,
}:
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.programs.zed-launcher;
in
{
  options.programs.zed-launcher = {
    enable = lib.mkEnableOption "Zed Launcher";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.zed-launcher;
      defaultText = lib.literalExpression "self.packages.${pkgs.stdenv.hostPlatform.system}.zed-launcher";
      description = "The Zed Launcher package to install.";
    };

    extraPackages = lib.mkOption {
      type = lib.types.listOf lib.types.package;
      default = with pkgs; [
        mangohud
        gamemode
        gamescope
      ];
      description = "Optional runtime tools made available on PATH.";
    };

    settings = lib.mkOption {
      type = lib.types.attrs;
      default = { };
      example = {
        default_prefix = "/home/you/Games/Zed";
        default_runner = "GE-Proton";
      };
      description = ''
        Settings written to {file}`$XDG_CONFIG_HOME/zed-launcher/config.json`.
        Leave empty to let the application manage its own configuration.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ] ++ cfg.extraPackages;

    xdg.configFile = lib.mkIf (cfg.settings != { }) {
      "zed-launcher/config.json".text = builtins.toJSON cfg.settings;
    };
  };
}
