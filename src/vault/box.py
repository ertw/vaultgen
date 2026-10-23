"""Native S4 drawer tray in module coordinates; source meshes are not build inputs.

Measured nominal dimensions from S4 Box 1F.stl. The front seating plane is
Y=188.1 and screw axes coincide with the S1F facade. Small source blends,
branding, and the thin bridge across the rear opening are simplified.
"""
from dataclasses import dataclass
from build123d import Solid, Wire, Face, Plane
from .shell import _rounded_rect


@dataclass(frozen=True)
class BoxSpec:
    family: str = 'S'
    depth_units: int = 4
    height_units: int = 1

    @property
    def name(self): return 'S4 Box 1F'

    @property
    def slug(self): return 's4_box_1f'


SPEC = BoxSpec()


def block(x0, y0, z0, x1, y1, z1):
    return Solid.make_box(x1-x0, y1-y0, z1-z0, Plane(origin=(x0,y0,z0)))


def profile(points, y, length):
    return Solid.extrude(Face(Wire.make_polygon([(x,y,z) for x,z in points], close=True)), (0,length,0))


def build_box():
    # Construct at the measurement datum, then register to the sleeve/facade.
    outside = _rounded_rect(-67.1,0,67.1,185.8,3.5,lambda x,y:(x,y,6))
    part = Solid.extrude(outside,(0,0,37.5))
    cavity = _rounded_rect(-62.9,3,62.9,179.2,3.5,lambda x,y:(x,y,9))
    part = part.cut(Solid.extrude(cavity,(0,0,40)))
    part = part.cut(block(-22.877,178.9,5,22.877,187,45))
    # Chamfered outside edges and opposed runner channels. The thin spring
    # strips connect at each end of the channel, rather than floating solids.
    for sign in (-1,1):
        for pts in [[(65.1,6),(67.2,6),(67.2,8.1)],
                    [(65.1,43.5),(67.2,41.4),(67.2,43.6)]]:
            part = part.cut(profile([(sign*x,z) for x,z in pts],-1,188))
        channel=[(64.9,18.254),(66.2,19.32),(67.3,18.7),
                 (67.3,30.3),(66.2,29.68),(64.9,30.746)]
        part = part.cut(profile([(sign*x,z) for x,z in channel],25.8,161))
        x0,x1=sorted((sign*65.9,sign*66.4))
        strip=block(x0,27.5,20.105,x1,185.3,29.483)
        for y in (26,184.64):
            a,b=sorted((sign*64.8,sign*66.4))
            strip=strip.fuse(block(a,y,20.105,b,min(y+2,185.8),29.483))
        part=part.fuse(strip)
        # Opposed upper/lower attachment recesses; central land carries screw.
        a,b=sorted((sign*22.877,sign*66.3))
        for z0,z1 in ((7.61,12.89),(36.11,42.86)):
            part=part.cut(block(a,180.5,z0,b,184.9,z1))
        x=sign*51.45
        part=part.cut(Solid.make_cylinder(1.8,12,Plane(origin=(x,175,24.5),z_dir=(0,1,0))))
        part=part.cut(Solid.make_cylinder(5.5,5,Plane(origin=(x,-1,24.5),z_dir=(0,1,0))))
    rear_slot=_rounded_rect(-22.65,19,22.65,30,5.49,lambda x,z:(x,-1,z))
    part=part.cut(Solid.extrude(rear_slot,(0,5,0)))
    part=part.translate((0,2.3,-1))
    part.label=SPEC.name + ' — unbranded'
    if not part.is_valid or len(part.solids()) != 1 or len(part.shells()) != 1:
        raise ValueError('Expected one valid box solid with one boundary shell')
    return part


def print_orientation(part):
    """Print the tray flat on its closed bottom."""
    return part.translate((0,0,-part.bounding_box().min.Z))
