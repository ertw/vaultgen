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

## Labels

Open **Labels** from the generator header and choose the facade family. Labels
extend along the wider facade recess while retaining their rounded end and
19.4 mm height × 2 mm thickness:

| Facade | Label length |
| --- | --- |
| S | 47 mm |
| M | 91.6 mm |
| L | 129.4 mm |

The same label size suits 1F and 2F facades; drawer depth does not affect it.
Changing size updates the live preview and available text area without stretching
the lettering. Previous designs without a size selection remain S labels.
Labels are independent jobs and are not included in a complete drawer set.
Choose one or two lines, each with its own size and color, plus a
background color. Two or three distinct colors are supported. The single font,
DejaVu Sans Bold, is bundled locally as vector outlines; neither the editor nor
the CAD constructor depends on installed browser or server fonts.

The live face preview uses the same glyph curves, spacing, and millimeter layout
as the native CAD constructor. A section view explains the optional hollow back.
It is an artwork preview rather than a running CAD kernel. **Generate label**
creates checked native solids and enables an interactive 3D preview of the
actual exported color components. Text that does not fit is rejected rather
than clipped or silently scaled. Each line allows up to 96 characters, subject
to the selected label's physical text area. Editing the artwork does not alter previously
generated files.

Print the supplied orientation with the lettering against the build plate.
The text is a flush 0.6 mm inlay, backed by the label face; a hollow label keeps
its perimeter rim. The 3MF preserves a single assembly containing named color
parts. Assign the corresponding filaments in your slicer: display colors do not
automatically select a printer's extruders. The ZIP also contains STL and STEP
files per color, the combined STEP, configuration, and print instructions.
Import the color STLs together as parts of one object and preserve their shared
coordinates; do not independently center or arrange them. A single-color STL
cannot preserve the label's material assignments.

Labels use a nominal envelope suited to the facade's label recess and require
adhesive attachment. They do not reproduce purchased label geometry or promise
a snap fit. CAD validity and clearance checks do not establish printed fit;
check the first label on your intended facade, printer, and material.

## Generator builds

Box floor thickness defaults to the current 0.8 mm, with the original 3 mm
floor available. Module rear thickness defaults to 0.9 mm, with the original
2 mm rear available. These thicknesses were checked against the supplied S4
STLs. Each variant has its own resolved parameters and build alias; external
dimensions remain fixed.

Changing the selection previews the newest matching cached part, or shows
“not generated yet.” Complete sets show the matching finished parts together in an assembled view,
with an explosion slider, component colors, visibility controls and click-to-highlight.
Fit view centers the visible components; endpoint buttons fit their pose, while
dragging the explosion slider preserves the camera.
Missing groups and legacy builds that need new assembly assets are listed explicitly. Recent builds can still be inspected independently.

Assembly previews use explicit native-coordinate transforms from
`src/vault/assembly.py`. The scene has 9 instances for 1F and 13 for 2F, with one
left/right runner pair on each tier. The drawer group moves forward as a unit
while the explosion separates its facade, rails and slides. Exploded positions
illustrate the parts; they do not certify a disassembly path. Lock/pinion, screws
and separate runner stoppers are omitted and identified in the scene.

New builds include finished assembly STL and STEP assets under `preview/assembly/`.
These omit module support webs and box runner sheets. Printable exports retain
those supports. The manifest identifies component roles, native coordinates and
print-to-native transforms. Legacy caches remain downloadable but require
regeneration for assembled viewing; no placement is guessed from print bounds.
Preview assets are excluded from printable ZIP bundles.

After generating a complete set, the worker imports its exact finished STEP
assets and checks topology, rigid transforms, mating registrations and pairwise
intersections using `src/vault/assembly_validation.py`. Intentional seating and
stop contacts are allowed; positive-volume collisions above numerical tolerance
fail. A fit-check receipt pins the result to the selected configuration and
immutable component build IDs, assembly definition and validator revision. Failed checks preserve individual exports and
mark the job failed. The scene warns when its cache combination has no passing
receipt. These checks verify the closed assembled pose, not printed fit or motion.

Assembly audits can also be run independently:

```bash
python tools/check_assembly.py --definitions-only
python tools/check_assembly.py --case S4:1 --case L7:2:3:2
python tools/check_assembly.py --all  # all 120 native assemblies; expensive
```

Recorded evidence in [`research/assembly_fit.json`](../research/assembly_fit.json)
covers all 120 definitions, four representative native assemblies, and a separate
S4 check of imported finished STEP exports: 264 component-pair checks and 72
mating checks passed with zero intersection volume. This sample is not an
exhaustive native audit of all 120 configurations; complete-set generation checks
the exact configuration and cached component builds requested.

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
