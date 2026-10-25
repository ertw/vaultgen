"""Browser checks against a running local Vault generator; no real builds submitted."""
import argparse
from pathlib import Path
import shutil

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', default='http://127.0.0.1:3941')
parser.add_argument('--chromium', default=shutil.which('chromium'))
parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'out' / 'web-review')
parser.add_argument('--require-runners', action='store_true', help='Require saved guides and slides, then preview and download every runner component.')
args = parser.parse_args()
if not args.chromium:
    parser.error('Chromium is required; enter the cad-tooling Nix environment or pass --chromium.')
out = args.output
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    page=browser.new_page(viewport={'width':1440,'height':1150},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    # Ignore unrelated live jobs; this check reads the real catalog and artifacts.
    page.route('**/api/jobs',lambda route:route.fulfill(json={'jobs':[]}))
    page.goto(args.base_url.rstrip('/')+'/')
    expect(page.get_by_role('link',name='Labels',exact=True)).to_have_attribute('href','/labels')
    expect(page.locator('#family-options button')).to_have_count(3)
    assert page.locator('#family-options button').count()==3
    assert page.locator('#depth-options button').count()==5
    assert page.locator('#height-options button').count()==2
    expect(page.locator('#part-options button')).to_have_count(7)
    for part, name in [('runner_guides', 'runner guides'), ('runner_slides', 'runner slides')]:
        page.locator(f'#part-options button[data-value="{part}"]').click()
        expect(page.locator('#build-button-text')).to_have_text(f'Generate {name}')
        expect(page.locator('#part-hint')).to_contain_text('follow depth')
    page.locator('#part-options button[data-value="set"]').click()
    expect(page.locator('#assembly-panel')).to_be_visible(timeout=60000)
    page.screenshot(path=str(out/'desktop-configurator.png'),full_page=True)
    print('history:',page.locator('.history-card').count())
    page.locator('#family-options button').nth(2).click()
    page.locator('#height-options button').nth(1).click()
    assert page.locator('#configuration-name').inner_text()=='L4 · 2F'
    expect(page.locator('#preview-title')).to_have_text('L4 · 2F complete set',timeout=60000)
    if page.locator('.history-card').count():
        page.locator('.history-card').first.click()
        expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true',timeout=60000)
        saved=page.locator('#preview-title').inner_text()
        assert page.locator('#configuration-name').inner_text()=='L4 · 2F'
        assert page.locator('#preview-eyebrow').inner_text()=='SAVED BUILD'
        assert page.locator('#stl-download').get_attribute('href').startswith('/files/')
        page.screenshot(path=str(out/'desktop-preview.png'),full_page=True)
        # An explicit configuration change returns from saved history to the
        # selected assembly; this behavior predates the label editor.
        page.locator('#family-options button').nth(1).click()
        expect(page.locator('#configuration-name')).to_have_text('M4 · 2F')
        expect(page.locator('#preview-title')).to_have_text('M4 · 2F complete set',timeout=60000)
        expect(page.locator('#preview-eyebrow')).to_have_text('COMPLETE SET')
        page.locator('.history-card').first.click()
        expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true',timeout=60000)
        expect(page.locator('#preview-title')).to_have_text(saved)
    if args.require_runners:
        builds=[build for build in page.request.get(args.base_url.rstrip('/')+'/api/builds').json()['builds'] if build['kind']!='label']
        for kind in ('runner_guides','runner_slides'):
            build=next((b for b in builds[:12] if b['kind']==kind),None)
            assert build, f'Generate {kind} before running --require-runners.'
            page.locator('.history-card').filter(has_text=build['name']).first.click()
            expect(page.locator('#artifact-tabs button')).to_have_count(len(build['parts']))
            for index,part in enumerate(build['parts']):
                page.locator('#artifact-tabs button').nth(index).click()
                expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true',timeout=60000)
                expect(page.locator('#viewport-label')).to_have_text(part['name'])
                for link in ('stl-download','step-download'):
                    response=page.request.get(args.base_url.rstrip('/')+page.locator(f'#{link}').get_attribute('href'))
                    assert response.ok, f'{kind} {part["name"]}: {link} failed'
                    assert len(response.body())>100
            page.screenshot(path=str(out/f'{kind}-preview.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(out/'mobile.png'),full_page=True)
    overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
    assert not overflow,'Mobile horizontal overflow'
    expect(page.get_by_role('link',name='Labels',exact=True)).to_be_visible()
    assert not errors,errors
    print('PASS: actual app config, bounded sizes, runner selectors, immutable history preview, STL WebGL, mobile width; no page errors')
    browser.close()
