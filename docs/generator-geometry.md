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
Z positions do not scale. Its lateral passages extend with family width.
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
