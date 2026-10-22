"""Place and join reusable analytic Vault stacking connectors.

Module size changes placement, bank repetition, and rail travel length. Each
mating cross-section stays nominal unless its dimensional dataclass is edited.
No STL, measured section table, or saved CAD shape is read by this module.
"""
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from math import isfinite

from build123d import Plane, Shape, Solid
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.collections import List_TopoDS_Shape

from .alignment_features import (
    LockingBridgeDimensions, LowerTabDimensions, UpperTabDimensions,
    lower_alignment_tab, upper_alignment_tab, upper_closed_end_locking_bridge,
)
from .hook_features import LowerHookDimensions, lower_outer_hook
from .mating_features import (
    LowerClosedDovetailDimensions, LowerOpenDovetailDimensions,
    UpperOpenDovetailDimensions, UpperRailDimensions, TrackDimensions,
    lower_closed_end_dovetail, lower_open_end_dovetail, lower_central_dovetail,
    upper_open_end_dovetail, upper_outer_rail, upper_track_cutter,
)
from .spec import DEFAULT_SPEC, ModuleSpec


Progress = Callable[[str], None]


@dataclass(frozen=True)
class ConnectorParameters:
    """Nominal mating dimensions; use dataclasses.replace for an explicit edit.

    The right closed-end notch is 0.1927 mm farther inward in the purchased
    source. The shared builder retains that one handed dimension. Other paired
    features share a mirrored nominal profile; their source asymmetries are
    included in the final surface comparison.
    """
    lower_closed_dovetail: LowerClosedDovetailDimensions = LowerClosedDovetailDimensions()
    lower_open_dovetail: LowerOpenDovetailDimensions = LowerOpenDovetailDimensions()
    upper_open_dovetail: UpperOpenDovetailDimensions = UpperOpenDovetailDimensions()
    upper_rail: UpperRailDimensions = UpperRailDimensions()
    lower_hook: LowerHookDimensions = LowerHookDimensions()
    lower_tab: LowerTabDimensions = LowerTabDimensions()
    upper_tab: UpperTabDimensions = UpperTabDimensions()
    locking_bridge: LockingBridgeDimensions = LockingBridgeDimensions()
    track: TrackDimensions = TrackDimensions()
    right_closed_notch_offset: float = .1927

    def __post_init__(self):
        if not isfinite(self.right_closed_notch_offset):
            raise ValueError("right_closed_notch_offset must be finite")


def _boolean(base: Shape, tools: Sequence[Shape], operation, *, parallel=False) -> Solid:
    """Run a native boolean, retaining the analytic faces without global merging."""
    arguments, operands = List_TopoDS_Shape(), List_TopoDS_Shape()
    arguments.Append(base.wrapped)
    for tool in tools:
        operands.Append(tool.wrapped)
    builder = operation()
    builder.SetArguments(arguments)
    builder.SetTools(operands)
    builder.SetRunParallel(parallel)
    builder.SetNonDestructive(True)
    builder.Build()
    if not builder.IsDone() or builder.Shape().IsNull():
        raise RuntimeError("Native connector boolean failed")
    result = Shape.cast(builder.Shape())
    solids = result.solids()
    if len(solids) != 1 or not result.is_valid:
        raise RuntimeError(f"Connector boolean produced {len(solids)} solids or invalid topology")
    return solids[0]


def adaptive_volume(shape: Shape) -> float:
    """Accurate native volume, also useful when comparing custom feature edits."""
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, properties, 1e-7, False, False)
    return properties.Mass()


def build_connectors(
    spec: ModuleSpec = DEFAULT_SPEC,
    parameters: ConnectorParameters = ConnectorParameters(),
    progress: Progress | None = None,
) -> list[Solid]:
    """Build placed additive features; every named result is one valid solid."""
    p = parameters
    if progress:
        progress("Building reusable mating profiles")
    closed_left = lower_closed_end_dovetail(p.lower_closed_dovetail)
    closed_right = lower_closed_end_dovetail(replace(
        p.lower_closed_dovetail,
        notch_x=p.lower_closed_dovetail.notch_x+p.right_closed_notch_offset,
    ))
    lower_carrier = lower_open_end_dovetail(p.lower_open_dovetail)
    lower_center = lower_central_dovetail(p.lower_open_dovetail)
    upper_carrier = upper_open_end_dovetail(p.upper_open_dovetail)
    lower_tab = lower_alignment_tab(p.lower_tab)
    upper_tab = upper_alignment_tab(p.upper_tab)
    bridge = upper_closed_end_locking_bridge(p.locking_bridge)
    result = []

    def add(name, solid, bank=0):
        solid = solid.translate((bank,0,0))
        solid.label = name
        result.append(solid)

    def pair(name, local, placement, bank=0, suffix="", right_local=None):
        left = local.translate(placement)
        right = (local if right_local is None else right_local).translate(placement).mirror(Plane.YZ)
        add(name+"_left"+suffix,left,bank)
        add(name+"_right"+suffix,right,bank)

    # Central connector banks repeat on wider families; all offsets are from
    # either the closed end or the open end, never scaled with drawer size.
    for index,bank in enumerate(spec.bank_centers):
        suffix = f"_bank_{index+1}" if len(spec.bank_centers)>1 else ""
        pair("lower_closed_end_dovetail",closed_left,(-56.6006,0,0),bank,suffix,closed_right)
        pair("lower_alignment_tab",lower_tab,(-15.1309,0,0),bank,suffix)
        pair("lower_open_end_dovetail",lower_carrier,(-57.6016,spec.depth-12.1258,0),bank,suffix)
        add("lower_open_end_dovetail_center"+suffix,lower_center.translate((0,spec.depth-12.1258,0)),bank)
        pair("upper_open_end_dovetail",upper_carrier,(-23,spec.depth-13,spec.height),bank,suffix)
        pair("upper_alignment_tab",upper_tab,(-15.1318,15.288,spec.height),bank,suffix)
        add("upper_closed_end_locking_bridge"+suffix,bridge.translate((0,0,spec.height)),bank)

    # The four outer features follow the actual outside walls, regardless of
    # how many central banks the family contains.
    rail_start,rail_setback = 7.9786,12.0
    rail = upper_outer_rail(p.upper_rail,length=spec.depth-rail_start-rail_setback)
    pair("upper_outer_rail",rail,(-spec.half_width,rail_start,spec.height))
    pair("lower_outer_hook",lower_outer_hook(p.lower_hook),(-spec.half_width,spec.depth,0))
    return result


def build_connector_cutters(
    spec: ModuleSpec = DEFAULT_SPEC,
    parameters: ConnectorParameters = ConnectorParameters(),
) -> list[Solid]:
    """Place a mirrored pair of shallow mechanical tracks per connector bank."""
    cutter = upper_track_cutter(parameters.track)
    result = []
    for bank in spec.bank_centers:
        for side in (-1,1):
            result.append(cutter.translate((bank+side*45.4814,spec.depth-55.3015,spec.height)))
    return result


def add_connectors(
    shell: Shape,
    spec: ModuleSpec = DEFAULT_SPEC,
    parameters: ConnectorParameters = ConnectorParameters(),
    progress: Progress | None = None,
) -> Solid:
    """Cut the shallow tracks, then join the analytic features to the skins."""
    if progress:
        progress("Cutting shallow mechanical tracks")
    shell = _boolean(shell,build_connector_cutters(spec,parameters),BRepAlgoAPI_Cut)
    connectors = build_connectors(spec,parameters,progress)
    if progress:
        progress(f"Attaching {len(connectors)} mating features")
    result = _boolean(shell,connectors,BRepAlgoAPI_Fuse,parallel=True)
    if progress:
        progress("Connector assembly complete")
    return result
