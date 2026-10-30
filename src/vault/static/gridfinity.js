import { STLViewer } from './stl-viewer.js';
import { api, downloadLink, errorMessage, isActive } from './client.js';

const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const KIND = 'gridfinity_bins';
const palette = ['#64889f', '#8c9981', '#a4896f', '#8a7e9e', '#629a96', '#a57982'];
const state = { config: null, draft: null, tool: 'cells', undo: [], stroke: null, view: 'layout', job: null,
  submitting: false, recovering: true, selected: null, viewer: null, pollTimer: null, modelRequest: 0, version: 0, submittedVersion: 0, completedJob: null };
const node = (tag, className, text) => { const n = document.createElement(tag); if (className) n.className = className; if (text !== undefined) n.textContent = text; return n; };
const svg = (tag, attrs) => { const n = document.createElementNS(NS, tag); for (const [key, value] of Object.entries(attrs)) n.setAttribute(key, value); return n; };
const cellKey = (x, y) => `${x},${y}`;
const dividerKey = d => `${d.axis},${d.x},${d.y}`;
const cells = () => new Set(state.draft.cells.map(([x, y]) => cellKey(x, y)));
const containerType = draft => draft?.container_type === undefined ? 'gridfinity' : draft.container_type;
const drawerFloor = draft => draft?.drawer_floor === undefined ? .8 : draft.drawer_floor;
const supportsDrawer = () => state.config.container_types?.includes('drawer') && Boolean(state.config.drawer_layouts?.length);
const drawerLayout = (draft = state.draft) => (state.config.drawer_layouts || []).find(layout =>
  layout.family === draft.family && layout.depth_units === draft.depth_units && layout.height_units === draft.height_units && layout.drawer_floor === drawerFloor(draft));
const columns = (draft = state.draft) => state.config.families.find(f => f.id === draft.family)[containerType(draft) === 'drawer' ? 'drawer_columns' : 'columns'];
const gridMetrics = () => {
  const layout = containerType(state.draft) === 'drawer' ? drawerLayout() : null;
  return { x: layout ? 64 * layout.pitch_x_mm / layout.pitch_y_mm : 64, y: 64 };
};
const fullGrid = (draft = state.draft) => Array.from({ length: draft.depth_units }, (_, y) => Array.from({ length: columns(draft) }, (_, x) => [x, y])).flat();
const describe = d => `${containerType(d) === 'drawer' ? `Drawer-fit box · ${drawerFloor(d)} mm drawer floor` : 'Gridfinity'} · ${d.family}${d.depth_units} · ${d.height_units}F · ${d.wall_pattern === 'miura' ? 'Miura-ori' : 'Plain'} · ${d.wall_perimeters} perimeter${d.wall_perimeters === 1 ? '' : 's'}`;
const sameDesign = (a, b) => a && b && containerType(a) === containerType(b) && (containerType(a) !== 'drawer' || drawerFloor(a) === drawerFloor(b)) && ['family', 'depth_units', 'height_units', 'wall_pattern', 'wall_perimeters'].every(key => a[key] === b[key]) &&
  JSON.stringify((a.cells || []).map(([x, y]) => cellKey(x, y)).sort()) === JSON.stringify((b.cells || []).map(([x, y]) => cellKey(x, y)).sort()) &&
  JSON.stringify((a.dividers || []).map(dividerKey).sort()) === JSON.stringify((b.dividers || []).map(dividerKey).sort());
const announce = message => { $('announcement').textContent = message; };
function storage(key, value) { try { if (value !== undefined) localStorage.setItem(key, JSON.stringify(value)); else return JSON.parse(localStorage.getItem(key)); } catch { return null; } }
function connectionError(error) { $('connection-error').hidden = !error; $('connection-error').textContent = error ? errorMessage(error) : ''; }
function validDivider(d, selected = cells()) {
  return d && ['x', 'y'].includes(d.axis) && Number.isInteger(d.x) && Number.isInteger(d.y) &&
    selected.has(cellKey(d.x, d.y)) && selected.has(cellKey(d.x - (d.axis === 'x' ? 1 : 0), d.y - (d.axis === 'y' ? 1 : 0)));
}
function cleanDividers() { const selected = cells(); state.draft.dividers = state.draft.dividers.filter(d => validDivider(d, selected)); }
function normalize() {
  if (containerType(state.draft) === 'gridfinity') { delete state.draft.container_type; delete state.draft.drawer_floor; }
  else state.draft.drawer_floor = drawerFloor(state.draft);
  state.draft.cells.sort((a, b) => a[1] - b[1] || a[0] - b[0]);
  state.draft.dividers.sort((a, b) => a.axis.localeCompare(b.axis) || a.x - b.x || a.y - b.y);
}
function remember() { state.undo.push(structuredClone(state.draft)); if (state.undo.length > 50) state.undo.shift(); }
function regions() {
  const remaining = cells(), groups = [];
  while (remaining.size) {
    const pending = [remaining.values().next().value], group = []; remaining.delete(pending[0]);
    while (pending.length) {
      const key = pending.pop(), [x, y] = key.split(',').map(Number); group.push(key);
      for (const next of [cellKey(x - 1, y), cellKey(x + 1, y), cellKey(x, y - 1), cellKey(x, y + 1)]) if (remaining.delete(next)) pending.push(next);
    }
    groups.push(group);
  }
  return groups;
}
function edited({ rebuild = false } = {}) {
  normalize(); state.version++; storage('vault-bin-draft', state.draft);
  if (state.view !== 'layout') setView('layout');
  if (rebuild) createGrid();
  render();
}
function change(key, value) {
  if ((key === 'container_type' ? containerType(state.draft) : key === 'drawer_floor' ? drawerFloor(state.draft) : state.draft[key]) === value) return;
  remember(); const wasFull = state.draft.cells.length === columns() * state.draft.depth_units;
  state.draft[key] = value;
  const resize = ['container_type', 'family', 'depth_units'].includes(key);
  if (resize) {
    state.draft.cells = wasFull ? fullGrid() : state.draft.cells.filter(([x, y]) => x < columns() && y < state.draft.depth_units);
    cleanDividers();
    announce('Grid resized. Partial layouts keep cells that fit; Undo restores the previous size.');
  }
  edited({ rebuild: resize || (containerType(state.draft) === 'drawer' && ['height_units', 'drawer_floor'].includes(key)) });
}
function createGrid() {
  const root = $('drawer-grid'), width = columns(), height = state.draft.depth_units, unit = gridMetrics();
  root.replaceChildren(); root.setAttribute('viewBox', `-8 -8 ${width * unit.x + 16} ${height * unit.y + 16}`);
  root.setAttribute('aria-label', `${width} column by ${height} row drawer layout. Back at top, front at bottom.`);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    root.append(svg('rect', { x: x * unit.x + 3, y: y * unit.y + 3, width: unit.x - 6, height: unit.y - 6, rx: 4, class: 'grid-cell',
      'data-kind': 'cell', 'data-x': x, 'data-y': y, role: 'button', tabindex: 0, 'aria-label': `Cell column ${x + 1}, row ${y + 1}`, 'aria-pressed': false }));
    root.append(svg('text', { x: (x + .5) * unit.x, y: (y + .5) * unit.y, class: 'cell-number', 'data-label': cellKey(x, y) }));
  }
  root.append(svg('g', { id: 'grid-boundaries', 'aria-hidden': true }));
  for (const axis of ['x', 'y']) for (let y = axis === 'y' ? 1 : 0; y < height; y++) for (let x = axis === 'x' ? 1 : 0; x < width; x++) {
    const group = svg('g', { class: 'grid-divider', 'data-kind': 'divider', 'data-axis': axis, 'data-x': x, 'data-y': y,
      role: 'button', tabindex: 0, 'aria-label': `${axis === 'x' ? 'Vertical' : 'Horizontal'} divider at column ${x + 1}, row ${y + 1}`, 'aria-pressed': false });
    const coords = axis === 'x' ? { x1: x * unit.x, x2: x * unit.x, y1: y * unit.y + 7, y2: (y + 1) * unit.y - 7 } : { x1: x * unit.x + 7, x2: (x + 1) * unit.x - 7, y1: y * unit.y, y2: y * unit.y };
    group.append(svg('line', { ...coords, class: 'divider-hit' }), svg('line', { ...coords, class: 'divider-line' })); root.append(group);
  }
}
function render() {
  if (!state.draft) return;
  const selected = cells(), groups = regions(), membership = new Map(); groups.forEach((group, index) => group.forEach(key => membership.set(key, index)));
  for (const button of document.querySelectorAll('[data-setting]')) button.setAttribute('aria-pressed', String(String(button.dataset.setting === 'container_type' ? containerType(state.draft) : button.dataset.setting === 'drawer_floor' ? drawerFloor(state.draft) : state.draft[button.dataset.setting]) === button.dataset.value));
  const drawer = containerType(state.draft) === 'drawer', layout = drawer ? drawerLayout() : null, unit = gridMetrics();
  for (const button of $('bin-family-options').querySelectorAll('button')) {
    const family = state.config.families.find(f => f.id === button.dataset.value), count = family[drawer ? 'drawer_columns' : 'columns'];
    button.querySelector('.family-width').textContent = `${count} columns`;
    button.setAttribute('aria-label', `${family.id} drawer, ${count} columns`);
  }
  for (const button of document.querySelectorAll('[data-tool]')) if (button.tagName === 'BUTTON') button.setAttribute('aria-pressed', String(button.dataset.tool === state.tool));
  $('drawer-grid').dataset.tool = state.tool;
  for (const rect of $('drawer-grid').querySelectorAll('[data-kind=cell]')) {
    const key = cellKey(rect.dataset.x, rect.dataset.y), painted = selected.has(key);
    rect.classList.toggle('selected', painted); rect.setAttribute('aria-pressed', String(painted));
    rect.style.setProperty('--cell-color', palette[(membership.get(key) || 0) % palette.length]);
  }
  for (const text of $('drawer-grid').querySelectorAll('[data-label]')) text.textContent = membership.has(text.dataset.label) ? membership.get(text.dataset.label) + 1 : '';
  const drawn = new Set(state.draft.dividers.map(dividerKey));
  for (const edge of $('drawer-grid').querySelectorAll('[data-kind=divider]')) {
    const d = { axis: edge.dataset.axis, x: Number(edge.dataset.x), y: Number(edge.dataset.y) }, valid = validDivider(d, selected);
    edge.setAttribute('aria-pressed', String(drawn.has(dividerKey(d)))); edge.style.display = valid ? '' : 'none';
    edge.setAttribute('tabindex', valid && state.tool !== 'cells' ? '0' : '-1');
  }
  const boundary = $('grid-boundaries'); boundary.replaceChildren();
  for (const [x, y] of state.draft.cells) for (const [dx, dy, x1, y1, x2, y2] of [
    [-1, 0, x, y, x, y + 1], [1, 0, x + 1, y, x + 1, y + 1], [0, -1, x, y, x + 1, y], [0, 1, x, y + 1, x + 1, y + 1]]) {
    if (!selected.has(cellKey(x + dx, y + dy))) boundary.append(svg('line', { x1: x1 * unit.x, y1: y1 * unit.y, x2: x2 * unit.x, y2: y2 * unit.y, class: 'grid-boundary' }));
  }
  const d = state.config.dimensions;
  const mm = value => Number(value.toFixed(2));
  $('type-hint').textContent = drawer ? 'Removable boxes fitted inside a plain Vault drawer. Flat floor, no Gridfinity feet.' : 'Removable containers for the Vault Gridfinity base.';
  $('size-grid-hint').textContent = drawer ? 'fitted planning grid' : '42 mm grid';
  $('height-hint').textContent = drawer ? `${mm(layout.height_mm)} mm box height · ${mm(layout.floor_thickness_mm)} mm floor.` : `${d.heights_mm[String(state.draft.height_units)]} mm container height, including the base.`;
  $('pattern-hint').textContent = state.draft.wall_pattern === 'miura' ? 'Folded facets on sides and dividers, continuous runs, and thin blended joints.' : 'Straight sides and dividers for a simple baseline.';
  $('perimeter-hint').textContent = `${(d.wall_line_width_mm * state.draft.wall_perimeters).toFixed(2)} mm target wall thickness · ${d.wall_line_width_mm} mm extrusion width.`;
  $('bin-summary').textContent = `${state.draft.family}${state.draft.depth_units} · ${state.draft.height_units}F · ${columns()} × ${state.draft.depth_units} grid`;
  $('bin-count').textContent = `${groups.length} container${groups.length === 1 ? '' : 's'} · ${selected.size} cells · ${drawn.size} dividers`;
  $('grid-badge').textContent = `${columns()} × ${state.draft.depth_units} · ${drawer ? 'planning grid' : `${d.pitch_mm} mm`}`;
  $('footprint-size').textContent = drawer ? `${mm(layout.outer_width_mm)} × ${mm(layout.outer_depth_mm)} mm full drawer envelope` : `${columns() * d.pitch_mm} × ${state.draft.depth_units * d.pitch_mm} mm grid`;
  $('balanced-design').hidden = !drawer;
  $('drawer-floor-setting').hidden = !drawer;
  $('layout-note').textContent = drawer ? 'Each colored region is one removable box. Paint lines between selected cells to add fixed dividers. The planning grid fills the drawer space; cells are not fixed at 42 mm.' : 'Each colored region is one removable container. Paint lines between selected cells to add fixed dividers. Empty cells leave space for other bins.';
  $('guidance-title').textContent = drawer ? 'Designed around the Vault drawer space.' : 'Made for the Vault Gridfinity base.';
  $('guidance-detail').textContent = drawer ? 'Use inside a plain Vault drawer. The balanced design is a starting point; choose one perimeter to compare material use and stiffness.' : 'Full drawer fills all whole grid cells.';
  $('validation-message').textContent = selected.size ? 'Ready to generate.' : 'Paint at least one cell to create a container.';
  $('validation-message').classList.toggle('invalid', !selected.size);
  const alreadyQueued = isActive(state.job) && sameDesign(state.job.configuration, state.draft);
  $('generate-bins').disabled = !selected.size || state.recovering || state.submitting || Boolean(alreadyQueued);
  $('generate-text').textContent = state.recovering ? 'Checking saved jobs…' : state.submitting ? 'Submitting…' : alreadyQueued ? 'Build in progress…' : isActive(state.job) ? 'Add to queue' : 'Generate containers';
  $('undo-layout').disabled = !state.undo.length;
  $('draft-note').hidden = !state.selected || sameDesign(state.selected.configuration, state.draft);
}
function targetAt(event) { return document.elementFromPoint(event.clientX, event.clientY)?.closest('#drawer-grid [data-kind]'); }
function applyPaint(target, erase) {
  if (!target) return false;
  const x = Number(target.dataset.x), y = Number(target.dataset.y), selected = cells();
  if (target.dataset.kind === 'cell' && state.tool !== 'dividers') {
    const key = cellKey(x, y); if (erase === !selected.has(key)) return false;
    if (erase) state.draft.cells = state.draft.cells.filter(([cx, cy]) => cx !== x || cy !== y);
    else state.draft.cells.push([x, y]);
    cleanDividers(); return true;
  }
  if (target.dataset.kind === 'divider' && state.tool !== 'cells') {
    const d = { axis: target.dataset.axis, x, y }; if (!validDivider(d, selected)) return false;
    const exists = state.draft.dividers.some(edge => dividerKey(edge) === dividerKey(d)); if (erase === !exists) return false;
    if (erase) state.draft.dividers = state.draft.dividers.filter(edge => dividerKey(edge) !== dividerKey(d));
    else state.draft.dividers.push(d);
    return true;
  }
  return false;
}
$('drawer-grid').addEventListener('pointerdown', event => {
  if (!state.draft || event.button !== 0) return;
  const target = event.target.closest('[data-kind]'); if (!target || (state.tool === 'dividers' && target.dataset.kind !== 'divider')) return;
  event.preventDefault(); remember();
  const erase = state.tool === 'erase' || target.getAttribute('aria-pressed') === 'true';
  state.stroke = { erase, pointer: event.pointerId }; $('drawer-grid').setPointerCapture(event.pointerId);
  if (applyPaint(target, erase)) edited();
});
$('drawer-grid').addEventListener('pointermove', event => { if (state.stroke?.pointer === event.pointerId && applyPaint(targetAt(event), state.stroke.erase)) edited(); });
for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) $('drawer-grid').addEventListener(type, () => { state.stroke = null; });
$('drawer-grid').addEventListener('keydown', event => {
  const target = event.target.closest('[data-kind]'); if (!target) return;
  if ([' ', 'Enter'].includes(event.key)) {
    event.preventDefault(); remember(); if (applyPaint(target, state.tool === 'erase' || target.getAttribute('aria-pressed') === 'true')) edited();
  } else if (target.dataset.kind === 'cell' && event.key.startsWith('Arrow')) {
    const delta = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key]; if (!delta) return;
    event.preventDefault(); $('drawer-grid').querySelector(`[data-kind=cell][data-x="${Number(target.dataset.x) + delta[0]}"][data-y="${Number(target.dataset.y) + delta[1]}"]`)?.focus();
  }
});
for (const button of document.querySelectorAll('button[data-tool]')) button.addEventListener('click', () => {
  state.tool = button.dataset.tool;
  $('tool-hint').textContent = { cells: 'Click or drag across squares. Joined squares make one container.', dividers: 'Click or drag along lines between painted cells. Click a divider again to remove it.', erase: 'Click or drag to remove cells and dividers. Empty cells leave space in the drawer.' }[state.tool]; render();
});
for (const [id, action] of [['fill-drawer', () => { state.draft.cells = fullGrid(); }], ['clear-layout', () => { state.draft.cells = []; state.draft.dividers = []; }], ['clear-dividers', () => { state.draft.dividers = []; }]]) $(id).addEventListener('click', () => { if (!state.draft) return; remember(); action(); edited(); });
$('apply-balanced-design').addEventListener('click', () => {
  if (!state.draft || containerType(state.draft) !== 'drawer') return;
  remember(); state.draft.wall_pattern = state.config.balanced_design.wall_pattern; state.draft.wall_perimeters = state.config.balanced_design.wall_perimeters; edited();
  announce('Balanced starting point applied: Miura-ori sides and dividers with two perimeter walls. Your layout is unchanged.');
});
$('undo-layout').addEventListener('click', () => { if (state.undo.length) { state.draft = state.undo.pop(); edited({ rebuild: true }); } });

async function setView(view) {
  state.view = view; const model = view === 'model'; ++state.modelRequest;
  $('layout-panel').hidden = model; $('model-panel').hidden = !model; $('reset-bin-view').hidden = !model;
  $('layout-view').setAttribute('aria-pressed', String(!model)); $('model-view').setAttribute('aria-pressed', String(model));
  if (model) await loadModel();
}
async function loadModel() {
  const build = state.selected, part = build?.parts?.[Number($('preview-part').value) || 0]; if (!part) return;
  const request = ++state.modelRequest; $('bin-model').dataset.modelReady = 'false'; state.viewer?.clear();
  $('model-message').textContent = 'Loading checked container…'; $('model-message').hidden = false;
  $('model-caption').textContent = `${describe(build.configuration)} · ${part.name} · base-down print orientation`;
  try {
    if (typeof part.stl_url !== 'string' || !/^\/files\/[^\s]*$/.test(part.stl_url) || part.stl_url.includes('\\')) throw new Error('This container has no preview mesh. Downloads remain available.');
    const response = await fetch(part.stl_url); if (!response.ok) throw new Error(response.status === 401 ? 'Sign in again to preview this container.' : 'The preview could not be loaded. Downloads remain available.');
    const bytes = await response.arrayBuffer(); if (request !== state.modelRequest || state.view !== 'model') return;
    state.viewer ||= new STLViewer($('bin-model')); state.viewer.load(bytes); $('bin-model').dataset.modelReady = 'true'; $('model-message').hidden = true;
  } catch (error) { if (request === state.modelRequest) { $('model-message').textContent = errorMessage(error); $('model-message').hidden = false; } }
}
function showBuild(build, bundleUrl) {
  state.selected = build; $('bin-downloads').hidden = false; $('model-view').disabled = !(build.parts || []).length;
  $('artifact-name').textContent = `${build.name} · ${describe(build.configuration)}`;
  const metrics = build.design_metrics, metric = value => Number(value.toFixed(2));
  const hasMetrics = metrics && ['material_volume_cm3', 'clear_height_mm', 'base_thickness_mm', 'wall_thickness_mm'].every(key => Number.isFinite(metrics[key]) && metrics[key] > 0);
  $('design-metrics').hidden = !hasMetrics;
  $('design-metrics').textContent = hasMetrics ? `CAD material: ${metric(metrics.material_volume_cm3)} cm³ · Clear height: ${metric(metrics.clear_height_mm)} mm · Base: ${metric(metrics.base_thickness_mm)} mm · Walls: ${metric(metrics.wall_thickness_mm)} mm` : '';
  downloadLink($('download-zip'), bundleUrl || build.bundle_url);
  $('artifact-freshness').hidden = !build.freshness?.warning; $('artifact-freshness').textContent = (build.freshness?.reasons || []).join(' ') || 'Regenerate for the current revision.';
  $('part-downloads').replaceChildren(); $('preview-part').replaceChildren();
  for (const [index, part] of (build.parts || []).entries()) {
    const row = node('div', 'bin-part-row'); row.append(node('span', '', part.name));
    for (const [label, url] of [['STL ↓', part.stl_url], ['STEP ↓', part.print_step_url || part.step_url]]) { const link = node('a', '', label); downloadLink(link, url); row.append(link); }
    $('part-downloads').append(row); const option = node('option', '', part.name); option.value = index; $('preview-part').append(option);
  }
  render();
}
function viewBuild(build, bundleUrl) { showBuild(build, bundleUrl); setView('model'); announce('Showing a saved container build. The layout draft is unchanged.'); }
function renderJob(job) {
  $('job-queue-link').href = `/queue?job=${encodeURIComponent(job.id)}`;
  state.job = job; $('bin-job-panel').hidden = false;
  $('job-title').textContent = { queued: 'Containers queued', running: 'Generating containers', completed: 'Your containers are ready', failed: 'Container generation failed', cancelled: 'Containers cancelled' }[job.status] || 'Container build';
  $('job-description').textContent = `${describe(job.configuration)}${isActive(job) ? ' · Building continues if you close this page.' : ''}`;
  $('job-status').textContent = job.status; $('job-indicator').className = `job-indicator${isActive(job) ? '' : job.status === 'failed' ? ' failed' : ' done'}`;
  $('job-error').hidden = !job.error; $('job-error').textContent = job.error || ''; $('job-log').textContent = job.logs || 'Waiting for the build worker…';
  if (job.status === 'failed') $('job-log-details').open = true;
  const build = job.builds?.find(item => item.kind === KIND); $('view-job-result').hidden = !build;
  if (job.status === 'completed' && state.completedJob !== job.id) {
    state.completedJob = job.id;
    if (build) { if (state.version === state.submittedVersion) viewBuild(build, job.bundle_url); else if (!state.selected) showBuild(build, job.bundle_url); }
    refreshHistory().catch(connectionError); announce('Containers complete. STL and STEP downloads are ready.');
  }
  render();
}
async function pollJob(id) {
  clearTimeout(state.pollTimer);
  try { const job = await api(`/api/jobs/${encodeURIComponent(id)}`); if (state.job?.id !== id) return; renderJob(job); connectionError(null); if (isActive(job)) state.pollTimer = setTimeout(() => pollJob(id), 1800); }
  catch (error) { connectionError(error); if (isActive(state.job)) state.pollTimer = setTimeout(() => pollJob(id), 5000); }
}
async function refreshHistory() {
  const response = await api('/api/builds'), builds = (response.builds || []).filter(build => build.kind === KIND); $('bin-history').replaceChildren();
  if (!builds.length) $('bin-history').append(node('p', 'empty-history', 'No containers generated yet.'));
  for (const build of builds.slice(0, 12)) {
    const button = node('button', 'history-card'), text = node('span'); button.type = 'button';
    text.append(node('strong', '', build.name), node('small', '', describe(build.configuration))); button.append(node('span', 'bin-history-icon', '▦'), text);
    button.addEventListener('click', () => { state.version++; viewBuild(build); }); $('bin-history').append(button);
  }
}
$('bin-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!state.draft?.cells.length || state.recovering || state.submitting || (isActive(state.job) && sameDesign(state.job.configuration, state.draft))) return;
  state.submitting = true; state.submittedVersion = state.version; render(); connectionError(null);
  try { const job = await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(state.draft) }); storage('vault-bin-job', job.id); renderJob(job); if (isActive(job)) pollJob(job.id); }
  catch (error) { connectionError(error); } finally { state.submitting = false; render(); }
});
$('layout-view').addEventListener('click', () => setView('layout'));
$('model-view').addEventListener('click', () => { if (state.selected) setView('model'); });
$('preview-part').addEventListener('change', loadModel);
$('reset-bin-view').addEventListener('click', () => state.viewer?.reset());
$('view-job-result').addEventListener('click', () => { const build = state.job?.builds?.find(item => item.kind === KIND); if (build) { state.version++; viewBuild(build, state.job.bundle_url); } });
$('refresh-bins').addEventListener('click', async () => { try { await refreshHistory(); connectionError(null); } catch (error) { connectionError(error); } });
$('retry-jobs').addEventListener('click', recoverJobs);
async function recoverJobs() {
  state.recovering = true; $('retry-jobs').hidden = true; render();
  try {
    const response = await api('/api/jobs');
    const jobs = (response.jobs || []).filter(job => job.configuration?.part === KIND), remembered = storage('vault-bin-job');
    let job = jobs.find(item => item.id === remembered);
    if (!job && typeof remembered === 'string') {
      // Distinguish a removed old job from a connection failure: a failed
      // recovery must not silently enable another submission.
      const response = await fetch(`/api/jobs/${encodeURIComponent(remembered)}`, { cache: 'no-store' });
      if (response.status !== 404) {
        if (!response.ok) throw new Error(response.status === 401 ? 'Session expired. Refresh to sign in; an existing build may still be running.' : 'Saved build recovery failed. Retry before generating.');
        const saved = await response.json(); if (saved.configuration?.part === KIND) job = saved;
      }
    }
    job ||= jobs.find(isActive);
    if (job) { storage('vault-bin-job', job.id); state.submittedVersion = sameDesign(job.configuration, state.draft) ? state.version : -1; renderJob(job); if (isActive(job)) pollJob(job.id); }
    state.recovering = false; connectionError(null);
  } catch (error) { connectionError(error); $('retry-jobs').hidden = false; }
  render();
}
function restore(saved) {
  if (!saved || saved.part !== KIND || !['gridfinity', 'drawer'].includes(containerType(saved)) || !state.config.families.some(f => f.id === saved.family) || !state.config.depths.includes(saved.depth_units) || !state.config.heights.includes(saved.height_units) || !state.config.wall_patterns.some(p => p.id === saved.wall_pattern) || !state.config.wall_perimeters.includes(saved.wall_perimeters)) return null;
  if (containerType(saved) === 'drawer' && (!supportsDrawer() || !(state.config.drawer_floors || []).includes(drawerFloor(saved)))) return null;
  if (!Array.isArray(saved.cells) || saved.cells.length > 42 || !saved.cells.every(c => Array.isArray(c) && c.length === 2 && c.every(Number.isInteger) && c[0] >= 0 && c[0] < columns(saved) && c[1] >= 0 && c[1] < saved.depth_units)) return null;
  const selected = new Set(saved.cells.map(([x, y]) => cellKey(x, y)));
  if (selected.size !== saved.cells.length || !Array.isArray(saved.dividers) || saved.dividers.length > 71 || !saved.dividers.every(d => validDivider(d, selected)) || new Set(saved.dividers.map(dividerKey)).size !== saved.dividers.length) return null;
  return { part: KIND, ...(containerType(saved) === 'drawer' ? { container_type: 'drawer', drawer_floor: drawerFloor(saved) } : {}), family: saved.family, depth_units: saved.depth_units, height_units: saved.height_units, cells: saved.cells.map(c => [...c]), dividers: saved.dividers.map(({ axis, x, y }) => ({ axis, x, y })), wall_pattern: saved.wall_pattern, wall_perimeters: saved.wall_perimeters };
}
async function initialize() {
  try {
    state.config = await api('/api/gridfinity/config'); state.draft = structuredClone(state.config.defaults);
    state.draft.part = KIND; state.draft.cells ||= fullGrid(); state.draft.dividers ||= [];
    state.draft = restore(storage('vault-bin-draft')) || state.draft; normalize();
    for (const [id, key, options] of [
      ['bin-type-options', 'container_type', [['gridfinity', 'Gridfinity'], ...(supportsDrawer() ? [['drawer', 'Drawer-fit box']] : [])]],
      ['bin-family-options', 'family', state.config.families.map(f => [f.id, f.id, `${f.columns} columns`])],
      ['bin-depth-options', 'depth_units', state.config.depths.map(v => [v, String(v)])],
      ['bin-height-options', 'height_units', state.config.heights.map(v => [v, `${v}F`])],
      ['bin-floor-options', 'drawer_floor', (state.config.drawer_floors || []).map(v => [v, `${v} mm`])],
      ['bin-pattern-options', 'wall_pattern', state.config.wall_patterns.map(p => [p.id, p.label])],
      ['bin-perimeter-options', 'wall_perimeters', state.config.wall_perimeters.map(v => [v, `${v} perimeter${v === 1 ? '' : 's'}`])]]) {
      for (const [value, label, hint] of options) {
        const button = node('button', hint ? 'option' : ''); button.type = 'button'; button.dataset.setting = key; button.dataset.value = value;
        if (hint) { button.append(node('span', 'family-letter', label), node('span', 'family-width', hint)); button.setAttribute('aria-label', `${label} drawer, ${hint}`); } else button.textContent = label;
        button.addEventListener('click', () => change(key, value)); $(id).append(button);
      }
    }
    createGrid(); render();
    const results = await Promise.allSettled([refreshHistory(), recoverJobs()]);
    if (results[0].status === 'rejected') connectionError(results[0].reason);
    if (results[1].status === 'rejected') connectionError(results[1].reason);
  } catch (error) { connectionError(error); }
}
initialize();
setInterval(() => { if (state.config) refreshHistory().catch(connectionError); }, 15000);
