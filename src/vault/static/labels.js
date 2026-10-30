import { STLViewer } from './stl-viewer.js';
import { api, downloadLink as link, errorMessage, isActive as active, matchesActiveJob } from './client.js';

const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const state = { config: null, font: null, draft: null, layouts: [], errors: [], job: null, submitting: false,
  builds: [], selected: null, viewer: null, view: 'face', pollTimer: null, modelRequest: 0, draftVersion: 0,
  submittedVersion: 0, completedJob: null, rememberedSecond: { text: 'M3 / M4 / M5', size: 4, color: '#d9a56a' } };
const el = (tag, className, value) => { const node = document.createElement(tag); if (className) node.className = className; if (value !== undefined) node.textContent = value; return node; };
const svg = (tag, attrs = {}) => { const node = document.createElementNS(NS, tag); for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value); return node; };
const validColor = value => /^#[a-f\d]{6}$/i.test(value || '');
const colors = draft => [...new Set([draft.background, ...draft.lines.map(line => line.color)].map(color => color.toLowerCase()))];
const announce = value => { $('announcement').textContent = value; };
function familyDefinition(design = state.draft) {
  return state.config.families?.find(family => family.id === (design?.family || 'S')) ||
    { id: 'S', dimensions: state.config.dimensions, outline_svg: state.config.outline_svg };
}
function familyDescription(design, recordedDimensions) { const family = familyDefinition(design); return `${family.id} facade · ${(recordedDimensions || family.dimensions).width_mm} mm label`; }
function storage(key, value) { try { if (value !== undefined) localStorage.setItem(key, JSON.stringify(value)); else return JSON.parse(localStorage.getItem(key)); } catch { return null; } }
function connectionError(error) { $('connection-error').hidden = !error; $('connection-error').textContent = error ? errorMessage(error) : ''; }

// Same ink-bound layout as label_config.label_layout. The paths are the very
// same locally bundled contours used to construct the native CAD faces.
function layout(draft) {
  const dimensions = familyDefinition(draft).dimensions, errors = [], lines = [];
  for (const [index, line] of draft.lines.entries()) {
    const scale = line.size / state.font.units_per_em;
    let cursor = 0;
    const bounds = [], glyphs = [];
    if (!line.text.trim()) errors.push(`Line ${index + 1} needs some text.`);
    if ([...line.text].length > state.config.max_characters_per_line) errors.push(`Line ${index + 1} has too many characters.`);
    if (!Number.isFinite(line.size) || line.size < state.config.font_size_min_mm || line.size > state.config.font_size_max_mm) errors.push(`Choose a font size from ${state.config.font_size_min_mm} to ${state.config.font_size_max_mm} mm.`);
    for (const char of line.text) {
      const glyph = state.font.glyphs[char];
      if (!glyph) { errors.push(`The font does not include “${char}”. Use Latin letters, numbers or punctuation.`); continue; }
      glyphs.push({ char, x: cursor });
      if (glyph.bounds) { const [x0, y0, x1, y1] = glyph.bounds; bounds.push([cursor + x0 * scale, y0 * scale, cursor + x1 * scale, y1 * scale]); }
      cursor += glyph.advance * scale;
    }
    const ink = bounds.length ? [Math.min(...bounds.map(b => b[0])), Math.min(...bounds.map(b => b[1])), Math.max(...bounds.map(b => b[2])), Math.max(...bounds.map(b => b[3]))] : [0, 0, 0, 0];
    if (ink[2] - ink[0] > dimensions.width_mm - 2 * dimensions.safe_margin_mm) errors.push(`Line ${index + 1} is too wide. Shorten it or reduce its font size.`);
    const offset = (dimensions.width_mm - ink[2] - ink[0]) / 2;
    lines.push({ ...line, scale, bounds: ink, glyphs: glyphs.map(glyph => ({ ...glyph, x: glyph.x + offset })) });
  }
  const height = lines.reduce((total, line) => total + line.bounds[3] - line.bounds[1], 0) + dimensions.line_gap_mm * (lines.length - 1);
  if (height > dimensions.height_mm - 2 * dimensions.safe_margin_mm) errors.push('The lines are too tall together. Reduce one or both font sizes.');
  let top = (dimensions.height_mm + height) / 2;
  for (const line of lines) { line.baseline_y = top - line.bounds[3]; top -= line.bounds[3] - line.bounds[1] + dimensions.line_gap_mm; }
  if (colors(draft).length < 2) errors.push('Choose at least two different colors.');
  if (draft.lines.some(line => line.color.toLowerCase() === draft.background.toLowerCase())) errors.push('Give each line a color different from the label so it remains visible.');
  return { lines, errors: [...new Set(errors)] };
}

function createEditors() {
  const editors = $('line-editors'); editors.replaceChildren();
  state.draft.lines.forEach((line, index) => {
    const section = el('div', 'line-editor');
    const label = el('label', '', `Line ${index + 1}`); label.htmlFor = `line-text-${index}`;
    const counter = el('span', '', `${[...line.text].length} / ${state.config.max_characters_per_line}`); counter.id = `line-counter-${index}`; label.append(counter);
    const input = el('input', 'line-text'); Object.assign(input, { type: 'text', id: `line-text-${index}`, value: line.text, maxLength: state.config.max_characters_per_line, autocomplete: 'off', spellcheck: false }); input.setAttribute('aria-describedby', 'validation-message');
    input.addEventListener('input', () => { line.text = input.value; counter.textContent = `${[...line.text].length} / ${state.config.max_characters_per_line}`; edited(); });
    const settings = el('div', 'line-settings'), fontSize = el('div', 'font-size-control'), sizeLabel = el('label', '', 'Font size'); sizeLabel.htmlFor = `line-size-${index}`; sizeLabel.append(el('span', '', 'mm'));
    const sizing = el('div', 'size-control'), range = el('input'), number = el('input');
    for (const [control, type] of [[range, 'range'], [number, 'number']]) { Object.assign(control, { type, min: state.config.font_size_min_mm, max: state.config.font_size_max_mm, step: .5, value: line.size }); control.setAttribute('aria-label', `Line ${index + 1} font size${type === 'range' ? ' slider' : ''}`); }
    number.id = `line-size-${index}`;
    range.addEventListener('input', () => { line.size = Number(range.value); number.value = range.value; edited(); });
    number.addEventListener('input', () => { line.size = number.value === '' ? NaN : Number(number.value); if (Number.isFinite(line.size)) range.value = line.size; edited(); });
    sizing.append(range, number); fontSize.append(sizeLabel, sizing);
    const colorLabel = el('label', 'line-color-label', 'Color'), color = el('input'); Object.assign(color, { type: 'color', value: line.color, id: `line-color-${index}` }); color.setAttribute('aria-label', `Line ${index + 1} color`);
    color.addEventListener('input', () => { line.color = color.value; edited(); }); colorLabel.append(color); settings.append(fontSize, colorLabel); section.append(label, input, settings); editors.append(section);
  });
}

function drawFace() {
  const family = familyDefinition(), d = family.dimensions, root = $('label-artwork'); root.replaceChildren();
  const outline = family.outline_svg;
  const shape = outline ? ['path', { d: outline }] : ['rect', { x: 0, y: 0, width: d.width_mm, height: d.height_mm, rx: d.corner_radius_mm }];
  root.append(svg(shape[0], { ...shape[1], transform: 'translate(0 .22)', fill: '#050608', filter: 'url(#label-shadow)' }));
  root.append(svg(shape[0], { ...shape[1], fill: state.draft.background, stroke: '#ffffff', 'stroke-opacity': .13, 'stroke-width': .08 }));
  for (const [index, line] of state.layouts.entries()) {
    if (!Number.isFinite(line.scale)) continue;
    const group = svg('g', { fill: line.color, 'data-line': index, 'aria-label': line.text });
    for (const glyph of line.glyphs) {
      const definition = state.font.glyphs[glyph.char];
      group.append(svg('path', { d: definition.commands.map(command => command.join(' ')).join(' '), transform: `translate(${glyph.x} ${d.height_mm - line.baseline_y}) scale(${line.scale} ${-line.scale})`, 'fill-rule': 'nonzero' }));
    }
    root.append(group);
  }
  const dimensions = $('label-dimensions'); dimensions.replaceChildren();
  dimensions.append(svg('path', { d: `M0 -2V-5 M${d.width_mm} -2V-5 M0 -3.5H${d.width_mm} M-2 0H-5 M-2 ${d.height_mm}H-5 M-3.5 0V${d.height_mm}`, class: 'label-dimension' }));
  const dimensionFont = Math.max(1.05, d.width_mm / 60);
  const width = svg('text', { x: d.width_mm / 2, y: -4.5, class: 'label-dimension-text' }); width.textContent = `${d.width_mm} mm`; width.style.fontSize = `${dimensionFont}px`;
  const height = svg('text', { transform: `translate(-4.5 ${d.height_mm / 2}) rotate(-90)`, class: 'label-dimension-text' }); height.textContent = `${d.height_mm} mm`; height.style.fontSize = `${dimensionFont}px`;
  dimensions.append(width, height);
  $('label-face').setAttribute('viewBox', `-7 -10 ${d.width_mm + 14} ${d.height_mm + 20}`);
  $('label-face').setAttribute('aria-label', `${family.id} facade label: ${state.draft.lines.map(line => line.text).join('; ')}. ${d.width_mm} by ${d.height_mm} millimeters.`);
  $('mobile-label-face').setAttribute('viewBox', `-2 -2 ${d.width_mm + 4} ${d.height_mm + 4}`);
  // Wide labels keep their real proportions. The mobile editing preview can
  // scroll horizontally so lettering remains legible while typing.
  $('mobile-label-face').style.minWidth = `${(d.width_mm + 4) * 4}px`;
  $('mobile-preview-caption').textContent = `Live ${family.id} face preview${d.width_mm > 80 ? ' · swipe to inspect' : ''}`;
}

function drawSection() {
  const root = $('label-section'); root.replaceChildren();
  const design = state.view === 'model' && state.selected?.configuration ? state.selected.configuration : state.draft;
  const family = familyDefinition(design), d = { ...family.dimensions, ...(state.view === 'model' ? state.selected?.label_dimensions : null) };
  root.setAttribute('viewBox', `-3 -1 ${d.width_mm + 6} 8`);
  const faceTop = d.thickness_mm - d.face_thickness_mm;
  root.append(svg('path', { d: `M0 0H${d.width_mm}V${d.thickness_mm}H0Z${design.hollow ? ` M${d.rim_thickness_mm} 0V${faceTop}H${d.width_mm - d.rim_thickness_mm}V0Z` : ''}`, fill: design.background, 'fill-rule': 'evenodd', stroke: '#8b96a1', 'stroke-width': .07 }));
  for (const [index, line] of design.lines.entries()) for (let part = 0; part < 5; part++) root.append(svg('rect', { x: d.width_mm / 2 - 13.5 + part * 5 + index * 2, y: d.thickness_mm - d.inlay_depth_mm, width: 1.3, height: d.inlay_depth_mm, fill: line.color }));
  root.append(svg('line', { x1: -2, x2: d.width_mm + 2, y1: d.thickness_mm + .22, y2: d.thickness_mm + .22, stroke: '#a0a9b4', 'stroke-width': .2 }));
  const bed = svg('text', { x: d.width_mm / 2, y: d.thickness_mm + 4, fill: '#a0a9b4', 'font-size': Math.max(1.65, d.width_mm / 35), 'font-family': 'system-ui, sans-serif', 'text-anchor': 'middle' }); bed.textContent = 'Build plate'; root.append(bed);
  $('construction-note').textContent = `${family.id} · ${d.width_mm} mm wide · ${design.hollow ? `Hollow back · ${d.face_thickness_mm} mm face` : 'Solid back'} · ${d.thickness_mm} mm total depth`;
}

function render() {
  if (!state.font) return;
  const result = layout(state.draft); state.layouts = result.lines; state.errors = result.errors;
  $('validation-message').textContent = result.errors[0] || 'Text fits. Each line is centered on its visible letter shapes.';
  $('validation-message').classList.toggle('invalid', Boolean(result.errors.length));
  for (const [index] of state.draft.lines.entries()) $(`line-text-${index}`)?.setAttribute('aria-invalid', String(result.errors.some(message => message.startsWith(`Line ${index + 1}`) || message.includes('font does not include'))));
  for (const button of $('line-count-options').children) button.setAttribute('aria-pressed', String(Number(button.dataset.lines) === state.draft.lines.length));
  const family = familyDefinition(), d = family.dimensions;
  for (const button of $('label-family-options').children) button.setAttribute('aria-pressed', String(button.dataset.family === family.id));
  $('label-summary').textContent = `${family.id} · ${d.width_mm} × ${d.height_mm} mm`;
  $('label-depth').textContent = `${d.thickness_mm} mm deep`;
  $('background-hex').textContent = state.draft.background.toUpperCase();
  for (const button of $('background-presets').children) button.setAttribute('aria-pressed', String(button.dataset.color === state.draft.background.toLowerCase()));
  $('material-summary').textContent = `${colors(state.draft).length} colors · face down`;
  const alreadyQueued = matchesActiveJob(state.job, state.draft);
  $('generate-label').disabled = Boolean(result.errors.length || state.submitting || alreadyQueued);
  $('generate-label-text').textContent = state.submitting ? 'Submitting…' : alreadyQueued ? 'Build in progress…' : active(state.job) ? 'Add to queue' : 'Generate label';
  drawFace(); drawSection();
}
function edited() {
  state.draftVersion++; storage('vault-label-draft', state.draft); render();
  if (state.view !== 'face') setView('face');
  $('preview-title').textContent = 'Your finished label'; $('preview-eyebrow').textContent = 'LIVE PREVIEW';
  $('preview-badge').textContent = 'Exact font outlines';
  if (state.selected) $('artifact-name').textContent = `${state.selected.name} · saved build; generate to apply edits`;
}

async function setView(view) {
  state.view = view;
  if (state.config && state.draft) drawSection();
  const model = view === 'model';
  $('face-view').setAttribute('aria-pressed', String(!model)); $('model-view').setAttribute('aria-pressed', String(model));
  $('label-face').toggleAttribute('hidden', model); $('label-model').hidden = !model; $('reset-label-view').hidden = !model;
  $('model-message').hidden = true;
  $('stage-caption').lastChild.textContent = model ? 'Generated geometry · drag to orbit · scroll to zoom' : 'Finished face · enlarged to show detail';
  if (!model || !state.selected) { ++state.modelRequest; return; }
  const request = ++state.modelRequest, selected = state.selected;
  state.viewer?.clear();
  $('model-message').textContent = 'Loading checked color parts…'; $('model-message').hidden = false;
  $('label-model').dataset.modelReady = 'false';
  try {
    const parts = await Promise.all((selected.parts || []).map(async (part, index) => {
      if (typeof part.stl_url !== 'string' || !/^\/files\/[^\s]*$/.test(part.stl_url) || part.stl_url.includes('\\')) throw new Error('This label has no preview mesh. Downloads remain available.');
      const response = await fetch(part.stl_url);
      if (!response.ok) throw new Error(response.status === 401 ? 'Sign in again to preview this label.' : 'The preview could not be loaded. Downloads remain available.');
      // The supplied STL is face down with mirrored X. Rotate it rigidly so
      // its finished face is upright and readable; keep download bytes intact.
      return { id: `color-${index}`, bytes: await response.arrayBuffer(), color: part.color || part.color_hex || colors(selected.configuration || state.draft)[index],
        transform: [-1,0,0,0, 0,0,1,0, 0,1,0,0, 0,0,0,1], explode: [0,0,0] };
    }));
    if (request !== state.modelRequest || state.view !== 'model') return;
    if (!parts.length) throw new Error('This build has no preview meshes.');
    state.viewer ||= new STLViewer($('label-model'));
    state.viewer.loadScene(parts); state.viewer.yaw = -.18; state.viewer.pitch = .16; state.viewer.render();
    $('label-model').dataset.modelReady = 'true'; $('model-message').hidden = true;
  } catch (error) { if (request === state.modelRequest) { $('model-message').textContent = errorMessage(error); $('model-message').hidden = false; } }
}

function showBuild(build, bundleUrl) {
  state.selected = build; $('label-downloads').hidden = false; $('model-view').disabled = false;
  $('artifact-name').textContent = `${build.name} · ${familyDescription(build.configuration, build.label_dimensions)}`;
  $('artifact-colors').textContent = `${(build.parts || []).length} color parts`;
  const reasons = build.freshness?.reasons || [];
  $('artifact-freshness').hidden = !build.freshness?.warning;
  $('artifact-freshness').textContent = reasons.join(' ') || 'This saved build needs regeneration for the current revision.';
  link($('download-3mf'), build.three_mf_url || build.threemf_url || build['3mf_url']);
  link($('download-zip'), bundleUrl || build.bundle_url);
  const list = $('color-downloads'); list.replaceChildren();
  for (const [index, part] of (build.parts || []).entries()) {
    const row = el('div', 'color-part-row'), swatch = el('span', 'color-dot');
    const color = part.color || part.color_hex || colors(build.configuration || state.draft)[index];
    if (validColor(color)) swatch.style.backgroundColor = color;
    row.append(swatch, el('span', '', part.name));
    for (const [label, url] of [['STL', part.stl_url], ['STEP', part.print_step_url || part.step_url]]) { const item = el('a', '', label); link(item, url); row.append(item); }
    list.append(row);
  }
}
function viewBuild(build, bundleUrl) {
  showBuild(build, bundleUrl); $('preview-title').textContent = build.name; $('preview-eyebrow').textContent = 'SAVED BUILD'; $('preview-badge').textContent = 'Checked CAD';
  setView('model'); announce('Showing the saved label. Your editor draft is unchanged.');
}

function renderJob(job) {
  $('job-queue-link').href = `/queue?job=${encodeURIComponent(job.id)}`;
  state.job = job; $('label-job-panel').hidden = false;
  $('job-title').textContent = { queued: 'Label queued', running: 'Generating label', completed: 'Your label is ready', failed: 'Label generation failed', cancelled: 'Label cancelled' }[job.status] || 'Label build';
  $('job-description').textContent = `${familyDescription(job.configuration)} · ${job.configuration.lines.map(line => line.text).join(' / ')}${active(job) ? ' · Building continues if you close this page.' : ''}`;
  $('job-status').textContent = job.status.charAt(0).toUpperCase() + job.status.slice(1);
  $('job-indicator').className = `job-indicator${active(job) ? '' : job.status === 'failed' ? ' failed' : ' done'}`;
  $('job-error').hidden = !job.error; $('job-error').textContent = job.error || '';
  $('job-log').textContent = job.logs || (job.status === 'queued' ? 'Waiting for the current build to finish…' : 'Preparing label geometry…');
  if (job.status === 'failed') $('job-log-details').open = true;
  $('view-job-result').hidden = !(job.builds || []).some(build => build.kind === 'label');
  if (job.status === 'completed' && state.completedJob !== job.id) {
    state.completedJob = job.id;
    const build = job.builds?.find(item => item.kind === 'label');
    if (build) {
      if (state.draftVersion === state.submittedVersion) viewBuild(build, job.bundle_url);
      else if (!state.selected) showBuild(build, job.bundle_url);
      announce('Label complete. Multicolor 3MF and color-separated STL and STEP downloads are ready.');
    }
    refreshHistory().catch(connectionError);
  }
  render();
}
async function pollJob(id) {
  clearTimeout(state.pollTimer);
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
    if (state.job && state.job.id !== id) return;
    renderJob(job); connectionError(null);
    if (active(job)) state.pollTimer = setTimeout(() => pollJob(id), 1800);
  } catch (error) { connectionError(error); if (active(state.job)) state.pollTimer = setTimeout(() => pollJob(id), 5000); }
}
async function refreshHistory() {
  const response = await api('/api/builds');
  state.builds = (response.builds || []).filter(build => build.kind === 'label');
  const list = $('label-history'); list.replaceChildren();
  if (!state.builds.length) { list.append(el('p', 'empty-history', 'No labels generated yet.')); return; }
  for (const build of state.builds.slice(0, 12)) {
    const button = el('button', 'history-card'); button.type = 'button';
    const swatches = el('span', 'label-history-swatches');
    for (const color of colors(build.configuration || state.draft)) { const swatch = el('span'); if (validColor(color)) swatch.style.backgroundColor = color; swatches.append(swatch); }
    const text = el('span'); text.append(el('strong', 'label-history-name', build.configuration?.lines?.map(line => line.text).join('\n') || build.name));
    const date = new Date(build.created_at), formatted = Number.isNaN(date.getTime()) ? 'Saved build' : new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
    text.append(el('small', '', `${familyDescription(build.configuration, build.label_dimensions)} · ${formatted} · ${build.configuration?.hollow ? 'Hollow' : 'Solid'} back`)); button.append(swatches, text, el('span', '', '→'));
    button.addEventListener('click', () => { state.draftVersion++; viewBuild(build); $('preview-title').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }); list.append(button);
  }
}

$('label-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!state.draft || state.errors.length || state.submitting || matchesActiveJob(state.job, state.draft)) return;
  state.submitting = true; render(); connectionError(null);
  const submitted = JSON.stringify(state.draft); state.submittedVersion = state.draftVersion;
  try { const job = await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: submitted }); storage('vault-label-job', job.id); renderJob(job); if (active(job)) pollJob(job.id); }
  catch (error) { connectionError(error); }
  finally { state.submitting = false; render(); }
});
for (const button of $('line-count-options').children) button.addEventListener('click', () => {
  if (!state.draft || state.draft.lines.length === Number(button.dataset.lines)) return;
  if (Number(button.dataset.lines) === 1) state.rememberedSecond = state.draft.lines.pop();
  else state.draft.lines.push({ ...state.rememberedSecond });
  createEditors(); edited();
});
$('background-color').addEventListener('input', event => { if (state.draft) { state.draft.background = event.target.value; edited(); } });
$('hollow-label').addEventListener('change', event => { if (state.draft) { state.draft.hollow = event.target.checked; edited(); } });
$('face-view').addEventListener('click', () => { setView('face'); $('preview-title').textContent = 'Your finished label'; $('preview-eyebrow').textContent = 'LIVE PREVIEW'; $('preview-badge').textContent = 'Exact font outlines'; });
$('model-view').addEventListener('click', () => { if (state.selected) viewBuild(state.selected, state.selected.bundle_url || (state.job?.builds?.some(build => build.id === state.selected.id) ? state.job.bundle_url : null)); });
$('reset-label-view').addEventListener('click', () => { if (state.viewer) { state.viewer.reset(); state.viewer.yaw = -.18; state.viewer.pitch = .16; state.viewer.render(); } });
$('view-job-result').addEventListener('click', () => { const build = state.job?.builds?.find(item => item.kind === 'label'); if (build) { state.draftVersion++; viewBuild(build, state.job.bundle_url); } });
$('refresh-labels').addEventListener('click', async () => { $('refresh-labels').disabled = true; try { await refreshHistory(); connectionError(null); } catch (error) { connectionError(error); } finally { $('refresh-labels').disabled = false; } });

async function initialize() {
  try {
    state.config = await api('/api/labels/config');
    if (typeof state.config.font_url !== 'string' || !state.config.font_url.startsWith('/static/')) throw new Error('Label font metadata is unavailable.');
    state.font = await api(state.config.font_url); state.draft = { ...structuredClone(state.config.defaults), family: state.config.defaults.family || 'S' };
    const saved = storage('vault-label-draft');
    const families = state.config.families || [{ id: 'S', dimensions: state.config.dimensions, outline_svg: state.config.outline_svg }];
    if (saved?.part === 'label' && families.some(family => family.id === (saved.family || 'S')) && validColor(saved.background) && typeof saved.hollow === 'boolean' && Array.isArray(saved.lines) && saved.lines.length >= 1 && saved.lines.length <= 2 && saved.lines.every(line => typeof line.text === 'string' && [...line.text].length <= state.config.max_characters_per_line && Number.isFinite(line.size) && validColor(line.color))) {
      state.draft = { part: 'label', family: saved.family || 'S', background: saved.background, hollow: saved.hollow, lines: saved.lines.map(({ text, size, color }) => ({ text, size, color })) };
    }
    $('font-name').textContent = state.config.font;
    for (const family of families) {
      const button = el('button', 'option'); button.type = 'button'; button.dataset.family = family.id;
      button.setAttribute('aria-label', `${family.id} facade, ${family.dimensions.width_mm} millimeter label`);
      button.append(el('span', 'family-letter', family.id), el('span', 'family-width', `${family.dimensions.width_mm} mm`));
      button.addEventListener('click', () => { state.draft.family = family.id; edited(); }); $('label-family-options').append(button);
    }
    $('background-color').value = state.draft.background; $('hollow-label').checked = state.draft.hollow;
    for (const [name, color] of [['Graphite', '#30343b'], ['Warm white', '#eee9df'], ['Terracotta', '#a9553a'], ['Blue', '#335f80']]) {
      const button = el('button', 'color-preset'); button.type = 'button'; button.style.backgroundColor = color; button.dataset.color = color; button.setAttribute('aria-label', `${name} label color`); button.title = name;
      button.addEventListener('click', () => { state.draft.background = color; $('background-color').value = color; edited(); }); $('background-presets').append(button);
    }
    createEditors(); render();
    const results = await Promise.allSettled([refreshHistory(), api('/api/jobs')]);
    if (results[0].status === 'rejected') connectionError(results[0].reason);
    if (results[1].status === 'rejected') { connectionError(results[1].reason); return; }
    const jobs = (results[1].value.jobs || []).filter(job => job.configuration?.part === 'label'), remembered = storage('vault-label-job');
    let job = jobs.find(item => item.id === remembered);
    if (!job && typeof remembered === 'string') {
      try { const savedJob = await api(`/api/jobs/${encodeURIComponent(remembered)}`); if (savedJob.configuration?.part === 'label') job = savedJob; }
      catch { /* A removed historical job does not prevent editing a new label. */ }
    }
    job ||= jobs.find(active);
    if (job) { storage('vault-label-job', job.id); renderJob(job); if (active(job)) pollJob(job.id); }
  } catch (error) { connectionError(error); }
}
initialize();
setInterval(() => { if (state.font) refreshHistory().catch(connectionError); }, 15000);
