# Two-piece snap-fit key

`src/vault/key_geometry.py` reconstructs the supplied `Key (Turn On Supports).stl`
with native curves. `src/vault/key.py` separates the gear from the handle at the
flat underside of the locating flange, 7.4 mm above the original base, and adds
the joint. Source STL files are used only by the comparison tool.

Build the print files, editable STEP files, and assembled/exploded previews:

```sh
source .local-env
python -m vault.key_build
```

The checked build is published under `out/latest/snap_key/`. Print **one each**
of `stl/key_gear.stl` and `stl/key_handle.stl`. Each STL already rests on Z=0:
the gear stands on its original oval base, and the handle stands on the flat
underside of its locating flange. Keep these orientations and disable supports.
The assembled STEP is for inspection, not a print-in-place model.

Use a 0.4 mm nozzle and 0.2 mm layers as a starting point, with four perimeters.
The design assumes PETG for the flexible catches; its toughness, layer adhesion,
and flexibility are described in the [Prusa PETG guide](https://help.prusa3d.com/article/petg_2059).
Printer-specific fit, retention force, and fatigue have not been physically
tested. Keep brim, stringing, and elephant foot out of the joint.

Align the clipped corner of the gear's drive boss with the handle socket, then
press the gear upward into the handle until both catches engage and the flange
seats against the gear shoulder. The rectangular boss transfers turning force;
the two flexible arms retain the assembly. The clipped corner prevents reversed
assembly. Small openings at the handle ends expose the catches.

The default clearance is **0.20 mm per side**. The flexible arms are 1.2 mm thick
and 4 mm wide, with rounded roots and sloped hook lead-ins. The hooks protrude
0.6 mm, requiring nominal 0.4 mm inward travel at the default clearance. The
assembled joint has 0.15 mm axial catch clearance. Internal roofs close at
45 degrees to avoid large blind-pocket bridges. Original small exterior rounds
remain, so inspect the slicer's first layers and overhang preview.

If a first print needs a fit adjustment, regenerate both pieces together:

```sh
python -m vault.key_build --clearance 0.25
```

The supported adjustment range is 0.10–0.30 mm per side. Larger values loosen
the drive fit and reduce catch engagement. The source scale and gear pitch stay
unchanged.

Geometry checks:

```sh
python -m unittest discover -s tests -p 'test_key_*.py' -v
python tools/check_key_reference.py
```

Export checks require two valid solids, one shell per part, no assembled
interference, closed STL meshes, and STEP round-trip agreement. The reference
report compares the original exterior before adding the intentional joint;
underside branding is omitted and the grip blend is regularized. The wing's
rounded junctions are reconstructed with native curves, and small localized
bumps on the original circular rim are replaced by the nominal smooth ring.
The reference audit keeps its strict 0.1 mm whole-region target and reports
these differences; its acceptance flag is separate from export validity.
Gear flank, locating flange, and indexing-tab diagnostic bands are also
reported separately. The delivered model's sampled maxima are 0.0089 mm at
the gear flanks, 0.0276 mm at the locating flange, and 0.0091 mm at the tabs.
The wing junction differs by up to 0.1723 mm and the rim bumps by 0.1265 mm,
so the strict 0.1 mm whole-region reference check is **not passed**. All eleven
joint/export tests and the saved STL/STEP validity checks pass. Sampled
surface comparisons do not establish a maximum error everywhere or prove
physical operation with the drawer mechanism.
