"""Plot retained-surface discrepancies from a completed numerical comparison.

Usage: python tools/plot_comparison.py [out/comparison.npz]
The plot uses measured distances, not an image comparison or a rendered model.
"""
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('out/comparison.npz')
data = np.load(path)
fig, axes = plt.subplots(2, 3, figsize=(15, 9), layout='constrained')
for row, (label, prefix) in enumerate([('Reference → CAD', 'reference'), ('CAD → reference', 'model')]):
    points, distances = data[f'{prefix}_points'], data[f'{prefix}_distances']
    # Paint the largest discrepancies last so small functional details remain
    # visible despite overlapping surfaces in an orthographic projection.
    order = np.argsort(distances)
    for column, (x, y) in enumerate([(0, 1), (0, 2), (1, 2)]):
        ax = axes[row, column]
        dots = ax.scatter(points[order, x], points[order, y], c=np.maximum(distances[order], .0001), s=.7,
                          cmap='turbo', norm=LogNorm(vmin=.001, vmax=max(.1, distances.max())), rasterized=True)
        ax.set(xlabel=f'{"XYZ"[x]} (mm)', ylabel=f'{"XYZ"[y]} (mm)', title=f'{label}: {"XYZ"[x]} / {"XYZ"[y]}')
        ax.set_aspect('equal')
    fig.colorbar(dots, ax=axes[row, :], label='Surface deviation (mm)', shrink=.8)
fig.suptitle('Retained surfaces — requested decoration regions excluded')
fig.savefig(path.with_suffix('.png'), dpi=150)
print(path.with_suffix('.png'))
