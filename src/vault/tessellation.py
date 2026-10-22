"""Internal surface tessellation for rendering and reference comparisons."""
from pathlib import Path
from tempfile import TemporaryDirectory


def review_mesh(shape):
    with TemporaryDirectory(prefix='vault-review-') as directory:
        return _tessellate(shape, Path(directory) / 'review.stl')


def load_model(path):
    import trimesh
    if Path(path).suffix.lower() == '.step':
        from build123d import import_step
        return review_mesh(import_step(path))
    return trimesh.load_mesh(path)


def _tessellate(module, mesh_path):
    import trimesh
    # Model-space tessellation is used only for surface checks and rendering.
    # build123d 0.13's STL helper uses relative deflection. Use an absolute
    # 0.05 mm edge chord tolerance, suitable for these printable features.
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.StlAPI import StlAPI_Writer
    BRepTools.Clean_s(module.wrapped)
    mesher = BRepMesh_IncrementalMesh()
    mesher.SetShape(module.wrapped)
    settings = mesher.ChangeParameters()
    settings.Deflection = .05
    settings.Angle = .5
    settings.Relative = False
    settings.InParallel = True
    # Retain interior deflection control: trimming a curved face can otherwise
    # leave long triangles whose interiors miss the native surface badly.
    settings.ControlSurfaceDeflection = True
    mesher.Perform()
    if not mesher.IsDone():
        raise ValueError('Absolute-tolerance CAD tessellation failed')
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(module.wrapped, str(mesh_path)):
        raise ValueError('STL export failed')
    mesh = trimesh.load_mesh(mesh_path)
    # OCC can emit repeated or collapsed triangles on very short trimmed edges.
    # Remove only exact zero-area/repeated triangles. A minimum-height filter
    # would incorrectly remove skinny valid triangles on the connector ramps.
    # No remeshing or smoothing is performed.
    mesh.update_faces(mesh.area_faces > 0.0)
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    from .mesh_cleanup import close_micro_triangles
    close_micro_triangles(mesh)
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        raise ValueError('Review tessellation is not a closed, consistently oriented positive-volume mesh')
    return mesh
