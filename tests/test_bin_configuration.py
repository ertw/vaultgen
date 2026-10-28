"""Bounded and canonical cell drawings remain independent of CAD imports."""
import unittest

from vault.bin_config import BinConfiguration, bin_catalog, bin_layout
from vault.gridfinity import GridfinityLayout
from vault.spec import ModuleSpec


class BinConfigurationTests(unittest.TestCase):
    def test_all_drawer_sizes_have_matching_whole_grid_and_safe_height(self):
        for family,columns in (('S',3),('M',5),('L',6)):
            for depth in range(3,8):
                for height in (1,2):
                    config = BinConfiguration(family,depth,height)
                    self.assertEqual((config.columns,config.rows),(columns,depth))
                    native_grid = GridfinityLayout(ModuleSpec(family,depth,height))
                    self.assertEqual((config.columns,config.rows),(native_grid.columns,native_grid.rows))
                    self.assertEqual(len(config.cells),columns*depth)
                    self.assertEqual(len(config.components),1)
                    # Thick-floor placement is the most restrictive drawer.
                    self.assertGreater(42.5+48*(height-1)-(8.25+config.height_mm),1)

    def test_components_use_edges_and_keep_holes_and_concave_shapes(self):
        config = BinConfiguration(cells=((0,0),(1,0),(0,1),(2,2)))
        self.assertEqual(config.components,(((0,0),(1,0),(0,1)),((2,2),)))
        ring = tuple((x,y) for y in range(3) for x in range(3) if (x,y)!=(1,1))
        self.assertEqual(len(BinConfiguration(cells=ring).components),1)

    def test_order_is_canonical_and_variants_have_distinct_build_keys(self):
        a = BinConfiguration(cells=((0,0),(1,0)),dividers=({'axis':'x','x':1,'y':0},))
        b = BinConfiguration.parse({**a.as_dict(),'cells':[[1,0],[0,0]]})
        self.assertEqual((a.key,a.as_dict()),(b.key,b.as_dict()))
        keys = {BinConfiguration.parse({**a.as_dict(),'wall_pattern':pattern,'wall_perimeters':lines}).key
                for pattern in ('plain','miura') for lines in (1,2)}
        self.assertEqual(len(keys),4)

    def test_rejects_invalid_cell_and_divider_input(self):
        invalid = [
            {'cells':[]}, {'cells':None}, {'cells':[[True,0]]}, {'cells':[[0.,0]]},
            {'cells':[[3,0]]}, {'cells':[[0,4]]}, {'cells':[[0,0],[0,0]]},
            {'family':'XL'}, {'depth_units':2}, {'depth_units':8}, {'depth_units':True},
            {'height_units':3}, {'height_units':False}, {'wall_perimeters':True},
            {'wall_perimeters':3}, {'wall_pattern':'waffle'}, {'unknown':True},
            {'cells':[[0,0]],'dividers':[{'axis':'x','x':1,'y':0}]},
            {'dividers':[{'axis':'x','x':0,'y':0}]},
            {'dividers':[{'axis':'z','x':1,'y':0}]},
            {'dividers':[{'axis':'x','x':True,'y':0}]},
            {'dividers':[{'axis':'x','x':1,'y':0,'extra':1}]},
            {'dividers':[{'axis':'x','x':1,'y':0}]*2},
        ]
        for payload in invalid:
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                BinConfiguration.parse(payload)

    def test_catalog_and_resolved_layout_expose_physical_choices(self):
        catalog = bin_catalog()
        self.assertEqual(catalog['wall_perimeters'],[1,2])
        self.assertEqual(catalog['dimensions']['nozzle_mm'],.6)
        self.assertEqual(catalog['dimensions']['wall_line_width_mm'],.65)
        self.assertEqual(bin_layout(BinConfiguration(wall_perimeters=1))['wall_thickness_mm'],.65)
        self.assertEqual(BinConfiguration.parse(catalog['defaults']).as_dict(),catalog['defaults'])

    def test_drawer_planning_grid_fills_native_cavity_and_matches_selected_floor(self):
        for family,columns,width in (('S',3,127.2),('M',4,216.4),('L',6,292.0)):
            for depth in range(3,8):
                for height in (1,2):
                    for floor in (.8,3.):
                        config = BinConfiguration(family,depth,height,container_type='drawer',drawer_floor=floor)
                        self.assertEqual((config.columns,config.rows),(columns,depth))
                        self.assertAlmostEqual(config.width_mm,width)
                        self.assertAlmostEqual(config.depth_mm,172.8+42*(depth-4))
                        self.assertAlmostEqual(config.pitch_x_mm*columns,config.width_mm)
                        self.assertAlmostEqual(config.pitch_y_mm*depth,config.depth_mm)
                        self.assertAlmostEqual(config.floor_top_mm,1.2)
                        self.assertEqual(config.foot_height_mm,0)
                        self.assertAlmostEqual(42.5+48*(height-1)-(5+floor+.25+config.height_mm),1.)
                        self.assertEqual(BinConfiguration.parse(config.as_dict()),config)

    def test_drawer_type_and_floor_have_distinct_canonical_identities(self):
        old = BinConfiguration()
        self.assertNotIn('container_type',old.as_dict())
        self.assertNotIn('drawer_floor',old.as_dict())
        self.assertEqual(BinConfiguration.parse(old.as_dict() | {'container_type':'gridfinity'}).key,old.key)
        thin = BinConfiguration(container_type='drawer')
        thick = BinConfiguration(container_type='drawer',drawer_floor=3)
        self.assertEqual(thick.key,BinConfiguration(container_type='drawer',drawer_floor=3.).key)
        self.assertEqual(len({old.key,thin.key,thick.key}),3)
        for change in ({'container_type':'unknown'},{'drawer_floor':0},
                       {'container_type':'drawer','drawer_floor':True},
                       {'container_type':'drawer','drawer_floor':1.2}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                BinConfiguration.parse(old.as_dict() | change)
        catalog = bin_catalog()
        self.assertEqual(len(catalog['drawer_layouts']),60)
        self.assertEqual(catalog['balanced_design'],{'wall_pattern':'miura','wall_perimeters':2})


if __name__ == '__main__':
    unittest.main()
