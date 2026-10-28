"""Native editable floor topology, separators, feet and measured Miura walls."""
import unittest
import hashlib
import json
import tempfile
from pathlib import Path

from vault.bin import bin_foot, build_bins
from vault.bin_config import BinConfiguration
from tools.check_gridfinity_bins import (intersection_volume, junction_layer_samples,
                                         load_build_parts, normal_wall_samples)


def ray_crossings(part, origin, direction, distance):
    """Cross a local wall in the actual solid, independent of its face layout."""
    from build123d import Axis
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.gp import gp_Lin
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(part.wrapped, 1e-6)
    intersector.Perform(gp_Lin(Axis(origin,direction).wrapped),0.,distance)
    result = []
    for value in sorted(intersector.WParameter(i) for i in range(1,intersector.NbPnt()+1)):
        if not result or value-result[-1] > 1e-5:
            result.append(value)
    return result


class BinGeometryTests(unittest.TestCase):
    def test_saved_print_steps_restore_recorded_cell_placement_and_verify_checksums(self):
        from build123d import Solid, export_step
        from vault.exports import translation_matrix
        config = BinConfiguration(cells=((0,0),(2,2)))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            checksums, metadata = {}, {'gridfinity_configuration':config.as_dict(), 'parts':{}}
            for index,offset in enumerate(((.25,.25,0.),(84.25,84.25,0.)),1):
                name = f'bin_{index:02d}'
                path = directory/f'{name}_print.step'
                export_step(Solid.make_box(2.,3.,4.),path)
                checksums[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                metadata['parts'][name] = {'kind':'gridfinity_bins', 'assembly_mesh':{
                    'coordinates':'native', 'print_to_native':translation_matrix(offset)}}
            path = directory/'build.json'
            path.write_text(json.dumps(metadata))
            checksums[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            (directory/'manifest.json').write_text(json.dumps({
                'schema':'cad-build-v1', 'passed':True, 'build_id':'test-build',
                'source_hash':'test-source', 'configuration_hash':config.key,
                'checksums':checksums}))
            restored, parts, evidence = load_build_parts(directory)
            self.assertEqual(restored,config)
            self.assertAlmostEqual(parts['bin_01'].bounding_box().min.X,.25)
            self.assertAlmostEqual(parts['bin_02'].bounding_box().min.Y,84.25)
            self.assertEqual(len(evidence['step_inputs']),2)
            with (directory/'bin_02_print.step').open('a') as handle:
                handle.write('\nchanged\n')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                load_build_parts(directory)

    def test_nominal_foot_sections_preserve_gridfinity_clearance(self):
        foot = bin_foot()
        for z,width in ((.4,36.4),(1.7,37.2),(3.6,39.2)):
            self.assertTrue(foot.is_inside((width/2-.01,0,z)))
            self.assertFalse(foot.is_inside((width/2+.01,0,z)))
        self.assertAlmostEqual(foot.bounding_box().max.Z,4.75,places=6)

    def test_concave_connected_cells_share_cavity_and_separate_islands(self):
        config = BinConfiguration(cells=((0,0),(1,0),(0,1),(2,2)),wall_perimeters=1,
                                  dividers=({'axis':'x','x':1,'y':0},))
        parts = build_bins(config)
        self.assertEqual(list(parts),['bin_01','bin_02'])
        first,second = parts.values()
        for part in parts.values():
            self.assertTrue(part.is_valid)
            self.assertEqual((len(part.solids()),len(part.shells())),(1,1))
        self.assertTrue(first.is_inside((42,21,15)))  # painted divider
        self.assertFalse(first.is_inside((21,42,15)))  # unpainted edge is open
        self.assertTrue(first.is_inside((21,42,6)))  # shared floor bridges feet
        self.assertFalse(first.is_inside((63,63,6)))  # concave missing cell
        self.assertLess(intersection_volume(first,second),1e-6)
        self.assertTrue(all(sample['passed'] for sample in normal_wall_samples(first,config)))

    def test_hole_keeps_its_own_walls_and_open_center(self):
        cells = tuple((x,y) for y in range(3) for x in range(3) if (x,y)!=(1,1))
        part = build_bins(BinConfiguration(cells=cells))['bin_01']
        self.assertTrue(part.is_valid)
        self.assertFalse(part.is_inside((63,63,6)))
        self.assertFalse(part.is_inside((63,63,15)))
        self.assertTrue(part.is_inside((41.5,63,15)))
        self.assertTrue(part.is_inside((84.5,63,15)))

    def test_four_cell_junction_has_continuous_floor_and_no_phantom_post(self):
        part = build_bins(BinConfiguration(cells=((0,0),(1,0),(0,1),(1,1))))['bin_01']
        for x,y in ((42,42),(41.9,42.1),(42.1,41.9),(41.4,41.4),(42.6,42.6)):
            self.assertTrue(part.is_inside((x,y,6)),(x,y))
            self.assertFalse(part.is_inside((x,y,15)),(x,y))

    def test_miura_side_and_separator_facets_have_selected_normal_thickness(self):
        for perimeters in (1,2):
            with self.subTest(perimeters=perimeters):
                config = BinConfiguration(cells=((0,0),(1,0)),wall_pattern='miura',
                    wall_perimeters=perimeters,dividers=({'axis':'x','x':1,'y':0},))
                part = build_bins(config)['bin_01']
                self.assertTrue(part.is_valid)
                samples = normal_wall_samples(part,config)
                self.assertGreaterEqual(len(samples),8)
                self.assertTrue(all(sample['passed'] for sample in samples),samples)
                # Explicitly sample the central separator as well as sides.
                central = [face for face in part.faces() if 40 < face.center().X < 44
                           and 10 < face.center().Y < 32 and 10 < face.center().Z < 24]
                self.assertTrue(any(.01 < abs(face.normal_at().Z) < .3 for face in central))

    def test_miura_merged_runs_and_remote_walls_have_no_thick_grid_bands(self):
        # A wide rear compartment and three front compartments: the reported
        # drawing had pads at y=126 and spurious bands on the remote y=0 side.
        dividers = tuple({'axis':'x','x':x,'y':y} for x in (1,2) for y in (2,3))
        dividers += tuple({'axis':'y','x':x,'y':2} for x in range(3))
        for perimeters in (1,2):
            with self.subTest(perimeters=perimeters):
                config = BinConfiguration(depth_units=4,wall_pattern='miura',
                    wall_perimeters=perimeters,dividers=dividers)
                part = build_bins(config)['bin_01']
                self.assertTrue(part.is_valid)
                for x in (42.,84.):
                    for origin,direction in (((x-4.,86.2,17.3),(1,0,0)),
                                             ((x-2.2,80.,17.3),(0,1,0))):
                        # Probe each arm close to the true T root without
                        # counting the unavoidable crossing of the two webs.
                        crossings = ray_crossings(part,origin,direction,8.)
                        self.assertEqual(len(crossings),2,crossings)
                        self.assertLess(crossings[1]-crossings[0],config.wall_thickness_mm*1.2)
                    for offset in (-1.2,.4,1.2):
                        crossings = ray_crossings(part,(x-4.,126.+offset,17.3),(1,0,0),8.)
                        self.assertEqual(len(crossings),2,crossings)
                        self.assertLess(crossings[1]-crossings[0],config.wall_thickness_mm*1.1)
                        # The remote boundary must preserve the periodic fold
                        # across the projected endpoint of a distant divider.
                        near = ray_crossings(part,(x+offset,-1.,17.3),(0,1,0),5.)
                        periodic = ray_crossings(part,(x+offset-14.,-1.,17.3),(0,1,0),5.)
                        self.assertEqual(len(near),2,near)
                        self.assertEqual(len(periodic),2,periodic)
                        self.assertLess(near[1]-near[0],config.wall_thickness_mm*1.1)
                        for actual, expected in zip(near,periodic):
                            self.assertAlmostEqual(actual,expected,places=5)
                layers = junction_layer_samples(part,config,config.components[0])
                self.assertEqual(len(layers),18)
                self.assertTrue(all(sample['passed'] for sample in layers),layers)

    def test_miura_cross_junction_connects_above_floor_with_free_ends(self):
        config = BinConfiguration(cells=tuple((x,y) for y in range(3) for x in range(3)),
            wall_pattern='miura',wall_perimeters=1,dividers=(
                {'axis':'x','x':1,'y':0},{'axis':'x','x':1,'y':1},
                {'axis':'y','x':0,'y':1},{'axis':'y','x':1,'y':1}))
        part = build_bins(config)['bin_01']
        layers = junction_layer_samples(part,config,config.components[0])
        self.assertTrue(part.is_valid)
        self.assertEqual({tuple(sample['junction_mm']) for sample in layers},
                         {(0.,42.),(42.,0.),(42.,42.)})
        self.assertTrue(all(sample['passed'] for sample in layers),layers)
        # A deliberate gap remains joined through the floor, but the local
        # layer check must reject it instead of accepting whole-solid validity.
        from build123d import Plane, Solid
        broken = part.cut(Solid.make_box(8.,.3,21.,Plane(origin=(38.,44.,7.1))))
        self.assertEqual(len(broken.solids()),1)
        broken_layers = junction_layer_samples(broken,config,config.components[0])
        self.assertFalse(all(sample['passed'] for sample in broken_layers),broken_layers)


if __name__ == '__main__':
    unittest.main()
