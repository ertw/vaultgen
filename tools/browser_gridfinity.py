"""Gridfinity and drawer-fit box editor checks with fixtures; never creates CAD jobs."""
import argparse
import json
from pathlib import Path
import shutil
import struct
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from vault.bin_config import BinConfiguration, bin_catalog, bin_layout


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--chromium', default=shutil.which('chromium'))
parser.add_argument('--output', type=Path, default=Path('out/web-review/gridfinity'))
args = parser.parse_args()
if not args.chromium:
    parser.error('Pass --chromium or add Chromium to PATH')
args.output.mkdir(parents=True, exist_ok=True)
STATIC = Path(__file__).resolve().parents[1] / 'src/vault/static'

# Closed local fixture meshes exercise the shared renderer without native CAD.
vertices = [(x, y, z) for z in (0, 28) for y in (0, 41.5) for x in (0, 41.5)]
faces = [(0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6), (0, 1, 4), (1, 5, 4),
         (2, 6, 3), (3, 6, 7), (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)]
mesh = bytes(80) + struct.pack('<I', len(faces)) + b''.join(
    struct.pack('<12fH', 0, 0, 0, *(coordinate for i in face for coordinate in vertices[i]), 0)
    for face in faces)
fixture = {'job': None, 'builds': [], 'submissions': [], 'mesh_failure': False,
           'omit_jobs': False, 'job_requests': [], 'mesh_requests': [],
           'delay_jobs': True, 'pending_jobs': []}


def route(request):
    path = urlsplit(request.request.url).path
    if path.startswith('/api/jobs'):
        fixture['job_requests'].append((request.request.method, path))
    if path == '/api/gridfinity/config':
        return request.fulfill(json=fixture.get('catalog', bin_catalog()))
    if path == '/api/builds':
        return request.fulfill(json={'builds': fixture['builds']})
    if path == '/api/jobs' and request.request.method == 'POST':
        configuration = json.loads(request.request.post_data)
        # Validate the actual browser submission against the HTTP contract.
        BinConfiguration.parse(configuration)
        fixture['submissions'].append(configuration)
        fixture['job'] = {'id': f"bin-job-{len(fixture['submissions'])}",
                          'configuration': configuration, 'status': 'running',
                          'builds': [], 'logs': 'Checking container solids…'}
        return request.fulfill(json=fixture['job'], status=202)
    if path == '/api/jobs':
        if fixture['delay_jobs']:
            fixture['pending_jobs'].append(request)
            return
        return request.fulfill(json={'jobs': [fixture['job']]
            if fixture['job'] and not fixture['omit_jobs'] else []})
    if path.startswith('/api/jobs/'):
        return request.fulfill(json=fixture['job'])
    if path.startswith('/files/'):
        fixture['mesh_requests'].append(path)
        if fixture['mesh_failure']:
            return request.fulfill(status=404, json={'error': 'Fixture unavailable'})
        return request.fulfill(body=mesh, content_type='application/octet-stream')
    file = STATIC / ('gridfinity.html' if path == '/gridfinity' else path.removeprefix('/static/'))
    mime = {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html',
            '.json': 'application/json'}.get(file.suffix, 'text/plain')
    headers = {'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"} if file.suffix == '.html' else {}
    return request.fulfill(body=file.read_bytes(), content_type=mime, headers=headers)


def cells(page):
    return page.locator('#drawer-grid [data-kind="cell"]')


def cell(page, x, y):
    return page.locator(f'#drawer-grid [data-kind="cell"][data-x="{x}"][data-y="{y}"]')


def divider(page, axis, x, y):
    return page.locator(f'#drawer-grid [data-kind="divider"][data-axis="{axis}"][data-x="{x}"][data-y="{y}"]')


def click_divider(page, axis, x, y):
    # SVG line bounding boxes exclude their painted stroke: a valid vertical
    # hit target has zero geometric width, so use its actual screen midpoint.
    page.locator('#drawer-grid').scroll_into_view_if_needed()
    point = divider(page, axis, x, y).evaluate('node => { const box = node.getBoundingClientRect(); return [box.x + box.width/2, box.y + box.height/2]; }')
    page.mouse.click(*point)


def selected_cells(page):
    return sorted(cells(page).evaluate_all('nodes => nodes.filter(node => node.getAttribute("aria-pressed") === "true").map(node => [+node.dataset.x, +node.dataset.y])'), key=lambda xy: (xy[1], xy[0]))


def option(page, group, value):
    return page.locator(f'#bin-{group}-options button[data-value="{value}"]')


def millimeters(value):
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def drag_cells(page, coordinates):
    cell(page, *coordinates[0]).scroll_into_view_if_needed()
    points = [cell(page, *xy).bounding_box() for xy in coordinates]
    page.mouse.move(points[0]['x'] + points[0]['width']/2, points[0]['y'] + points[0]['height']/2)
    page.mouse.down()
    for point in points[1:]:
        page.mouse.move(point['x'] + point['width']/2, point['y'] + point['height']/2, steps=5)
    page.mouse.up()


def saved_build(identifier, configuration):
    native = BinConfiguration.parse(configuration)
    layout = bin_layout(native)
    return {'id': identifier, 'kind': 'gridfinity_bins', 'name': native.name,
            'configuration': native.as_dict(), 'created_at': '2026-10-27T12:00:00Z',
            'gridfinity_layout': layout, 'bundle_url': f'/api/builds/{identifier}/bundle.zip',
            'freshness': {'warning': True, 'reasons': ['Repository has uncommitted changes.']},
            'parts': [{'name': component['name'],
                       'stl_url': f'/files/{identifier}/{component["name"]}.stl',
                       'print_step_url': f'/files/{identifier}/{component["name"]}.step',
                       'print_bbox_mm': [41.5, 41.5, native.height_mm]}
                      for component in layout['components']]}


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.chromium, headless=True,
        args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text)
            if 'Content Security Policy' in message.text else None)
    page.route('**/*', route)
    page.goto('http://vault.test/gridfinity')
    # The saved drawing can load before job recovery. During that window the
    # page must not create another build or overwrite the job being recovered.
    expect(cells(page)).to_have_count(len(bin_catalog()['defaults']['cells']))
    expect(page.locator('#generate-bins')).to_be_disabled()
    page.evaluate('document.querySelector("#bin-form").requestSubmit()')
    assert not fixture['submissions'], 'Submission must wait for initial job recovery'
    assert fixture['pending_jobs'], 'Expected delayed initial job recovery'
    fixture['delay_jobs'] = False
    for pending in fixture['pending_jobs']:
        pending.fulfill(status=503, json={'error': 'Fixture recovery unavailable'})
    fixture['pending_jobs'].clear()
    expect(page.locator('#connection-error')).to_contain_text('Fixture recovery unavailable')
    expect(page.locator('#retry-jobs')).to_be_visible()
    expect(page.locator('#generate-bins')).to_be_disabled()
    page.evaluate('document.querySelector("#bin-form").requestSubmit()')
    assert not fixture['submissions'], 'Failed recovery must not allow duplicate jobs'
    page.locator('#retry-jobs').click()
    expect(page.locator('#generate-bins')).to_be_enabled()
    expect(page.locator('#retry-jobs')).to_be_hidden()
    expect(page.locator('#connection-error')).to_be_hidden()
    expect(page.get_by_role('link', name='Gridfinity', exact=True)).to_have_attribute('aria-current', 'page')
    expect(page.locator('#bin-family-options button')).to_have_count(3)
    expect(page.locator('#bin-depth-options button')).to_have_count(5)
    expect(page.locator('#bin-height-options button')).to_have_count(2)
    expect(page.locator('#bin-type-options button')).to_have_count(2)
    expect(option(page, 'type', 'gridfinity')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#balanced-design')).to_be_hidden()
    expect(page.locator('#drawer-floor-setting')).to_be_hidden()
    assert selected_cells(page) == bin_catalog()['defaults']['cells']

    # Full drawings expand to the selected drawer. Partial drawings preserve
    # in-bounds cells and discard edges that no longer join painted cells.
    option(page, 'family', 'M').click()
    expect(cells(page)).to_have_count(20)
    assert len(selected_cells(page)) == 20
    option(page, 'family', 'L').click()
    option(page, 'depth', 7).click()
    expect(cells(page)).to_have_count(42)
    assert len(selected_cells(page)) == 42
    option(page, 'height', 2).click()
    expect(page.locator('#height-hint')).to_contain_text('77')
    page.screenshot(path=str(args.output / 'desktop-full-l7.png'), full_page=True)
    page.locator('#clear-layout').click()
    expect(page.locator('#generate-bins')).to_be_disabled()
    for xy in ((0, 0), (1, 0), (0, 1), (5, 6)):
        cell(page, *xy).click()
    option(page, 'family', 'S').click()
    option(page, 'depth', 3).click()
    expect(cells(page)).to_have_count(9)
    assert selected_cells(page) == [[0, 0], [1, 0], [0, 1]]
    option(page, 'depth', 4).click()
    assert len(selected_cells(page)) == 3, 'Partial drawings must not expand on resize'
    option(page, 'depth', 3).click()
    option(page, 'height', 1).click()

    page.locator('#clear-layout').click()
    drag_cells(page, ((0, 0), (1, 0), (2, 0)))
    assert selected_cells(page) == [[0, 0], [1, 0], [2, 0]]
    page.locator('#undo-layout').click()
    assert selected_cells(page) == [], 'Undo should revert one whole painting stroke'
    drag_cells(page, ((0, 0), (1, 0), (2, 0)))
    cell(page, 0, 1).click()
    cell(page, 2, 2).click()
    expect(page.locator('#bin-count')).to_contain_text('2 containers')
    page.locator('[data-tool="dividers"]').click()
    click_divider(page, 'x', 1, 0)
    click_divider(page, 'y', 0, 1)
    expect(divider(page, 'x', 1, 0)).to_have_attribute('aria-pressed', 'true')
    expect(divider(page, 'y', 0, 1)).to_have_attribute('aria-pressed', 'true')
    page.locator('#clear-dividers').click()
    expect(page.locator('[data-kind="divider"][aria-pressed="true"]')).to_have_count(0)
    page.locator('#undo-layout').click()
    expect(page.locator('[data-kind="divider"][aria-pressed="true"]')).to_have_count(2)
    page.locator('[data-tool="erase"]').click()
    cell(page, 0, 1).click()
    expect(page.locator('[data-kind="divider"][aria-pressed="true"]')).to_have_count(1)
    page.locator('#undo-layout').click()
    expect(page.locator('[data-kind="divider"][aria-pressed="true"]')).to_have_count(2)
    page.locator('[data-tool="cells"]').click()
    option(page, 'pattern', 'miura').click()
    option(page, 'perimeter', 1).click()
    expect(page.locator('#perimeter-hint')).to_contain_text('0.65')
    option(page, 'perimeter', 2).click()
    expect(page.locator('#perimeter-hint')).to_contain_text('1.3')
    option(page, 'perimeter', 1).click()
    expected_config = BinConfiguration(family='S', depth_units=3, height_units=1,
        cells=((0, 0), (1, 0), (2, 0), (0, 1), (2, 2)),
        dividers=({'axis': 'x', 'x': 1, 'y': 0}, {'axis': 'y', 'x': 0, 'y': 1}),
        wall_pattern='miura', wall_perimeters=1).as_dict()
    page.reload()
    expect(option(page, 'pattern', 'miura')).to_have_attribute('aria-pressed', 'true')
    expect(option(page, 'perimeter', 1)).to_have_attribute('aria-pressed', 'true')
    assert selected_cells(page) == expected_config['cells']
    expect(page.locator('[data-kind="divider"][aria-pressed="true"]')).to_have_count(2)
    page.screenshot(path=str(args.output / 'desktop-editor.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile editor overflow'
    page.screenshot(path=str(args.output / 'mobile-editor.png'), full_page=True)
    page.set_viewport_size({'width': 1440, 'height': 1080})

    page.locator('#generate-bins').click()
    expect(page.locator('#bin-job-panel')).to_be_visible()
    expect(page.locator('#generate-bins')).to_be_disabled()
    page.evaluate('document.querySelector("#bin-form").requestSubmit()')
    assert fixture['submissions'] == [expected_config], 'An active build must prevent repeat submission'
    fixture['omit_jobs'] = True  # Recovery must work beyond the recent jobs list.
    page.reload()
    expect(page.locator('#bin-job-panel')).to_be_visible()
    expect(page.locator('#generate-bins')).to_be_disabled()
    assert ('GET', '/api/jobs/bin-job-1') in fixture['job_requests']
    assert selected_cells(page) == expected_config['cells']
    assert len(fixture['submissions']) == 1
    fixture['omit_jobs'] = False

    build = saved_build('saved-bins', expected_config)
    fixture['builds'] = [build, {'id': 'label-build', 'kind': 'label', 'name': 'Unrelated label'}]
    fixture['job'].update(status='completed', builds=[build], bundle_url='/api/jobs/bin-job-1/bundle.zip')
    expect(page.locator('#generate-bins')).to_be_enabled(timeout=10000)
    expect(page.locator('#bin-model')).to_have_attribute('data-model-ready', 'true')
    expect(page.locator('#preview-part option')).to_have_count(2)
    expect(page.locator('#part-downloads .bin-part-row')).to_have_count(2)
    expect(page.locator('#design-metrics')).to_be_hidden()
    expect(page.locator('#download-zip')).to_have_attribute('href', '/api/jobs/bin-job-1/bundle.zip')
    for part in build['parts']:
        expect(page.locator(f'#part-downloads a[href="{part["stl_url"]}"]')).to_be_visible()
        expect(page.locator(f'#part-downloads a[href="{part["print_step_url"]}"]')).to_be_visible()
    page.locator('#preview-part').select_option(index=1)
    expect(page.locator('#bin-model')).to_have_attribute('data-model-ready', 'true')
    assert '/files/saved-bins/bin_02.stl' in fixture['mesh_requests']
    page.screenshot(path=str(args.output / 'desktop-result.png'), full_page=True)

    # Browsing a previous result leaves the edited drawing intact.
    page.locator('#layout-view').click()
    cell(page, 1, 1).click()
    edited_cells = selected_cells(page)
    expect(page.locator('#draft-note')).to_be_visible()
    expect(page.locator('#model-panel')).to_be_hidden()
    page.locator('#refresh-bins').click()
    expect(page.locator('#bin-history button')).to_have_count(1)
    page.locator('#bin-history button').click()
    expect(page.locator('#model-panel')).to_be_visible()
    expect(page.locator('#download-zip')).to_have_attribute('href', '/api/builds/saved-bins/bundle.zip')
    page.locator('#layout-view').click()
    assert selected_cells(page) == edited_cells
    fixture['mesh_failure'] = True
    page.locator('#model-view').click()
    expect(page.locator('#model-message')).to_contain_text('preview could not be loaded')
    expect(page.locator('#download-zip')).to_be_visible()
    fixture['mesh_failure'] = False
    page.locator('#layout-view').click()

    page.locator('#generate-bins').click()
    expect(page.locator('#generate-bins')).to_be_disabled()
    page.locator('#bin-history button').click()
    expect(page.locator('#bin-model')).to_have_attribute('data-model-ready', 'true')
    newer = saved_build('newer-bins', fixture['submissions'][-1])
    fixture['job'].update(status='completed', builds=[newer], bundle_url='/api/jobs/bin-job-2/bundle.zip')
    expect(page.locator('#generate-bins')).to_be_enabled(timeout=10000)
    expect(page.locator('#download-zip')).to_have_attribute('href', '/api/builds/saved-bins/bundle.zip')
    page.locator('#view-job-result').click()
    expect(page.locator('#download-zip')).to_have_attribute('href', '/api/jobs/bin-job-2/bundle.zip')
    page.locator('#layout-view').click()
    page.locator('#generate-bins').click()
    fixture['job'].update(status='failed', error='Fixture validation failed',
                          logs='Failed before immutable publication.')
    expect(page.locator('#job-error')).to_contain_text('Fixture validation failed', timeout=10000)
    expect(page.locator('#generate-bins')).to_be_enabled()
    expect(page.locator('#download-zip')).to_be_visible()
    assert len(fixture['submissions']) == 3

    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('#model-view').click()
    expect(page.locator('#bin-model')).to_have_attribute('data-model-ready', 'true')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile result overflow'
    page.screenshot(path=str(args.output / 'mobile-result.png'), full_page=True)

    # Drawer-fit boxes share the editor, but have a fitted planning grid rather
    # than Gridfinity's fixed pitch. Changing type preserves wall choices and
    # partial drawings; a full drawing fills the new grid.
    page.set_viewport_size({'width': 1440, 'height': 1080})
    page.locator('#layout-view').click()
    page.locator('#fill-drawer').click()
    option(page, 'family', 'M').click()
    option(page, 'depth', 5).click()
    expect(cells(page)).to_have_count(25)
    option(page, 'type', 'drawer').click()
    expect(cells(page)).to_have_count(20)
    assert len(selected_cells(page)) == 20
    expect(option(page, 'pattern', 'miura')).to_have_attribute('aria-pressed', 'true')
    expect(option(page, 'perimeter', 1)).to_have_attribute('aria-pressed', 'true')
    expect(option(page, 'family', 'M')).to_contain_text('4 columns')
    expect(page.locator('#grid-badge')).to_contain_text('4 × 5 · planning grid')
    expect(page.locator('#type-hint')).to_contain_text('plain Vault drawer')
    expect(page.locator('#balanced-design')).to_be_visible()
    expect(page.locator('#drawer-floor-setting')).to_be_visible()
    layout = next(layout for layout in bin_catalog()['drawer_layouts']
                  if (layout['family'], layout['depth_units'], layout['height_units'], layout['drawer_floor']) == ('M', 5, 1, .8))
    grid_ratio = cell(page, 0, 0).evaluate('node => (+node.getAttribute("width") + 6) / (+node.getAttribute("height") + 6)')
    assert abs(grid_ratio - layout['pitch_x_mm']/layout['pitch_y_mm']) < 1e-8, 'Planning grid must preserve physical proportions'
    expect(page.locator('#footprint-size')).to_contain_text(millimeters(layout['outer_width_mm']))
    expect(page.locator('#height-hint')).to_contain_text('1.2 mm floor')
    page.locator('#apply-balanced-design').click()
    expect(option(page, 'perimeter', 2)).to_have_attribute('aria-pressed', 'true')
    assert len(selected_cells(page)) == 20, 'The balanced preset must preserve the layout'
    page.locator('#undo-layout').click()
    expect(option(page, 'perimeter', 1)).to_have_attribute('aria-pressed', 'true')
    page.locator('#apply-balanced-design').click()
    option(page, 'floor', 3).click()
    thick_floor_layout = next(layout for layout in bin_catalog()['drawer_layouts']
                              if (layout['family'], layout['depth_units'], layout['height_units'], layout['drawer_floor']) == ('M', 5, 1, 3))
    expect(page.locator('#height-hint')).to_contain_text(millimeters(thick_floor_layout['height_mm']))
    page.reload()
    expect(option(page, 'floor', 3)).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#height-hint')).to_contain_text(millimeters(thick_floor_layout['height_mm']))
    assert len(selected_cells(page)) == 20, 'Changing the existing floor must preserve the layout'
    option(page, 'floor', .8).click()
    option(page, 'height', 2).click()
    tall_layout = next(layout for layout in bin_catalog()['drawer_layouts']
                       if (layout['family'], layout['depth_units'], layout['height_units'], layout['drawer_floor']) == ('M', 5, 2, .8))
    expect(page.locator('#height-hint')).to_contain_text(millimeters(tall_layout['height_mm']))
    option(page, 'height', 1).click()
    page.screenshot(path=str(args.output / 'desktop-drawer-m5.png'), full_page=True)

    page.locator('#clear-layout').click()
    for xy in ((0, 0), (1, 0), (3, 4)):
        cell(page, *xy).click()
    page.locator('[data-tool="dividers"]').click()
    click_divider(page, 'x', 1, 0)
    option(page, 'type', 'gridfinity').click()
    expect(cells(page)).to_have_count(25)
    assert len(selected_cells(page)) == 3, 'Partial layouts must not expand when changing type'
    page.locator('[data-tool="cells"]').click()
    cell(page, 4, 4).click()
    page.locator('[data-tool="dividers"]').click()
    click_divider(page, 'x', 4, 4)
    option(page, 'type', 'drawer').click()
    assert selected_cells(page) == [[0, 0], [1, 0], [3, 4]]
    expect(page.locator('[data-kind="divider"][aria-pressed="true"]')).to_have_count(1)
    page.locator('#undo-layout').click()
    expect(option(page, 'type', 'gridfinity')).to_have_attribute('aria-pressed', 'true')
    assert len(selected_cells(page)) == 4
    expect(page.locator('[data-kind="divider"][aria-pressed="true"]')).to_have_count(2)
    option(page, 'type', 'drawer').click()
    option(page, 'family', 'S').click()
    option(page, 'depth', 4).click()
    page.locator('#fill-drawer').click()
    page.locator('#clear-dividers').click()
    for x in range(3):
        click_divider(page, 'y', x, 2)
    for x in (1, 2):
        for y in (2, 3):
            click_divider(page, 'x', x, y)
    drawer_config = BinConfiguration(family='S', depth_units=4, height_units=1,
        dividers=tuple({'axis': 'y', 'x': x, 'y': 2} for x in range(3)) +
                 tuple({'axis': 'x', 'x': x, 'y': y} for x in (1, 2) for y in (2, 3)),
        wall_pattern='miura', wall_perimeters=2, container_type='drawer').as_dict()
    page.reload()
    expect(option(page, 'type', 'drawer')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#grid-badge')).to_contain_text('3 × 4 · planning grid')
    expect(page.locator('[data-kind="divider"][aria-pressed="true"]')).to_have_count(7)
    assert selected_cells(page) == drawer_config['cells']
    page.screenshot(path=str(args.output / 'desktop-drawer-editor.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile drawer editor overflow'
    page.screenshot(path=str(args.output / 'mobile-drawer-editor.png'), full_page=True)
    page.set_viewport_size({'width': 1440, 'height': 1080})
    page.locator('#generate-bins').click()
    expect(page.locator('#generate-bins')).to_be_disabled()
    assert fixture['submissions'][-1] == drawer_config, 'Drawer submission must retain its type and normalized native drawing'
    page.reload()
    expect(option(page, 'type', 'drawer')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#job-description')).to_contain_text('Drawer-fit box')
    expect(page.locator('#generate-bins')).to_be_disabled()
    drawer_build = saved_build('saved-drawer', drawer_config)
    drawer_build['design_metrics'] = {'material_volume_cm3': 94.52, 'clear_height_mm': 34.25,
        'planning_area_mm2': 21853.16, 'base_thickness_mm': 1.2, 'wall_thickness_mm': 1.3}
    fixture['builds'] = [drawer_build, build]
    fixture['job'].update(status='completed', builds=[drawer_build], bundle_url='/api/jobs/bin-job-4/bundle.zip')
    expect(page.locator('#generate-bins')).to_be_enabled(timeout=10000)
    expect(page.locator('#model-caption')).to_contain_text('Drawer-fit box')
    expect(page.locator('#design-metrics')).to_have_text('CAD material: 94.52 cm³ · Clear height: 34.25 mm · Base: 1.2 mm · Walls: 1.3 mm')
    expect(page.locator('#download-zip')).to_have_attribute('href', '/api/jobs/bin-job-4/bundle.zip')
    page.locator('#refresh-bins').click()
    expect(page.locator('#bin-history button')).to_have_count(2)
    expect(page.locator('#bin-history button').nth(0)).to_contain_text('Drawer-fit box')
    expect(page.locator('#bin-history button').nth(1)).to_contain_text('Gridfinity')
    page.locator('#bin-history button').nth(1).click()
    expect(page.locator('#model-caption')).to_contain_text('Gridfinity')
    expect(page.locator('#design-metrics')).to_be_hidden()
    page.locator('#layout-view').click()
    expect(option(page, 'type', 'drawer')).to_have_attribute('aria-pressed', 'true')
    assert selected_cells(page) == drawer_config['cells'], 'Viewing Gridfinity history must preserve the drawer draft'

    # Static assets refresh before the Python process during a rolling update.
    # New controls must tolerate the old catalog, including a saved new draft.
    legacy_catalog = bin_catalog()
    for key in ('container_types', 'drawer_floors', 'drawer_layouts', 'balanced_design'):
        legacy_catalog.pop(key)
    for family in legacy_catalog['families']:
        family.pop('drawer_columns')
    fixture['catalog'] = legacy_catalog
    page.reload()
    expect(page.locator('#bin-type-options button')).to_have_count(1)
    expect(option(page, 'type', 'gridfinity')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#drawer-floor-setting')).to_be_hidden()
    expect(cells(page)).to_have_count(len(legacy_catalog['defaults']['cells']))
    expect(page.locator('#generate-bins')).to_be_enabled()
    expect(page.locator('#connection-error')).to_be_hidden()
    assert not errors, errors
    browser.close()
print('Container browser checks passed: Gridfinity and fitted drawer grids, proportions, drawing/undo/dividers, balanced design, wall variants, compatible native payloads, draft and job recovery, mixed history, downloads/previews, failures, desktop/mobile.')
