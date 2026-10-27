"""Tray integrity, breakaway supports, attachment clearance, and print placement."""
import unittest
from vault.box import SPEC, _runner_support, build_box, print_orientation
from vault.drawer import DrawerLayout
from vault.spec import ModuleSpec


def support_tooth_intervals(support):
    """Measure each tooth's bottom face independently of the spacing formula."""
    bottom = support.bounding_box().min.Z
    return sorted((face.bounding_box().min.Y, face.bounding_box().max.Y)
                  for face in support.faces()
                  if abs(face.bounding_box().min.Z-bottom) < 1e-7
                  and abs(face.bounding_box().max.Z-bottom) < 1e-7)


class BoxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box = build_box()

    def test_single_solid_and_envelope(self):
        self.assertTrue(self.box.is_valid)
        self.assertEqual(len(self.box.solids()), 1)
        self.assertEqual(len(self.box.shells()), 1)
        for actual, expected in zip(self.box.bounding_box().size, (134.2,185.8,37.5)):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertAlmostEqual(self.box.bounding_box().max.Y,188.1,places=5)
        self.assertEqual(SPEC.slug, 's4_box_1f')

    def test_open_tray_and_facade_attachment(self):
        self.assertTrue(self.box.is_inside((0,80,5.4)))
        self.assertFalse(self.box.is_inside((0,80,15)))
        self.assertFalse(self.box.is_inside((0,186,23.5)))
        for x in (-51.45,51.45):
            self.assertFalse(self.box.is_inside((x,183,23.5)))
            self.assertTrue(self.box.is_inside((x+3,183,23.5)))
            self.assertTrue(self.box.is_inside((x,3.5,23.5)))

    def test_thin_floor_and_reinforcing_inside_fillet(self):
        # Outside bottom is Z5; the flat interior floor is Z5.8.
        for x, y in ((0, 80), (-52.9, 39.53), (40, 160)):
            self.assertTrue(self.box.is_inside((x, y, 5.79)))
            self.assertFalse(self.box.is_inside((x, y, 5.81)))
        for x, y in ((63.5, 80), (-63.5, 80), (0, 5.4), (40, 181.4)):
            self.assertTrue(self.box.is_inside((x, y, 6.2)))
            self.assertFalse(self.box.is_inside((x, y, 6.9)))
        self.assertFalse(self.box.is_inside((62.5, 80, 5.9)))

    def test_runner_backing_walls_are_1_3_mm(self):
        for sign in (-1, 1):
            for y in (40, 100, 170):
                for z in (20, 23.5, 27):
                    self.assertFalse(self.box.is_inside((sign*63.59,y,z)))
                    self.assertTrue(self.box.is_inside((sign*63.61,y,z)))
                    self.assertTrue(self.box.is_inside((sign*64.89,y,z)))
                    self.assertFalse(self.box.is_inside((sign*64.91,y,z)))
            # The original front attachment land still begins at Y181.5.
            self.assertFalse(self.box.is_inside((sign*51.45,181.49,20)))
            self.assertTrue(self.box.is_inside((sign*51.45,181.51,20)))

    def test_closed_pockets_keep_continuous_walls_at_front_corners(self):
        # The selected defect was at X65.943/Y187.2/Z6.61..11.89:
        # a rounded outside corner broke through a rectangular closed pocket.
        # Source front corners are square in plan, with a retained side wall
        # and front rim; only the opposite diagonal has external gear exits.
        for sign, z in ((1, 9), (-1, 38)):
            for y in (183, 185.5, 186.9, 187.1, 187.19):
                self.assertTrue(self.box.is_inside((sign*66.7, y, z)))
                self.assertFalse(self.box.is_inside((sign*65, y, z)))
            self.assertTrue(self.box.is_inside((sign*66.7, 187.7, z)))

    def test_linear_gear_passages_exit_on_opposed_outer_corners(self):
        # Source tray sections show -X/lower and +X/upper exits. Follow each
        # passage from the central opening through the full outside wall.
        for sign, z in ((-1, 8), (1, 39)):
            for x in (23, 40, 60, 66.8, 67.05):
                for y in (183, 185.5, 187.1):
                    with self.subTest(side=sign, x=x, y=y):
                        self.assertFalse(self.box.is_inside((sign*x, y, z)))
            self.assertTrue(self.box.is_inside((-sign*66.8, 185.5, z)))

    def test_upper_closed_pocket_keeps_wall_below_exterior_chamfer(self):
        for radius in (0, .8, 1):
            box = self.box if radius == .8 else build_box(gear_corner_radius=radius)
            for y in (183.8, 185, 186.2):
                # Sample just inside the chamfer over the former breakthrough.
                for z in (41, 41.5, 41.85):
                    x = -(107.6-z-.1)  # exterior: |X|+Z=107.6 after registration
                    self.assertTrue(box.is_inside((x,y,z)))
                self.assertFalse(box.is_inside((-65, y, 39)))
                self.assertFalse(box.is_inside((-64, y, 41.5)))

    def test_gear_channel_rounds_support_roofs_without_closing_passages(self):
        sharp = build_box(gear_corner_radius=0)
        # The added corner material is at the selected upper edge and its
        # matching channel edges, on both the rear and front of the pocket.
        for x, floor, roof in ((60,35.193,40.393), (-60,6.607,11.807),
                               (60,6.61,11.89), (-60,35.11,41.86)):
            for y in (182.85,187.15):
                for z in (floor+.05,roof-.05):
                    self.assertFalse(sharp.is_inside((x,y,z)))
                    self.assertTrue(self.box.is_inside((x,y,z)))
            self.assertFalse(self.box.is_inside((x,185,(floor+roof)/2)))
        self.assertGreater(self.box.volume, sharp.volume)

    def test_linear_gear_exits_retain_rounded_lips_roof_and_front_rim(self):
        # R1 rolled lips widen the exit below/above the straight gear slot.
        for x, y, z in ((66.8, 185.5, 35.1), (-66.8, 183.3, 11.9)):
            self.assertFalse(self.box.is_inside((x, y, z)))
        for x, y, z in ((66.8, 185.5, 34.7), (-66.8, 183.3, 12.3)):
            self.assertTrue(self.box.is_inside((x, y, z)))
        # The upper clearance has a rounded raised center and solid shoulders;
        # a plain taller rectangle would erase both shoulders and the roof.
        self.assertFalse(self.box.is_inside((65, 185, 41.6)))
        self.assertTrue(self.box.is_inside((65, 183, 41.6)))
        self.assertFalse(self.box.is_inside((65, 183.9, 41.5)))
        self.assertTrue(self.box.is_inside((65, 183.9, 41.8)))
        self.assertTrue(self.box.is_inside((65, 185, 42.2)))
        for x, z in ((65, 38), (-65, 9)):
            for y in (182.4, 187.6):
                self.assertTrue(self.box.is_inside((x, y, z)))

    def test_lower_gear_roofs_have_rounded_bridge_relief(self):
        # Both halves of the lower passage need headroom above the rail.
        # The upper profile supplies a 1.516 mm rise and 0.8 mm flat crown;
        # curved shoulders keep the original front and rear walls intact.
        for x, floor, roof in ((-60, 6.607, 11.807), (60, 6.61, 11.89)):
            with self.subTest(x=x):
                for y in (184.7, 185, 185.3):
                    self.assertFalse(self.box.is_inside((x, y, roof+1.5)))
                    self.assertTrue(self.box.is_inside((x, y, roof+1.54)))
                # These points distinguish the rounded crown from a raised
                # rectangle and from an arch inverted into the channel floor.
                for y in (183.9, 186.1):
                    self.assertFalse(self.box.is_inside((x, y, roof+1.2)))
                    self.assertTrue(self.box.is_inside((x, y, roof+1.4)))
                for y in (183.3, 186.7):
                    self.assertTrue(self.box.is_inside((x, y, roof+.2)))
                for y in (182.4, 187.6):
                    for z in (floor+.5, roof+.6):
                        self.assertTrue(self.box.is_inside((x, y, z)))
                self.assertTrue(self.box.is_inside((x, 185, floor-.02)))
                self.assertFalse(self.box.is_inside((x, 185, floor+.02)))
        # Relief reaches the open exit, but the blind pocket's fixed stop
        # remains a closed wall at the rail's original installation datum.
        self.assertFalse(self.box.is_inside((-67.05, 185, 13)))
        for z in (9, 13):
            self.assertFalse(self.box.is_inside((66.29, 185, z)))
            self.assertTrue(self.box.is_inside((66.31, 185, z)))

    def test_runner_channels_and_print_bed(self):
        for sign in (-1,1):
            self.assertFalse(self.box.is_inside((sign*65.4,80,23.5)))
            self.assertTrue(self.box.is_inside((sign*66.15,80,23.5)))
        printed=print_orientation(self.box)
        self.assertAlmostEqual(printed.bounding_box().min.Z,0,places=6)
        self.assertAlmostEqual(printed.volume,self.box.volume,places=5)

    def test_runner_flank_clearance_preserves_channel_depth(self):
        nominal = build_box(runner_clearance=0)
        for sign in (-1, 1):
            for z in (17.6, 29.4):
                point = (sign*65.4,80,z)
                self.assertTrue(nominal.is_inside(point))
                self.assertFalse(self.box.is_inside(point))
            self.assertTrue(self.box.is_inside((sign*64.85,80,23.5)))
            self.assertFalse(self.box.is_inside((sign*64.95,80,23.5)))

    def test_lock_floor_opening_matches_original_lower_bevel(self):
        # Registered source sections: Y = 177.1 + (Z - 5), across
        # the central opening. Preserve the adjacent attachment lands.
        for x in (-22.7, 0, 22.7):
            for z in (5.1,5.4,5.7):
                edge_y = 177.1 + z - 5
                self.assertTrue(self.box.is_inside((x,edge_y-.05,z)))
                self.assertFalse(self.box.is_inside((x,edge_y+.05,z)))
            self.assertFalse(self.box.is_inside((x,180,5.4)))
        for x in (-25,25):
            self.assertTrue(self.box.is_inside((x,180,5.4)))

    def test_runner_teeth_carry_the_sheet_between_both_channel_lips(self):
        # Sample the first and last teeth as well as teeth along the channel.
        # A continuous connection at each tooth supports the first sheet layers
        # and the roof while the narrow gaps between teeth permit removal.
        intervals = support_tooth_intervals(_runner_support(1))
        selected = (0, len(intervals)//4, len(intervals)//2, len(intervals)-1)
        for sign in (-1, 1):
            for index in selected:
                y = sum(intervals[index])/2 + 2.3
                with self.subTest(side=sign, tooth_y=y):
                    for z in (18, 18.55, 19.2, 23.5, 28.4, 28.6, 28.9):
                        self.assertTrue(self.box.is_inside((sign*66.15, y, z)))
            for index in (0, len(intervals)//4, len(intervals)//2, len(intervals)-2):
                y = (intervals[index][1]+intervals[index+1][0])/2 + 2.3
                with self.subTest(side=sign, gap_y=y):
                    self.assertFalse(self.box.is_inside((sign*66.15, y, 18.55)))
                    self.assertTrue(self.box.is_inside((sign*66.15, y, 23.5)))
                    self.assertFalse(self.box.is_inside((sign*66.15, y, 28.6)))

    def test_runner_support_shortens_bridges_and_keeps_end_contacts_at_every_depth(self):
        for depth in range(3, 8):
            layout = DrawerLayout(ModuleSpec('S', depth))
            for sign in (-1, 1):
                with self.subTest(depth=depth, side=sign):
                    support = _runner_support(sign, layout=layout)
                    self.assertTrue(support.is_valid)
                    self.assertEqual(len(support.solids()), 1)
                    self.assertAlmostEqual(support.bounding_box().size.X, .5)
                    intervals = support_tooth_intervals(support)
                    self.assertAlmostEqual(intervals[0][0], 28.7)
                    self.assertAlmostEqual(intervals[-1][1], 183.95+layout.depth_delta)
                    for start, end in intervals:
                        self.assertAlmostEqual(end-start, .7)
                    for previous, following in zip(intervals, intervals[1:]):
                        self.assertLessEqual(following[0]-previous[0], 7.5+1e-7)
                        self.assertLessEqual(following[0]-previous[1], 6.8+1e-7)
                    if depth == 4:
                        self.assertGreater(len(intervals), 18)

    def test_runner_support_leaves_its_back_and_ends_clear(self):
        for sign in (-1, 1):
            # The half-mm sheet stays on the outside of the runner recess;
            # teeth must not fill the functional channel behind it.
            for y in (31.35, 36, 113.2, 185.9):
                self.assertFalse(self.box.is_inside((sign*65.4, y, 23.5)))
            for x in (65.8, 66.5):
                self.assertFalse(self.box.is_inside((sign*x, 80, 23.5)))
            for y in (29.5, 187.5):
                self.assertFalse(self.box.is_inside((sign*66.15, y, 23.5)))

    def test_rear_wall_is_solid_across_former_circles_and_oval(self):
        for x in (-56, -51.45, -47, -21, -18, -10.4, -6, 0,
                  6, 10.4, 18, 21, 47, 51.45, 56):
            for y in (2.6, 3.8, 5):
                for z in (18.3, 20, 23.5, 27, 28.7):
                    with self.subTest(x=x, y=y, z=z):
                        self.assertTrue(self.box.is_inside((x, y, z)))
        for x in (-51.45, 0, 51.45):
            self.assertFalse(self.box.is_inside((x, 6, 23.5)))
