"""Selection/cache regression checks using deterministic browser fixtures, no CAD jobs."""
import argparse
import shutil
from pathlib import Path
import struct
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright, expect
from vault.generator import Configuration, catalog
from vault.assembly import assembly_definition

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--chromium', default=shutil.which('chromium'))
args = parser.parse_args()
if not args.chromium:
    parser.error('Pass --chromium or add Chromium to PATH')

STATIC = Path(__file__).resolve().parents[1] / 'src/vault/static'
mesh = bytes(80) + struct.pack('<I', 1) + struct.pack('<12fH', 0,0,1, 0,0,0, 10,0,0, 0,10,0, 0)
def build(kind, config, name):
    return dict(id=name, kind=kind, name=name, configuration=dict(part=kind, **config),
                created_at='2026-10-24T00:00:00Z',
                freshness=dict(warning=True, reasons=['Cached build is from a different commit; rebuild for the current revision.']),
                parts=[dict(name=name, stl_url='/files/test/mesh.stl', print_bbox_mm=[10,10,1])])
builds = [build('rails',dict(family='L'),'L geared rails'),
          build('box',dict(family='L',depth_units=6,height_units=2),'L6 box thin'),
          build('box',dict(family='L',depth_units=6,height_units=2,box_floor=3),'L6 box thick')]
builds += [build(kind, {}, kind) for kind in ('key','spring','runner_stop','facade_cap','key_cap', 'latch')]
builds += [build('module', dict(family='L', depth_units=6, height_units=2, drawer_columns=2), 'L6² Module 2F'),
           build('box', dict(family='S', depth_units=6, height_units=2, box_floor=3), 'S6 box thick'),
           build('facade', dict(family='S', height_units=2), 'S2F facade'),
           build('rails', dict(family='S'), 'S geared rails'),
           build('box', dict(family='S', depth_units=6, height_units=1, box_floor=3), 'S6 1F box thick'),
           build('facade', dict(family='S', height_units=1), 'S1F facade')]
legacy = build('module', dict(family='L', depth_units=6, height_units=2, drawer_columns=2, drawer_rows=2), 'L6² Module 2F · 4 S1F drawers')
legacy['legacy_partitioned_module'] = True
builds.insert(0, legacy)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.chromium, headless=True,
        args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width':1440,'height':1150})
    errors, assembly_queries, submissions = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def route(request):
        parsed = urlsplit(request.request.url)
        path = parsed.path
        if path == '/api/jobs' and request.request.method == 'POST':
            submissions.append(request.request.post_data_json)
            return request.fulfill(json={'id':'fixture-job','configuration':submissions[-1],'status':'queued','log':[],'builds':[]})
        if path == '/api/jobs/fixture-job':
            return request.fulfill(json={'id':'fixture-job','configuration':submissions[-1],'status':'queued','log':[],'builds':[]})
        if path == '/api/assembly':
            query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            assembly_queries.append(query)
            if query.get('drawer_columns') == '2':
                config = Configuration(family=query['family'], depth_units=int(query['depth_units']),
                                       height_units=int(query['height_units']), drawer_columns=2,
                                       drawer_rows=int(query['drawer_rows']))
                scene = assembly_definition(config)
                suffix = ' · 4 drawers' if config.drawer_rows == 2 else ''
                scene.update(name=f'L{config.depth_units}² · {config.height_units}F{suffix} complete set',
                             missing=[], warnings=[], complete=True, validation={'passed':True})
                for item in scene['instances']:
                    item.update(mesh_url='/files/test/mesh.stl', build_id=item['kind'], freshness={'warning':False})
                return request.fulfill(json=scene)
        saved_jobs = [{'id':'fixture-job','configuration':submissions[-1],'status':'queued','log':[],'builds':[]}] if submissions else []
        payload = {'/api/config':catalog(), '/api/jobs':{'jobs':saved_jobs},
                   '/api/assembly':{'name':'Complete set', 'instances':[], 'missing':[], 'warnings':[], 'complete':False},
                   '/api/builds':{'builds':builds,'repository':{'commit':'newcommit','dirty':True}}}.get(path)
        if payload is not None: return request.fulfill(json=payload)
        if path.startswith('/files/'): return request.fulfill(body=mesh,content_type='application/octet-stream')
        file = STATIC / ('index.html' if path == '/' else path.removeprefix('/static/'))
        mime = {'.js':'text/javascript','.css':'text/css','.html':'text/html'}.get(file.suffix,'text/plain')
        request.fulfill(body=file.read_bytes(),content_type=mime)
    page.route('**/*',route)
    page.goto('http://vault.test/')
    expect(page.locator('#box-floor-options button')).to_have_count(2)
    expect(page.locator('#drawer-layout-options button[data-value="2"]')).to_be_disabled()
    expect(page.locator('#drawer-layout-options button[data-value="4"]')).to_be_disabled()
    expect(page.locator('#part-options .common-components-heading')).to_have_text('Common components')
    assert page.locator('#part-options').evaluate('node => Array.from(node.children).findIndex(child => child.classList.contains("common-components-heading"))') == 7
    assert page.locator('#part-options .common-components-heading').evaluate('node => getComputedStyle(node).borderTopStyle') == 'solid'
    expect(page.locator('#repository-status')).to_have_count(0)
    expect(page.locator('.preview-status-row .revision-status')).to_have_count(1)
    expect(page.locator('#build-freshness')).to_contain_text('⚠ Uncommitted changes')
    for target,value in [('family','L'),('depth','6'),('height','2'),('part','rails')]:
        page.locator(f'#{target}-options button[data-value="{value}"]').click()
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true')
    expect(page.locator('#preview-title')).to_have_text('L geared rails')
    assert 'different commit' in page.locator('#build-freshness').get_attribute('title')
    page.locator('#part-options button[data-value="module"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    expect(page.locator('#model-canvas')).to_be_hidden()
    expect(page.locator('#artifact-panel')).to_be_hidden()
    page.locator('#part-options button[data-value="box"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6 box thin')
    page.locator('#box-floor-options button[data-value="3"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6 box thick')
    page.locator('#depth-options button[data-value="7"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    for kind in ('key','spring','runner_stop','facade_cap','key_cap', 'latch'):
        page.locator(f'#part-options button[data-value="{kind}"]').click()
        expect(page.locator('#preview-title')).to_have_text(kind)
        expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true')
    page.locator('#depth-options button[data-value="6"]').click()
    page.locator('#drawer-layout-options button[data-value="2"]').click()
    expect(page.locator('#configuration-name')).to_have_text('L6² · 2F')
    expect(page.locator('#drawer-layout-hint')).to_contain_text('Two S2F drawers')
    expect(page.locator('#drawer-layout-hint')).to_contain_text('same open module')
    for kind, name in [('module','L6² Module 2F'), ('box','S6 box thick'),
                       ('facade','S2F facade'), ('rails','S geared rails')]:
        page.locator(f'#part-options button[data-value="{kind}"]').click()
        expect(page.locator('#preview-title')).to_have_text(name)
        expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true')
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(25)
    expect(page.locator('#part-hint')).to_contain_text('Print 4 pairs')
    expect(page.locator('#preview-title')).to_have_text('L6² · 2F complete set')
    assert assembly_queries[-1]['drawer_columns'] == '2'
    page.locator('#family-options button[data-value="M"]').click()
    expect(page.locator('#drawer-layout-options button[data-value="1"]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('#drawer-layout-options button[data-value="2"]')).to_be_disabled()
    expect(page.locator('#configuration-name')).to_have_text('M6 · 2F')
    assert assembly_queries[-1]['drawer_columns'] == '1'
    page.locator('#family-options button[data-value="L"]').click()
    expect(page.locator('#drawer-layout-options button[data-value="1"]')).to_have_attribute('aria-pressed','true')
    page.locator('#part-options button[data-value="box"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6 box thick')
    page.locator('#drawer-layout-options button[data-value="2"]').click()
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(25)
    output = STATIC.parents[2] / 'out/web-review'
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / 'multi-drawer-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(output / 'multi-drawer-mobile.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width':1440,'height':1150})
    page.locator('#drawer-layout-options button[data-value="4"]').click()
    expect(page.locator('#configuration-name')).to_have_text('L6² · 2F · 4 drawers')
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(33)
    expect(page.locator('#part-hint')).to_contain_text('four S1F boxes')
    expect(page.locator('#drawer-layout-hint')).to_contain_text('shared open L2F module')
    assert assembly_queries[-1]['drawer_rows'] == '2'
    for kind, name in [('module','L6² Module 2F'), ('box','S6 1F box thick'),
                       ('facade','S1F facade'), ('rails','S geared rails')]:
        page.locator(f'#part-options button[data-value="{kind}"]').click()
        expect(page.locator('#preview-title')).to_have_text(name)
    # Historical partitioned modules remain inspectable but cannot match either open-module layout.
    page.locator('.history-card').filter(has_text='L6² Module 2F · 4 S1F drawers').click()
    expect(page.locator('#preview-title')).to_have_text('L6² Module 2F · 4 S1F drawers')
    expect(page.locator('#configuration-name')).to_have_text('L6² · 2F · 4 drawers')
    page.locator('#part-options button[data-value="module"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6² Module 2F')
    expect(page.locator('#part-hint')).to_contain_text('Fits two S2F drawers or four S1F drawers')
    page.locator('#depth-options button[data-value="7"]').click()
    page.locator('#drawer-layout-options button[data-value="2"]').click()
    open_envelope = page.locator('#envelope-drawing').inner_html()
    page.locator('#drawer-layout-options button[data-value="4"]').click()
    assert page.locator('#envelope-drawing').inner_html() == open_envelope, 'Both layouts use the same open two-bay shell'
    page.locator('#depth-options button[data-value="6"]').click()
    page.locator('#drawer-layout-options button[data-value="2"]').click()
    page.locator('#part-options button[data-value="box"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 box thick')
    page.locator('#drawer-layout-options button[data-value="4"]').click()
    page.locator('#height-options button[data-value="1"]').click()
    expect(page.locator('#drawer-layout-options button[data-value="4"]')).to_be_disabled()
    expect(page.locator('#drawer-layout-options button[data-value="2"]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('#configuration-name')).to_have_text('L6² · 1F')
    page.locator('#height-options button[data-value="2"]').click()
    expect(page.locator('#drawer-layout-options button[data-value="2"]')).to_have_attribute('aria-pressed','true')
    page.locator('#drawer-layout-options button[data-value="4"]').click()
    page.locator('#family-options button[data-value="S"]').click()
    expect(page.locator('#drawer-layout-options button[data-value="1"]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('#drawer-layout-options button[data-value="4"]')).to_be_disabled()
    page.locator('#family-options button[data-value="L"]').click()
    page.locator('#drawer-layout-options button[data-value="4"]').click()
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(33)
    page.screenshot(path=str(output / 'four-drawer-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(output / 'four-drawer-mobile.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#build-button').click()
    expect(page.locator('#build-button')).to_be_disabled()
    assert len(submissions) == 1 and submissions[0]['drawer_columns'] == 2 and submissions[0]['family'] == 'L'
    assert submissions[0]['drawer_rows'] == 2 and submissions[0]['height_units'] == 2
    page.reload()
    expect(page.locator('#job-description')).to_contain_text('L6² · 2F · 4 drawers')
    expect(page.locator('#job-status')).to_have_text('Queued')
    expect(page.locator('#build-button')).to_be_disabled()
    assert not errors, errors
    browser.close()
print('Configurator browser checks passed')
