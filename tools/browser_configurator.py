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
output = STATIC.parents[2] / 'out/web-review'
output.mkdir(parents=True, exist_ok=True)
mesh = bytes(80) + struct.pack('<I', 1) + struct.pack('<12fH', 0,0,1, 0,0,0, 10,0,0, 0,10,0, 0)
def build(kind, config, name):
    if kind in ('module', 'box'):
        config = dict(wall_perimeters=2, nozzle_size=.6, **config) if 'wall_perimeters' not in config else config
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
           build('facade', dict(family='S', height_units=2, facade_floor=0.8), 'S2F shelled facade'),
           build('rails', dict(family='S'), 'S geared rails'),
           build('box', dict(family='S', depth_units=6, height_units=1, box_floor=3), 'S6 1F box thick'),
           build('facade', dict(family='S', height_units=1), 'S1F facade')]
legacy = build('module', dict(family='L', depth_units=6, height_units=2, drawer_columns=2, drawer_rows=2), 'L6² Module 2F · 4 S1F drawers')
legacy['legacy_partitioned_module'] = True
builds.insert(0, legacy)
pattern_config = dict(family='L', depth_units=6, height_units=2, drawer_columns=2,
                      pattern_pitch=14, pattern_depth=1.7)
builds += [build('module', dict(pattern_config, wall_pattern='miura'), 'L6 Miura module'),
           build('module', dict(pattern_config, wall_pattern='miura', pattern_pitch=16,
                                pattern_depth=1.4), 'L6 custom Miura module'),
           build('module', dict(pattern_config, wall_perimeters=None, wall_pattern='plain'), 'Historical L6 solid module'),
           build('module', dict(pattern_config, wall_perimeters='full', wall_pattern='plain'), 'L6 full width module')]
builds += [build('box', dict(family=family, depth_units=6, height_units=height,
                             box_floor=3, box_variant='gridfinity'), name)
           for family, height, name in [('L', 2, 'L6 Gridfinity box thick'),
                                       ('S', 2, 'S6 Gridfinity box thick'),
                                       ('S', 1, 'S6 1F Gridfinity box thick')]]
builds += [build('box', dict(family='S', depth_units=6, height_units=1,
                             box_floor=3, box_variant='gridfinity', wall_pattern=pattern),
                  f'S6 1F Gridfinity {pattern} rear box') for pattern in ('miura',)]
builds += [build('box', dict(family='S', depth_units=6, height_units=1,
                             box_floor=0, box_variant='gridfinity', wall_pattern='miura'),
                  'S6 1F Floorless Gridfinity miura rear box')]
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
                                       drawer_rows=int(query['drawer_rows']),
                                       box_floor=float(query['box_floor']), box_variant=query['box_variant'],
                                       facade_floor=float(query['facade_floor']) if query['facade_floor'] != 'default' else 'default',
                                       module_rear=float(query['module_rear']),
                                       wall_pattern=query['wall_pattern'], pattern_pitch=float(query['pattern_pitch']),
                                       pattern_depth=float(query['pattern_depth']), nozzle_size=float(query['nozzle_size']),
                                       wall_perimeters=int(query['wall_perimeters']) if query['wall_perimeters'] != 'full' else 'full')
                scene = assembly_definition(config)
                suffix = ' · 4 drawers' if config.drawer_rows == 2 else ''
                if config.wall_pattern != 'plain': suffix += ' · ' + {'waffle':'Waffle', 'miura':'Miura-ori'}[config.wall_pattern]
                if config.box_variant == 'gridfinity': suffix += ' · Gridfinity'
                if config.box_floor == 0: suffix += ' · Floorless'
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
    expect(page.locator('#height-options button')).to_have_text(['1F', '2F', '4F'])
    expect(page.locator('.size-limit')).to_have_text('S → L · 4F max')
    expect(page.locator('#minimum-floor-options button')).to_have_text(['0.8 mm', 'Default'])
    expect(page.locator('#perimeters-options button')).to_have_text(['1 perimeter', '2 perimeters', 'Full width'])
    expect(page.locator('#perimeters-options button[data-value="2"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#nozzle-options button')).to_have_text(['0.6 mm', '0.8 mm'])
    expect(page.locator('#nozzle-options button[data-value="0.6"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#minimum-floor-options button[data-value="0.8"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#minimum-floor-field')).to_be_visible()
    expect(page.locator('#perimeters-field')).to_be_visible()
    expect(page.locator('#box-bottom-options button[data-value="floorless"]')).to_be_hidden()
    expect(page.locator('#box-variant-options button')).to_have_count(2)
    expect(page.locator('#box-variant-options button[data-value="plain"]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('#wall-pattern-options button')).to_have_text(['Plain', 'Miura-ori'])
    expect(page.locator('#wall-pattern-field legend')).to_have_text('Wall pattern')
    for retired in ('box-rear-pattern-field', 'pattern-construction-options', 'pattern-faces-options', 'pattern-line-width'):
        expect(page.locator('#' + retired)).to_have_count(0)
    expect(page.locator('#wall-pattern-settings')).to_be_hidden()
    expect(page.locator('#drawer-layout-options button[data-value="2"]')).to_be_disabled()
    expect(page.locator('#drawer-layout-options button[data-value="4"]')).to_be_disabled()
    expect(page.locator('#part-options .common-components-heading')).to_have_text('Common components')
    assert page.locator('#part-options').evaluate('node => Array.from(node.children).findIndex(child => child.classList.contains("common-components-heading"))') == 7
    assert page.locator('#part-options .common-components-heading').evaluate('node => getComputedStyle(node).borderTopStyle') == 'solid'
    expect(page.locator('#repository-status')).to_have_count(0)
    expect(page.locator('.preview-status-row .revision-status')).to_have_count(1)
    expect(page.locator('#build-freshness')).to_contain_text('⚠ Uncommitted changes')
    assert assembly_queries[-1]['facade_floor'] == '0.8'
    assert assembly_queries[-1]['box_floor'] == '0.8'
    # Tall configurations retain all height controls and show their body size.
    for target, value in [('part', 'module'), ('depth', '3'), ('height', '4')]:
        page.locator(f'#{target}-options button[data-value="{value}"]').click()
    expect(page.locator('#height-hint')).to_have_text('191 mm body height')
    expect(page.locator('#configuration-dimensions')).to_have_text('164.8 × 146.1 × 191 mm body')
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    page.locator('.configurator').screenshot(path=str(output / '4f-controls-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.locator('.configurator').screenshot(path=str(output / '4f-controls-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#height-options button').evaluate_all('buttons => buttons.every(button => button.scrollWidth <= button.clientWidth)')
    page.set_viewport_size({'width':1440,'height':1150})
    for family in ('S', 'M', 'L'):
        page.locator(f'#family-options button[data-value="{family}"]').click()
        expect(page.locator('#configuration-name')).to_have_text(f'{family}3 · 4F')
        expect(page.locator('#height-options button[data-value="4"]')).to_have_attribute('aria-pressed','true')
        expect(page.locator('#drawer-layout-options button[data-value="4"]')).to_be_disabled()
    for target,value in [('family','L'),('depth','6'),('height','2'),('part','rails')]:
        page.locator(f'#{target}-options button[data-value="{value}"]').click()
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true')
    expect(page.locator('#preview-title')).to_have_text('L geared rails')
    expect(page.locator('#minimum-floor-field')).to_be_hidden()
    expect(page.locator('#perimeters-field')).to_be_hidden()
    assert 'different commit' in page.locator('#build-freshness').get_attribute('title')
    page.locator('#part-options button[data-value="module"]').click()
    expect(page.locator('#box-variant-field')).to_be_hidden()
    expect(page.locator('#minimum-floor-field')).to_be_hidden()
    expect(page.locator('#perimeters-field')).to_be_visible()
    expect(page.locator('#perimeters-hint')).to_contain_text('1.30 mm')
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    expect(page.locator('#model-canvas')).to_be_hidden()
    expect(page.locator('#artifact-panel')).to_be_hidden()
    page.locator('#part-options button[data-value="box"]').click()
    expect(page.locator('#minimum-floor-field')).to_be_visible()
    expect(page.locator('#perimeters-field')).to_be_visible()
    expect(page.locator('#preview-title')).to_have_text('L6 box thin')
    page.locator('#minimum-floor-options button[data-value="default"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6 box thick')
    page.locator('#box-variant-options button[data-value="gridfinity"]').click()
    expect(page.locator('#box-bottom-options button[data-value="floorless"]')).to_be_visible()
    expect(page.locator('#preview-title')).to_have_text('L6 Gridfinity box thick')
    expect(page.locator('#configuration-name')).to_have_text('L6 · 2F · Gridfinity')
    expect(page.locator('#box-variant-hint')).to_contain_text('6 × 6 Gridfinity grid inside each box')
    expect(page.locator('#box-variant-hint')).to_contain_text('42 mm pitch')
    expect(page.locator('#box-variant-hint')).to_contain_text('Adds 5 mm above the selected floor')
    expect(page.locator('#minimum-floor-options button[data-value="default"]')).to_have_attribute('aria-pressed','true')
    page.locator('#minimum-floor-options button[data-value="0.8"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    page.locator('#box-variant-options button[data-value="plain"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6 box thin')
    page.locator('#minimum-floor-options button[data-value="default"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6 box thick')
    page.locator('#depth-options button[data-value="7"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    for kind in ('key','spring','runner_stop','facade_cap','key_cap', 'latch'):
        page.locator(f'#part-options button[data-value="{kind}"]').click()
        expect(page.locator('#minimum-floor-field')).to_be_hidden()
        expect(page.locator('#perimeters-field')).to_be_hidden()
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
    page.locator('#part-options button[data-value="facade"]').click()
    expect(page.locator('#minimum-floor-field')).to_be_visible()
    expect(page.locator('#perimeters-field')).to_be_hidden()
    expect(page.locator('#minimum-floor-hint')).to_contain_text('facade shell')
    # Missing facade_floor on historical builds means the original facade,
    # even though the generic control initially selects the new 0.8 mm shell.
    page.locator('#minimum-floor-options button[data-value="0.8"]').click()
    expect(page.locator('#preview-title')).to_have_text('S2F shelled facade')
    page.locator('.configurator').screenshot(path=str(output / 'facade-controls-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.locator('.configurator').screenshot(path=str(output / 'facade-controls-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width':1440,'height':1150})
    page.locator('#depth-options button[data-value="7"]').click()
    expect(page.locator('#preview-title')).to_have_text('S2F shelled facade')
    page.locator('#minimum-floor-options button[data-value="default"]').click()
    expect(page.locator('#preview-title')).to_have_text('S2F facade')
    page.locator('#depth-options button[data-value="6"]').click()
    page.locator('#part-options button[data-value="module"]').click()
    page.locator('#perimeters-options button[data-value="1"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    page.locator('#perimeters-options button[data-value="2"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6² Module 2F')
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#minimum-floor-field')).to_be_visible()
    expect(page.locator('#perimeters-field')).to_be_visible()
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(51)
    expect(page.locator('#part-hint')).to_contain_text('Print 4 pairs')
    expect(page.locator('#preview-title')).to_have_text('L6² · 2F complete set')
    assert assembly_queries[-1]['drawer_columns'] == '2'
    assert assembly_queries[-1]['facade_floor'] == 'default'
    assert assembly_queries[-1]['box_floor'] == '3'
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
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(51)
    page.screenshot(path=str(output / 'multi-drawer-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(output / 'multi-drawer-mobile.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width':1440,'height':1150})
    page.locator('#drawer-layout-options button[data-value="4"]').click()
    expect(page.locator('#configuration-name')).to_have_text('L6² · 2F · 4 drawers')
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(67)
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
    page.locator('#wall-pattern-options button[data-value="miura"]').click()
    expect(page.locator('#wall-pattern-settings')).to_be_visible()
    expect(page.locator('#preview-title')).to_have_text('L6 Miura module')
    expect(page.locator('#wall-pattern-hint')).to_contain_text('all eligible module faces')
    # Every geometry control participates in module cache matching.
    for selector, changed, original in [('#pattern-pitch','15','14'), ('#pattern-depth','1.6','1.7')]:
        page.locator(selector).fill(changed)
        expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
        page.locator(selector).fill(original)
        expect(page.locator('#preview-title')).to_have_text('L6 Miura module')
    for perimeters in (1, 2):
        for nozzle, line in ((0.6, 0.65), (0.8, 0.85)):
            page.locator(f'#perimeters-options button[data-value="{perimeters}"]').click()
            page.locator(f'#nozzle-options button[data-value="{nozzle}"]').click()
            expect(page.locator('#perimeters-hint')).to_contain_text(f'{perimeters * line:.2f} mm')
            if (perimeters, nozzle) != (2, .6):
                expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    page.locator('#nozzle-options button[data-value="0.6"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6 Miura module')
    page.locator('#pattern-depth').fill('2')
    expect(page.locator('#build-button')).to_be_enabled()  # Fold height is fitted to the available wall.
    page.locator('#pattern-depth').fill('')
    expect(page.locator('#wall-pattern-error')).to_contain_text('Depth must be between')
    expect(page.locator('#build-button')).to_be_disabled()
    page.locator('#part-options button[data-value="box"]').click()
    expect(page.locator('#wall-pattern-field')).to_be_visible()
    expect(page.locator('#build-button')).to_be_disabled()
    page.locator('#part-options button[data-value="rails"]').click()
    expect(page.locator('#wall-pattern-field')).to_be_hidden()
    expect(page.locator('#build-button')).to_be_enabled()
    page.locator('#part-options button[data-value="module"]').click()
    page.locator('#wall-pattern-options button[data-value="plain"]').click()
    expect(page.locator('#wall-pattern-settings')).to_be_hidden()
    expect(page.locator('#preview-title')).to_have_text('L6² Module 2F')
    # Legacy plain walls remain inspectable and never satisfy a new thin-wall selection.
    page.locator('#perimeters-options button[data-value="1"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    page.locator('#perimeters-options button[data-value="full"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6 full width module')
    expect(page.locator('#wall-pattern-options button[data-value="miura"]')).to_be_disabled()
    expect(page.locator('#nozzle-options button[data-value="0.8"]')).to_be_disabled()
    expect(page.locator('#perimeters-hint')).to_contain_text('original solid walls')
    page.locator('#perimeters-options button[data-value="2"]').click()
    page.locator('#wall-pattern-options button[data-value="miura"]').click()
    page.locator('#pattern-pitch').fill('16')
    page.locator('#pattern-depth').fill('1.4')
    expect(page.locator('#preview-title')).to_have_text('L6 custom Miura module')
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(67)
    expect(page.locator('#configuration-name')).to_contain_text('Miura-ori')
    assert {key: assembly_queries[-1][key] for key in ('wall_pattern', 'pattern_pitch', 'pattern_depth', 'wall_perimeters', 'nozzle_size')} == {
        'wall_pattern':'miura', 'pattern_pitch':'16', 'pattern_depth':'1.4', 'wall_perimeters':'2', 'nozzle_size':'0.6'}
    for retired in ('box_rear_pattern', 'pattern_faces', 'pattern_construction', 'pattern_line_width'):
        assert retired not in assembly_queries[-1]
    page.screenshot(path=str(output / 'wall-pattern-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(output / 'wall-pattern-mobile.png'), full_page=True)
    page.locator('#wall-pattern-field').screenshot(path=str(output / 'wall-pattern-controls-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width':1440,'height':1150})
    page.locator('#wall-pattern-options button[data-value="plain"]').click()
    page.locator('#part-options button[data-value="module"]').click()
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
    page.locator('#height-options button[data-value="4"]').click()
    expect(page.locator('#drawer-layout-options button[data-value="4"]')).to_be_disabled()
    expect(page.locator('#drawer-layout-options button[data-value="2"]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('#configuration-name')).to_have_text('L6² · 4F')
    expect(page.locator('#drawer-layout-hint')).to_contain_text('Two S4F drawers')
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(83)
    expect(page.locator('#preview-title')).to_have_text('L6² · 4F complete set')
    expect(page.locator('#part-hint')).to_contain_text('Print 8 pairs')
    assert assembly_queries[-1]['height_units'] == '4' and assembly_queries[-1]['drawer_rows'] == '1'
    page.locator('#height-options button[data-value="2"]').click()
    page.locator('#drawer-layout-options button[data-value="4"]').click()
    page.locator('#family-options button[data-value="S"]').click()
    expect(page.locator('#drawer-layout-options button[data-value="1"]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('#drawer-layout-options button[data-value="4"]')).to_be_disabled()
    page.locator('#family-options button[data-value="L"]').click()
    page.locator('#drawer-layout-options button[data-value="4"]').click()
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(67)
    page.screenshot(path=str(output / 'four-drawer-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(output / 'four-drawer-mobile.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#box-variant-options button[data-value="gridfinity"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6² · 2F · 4 drawers · Gridfinity complete set')
    expect(page.locator('#box-variant-hint')).to_contain_text('3 × 6 Gridfinity grid inside each box')
    assert assembly_queries[-1]['box_variant'] == 'gridfinity'
    page.locator('#part-options button[data-value="box"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 1F Gridfinity box thick')
    page.locator('#drawer-layout-options button[data-value="2"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 Gridfinity box thick')
    page.locator('#part-options button[data-value="module"]').click()
    expect(page.locator('#box-variant-field')).to_be_hidden()
    expect(page.locator('#configuration-name')).not_to_contain_text('Gridfinity')
    expect(page.locator('#preview-title')).to_have_text('L6² Module 2F')
    page.locator('#part-options button[data-value="box"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 Gridfinity box thick')
    page.locator('#family-options button[data-value="M"]').click()
    expect(page.locator('#box-variant-hint')).to_contain_text('5 × 6 Gridfinity grid inside each box')
    page.locator('#family-options button[data-value="L"]').click()
    page.locator('#drawer-layout-options button[data-value="4"]').click()
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(67)
    expect(page.locator('#minimum-floor-options button[data-value="default"]')).to_have_attribute('aria-pressed','true')
    page.screenshot(path=str(output / 'gridfinity-mobile.png'), full_page=True)
    page.locator('#box-variant-field').screenshot(path=str(output / 'gridfinity-controls-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width':1440,'height':1150})
    page.screenshot(path=str(output / 'gridfinity-desktop.png'), full_page=True)
    # One wall pattern controls the matching box and module, independently of
    # base, floor and drawer layout. Nozzle and perimeter changes invalidate both.
    page.locator('#part-options button[data-value="box"]').click()
    page.locator('#wall-pattern-options button[data-value="miura"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 1F Gridfinity miura rear box')
    expect(page.locator('#wall-pattern-hint')).to_contain_text('box rear wall')
    expect(page.locator('#wall-pattern-hint')).to_contain_text('Box runner backing')
    page.locator('#nozzle-options button[data-value="0.8"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    expect(page.locator('#perimeters-hint')).to_contain_text('0.8 mm narrower')
    page.locator('#nozzle-options button[data-value="0.6"]').click()
    expect(page.locator('#perimeters-hint')).not_to_contain_text('narrower')
    page.locator('#perimeters-options button[data-value="1"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    page.locator('#perimeters-options button[data-value="2"]').click()
    page.locator('#box-variant-options button[data-value="plain"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    page.locator('#box-variant-options button[data-value="gridfinity"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 1F Gridfinity miura rear box')
    page.locator('#minimum-floor-options button[data-value="0.8"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    page.locator('#minimum-floor-options button[data-value="default"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 1F Gridfinity miura rear box')
    page.locator('#part-options button[data-value="module"]').click()
    expect(page.locator('#preview-title')).to_have_text('L6 Miura module')
    page.locator('#part-options button[data-value="box"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 1F Gridfinity miura rear box')
    page.locator('#box-bottom-options button[data-value="floorless"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 1F Floorless Gridfinity miura rear box')
    expect(page.locator('#minimum-floor-field')).to_be_hidden()
    expect(page.locator('#box-variant-hint')).to_contain_text('Open cell bottoms; bins rest on the grid')
    page.locator('#box-bottom-options button[data-value="closed"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 1F Gridfinity miura rear box')
    expect(page.locator('#minimum-floor-options button[data-value="default"]')).to_have_attribute('aria-pressed','true')
    page.locator('#box-bottom-options button[data-value="floorless"]').click()
    # A plain box restores the chosen closed floor when changing base.
    page.locator('#box-variant-options button[data-value="plain"]').click()
    expect(page.locator('#box-bottom-options button[data-value="floorless"]')).to_be_hidden()
    expect(page.locator('#minimum-floor-options button[data-value="default"]')).to_have_attribute('aria-pressed','true')
    page.locator('#box-variant-options button[data-value="gridfinity"]').click()
    page.locator('#box-bottom-options button[data-value="floorless"]').click()
    expect(page.locator('#preview-title')).to_have_text('S6 1F Floorless Gridfinity miura rear box')
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#configuration-name')).to_contain_text('Miura-ori · Gridfinity · Floorless')
    assert assembly_queries[-1]['wall_pattern'] == 'miura'
    assert assembly_queries[-1]['box_floor'] == '0'
    expect(page.locator('#minimum-floor-field')).to_be_visible()
    page.locator('#minimum-floor-options button[data-value="0.8"]').click()
    expect(page.locator('#minimum-floor-hint')).to_contain_text('facade shell')
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(67)
    assert assembly_queries[-1]['box_floor'] == '0'
    assert assembly_queries[-1]['facade_floor'] == '0.8'
    page.screenshot(path=str(output / 'box-rear-pattern-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(output / 'box-rear-pattern-mobile.png'), full_page=True)
    page.locator('#wall-pattern-field').screenshot(path=str(output / 'shared-wall-pattern-controls-mobile.png'))
    page.locator('#nozzle-field').screenshot(path=str(output / 'nozzle-controls-mobile.png'))
    page.locator('#minimum-floor-field').screenshot(path=str(output / 'minimum-floor-controls-mobile.png'))
    page.locator('#perimeters-field').screenshot(path=str(output / 'perimeters-controls-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#build-button').click()
    expect(page.locator('#build-button')).to_be_disabled()
    assert len(submissions) == 1 and submissions[0]['drawer_columns'] == 2 and submissions[0]['family'] == 'L'
    assert submissions[0]['drawer_rows'] == 2 and submissions[0]['height_units'] == 2
    assert {key:submissions[0][key] for key in ('wall_pattern','pattern_pitch','pattern_depth','wall_perimeters','nozzle_size')} == {
        'wall_pattern':'miura', 'pattern_pitch':14, 'pattern_depth':1.7, 'wall_perimeters':2, 'nozzle_size':0.6}
    for retired in ('box_rear_pattern', 'pattern_faces', 'pattern_construction', 'pattern_line_width'):
        assert retired not in submissions[0]
    assert submissions[0]['box_variant'] == 'gridfinity' and submissions[0]['box_floor'] == 0
    assert submissions[0]['facade_floor'] == 0.8
    page.reload()
    expect(page.locator('#job-description')).to_contain_text('L6² · 2F · 4 drawers')
    expect(page.locator('#job-description')).to_contain_text('Gridfinity')
    expect(page.locator('#job-description')).to_contain_text('Floorless')
    expect(page.locator('#job-description')).to_contain_text('Miura-ori')
    expect(page.locator('#job-status')).to_have_text('Queued')
    # Reload keeps the queued job visible and restores the default selection;
    # a different configuration can now join the durable queue.
    expect(page.locator('#build-button')).to_be_enabled()
    expect(page.locator('#build-button-text')).to_have_text('Add to queue')
    assert '/queue?job=' in page.locator('#job-queue-link').get_attribute('href')
    # A separate fixture submission verifies that 4F survives the API payload
    # and queued-job recovery, without sending any CAD work to a real server.
    submissions.clear()
    page.evaluate('localStorage.removeItem("vault-active-job")')
    page.reload()
    page.locator('#height-options button[data-value="4"]').click()
    page.locator('#build-button').click()
    expect(page.locator('#build-button')).to_be_disabled()
    assert len(submissions) == 1
    assert submissions[0]['height_units'] == 4 and submissions[0]['family'] == 'S'
    assert submissions[0]['drawer_rows'] == 1 and submissions[0]['drawer_columns'] == 1
    page.reload()
    expect(page.locator('#job-description')).to_contain_text('S4 · 4F')
    expect(page.locator('#job-status')).to_have_text('Queued')
    assert not errors, errors
    browser.close()
print('Configurator browser checks passed')
