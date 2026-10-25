import { STLViewer } from './stl-viewer.js';

const $ = id => document.getElementById(id);
const state = {
  builds: [], repository: null, browsingSelection: true,
  config: null, selection: null, job: null, artifacts: [], selectedArtifact: null,
  viewer: null, previewRequest: 0, navigationVersion: 0, jobNavigationVersion: 0, submitting: false,
  shownCompletedJob: null, shownFailedJob: null, pollTimer: null,
  assembly: null, assemblySignature: null, assemblyKey: null, assemblyRequest: 0,
  assemblyController: null, assemblyPending: false, assemblyShowing: false,
  hiddenInstances: new Set(), selectedInstance: null,
};
const names = {
  set: 'Complete set', module: 'Module', box: 'Box', facade: 'Facade',
  rails: 'Geared rails', runner_guides: 'Runner guides', runner_slides: 'Runner slides',
};
const partDescriptions = {
  set: 'Module, box, facade, geared rails, runner guides and runner slides.',
  module: 'The outside shell, sized by family, depth and height.',
  box: 'The drawer tray, sized to fit the selected module.',
  facade: 'The drawer front follows family and height; depth does not change it.',
  rails: 'The geared locking rails follow family; depth and height do not change them.',
  runner_guides: 'Guides follow depth; the same guides fit S, M and L at either height.',
  runner_slides: 'Slides follow depth; the same slides fit S, M and L at either height.',
};
const isActive = job => job && ['queued', 'running'].includes(job.status);
const configurationName = config => `${config.family || 'S'}${config.depth_units || ''} · ${config.height_units || 1}F`;
const svgIcon = name => {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.classList.add('icon');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use'); use.setAttribute('href', `#i-${name}`); svg.append(use); return svg;
};
const element = (tag, className, text) => {
  const node = document.createElement(tag); if (className) node.className = className;
  if (text !== undefined) node.textContent = text; return node;
};
const announce = text => { $('announcement').textContent = text; };
const errorMessage = error => error instanceof Error ? error.message : String(error);
function connectionError(error) {
  $('connection-error').textContent = error ? errorMessage(error) : '';
  $('connection-error').hidden = !error;
}
async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  if (response.status === 401) throw new Error('Session expired. Refresh to sign in; an existing build may still be running.');
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const body = await response.json(); message = body.error || message; } catch { /* Keep the HTTP error. */ }
    throw new Error(message);
  }
  return response.json();
}
function downloadLink(node, url) {
  const valid = typeof url === 'string' && /^\/(?:files\/|api\/jobs\/)[^\s]*$/.test(url) && !url.includes('\\');
  node.hidden = !valid;
  if (valid) { node.href = url; node.setAttribute('download', ''); }
  else node.removeAttribute('href');
}
function rememberJob(id) { try { localStorage.setItem('vault-active-job', id); } catch { /* Storage may be disabled. */ } }
function rememberedJob() { try { return localStorage.getItem('vault-active-job'); } catch { return null; } }

function optionButton(value, key, label, className) {
  const button = element('button', className); button.type = 'button'; button.dataset.value = String(value);
  button.setAttribute('aria-label', label); button.setAttribute('aria-pressed', 'false');
  button.addEventListener('click', () => {
    state.navigationVersion++; state.browsingSelection = true;
    state.selection[key] = value; renderSelection(); showSelection();
  });
  return button;
}
function createControls(config) {
  for (const family of config.families) {
    const button = optionButton(family.id, 'family', `${family.id}, ${family.width_mm} millimeters wide`, 'option');
    button.append(element('span', 'family-letter', family.id), element('span', 'family-width', `${family.width_mm} mm`));
    $('family-options').append(button);
  }
  for (const [values, key, target] of [[config.depths, 'depth_units', 'depth-options'], [config.heights, 'height_units', 'height-options']]) {
    for (const value of values) {
      const button = optionButton(value, key, `${value} ${key === 'depth_units' ? 'depth units' : 'floors'}`, '');
      button.textContent = key === 'height_units' ? `${value}F` : value; $(target).append(button);
    }
  }
  for (const [key, target] of [['box_floor', 'box-floor-options'], ['module_rear', 'module-rear-options']]) {
    for (const [index, value] of config.thicknesses[key].entries()) {
      const label = `${value} mm · ${index ? 'Original' : 'Current'}`;
      const button = optionButton(value, key, label, ''); button.textContent = label; $(target).append(button);
    }
  }
  for (const part of config.parts) {
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
  for (const [target, key] of [['family-options','family'], ['depth-options','depth_units'], ['height-options','height_units'], ['part-options','part'], ['box-floor-options','box_floor'], ['module-rear-options','module_rear']]) {
    for (const button of $(target).querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.value === String(state.selection[key])));
  }
  const dimensions = envelopeDimensions(), config = state.selection;
  $('depth-hint').textContent = `${dimensions[1].toFixed(1)} mm deep`;
  $('height-hint').textContent = `${dimensions[2]} mm body height`;
  $('configuration-name').textContent = configurationName(config);
  $('configuration-dimensions').textContent = `${dimensions[0]} × ${dimensions[1].toFixed(1)} × ${dimensions[2]} mm body`;
  $('part-hint').textContent = partDescriptions[config.part] || '';
  if (!state.selectedArtifact && !state.assemblyShowing) {
    $('preview-title').textContent = configurationName(config);
    renderEnvelope(dimensions); setMetrics(dimensions);
  }
  $('build-button').disabled = state.submitting || isActive(state.job);
  $('build-button-text').textContent = state.submitting ? 'Starting build…' : isActive(state.job) ? 'Build in progress…' : config.part === 'set' ? 'Generate complete set' : `Generate ${names[config.part].toLowerCase()}`;
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
  $('envelope').setAttribute('hidden', ''); $('model-canvas').hidden = true;
  $('model-canvas').dataset.modelReady = 'false';
  $('viewer-message').hidden = false; $('viewer-message').textContent = 'Loading model…';
  $('viewer-help').hidden = true; $('reset-view').hidden = true;
  try {
    if (!part.stl_url?.startsWith('/files/')) throw new Error('This build has no preview mesh. Download STEP to inspect the solid.');
    const response = await fetch(part.stl_url);
    if (!response.ok) throw new Error(response.status === 401 ? 'Sign in again to load this preview.' : 'The preview could not be loaded. Download files below or retry this part.');
    const bytes = await response.arrayBuffer();
    if (request !== state.previewRequest) return;
    $('model-canvas').hidden = false;
    state.viewer ||= new STLViewer($('model-canvas'));
    state.viewer.onSelect = null;
    const dimensions = state.viewer.load(bytes); setMetrics(dimensions);
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
  if (build.kind !== kind) return false;
  const c = build.configuration, s = state.selection;
  const keys = {module: ['family','depth_units','height_units','module_rear'], box: ['family','depth_units','height_units','box_floor'], facade: ['family','height_units'], rails: ['family'], runner_guides: ['depth_units'], runner_slides: ['depth_units']}[kind];
  return keys.every(key => (c[key] ?? state.config.defaults[key]) === s[key]);
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
  $('assembly-summary').textContent = `${scene.instances.length} available components · ${scene.complete ? 'All generated parts available' : 'Incomplete set'} · ${scene.complete && scene.validation?.passed ? '✓ Fit checked' : '⚠ Fit not verified for this view'}`;
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
    if (/^#[a-f\d]{6}$/i.test(instance.color || '')) swatch.style.backgroundColor = instance.color;
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
  const query = new URLSearchParams(Object.fromEntries(['family', 'depth_units', 'height_units', 'box_floor', 'module_rear'].map(key => [key, state.selection[key]])));
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
  $('preview-kind').textContent = 'Assembled dimensions · X / Y / Z';
  const builds = Object.keys(names).filter(kind => kind !== 'set').map(kind => state.builds.find(build => matches(build, kind))).filter(Boolean);
  showArtifacts(builds, null, false, false);
  $('artifact-description').textContent = 'Printable downloads · select a part below to inspect its print orientation.';
  $('print-note').textContent = 'Assembly previews use finished parts. Print downloads retain required sacrificial supports.';
  downloadLink($('stl-download'), null); downloadLink($('step-download'), null);
  renderFreshness();
  try {
    const response = await api(`/api/assembly?${query}`, { signal: controller.signal });
    if (request !== state.assemblyRequest) return;
    if (response.repository) state.repository = response.repository;
    const scene = { ...response, instances: response.instances || [], missing: response.missing || [] };
    const signature = JSON.stringify(scene.instances.map(({ id, mesh_url, transform, explode, color }) => ({ id, mesh_url, transform, explode, color })));
    $('preview-title').textContent = scene.name || `${configurationName(state.selection)} assembly`;
    if (signature === state.assemblySignature && state.assembly) {
      state.assembly = scene; renderAssemblyDetails(scene); return;
    }
    const urls = [...new Set(scene.instances.map(instance => instance.mesh_url))];
    const fetched = await Promise.allSettled(urls.map(async url => {
      if (typeof url !== 'string' || !/^\/files\/[^\s]*$/.test(url) || url.includes('\\')) throw new Error('Finished assembly mesh unavailable; rebuild this part.');
      const mesh = await fetch(url, { signal: controller.signal });
      if (!mesh.ok) throw new Error(mesh.status === 401 ? 'Sign in again to load this component.' : 'Finished mesh could not be loaded; retry or rebuild this part.');
      return mesh.arrayBuffer();
    }));
    if (request !== state.assemblyRequest) return;
    const loaded = [], missing = [...scene.missing];
    for (const instance of scene.instances) {
      const result = fetched[urls.indexOf(instance.mesh_url)];
      if (result.status === 'fulfilled') loaded.push({ ...instance, bytes: result.value });
      else missing.push({ kind: instance.kind, label: instance.label, reason: errorMessage(result.reason) });
    }
    const available = { ...scene, instances: loaded.map(({ bytes, ...instance }) => instance), missing, complete: scene.complete && !missing.length };
    if (loaded.length) {
      $('model-canvas').hidden = false;
      state.viewer ||= new STLViewer($('model-canvas'));
      const dimensions = state.viewer.loadScene(loaded); setMetrics(dimensions);
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
  const { builds, repository } = await api('/api/builds');
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
    const job = await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(state.selection) });
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
    state.config = await api('/api/config'); state.selection = { ...state.config.defaults };
    createControls(state.config); renderSelection();
    await refreshHistory();
    const { jobs } = await api('/api/jobs');
    const stored = rememberedJob();
    const job = jobs.find(item => item.id === stored) || jobs.find(isActive);
    if (job) { rememberJob(job.id); renderJob(job); if (isActive(job)) pollJob(job.id); }
  } catch (error) { connectionError(error); }
}
initialize();
setInterval(() => refreshHistory().catch(connectionError), 15000);
