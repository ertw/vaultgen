# Vault generator

`vaultgen.erik.cl` is a dedicated configurator using the same native constructors,
STEP round-trip validation, print orientation, mesh checks and immutable build
storage as the CAD CLI. It does not read purchased STL files to generate parts.
The existing cad.erik.cl catalog remains available separately.

The selector supports S/M/L widths, depth units 3 through 7 (146.1–314.1 mm),
and heights 1F/2F/4F (47/95/191 mm outside skins, excluding connectors). L×4F is
the largest family/height offered. These are nominal dimensions; the downloads show
each part's actual print bounding box. XL and other heights are unavailable in the web
controls and the server validation. The original lower-level module constructor
retains its broader research capabilities for compatibility.

Choose an individual module, box, facade, geared rail pair, runner guides,
runner slides, key, spring, runner stop, facade cap, key cap, latch, or a complete set. A facade depends on family and height, geared
rails depend only on family, and runner guides/slides depend only on depth.
Changing S/M/L or 1F/2F/4F does not alter the guides or slides for a given depth.
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

The same label size suits 1F, 2F and 4F facades; drawer depth does not affect it.
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

**Minimum floor** offers **0.8 mm** or **Default** for boxes, facades, and
complete sets. The thin choice selects the 0.8 mm box floor and a shelled
facade with a 0.8 mm front skin; Default restores the 3 mm box floor and the
original facade pockets. The browser starts with the thin choice.

**Perimeters** offers **1 perimeter**, **2 perimeters** (the default), or
**Full width** for boxes, modules, and complete sets. **Nozzle size** offers
**0.6 mm** (the default) and **0.8 mm**. These choices target thin sections with
one or two nominal extrusion lines: 0.65/1.30 mm for the 0.6 mm nozzle and
0.85/1.70 mm for the 0.8 mm nozzle. They apply to Plain and Miura-ori walls.
Full width retains the original solid wall geometry. Select a numbered
perimeter choice to make Miura-ori available again. Controls are hidden for unrelated parts.
The module's bed-facing rear panel remains a separate floor dimension, rather
than being sized as a vertical extrusion wall.

The API retains `box_floor` (0.8 or 3), `module_rear` (0.9 or 2), and adds
`facade_floor` (0.8 or `"default"`). Omitting `facade_floor` retains the original
facade for older saved requests and CLI callers. Each geometry variant has a
separate build identity and cache match; external dimensions remain fixed.
Complete sets apply the floor choice to each matching drawer facade and box.

The shelled facade retains the front and side profiles, lock opening, screw
interfaces, label recess and seating lands. It removes material from the rear,
leaving reinforcement around the perimeter, lock and screws. Its print exports
place the front face on the bed with the rear cavities open upward; check the
existing recessed label and lock details for local support in your slicer.
The original facade retains its rear-down print orientation. Material savings
are measured from CAD volume; printed strength and print time require a slicer
and physical samples.

```bash
python -m vault build --part facade --facade-floor 0.8
python -m vault build --part facade --facade-floor default
python tools/check_assembly.py --case S4:1 --facade-floor 0.8
python tools/check_label_interfaces.py --facade-floor 0.8
```

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

With Gridfinity selected, **Box bottom → Floorless** opens the cell bottoms
and retains the grid webs and perimeter as physical support. The socket
profiles and height match the 0.8 mm-floor Gridfinity box. The API/CLI value
is `box_floor: 0` / `--box-floor 0`, accepted only with Gridfinity; switching
the browser back to a plain base restores the selected minimum/default floor.
The floor control is hidden for a floorless box alone; it still controls the
facades in a complete set. Floorless boxes
have their own build and cache identity and combine with either rear-wall
pattern. Regenerate the box to use this option.

```bash
python -m vault build --part box --box-variant gridfinity
python tools/check_assembly.py --definitions-only --box-variant gridfinity
python tools/check_assembly.py --case S4:1 --box-variant gridfinity
```

**Wall pattern** selects **Plain** or **Miura-ori** for both the module and
box. Every eligible module face is included; connector roots, runner lips,
stopper regions, corners and other mechanical lands remain solid. Box patterns
apply to the nonmating rear panel, and the plain backing behind its side runner
channels follows the same perimeter target. The floor, rear corners, top rim,
runner profiles and front attachment features remain protected. With two
perimeters and a 0.8 mm nozzle, the box cavity is 0.8 mm narrower overall;
existing drawer-fit inserts designed for the original cavity need resizing.

Plain walls have flat thin panels. Miura-ori pairs native reliefs on both faces
to target the selected thickness normal to each facet. Fold junctions and
transitions into structural lands can be thicker. Pitch accepts 8–40 mm and
maximum relief depth accepts 0.2–2 mm, defaulting to 14 mm and 1.7 mm. Fold height
is reduced as needed to fit the selected thickness inside the existing wall
envelope. Miura-ori is a rigid crease relief, not a folding mechanism.

These are geometry targets for the **Arachne** wall generator. Arachne varies
extrusion width and transitions between line counts, so inspect the actual
sliced paths with the chosen nozzle and print profile. Structural lands need
additional lines; CAD checks do not establish printed fit or stiffness. See
[Prusa's Arachne documentation](https://help.prusa3d.com/article/arachne-perimeter-generator_352769).

Fresh API requests use `wall_pattern` (`plain` or `miura`), `wall_perimeters`
(`1`, `2`, or `"full"`), and `nozzle_size` (`0.6` or `0.8`). Line width is derived
from the nozzle; construction and patterned-face controls are no longer offered.
The CLI equivalents are `--wall-pattern`, `--wall-perimeters`, and `--nozzle-size`.
New builds record the resolved settings in their identities and manifests, and
assembly previews and fit receipts match those exact component variants.
Older saved requests retain their historical independent box/module patterns
and thicknesses. Existing immutable builds are not changed or reused as a
new thin-wall selection. The separate viewer catalog remains unchanged.

Changing the selection previews the newest matching cached part, or shows
“not generated yet.” Complete sets show the matching finished parts together in an assembled view,
with an explosion slider, component colors, visibility controls and click-to-highlight.
Fit view centers the visible components; endpoint buttons fit their pose, while
dragging the explosion slider preserves the camera.
The three color circles after **Fit view** open native color pickers for the
complete-set preview. Primary defaults to matte white for the module, facade
and runner guides; secondary defaults to matte black for the box and runner
slides; highlight defaults to matte pink for the geared rails. Changes last
until the page is reloaded and apply only to the assembly preview and its
component swatches. Individual print previews and downloads keep their existing
appearance and contents.
Missing groups and legacy builds that need new assembly assets are listed explicitly. Recent builds can still be inspected independently.

Choose **Two S drawers** with family L for an L² module. Both drawers have the
selected depth and height: L6² 2F contains two S6 2F drawers side by side.
The module keeps the 329.6 mm L width. Boxes, facades and geared rails resolve
to the matching S parts. With an L 2F module, **Four S drawers** selects a
2 × 2 arrangement of S1F drawers. Both layouts use the same open L² 2F module
and shadow-gap pattern for four S1F facades, sharing its build and STL/STEP downloads
for the same depth, rear thickness, and wall settings. The layout changes drawer parts,
quantities and placement. Module-only previews and downloads therefore stay
the same when switching between two and four drawers. Other families offer
one drawer. Each complete-set ZIP
includes `PRINTING.txt` and `print-plan.json`, identifying the immutable build
and number of copies of each printable file; repeated parts share the same STL.

Assembly previews use explicit native-coordinate transforms from
`src/vault/assembly.py`. The view includes all twelve generated part groups.
The module's native underside is rotated down into the installed drawer frame;
the box stays upright with its floor below its contents. Print orientations
and immutable component meshes retain their original coordinates.
Facade caps sit in the documented screw seats. Keys and their caps occupy the
front lock, with the spring pair seated behind each facade. Runner stops occupy
the module's side slots, and latches sit on its underside connector banks.
Only screws are omitted. S scenes have 18/26/42 instances for 1F/2F/4F;
M has 20/28/44 and L has 21/29/45. L² has 35/51/83 instances with two
drawers, or 67 with four S1F drawers in a 2F module.
Each drawer has two springs and a left/right runner pair on every tier;
latch quantities follow the module's connector banks, independently of drawer count.
The drawer group moves forward while the explosion separates its facade,
rails, slides, key, springs and caps. Runner stops and latches separate from
the module with the fixed hardware.
Exploded positions illustrate the parts; they do not certify a disassembly path.
Accessory build IDs are pinned separately from the six groups covered by the
drawer fit check. A changed accessory build also invalidates the scene's receipt;
the UI explicitly identifies accessory fit as unchecked.

New builds include finished assembly STL and STEP assets under `preview/assembly/`.
These omit module support webs and box runner sheets. Printable exports retain
those supports. The manifest identifies component roles, native coordinates and
print-to-native transforms. Legacy caches remain downloadable but require
regeneration for assembled viewing; no placement is guessed from print bounds.
Preview assets are excluded from printable ZIP bundles.

After generating a complete set, the worker imports its exact finished STEP
assets and checks topology, rigid transforms, mating registrations and pairwise
intersections for the six drawer component groups using `src/vault/assembly_validation.py`.
All displayed instances also receive inventory and rigid-transform checks.
Accessory interfaces are outside the native drawer fit audit. Intentional seating and
stop contacts are allowed; positive-volume collisions above numerical tolerance
fail. A fit-check receipt pins the result to the selected configuration and
immutable component build IDs, assembly definition and validator revision. Failed checks preserve individual exports and
mark the job failed. The scene warns when its cache combination has no passing
receipt. These checks verify the closed assembled pose, not printed fit or motion.

Assembly audits can also be run independently. Include `--wall-perimeters 2`
to audit the new default walls; omitting it retains historical native geometry:

```bash
python tools/check_assembly.py --definitions-only
python tools/check_assembly.py --case S4:1 --case L7:2:3:2
python tools/check_assembly.py --case L6x2:2 --case L3x2:1:3:2
python tools/check_assembly.py --case L6x2x2:2
python tools/check_assembly.py --case S4:1 --wall-pattern plain --wall-perimeters 1 --nozzle-size 0.6
python tools/check_assembly.py --case S4:1 --wall-pattern miura --wall-perimeters 2 --nozzle-size 0.8
python tools/check_assembly.py --all  # all 260 native assemblies; expensive
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
revision information. New cached parts are checked against their recorded
dependency graph, resolved parameters and runtime toolchain. A build from an
older clean commit can remain fresh when those inputs agree. Changed dependency
files appear in the freshness reasons. Either dirty checkout or unknown Git
provenance still requires rebuilding. Legacy builds without dependency metadata
retain the exact clean-revision policy. Generate rebuilds rather than reusing
caches while the repository is dirty.

### Build queue and timings

The **Queue** page at `/queue` lists running, waiting and previous jobs from all
three editors. Select a job to inspect its parts, current stages, errors and
logs, start/finish times, waiting time, run time and render time. Completed parts
keep their checked downloads even if a later task fails. Cancel stops remaining
work; retry creates a new job, or returns an identical active job, and keeps the
original record. Changing a design
while another job runs enables **Add to queue**. An identical active request
returns its existing job.

Jobs and part tasks are stored transactionally in `out/web/jobs.sqlite3`.
The scheduler runs at most **two isolated CAD processes** by default, shared
across all jobs. Independent parts of a complete set can run concurrently;
assembly validation starts only after all requested parts succeed and occupies
one of the same worker slots. Tasks are claimed in job submission order, then
part order. Up to four jobs can be queued/running. Both limits can be configured
with the server's `--workers` and `--queue-capacity` options.

Waiting jobs survive a service restart. A job interrupted during execution is
marked failed, with its completed parts retained; **Retry** resubmits it.
Closing or refreshing the browser does not interrupt work. The execution limit
is one hour from the job's first task through its final validation, excluding
its initial queue wait. Cancellation or failure stops the job's remaining work,
including running processes, without changing successful published artifacts.

Run time includes construction, export validation and rendering. **Render**
measures the review-image renderer specifically, not the entire CAD build.
Stage timings are inclusive: rendering is also within the export stage, so
stage durations should not be added together. Parallel task durations can sum
to more than the job's elapsed wall time. An em dash means no measurement is
available; historical JSON jobs are imported once without inventing timings.
Original JSON files, receipts and immutable builds remain untouched.

Each job pins its complete source digest when work starts; source changes during
the job still fail it. New builds also save `dependencies.json`, with transitive
local imports, declared data assets, file hashes, resolved parameters and runtime
toolchain identity. The worker searches immutable build history for matching
dependency fingerprints and checks all recorded artifact checksums before reuse.
It can reuse a part from an older clean commit even when unrelated source files
changed. Dirty or unknown Git provenance prevents reuse. Legacy builds retain
the original latest-pointer, complete-source and exact clean-revision checks.

Assembly validation verifies each dependency-aware component against the pinned
job's expected inputs, then records its exact immutable build ID and dependency
digest. It can combine compatible parts from different complete source snapshots.
Native intersection and clearance checks retain per-pair timing records; changed
assembly definitions or validators require fresh fit evidence. CAD validation
does not establish physical printed fit.

The graph follows imports inside functions and branches conservatively, so shared
builder files can invalidate more parts than strictly necessary. Tests and browser
assets are outside the geometry graph unless an actual dependency includes them.
The label font JSON and renderer C source are explicit data dependencies. Unknown
local imports, dynamic code loading and missing declared assets prevent reuse.
This is a checked input model, not a sandbox or a proof that arbitrary Python has
no undeclared inputs; it does not provide unconditional 100% confidence.

Inspect the graph, or compare its file states with a saved build, without running
CAD construction:

```bash
source .local-env
python -m vault.dependencies --kind key
python -m vault.dependencies --kind key \
  --parameters out/latest/snap_key/resolved-parameters.json \
  --compare out/latest/snap_key/manifest.json
```

Cache decisions and their reasons are retained in worker logs. Direct CLI builds
continue to generate a new checked export rather than selecting cached artifacts.

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
two springs per drawer, two runner stops per populated tier, a cap for each facade screw
counterbore, and one key cap per drawer if desired. Print one underside latch per
module connector bank: one for S/M, two for L, including either L² drawer layout.
The spring pair and module-mounted latch follow the local assembly instructions
(pages 2 and 8). Each choice exports checked STL and
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

### Facade lock markings

New facade builds include native lock and unlock icons as flush 0.6 mm inlays.
The body uses **Primary** and both icons use **Secondary** in the complete-set
view. These parts move, highlight and hide together as one facade. The markings
stay beside the bottom-tier lock across S/M/L and all three heights.

Choose **Download 3MF** from a generated facade, or use its 3MF in the complete
ZIP. Open it as one multipart object and assign the named primary and secondary
materials to your filaments. Both icons share the secondary material slot.
Keep the supplied print orientation and registration. The ZIP also includes
registered color STEP files and printing notes; the ordinary STL is a
single-color alternative with the same exterior. Existing builds are immutable
and must be regenerated to include markings. Preview palette edits remain local
to the page; assign the desired filament colors in the slicer.
