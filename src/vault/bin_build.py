"""Checked immutable exports for painted Gridfinity drawer containers."""
import argparse
import json
from pathlib import Path

from ._build import run_build, write_json
from .bin_config import BinConfiguration, bin_layout
from .project import PROJECT_ROOT


def print_note(config):
    drawer = config.container_type == 'drawer'
    return (
        ('Print each box upright with its flat base on the bed, using ' if drawer else
         'Print each container upright with its Gridfinity feet on the bed, using ')
        +
        'the supplied STL or print STEP orientation. '
        f'Walls and dividers target {config.wall_perimeters} perimeter'
        f'{"s" if config.wall_perimeters == 2 else ""} at 0.65 mm extrusion width '
        f'with a 0.6 mm nozzle ({config.wall_thickness_mm:g} mm nominal wall thickness). '
        'Inspect perimeter paths and thin-wall handling in the slicer. '
        + ('Miura-ori is a rigid corrugated wall pattern, not a folding mechanism. '
           if config.wall_pattern == 'miura' else '')
        + (f'Place each box at its painted planning cells inside the matching plain Vault '
           f'drawer with a {config.drawer_floor:g} mm floor. The 1.2 mm base has a '
           'relieved lower edge; no Gridfinity feet or sockets are used. '
           'The balanced starting point uses two-perimeter Miura walls, a flat '
           'supported floor and thin blended joins. Material volume is recorded '
           'in the build; print time depends on the slicer and printer profile. '
           if drawer else 'Place each container at its painted grid cells in the matching Vault '
           'Gridfinity drawer. No magnets or stacking lip are included. ')
        +
        'CAD and mesh checks do not establish printed fit or stiffness; test '
        'a small container before printing a full drawer.'
    )


def _export_bins(output, config):
    from .bin import build_bins as construct_bins
    from .exports import export_part_set

    parts = construct_bins(config)
    note = print_note(config)
    manifest, viewer = export_part_set(
        output, config, parts, kind='gridfinity_bins', print_note=note)
    layout = bin_layout(config)
    (output / 'printing.txt').write_text(
        f'{config.name}\n\n{note}\n\n'
        'One STL per connected painted region; print one copy of each.\n'
        'The configuration records the original drawer placement; individual '
        'print files are translated onto the bed.\n\n'
        + '\n'.join(f'stl/{name}.stl' for name in parts) + '\n')
    manifest.update({
        'gridfinity_configuration': config.as_dict(),
        'gridfinity_layout': layout,
        'design_metrics': {
            'material_volume_cm3': sum(part['cad_volume_mm3'] for part in manifest['parts'].values())/1000,
            'clear_height_mm': config.height_mm-config.floor_top_mm,
            'planning_area_mm2': len(config.cells)*config.pitch_x_mm*config.pitch_y_mm,
            'base_thickness_mm': config.floor_top_mm-config.foot_height_mm,
            'wall_thickness_mm': config.wall_thickness_mm,
        },
        'print_instructions': 'printing.txt',
    })
    write_json(output / 'build.json', manifest)
    return manifest, viewer


def build_bins(output: Path, config=None):
    """Publish only after every bin passes solid, STEP and print-mesh checks."""
    config = config or BinConfiguration()
    return run_build(
        PROJECT_ROOT, config.key, lambda state: _export_bins(state.stage, config),
        parameters={'part': config.slug, 'gridfinity_configuration': config.as_dict()},
        output=Path(output), aliases=[f'latest/{config.slug}'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'out')
    parser.add_argument('--configuration', type=Path,
                        help='Gridfinity editor request JSON')
    args = parser.parse_args(argv)
    config = (BinConfiguration.parse(json.loads(args.configuration.read_text()))
              if args.configuration else BinConfiguration())
    build_bins(args.output, config)


if __name__ == '__main__':
    main()
