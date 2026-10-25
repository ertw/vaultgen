"""Checked, immutable multicolor label exports with common part registration."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from ._build import run_build, write_json
from .label_config import LabelConfiguration, label_dimensions, label_layout
from .reference import PROJECT_ROOT


PRINT_NOTE = (
    'Print face down in the supplied orientation. The first 0.6 mm contains '
    'flush text inlays: assign a filament to each named color part in your slicer. '
    'Import the 3MF as one multipart object, or all STLs together and retain '
    'their shared coordinates. Do not auto-arrange or center individual colors. '
    'Use 0.2 mm layers (three colored layers) and no supports. '
    'The hollow version has a 0.9 mm face and 0.8 mm adhesion rim. '
    'Mount with suitable adhesive; no snap attachment is included. '
    'Physical printer/material fit has not been tested.'
)
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'


def _check_step(shape, path):
    """Retain the regular STEP tolerances, allowing disconnected ink solids."""
    from build123d import import_step
    from .exports import precise_volume
    restored = import_step(path)
    volume, restored_volume = precise_volume(shape), precise_volume(restored)
    delta = abs(restored_volume-volume)/max(abs(volume),1.)
    before, after = shape.bounding_box(), restored.bounding_box()
    bounds_error = max(abs(a-b) for a,b in zip((*before.min,*before.max),(*after.min,*after.max)))
    expected = len(shape.solids())
    passed = (restored.is_valid and expected > 0 and len(restored.solids()) == expected
              and len(restored.shells()) == expected and volume > 0 and restored_volume > 0
              and delta < 1e-5 and bounds_error < 1e-4)
    report = {'passed': bool(passed), 'solids': len(restored.solids()),
              'boundary_shells': len(restored.shells()), 'volume_relative_error': delta,
              'volume_relative_tolerance': 1e-5, 'bbox_max_error_mm': bounds_error}
    if not passed:
        raise ValueError(f'{path.name}: label STEP round trip failed: {report}')
    return restored, report


def _write_3mf(path, meshes, colors):
    """3MF core base materials and a single multipart assembly/build item."""
    ET.register_namespace('', NS)
    tag = lambda name: f'{{{NS}}}{name}'
    model = ET.Element(tag('model'), {'unit':'millimeter', '{http://www.w3.org/XML/1998/namespace}lang':'en-US'})
    ET.SubElement(model,tag('metadata'),{'name':'Application'}).text = 'Vaultgen native labels'
    resources = ET.SubElement(model,tag('resources'))
    materials = ET.SubElement(resources,tag('basematerials'),{'id':'1'})
    object_ids = []
    for index,(name,mesh) in enumerate(meshes.items()):
        color = colors[name]
        ET.SubElement(materials,tag('base'),{'name':f'{name} {color}', 'displaycolor':color.upper()+'FF'})
        object_id = str(index+2)
        object_ids.append(object_id)
        obj = ET.SubElement(resources,tag('object'),{'id':object_id,'type':'model','name':name,'pid':'1','pindex':str(index)})
        element = ET.SubElement(obj,tag('mesh'))
        vertices = ET.SubElement(element,tag('vertices'))
        triangles = ET.SubElement(element,tag('triangles'))
        for vertex in mesh.vertices:
            ET.SubElement(vertices,tag('vertex'),dict(zip(('x','y','z'),(f'{v:.12g}' for v in vertex))))
        for triangle in mesh.faces:
            ET.SubElement(triangles,tag('triangle'),dict(zip(('v1','v2','v3'),map(str,triangle))))
    assembly_id = str(len(meshes)+2)
    assembly = ET.SubElement(resources,tag('object'),{'id':assembly_id,'type':'model','name':'Vault label — print face down'})
    components = ET.SubElement(assembly,tag('components'))
    for object_id in object_ids:
        ET.SubElement(components,tag('component'),{'objectid':object_id})
    build = ET.SubElement(model,tag('build'))
    ET.SubElement(build,tag('item'),{'objectid':assembly_id})
    types = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    relationships = ('<?xml version="1.0" encoding="UTF-8"?>'
                     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
                     '</Relationships>')
    with ZipFile(path,'w',compression=ZIP_DEFLATED) as package:
        package.writestr('[Content_Types].xml',types)
        package.writestr('_rels/.rels',relationships)
        package.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
    return _check_3mf(path,meshes,colors)


def _check_3mf(path, meshes, colors):
    """Read back every packed mesh and check registration/material identities."""
    import numpy as np
    import trimesh
    with ZipFile(path) as package:
        if package.testzip() is not None:
            raise ValueError('3MF ZIP checksum failure')
        root = ET.fromstring(package.read('3D/3dmodel.model'))
    q = lambda name: f'{{{NS}}}{name}'
    resources = root.find(q('resources'))
    objects = resources.findall(q('object'))
    materials = resources.find(q('basematerials')).findall(q('base'))
    if len(materials) != len(meshes) or len(objects) != len(meshes)+1:
        raise ValueError('3MF lost colors or components')
    assembly = objects[-1]
    components = assembly.find(q('components')).findall(q('component'))
    items = root.find(q('build')).findall(q('item'))
    if (len(items) != 1 or items[0].get('objectid') != assembly.get('id')
            or [c.get('objectid') for c in components] != [o.get('id') for o in objects[:-1]]
            or any('transform' in c.attrib for c in components+items)):
        raise ValueError('3MF must preserve one registered multipart label')
    for index, ((name, expected), obj) in enumerate(zip(meshes.items(), objects)):
        element = obj.find(q('mesh'))
        vertices = [[float(v.get(a)) for a in ('x','y','z')] for v in element.find(q('vertices'))]
        faces = [[int(v.get(a)) for a in ('v1','v2','v3')] for v in element.find(q('triangles'))]
        restored = trimesh.Trimesh(vertices=vertices,faces=faces,process=False)
        if (not restored.is_watertight or not restored.is_winding_consistent or restored.volume <= 0
                or not np.allclose(restored.vertices,expected.vertices,atol=1e-8,rtol=0)
                or not np.array_equal(restored.faces,expected.faces)
                or obj.get('name') != name or obj.get('pid') != '1' or obj.get('pindex') != str(index)
                or materials[index].get('displaycolor') != colors[name].upper()+'FF'):
            raise ValueError(f'3MF component/material round-trip failed: {name}')
    return {'passed':True,'colors':len(meshes),'registered_components':len(meshes),'build_items':1}


def _export_label(output, config):
    from build123d import Compound, export_brep, export_step
    from .exports import precise_volume
    from .label import build_label_parts, to_print
    from .tessellation import export_print_mesh

    started = time.monotonic()
    native, geometry_check = build_label_parts(config)
    reports, components, print_children, native_children, meshes = {}, [], [], [], {}
    for name, description in native.items():
        shape = description['shape']
        printable = to_print(shape,config)
        print(f'Exporting {name} ({description["color"]}) in common print coordinates…',flush=True)
        for item,suffix in ((shape,''),(printable,'_print')):
            path = output / f'{name}{suffix}.step'
            if not export_step(item,path):
                raise ValueError(f'{name}: STEP export failed')
            _,check = _check_step(item,path)
            if suffix: print_check = check
            else: native_check = check
        if not export_brep(shape,output/f'{name}.brep'):
            raise ValueError(f'{name}: BREP export failed')
        mesh = export_print_mesh(printable,output/'stl'/f'{name}.stl')
        meshes[name] = mesh
        bounds = printable.bounding_box()
        reports[name] = {'kind':'label','role':description['role'],'color':description['color'],
                         'cad_valid':True,'solids':len(shape.solids()),'boundary_shells':len(shape.shells()),
                         'cad_volume_mm3':precise_volume(shape),'step_roundtrip':native_check,
                         'print_step_roundtrip':print_check,'print_bbox_mm':list(bounds.size),
                         'print_bounds_mm':[list(bounds.min),list(bounds.max)],'print_note':PRINT_NOTE,
                         'stl_watertight':bool(mesh.is_watertight),'stl_winding_consistent':bool(mesh.is_winding_consistent)}
        components.append({'name':name,'step':f'{name}.step','kind':'label','color':description['color']})
        for children,item in ((native_children,shape),(print_children,printable)):
            child = deepcopy(item)
            child.parent = None
            child.label = name
            children.append(child)
    checks = {}
    for children,suffix in ((native_children,''),(print_children,'_print')):
        assembly = Compound(label=config.name,children=children)
        path = output / f'{config.slug}{suffix}.step'
        if not export_step(assembly,path):
            raise ValueError('Label assembly STEP export failed')
        restored,check = _check_step(assembly,path)
        if {child.label for child in restored.children} != set(native):
            raise ValueError('Label STEP lost color component names')
        checks[suffix or 'native'] = check
    three_mf = f'{config.slug}.3mf'
    multicolor_check = _write_3mf(output/three_mf,meshes,{name:item['color'] for name,item in native.items()})
    dimensions = label_dimensions(config)
    (output/'printing.txt').write_text(f'VAULT {config.family} LABEL — PRINTING\n\n'
        f'{dimensions["width_mm"]:g} × {dimensions["height_mm"]:g} × {dimensions["thickness_mm"]:g} mm\n\n'+PRINT_NOTE+'\n\n'+
        '\n'.join(f'{name}: {item["color"]}' for name,item in native.items())+'\n')
    manifest = {'passed':True,'project':'vault','name':config.name,'units':'mm','status':'Completed CAD build',
                'cad_valid':True,'solids':sum(item['solids'] for item in reports.values()),
                'boundary_shells':sum(item['boundary_shells'] for item in reports.values()),
                'cad_volume_mm3':geometry_check['color_volume_mm3'],'parts':reports,
                'label_configuration':config.as_dict(),'label_dimensions':dimensions,
                'label_layout':label_layout(config),'geometry_check':geometry_check,
                'step_roundtrip':checks['native'],'print_step_roundtrip':checks['_print'],
                'multicolor_3mf':three_mf,'multicolor_roundtrip':multicolor_check,
                'print_instructions':'printing.txt','elapsed_seconds':time.monotonic()-started}
    write_json(output/'build.json',manifest)
    return manifest, {'assembly':f'{config.slug}.step','components':components}


def build_label(output: Path, config=None):
    config = config or LabelConfiguration()
    return run_build(PROJECT_ROOT,config.key,lambda state:_export_label(state.stage,config),
                     parameters={'part':config.slug,'label_configuration':config.as_dict()},
                     output=Path(output),aliases=[f'latest/{config.slug}'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=PROJECT_ROOT/'out')
    parser.add_argument('--configuration',type=Path,help='label request JSON (defaults to BOLTS)')
    args = parser.parse_args(argv)
    config = LabelConfiguration.parse(json.loads(args.configuration.read_text())) if args.configuration else LabelConfiguration()
    build_label(args.output,config)


if __name__ == '__main__':
    main()
