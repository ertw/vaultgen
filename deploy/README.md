# vaultgen.erik.cl deployment

Vaultgen runs the repository's prepared Python environment as `ertw`, bound to
`127.0.0.1:3941`. Nginx supplies HTTPS with the host's existing wildcard certificate
and the same OAuth gate as `cad.erik.cl`. API authentication failures return 401
so an expired login is not mistaken for a successful build submission.

The NixOS source is `/home/ertw/src/nixos-config`. `nixos.patch` adds the service
import and authenticated virtual host; `vaultgen.nix` defines the service. Review
the patch against local changes before applying it:

```bash
cd /home/ertw/src/cad/projects/vault
mkdir -p out .cache/matplotlib
nix develop path:. -c just setup  # only needed for a fresh/changed virtualenv
git -C /home/ertw/src/nixos-config apply --check "$PWD/deploy/nixos.patch"
git -C /home/ertw/src/nixos-config apply "$PWD/deploy/nixos.patch"
cp deploy/vaultgen.nix /home/ertw/src/nixos-config/hosts/nixos01/modules/services/vaultgen.nix
sudo nixos-rebuild switch --flake path:/home/ertw/src/nixos-config#nixos01
```

Using `path:` includes the new service file without staging or committing unrelated
configuration changes. Keep any existing changes in the NixOS repository. The
service writes only to `out/` and `.cache/`; source files and the shared tooling
remain read-only. Build jobs use immutable `cad_build` storage. Restarting the
service interrupts active jobs, so wait for builds to finish before deploying
Python changes. Static frontend changes are loaded on browser refresh.

```bash
systemctl status vaultgen.service --no-pager
curl --fail http://127.0.0.1:3941/api/config
curl -I https://vaultgen.erik.cl/
curl -i https://vaultgen.erik.cl/api/config
journalctl -u vaultgen.service -n 100 --no-pager
```

An unauthenticated HTTPS page request should redirect to `login.erik.cl`; an
unauthenticated API request should return 401. Sign in normally to use the app.
No separate firewall opening is needed for port 3941. The hostname uses the
existing `*.erik.cl` certificate and must resolve to this reverse proxy.

For a local development session:

```bash
cd /home/ertw/src/cad/projects/vault
nix develop path:. -c python -m vault.web --host 127.0.0.1 --port 3941
```

The CAD tooling environment at `/home/ertw/src/cad/cad-tooling` includes Playwright
and Chromium for browser validation. The application itself has no CDN or browser
package dependency.

## Browser checks

With the local server running, use the shared tooling environment's browser
dependencies. Neither check submits real CAD builds:

```bash
cd /home/ertw/src/cad/projects/vault
nix develop path:/home/ertw/src/cad/cad-tooling -c \
  /home/ertw/src/cad/cad-tooling/.venv/bin/python tools/browser_check.py
nix develop path:/home/ertw/src/cad/cad-tooling -c \
  /home/ertw/src/cad/cad-tooling/.venv/bin/python tools/browser_failures.py
```

`browser_check.py` reads the real configuration and saved artifacts, checks size
controls, preview/configuration separation, STL rendering and mobile overflow,
and saves desktop/mobile screenshots in `out/web-review/`. It suppresses unrelated
live job notifications in its own browser context. Without saved builds it checks
the empty configurator; create a successful build first to exercise the real STL
preview.

`browser_failures.py` requires at least two successful saved builds. It intercepts
job requests only within its own browser context and checks delayed submission,
duplicate-submit prevention, progress, history navigation during a build, result
and ZIP access, reload recovery, partial failure and failed preview loading. The
fixture's ZIP link is checked for availability; it is not a real archive download.

Both accept `--base-url http://127.0.0.1:PORT` and `--chromium /path/to/chromium`.
The screenshot check also accepts `--output PATH`. Run browser checks with access
to local sockets; restricted execution sandboxes may prevent Chromium startup.
