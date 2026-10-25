"""Assemble an unbranded Vault drawer module from native build123d features.

Axes: X across the drawer, Y from the closed back to the open front, Z upward.
The three decorative ovals, branding, alignment text/arrow, raised S4 marking,
and transverse alignment groove are absent. Construction uses reusable analytic
features; it does not import an STL, BREP, or measured profile table.
"""
from collections.abc import Callable

from build123d import Axis, Shape

from .connectors import ConnectorParameters, add_connectors
from .shell import DEFAULT_DIMENSIONS, ShellDimensions, build_shell
from .spec import ModuleSpec, DEFAULT_SPEC
from .shadow_gap import DEFAULT_GAP, ShadowGap, perimeter_rebate


def build_module(
    spec: ModuleSpec = DEFAULT_SPEC,
    shell_dimensions: ShellDimensions = DEFAULT_DIMENSIONS,
    connector_parameters: ConnectorParameters = ConnectorParameters(),
    progress: Callable[[str], None] | None = None,
    shadow_gap: ShadowGap | None = DEFAULT_GAP,
    *,
    include_supports: bool = True,
) -> Shape:
    """Build one valid solid, with independently editable mating features.

    Size determines feature placement and runner repetition. Feature dimensions
    stay nominal unless explicitly changed; no material shrink correction is
    applied. Use dataclasses.replace on a nested feature's dimension set to edit
    its profile without duplicating the left/right construction.
    ``progress`` receives status messages during construction, if supplied.
    Set ``include_supports=False`` for the finished assembly geometry after
    removing the sacrificial runner-mouth webs. Printable builds retain them.
    """
    if progress is not None:
        progress('Building sleeve, drawer runners, and retention details')
    if shell_dimensions is DEFAULT_DIMENSIONS:
        from dataclasses import replace
        shell_dimensions = replace(shell_dimensions, back_wall=spec.module_rear)
    if not include_supports:
        from dataclasses import replace
        shell_dimensions = replace(shell_dimensions, pocket_support_thickness=0)
    shell = build_shell(spec=spec, dimensions=shell_dimensions)
    part = add_connectors(shell, spec=spec, parameters=connector_parameters, progress=progress)
    if shadow_gap is not None:
        part = perimeter_rebate(part, spec.depth, -1, spec, shadow_gap)
    part.label = f'{spec.name} — unbranded'
    if not part.is_valid:
        raise ValueError('Reconstructed module is not a valid CAD shape')
    solid_count = len(part.solids())
    if solid_count != 1:
        raise ValueError(f'Expected one connected solid, got {solid_count}')
    if len(part.shells()) != 1:
        raise ValueError('The open sleeve must have one boundary shell, with no internal shells')
    return part


def print_orientation(part: Shape) -> Shape:
    """Rotate a model-coordinate shape so its closed back lies on the plate."""
    return part.rotate(Axis.X, 90)
