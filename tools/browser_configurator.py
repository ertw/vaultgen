"""Selection/cache regression checks using deterministic browser fixtures, no CAD jobs."""
import argparse
import shutil
from pathlib import Path
import struct
from playwright.sync_api import sync_playwright, expect
from vault.generator import catalog

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
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.chromium, headless=True,
        args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def route(request):
        from urllib.parse import urlsplit
        path = urlsplit(request.request.url).path
        payload = {'/api/config':catalog(), '/api/jobs':{'jobs':[]},
                   '/api/builds':{'builds':builds,'repository':{'commit':'newcommit','dirty':True}}}.get(path)
        if payload is not None: return request.fulfill(json=payload)
        if path.startswith('/files/'): return request.fulfill(body=mesh,content_type='application/octet-stream')
        file = STATIC / ('index.html' if path == '/' else path.removeprefix('/static/'))
        mime = {'.js':'text/javascript','.css':'text/css','.html':'text/html'}.get(file.suffix,'text/plain')
        request.fulfill(body=file.read_bytes(),content_type=mime)
    page.route('**/*',route)
    page.goto('http://vault.test/')
    expect(page.locator('#box-floor-options button')).to_have_count(2)
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
    assert not errors, errors
    browser.close()
print('Configurator browser checks passed')
