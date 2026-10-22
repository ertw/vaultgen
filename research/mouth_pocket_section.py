"""Plot actual source-STL section through the handed runner mouth pockets."""
from pathlib import Path
import numpy as np
import trimesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from vault.reference import load_reference, PROJECT_ROOT

Y_SECTION = 187.1
mesh = load_reference()
section = trimesh.intersections.mesh_plane(mesh, [0, 1, 0], [0, Y_SECTION, 0])
segments = section[:, :, [0, 2]]
midpoints = segments.mean(axis=1)
right_pocket = (midpoints[:, 0] > 66) & (midpoints[:, 0] < 77) & (midpoints[:, 1] > 5.7) & (midpoints[:, 1] < 8.9)
left_pocket = (midpoints[:, 0] < -66) & (midpoints[:, 0] > -77) & (midpoints[:, 1] > 38.1) & (midpoints[:, 1] < 41.4)
colors = {'right': '#d16b14', 'left': '#147aaa', 'ordinary': '#515860'}

fig = plt.figure(figsize=(14, 10), facecolor='white')
grid = fig.add_gridspec(3, 2, height_ratios=[1.65, 1, 1], hspace=.45, wspace=.15)
context = fig.add_subplot(grid[0, :])
axes = [context]

def draw(ax, linewidth=1.0):
    ax.add_collection(LineCollection(segments, colors=colors['ordinary'], linewidths=linewidth))
    ax.add_collection(LineCollection(segments[right_pocket], colors=colors['right'], linewidths=linewidth*2.5))
    ax.add_collection(LineCollection(segments[left_pocket], colors=colors['left'], linewidths=linewidth*2.5))
    ax.set_aspect('equal')
    ax.grid(alpha=.16)
    ax.set_xlabel('Model X (mm); positive X is screen-left in this front view')
    ax.set_ylabel('Model Z (mm)')

draw(context)
context.set_xlim(85, -85)
context.set_ylim(-1, 49)
context.set_title('Original purchased STL — actual cross-section 1 mm behind the opening', fontsize=15, weight='bold', pad=13)
context.text(70, 44.5, 'RIGHT RUNNER (+X)', color=colors['right'], ha='center', weight='bold')
context.text(-70, 44.5, 'LEFT RUNNER (−X)', color=colors['left'], ha='center', weight='bold')
context.text(0, 23.5, 'OPEN DRAWER SPACE', ha='center', va='center', color='#777777', fontsize=13)
context.annotate('Lower relief', xy=(72, 6.667), xytext=(44, 14), ha='center', color=colors['right'], arrowprops={'arrowstyle':'->','color':colors['right']})
context.annotate('Upper relief', xy=(-72,40.104), xytext=(-44,33), ha='center', color=colors['left'], arrowprops={'arrowstyle':'->','color':colors['left']})

panels=[
    (1,0,(80,63),(32,42.5),'Right upper: ordinary corner',37.7695266,70.3344,colors['ordinary']),
    (1,1,(-63,-80),(32,42.5),'Left upper: extra relief',40.1039236,-70.3344,colors['left']),
    (2,0,(80,63),(4.5,15),'Right lower: extra relief',6.6665116,70.3344,colors['right']),
    (2,1,(-63,-80),(4.5,15),'Left lower: ordinary corner',9.2294465,-70.3344,colors['ordinary']),
]
for row,col,xlim,ylim,title,z,x,color in panels:
    ax=fig.add_subplot(grid[row,col]);draw(ax,1.5)
    ax.set_xlim(*xlim);ax.set_ylim(*ylim);ax.set_title(title,fontsize=12,color=color,weight='bold')
    ax.set_xlabel('Model X (mm)')
    ax.scatter([x],[z],s=30,c=color,zorder=5)
    text_z=z-2 if row==1 else z+2
    ax.annotate(f'Z = {z:.3f} mm',xy=(x,z),xytext=(x,text_z),ha='center',color=color,arrowprops={'arrowstyle':'->','color':color})
fig.text(.5,.015,'Contours come directly from source STL triangle intersections at Y = 187.1 mm. Colored surfaces identify the diagonal relief pockets; no model fitting or side registration is used.',ha='center',fontsize=9,color='#555555')
out=PROJECT_ROOT/'out/review/mouth_pocket_section.png';out.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(out,dpi=180,bbox_inches='tight')
print(out)
