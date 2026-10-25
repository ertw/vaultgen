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

Choose an individual module, box, facade, geared rail pair, runner guides,
runner slides, or a complete set. A facade depends on family and height, geared
rails depend only on family, and runner guides/slides depend only on depth.
Changing S/M/L or 1F/2F does not alter the guides or slides for a given depth.
The complete set includes printable files for all six groups, with separate
STLs for components that need their own print orientation. Runner exports contain
one left/right pair of guides and one left/right pair of slides. Use one pair of
each per populated runner tier, reprinting the files for additional tiers.
No pinion, lock, lid, sustainer, screw, or divider is generated.

Box floor thickness defaults to the current 0.8 mm, with the original 3 mm
floor available. Module rear thickness defaults to 0.9 mm, with the original
2 mm rear available. These thicknesses were checked against the supplied S4
STLs. Each variant has its own resolved parameters and build alias; external
dimensions remain fixed.

Changing the selection previews the newest matching cached part, or shows
“not generated yet.” Complete sets show available matching parts and list any
missing groups. Recent builds can still be inspected independently.

Repository status refreshes every 15 seconds. Text, a symbol and green/amber
color distinguish a clean repository from uncommitted changes or unavailable
revision information. Cached parts warn when their commit differs from HEAD,
when either checkout was dirty, or when provenance is unknown. This is a
conservative revision check, not a claim that a particular edit affects a part.
Generate rebuilds rather than reusing caches while the repository is dirty.

Generation runs in a separate Python process. One job runs at a time, up to four
jobs can be running/queued, duplicate active requests reuse the same job, and
completed parts are reused only when source and clean Git revision match. Jobs survive browser reloads;
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
