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
left/right component names survive export. A complete generator set has six
build groups and nine STL files; repeated tier quantities reuse those files.
