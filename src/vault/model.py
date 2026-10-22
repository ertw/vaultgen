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


def build_module(
    spec: ModuleSpec = DEFAULT_SPEC,
    shell_dimensions: ShellDimensions = DEFAULT_DIMENSIONS,
    connector_parameters: ConnectorParameters = ConnectorParameters(),
    progress: Callable[[str], None] | None = None,
) -> Shape:
    """Build one valid solid, with independently editable mating features.

    Size determines feature placement and runner repetition. Feature dimensions
    stay nominal unless explicitly changed; no material shrink correction is
    applied. Use dataclasses.replace on a nested feature's dimension set to edit
    its profile without duplicating the left/right construction.
    ``progress`` receives status messages during construction, if supplied.
    """
    if progress is not None:
        progress('Building sleeve, drawer runners, and retention details')
    shell = build_shell(spec=spec, dimensions=shell_dimensions)
    part = add_connectors(shell, spec=spec, parameters=connector_parameters, progress=progress)
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
