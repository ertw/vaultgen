# Vault CAD

Editable build123d drawer modules reconstructed from purchased Vault STLs.
S4 Module 1F is the primary reference. Branding, decorative bottom ovals,
“align to connect” text and arrow, the large S4 marking, and the transverse
alignment groove are omitted. Runners, stopper slots, mounting bores, stacking
connectors, tracks, and drawer retention features remain.

Construction uses native curves, extrusions, fillets, chamfers, and short lofts.
It does not load an STL, BREP, or measured profile table. Purchased files in
`original_files/` remain local and are excluded from Git. They are needed only
for reference measurements and comparison validation, not model construction.

## Build

Enter the pinned development environment:

```bash
nix develop
# On a fresh checkout, run just setup once.
python -m vault build
python -m vault validate
python -m unittest discover -s tests -v
```

Other sizes reuse the same feature definitions:

```bash
python -m vault build --depth-units 3 --height-units 2
python -m vault build --family M --depth-units 5
python -m vault build --family L --height-units 2
python -m vault build --family XL
```

All sizes use the shared [build storage library](../../cad-tooling/docs/builds.md).
Successful builds are preserved in `out/builds/<build-id>/`, with Git provenance,
source snapshots, checksums, and `manifest.json`. `out/latest/<size>` selects the
newest build for each size; `out/latest-successful` selects the latest overall.
`--output PATH` chooses a different storage root. The viewer shows builds under
expandable commit messages; builds without Git provenance remain unlinked.
`render` and `validate` select the latest build for the requested size and write
new reports under `out/reviews/<build-id>/`. Legacy output directories remain
readable. Full `validate` currently compares S4 1F against its registered source;
other sizes need separate source checks.

Dependencies are pinned in `pyproject.toml` and `uv.lock`. The Nix workflow is
`nix develop`, `just setup`, `just build`. Builds and storage tests have also
been verified with this pinned Nix environment. Entering the shell does not
install dependencies.

## Size and feature definitions

| File | Responsibility |
| --- | --- |
| `src/vault/spec.py` | Family widths, connector bank positions, depth and tier counts. |
| `src/vault/model.py` | Assembly; require one valid solid with one boundary shell. |
| `src/vault/envelope.py` | Smooth sleeve corners and mirrored outside ears. |
| `src/vault/shell.py` | Cavity, repeated runners, bores, slots, catches, and mouth recesses. |
| `src/vault/connectors.py` | Reusable stacking features, dimensions, and placements. |
| `src/vault/mating_features.py` | Dovetail, rail, and shallow-track constructors. |
| `src/vault/alignment_features.py` | Alignment tabs and locking bridge. |
| `src/vault/hook_features.py` | Outer hook and its compact entry blend. |
| `src/vault/reference.py` | Source registration and comparison regions. |
| `src/vault/validation.py` | Surface checks, mechanical regions, and cleanup probes. |

Dimensions are millimeters. Model X is width, Y is travel from the closed back
toward the opening, and Z is height. Size changes move or repeat mating
features instead of stretching their cross-sections:

- Depth is `42 * depth_units + 20.1`.
- Outside skin height is `48 * height_units - 1`; runners repeat every 48 mm.
- Widths: S 164.8, M 254.0, L 329.6, XL 418.8.
- S and M have one central connector bank. L has banks centered at X = −82.4
  and +82.4. XL has banks at −82.4 and +127.0.
- Front connectors/catches follow the opening; rear features follow the back.
  The side stopper follows `depth / 2 + 28.50005`.

The closed rear wall is 0.6 mm thick for two 0.3 mm layers when printed with
the back on the bed. This intentionally differs from the 2 mm reference wall.

Supplied drawer references cover depth units 3–7 and heights 1F, 2F, 4F
(XL: 1F only). Other generated depths/tier counts are extensions. This
constructor does not reproduce the separate sustainer, lid, or divider
products. Measurement evidence is in `research/size_catalog.json`,
`research/depth_connector_sections.json`, and `research/shell_depth_anchors.json`.

For example, changing bore clearance does not move its axis or alter box size:

```python
from dataclasses import replace
from vault.model import build_module
from vault.shell import ShellDimensions
from vault.spec import ModuleSpec

module = build_module(
    spec=ModuleSpec("S", depth_units=3, height_units=2),
    shell_dimensions=replace(ShellDimensions(), bore_radius=1.9),
)
```

Connector dimension sets are grouped in `ConnectorParameters`. Use
`dataclasses.replace` on the appropriate nested dimension set to edit a shared
feature. Construction and left/right/front/back placement are separate.
Fit dimensions remain nominal for PLA; no untested shrinkage correction is
applied. Physical fit still needs checking with a particular printer and PLA.

The superseded dense section tables are archived under
`research/legacy_profiles/`; none is an input to the current constructors.

## Symmetry

The common sleeve corners and paired connectors share definitions. The source
is not entirely mirror-symmetric:

- One runner has a lower mouth recess; the opposite runner has an upper recess.
  They are placed with a half-turn about the travel axis, with a small
  difference in their entry blends.
- Lower closed-end dovetails have a small notch-position difference.
- The original lower-left outside corner has a localized ~0.2 mm bulge. The
  clean symmetric envelope omits that non-mating irregularity.

![Original STL section showing the opposed runner recesses](research/mouth_pocket_section.png)

This actual triangle cross-section is 1 mm behind the opening, generated by
`research/mouth_pocket_section.py`. Positive model X is screen-left when
looking into the opening. Evidence is in `research/symmetry_audit.json`.

## STEP solids and review accuracy

Each build publishes `<size>.step` in model coordinates and
`<size>_print.step` with the closed back on the bed, plus native BREP,
`build.json`, the shared `manifest.json`, cyclone-style `viewer.json`, and
rendered `review/` images, and `stl/<module>.stl` for printing. The STL uses
the recorded print orientation and is validated as a closed, consistently oriented
mesh with positive volume. Its checksum is recorded in the immutable build manifest
and the viewer offers it under **Download STL**.

Both STEP exports are imported again before publishing. Like cyclone, the
round-trip checks require a valid solid and bounding-box error below 1e-4 mm.
Vault also requires one boundary shell. Its relative volume limit is 1e-5
(0.001%): the trimmed Vault surfaces show about 5.4e-6 drift after STEP
import across precision settings, exceeding cyclone’s 1e-7 limit.
Failed exports do not advance the latest-build pointers.

Rendering and reference comparisons tessellate the saved model-coordinate
STEP internally with absolute 0.05 mm chord and 0.5 radian angular settings,
with surface deflection control enabled. Temporary mesh interchange files
are removed after loading. This review mesh must be watertight, consistently
oriented, and agree with CAD volume within 0.1%. Cleanup removes only exact
collapsed/duplicate triangles or isolated defects within 0.005 mm without
moving vertices. STEP preserves native curves independently of review density.
Legacy STL builds remain readable by review commands.

## Validation

Comparison uses deterministic area samples plus vertices in both directions,
with exact point-to-triangle distances. It is a sampled comparison, not a proof
of maximum error at every point.

Default limits are 0.25 mm for retained surfaces, including the explicitly
simplified outside bulge/corner transitions, and 0.1 mm for mechanical regions:
connectors/tracks, cavity, runners, mouth recesses, bores, stopper slots,
catches, and rear reliefs. These stricter checks do not exclude anything from
the full comparison. Only requested decoration/groove removals are excluded
from source matching. Separate probes verify their flat replacements to 0.01 mm.

```bash
python -m vault validate --samples 100000 --tolerance 0.25 --mating-tolerance 0.1
python tools/plot_comparison.py
```

Results and worst points go to `comparison.json`; sampled points/distances go
to `comparison.npz`. Rebuilding invalidates old comparisons. Research reports
identify checked source/artifacts by hashes. `initial_export_validation.json`
belongs to the superseded detailed model.

## S1F facade and matching shadow line

`python -m vault build --part facade` builds the native S1F drawer facade
from `S1F (Turn On Supports).stl` measurements. `python -m vault build`
builds the corresponding S4 Module 1F. Both use the usual immutable build
storage and appear in the existing Vault viewer. The latest files are
`out/latest/s1f_facade/s1f_facade.step` and
`out/latest/s4_module_1f/s4_module_1f.step`.

The facade constructor is `src/vault/facade.py`; it uses native lofts, arcs,
extrusions and booleans, without loading the source mesh. It retains the
164.8 × 47 × 10 mm envelope, rear pockets, flat-sided screw bosses at
X=±51.45 / Z=23.5, 4.4 mm screw clearances, 10 mm counterbores, shaped finger
opening and shallow front-side recess. Curved blends are reconstructed
approximations. Small molded branding and front indexing marks are omitted,
consistent with the project's unbranded models. Run
`python tools/measure_facade.py` for a sampled, bidirectional source comparison;
its report includes the intended changes rather than hiding them. A successful
CAD export establishes solid validity, not exact source equivalence.

`ShadowGap` in `src/vault/shadow_gap.py` defines a **0.5 mm axial depth and
1 mm peripheral width on each mating face**. Together they form a 1 mm axial
shadow line, while the inner seating lands retain the original face positions.
The facade's rear seating plane is Y=0 and its front is Y=10. For a closed
assembly, translate it by (0, 188.1, 0) beside the S4 module. The module rebate
applies only to S4 1F; other module sizes retain their previous geometry.
Passing `shadow_gap=None` to `build_module` or `gap=None` to `build_facade`
builds an unrecessed part. Gap tests probe both rebates, preserved lands and
screw clearances. Physical fit has not been tested.

The facade's curved surfaces can require finer mesh resolution: tessellation
now retries at 0.01 mm if the default 0.05 mm mesh exceeds the existing 0.1%
CAD-volume tolerance. STEP remains independent of the mesh resolution.
