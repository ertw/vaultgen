{
  description = "Editable Vault CAD models (project-local, x86_64-linux)";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/02e08985a27c65ffd33d434eeb2e660a2e4dc84d";
  outputs = { self, nixpkgs }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
  in {
    devShells.${system}.default = pkgs.mkShell {
      packages = with pkgs; [ python312 uv just ];
      LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
        pkgs.stdenv.cc.cc.lib pkgs.zlib pkgs.expat pkgs.libGL
        pkgs.libx11 pkgs.libxext pkgs.libxrender pkgs.libice pkgs.libsm
      ];
      UV_PYTHON_DOWNLOADS = "never";
      UV_NO_MANAGED_PYTHON = "1";
      UV_CACHE_DIR = "./.cache/uv";
      PYTHONPATH = "./src";
      PYTHONDONTWRITEBYTECODE = "1";
      MPLCONFIGDIR = "./.cache/matplotlib";
      shellHook = ''
        export PATH="$PWD/.venv/bin:$PATH"
        echo "Vault CAD: just setup, just build, just validate."
      '';
    };
  };
}
