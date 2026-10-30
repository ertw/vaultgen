"""Queue page fixtures: timing, errors, recovery, controls and responsive layout.

Intercepts every request. Does not start a server or submit real CAD jobs.
"""
import argparse
from collections import Counter
from copy import deepcopy
import mimetypes
from pathlib import Path
import shutil
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--chromium', default=shutil.which('chromium'))
parser.add_argument('--output', type=Path, default=Path('out/web-review'))
args = parser.parse_args()
if not args.chromium:
    parser.error('Pass --chromium or enter the cad-tooling Nix environment.')
args.output.mkdir(parents=True, exist_ok=True)
STATIC = Path(__file__).resolve().parents[1] / 'src/vault/static'
ORIGIN = 'http://vault.test'


def task(kind, status, elapsed=None, render=None, error=None):
    return dict(kind=kind, status=status, elapsed_seconds=elapsed, render_seconds=render,
                started_at='2026-10-29T20:01:00Z' if elapsed is not None else None,
                finished_at='2026-10-29T20:02:00Z' if status in ('completed', 'failed') else None,
                stage='constructing' if status == 'running' else None,
                stage_timings=[dict(stage='construction', elapsed_seconds=elapsed)] if elapsed else [],
                error=error, logs='Building native solid\n' + (error or 'Checking exports\n'), reused=False,
                build_ids=[])


def job(job_id, status, kind='set', tasks=(), legacy=False):
    return dict(id=job_id, status=status,
                configuration=dict(family='M', depth_units=6, height_units=2, part=kind, wall_pattern='miura'),
                created_at='2026-10-29T20:00:00Z',
                started_at=None if status == 'queued' or legacy else '2026-10-29T20:01:00Z',
                finished_at=None if status in ('queued', 'running') or legacy else '2026-10-29T20:06:00Z',
                elapsed_seconds=None if status == 'queued' or legacy else 300,
                wait_seconds=None if legacy else 60, queue_position=1 if status == 'queued' else None,
                tasks=list(tasks), task_counts=dict(Counter(t['status'] for t in tasks)),
                error='A part failed. Completed parts remain available.' if status == 'failed' else None,
                logs='Retained original job output\n', builds=[], bundle_url=None)


error = 'ValueError: STEP round-trip failed\n<svg onload="window.injected=true">'
jobs = [job('running-job', 'running', tasks=[task('module', 'running', 180, 3.5), task('box', 'completed', 45.2, 1.2), task('assembly', 'blocked')]),
        job('queued-job', 'queued', kind='key', tasks=[task('key', 'queued')]),
        job('failed-job', 'failed', tasks=[task('module', 'completed', 122, 4.5), task('box', 'failed', 31, 0, error), task('assembly', 'skipped')]),
        job('complete-job', 'completed', tasks=[task('key', 'completed', 51, 2.25)]),
        job('legacy-job', 'completed', legacy=True)]
checked_build = dict(id='checked-build', name='M6 Module 2F', kind='module',
                     bundle_url='/api/builds/checked-build/bundle.zip', parts=[])
jobs[2]['builds'] = [checked_build]
jobs[3]['builds'] = [checked_build]
jobs[3]['bundle_url'] = '/api/jobs/complete-job/bundle.zip'
jobs += [job(f'history-{i}', 'completed', kind='spring', legacy=True) for i in range(29)]
fixture = {'jobs': jobs, 'actions': [], 'queue_reads': 0, 'detail_reads': 0, 'offline': False}


def route(request):
    parsed = urlsplit(request.request.url)
    path = parsed.path
    if path == '/queue':
        return request.fulfill(path=str(STATIC / 'queue.html'), content_type='text/html')
    if path.startswith('/static/'):
        file = STATIC / path.removeprefix('/static/')
        assert file.parent == STATIC and file.is_file(), path
        return request.fulfill(path=str(file), content_type=mimetypes.guess_type(file.name)[0])
    if path == '/api/queue':
        fixture['queue_reads'] += 1
        if fixture['offline']:
            return request.fulfill(status=503, json={'error': 'Temporary queue connection failure'})
        query = parse_qs(parsed.query)
        status = query.get('status', ['all'])[0]
        selected = [item for item in fixture['jobs'] if status == 'all' or
                    (status == 'active' and item['status'] in ('queued', 'running')) or item['status'] == status]
        limit, offset = int(query.get('limit', ['30'])[0]), int(query.get('offset', ['0'])[0])
        summaries = [{key: value for key, value in item.items() if key not in ('tasks', 'logs', 'builds')}
                     for item in selected[offset:offset + limit]]
        return request.fulfill(json=dict(jobs=summaries, total=len(selected), limit=limit, offset=offset,
            workers=2, capacity=4, counts=dict(Counter(item['status'] for item in fixture['jobs']))))
    if path.startswith('/api/jobs/'):
        parts = path.split('/')
        item = next((job for job in fixture['jobs'] if job['id'] == parts[3]), None)
        assert item, path
        if request.request.method == 'POST':
            action = parts[4]
            fixture['actions'].append((item['id'], action))
            assert request.request.post_data_json == {}
            if action == 'cancel':
                item['status'] = 'cancelled'
                for detail in item['tasks']:
                    if detail['status'] in ('queued', 'running', 'blocked'):
                        detail['status'] = 'cancelled'
                item['task_counts'] = dict(Counter(t['status'] for t in item['tasks']))
                return request.fulfill(json=item)
            assert action == 'retry', action
            retried = job('retry-job', 'queued', tasks=[task('module', 'queued'), task('box', 'queued'), task('assembly', 'blocked')])
            fixture['jobs'].insert(0, retried)
            return request.fulfill(status=202, json=retried)
        fixture['detail_reads'] += 1
        return request.fulfill(json=item)
    raise AssertionError(f'Unexpected request: {request.request.method} {path}')


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.chromium, headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/*', route)
    page.goto(ORIGIN + '/queue')
    expect(page.locator('#detail-status')).to_have_text('Running')
    expect(page.locator('#count-running')).to_have_text('1')
    expect(page.locator('#count-queued')).to_have_text('1')
    expect(page.locator('#worker-count')).to_have_text('2')
    expect(page.locator('#detail-render')).to_have_text('4.7 s')
    expect(page.locator('[data-task-kind="module"] .task-metrics')).to_contain_text('3m 0s')
    expect(page.locator('#next-page')).to_be_enabled()
    page.locator('#next-page').click()
    expect(page.locator('#page-range')).to_have_text('31–34 of 34')
    page.locator('#previous-page').click()
    expect(page.locator('[data-job-id="failed-job"]')).to_be_visible()
    page.locator('[data-job-id="failed-job"]').click()
    expect(page.locator('#detail-status')).to_have_text('Failed')
    failed = page.locator('[data-task-kind="box"]')
    expect(failed).to_have_attribute('open', '')
    expect(failed.locator('.error-message')).to_have_text(error)
    expect(page.locator('#job-downloads')).to_be_visible()
    expect(page.locator('#download-list a')).to_have_attribute('href', '/api/builds/checked-build/bundle.zip')
    assert not page.evaluate('Boolean(window.injected)')
    # Polling keeps the selected job and does not collapse an opened log.
    page.locator('#job-log-details summary').click()
    page.locator('#job-log').evaluate('node => { const range = document.createRange(); range.selectNodeContents(node); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); }')
    selected_text = page.evaluate('window.getSelection().toString()')
    fixture['jobs'][2]['logs'] += 'A later log line\n'
    before = fixture['detail_reads']
    page.wait_for_timeout(2500)
    assert fixture['detail_reads'] > before
    assert page.evaluate('window.getSelection().toString()') == selected_text
    expect(page.locator('#job-log-details')).to_have_attribute('open', '')
    expect(page.locator('#detail-status')).to_have_text('Failed')
    page.evaluate('window.getSelection().removeAllRanges()')
    page.screenshot(path=str(args.output / 'queue-desktop.png'), full_page=True)
    page.locator('#queue-filter').select_option('failed')
    expect(page.locator('.queue-job')).to_have_count(1)
    expect(page.locator('#count-running')).to_have_text('1')
    page.locator('#retry-job').click()
    expect(page.locator('#detail-status')).to_have_text('Queued')
    expect(page.locator('#detail-id')).to_have_text('Job retry-job')
    assert fixture['actions'] == [('failed-job', 'retry')]
    page.locator('#cancel-job').click()
    expect(page.locator('#detail-status')).to_have_text('Cancelled')
    assert fixture['actions'][-1] == ('retry-job', 'cancel')
    page.goto(ORIGIN + '/queue?job=legacy-job')
    expect(page.locator('#detail-status')).to_have_text('Completed')
    expect(page.locator('#detail-elapsed')).to_have_text('—')
    expect(page.locator('#detail-render')).to_have_text('—')
    expect(page.locator('#legacy-note')).to_be_visible()
    page.goto(ORIGIN + '/queue?job=complete-job')
    expect(page.locator('#job-download')).to_have_attribute('href', '/api/jobs/complete-job/bundle.zip')
    # Failed refresh retains the loaded details and recovers automatically.
    fixture['offline'] = True
    page.locator('#refresh-queue').click()
    expect(page.locator('#connection-error')).to_contain_text('Temporary queue connection failure')
    expect(page.locator('#detail-status')).to_have_text('Completed')
    fixture['offline'] = False
    expect(page.locator('#connection-error')).to_be_hidden(timeout=6000)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(ORIGIN + '/queue?job=failed-job')
    expect(page.locator('#detail-status')).to_have_text('Failed')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
    page.screenshot(path=str(args.output / 'queue-mobile.png'), full_page=True)
    assert not errors, errors
    print('PASS: queue pagination/filters, per-part timing/error logs, safe text, preserved polling selection, retry/cancel, legacy unknown timings, completed downloads, reconnect and mobile layout; no real CAD submissions')
    browser.close()
