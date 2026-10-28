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
runner slides, key, spring, runner stop, facade cap, key cap, latch, or a complete set. A facade depends on family and height, geared
rails depend only on family, and runner guides/slides depend only on depth.
Changing S/M/L or 1F/2F does not alter the guides or slides for a given depth.
The complete set includes printable files for all twelve groups, with separate
STLs for components that need their own print orientation. Runner exports contain
one left/right pair of guides and one left/right pair of slides. Use one pair of
each per populated runner tier, reprinting the files for additional tiers.
The key includes its drive pinion. No separate lock, lid, sustainer, screw, or divider is generated.

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

For a box or complete set, **Box base** selects **Plain** (the default) or
**Gridfinity**. Gridfinity integrates a baseplate into the closed drawer floor,
with 42 mm cells: S has three columns, M five, and L six; the number of rows
matches depth units 3–7. Two- and four-drawer L² layouts use three columns in
each S drawer. Both 1F and 2F boxes and both floor thicknesses are supported.
The grid rises 5 mm above the selected floor, and bin feet recess into its
sockets. Choose bins whose installed height fits beneath the drawer opening;
bin height is not validated by the generator. Bins, magnet holes and magnets
are not generated.

The API field is `box_variant`, accepting `plain` or `gridfinity`; older saved
configurations default to `plain`. Gridfinity boxes have separate cache and
download identities and appear in the finished assembly preview. Their STL
retains the normal breakaway runner supports. Complete-set fit receipts still
check the exact selected component builds. Gridfinity bin seating is checked
separately with nominal native feet; physical printed fit remains untested.

With Gridfinity selected, **Box floor → Floorless** opens the cell bottoms
and retains the grid webs and perimeter as physical support. The socket
profiles and height match the 0.8 mm-floor Gridfinity box. The API/CLI value
is `box_floor: 0` / `--box-floor 0`, accepted only with Gridfinity; switching
the browser back to a plain base restores the 0.8 mm floor. Floorless boxes
have their own build and cache identity and combine with either rear-wall
pattern. Regenerate the box to use this option.

```bash
python -m vault build --part box --box-variant gridfinity
python tools/check_assembly.py --definitions-only --box-variant gridfinity
python tools/check_assembly.py --case S4:1 --box-variant gridfinity
```

For a box or complete set, **Box rear wall** selects Plain, Waffle, or
Miura-ori independently of the box base and module pattern. Waffle and
Miura-ori use two-perimeter corrugation with fixed 14 mm pitch and 1.3 mm
facets for two 0.65 mm extrusion lines. Floor, corner and top bands remain
solid. The API field is `box_rear_pattern` (`plain`, `waffle`, or `miura`);
older requests and cached boxes default to `plain`. Patterned rear walls
have separate build identities and are matched in assembly previews and
fit receipts. The CLI option is `--box-rear-pattern`. Regenerate the box
to include the chosen rear wall, the lower rail arches and denser support teeth.

For a module or complete set, **Module wall pattern** selects Plain, Waffle,
or Miura-ori. Patterned variants also select **Recessed** or **Two-perimeter
corrugated** construction, pitch, maximum recess depth, extrusion line width,
and either all four long sleeve faces or just the left/right sides. Defaults are
Recessed, all four faces, 14 mm pitch, 1.7 mm depth, and 0.65 mm line width for a
0.6 mm nozzle. Recessed valleys retain a 1.3 mm minimum web for two nominal lines;
crests are thicker and original inner surfaces remain. Corrugated construction
relieves both sides of the nonmating panels, targeting 1.3 mm normal facet
thickness throughout their thin areas. Fold junctions and transitions can be
thicker. Both choices stay within the existing 3 mm wall. Front lips, stopper
regions, connector roots and other mechanical lands remain full thickness with
tapered transitions. Miura-ori is a rigid crease relief, not a folding mechanism;
its corrugated fold height is reduced as needed to fit the normal thickness within
the selected maximum recess envelope. Inspect the slicer's actual perimeter paths
before printing; full-thickness lands intentionally need more than two lines.

Pitch accepts 8–40 mm, depth 0.2–2 mm, and line width 0.6–1 mm. Depth plus two line
widths must fit within the 3 mm wall. A pattern must also fit the protected panels;
the geometry builder rejects a selection that leaves no complete pattern.
Pattern settings affect only module geometry. Plain retains its existing identity;
patterned modules record all settings and use distinct build aliases, including
custom parameter values. Matching assembly previews and fit receipts retain the
selected pattern and exact module build. Two- and four-drawer L² sets share a
module only when their wall settings also agree. The separate CAD viewer's fixed
catalog stays unchanged; use this configurator or the CLI for patterned variants.

Changing the selection previews the newest matching cached part, or shows
“not generated yet.” Complete sets show the matching finished parts together in an assembled view,
with an explosion slider, component colors, visibility controls and click-to-highlight.
Fit view centers the visible components; endpoint buttons fit their pose, while
dragging the explosion slider preserves the camera.
Missing groups and legacy builds that need new assembly assets are listed explicitly. Recent builds can still be inspected independently.

Choose **Two S drawers** with family L for an L² module. Both drawers have the
selected depth and height: L6² 2F contains two S6 2F drawers side by side.
The module keeps the 329.6 mm L width. Boxes, facades and geared rails resolve
to the matching S parts. With an L 2F module, **Four S drawers** selects a
2 × 2 arrangement of S1F drawers. Both layouts use the same open L² 2F module
and shadow-gap pattern for four S1F facades, sharing its build and STL/STEP downloads
for the same depth and rear thickness. The layout changes drawer parts,
quantities and placement. Module-only previews and downloads therefore stay
the same when switching between two and four drawers. Other families offer
one drawer. Each complete-set ZIP
includes `PRINTING.txt` and `print-plan.json`, identifying the immutable build
and number of copies of each printable file; repeated parts share the same STL.

Assembly previews use explicit native-coordinate transforms from
`src/vault/assembly.py`. A single-drawer scene has 9 instances for 1F and 13 for
2F; L² has 17 and 25 respectively, with a left/right runner pair on each tier
of each bay. Four S1F drawers have 33 instances. The drawer group moves forward as a unit
while the explosion separates its facade, rails and slides. Exploded positions
illustrate the parts; they do not certify a disassembly path. Key, spring, latch, runner stops, caps and screws are omitted and identified in the scene.
The six accessory groups are included in complete-set downloads but are not
positioned in the drawer preview or covered by its assembly fit receipt.
Accessory build IDs are recorded separately from the checked drawer build IDs.

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
python tools/check_assembly.py --case L6x2:2 --case L3x2:1:3:2
python tools/check_assembly.py --case L6x2x2:2
python tools/check_assembly.py --case S4:1 --wall-pattern waffle
python tools/check_assembly.py --case S4:1 --wall-pattern miura
python tools/check_assembly.py --case S4:1 --wall-pattern miura --pattern-construction corrugated
python tools/check_assembly.py --all  # all 180 native assemblies; expensive
```

Recorded evidence in [`research/assembly_fit.json`](../research/assembly_fit.json)
covers all 120 definitions, four representative native assemblies, and a separate
S4 check of imported finished STEP exports: 264 component-pair checks and 72
mating checks passed with zero intersection volume. This sample is not an
exhaustive native audit of all 120 configurations; complete-set generation checks
the exact configuration and cached component builds requested.

[`research/unified_module_assembly.json`](../research/unified_module_assembly.json)
records the two-drawer L6² 2F audit from current native construction and the
four-drawer audit from exact checksummed finished STEP exports, with component
build IDs recorded. Both use the shared open module, default 0.8 mm box floor
and 0.9 mm module rear. These are representative
configurations; every generated complete set checks its exact finished STEP
files before receiving a passing receipt. Two- and four-drawer sets retain
separate fit receipts even when they share the module build. The four-drawer
scene has 33 placed solids, 528 component pairs and 48 mating checks.

Earlier reports remain in
[`research/multi_drawer_assembly.json`](../research/multi_drawer_assembly.json)
and [`research/four_drawer_assembly.json`](../research/four_drawer_assembly.json),
tied to their original construction hashes. Use the commands above to audit
the current checkout. These audits exclude catch/latch operation, accessory
installation and loaded or printed behavior.

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

## Gridfinity containers

Open **Gridfinity** at `/gridfinity` to design removable containers for a drawer
with the Gridfinity box base. This editor selects its drawer size independently
of the Parts tab: S has 3 columns, M 5 and L 6, with one 42 mm row per depth unit
(3–7). Choose 1F or 2F; for L² modules, select the individual S drawer size.

The layout starts filled. **Paint cells** toggles squares by click, touch or drag;
edge-connected squares share one floor and cavity. Separate painted regions
become separate printable containers. **Dividers** paints internal lines between
selected cells, creating fixed separators inside a container. **Erase** removes
cells or dividers; removing a cell also removes its unsupported dividers.
**Fill drawer**, **Clear layout**, **Clear dividers** and **Undo** support quick
experiments. Keyboard users can focus cells or dividers and press Space or Enter;
arrow keys move between cells. A full layout expands with the drawer size; a
partial layout keeps cells inside the resized grid. Undo restores clipped cells.

Full drawer means all whole Gridfinity cells, leaving the drawer's existing
peripheral margins. Plain and Miura-ori apply to both sides and separators. The
perimeter choice targets one 0.65 mm extrusion line or two lines (1.30 mm) for a
0.6 mm nozzle. Straight painted divider runs merge into continuous walls. Miura
folds blend into thin webs at actual connections, without thick pads at ordinary
grid boundaries or interruptions opposite dividers that do not reach a wall.
Container heights are 28 mm for 1F and 77 mm for 2F, including the
feet. There is no stacking lip or magnet pocket. Inspect slicer paths and compare
printed samples for fit and stiffness before producing a full drawer.

Generation uses the same persistent job queue, revision checks, immutable build
storage, checked downloads and bounded same-origin JSON submission as Parts and
Labels. Drafts and the current job survive reloads. Generated 3D previews use a
container selector; viewing a saved build leaves the drawing unchanged. Each
container downloads separately as base-down STL and STEP, or together in a ZIP
with the configuration recording its original grid placement. The layout is a
schematic; generate to inspect the actual feet and wall facets.

The request uses `part: "gridfinity_bins"`, `family`, `depth_units`,
`height_units`, `cells: [[x,y], ...]`, `dividers: [{"axis":"x","x":1,"y":0}, ...]`,
`wall_pattern: "plain" | "miura"`, and `wall_perimeters: 1 | 2`. Coordinates start
at the rear-left cell. An `x` divider is vertical at grid line x along cell row y;
a `y` divider is horizontal at line y along column x. Both adjacent cells must
be selected. Omitting cells selects the full grid; an explicit empty drawing is
rejected. The server rejects unknown fields, duplicates and out-of-grid values.

```bash
source .local-env
python -m vault.bin_build --configuration containers.json
python tools/check_gridfinity_bins.py
```

### Drawer-fit boxes

Choose **Drawer-fit box** on the same page to create removable organizers for a
plain Vault drawer. Planning cells stretch over its usable cavity: S has three
columns, M four and L six, with one row per selected depth unit. For example,
S4 has a 3 × 4 drawing and M5 has a 4 × 5 drawing. Cells display their actual
proportions; the drawing keeps the same full/partial footprints, dividers and undo.
The front lock space remains clear.

Select the existing drawer's **0.8 mm** or **3 mm** floor. This sets the container
height to leave 1 mm below the drawer rim. These boxes have a 1.2 mm flat floor,
a relieved lower edge for the drawer's floor fillet, and 0.25 mm nominal clearance
at their perimeter and beneath their base. They fit the plain drawer rather than
the Gridfinity socket base.

**Apply balanced design** selects two-perimeter Miura walls with thin blended
connections. The folds add depth to the wall section while the flat, supported
floor and absence of feet limit base material and layers. One-perimeter Miura and
plain walls remain available for comparison. Generated results show measured CAD
material volume, clear compartment height and wall/base thickness. Print time
depends on the slicer profile; loaded strength and printed fit need physical tests.

Requests retain `part: "gridfinity_bins"` and add `container_type: "drawer"` and
`drawer_floor: 0.8 | 3`. Existing drawings that omit the type retain Gridfinity
behavior and their configuration identities. Floor and wall choices, recovery,
history and checksummed downloads use the existing shared queue.

```bash
python -m vault.bin_build --configuration drawer-boxes.json
python tools/check_drawer_bins.py --build out/builds/<build-id>
```

## Universal accessories

Key, spring, latch, runner stop, facade cap and key cap fit all offered size selections;
changing family, depth or height does not change their cache identity. The key
is a single piece with an integrated drive pinion. Print one per drawer. Print
one spring, two runner stops per populated tier, a cap for each facade screw
counterbore, and one key cap if desired. Each choice exports checked STL and
STEP through immutable build storage. Complete sets contain twelve build groups
and fifteen STL files; quantities reuse the same files.

The latch retreats its entire planar outline by 0.10 mm and reduces its
4.5 mm thickness by 0.15 mm, easing the fit without scaling attachment spacing.
Its rounded through-opening extends the finger aperture along the central
tongue, following its perimeter to remove material. A larger straight aperture
with a small lower chamfer replaces the deep double countersink, and the upper
edges are rounded. The vertical profiles of the flexible arms, slots, snap
hooks and detents are retained, along with the chamfered V seat. The bed face
stays flat and the print height remains 4.35 mm.
Print it flat and test insertion, retention and restoring force before making
more. Removed CAD volume does not predict filament or print-time savings:
the extra opening perimeter can offset reduced infill, so compare the same
slicer profile. The spring now uses nominal dimensions with no added fit relief: the
clearance request applies to the latch. Earlier spring builds remain immutable.
Caps print closed-face down; runner stops print flange down.

The universal accessories appear below the main size-dependent parts under
**Common components**, separated by a light rule.

The accessories regularize small source blends. Cap seated-pose collision checks
and sampled source comparisons are recorded in `research/accessories.json`;
run `python tools/check_accessories.py` to audit the current checkout. The latch's
enlarged opening intentionally differs from the purchased reference; historical
source agreement does not apply to that opening. These diagnostics do not certify
spring, latch or stop installation, insertion motion, retention, or printed fit.
