import { STLViewer } from './stl-viewer.js';
import { api, downloadLink, errorMessage, isActive } from './client.js';

const $ = id => document.getElementById(id);
const state = {
  builds: [], repository: null, browsingSelection: true,
  config: null, selection: null, job: null, artifacts: [], selectedArtifact: null,
  viewer: null, previewRequest: 0, navigationVersion: 0, jobNavigationVersion: 0, submitting: false,
  shownCompletedJob: null, shownFailedJob: null, pollTimer: null,
  assembly: null, assemblySignature: null, assemblyKey: null, assemblyRequest: 0,
  assemblyController: null, assemblyPending: false, assemblyShowing: false,
  hiddenInstances: new Set(), selectedInstance: null,
  minimumFloor: 0.8,
};
const names = {
  set: 'Complete set', module: 'Module', box: 'Box', facade: 'Facade',
  key: 'Key', spring: 'Spring', runner_stop: 'Runner stop', facade_cap: 'Facade cap', key_cap: 'Key cap', latch: 'Latch',
  rails: 'Geared rails', runner_guides: 'Runner guides', runner_slides: 'Runner slides',
};
// Preview palette; exported multicolor parts retain their named filament roles.
const assemblyColorRoles = {
  module: 'primary', facade: 'primary', runner_guides: 'primary', facade_cap: 'primary', key_cap: 'primary',
  box: 'secondary', runner_slides: 'secondary', key: 'secondary',
  rails: 'highlight', spring: 'highlight', runner_stop: 'highlight', latch: 'highlight',
};
const assemblyColor = instance => $(`assembly-${assemblyColorRoles[instance.kind] || 'primary'}-color`).value;
const materialColor = material => $(`assembly-${material.role}-color`).value;
const previewMaterials = instance => instance.material_meshes?.length ? instance.material_meshes : [{mesh_url: instance.mesh_url}];
const partDescriptions = {
  set: 'Module, box, facade, geared rails, runner guides, runner slides, key, spring, latch, runner stops and caps.',
  module: 'The outside shell, sized by family, depth and height.',
  box: 'The drawer tray, sized to fit the selected module.',
  facade: 'The drawer front follows family and height; depth does not change it.',
  rails: 'The geared locking rails follow family; depth and height do not change them.',
  key: 'Universal single-piece key with an integrated drive pinion. Print one per drawer.',
  spring: 'Universal spring at nominal dimensions. Print two per drawer.',
  latch: 'Universal underside latch with 0.10 mm outline relief and 0.15 mm less thickness for an easier fit.',
  runner_stop: 'Universal runner stop. Print two per populated runner tier.',
  facade_cap: 'Universal facade screw cap. Repeat for each screw counterbore.',
  key_cap: 'Universal cap for the key handle.',
  runner_guides: 'Guides follow depth; the same guides fit S, M and L at every height.',
  runner_slides: 'Slides follow depth; the same slides fit S, M and L at every height.',
};
const configurationName = config => [
  `${config.family || 'S'}${config.depth_units || ''}${config.drawer_columns === 2 ? '²' : ''}`,
  `${config.height_units || 1}F`, config.drawer_rows === 2 ? '4 drawers' : '',
  (config.wall_perimeters != null ? ['set','module','box'] : ['set','module']).includes(config.part) && config.wall_perimeters !== 'full' ? {waffle:'Waffle', miura:'Miura-ori'}[config.wall_pattern] : '',
  config.wall_perimeters == null && ['set','module'].includes(config.part) && config.wall_pattern !== 'plain' && config.pattern_construction === 'corrugated' ? 'Corrugated' : '',
  ['set','box'].includes(config.part) && config.box_variant === 'gridfinity' ? 'Gridfinity' : '',
  ['set','box'].includes(config.part) && config.box_floor === 0 ? 'Floorless' : '',
  config.wall_perimeters == null && ['set','box'].includes(config.part) ? {waffle:'Waffle rear', miura:'Miura-ori rear'}[config.box_rear_pattern] : '',
].filter(Boolean).join(' · ');
const drawerFamily = config => config.drawer_columns === 2 ? 'S' : config.family;
const drawerHeight = config => config.height_units / (config.drawer_rows || 1);
const drawerCount = config => (config.drawer_columns || 1) * (config.drawer_rows || 1);
const layoutCount = layout => layout.columns * (layout.rows || 1);
const patternKeys = ['wall_pattern', 'pattern_pitch', 'pattern_depth', 'wall_perimeters', 'nozzle_size'];
const patternDefaults = {wall_pattern: 'plain', pattern_pitch: 14, pattern_depth: 1.7, wall_perimeters: 2, nozzle_size: 0.6};
const moduleSelected = () => ['set', 'module'].includes(state.selection.part);
const boxSelected = () => ['set', 'box'].includes(state.selection.part);
const wallsSelected = () => moduleSelected() || boxSelected();
const thicknessApplies = key => state.selection.part === 'set'
  || (state.config.thickness_applicability?.[key] ?? {minimum_floor: ['box', 'facade'], perimeters: ['module', 'box']}[key]).includes(state.selection.part);
const closedBoxFloor = () => state.minimumFloor === 'default' ? 3 : 0.8;
const defaultPattern = () => Object.fromEntries(patternKeys.map(key => [key, state.config.defaults[key] ?? patternDefaults[key]]));
const requestConfiguration = () => {
  const request = {...state.selection};
  // Historical fields remain readable in saved builds; current selections have
  // one wall pattern and nozzle-derived thickness for both component types.
  for (const key of ['box_rear_pattern', 'pattern_faces', 'pattern_construction', 'pattern_line_width']) delete request[key];
  if (!wallsSelected()) Object.assign(request, defaultPattern(), {wall_pattern: 'plain'});
  if (request.wall_perimeters === 'full') request.wall_pattern = 'plain';
  if (!boxSelected()) Object.assign(request, {box_variant: 'plain', box_floor: state.selection.box_floor || closedBoxFloor()});
  return request;
};
const svgIcon = name => {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.classList.add('icon');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use'); use.setAttribute('href', `#i-${name}`); svg.append(use); return svg;
};
const element = (tag, className, text) => {
  const node = document.createElement(tag); if (className) node.className = className;
  if (text !== undefined) node.textContent = text; return node;
};
const announce = text => { $('announcement').textContent = text; };
function connectionError(error) {
  $('connection-error').textContent = error ? errorMessage(error) : '';
  $('connection-error').hidden = !error;
}
function rememberJob(id) { try { localStorage.setItem('vault-active-job', id); } catch { /* Storage may be disabled. */ } }
function rememberedJob() { try { return localStorage.getItem('vault-active-job'); } catch { return null; } }

function optionButton(value, key, label, className) {
  const button = element('button', className); button.type = 'button'; button.dataset.value = String(value);
  button.setAttribute('aria-label', label); button.setAttribute('aria-pressed', 'false');
  button.addEventListener('click', () => {
    state.navigationVersion++; state.browsingSelection = true;
    if (key === 'drawer_layout') {
      const layout = state.config.drawer_layouts.find(item => layoutCount(item) === value);
      state.selection.drawer_columns = layout.columns; state.selection.drawer_rows = layout.rows || 1;
    } else if (key === 'minimum_floor') {
      state.minimumFloor = value;
      state.selection.facade_floor = value;
      if (state.selection.box_floor !== 0) state.selection.box_floor = closedBoxFloor();
    } else if (key === 'box_bottom') {
      state.selection.box_floor = value === 'floorless' ? 0 : closedBoxFloor();
    } else state.selection[key] = value;
    if (key === 'family' && value !== 'L') {
      state.selection.drawer_columns = 1; state.selection.drawer_rows = 1;
    }
    if (key === 'height_units' && value !== 2) state.selection.drawer_rows = 1;
    if (key === 'wall_pattern' && value === 'plain') {
      const defaults = defaultPattern();
      state.selection.pattern_pitch = defaults.pattern_pitch; state.selection.pattern_depth = defaults.pattern_depth;
    }
    if (key === 'wall_perimeters' && value === 'full') state.selection.wall_pattern = 'plain';
    if (key === 'box_variant' && value === 'plain' && state.selection.box_floor === 0) state.selection.box_floor = closedBoxFloor();
    renderSelection(); showSelection();
  });
  return button;
}
function createControls(config) {
  for (const family of config.families) {
    const button = optionButton(family.id, 'family', `${family.id}, ${family.width_mm} millimeters wide`, 'option');
    button.append(element('span', 'family-letter', family.id), element('span', 'family-width', `${family.width_mm} mm`));
    $('family-options').append(button);
  }
  for (const layout of config.drawer_layouts) {
    const count = layoutCount(layout), label = {1: 'One drawer', 2: 'Two S drawers', 4: 'Four S drawers'}[count];
    const button = optionButton(count, 'drawer_layout', label, '');
    button.textContent = label; $('drawer-layout-options').append(button);
  }
  for (const [values, key, target] of [[config.depths, 'depth_units', 'depth-options'], [config.heights, 'height_units', 'height-options']]) {
    for (const value of values) {
      const button = optionButton(value, key, `${value} ${key === 'depth_units' ? 'depth units' : 'floors'}`, '');
      button.textContent = key === 'height_units' ? `${value}F` : value; $(target).append(button);
    }
  }
  for (const [key, target, values] of [
    ['minimum_floor', 'minimum-floor-options', [[0.8, '0.8 mm'], ['default', 'Default']]],
    ['wall_perimeters', 'perimeters-options', (config.wall_perimeters || [{id:1,name:'1 perimeter'}, {id:2,name:'2 perimeters'}, {id:'full',name:'Full width'}]).map(option => [option.id, option.name])],
    ['nozzle_size', 'nozzle-options', (config.nozzle_sizes || [0.6, 0.8]).map(value => [value, `${value} mm`])],
    ['box_bottom', 'box-bottom-options', [['closed', 'Closed'], ['floorless', 'Floorless']]],
  ]) {
    for (const [value, label] of values) {
      const button = optionButton(value, key, label, ''); button.textContent = label; $(target).append(button);
    }
  }
  for (const [values, key, target] of [
    [config.box_variants || [{id:'plain', name:'Plain'}, {id:'gridfinity', name:'Gridfinity'}], 'box_variant', 'box-variant-options'],
    [config.wall_patterns || [{id:'plain', name:'Plain'}, {id:'miura', name:'Miura-ori'}], 'wall_pattern', 'wall-pattern-options'],
  ]) {
    for (const value of values) {
      const button = optionButton(value.id, key, value.name, ''); button.textContent = value.name; $(target).append(button);
    }
  }
  for (const [name, id] of [['pitch', 'pattern-pitch'], ['depth', 'pattern-depth']]) {
    const input = $(id), settings = config.pattern_settings?.[name];
    if (settings) { input.min = settings.min; input.max = settings.max; }
    input.addEventListener('input', () => {
      state.navigationVersion++; state.browsingSelection = true;
      state.selection[`pattern_${name}`] = input.valueAsNumber;
      renderSelection(); showSelection();
    });
  }
  let commonStarted = false;
  for (const part of config.parts) {
    if (part.common && !commonStarted) {
      const heading = element('div', 'common-components-heading', 'Common components');
      $('part-options').append(heading);
      commonStarted = true;
    }
    const button = optionButton(part.id, 'part', part.name, 'part-option');
    button.append(element('span', 'radio-dot'), element('span', '', names[part.id] || part.name));
    if (part.id === 'set') button.append(element('span', 'part-option-note', 'All matching parts'));
    $('part-options').append(button);
  }
}
function envelopeDimensions() {
  const family = state.config.families.find(item => item.id === state.selection.family);
  return [family.width_mm, 42 * state.selection.depth_units + 20.1, 48 * state.selection.height_units - 1];
}
function setMetrics(dimensions) {
  for (const [index, axis] of ['width', 'depth', 'height'].entries()) {
    const metric = $(`metric-${axis}`); metric.replaceChildren(document.createTextNode(`${Number(dimensions[index]).toFixed(1).replace(/\.0$/, '')} `), element('small', '', 'mm'));
  }
}
function renderEnvelope(dimensions) {
  const [width, depth, height] = dimensions;
  const scale = 390 / Math.max(width + depth * 0.55, 270);
  const point = (x, y, z) => [340 + (x - width / 2 + (y - depth / 2) * 0.53) * scale,
    233 + ((x - width / 2) * 0.16 - (y - depth / 2) * 0.39 - (z - height / 2)) * scale];
  const drawing = $('envelope-drawing'); drawing.replaceChildren();
  const polygon = (coordinates, fill, stroke = '#8ba9c1', opacity = 1) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    node.setAttribute('points', coordinates.map(p => point(...p).join(',')).join(' '));
    node.setAttribute('fill', fill); node.setAttribute('stroke', stroke); node.setAttribute('stroke-width', '1.3'); node.setAttribute('opacity', opacity); node.setAttribute('stroke-linejoin', 'round'); drawing.append(node);
  };
  polygon([[0, 0, 0], [width, 0, 0], [width, depth, 0], [0, depth, 0]], '#34424f', '#68849b', .28);
  polygon([[0, depth, 0], [width, depth, 0], [width, depth, height], [0, depth, height]], '#28333d');
  polygon([[width, 0, 0], [width, depth, 0], [width, depth, height], [width, 0, height]], '#314150');
  polygon([[0, 0, height], [width, 0, height], [width, depth, height], [0, depth, height]], '#3e5263');
  polygon([[0, 0, 0], [width, 0, 0], [width, 0, height], [0, 0, height]], '#485e70');
  const insetX = Math.min(10, width * .06), insetZ = Math.min(5, height * .15);
  polygon([[insetX, 0, insetZ], [width-insetX, 0, insetZ], [width-insetX, 0, height-insetZ], [insetX, 0, height-insetZ]], '#24323e');
  polygon([[insetX+3, 0, insetZ+3], [width-insetX-3, 0, insetZ+3], [width-insetX-3, 0, height-insetZ-3], [insetX+3, 0, height-insetZ-3]], '#304352', '#7591a7');
  if (state.selection.drawer_columns === 2) {
    polygon([[width/2-4, 0, insetZ], [width/2+4, 0, insetZ], [width/2+4, 0, height-insetZ], [width/2-4, 0, height-insetZ]], '#485e70');
  }
  const line = (a, b) => {
    const p = point(...a), q = point(...b), node = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    node.setAttribute('d', `M${p} L${q}`); node.setAttribute('stroke', '#7e95a8'); node.setAttribute('stroke-width', '1'); node.setAttribute('stroke-dasharray', '3 4'); drawing.append(node);
  };
  line([0, 0, -17], [width, 0, -17]); line([width+18, 0, 0], [width+18, depth, 0]);
  const label = (x, y, z, text) => {
    const [px, py] = point(x,y,z), node = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    node.setAttribute('x', px); node.setAttribute('y', py + 15); node.setAttribute('text-anchor', 'middle');
    node.setAttribute('font-family', 'inherit'); node.setAttribute('font-size', '10'); node.setAttribute('fill', '#b5c3cf'); node.textContent = text; drawing.append(node);
  };
  label(width/2,0,-17,`${width} mm`); label(width+25,depth/2,0,`${depth.toFixed(1)} mm`);
}
function renderSelection() {
  for (const [target, key] of [['family-options','family'], ['depth-options','depth_units'], ['height-options','height_units'], ['part-options','part'], ['box-variant-options','box_variant'], ['perimeters-options','wall_perimeters'], ['nozzle-options','nozzle_size'], ['wall-pattern-options','wall_pattern']]) {
    for (const button of $(target).querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.value === String(state.selection[key])));
  }
  const dimensions = envelopeDimensions(), config = state.selection;
  for (const button of $('minimum-floor-options').querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.value === String(state.minimumFloor)));
  for (const button of $('box-bottom-options').querySelectorAll('button')) button.setAttribute('aria-pressed', String((button.dataset.value === 'floorless') === (config.box_floor === 0)));
  for (const button of $('drawer-layout-options').querySelectorAll('button')) {
    const layout = state.config.drawer_layouts.find(item => layoutCount(item) === Number(button.dataset.value));
    button.disabled = !layout.families.includes(config.family) || (layout.heights && !layout.heights.includes(config.height_units));
    button.setAttribute('aria-pressed', String(layoutCount(layout) === drawerCount(config)));
  }
  $('drawer-layout-hint').textContent = config.drawer_rows === 2
    ? 'Four S1F drawers: two across and two high in the shared open L2F module. Print each matching drawer four times.'
    : config.drawer_columns === 2
      ? `Two S${config.height_units}F drawers side by side.${config.height_units === 2 ? ' The same open module also fits four S1F drawers.' : ' Choose 2F for four drawers.'} Print each matching drawer twice.`
      : `One ${config.family} drawer. Choose L for two S drawers, or L2F for four.`;
  $('depth-hint').textContent = `${dimensions[1].toFixed(1)} mm deep`;
  $('height-hint').textContent = `${dimensions[2]} mm body height`;
  $('configuration-name').textContent = configurationName(config);
  $('configuration-dimensions').textContent = `${dimensions[0]} × ${dimensions[1].toFixed(1)} × ${dimensions[2]} mm body`;
  $('part-hint').textContent = partDescription(config);
  $('box-variant-field').hidden = !boxSelected();
  $('box-bottom-field').hidden = !boxSelected() || config.box_variant !== 'gridfinity';
  $('minimum-floor-field').hidden = !thicknessApplies('minimum_floor') || (config.part === 'box' && config.box_floor === 0);
  $('perimeters-field').hidden = !thicknessApplies('perimeters');
  $('nozzle-field').hidden = !wallsSelected();
  for (const button of $('nozzle-options').querySelectorAll('button')) button.disabled = config.wall_perimeters === 'full';
  $('perimeters-hint').textContent = config.wall_perimeters === 'full'
    ? 'Full width keeps the original solid walls. Select 1 or 2 perimeters to use thin plain or Miura-ori walls.'
    : `Thin sections target ${(config.wall_perimeters * (config.nozzle_size === 0.8 ? 0.85 : 0.65)).toFixed(2)} mm for ${config.wall_perimeters} ${config.wall_perimeters === 1 ? 'perimeter' : 'perimeters'} with a ${config.nozzle_size} mm nozzle. Use Arachne and check the sliced paths; reinforced lands remain thicker.${boxSelected() && config.wall_perimeters === 2 && config.nozzle_size === 0.8 ? ' Box cavity is 0.8 mm narrower; existing drawer-fit inserts need resizing.' : ''}`;
  $('minimum-floor-hint').textContent = config.part === 'facade' || (config.part === 'set' && config.box_floor === 0)
    ? 'Applies to the facade shell. Edges, lock and screw supports retain their reinforcement.'
    : config.part === 'set' ? 'Applies to box floors and facade shells. Reinforced features keep their thickness.'
      : 'Applies to the box floor.';
  $('box-variant-hint').textContent = config.box_variant === 'gridfinity'
    ? `Integrated ${({S: 3, M: 5, L: 6})[drawerFamily(config)]} × ${config.depth_units} Gridfinity grid inside each box, on a 42 mm pitch. ${config.box_floor === 0 ? 'Open cell bottoms; bins rest on the grid. The perimeter and grid webs support the box.' : 'Adds 5 mm above the selected floor.'}`
    : 'A plain interior floor. Choose Gridfinity to locate bins on an integrated grid inside the box.';
  if (!state.selectedArtifact && !state.assemblyShowing) {
    $('preview-title').textContent = configurationName(config);
    renderEnvelope(dimensions); setMetrics(dimensions);
  }
  renderPatternSettings();
  $('build-button').disabled = state.submitting || isActive(state.job) || Boolean(patternError());
  $('build-button-text').textContent = state.submitting ? 'Starting build…' : isActive(state.job) ? 'Build in progress…' : config.part === 'set' ? 'Generate complete set' : `Generate ${names[config.part].toLowerCase()}`;
}

function patternError() {
  if (!wallsSelected() || state.selection.wall_pattern === 'plain' || state.selection.wall_perimeters === 'full') return '';
  for (const [key, id, label] of [['pattern_pitch', 'pattern-pitch', 'Pitch'], ['pattern_depth', 'pattern-depth', 'Depth']]) {
    const input = $(id), value = state.selection[key];
    if (!Number.isFinite(value) || value < Number(input.min) || value > Number(input.max)) return `${label} must be between ${input.min} and ${input.max} mm.`;
  }
  return '';
}
function renderPatternSettings() {
  const full = state.selection.wall_perimeters === 'full';
  const enabled = wallsSelected() && state.selection.wall_pattern === 'miura' && !full;
  $('wall-pattern-field').hidden = !wallsSelected();
  $('wall-pattern-settings').hidden = !enabled;
  for (const button of $('wall-pattern-options').querySelectorAll('button')) button.disabled = full;
  for (const [key, id] of [['pattern_pitch', 'pattern-pitch'], ['pattern_depth', 'pattern-depth']]) {
    const input = $(id); input.disabled = !enabled;
    if (document.activeElement !== input) input.value = Number.isFinite(state.selection[key]) ? state.selection[key] : '';
  }
  const error = patternError();
  $('wall-pattern-error').hidden = !error; $('wall-pattern-error').textContent = error;
  for (const id of ['pattern-pitch', 'pattern-depth']) $(id).setAttribute('aria-invalid', String(Boolean(error)));
  const surfaces = state.selection.part === 'box' ? 'the box rear wall'
    : state.selection.part === 'module' ? 'all eligible module faces' : 'all eligible module faces and box rear walls';
  const runnerNote = boxSelected() ? ' Box runner backing also follows the perimeter and nozzle choices.' : '';
  $('wall-pattern-hint').textContent = full
    ? 'Original solid walls. Miura-ori is available with 1 or 2 perimeters.'
    : enabled
      ? `Miura-ori applies to ${surfaces}. Facet thickness follows the perimeter and nozzle choices; fold height is reduced as needed to fit the wall. Corners and mechanical lands stay solid.${runnerNote}`
      : `Plain thin sections apply to ${surfaces}. Corners and mechanical lands stay solid.${runnerNote}`;
}

function partDescription(config) {
  if (config.part === 'latch') return `${partDescriptions.latch} Print ${config.family === 'L' ? 'two' : 'one'}, one per module connector bank.`;
  if (config.drawer_columns !== 2) return partDescriptions[config.part] || '';
  const count = drawerCount(config), copies = count === 4 ? 'four' : 'two';
  const size = config.drawer_rows === 2 ? 'S1F' : 'S', pairs = count * drawerHeight(config);
  const quantity = {
    set: `One L² module, ${copies} ${size} boxes, ${copies} ${size} facades and ${copies} S geared rail pairs. Print ${pairs} pairs each of runner guides and slides, plus matching common components.`,
    module: config.height_units === 2 ? 'One L2F module with two open bays and shadow gaps for four drawer fronts. Fits two S2F drawers or four S1F drawers.' : 'One L module with two side-by-side S drawer bays.',
    box: `Matching ${size} drawer tray. Print ${copies} for the selected L² module.`,
    facade: `Matching ${size} drawer front. Print ${copies} for the selected L² module.`,
    rails: `Matching S geared rail pair. Print ${copies} pairs for the selected L² module.`,
    runner_guides: `Guides follow depth. Print ${pairs} pairs: one per tier in each drawer bay.`,
    runner_slides: `Slides follow depth. Print ${pairs} pairs: one per tier in each drawer bay.`,
    key: `Universal single-piece key. Print ${copies}, one per drawer.`,
    spring: `Universal spring at nominal dimensions. Print ${2 * count}, two per drawer.`,
    runner_stop: `Universal runner stop. Print ${2 * pairs}, two per populated tier in each drawer bay.`,
    facade_cap: `Universal facade screw cap. Print ${2 * pairs}, one per S facade screw counterbore.`,
    key_cap: `Universal cap for the key handle. Print ${copies} if desired, one per drawer.`,
  };
  return quantity[config.part] || partDescriptions[config.part] || '';
}

async function selectArtifact(index, userAction = false) {
  const artifact = state.artifacts[index]; if (!artifact) return;
  leaveAssembly();
  if (userAction) { state.navigationVersion++; state.browsingSelection = false; }
  const { build, part } = artifact; state.selectedArtifact = artifact;
  const request = ++state.previewRequest;
  for (const [i, button] of [...$('artifact-tabs').children].entries()) button.setAttribute('aria-pressed', String(i === index));
  renderFreshness(build);
  $('preview-eyebrow').textContent = 'SAVED BUILD';
  $('preview-title').textContent = build.name;
  $('preview-badge').textContent = 'Actual print STL';
  $('viewport-label').textContent = part.name;
  $('preview-kind').textContent = 'Print orientation · X / Y / Z';
  $('print-note').textContent = part.print_note || 'Shown in its exported print orientation. Dimensions are X × Y × Z.';
  $('artifact-description').textContent = `Saved ${formatDate(build.created_at)} · ${state.browsingSelection ? 'matches the current selection' : 'saved build; configuration unchanged'}`;
  if (part.print_bbox_mm?.length === 3) setMetrics(part.print_bbox_mm);
  downloadLink($('stl-download'), part.stl_url);
  downloadLink($('step-download'), part.step_url || build.step_url);
  downloadLink($('three-mf-download'), build.three_mf_url);
  $('envelope').setAttribute('hidden', ''); $('model-canvas').hidden = true;
  $('model-canvas').dataset.modelReady = 'false';
  $('viewer-message').hidden = false; $('viewer-message').textContent = 'Loading model…';
  $('viewer-help').hidden = true; $('reset-view').hidden = true;
  try {
    if (!part.stl_url?.startsWith('/files/')) throw new Error('This build has no preview mesh. Download STEP to inspect the solid.');
    const urls = part.material_meshes?.length ? part.material_meshes.map(material => material.print_url) : [part.stl_url];
    const buffers = await Promise.all(urls.map(async url => {
      if (!url?.startsWith('/files/')) throw new Error('Print material mesh unavailable; rebuild this part.');
      const response = await fetch(url);
      if (!response.ok) throw new Error(response.status === 401 ? 'Sign in again to load this preview.' : 'The preview could not be loaded. Download files below or retry this part.');
      return response.arrayBuffer();
    }));
    if (request !== state.previewRequest) return;
    $('model-canvas').hidden = false;
    state.viewer ||= new STLViewer($('model-canvas'));
    state.viewer.onSelect = null;
    const dimensions = part.material_meshes?.length
      ? state.viewer.loadScene(part.material_meshes.map((material, i) => ({id: material.name, bytes: buffers[i],
        color: materialColor(material), transform: [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1], explode: [0,0,0]})), {assembly: false})
      : state.viewer.load(buffers[0]); setMetrics(dimensions);
    $('viewer-message').hidden = true; $('viewer-help').hidden = false; $('reset-view').hidden = false;
    $('model-canvas').dataset.modelReady = 'true';
  } catch (error) {
    if (request !== state.previewRequest) return;
    $('viewer-message').textContent = errorMessage(error); $('model-canvas').dataset.modelReady = 'false';
    $('model-canvas').hidden = true;
  }
}
function showArtifacts(builds, bundleUrl = null, userAction = false, selectFirst = true) {
  state.artifacts = builds.flatMap(build => (build.parts || []).map(part => ({ build, part })));
  $('artifact-panel').hidden = state.artifacts.length === 0;
  downloadLink($('bundle-download'), bundleUrl);
  const tabs = $('artifact-tabs'); tabs.replaceChildren();
  for (const [index, { part }] of state.artifacts.entries()) {
    const button = element('button', 'artifact-tab', part.name); button.type = 'button'; button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => selectArtifact(index, true)); tabs.append(button);
  }
  if (state.artifacts.length && selectFirst) selectArtifact(0, userAction);
}
function renderFreshness(build = null) {
  const status = $('build-freshness'), info = build?.freshness, repo = state.repository;
  const warning = !repo || repo.dirty || (build && (!info || info.warning));
  const details = [...(info?.reasons || [])];
  if (!repo) details.unshift('Repository status unavailable.');
  else if (repo.dirty && !details.some(reason => reason.startsWith('Repository has uncommitted'))) {
    details.unshift('Repository has uncommitted changes; rebuild to include current code.');
  }
  if (build && !info) details.push('Cached build revision unknown; rebuild recommended.');
  status.hidden = false;
  status.classList.toggle('warning', Boolean(warning));
  status.textContent = repo?.dirty ? '⚠ Uncommitted changes' : warning ? '⚠ Check revision' : build ? '✓ Up to date' : '✓ Repository clean';
  status.title = details.length ? details.join(' ') : build
    ? 'Cached build matches the current clean commit.' : `Repository clean · ${repo.commit.slice(0, 8)}`;
  status.setAttribute('aria-label', `${status.textContent}. ${status.title}`);
}

function matches(build, kind) {
  if (build.kind !== kind || (kind === 'module' && build.legacy_partitioned_module)) return false;
  const c = build.configuration, s = state.selection;
  const keys = {module: ['family','depth_units','height_units','module_rear','drawer_columns'], box: ['family','depth_units','height_units','box_floor'], facade: ['family','height_units'], rails: ['family'], runner_guides: ['depth_units'], runner_slides: ['depth_units'], key: [], spring: [], runner_stop: [], facade_cap: [], key_cap: [], latch: []}[kind];
  const selected = kind === 'module' ? s : {...s, family: drawerFamily(s), height_units: drawerHeight(s)};
  if (kind === 'box' && (c.box_variant ?? 'plain') !== s.box_variant) return false;
  if (kind === 'facade' && (c.facade_floor ?? 'default') !== s.facade_floor) return false;
  if (kind === 'module' || kind === 'box') {
    // Missing wall_perimeters denotes a historical wall, including historical
    // plain builds. It must never satisfy a new thin-wall selection.
    if (c.wall_perimeters !== s.wall_perimeters) return false;
    if (s.wall_perimeters !== 'full') {
      if ((c.nozzle_size ?? 0.6) !== s.nozzle_size || (c.wall_pattern ?? 'plain') !== s.wall_pattern) return false;
      if (s.wall_pattern === 'miura' && !['pattern_pitch', 'pattern_depth'].every(key => (c[key] ?? patternDefaults[key]) === s[key])) return false;
    }
  }
  return keys.every(key => (c[key] ?? state.config.defaults[key]) === selected[key]);
}

function leaveAssembly() {
  state.assemblyController?.abort(); ++state.assemblyRequest;
  state.assemblyPending = false; state.assemblyShowing = false;
  state.assembly = null; state.assemblySignature = null;
  $('assembly-controls').hidden = true; $('assembly-panel').hidden = true;
  if (state.viewer) state.viewer.onSelect = null;
}
function setExplosion(value) {
  const amount = Math.max(0, Math.min(100, Number(value) || 0));
  $('explosion').value = amount; $('explosion-value').value = `${amount}%`;
  $('assemble-view').setAttribute('aria-pressed', String(amount === 0));
  $('explode-view').setAttribute('aria-pressed', String(amount === 100));
  if (state.assemblyShowing) {
    state.viewer?.setExplosion(amount / 100);
    $('preview-badge').textContent = amount === 0 ? 'Assembled' : amount === 100 ? 'Exploded' : `Exploded · ${amount}%`;
  }
}
function updateAssemblyColors() {
  if (!state.assemblyShowing || !state.assembly) return;
  const colors = Object.fromEntries(state.assembly.instances.map(instance => [instance.id, assemblyColor(instance)]));
  for (const instance of state.assembly.instances) for (const material of instance.material_meshes || []) {
    colors[`${instance.id}:${material.name}`] = materialColor(material);
  }
  state.viewer?.setColors(colors);
  for (const row of $('assembly-instances').children) {
    row.querySelector('.instance-color').style.backgroundColor = colors[row.dataset.instance];
  }
}
function selectInstance(id) {
  const instance = state.assembly?.instances.find(item => item.id === id);
  state.selectedInstance = instance?.id || null;
  state.viewer?.select(state.selectedInstance);
  for (const row of $('assembly-instances').children) {
    const selected = row.dataset.instance === state.selectedInstance;
    row.dataset.selected = String(selected); row.querySelector('button').setAttribute('aria-pressed', String(selected));
  }
  $('assembly-selection').textContent = instance
    ? `${instance.label} · ${names[instance.kind] || instance.kind} · build ${instance.build_id || 'unknown'}${state.hiddenInstances.has(instance.id) ? ' · hidden' : ''}`
    : 'Select a component in the view or list to highlight it.';
  $('viewport-label').textContent = instance?.label || `${state.assembly?.instances.length || 0} assembly components`;
}
function renderAssemblyDetails(scene) {
  const warnings = [...new Set([...(scene.warnings || []), ...scene.instances.flatMap(instance => instance.freshness?.reasons || [])])];
  if (state.repository?.dirty && !warnings.some(reason => reason.startsWith('Repository has uncommitted'))) warnings.unshift('Repository has uncommitted changes; rebuild to include current code.');
  if (!state.repository) warnings.unshift('Repository status unavailable.');
  const revisionReasons = scene.instances.flatMap(instance => instance.freshness?.warning ? instance.freshness.reasons || ['Cached build revision needs checking.'] : !instance.freshness ? ['Cached build revision unknown; rebuild recommended.'] : []);
  renderFreshness(scene.instances.length ? { freshness: { warning: revisionReasons.length > 0, reasons: [...new Set(revisionReasons)] } } : null);
  const fitStatus = scene.complete && scene.validation?.passed
    ? (scene.validation_scope === 'drawer_components' ? '✓ Drawer fit checked · accessory fit not checked' : '✓ Fit checked')
    : '⚠ Fit not verified for this view';
  $('assembly-summary').textContent = `${scene.instances.length} available components · ${scene.complete ? 'All generated parts available' : 'Incomplete set'} · ${fitStatus}`;
  if (scene.notes?.length) $('assembly-note').textContent = scene.notes.join(' ');
  $('assembly-omissions').hidden = !scene.omissions?.length;
  $('assembly-omissions').textContent = scene.omissions?.length ? `Not included: ${scene.omissions.join(', ')}.` : '';
  $('assembly-warnings').hidden = !warnings.length; $('assembly-warnings').textContent = warnings.length ? `⚠ ${warnings.join(' ')}` : '';
  const missing = $('assembly-missing'); missing.replaceChildren(); missing.hidden = !scene.missing.length;
  for (const item of scene.missing) missing.append(element('li', '', `${item.label || names[item.kind] || item.kind}: ${item.reason || 'Not generated yet; generate the complete set.'}`));
  $('selection-note').hidden = !scene.missing.length;
  $('selection-note').textContent = scene.missing.length ? '⚠ Incomplete assembly. Generate the complete set to build missing or older parts; details below.' : '';
  const list = $('assembly-instances'); list.replaceChildren();
  for (const instance of scene.instances) {
    const row = element('div', 'assembly-instance'); row.dataset.instance = instance.id;
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = !state.hiddenInstances.has(instance.id);
    checkbox.setAttribute('aria-label', `Show ${instance.label}`);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) state.hiddenInstances.delete(instance.id); else state.hiddenInstances.add(instance.id);
      state.viewer?.setVisible(instance.id, checkbox.checked); selectInstance(state.selectedInstance);
    });
    const button = element('button', 'instance-select'); button.type = 'button'; button.setAttribute('aria-label', `Highlight ${instance.label}`);
    const swatch = element('span', 'instance-color'); swatch.setAttribute('aria-hidden', 'true');
    swatch.style.backgroundColor = assemblyColor(instance);
    const text = element('span'); text.append(element('span', 'instance-label', instance.label));
    const warning = !instance.freshness || instance.freshness.warning;
    const revision = element('span', `instance-revision${warning ? ' warning' : ''}`, `${warning ? '⚠ Check revision' : '✓ Current'} · ${(instance.build_id || 'unknown build').slice(0, 12)}`);
    revision.title = instance.freshness?.reasons?.join(' ') || (warning ? 'Build revision unknown.' : 'Matches the current clean commit.');
    text.append(revision); button.append(swatch, text);
    button.addEventListener('click', () => selectInstance(state.selectedInstance === instance.id ? null : instance.id));
    row.append(checkbox, button); list.append(row);
  }
  selectInstance(state.selectedInstance);
}
async function showAssembly(preservePreview = false) {
  const query = new URLSearchParams(Object.fromEntries(['family', 'depth_units', 'height_units', 'box_floor', 'facade_floor', 'box_variant', 'module_rear', 'drawer_columns', 'drawer_rows', ...patternKeys].map(key => [key, requestConfiguration()[key]])));
  const key = query.toString(), newSelection = !state.assemblyShowing || state.assemblyKey !== key;
  if (preservePreview && !newSelection && state.assemblyPending) return;
  state.assemblyController?.abort();
  const controller = new AbortController(); state.assemblyController = controller;
  const request = ++state.assemblyRequest; state.assemblyPending = true;
  state.selectedArtifact = null; state.assemblyShowing = true;
  if (newSelection) {
    ++state.previewRequest; state.assemblyKey = key; state.assembly = null; state.assemblySignature = null;
    state.hiddenInstances.clear(); state.selectedInstance = null; setExplosion(0);
    $('model-canvas').hidden = true; $('model-canvas').dataset.modelReady = 'false';
    $('viewer-message').hidden = false; $('viewer-message').textContent = 'Loading assembled parts…';
    $('viewer-help').hidden = true; $('reset-view').hidden = true;
    $('assembly-panel').hidden = true; $('selection-note').hidden = true;
    setMetrics(envelopeDimensions());
  }
  $('envelope').setAttribute('hidden', ''); $('assembly-controls').hidden = false;
  $('preview-eyebrow').textContent = 'COMPLETE SET';
  $('preview-title').textContent = `${configurationName(state.selection)} assembly`;
  $('preview-kind').textContent = 'Complete-set view · X / Y / Z';
  const builds = Object.keys(names).filter(kind => kind !== 'set').map(kind => state.builds.find(build => matches(build, kind))).filter(Boolean);
  showArtifacts(builds, null, false, false);
  $('artifact-description').textContent = 'Printable downloads · select a part below to inspect its print orientation.';
  $('print-note').textContent = 'Complete set includes drawer parts and accessories. Accessory placement and retention are not fit checked. Print downloads retain required sacrificial supports.';
  downloadLink($('stl-download'), null); downloadLink($('step-download'), null);
  downloadLink($('three-mf-download'), null);
  renderFreshness();
  try {
    const response = await api(`/api/assembly?${query}`, { signal: controller.signal });
    if (request !== state.assemblyRequest) return;
    if (response.repository) state.repository = response.repository;
    const scene = { ...response, instances: response.instances || [], missing: response.missing || [] };
    const signature = JSON.stringify(scene.instances.map(({ id, mesh_url, material_meshes, transform, explode, color }) => ({ id, mesh_url, material_meshes, transform, explode, color })));
    $('preview-title').textContent = scene.name || `${configurationName(state.selection)} assembly`;
    if (signature === state.assemblySignature && state.assembly) {
      state.assembly = scene; renderAssemblyDetails(scene); return;
    }
    const urls = [...new Set(scene.instances.flatMap(instance => previewMaterials(instance).map(material => material.mesh_url)))];
    const fetched = await Promise.allSettled(urls.map(async url => {
      if (typeof url !== 'string' || !/^\/files\/[^\s]*$/.test(url) || url.includes('\\')) throw new Error('Finished assembly mesh unavailable; rebuild this part.');
      const mesh = await fetch(url, { signal: controller.signal });
      if (!mesh.ok) throw new Error(mesh.status === 401 ? 'Sign in again to load this component.' : 'Finished mesh could not be loaded; retry or rebuild this part.');
      return mesh.arrayBuffer();
    }));
    if (request !== state.assemblyRequest) return;
    const loaded = [], missing = [...scene.missing];
    for (const instance of scene.instances) {
      const materials = previewMaterials(instance).map(material => ({...material, result: fetched[urls.indexOf(material.mesh_url)]}));
      const failed = materials.find(material => material.result.status !== 'fulfilled');
      if (failed) missing.push({kind: instance.kind, label: instance.label, reason: errorMessage(failed.result.reason)});
      else loaded.push({...instance, meshes: materials.map(({result, ...material}) => ({...material, bytes: result.value}))});
    }
    const available = { ...scene, instances: loaded.map(({ meshes, ...instance }) => instance), missing, complete: scene.complete && !missing.length };
    if (loaded.length) {
      $('model-canvas').hidden = false;
      state.viewer ||= new STLViewer($('model-canvas'));
      const dimensions = state.viewer.loadScene(loaded.flatMap(({meshes, ...instance}) => meshes.map(material => ({
        ...instance, bytes: material.bytes, color_key: material.name ? `${instance.id}:${material.name}` : instance.id,
        color: material.role ? materialColor(material) : assemblyColor(instance),
      })))); setMetrics(dimensions);
      state.viewer.onSelect = selectInstance;
      state.viewer.setExplosion(Number($('explosion').value) / 100);
      for (const id of state.hiddenInstances) state.viewer.setVisible(id, false);
      state.viewer.fitCurrent();
      $('model-canvas').dataset.modelReady = 'true';
      $('viewer-message').hidden = true; $('viewer-help').hidden = false; $('reset-view').hidden = false;
    } else {
      state.viewer?.clear(); $('model-canvas').hidden = true; $('model-canvas').dataset.modelReady = 'false';
      $('viewer-help').hidden = true; $('reset-view').hidden = true;
      $('viewer-message').hidden = false;
      $('viewer-message').textContent = 'Assembly parts have not been generated yet. Generate the complete set to create finished assembly meshes.';
    }
    state.assembly = available; $('assembly-panel').hidden = false;
    // A failed mesh is retried on refresh; unchanged successful scenes preserve the camera.
    state.assemblySignature = fetched.every(result => result.status === 'fulfilled') ? signature : null;
    renderAssemblyDetails(available);
  } catch (error) {
    if (request !== state.assemblyRequest || error.name === 'AbortError') return;
    if (state.assembly) {
      $('assembly-warnings').hidden = false;
      $('assembly-warnings').textContent = `⚠ Could not refresh the assembly. ${errorMessage(error)}`;
    } else {
      $('viewer-message').hidden = false; $('viewer-message').textContent = errorMessage(error);
      $('model-canvas').hidden = true; $('model-canvas').dataset.modelReady = 'false';
    }
  } finally {
    if (request === state.assemblyRequest) state.assemblyPending = false;
  }
}

function showSelection(preservePreview = false) {
  if (patternError()) {
    leaveAssembly(); state.selectedArtifact = null; ++state.previewRequest;
    $('artifact-panel').hidden = true; $('model-canvas').hidden = true; $('model-canvas').dataset.modelReady = 'false';
    $('envelope').setAttribute('hidden', ''); $('viewer-help').hidden = true; $('reset-view').hidden = true;
    $('preview-eyebrow').textContent = 'SELECTION'; $('preview-title').textContent = configurationName(state.selection);
    $('preview-badge').textContent = 'Check settings'; $('selection-note').hidden = true;
    $('viewer-message').hidden = false; $('viewer-message').textContent = 'Correct the wall pattern settings to preview or generate this configuration.';
    return;
  }
  if (state.selection.part === 'set') { showAssembly(preservePreview); return; }
  leaveAssembly();
  const kinds = state.selection.part === 'set' ? Object.keys(names).filter(k => k !== 'set') : [state.selection.part];
  const builds = kinds.map(kind => state.builds.find(build => matches(build, kind))).filter(Boolean);
  const missing = kinds.filter(kind => !builds.some(build => build.kind === kind));
  $('selection-note').hidden = !missing.length;
  $('selection-note').textContent = missing.length ? `Not generated yet for this configuration: ${missing.map(k => names[k]).join(', ')}.` : '';
  if (preservePreview && state.selectedArtifact &&
      builds.flatMap(b => b.parts.map(p => `${b.id}/${p.name}`)).join() ===
      state.artifacts.map(a => `${a.build.id}/${a.part.name}`).join()) {
    renderFreshness(builds.find(b => b.id === state.selectedArtifact.build.id));
    return;
  }
  state.selectedArtifact = null; ++state.previewRequest;
  showArtifacts(builds);
  if (builds.length) return;
  renderFreshness();
  $('preview-eyebrow').textContent = 'SELECTION';
  $('preview-title').textContent = configurationName(state.selection);
  $('preview-badge').textContent = 'Not generated yet';
  $('model-canvas').hidden = true; $('model-canvas').dataset.modelReady = 'false';
  $('envelope').setAttribute('hidden', '');
  $('viewer-help').hidden = true; $('reset-view').hidden = true;
  $('viewer-message').hidden = false;
  $('viewer-message').textContent = 'This part has not been generated yet for this configuration.';
  $('viewport-label').textContent = names[state.selection.part];
  $('preview-kind').textContent = 'Selected module body dimensions';
  setMetrics(envelopeDimensions());
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'recently' : new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
}
async function refreshHistory() {
  const { builds: allBuilds, repository } = await api('/api/builds');
  const builds = allBuilds.filter(build => !['label', 'gridfinity_bins'].includes(build.kind));
  state.builds = builds; state.repository = repository;
  if (state.browsingSelection) showSelection(true);
  else if (state.selectedArtifact) renderFreshness(builds.find(b => b.id === state.selectedArtifact.build.id) || state.selectedArtifact.build);
  const list = $('history-list'); list.replaceChildren();
  if (!builds.length) { list.append(element('p', 'empty-history', 'No completed builds.')); return; }
  for (const build of builds.slice(0, 12)) {
    const button = element('button', 'history-card'); button.type = 'button';
    const icon = element('span', 'history-icon'); icon.append(svgIcon('cube'));
    const text = element('span'); text.append(element('strong', '', build.name), element('small', '', `${formatDate(build.created_at)} · ${(build.parts || []).length} printable ${(build.parts || []).length === 1 ? 'part' : 'parts'}`));
    button.append(icon, text, svgIcon('arrow')); button.addEventListener('click', () => {
      $('selection-note').hidden = true; showArtifacts([build], null, true); $('preview-title').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      announce(`Previewing saved ${build.name}. Configuration unchanged.`);
    }); list.append(button);
  }
}
function renderJob(job) {
  state.job = job; $('job-panel').hidden = false;
  const active = isActive(job), failed = job.status === 'failed';
  $('job-title').textContent = { queued: 'Build queued', running: 'Generating parts', completed: 'Build complete', failed: 'Build failed' }[job.status] || 'Build status';
  $('job-description').textContent = `${configurationName(job.configuration)} · ${names[job.configuration.part] || job.configuration.part}${active ? ' · Build continues when this page is closed.' : ''}`;
  $('job-status').textContent = job.status.charAt(0).toUpperCase() + job.status.slice(1);
  $('job-indicator').className = `job-indicator${failed ? ' failed' : active ? '' : ' done'}`;
  $('job-error').hidden = !job.error; $('job-error').textContent = job.error || '';
  $('job-artifacts-button').hidden = !(job.builds || []).some(build => build.parts?.length);
  $('job-artifacts-button').firstChild.textContent = failed ? 'View completed parts ' : 'View generated parts ';
  downloadLink($('job-bundle-download'), job.bundle_url);
  const log = $('build-log'), atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 50;
  log.textContent = job.logs || (job.status === 'queued' ? 'Waiting for the current CAD build to finish…' : 'Preparing the CAD builder…');
  if (atBottom) log.scrollTop = log.scrollHeight;
  $('log-line-count').textContent = job.logs ? `${job.logs.trim().split('\n').length} lines` : '';
  if (failed) $('build-log-details').open = true;
  renderSelection();
  if (job.status === 'completed' && state.shownCompletedJob !== job.id) {
    state.shownCompletedJob = job.id;
    if (state.navigationVersion === state.jobNavigationVersion && !state.browsingSelection) showArtifacts(job.builds || [], job.bundle_url);
    refreshHistory().catch(connectionError); announce(`${configurationName(job.configuration)} complete. Downloads available.`);
  }
  if (failed && state.shownFailedJob !== job.id) {
    state.shownFailedJob = job.id;
    refreshHistory().catch(connectionError);
    announce(`The build failed. ${(job.builds || []).length ? 'Completed parts are available to view.' : 'See the build log for details.'}`);
  }
}
async function pollJob(id) {
  clearTimeout(state.pollTimer);
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
    if (state.job && state.job.id !== id) return;
    renderJob(job); connectionError(null);
    if (isActive(job)) state.pollTimer = setTimeout(() => pollJob(id), 1800);
  } catch (error) {
    connectionError(error);
    if (isActive(state.job)) state.pollTimer = setTimeout(() => pollJob(id), 5000);
  }
}
$('configuration-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!state.selection || state.submitting || isActive(state.job) || $('build-button').disabled) return;
  state.submitting = true; renderSelection(); connectionError(null);
  try {
    const job = await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestConfiguration()) });
    state.jobNavigationVersion = state.navigationVersion; rememberJob(job.id); renderJob(job);
    announce(`Generating ${configurationName(job.configuration)}.`); pollJob(job.id);
  } catch (error) { connectionError(error); }
  finally { state.submitting = false; renderSelection(); }
});
$('reset-view').addEventListener('click', () => state.viewer?.reset());
$('explosion').addEventListener('input', event => setExplosion(event.target.value));
$('assemble-view').addEventListener('click', () => { setExplosion(0); state.viewer?.fitCurrent(); });
$('explode-view').addEventListener('click', () => { setExplosion(100); state.viewer?.fitCurrent(); });
$('fit-view').addEventListener('click', () => state.viewer?.fitCurrent());
$('assembly-colors').addEventListener('input', updateAssemblyColors);
$('show-all-instances').addEventListener('click', () => {
  state.hiddenInstances.clear();
  for (const instance of state.assembly?.instances || []) state.viewer?.setVisible(instance.id, true);
  if (state.assembly) renderAssemblyDetails(state.assembly);
});
$('job-artifacts-button').addEventListener('click', () => {
  if (!state.job) return;
  showArtifacts(state.job.builds || [], state.job.bundle_url, true);
  $('preview-title').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});
$('refresh-history').addEventListener('click', async () => {
  $('refresh-history').disabled = true;
  try { await refreshHistory(); connectionError(null); } catch (error) { connectionError(error); }
  finally { $('refresh-history').disabled = false; }
});
async function initialize() {
  try {
    state.config = await api('/api/config'); state.selection = { ...patternDefaults, box_variant: 'plain', ...state.config.defaults };
    state.minimumFloor = state.selection.box_floor === 3 ? 'default' : 0.8;
    state.selection.facade_floor = state.minimumFloor;
    createControls(state.config); renderSelection();
    await refreshHistory();
    const { jobs: allJobs } = await api('/api/jobs');
    const jobs = allJobs.filter(job => !['label', 'gridfinity_bins'].includes(job.configuration.part));
    const stored = rememberedJob();
    const job = jobs.find(item => item.id === stored) || jobs.find(isActive);
    if (job) { rememberJob(job.id); renderJob(job); if (isActive(job)) pollJob(job.id); }
  } catch (error) { connectionError(error); }
}
initialize();
setInterval(() => refreshHistory().catch(connectionError), 15000);
