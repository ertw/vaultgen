# Single-piece key

The key is one native solid with an integrated drive pinion. `key_geometry.py`
constructs the gear and handle and fuses them; `key.py` supplies the printable
part. There is no separate socket, catch, or assembly operation.

```sh
source .local-env
python -m vault.key_build
```

The checked build is published through immutable storage under
`out/latest/snap_key/`; the historical catalog identifier is retained for
compatibility. Print one `stl/key.stl` per drawer, gear bottom on the bed.
Check overhangs and support needs in the slicer and verify printed fit.
The export pipeline checks solid validity, STEP round trips and watertight
print meshes. These checks do not establish printed fit or torque capacity.

Existing two-piece builds remain immutable historical artifacts. New builds
use the single-piece geometry. Purchased meshes remain local comparison inputs
and are never construction inputs or downloadable assets.
