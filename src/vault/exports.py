"""Verify native STEP solids using the cyclone export round-trip checks."""


def precise_volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, properties, 1e-10, True, False)
    return properties.Mass()


def check_step(original, path):
    from build123d import import_step
    restored = import_step(path)
    volume = precise_volume(original)
    restored_volume = precise_volume(restored)
    delta = abs(restored_volume - volume) / max(abs(volume), 1.)
    before, after = original.bounding_box(), restored.bounding_box()
    bounds_delta = max(abs(a - b) for a, b in zip(
        (*before.min, *before.max), (*after.min, *after.max)))
    # Vault's trimmed surfaces shift volume by about 5.4e-6 on STEP import,
    # including with tighter integration and every STEP precision mode.
    # Allow 0.001% while retaining the strict spatial and topology checks.
    passed = (restored.is_valid and len(restored.solids()) == 1
              and len(restored.shells()) == 1 and volume > 0 and restored_volume > 0
              and delta < 1e-5 and bounds_delta < 1e-4)
    report = {'passed': bool(passed), 'volume_relative_error': delta,
              'volume_relative_tolerance': 1e-5, 'bbox_max_error_mm': bounds_delta}
    if not passed:
        raise ValueError(f'STEP round-trip failed for {path.name}: {report}')
    return restored, report
