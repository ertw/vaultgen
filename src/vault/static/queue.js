import { api, downloadLink, errorMessage, isActive } from './client.js';

const $ = id => document.getElementById(id);
const names = { set: 'Complete set', module: 'Module', box: 'Box', facade: 'Facade', rails: 'Geared rails', runner_guides: 'Runner guides', runner_slides: 'Runner slides', key: 'Key', spring: 'Spring', runner_stop: 'Runner stop', facade_cap: 'Facade cap', key_cap: 'Key cap', latch: 'Latch', label: 'Label', gridfinity_bins: 'Containers', assembly: 'Assembly validation' };
const statusNames = { queued: 'Queued', blocked: 'Waiting for parts', running: 'Running', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled', skipped: 'Skipped' };
const state = { selected: new URLSearchParams(location.search).get('job'), detail: null, filter: 'all', offset: 0, limit: 30, total: 0, timer: null, refreshing: false, action: false, jobs: new Map(), tasks: new Map(), downloads: '', detailRequest: 0 };

function element(tag, className = '', value = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== '') node.textContent = value;
  return node;
}
function text(node, value) {
  value = String(value ?? '');
  if (node.textContent === value) return;
  const selection = window.getSelection();
  // Let people copy a log while new output arrives.
  if (selection && !selection.isCollapsed && selection.containsNode(node, true)) return;
  node.textContent = value;
}
function duration(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return '—';
  const value = Math.max(0, Number(seconds));
  if (value < 1) return `${value.toFixed(2)} s`;
  if (value < 60) return `${value.toFixed(1)} s`;
  if (value < 3600) return `${Math.floor(value / 60)}m ${Math.floor(value % 60)}s`;
  return `${Math.floor(value / 3600)}h ${Math.floor(value % 3600 / 60)}m`;
}
function date(value, full = false) {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Unknown time';
  return new Intl.DateTimeFormat(undefined, full ? { dateStyle: 'medium', timeStyle: 'short' } : { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value));
}
function jobName(job) {
  const config = job.configuration || {};
  if (config.part === 'label') return `${config.family || 'S'} label`;
  if (!config.family) return names[config.part] || 'Build';
  const size = `${config.family}${config.depth_units || ''} · ${config.height_units || 1}F`;
  return size + (config.drawer_columns === 2 ? ` · ${config.drawer_rows === 2 ? '4' : '2'} drawers` : '');
}
function jobType(job) {
  const config = job.configuration || {};
  return [names[config.part] || config.part || 'Build', config.wall_pattern === 'miura' ? 'Miura-ori' : null].filter(Boolean).join(' · ');
}
function setStatus(node, status) {
  text(node, statusNames[status] || status || 'Unknown');
  node.dataset.status = status || 'unknown';
}
function taskCounts(job) {
  if (job.task_counts) return job.task_counts;
  const counts = {};
  for (const task of job.tasks || []) counts[task.status] = (counts[task.status] || 0) + 1;
  return counts;
}
function progress(job) {
  const counts = taskCounts(job);
  const total = Object.entries(counts).filter(([key]) => key !== 'total').reduce((sum, [, value]) => sum + Number(value || 0), 0);
  const messages = [];
  if (job.status === 'queued' && job.queue_position != null) messages.push(`Queue position ${job.queue_position}`);
  if (total) messages.push(`${counts.completed || 0} / ${total} tasks complete`);
  if (counts.running) messages.push(`${counts.running} running`);
  if (counts.failed) messages.push(`${counts.failed} failed`);
  return messages.join(' · ') || (isActive(job) ? 'Waiting for worker updates' : 'Saved build');
}
function connectionError(error) {
  $('connection-error').hidden = !error;
  text($('connection-error'), error ? errorMessage(error) : '');
}
function makeJob(job) {
  const button = element('button', 'queue-job'); button.type = 'button'; button.dataset.jobId = job.id;
  const heading = element('span', 'queue-job-title'), name = element('strong'), status = element('span', 'queue-status');
  heading.append(name, status);
  const type = element('span', 'queue-job-type'), meta = element('span', 'queue-job-meta'), created = element('span'), elapsed = element('span'), note = element('span', 'queue-job-progress');
  meta.append(created, elapsed); button.append(heading, type, meta, note);
  button.addEventListener('click', () => selectJob(job.id, true));
  return { button, name, status, type, created, elapsed, note };
}
function renderQueue(data) {
  state.total = data.total || 0;
  for (const status of ['running', 'queued', 'failed']) text($(`count-${status}`), data.counts?.[status] ?? 0);
  text($('worker-count'), data.workers ?? '—');
  text($('capacity-note'), `Up to ${data.workers ?? '—'} tasks run in parallel across ${data.capacity ?? '—'} active jobs. Assembly checks wait for their required parts.`);
  const jobs = data.jobs || [], present = new Set(jobs.map(job => job.id));
  for (const [id, item] of state.jobs) if (!present.has(id)) { item.button.remove(); state.jobs.delete(id); }
  jobs.forEach((job, index) => {
    let item = state.jobs.get(job.id);
    if (!item) { item = makeJob(job); state.jobs.set(job.id, item); }
    text(item.name, jobName(job)); setStatus(item.status, job.status); text(item.type, jobType(job));
    text(item.created, date(job.created_at)); text(item.elapsed, `Run ${duration(job.elapsed_seconds)}`); text(item.note, progress(job));
    item.button.setAttribute('aria-pressed', String(job.id === state.selected));
    if ($('queue-list').children[index] !== item.button) $('queue-list').insertBefore(item.button, $('queue-list').children[index] || null);
  });
  $('queue-empty').hidden = jobs.length > 0;
  text($('queue-empty'), state.filter === 'all' ? 'No jobs yet. Generate parts, labels or containers to get started.' : `No ${state.filter} jobs.`);
  text($('page-range'), state.total ? `${state.offset + 1}–${state.offset + jobs.length} of ${state.total}` : '0 jobs');
  $('previous-page').disabled = state.offset === 0;
  $('next-page').disabled = state.offset + jobs.length >= state.total;
  if (!state.selected && jobs.length) selectJob(jobs[0].id);
}
function makeTask(task) {
  const details = element('details', 'queue-task'); details.dataset.taskKind = task.kind;
  const summary = element('summary'), name = element('span', 'task-name'), status = element('span', 'queue-status'), stage = element('span', 'task-stage'), metrics = element('span', 'task-metrics');
  const elapsedLabel = element('span', '', 'Run '), renderLabel = element('span', '', 'Render '), elapsed = element('strong'), render = element('strong');
  elapsedLabel.append(elapsed); renderLabel.append(render); metrics.append(elapsedLabel, renderLabel);
  summary.append(name, status, stage, metrics);
  const body = element('div', 'task-body'), dates = element('p', 'task-dates'), error = element('pre', 'error-message'), stages = element('div', 'stage-list'), logHeading = element('p', 'task-log-heading', 'Part log'), log = element('pre');
  log.setAttribute('aria-label', `${names[task.kind] || task.kind} log`);
  body.append(dates, error, stages, logHeading, log); details.append(summary, body);
  // Only open a failed task on first appearance; polling preserves the user's choice.
  details.open = task.status === 'failed';
  return { details, name, status, stage, elapsed, render, dates, error, stages, log, stageKey: '' };
}
function renderTasks(tasks) {
  const present = new Set(tasks.map(task => task.kind));
  for (const [kind, item] of state.tasks) if (!present.has(kind)) { item.details.remove(); state.tasks.delete(kind); }
  tasks.forEach((task, index) => {
    let item = state.tasks.get(task.kind);
    if (!item) { item = makeTask(task); state.tasks.set(task.kind, item); }
    text(item.name, names[task.kind] || task.kind); setStatus(item.status, task.status);
    text(item.stage, task.reused ? 'Reused checked build' : task.stage || (task.kind === 'assembly' && ['queued', 'blocked'].includes(task.status) ? 'Waiting for checked parts' : ''));
    text(item.elapsed, duration(task.elapsed_seconds)); text(item.render, duration(task.render_seconds));
    text(item.dates, task.started_at ? `Started ${date(task.started_at, true)}${task.finished_at ? ` · Finished ${date(task.finished_at, true)}` : ''}` : 'Not started');
    item.error.hidden = !task.error; text(item.error, task.error || '');
    text(item.log, task.logs || 'No output recorded.');
    const stages = Array.isArray(task.stage_timings) ? task.stage_timings : Object.entries(task.stage_timings || {}).map(([stage, elapsed_seconds]) => ({ stage, elapsed_seconds }));
    const stageKey = JSON.stringify(stages);
    if (item.stageKey !== stageKey) {
      item.stageKey = stageKey;
      item.stages.replaceChildren(...stages.map(record => {
        const node = element('span', 'stage-time', String(record.stage || 'Stage').replaceAll('_', ' '));
        node.append(element('strong', '', duration(record.elapsed_seconds))); return node;
      }));
    }
    if ($('task-list').children[index] !== item.details) $('task-list').insertBefore(item.details, $('task-list').children[index] || null);
  });
  text($('tasks-count'), `${tasks.length} tasks`);
  $('legacy-note').hidden = tasks.length > 0 && tasks.some(task => task.started_at || task.elapsed_seconds != null);
}
function renderDownloads(job) {
  const builds = job.builds || [], key = JSON.stringify(builds.map(build => [build.id, build.bundle_url, build.three_mf_url]));
  $('job-downloads').hidden = builds.length === 0;
  if (key === state.downloads) return;
  state.downloads = key;
  $('download-list').replaceChildren(...builds.map(build => {
    const item = element('div', 'download-item'), links = element('div');
    for (const [label, url] of [['STL + STEP ZIP ↓', build.bundle_url], ['3MF ↓', build.three_mf_url]]) {
      const link = element('a', 'text-button', label); downloadLink(link, url); if (!link.hidden) links.append(link);
    }
    item.append(element('strong', '', build.name || names[build.kind] || build.id), links); return item;
  }));
}
function renderDetail(job) {
  if (job.id !== state.selected) return;
  state.detail = job;
  $('detail-empty').hidden = true; $('job-detail').hidden = false;
  $('job-detail').parentElement.setAttribute('aria-labelledby', 'detail-name');
  text($('detail-name'), jobName(job)); text($('detail-kind'), jobType(job)); setStatus($('detail-status'), job.status);
  text($('detail-created'), `Submitted ${date(job.created_at, true)}`); text($('detail-progress'), progress(job));
  text($('detail-wait'), duration(job.wait_seconds)); text($('detail-elapsed'), duration(job.elapsed_seconds));
  const times = (job.tasks || []).map(task => task.render_seconds).filter(value => value != null);
  text($('detail-render'), duration(job.render_seconds ?? (times.length ? times.reduce((sum, value) => sum + value, 0) : null)));
  $('detail-error').hidden = !job.error; text($('detail-error'), job.error || '');
  $('cancel-job').hidden = !isActive(job); $('retry-job').hidden = !['failed', 'cancelled'].includes(job.status);
  $('cancel-job').disabled = state.action; $('retry-job').disabled = state.action;
  downloadLink($('job-download'), job.bundle_url);
  $('job-permalink').href = `/queue?job=${encodeURIComponent(job.id)}`;
  text($('job-log'), job.logs || 'No output yet.'); text($('job-configuration'), JSON.stringify(job.configuration || {}, null, 2)); text($('detail-id'), `Job ${job.id}`);
  renderTasks(job.tasks || []); renderDownloads(job);
}
async function loadDetail() {
  if (!state.selected) return;
  const id = state.selected, request = ++state.detailRequest;
  const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
  if (request === state.detailRequest && id === state.selected) renderDetail(job);
}
async function selectJob(id, user = false) {
  if (state.selected !== id || !state.detail) {
    state.selected = id; state.detail = null; state.tasks.clear(); state.downloads = '';
    $('task-list').replaceChildren(); $('job-log-details').open = false; $('configuration-details').open = false;
    $('job-detail').hidden = true; $('detail-empty').hidden = false; text($('detail-title'), 'Loading job…');
    history.replaceState(null, '', `/queue?job=${encodeURIComponent(id)}`);
    for (const [jobId, item] of state.jobs) item.button.setAttribute('aria-pressed', String(jobId === id));
  }
  try {
    await loadDetail();
    if (user) { text($('announcement'), `Selected ${jobName(state.detail || {})}.`); if (innerWidth <= 800) $('job-detail').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
  } catch (error) { connectionError(error); text($('detail-title'), 'Job unavailable'); }
}
async function refresh() {
  if (state.refreshing) return;
  state.refreshing = true; $('refresh-queue').disabled = true;
  clearTimeout(state.timer);
  try {
    const data = await api(`/api/queue?status=${encodeURIComponent(state.filter)}&limit=${state.limit}&offset=${state.offset}`);
    renderQueue(data); await loadDetail(); connectionError(null); text($('refresh-status'), 'Live · updates every 2s');
  } catch (error) { connectionError(error); text($('refresh-status'), 'Connection interrupted'); }
  finally { state.refreshing = false; $('refresh-queue').disabled = false; state.timer = setTimeout(refresh, 2000); }
}
async function action(kind) {
  if (!state.selected || state.action) return;
  state.action = true; $('cancel-job').disabled = true; $('retry-job').disabled = true;
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(state.selected)}/${kind}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    if (kind === 'retry') { state.filter = 'all'; $('queue-filter').value = 'all'; state.offset = 0; await selectJob(job.id); }
    else renderDetail(job);
    text($('announcement'), kind === 'retry' ? 'Retry added to the queue.' : 'Job cancelled. Completed downloads are retained.');
    connectionError(null); await refresh();
  } catch (error) { connectionError(error); }
  finally { state.action = false; $('cancel-job').disabled = false; $('retry-job').disabled = false; }
}
$('queue-filter').addEventListener('change', () => { state.filter = $('queue-filter').value; state.offset = 0; refresh(); });
$('previous-page').addEventListener('click', () => { state.offset = Math.max(0, state.offset - state.limit); refresh(); });
$('next-page').addEventListener('click', () => { state.offset += state.limit; refresh(); });
$('refresh-queue').addEventListener('click', refresh);
$('cancel-job').addEventListener('click', () => action('cancel'));
$('retry-job').addEventListener('click', () => action('retry'));
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
refresh();
