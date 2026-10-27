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
rail, and four left/right runner pairs in total. The assembly preview has 33
instances, each with its own drawer identity and explicit (X,Z) placement.

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
build groups and sixteen STL files; repeated tier quantities reuse those files.

## Universal accessories

`accessories.py` constructs the spring, runner stop, facade cap and key cap from
native arcs, extrusions, lofts and fillets. `key.py` / `key_build.py` supply the
existing snap-fit key. CLI selectors are `key`, `spring`, `runner_stop`,
`facade_cap`, `key_cap`, and `latch`; these have no family/depth/height dependencies.
`latch.py` uses native symmetric curves for the underside latch.
`LatchDimensions` records explicit outline and thickness relief (0.10 and
0.15 mm). Setting both to zero provides the nominal comparison.
`SpringDimensions` now defaults to zero relief; the spring is nominal.
Reference meshes are used only by the diagnostic tool, never by construction.

Accessory native frames are print frames, not installed drawer poses. They are
excluded from drawer assembly validation and explicitly listed as omissions in
the scene. Complete-set receipts separately record their immutable build IDs.
The cap interface diagnostic checks a facade screw cap at (51.45, 10, 23.5)
after a +90° X rotation, and a key cap at Z=35.517 after a 180° X rotation.
These are geometric seated-pose checks, not insertion or snap retention tests.
