# Generator geometry

The generator supports S, M, and L widths, depth units 3–7, and 1F or 2F
heights. The Python `ModuleSpec` still permits previously supported sizes;
`BoxSpec` and `FacadeSpec` reject XL and heights beyond 2F. Drawer depth
extensions above 7 remain available to Python callers, but are not exposed
in the web generator.

`src/vault/drawer.py` defines shared box/facade dimensions and screw axes.
`build_box(spec=ModuleSpec(...))` and `build_facade(spec=ModuleSpec(...))`
accept the same size as `build_module`; they also accept `BoxSpec` and
`FacadeSpec`, respectively. Existing calls without a spec retain S4 1F
geometry and the existing facade `gap` argument remains positional.

## Dimensions and interfaces

| Property | Rule |
| --- | --- |
| Sleeve width | S 164.8, M 254.0, L 329.6 mm |
| Sleeve depth | `42 × depth_units + 20.1` mm |
| Sleeve skin height | `48 × height_units − 1` mm |
| Box width | Sleeve width − 30.6 mm |
| Box depth | Sleeve depth − 2.3 mm |
| Box height | Sleeve skin height − 9.5 mm |
| Box bottom | Z = 5 mm in assembly coordinates |
| Box front / facade seating plane | Y = sleeve depth |
| Runner / screw tier pitch | 48 mm |
| Screw height | Z = 23.5 mm + tier offset |
| Inner lock screws | X = ±51.45 mm |
| M outer screws | X = ±92.45 mm |
| L outer screws | X = ±130.25 mm |

## Shelled facades

`FacadeSpec(facade_floor=0.8)` subtracts deeper rear-open pockets from the
original native facade. `facade_floor='default'` retains the original geometry.
The thin variant has a separate identity such as `s1f_facade_floor_0p8`; older
saved builds without the field resolve to the default facade.

The flat front remains at Y=10 with a 0.8 mm skin. Under the recessed label face
at Y=7.91, the cavity stops at Y=7.11; a matching 0.8 mm inset also protects the
recess sidewalls. A 3.5 mm land inside the flat front perimeter retains the
entire rolled outer edge and the rear seating rebate. The rear seating lands
retain their complete original footprint for the first 0.8 mm; a 45° cavity
flare connects that opening to the broader front pocket. The lock's protected
radius is 24.125 mm, 4 mm beyond its largest opening lobe. Screw protection
extends to radius 10.8 mm, 4 mm beyond the existing 6.8 mm risers. Retained
2.4 mm webs connect the screw tiers, lock region and perimeter where material
exists in the original facade. The shell removes material without adding it to
the existing rear clearances or changing the front, sides, screw bores,
counterbores or label recess. All construction uses native wires, extrusions
and booleans; no purchased meshes are used.

Thin facades print front-down: rotate −90° about X and translate +10 mm in Z.
The export records the exact inverse transform for assembly previews and
checks. Rear pockets open upward rather than forming broad unsupported roofs.
The existing recessed label and lock features may still need local support;
inspect the sliced paths and outside roll. Default facades keep their original
rear-down orientation. Strength, screw torque and printing time have not been
qualified by physical tests.

```bash
python -m vault build --part facade --family S --height-units 1 --facade-floor 0.8
python tools/check_label_interfaces.py --facade-floor 0.8
python tools/check_assembly.py --definitions-only --facade-floor 0.8
python tools/check_assembly.py --case S4:1 --facade-floor 0.8
```

The facade tests compare all six S/M/L × 1F/2F variants against the original,
checking connectedness, bounds, skin and reinforcement. The label checker
checks the unchanged recess clearance. The assembly checker checks the closed
rigid pose and mating registrations; it does not certify lock motion, loaded
strength or printed fit. Fresh exports retain the normal STEP round-trip and
watertight print-mesh checks.

## Gridfinity boxes

`BoxSpec(box_variant='gridfinity')` adds an integral baseplate inside the native
Vault tray. `plain` remains the default, including for existing saved requests.
The 42 mm pitch and mating dimensions follow the
[Gridfinity design reference](https://gridfinity.xyz/specification/) and the
[Gridfinity Rebuilt bin](https://github.com/kennetek/gridfinity-rebuilt-openscad/blob/main/src/core/standard.scad)
and [baseplate definitions](https://github.com/kennetek/gridfinity-rebuilt-openscad/blob/main/src/core/gridfinity-baseplate.scad).
Construction uses native rounded wires, extrusions, lofts and booleans; no
downloaded or purchased geometry is a constructor input.

| Property | Value |
| --- | --- |
| Cell pitch | 42 mm in X and Y |
| Grid columns | S 3, M 5, L 6; L² uses S drawers |
| Grid rows | Selected depth units, 3–7 |
| Socket opening | 42 mm square, R4 corners |
| Socket profile, bottom to top | 0.7 mm lower chamfer, 1.8 mm vertical, 2.15 mm upper chamfer |
| Clearance below profile | 0.35 mm |
| Total rise above the closed floor | 5 mm |
| Closed floor beneath sockets | Selected 0.8 or 3 mm |

Whole cells are centered across the available floor and stay behind the front
lock opening. Mating profiles keep their dimensions for every family, depth,
height and drawer layout. Exterior geometry, attachment passages, screw axes,
runner channels, removable supports and assembly transforms are preserved.
The grid remains in both printable and finished assembly exports; only the
normal sacrificial runner sheets are removed from finished previews.

Default identity is `s4_box_1f_gridfinity`; the thick-floor variant is
`s4_box_1f_floor_3mm_gridfinity`. Plain aliases stay unchanged. The configuration
and immutable build parameters record `box_variant`; module, facade, rail and
accessory identities remain independent of this box option. No catalog entries
are inferred from generated files.

**Floorless Gridfinity** uses `BoxSpec(box_variant='gridfinity', box_floor=0)`
and the identity `s4_box_1f_floorless_gridfinity`. Each 36.3 mm rounded-square
cell bottom (R1.15 corners) is cut through the floor and base skin. The
0.8 mm foundation remains beneath the grid webs and perimeter to connect
the grid to the drawer walls. The socket datum stays at Z = 5.8 mm, matching
the thin-floor variant; the 5 mm socket profile is unchanged. This removes
the square cell floors without moving the bins, runner interfaces or outer
envelope. The lower socket chamfers support single-cell bins, and the webs
support multi-cell bridges. This option combines with either rear-wall
pattern; its protected floor-fillet band uses the retained 0.8 mm foundation.
Plain boxes reject `box_floor=0`.

Native tests check the retained floor, socket sections, unchanged outer bounds,
and nominal Gridfinity feet at edge cells and across multiple cells. The normal
export pipeline also checks solid validity, STEP round trips and watertight
print meshes. The assembly audit checks the closed Vault assembly, including
its runners and rails; it does not check added bins or their height. These
checks do not certify printed fit, retention under load or insertion motion.

```bash
python tools/check_gridfinity.py --case S4:1 --case L7:2:3
python tools/check_assembly.py --case S4:1 --box-variant gridfinity
python -m vault build --part box --box-variant gridfinity --box-floor 3
```

The Gridfinity checker compares the variant with a plain native box, proves
that material was added only inside the grid footprint above the floor, and
checks nominal rounded bin feet and a full-grid bin base. Single-cell feet can
seat on the floor; a multi-cell bin's continuous bridge seats on the webs with
its feet 0.25 mm above the floor. A deliberately displaced bin must collide
with a socket wall. `--plain-step` and `--gridfinity-step`, with a single
`--case`, audit saved solids and record their input checksums.

## Gridfinity containers

`bin_config.py` defines the bounded drawer drawing; `bin.py` constructs it with
native rounded wires, extrusions, ruled lofts and planar faces. No purchased
geometry is used. Each edge-connected region receives a continuous floor and
outer walls; disconnected regions are exported as separate solids. Internal
selected edges become permanent separators. Concave footprints and holes retain
their boundary walls. Grid cells use the same 42 mm pitch as the drawer sockets.

Nominal feet have a 35.6 mm rounded-square bottom (R0.8), an 0.8 mm lower chamfer,
a 37.2 mm / R1.6 vertical section up to Z=2.6, and an upper chamfer to 41.5 mm /
R3.75 at Z=4.75. The continuous floor reaches Z=7.0 mm. Total heights are 28 mm
(1F) and 77 mm (2F), chosen to clear even the 3 mm-floor drawer. Full-grid bins
occupy the grid footprint with 0.25 mm edge clearance; the drawer's margins are
preserved. Feet remain unscaled across families, heights and wall variants.

Plain walls target 0.65 or 1.30 mm thickness. Miura-ori uses paired native facets
on both sides, with 14 mm pattern pitch and 1.3 mm relief. Face separation
compensates for slope to target the selected normal wall thickness. Collinear
painted divider edges merge into continuous runs. The fold amplitude blends into
thin webs at actual T/X and boundary connections; a divider that stops short of
an outer wall does not interrupt that wall's pattern. Ordinary grid boundaries
receive no joint pads.

Joint blends span 7 mm along each adjoining run, and the pattern fades into thin
floor and top edges over 3.5 mm. The blend surfaces use native triangular facets;
normal thickness checks allow 0.02 mm deviation from the selected target. Rounded
corners retain thin walls. Outer folds extend inward, preserving the external
footprint and mating feet. These are rigid printed walls; stiffness and slicer
perimeter counts require physical/slicer comparison.

`python tools/check_gridfinity_bins.py` audits native containers in their actual
drawer grid placement. It checks collision and vertical clearance; the geometry
tests cover connectedness, selected footprints, separators and wall variants.
Use `--build out/builds/<build-id>` to check the exact exported print STEPs with
their recorded transforms back into drawer coordinates. The report records input
checksums and samples horizontal sections at actual T/X junctions above the floor.
`python -m vault.bin_build --configuration containers.json` uses the normal
immutable part-set pipeline: each solid and boundary shell, STEP round trip and
watertight print mesh must pass before publication. Individual print files move
each bin onto the bed, while recorded cell coordinates retain drawer placement.
These checks do not establish printed fit, loaded behavior or stiffness.

### Drawer-fit containers

`BinConfiguration(container_type='drawer')` reuses the cell editor for removable
boxes inside a plain native drawer. The logical grid uses S=3, M=4 and L=6 columns
and the selected depth as rows. Independent X/Y pitches divide the real cavity
dimensions; geometry is constructed at those dimensions rather than scaling a
Gridfinity part. Full nominal widths are 127.2 / 216.4 / 292.0 mm. Nominal depth
is `172.8 + 42 × (depth_units − 4)` mm. Exposed outlines inset by 0.25 mm, with
R3.25 corners, a 1.2 mm floor and a 0.75 mm bottom-edge chamfer.

Native box coordinates use the same lower-left planning-grid frame as the editor.
Placement in the plain drawer is `(-width/2, 5.3, 5 + drawer_floor + 0.25)`.
The front edge stops at Y=`177.85 + depth_delta`, clear of the center lock opening.
Height leaves 1 mm below the drawer rim: 35.45 / 83.45 mm for its 0.8 mm floor,
or 33.25 / 81.25 mm for its 3 mm floor. No Gridfinity feet are constructed.

The balanced preset uses 1.30 mm Miura walls, 1.3 mm relief and the same thin
merged-run junctions as the corrected Gridfinity version. Whole fold counts fit
each planning-cell pitch near a nominal 14 mm; vertical fold rows fit the wall
height near 7 mm. Outer corner attachments end on fold stations, and the folded
surface starts just inside the floor so the union has a real overlap. This avoids
tiny clipped facets at corners and the floor. Rims fade over one fold row, keeping
the transition gentle enough for both wall thicknesses. Native blend sampling adapts to keep the
0.02 mm sampled normal-thickness tolerance and positive offset-triangle area.
The preset balances a thin supported floor,
folded wall section and usable space; it does not compute loaded strength or
printer-specific time. Exports record actual material volume and compartment
height for comparing variants.

`tools/check_drawer_bins.py` audits exact native plain-drawer collisions, vertical
clearance, footless floors, missing-cell topology, sampled normal thickness and
actual T/X junction sections above the floor. `--build` restores checked print
STEP files using their recorded transforms and pins its report to their checksums.
The normal immutable export checks still require valid solids, STEP round trips
and watertight meshes.

## Patterned box rear walls

`BoxSpec(box_rear_pattern='waffle')` and
`BoxSpec(box_rear_pattern='miura')` add two-perimeter corrugation to the rear
wall. `plain` remains the default. This setting is independent of module wall
patterns and combines with either box base and either floor thickness.

The rear wall remains inside its original Y = 2.3–5.3 mm envelope. Both faces
are relieved using the same native Waffle and Miura-ori constructors as the
module's corrugated walls. Pitch is fixed at 14 mm, maximum relief depth at
1.7 mm, and nominal facet thickness at 1.3 mm normal to the face, for two
0.65 mm extrusion lines. Miura fold height is reduced to fit this thickness
inside the original wall. Solid perimeter lands preserve rear corners, the
floor fillet and top rim; the pattern stops 3 mm above the floor fillet and
3 mm below the top. The Gridfinity base, runner channels, removable supports,
rail passages and assembly placements retain their geometry.

Default patterned identities are `s4_box_1f_rear_waffle_corrugated` and
`s4_box_1f_rear_miura_corrugated`; floor and Gridfinity suffixes precede the
rear pattern suffix. Resolved parameters and assembly matching retain
`box_rear_pattern`. Existing plain identities and immutable builds remain
unchanged. Finished previews retain the pattern and omit only the normal
sacrificial runner supports.

```bash
python -m vault build --part box --box-rear-pattern waffle
python -m vault build --part box --box-rear-pattern miura --box-variant gridfinity
python tools/check_assembly.py --case S4:1 --box-rear-pattern waffle
```

Native checks cover solid validity, removed-material containment, preserved
interfaces and sampled normal facet thickness. Export checks include STEP
round trips and watertight print meshes. Inspect the slicer's perimeter paths;
these checks do not establish printed stiffness, bridging or fit.

## Patterned module walls

`ModuleSpec(wall_pattern='waffle')` and `ModuleSpec(wall_pattern='miura')`
apply native relief cutters from `src/vault/wall_patterns.py`. Plain remains the
default. Both patterns offer `pattern_construction='recessed'` (the default) and
`pattern_construction='corrugated'`. Recessed construction removes material from
the outside while preserving the original inner surfaces, producing a variable
wall thickness. Corrugated construction pairs relief on both sides of the
nonmating panels to form thin facets; the entire construction stays inside the
original wall thickness. Waffle uses rounded square dimples with sloping
shoulders and flat valleys. Miura-ori uses connected planar parallelograms with
alternating row offsets to form a sharper zigzag crease layout. This is a rigid
printed relief, not a foldable origami mechanism.

| Parameter | Default | Accepted range or values |
| --- | --- | --- |
| `wall_pattern` | `plain` | `plain`, `waffle`, `miura` |
| `pattern_construction` | `recessed` | `recessed`, `corrugated` |
| `pattern_pitch` | 14 mm | 8–40 mm |
| `pattern_depth` | 1.7 mm | 0.2–2 mm |
| `pattern_line_width` | 0.65 mm | 0.6–1 mm |
| `pattern_faces` | `all` | `all` four long faces, or `sides` left/right only |

Recessed default valleys retain **1.3 mm** within the 3 mm skin, targeting two
0.65 mm extrusion lines for a 0.6 mm nozzle; crests and ribs retain more material.
Corrugated patterned facets target **1.3 mm thickness measured normal to the
facet**, with thicker fold junctions, panel borders and structural transitions.
For corrugated Miura-ori, the selected depth is a maximum recess envelope:
the effective fold amplitude is reduced so the normal facet thickness also
fits inside the original skin. It is not a promise of a full 1.7 mm fold height.
The constructor requires `pattern_depth + 2 * pattern_line_width`
to fit the actual native wall; custom `ShellDimensions` therefore receive an
additional thickness check. Values are finite and bounded at both API and CLI
entry points. Cells become rectangular on narrow side panels; when a large cell
cannot avoid a short module's connectors, its footprint is trimmed to an
available rectangular land. A panel with no room for a tapered cell is rejected. These
are geometric limits; slicer line placement, printability and loaded stiffness
still need checking on a physical part.

Side panels stay between the existing runner floors and ceilings. Solid lands
retain the entire stopper footprint and its chamfer, corners, inter-tier webs,
front mouth lips, catches and mounting features. The front and rear bands follow
native feature dimensions, retaining at least 12 mm at the front and 8 mm at the
rear. Top and bottom panel exclusions use the actual native connector and cutter
footprints, with 3 mm of surrounding full-thickness material. This protects the
stacking mating surfaces and their roots. L² also retains the central divider
and its root lands. The rear panel, its selected thickness, and all sacrificial
mouth supports remain unchanged.

Waffle uses tapered cells that avoid every protected footprint. Miura
clips its connected crease field with native tapered masks: panel edges and
feature exclusions return to full thickness over a 2:1 run relative to depth.
Both constructions preserve mating surfaces and their protected inner and outer
lands; corrugation changes only nonmating panel surfaces. Patterns never stretch
a mating cross-section or move assembly transforms.
Corrugated side walls reshape the broad back of the runner channels while
retaining their floor, ceiling, stopper and mouth regions. Recessed walls keep
those broad inner faces flat. This difference matters when comparing loaded
stiffness and print behavior.
Finished assembly exports omit only the usual sacrificial supports; printable
exports retain them. Every patterned build uses the existing solid, STEP
round-trip and watertight-mesh validation pipeline.

```bash
python -m vault build --wall-pattern waffle
python -m vault build --wall-pattern miura
python -m vault build --wall-pattern waffle --pattern-construction corrugated
python -m vault build --wall-pattern miura --pattern-construction corrugated
python -m vault build --wall-pattern miura --pattern-pitch 20 \
  --pattern-depth 1.4 --pattern-line-width 0.8 --pattern-faces sides
python tools/check_assembly.py --definitions-only --wall-pattern waffle
python tools/check_assembly.py --case S4:1 --wall-pattern miura
python tools/check_assembly.py --case S4:1 --wall-pattern miura --pattern-construction corrugated
python tools/check_wall_patterns.py --pattern waffle --construction corrugated
```

The wall-pattern audit checks exact containment of the removed material and
unchanged native connector roots, probes the protected interfaces, and samples
corrugated thickness along native face normals. Its optional `--baseline-step`
and `--pattern-step` arguments inspect exported solids and record their hashes.
Thickness samples do not establish slicer toolpaths or printed fit.

Default pattern identities are `s4_module_1f_waffle` and
`s4_module_1f_miura`. Nondefault pattern controls add a stable parameter digest;
the corrugated constructions add `_corrugated`, and resolved parameters retain
every value. Existing recessed aliases remain unchanged. Box, facade, rail and accessory
identities remain independent of wall style. Existing build directories remain
immutable. The historical S4 source comparison expects the original flat skin
and is not an acceptance test for these intentional reliefs.

## Multi-drawer modules

`ModuleSpec('L', 6, 2, drawer_columns=2)` builds **L6² Module 2F**: a single
L-width module with two continuous S-width cavities. It accepts two S6 2F
drawers or four S6 1F drawers. Bay centers are X = −82.4 and +82.4 mm.
Each bay has the S cavity and unchanged runner and locking profiles.
The vertical divider is constructed from native features in one L envelope;
it does not contain the outer ears, hooks or stacking rails of two independent
S modules. The two stacking connector banks retain their existing L positions.

The center divider has rear access passages for its runner stops on every
48 mm tier. Handed mouth recesses and removable webs repeat independently in
each bay. Printable exports retain all support webs; finished assembly assets
omit them. Only the outside of the module has stacking connectors and rear
stacking-entry reliefs.

Adding `drawer_rows=2` selects **four S1F drawers** in that same open module.
The lower drawer origins are (X,Z) = (−82.4,0) and (+82.4,0); the upper row
uses Z = 48 mm. The cavities remain continuous from Z = 3 to 92 mm, matching
the open layout measured in the purchased L² 2F reference. The existing
floor/ceiling recesses stay at the outside skins. Four S1F facades retain the
nominal 1 mm gap between rows.

Every L² 2F module uses the **shadow-gap pattern for four S1F facades**,
independently of the selected drawer contents. Four S1F perimeter rebate cutters are placed at
the drawer origins above; they remove the existing 0.5 mm deep, 1 mm wide strips
where they meet the module's front rim. The same pattern remains when two tall
S2F facades are fitted. The open middle of each bay has no horizontal seating
land or added retention recess. Facades still meet the front seating datum on
the surrounding lands. This shared rebate is an intentional change from the
purchased reference.

The module's name, resolved build parameters and download identity depend on
its envelope, columns and rear thickness. Drawer rows affect the installed
parts and their quantities, not the module geometry. At depth 6, both 2F
layouts resolve to `l6_2_columns_module_2f` and share its STL/STEP files and
reusable build. Existing immutable exports retain their original geometry and
provenance; a changed module is regenerated through the normal export pipeline.

The generator's `drawer_columns` field defaults to 1 and accepts 2 only with
family L. Existing saved configurations without this field remain single
drawers. `select_spec` resolves the module to L² and the box, facade and geared
rails to S; shared runners still depend only on depth. The assembly definition
duplicates the S drawer instances at the recorded bay centers, and fit receipts
include the selected layout and the exact component builds, so the two layouts
keep separate assembly receipts while sharing the module. ZIP files reuse
the unique STL/STEP files and record the required quantities. In the independent
Labels editor, choose S labels for these S facades.

`drawer_rows` defaults to 1. The value 2 is accepted only with family L,
height 2F and two columns. Boxes and facades then resolve to S1F; the module
stays 2F. The print plan calls for four copies of each box, facade and geared
rail, and four left/right runner pairs in total. The assembly preview includes
33 drawer components plus 34 accessory instances (67 total). Facade caps use
the screw seats; the other accessories are laid out separately with unverified
installation poses. Drawer components retain their own drawer identity and
explicit (X,Z) placement.

The supplied L² module references cover depths 3–7 and 1F/2F/4F. The web
generator remains limited to 1F/2F; 4F is available only through the lower-level
module API/CLI and has no generated matching drawer set. XL² references are
outside this implementation. The separate CAD viewer's fixed catalog is
unchanged; L² builds are available through the configurator and CLI.

`python tools/check_multi_drawer.py` records reference registration, divider
datums and sampled interface comparisons. The shared L6² 2F module is checked
in [`research/unified_module_reference.json`](../research/unified_module_reference.json);
the earlier L3² 1F and L6² 2F evidence remains in `research/multi_drawer.json`.
The checker samples four transverse sections in both directions against a
0.1 mm limit. It covers runner/mouth profiles and the central access passage;
it excludes the intentionally changed rear wall and mounting bores, outside
styling, branding, stacking connectors and shadow rebate.
`python tools/check_assembly.py --case L6x2:2` checks the complete
native two-drawer assembly; `--case L6x2x2:2` checks four drawers.
[`research/unified_module_assembly.json`](../research/unified_module_assembly.json)
records the two-drawer audit from current native construction and the four-drawer
audit from exact checksummed finished STEP exports, identifying their component
builds; both use the shared module and default thicknesses.
These checks do not establish insertion motion, runner-stop installation,
catch/latch operation, loaded behavior or printed fit. Accessory retention
when four drawers share the open bays remains unvalidated. The historical
S4 `validate` command does not apply to L².

## Shared drawer features

S repeats its screw pair at every tier. M/L keep the inner pair at the
bottom lock and repeat their outer pair at each tier. The box and facade
use the same list of axes. Screw holes remain 3.6 mm in the box and 4.4 mm
in the facade, with the original facade counterbores and bosses.

The gear mechanism remains on the bottom tier in both heights; its central
opening, cross-sections, rounded exit lips, roof clearance and fixed gear
Z positions do not scale. Its open exit passages extend with family width.
Both lower rail passages include the upper exit's rounded roof profile:
2.8 mm wide with R1 corners, a 0.8 mm flat crown and 1.516 mm rise above their
original ceilings. This intentional relief gives bridge sag extra headroom
while preserving the floors, side shoulders, front rim and blind stops.
It applies to plain and Gridfinity boxes at every supported size; CAD checks
do not establish printed bridging or fit.
The two blind rail pockets end at X = ±66.3 mm for every family, preserving
the working S4/S-rail unlocked installation stop. M/L rails extend their
outgoing tails only; extending the blind pockets would let the tooth train
retract past the lock's installation position. Push both rails against their
blind ends before installing the lock in its open position.
`research/gear_pocket_stops.json` records measurements of the original S4 1F,
M3 1F and L6 2F pockets; all terminate near this central datum despite their
different outside widths. Their rounded end surfaces differ from the native
flat stops. `python tools/check_gear_pocket_stops.py` reproduces the measurements.
Runner channels repeat every 48 mm and move out with the side walls. The
0.8 mm floor, 1 mm interior floor fillet, 1.3 mm runner backing walls, 0.3 mm
runner flank clearance, and breakaway sheets are preserved. Sheet teeth are
repeated at approximately the original pitch as depth changes.

The facade uses the sleeve's parametric outer silhouette and a matching
perimeter shadow rebate. Because the silhouette rolls inward behind its
widest seating edge, the rebate makes the actual facade width and height
about 0.021 mm smaller than their nominal values. The same effect already
exists in the S1F template. Facades have 10 mm nominal thickness.

## Source evidence and limits

`research/drawer_size_datums.json` records purchased S/M/L 1F/2F box and
facade bounds and box screw centers measured from front cross-sections.
It confirms the nominal box size formulas, repeated runner tiers and
additional M/L screw locations. The source files remain research inputs;
constructors do not load or redistribute them.

The larger facades extend the native S1F template's rear pockets and keep
the handle and lock recess on the bottom tier, aligned with the box gear
mechanism. This is a consistent generated assembly, not a claim that every
larger purchased facade's pocket topology, markings, and print layout have
been reconstructed. The handle, screw and lock features retain their
original dimensions.

Existing S4 box/facade regression tests cover gear passage lips, corner
radii, closed pockets, cavity fillets, supports, screws and rebates.
`tests/test_drawer_sizes.py` additionally checks S3 2F, M5 1F and L7 2F
for valid connected solids, expected bounds, floor thickness, screw
alignment, runner positions, gear exits and matching facade rebates.
These CAD checks do not establish physical printed fit.

## Labels

Label requests have their own bounded configuration in `label_config.py` and
select a drawer family independently of the main parts configurator. Length is
`47 + (facade_width - 164.8) / 2`: S 47 mm, M 91.6 mm, L 129.4 mm. Height and
thickness stay 19.4 × 2 mm, independent of depth and tier count. The straight
section extends while the semicircular end, small opposite corner radii, rim,
and text profiles keep their dimensions. Requests without a family default to S.
The native constructor uses shared glyph outlines from
`static/label-font.json`. These outlines and their font license are local source
assets included in immutable source snapshots, not purchased reference meshes.

The front is a 0.9 mm face with 0.6 mm flush text inlays. The hollow option
retains a 0.8 mm perimeter rim; the solid option fills the back. One or two lines
are centered by visible glyph bounds with a 1.5 mm interline gap. Text is never
stretched to fit. The editor uses the same curves and layout in millimeters.

Every material shares the same rigid front-to-print transform. Text and
background therefore meet on Z=0 without independently centering individual
letters, counters, or color parts. Disconnected solids within a material are
checked individually, then exported in their shared coordinates. The 3MF stores
named color components in one assembly. Native topology, STEP round trips,
watertight print meshes, and material registration are checked before publishing.
These checks do not certify small-text resolution or adhesive fit on a printer.

`python tools/check_label_interfaces.py` checks the conservative full label
envelope against the matching native S/M/L facades at both 1F and 2F using the
family-specific rigid transform in `label.py`. The rounded tip stays at native
X=32.3 mm while the outside edge follows half the facade width. It checks
clearance and matching label width, while geometry unit tests check
that the mounted face points outward and the lettering stays upright. This is
a geometric seating check, not a snap-fit or physical retention test.

`python -m vault.label_build` builds the default label through the immutable
export pipeline. Pass `--configuration label.json` for an editor-style request
and `--output PATH` for separate build storage. `python tools/label_font.py`
reproduces the shared vector font from the pinned Matplotlib font asset.

## Runner guides and slides

`runner_guides.py` and `runner_slides.py` reconstruct the universal x3–x7
parts with native arcs, extrusions, fillets and chamfers. Their source files
contain two identical copies of each part. Exported left/right names identify
installation sides; they do not imply handed geometry. Use one pair of each
per populated runner tier, repeating prints for additional tiers.

| Part | Width | Length at depth n | Print height |
| --- | --- | --- | --- |
| Guide | 27 mm | `42 × n + 17.5` mm | 9.4 mm |
| Slide | 18.22 mm | `42 × n − 8` mm | 8.979 mm |

Depth changes the straight lengths and stop positions, preserving the mating
profiles. The x3 guide retains the source's one-millimeter-shorter travel slot.
These parts are shared across S/M/L widths and 1F/2F heights. Their constructors
never load the purchased meshes. Both print with the supplied flat face on Z=0.

Slides add a 1 mm, 45° crown chamfer at the insertion nose to ease entry into
the mate. The top edge moves from Y=0.048 to Y=1.048 mm; the stop and running
profile beyond the nose are preserved. This intentional clearance change
departs from the purchased mesh, so the original-mesh slide audit's 0.08 mm
deviation limit no longer applies at that chamfer.

`tools/check_runner_guides.py` and `tools/check_runner_slides.py` compare native
geometry against both original copies at each depth. The guide audit also
checks module/guide and guide/slide clearance and the head stop.
`tools/check_runner_slides_fit.py` checks the native box on both sides and every
tier of S4/1F, M3/1F and L7/2F. The seated slide contacts its rear stop; withdrawing
it 0.1 mm clears that contact. These are geometric checks, not printer fit tests.

Runner and geared-rail sets share `exports.export_part_set`, which checks each
solid, each print/model STEP round-trip, watertight STL, and the combined STEP's
part count and names. Identical parts receive independent STEP shapes so both
left/right component names survive export. A complete generator set has twelve
build groups and fifteen STL files; repeated tier quantities reuse those files.

## Universal accessories

`accessories.py` constructs the spring, runner stop, facade cap and key cap from
native arcs, extrusions, lofts and fillets. `key.py` / `key_build.py` supply the
single-piece key with an integrated drive pinion. CLI selectors are `key`, `spring`, `runner_stop`,
`facade_cap`, `key_cap`, and `latch`; these have no family/depth/height dependencies.
`latch.py` uses native symmetric curves for the underside latch.
`LatchDimensions` records explicit outline and thickness relief (0.10 and
0.15 mm), giving a default print thickness of 4.35 mm. Setting both to zero
removes that fit relief while retaining the lightened opening.
The rounded through-window extends the enlarged finger aperture along the
central tongue, following its perimeter with native editable curves. Rounded
upper edges (R0.5) and a 0.3 mm lower opening chamfer replace the deep double
countersink. The bed face stays flat at Z=0 and the print height stays 4.35 mm.
Small detents and insertion tips retain R0.15 blends, with the diagonal
insertion leads tapering into the main radius in one native fillet operation.
`LatchDimensions.top_fillet_radius=0` disables the upper round, including for
research fits with larger outline relief whose tiny insertion tips cannot
accept the default radius. Offset curves are converted to native splines
before extrusion; volume guards, STEP round trips and watertight print-mesh
checks remain in force. Small rounded junctions can require finer tessellation.
The midsection profiles of the outer perimeter, flexible arms, slots, hooks and
detents are preserved, along with the 1.5 mm V-seat chamfers.
The opening intentionally differs from the purchased reference, so historical
latch source-comparison results do not validate this change. Test printed
insertion, retention and restoring force, and compare slicer filament use and
time with the same profile; removing volume adds perimeter without reducing
the part's layer count.
`SpringDimensions` now defaults to zero relief; the spring is nominal.
Reference meshes are used only by the diagnostic tool, never by construction.

Accessory native frames are print frames, not installed drawer poses. The
complete-set view places facade caps at the shared screw axes; other accessories
appear in a labeled loose-part layout in front of the drawer. These display
transforms are explicit in `assembly.py`, independent of print bounds. All
accessories remain outside drawer fit validation, and complete-set receipts
pin their immutable build IDs separately. Quantities include two springs per
drawer and one latch per module connector bank.
The cap interface diagnostic checks a facade screw cap at (51.45, 10, 23.5)
after a +90° X rotation, and a key cap at Z=35.517 after a 180° X rotation.
These are geometric seated-pose checks, not insertion or snap retention tests.
