"""Deterministic headless review images rendered from the exported geometry."""
from pathlib import Path
import numpy as np
from PIL import Image


def render_mesh(mesh, path: Path, eye=(1, 1, 1.15), width=1400, height=1000, *, backend='auto'):
    """Orthographic triangle rendering; no browser, GPU, or hand-drawn geometry."""
    if backend not in {'auto', 'native', 'python'}:
        raise ValueError('Renderer backend must be auto, native, or python')
    view = np.array(eye, dtype=float)
    view /= np.linalg.norm(view)
    right = np.cross([0., 0., 1.], view) if abs(view[2]) < .99 else np.array([1., 0., 0.])
    right /= np.linalg.norm(right)
    up = np.cross(view, right)
    projected = mesh.vertices @ np.array([right, up, view]).T
    span = np.ptp(projected[:, :2], axis=0)
    scale = min((width - 80) / span[0], (height - 80) / span[1])
    xy = (projected[:, :2] - projected[:, :2].min(0)) * scale
    xy += (np.array([width, height]) - span * scale) / 2
    xy[:, 1] = height - xy[:, 1]
    normals = mesh.face_normals
    light = .2 * right + .6 * up + .7 * view
    light /= np.linalg.norm(light)
    shade = .40 + .60 * np.maximum(0, normals @ light)
    colors = (np.array([80, 155, 210])[None, :] * shade[:, None]).astype(np.uint8)
    visible = np.flatnonzero(normals @ view > 0)
    pixels = np.full((height, width, 3), (245, 246, 249), dtype=np.uint8)
    depth = np.full((height, width), -np.inf)
    native = None
    if backend != 'python':
        from .native_renderer import native_rasterizer
        native, failure = native_rasterizer()
        if native is None and backend == 'native':
            raise RuntimeError(f'Native renderer unavailable: {failure}')
    if native is not None:
        native(np.ascontiguousarray(xy, dtype=np.float64),
               np.ascontiguousarray(projected[:, 2], dtype=np.float64),
               np.ascontiguousarray(mesh.faces, dtype=np.int64),
               np.ascontiguousarray(visible, dtype=np.int64),
               np.ascontiguousarray(colors), len(visible), width, height, pixels, depth)
    else:
        _rasterize_python(xy, projected[:, 2], mesh.faces, visible, colors, pixels, depth)
    canvas = Image.fromarray(pixels)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def _rasterize_python(xy, z_coordinates, faces, visible, colors, pixels, depth):
    """Portable reference implementation used when no compiler is available."""
    height, width = depth.shape
    # Barycentric Z-buffer: overlapping interior/exterior faces must not be
    # painter-sorted by their centroids (large CAD triangles would show through).
    for i in visible:
        ids = faces[i]
        a, b, c = xy[ids]
        x0, y0 = np.maximum(0, np.floor(np.minimum(np.minimum(a, b), c))).astype(int)
        x1, y1 = np.minimum([width-1, height-1], np.ceil(np.maximum(np.maximum(a, b), c))).astype(int)
        determinant = (b[1]-c[1])*(a[0]-c[0]) + (c[0]-b[0])*(a[1]-c[1])
        if abs(determinant) < 1e-12 or x1 < x0 or y1 < y0:
            continue
        x = np.arange(x0, x1+1)[None, :] + .5
        y = np.arange(y0, y1+1)[:, None] + .5
        u = ((b[1]-c[1])*(x-c[0]) + (c[0]-b[0])*(y-c[1])) / determinant
        v = ((c[1]-a[1])*(x-c[0]) + (a[0]-c[0])*(y-c[1])) / determinant
        w = 1-u-v
        z = u*z_coordinates[ids[0]] + v*z_coordinates[ids[1]] + w*z_coordinates[ids[2]]
        region = depth[y0:y1+1, x0:x1+1]
        inside = (u >= -1e-8) & (v >= -1e-8) & (w >= -1e-8) & (z > region)
        region[inside] = z[inside]
        pixels[y0:y1+1, x0:x1+1][inside] = colors[i]


def render_review(mesh, directory: Path):
    for name, eye in {
        'isometric': (1, 1, 1.15),
        'underside': (1, -1, -1),
        'closed-back': (0, -1, 0),
        'open-front': (0, 1, 0),
    }.items():
        render_mesh(mesh, directory / f'{name}.png', eye=eye)
