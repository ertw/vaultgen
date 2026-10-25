# Vault / vaultgen

- This repository owns Vault geometry, exports, and the `vaultgen.erik.cl`
  configurator. Shared build storage and the separate CAD viewer live in
  `../../cad-tooling/`. Read `README.md`, `docs/generator.md`, and
  `docs/generator-geometry.md` for the relevant behavior; deployment and browser
  check commands are in `deploy/README.md`.
- Run commands from this repository root. Use `nix develop path:.`; install
  locked dependencies explicitly with `just setup` when needed. Do not install
  dependencies during shell or service startup. This checkout also has a
  prepared runtime available through `source .local-env`.
- Construct geometry with native build123d features. Purchased files under
  `original_files/` and measured profiles are reference/comparison inputs, never
  constructor inputs or downloadable assets. Keep purchased files local and
  excluded from Git.
- Dimensions are millimeters; model X is width, Y runs from the closed back
  toward the opening, and Z is height. Change shared dimensions and placements
  rather than stretching mating profiles. Preserve intentional handedness,
  clearances, print orientation, and removable supports unless the task changes
  them. CAD validity and sampled source agreement do not establish printed fit.
- The generator supports S/M/L, depths 3–7, and heights 1F/2F. Keep browser
  choices and server validation consistent. Broader lower-level research APIs
  do not imply that a size is supported by the generator.
- Completed builds in `out/builds/` are immutable. Never edit published
  artifacts, checksums, provenance, or fit receipts, or advance latest pointers
  after a failed build. Rebuild changed geometry through the normal export
  pipeline, retaining solid, STEP round-trip, and watertight print-mesh checks.
  `partcad.json` and `cad-builds.json` define catalog membership, not files in
  `out/`. Preserve existing build history and runtime jobs in `out/web/`.
- Assembly placement comes from `src/vault/assembly.py` and recorded component
  transforms, not guessed print bounds. Finished assembly previews omit
  sacrificial supports; printable exports retain them. Keep preview assets out
  of print ZIPs, and preserve checksummed downloads and fit receipts tied to the
  exact component builds. Do not bypass revision/dirty-checkout cache checks.
- For code changes, run relevant tests in the prepared environment; use
  `python -m unittest discover -s tests -v` for the full suite. Geometry/export
  changes also need a fresh affected build and relevant interface checks.
  Assembly changes need `python tools/check_assembly.py --definitions-only`
  plus affected native `--case` checks; `--all` is intentionally expensive.
  The historical module `validate` comparison is specific to S4/1F and retains
  reflected mouth registration; it is not a universal acceptance test. Use the
  part/interface checkers documented in the README and report their limits.
- For frontend changes, run the relevant Playwright checks using the
  `cad-tooling` environment and its virtualenv Python as shown in
  `deploy/README.md`. `tools/browser_configurator.py` and
  `tools/browser_assembly.py` use fixtures without a server;
  `tools/browser_check.py` and `tools/browser_failures.py` target a running
  server, and the latter needs at least two saved successful builds. These
  checks do not submit real CAD jobs. Inspect desktop/mobile results for layout
  changes. Keep browser assets local, without CDN dependencies.
- HTML/CSS/JS changes take effect on browser refresh. Loaded server Python
  changes require a service restart; geometry changes require new builds.
  Documentation-only changes require neither a restart nor CAD tests.
- As `ertw`, run `systemctl restart vaultgen.service` without root or `sudo`;
  the host's polkit rule permits it. This is a system service, so omit `--user`.
  First inspect `http://127.0.0.1:3941/api/jobs` and wait for queued/running jobs
  to finish: a restart interrupts them and marks them failed. After restarting,
  check `systemctl status vaultgen.service --no-pager` and
  `curl --fail http://127.0.0.1:3941/healthz`; use
  `journalctl -u vaultgen.service -n 100 --no-pager` for failures.
- Bind development servers to `127.0.0.1` and use another port if 3941 is
  occupied. Use a separate `--output` directory for a second server so it does
  not share the live job state. Keep NixOS, nginx, and authentication changes
  outside routine application edits; preserve the HTTPS/OAuth gate and
  same-origin JSON build submission checks.
