"""Label editor regression checks with local fixtures; never submits a CAD job."""
import argparse
import json
from pathlib import Path
import shutil
import struct
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from vault.label_config import LabelConfiguration, label_catalog, label_dimensions, label_layout


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--chromium', default=shutil.which('chromium'))
parser.add_argument('--output', type=Path, default=Path('out/web-review/labels'))
args = parser.parse_args()
if not args.chromium:
    parser.error('Pass --chromium or add Chromium to PATH')
args.output.mkdir(parents=True, exist_ok=True)
STATIC = Path(__file__).resolve().parents[1] / 'src/vault/static'

# A small closed prism is sufficient to exercise the existing STL renderer.
vertices = [(x, y, z) for z in (0, 2) for y in (0, 19.4) for x in (0, 47)]
faces = [(0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6), (0, 1, 4), (1, 5, 4),
         (2, 6, 3), (3, 6, 7), (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)]
mesh = bytes(80) + struct.pack('<I', len(faces)) + b''.join(
    struct.pack('<12fH', 0, 0, 0, *(coordinate for i in face for coordinate in vertices[i]), 0)
    for face in faces)

fixture = {'job': None, 'builds': [], 'submissions': [], 'mesh_failure': False, 'omit_jobs': False,
           'job_requests': []}


def route(request):
    path = urlsplit(request.request.url).path
    if path.startswith('/api/jobs'):
        fixture['job_requests'].append((request.request.method, path))
    if path == '/api/labels/config':
        return request.fulfill(json=label_catalog())
    if path == '/api/builds':
        return request.fulfill(json={'builds': fixture['builds']})
    if path == '/api/jobs' and request.request.method == 'POST':
        configuration = json.loads(request.request.post_data)
        LabelConfiguration.parse(configuration)  # Browser and server agree.
        fixture['submissions'].append(configuration)
        fixture['job'] = {'id': f"label-job-{len(fixture['submissions'])}",
                          'configuration': configuration, 'status': 'running',
                          'builds': [], 'logs': 'Creating color inlays…'}
        return request.fulfill(json=fixture['job'], status=202)
    if path == '/api/jobs':
        return request.fulfill(json={'jobs': [fixture['job']] if fixture['job'] and not fixture['omit_jobs'] else []})
    if path.startswith('/api/jobs/'):
        return request.fulfill(json=fixture['job'])
    if path.startswith('/files/'):
        if fixture['mesh_failure']:
            return request.fulfill(status=404, json={'error': 'Fixture unavailable'})
        return request.fulfill(body=mesh, content_type='application/octet-stream')
    file = STATIC / ('labels.html' if path == '/labels' else path.removeprefix('/static/'))
    mime = {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html',
            '.json': 'application/json'}.get(file.suffix, 'text/plain')
    headers = {'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"} if file.suffix == '.html' else {}
    return request.fulfill(body=file.read_bytes(), content_type=mime, headers=headers)


def assert_layout(page, configuration):
    expected = label_layout(LabelConfiguration.parse(configuration))
    actual = page.locator('#label-artwork g[data-line]').evaluate_all("""groups => groups.map(group => ({
      color: group.getAttribute('fill'),
      transforms: [...group.querySelectorAll('path')].map(path => path.getAttribute('transform'))
    }))""")
    assert len(actual) == len(expected)
    for shown, native in zip(actual, expected):
        assert shown['color'] == native['color']
        for transform, glyph in zip(shown['transforms'], native['glyphs']):
            import re
            values = list(map(float, re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?', transform)))
            desired = [glyph['x'], label_dimensions(configuration.get('family', 'S'))['height_mm'] - native['baseline_y'],
                       native['scale'], -native['scale']]
            assert all(abs(a - b) < 1e-9 for a, b in zip(values, desired)), (values, desired)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.chromium, headless=True,
        args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if 'Content Security Policy' in message.text else None)
    page.route('**/*', route)
    page.goto('http://vault.test/labels')
    expect(page.locator('#generate-label')).to_be_enabled()
    expect(page.locator('#font-name')).to_have_text('DejaVu Sans Bold')
    expect(page.locator('#label-family-options button')).to_have_count(3)
    assert_layout(page, label_catalog()['defaults'])
    page.get_by_role('button', name='Two lines', exact=True).click()
    page.locator('#line-text-0').fill('Bolts & nuts')
    page.locator('#line-size-0').fill('5')
    page.locator('#line-text-1').fill('M3 · M4 · M5')
    page.locator('#line-size-1').fill('3.5')
    expected_config = {'part': 'label', 'family': 'S', 'background': '#30343b', 'hollow': True,
                       'lines': [{'text': 'Bolts & nuts', 'size': 5, 'color': '#ffffff'},
                                 {'text': 'M3 · M4 · M5', 'size': 3.5, 'color': '#d9a56a'}]}
    expect(page.locator('#generate-label')).to_be_enabled()
    assert_layout(page, expected_config)
    expect(page.locator('#material-summary')).to_contain_text('3 colors')
    page.locator('#line-text-0').fill('★')
    expect(page.locator('#validation-message')).to_contain_text('font does not include')
    expect(page.locator('#generate-label')).to_be_disabled()
    page.locator('#line-text-0').fill('MMMMMMMMMMMMMMMMMMMM')
    expect(page.locator('#validation-message')).to_contain_text('too wide')
    page.locator('#line-text-0').fill('')
    expect(page.locator('#generate-label')).to_be_disabled()
    page.locator('#line-text-0').fill('Bolts & nuts')
    page.locator('#hollow-label').uncheck()
    expect(page.locator('#construction-note')).to_contain_text('Solid back')
    page.locator('#hollow-label').check()
    page.get_by_role('button', name='One line', exact=True).click()
    expect(page.locator('.line-editor')).to_have_count(1)
    page.get_by_role('button', name='Two lines', exact=True).click()
    expect(page.locator('#line-text-1')).to_have_value('M3 · M4 · M5')
    page.screenshot(path=str(args.output / 'desktop.png'), full_page=True)

    # Width changes move the text and extend the straight section. Font size,
    # height and the rounded end stay at their native dimensions.
    for family in label_catalog()['families']:
        page.locator(f'#label-family-options button[data-family="{family["id"]}"]').click()
        expect(page.locator('#label-summary')).to_contain_text(f'{family["dimensions"]["width_mm"]:g}')
        expect(page.locator('#line-size-0')).to_have_value('5')
        expect(page.locator('#label-artwork > path').nth(1)).to_have_attribute('d', family['outline_svg'])
        assert_layout(page, {**expected_config, 'family': family['id']})
    page.locator('#line-text-0').fill('FASTENERS & FIXINGS')
    page.locator('#line-size-0').fill('8')
    page.locator('#line-text-1').fill('Machine screws · washers · lock nuts')
    page.locator('#line-size-1').fill('4.5')
    long_config = {**expected_config, 'family': 'L', 'lines': [
        {'text': 'FASTENERS & FIXINGS', 'size': 8, 'color': '#ffffff'},
        {'text': 'Machine screws · washers · lock nuts', 'size': 4.5, 'color': '#d9a56a'}]}
    expect(page.locator('#generate-label')).to_be_enabled()
    expect(page.locator('#line-text-1')).to_have_attribute('maxlength', '96')
    assert_layout(page, long_config)
    page.locator('#label-family-options button[data-family="S"]').click()
    expect(page.locator('#generate-label')).to_be_disabled()
    expect(page.locator('#validation-message')).to_contain_text('too wide')
    page.locator('#label-family-options button[data-family="L"]').click()
    page.reload()
    expect(page.locator('#label-family-options button[data-family="L"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#line-text-1')).to_have_value(long_config['lines'][1]['text'])
    assert_layout(page, long_config)
    page.screenshot(path=str(args.output / 'desktop-l.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'L label mobile overflow'
    page.screenshot(path=str(args.output / 'mobile-l.png'), full_page=True)
    page.locator('#line-size-1').scroll_into_view_if_needed()
    expect(page.locator('#mobile-label-face')).to_have_attribute('viewBox', '-2 -2 133.4 23.4')
    assert page.locator('.mobile-face-scroll').evaluate('node => node.scrollWidth > node.clientWidth')
    page.screenshot(path=str(args.output / 'mobile-l-editing.png'))
    page.set_viewport_size({'width': 1440, 'height': 1080})
    # A draft saved before families existed still means the original S label.
    legacy_draft = {key: value for key, value in expected_config.items() if key != 'family'}
    page.evaluate('draft => localStorage.setItem("vault-label-draft", JSON.stringify(draft))', legacy_draft)
    page.reload()
    expect(page.locator('#label-family-options button[data-family="S"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#line-text-0')).to_have_value('Bolts & nuts')
    assert_layout(page, expected_config)

    page.locator('#generate-label').click()
    expect(page.locator('#label-job-panel')).to_be_visible()
    expect(page.locator('#job-title')).to_have_text('Generating label')
    expect(page.locator('#generate-label')).to_be_disabled()
    assert fixture['submissions'] == [expected_config]
    fixture['omit_jobs'] = True  # Remembered jobs remain recoverable beyond the recent 30.
    page.reload()
    try:
        expect(page.locator('#label-job-panel')).to_be_visible()
    except AssertionError:
        print('Recovery diagnostic:', fixture['job_requests'], page.evaluate('({...localStorage})'),
              page.locator('#connection-error').text_content(), errors)
        raise
    expect(page.locator('#job-title')).to_have_text('Generating label')
    expect(page.locator('#generate-label')).to_be_disabled()
    expect(page.locator('#line-text-0')).to_have_value('Bolts & nuts')
    assert len(fixture['submissions']) == 1
    fixture['omit_jobs'] = False

    build = {'id': 'saved-label', 'kind': 'label', 'name': 'Label · Bolts & nuts / M3 · M4 · M5',
             'configuration': legacy_draft, 'created_at': '2026-10-25T12:00:00Z',
             'three_mf_url': '/files/label/print.3mf', 'bundle_url': '/api/builds/saved-label/bundle.zip',
             'freshness': {'warning': True, 'reasons': ['Repository has uncommitted changes.']},
             'parts': [{'name': name, 'color': color, 'stl_url': f'/files/label/{name}.stl',
                        'print_step_url': f'/files/label/{name}.step'}
                       for name, color in [('base', '#30343b'), ('white', '#ffffff'), ('gold', '#d9a56a')]]}
    fixture['builds'] = [build]
    fixture['job'].update(status='completed', builds=[build], bundle_url='/api/jobs/label-job-1/bundle.zip')
    expect(page.locator('#job-title')).to_have_text('Your label is ready', timeout=10000)
    expect(page.locator('#label-model')).to_have_attribute('data-model-ready', 'true')
    expect(page.locator('#label-face')).to_be_hidden()
    expect(page.locator('#download-3mf')).to_have_attribute('href', '/files/label/print.3mf')
    expect(page.locator('#download-zip')).to_have_attribute('href', '/api/jobs/label-job-1/bundle.zip')
    expect(page.locator('#construction-note')).to_contain_text('S · 47 mm wide')
    expect(page.locator('#color-downloads .color-part-row')).to_have_count(3)
    expect(page.locator('#generate-label')).to_be_enabled()
    page.locator('#line-text-0').fill('Washers')
    expect(page.locator('#label-face')).to_be_visible()
    expect(page.locator('#label-model')).to_be_hidden()
    page.locator('#label-history button').click()
    expect(page.locator('#label-model')).to_be_visible()
    expect(page.locator('#line-text-0')).to_have_value('Washers')
    expect(page.locator('#download-zip')).to_have_attribute('href', '/api/builds/saved-label/bundle.zip')
    page.locator('#face-view').click()
    fixture['mesh_failure'] = True
    page.locator('#model-view').click()
    expect(page.locator('#model-message')).to_contain_text('preview could not be loaded')
    expect(page.locator('#download-3mf')).to_be_visible()
    page.locator('#face-view').click()
    fixture['mesh_failure'] = False

    page.locator('#generate-label').click()
    expect(page.locator('#job-title')).to_have_text('Generating label')
    page.locator('#label-history button').click()
    expect(page.locator('#label-model')).to_have_attribute('data-model-ready', 'true')
    newer = {**build, 'id': 'newer-label', 'name': 'Label · Washers',
             'configuration': {**fixture['submissions'][-1], 'family': 'L', 'hollow': False, 'background': '#335f80'},
             'label_dimensions': {**label_dimensions('L'), 'width_mm': 128.8},
             'three_mf_url': '/files/newer/print.3mf'}
    fixture['job'].update(status='completed', builds=[newer], bundle_url='/api/jobs/label-job-2/bundle.zip')
    expect(page.locator('#job-title')).to_have_text('Your label is ready', timeout=10000)
    expect(page.locator('#preview-title')).to_have_text(build['name'])
    expect(page.locator('#download-3mf')).to_have_attribute('href', '/files/label/print.3mf')
    page.locator('#view-job-result').click()
    expect(page.locator('#download-3mf')).to_have_attribute('href', '/files/newer/print.3mf')
    expect(page.locator('#construction-note')).to_contain_text('Solid back')
    expect(page.locator('#construction-note')).to_contain_text('L · 128.8 mm wide')
    expect(page.locator('#label-section')).to_have_attribute('viewBox', '-3 -1 134.8 8')
    expect(page.locator('#label-section path')).to_have_attribute('fill', '#335f80')
    expect(page.locator('#hollow-label')).to_be_checked()
    page.locator('#face-view').click()
    expect(page.locator('#construction-note')).to_contain_text('Hollow back')
    expect(page.locator('#construction-note')).to_contain_text('S · 47 mm wide')
    expect(page.locator('#label-section')).to_have_attribute('viewBox', '-3 -1 53 8')
    expect(page.locator('#label-section path')).to_have_attribute('fill', '#30343b')
    page.locator('#generate-label').click()
    expect(page.locator('#job-title')).to_have_text('Generating label')
    fixture['job'].update(status='failed', error='Fixture validation failed', logs='Validation failed before publishing.')
    expect(page.locator('#job-title')).to_have_text('Label generation failed', timeout=10000)
    expect(page.locator('#job-error')).to_contain_text('Fixture validation failed')
    expect(page.locator('#generate-label')).to_be_enabled()
    expect(page.locator('#download-3mf')).to_be_visible()
    assert len(fixture['submissions']) == 3

    fixture['job'].update(status='completed', builds=[build], bundle_url='/api/jobs/label-job-3/bundle.zip', error=None)
    page.reload()
    expect(page.locator('#job-title')).to_have_text('Your label is ready')
    page.locator('#face-view').click()

    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('#line-text-0').fill('Bolts & nuts')
    page.evaluate('window.scrollTo(0, 0)')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
    expect(page.locator('#line-text-0')).to_be_visible()
    expect(page.locator('#label-face')).to_be_visible()
    page.screenshot(path=str(args.output / 'mobile.png'), full_page=True)
    page.locator('#line-size-1').scroll_into_view_if_needed()
    assert page.locator('.mobile-label-live').bounding_box()['y'] >= 0
    page.screenshot(path=str(args.output / 'mobile-editing.png'))

    # A legal unbroken 96-character name must wrap in every saved-build label.
    long_name = 'i' * 96
    unbroken_config = LabelConfiguration.parse({'family': 'L', 'lines': [{'text': long_name, 'size': 3}]}).as_dict()
    unbroken_build = {**build, 'id': 'unbroken-label', 'name': 'L Label · ' + long_name,
                      'configuration': unbroken_config}
    fixture['builds'] = [unbroken_build]
    fixture['job'].update(configuration=unbroken_config, builds=[unbroken_build])
    page.evaluate('draft => localStorage.setItem("vault-label-draft", JSON.stringify(draft))', unbroken_config)
    page.reload()
    expect(page.locator('#preview-title')).to_have_text(unbroken_build['name'])
    expect(page.locator('#job-description')).to_contain_text(long_name)
    expect(page.locator('#generate-label')).to_be_enabled()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Unbroken saved label mobile overflow'
    assert not errors, errors
    browser.close()
print('Label browser checks passed: S/M/L sizing, exact layout, legacy drafts/builds, edits, validation, job recovery, downloads, failures, desktop/mobile.')
