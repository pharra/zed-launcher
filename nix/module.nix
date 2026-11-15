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
  cfg = config.services.zed-launcher;
in
{
  options.services.zed-launcher = {
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
      description = ''
        Optional runtime tools made available on PATH. These are picked up by
        Zed Launcher when the matching toggles are enabled per game.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ] ++ cfg.extraPackages;

    warnings = lib.optional (!config.programs.steam.enable) ''
      services.zed-launcher: umu-launcher expects a Steam runtime. Enable
      `programs.steam.enable = true` for 32-bit graphics drivers and the FHS
      environment used by Proton.
    '';
  };
}
