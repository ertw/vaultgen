# S4 Module 1f source notes

The purchased reference geometry is
`original_files/01. DRAWERS/01. S Families/S4/Modules/S4 Module 1f.stl`.
The original files are retained unchanged. Dimensions for the reconstruction
come from this STL; the supplied PDFs do not provide dimensioned drawings or
manufacturing tolerances. All CAD dimensions are millimeters.

The PDFs are image documents. The following references use the PDF's page
number, counting its first page as page 1.

## Mechanical features to preserve

- **Drawer guides and stops:** `02_Drawer Assembly.pdf`, pages 7–8, shows runner
  guides fitted to the drawer before the assembly slides into the module's front
  opening. Runner stoppers are then inserted through the module's side openings.
  Those oval openings serve a mechanical purpose and are retained; they are
  distinct from the decorative ovals the user requested removed.
- **Underside latch mount:** `02_Drawer Assembly.pdf`, page 8, shows the module
  flipped over and a separate spring latch pushed into its underside carrier.
  Preserve the carrier, its retaining geometry, and adjacent mating surfaces.
- **Stacking interfaces:** `01_Instructions Manual.pdf`, page 8, says modules
  with the same width and depth can stack, including drawer and sustainer
  modules. Their top and bottom mating features therefore remain part of the
  reconstruction.
- **Separate components:** `01_Instructions Manual.pdf`, page 11, labels the
  module, runner guides, runner slides, runner stopper, and latch separately.
  This project initially reconstructs the module shell alone.

## Naming and print context

`01_Instructions Manual.pdf`, page 6, identifies S/M/L/XL as width families,
the numeric suffix as depth based on 42 mm Gridfinity units, and 1F/2F/4F as
height tiers. These naming rules are context, not a substitute for measuring
the actual module's outside dimensions.

Page 1 says the original design targets basic PLA and standard slicer settings.
Page 20 illustrates optional manual support pieces for stability during upright
printing. These are source statements, not print qualification of the rebuilt
model.

The requested intentional changes are removal of the bottom branding and
decorative ovals, the “align to connect” text and adjacent arrow, and the large
“S4” marking. The user subsequently requested removal of the transverse
alignment groove as well, including its continuation across the nearby
dovetail crowns. It appears to be a visual positioning reference; no mating
rib or snap was identified that engages this groove. Mechanical interfaces
are preserved.

## Source mesh condition

The source is a 53,474,534-byte binary STL with SHA-256
`70e689ceb22a620764bd98eb776c7c143292c52dedabe13c9d3ecafe5a4b9e03`.
Reading it with trimesh 4.12.2 and its default vertex merging gives 1,069,489
triangles and 534,727 vertices. Its triangle winding is consistent, but it is
not watertight: there are 2 edges used by one triangle, 13 used by three
triangles, and 10 used by four triangles. The mesh also has 6,522 zero-area
triangles and 2 duplicate triangles. These defects belong to the purchased
reference and are not repaired in place.

The source uses large absolute coordinates. Its original-coordinate bounds are
`[8919.056640625, 722.38427734375, 583.0018310546875]` to
`[9084.0517578125, 779.3933715820312, 771.1028442382812]` mm. The resulting
extents are approximately 164.995117 × 57.009094 × 188.101013 mm; these axes are
reordered for the model's width, drawer travel, and height coordinates.

The historical module comparison registration swaps source Y and Z and retains
X, producing a reflection (determinant −1). Assembling the original module with
the bottom-down box instead requires a proper rotation: negate centered X as
well as exchanging Y and Z (determinant +1). This places the module's lower mouth
pocket at negative X and its upper pocket at positive X, matching the box's gear
exits. The mouth constructors now use that assembly handedness. Historical
whole-model comparisons keep their original registration for reproducibility;
`tools/check_runner_interfaces.py` records the corrected interface checks.

Binary STL stores coordinates as 32-bit floats. At this source location,
adjacent representable coordinates are approximately 0.000976563 mm apart
along original X and 0.000061035 mm apart along original Y and Z. Smooth CAD
surfaces cannot reproduce every such quantized facet exactly. A measured
surface-distance tolerance is therefore more meaningful than a literal
pixel-perfect or identical-triangle claim. The comparison reports preserve
the source geometry and distinguish these finite-precision differences from
the intentionally removed decoration.
