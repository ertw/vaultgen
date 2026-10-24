# Vault generator

`vaultgen.erik.cl` is a dedicated configurator using the same native constructors,
STEP round-trip validation, print orientation, mesh checks and immutable build
storage as the CAD CLI. It does not read purchased STL files to generate parts.
The existing cad.erik.cl catalog remains available separately.

The selector supports S/M/L widths, depth units 3 through 7 (146.1–314.1 mm),
and heights 1F/2F (47/95 mm outside skins, excluding connectors). L×2F is the
largest family/height offered. These are nominal dimensions; the downloads show
each part's actual print bounding box. XL and 4F are unavailable in both the web
controls and the server validation. The original lower-level module constructor
retains its broader research capabilities for compatibility.

Choose an individual module, box, facade, rail pair, or a complete set. A facade
depends on family and height, and rails depend only on family. The complete set
contains one of each selected part, with separate plain/retained rail STL files.
No pinion, lock, lid, sustainer, screw, or divider is generated.

Generation runs in a separate Python process. One job runs at a time, up to four
jobs can be running/queued, duplicate active requests reuse the same job, and
completed parts with unchanged source are reused. Jobs survive browser reloads;
a service restart marks interrupted jobs as failed. Generate again to reuse any
parts already completed. The build log is bounded and jobs time out after one
hour. Failed generation preserves all earlier successful builds and downloads.

STL files use the intended print orientation. STEP is available both in original
model coordinates and per-part print coordinates. Every downloadable artifact
is checked against its immutable build checksum. ZIP downloads include the
configuration, part metadata and the selected set's STL/STEP files. They exclude
source snapshots and original purchased files.

The server uses only the Python standard library beyond the existing CAD
environment. Browser code is local, without CDN dependencies. Nginx provides
the host's established HTTPS/OAuth gate; the application binds only to loopback.
Build submission requires a same-origin JSON request. No shell commands,
filesystem paths, arbitrary Python, or CAD source can be submitted through the
interface.

Solid and export checks establish model validity, not physical print fit. The
S4/1F reconstruction remains the template; larger parts use measured envelope,
runner and attachment datums with shared native features. Preserve the existing
print notes, remove sacrificial runner supports, and check the first printed set
on the intended printer before producing multiples.

Validation:

```bash
source .local-env  # this checkout's prepared runtime; alternatively nix develop
python -m unittest discover -s tests -v
python -m vault.web --port 3941
```

Runtime data lives under `out/web/`; successful artifacts remain under
`out/builds/`. Both are ignored by Git. Deployment is documented in
[`deploy/README.md`](../deploy/README.md).
