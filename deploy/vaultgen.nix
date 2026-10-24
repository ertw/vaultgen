{ lib, pkgs, ... }:
let
  project = "/home/ertw/src/cad/projects/vault";
  tooling = "/home/ertw/src/cad/cad-tooling";
in
{
  # The pinned virtualenv is prepared explicitly, never at service startup.
  systemd.services.vaultgen = {
    description = "Vault parametric CAD generator";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];
    unitConfig.RequiresMountsFor = [ project tooling ];
    path = [ pkgs.python312 pkgs.git ];
    environment = {
      PYTHONPATH = "${project}/src:${tooling}/src";
      PYTHONDONTWRITEBYTECODE = "1";
      PYTHONUNBUFFERED = "1";
      MPLCONFIGDIR = "${project}/.cache/matplotlib";
      LD_LIBRARY_PATH = lib.makeLibraryPath [
        pkgs.stdenv.cc.cc.lib
        pkgs.zlib
        pkgs.expat
        pkgs.libGL
        pkgs.libx11
        pkgs.libxext
        pkgs.libxrender
        pkgs.libice
        pkgs.libsm
      ];
    };
    serviceConfig = {
      User = "ertw";
      Group = "users";
      WorkingDirectory = project;
      ExecStart = "${project}/.venv/bin/python -m vault.web --host 127.0.0.1 --port 3941";
      Restart = "on-failure";
      RestartSec = 5;
      TimeoutStopSec = 30;
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectSystem = "strict";
      ProtectHome = "read-only";
      ReadWritePaths = [ "${project}/out" "${project}/.cache" ];
      ProtectKernelTunables = true;
      ProtectKernelModules = true;
      ProtectControlGroups = true;
      RestrictSUIDSGID = true;
      CapabilityBoundingSet = "";
      RestrictAddressFamilies = [ "AF_INET" "AF_INET6" "AF_UNIX" "AF_NETLINK" ];
      UMask = "0027";
    };
  };
}
