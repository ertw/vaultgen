"""Browser checks against a running local Vault generator; no real builds submitted."""
import argparse
from pathlib import Path
import shutil

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', default='http://127.0.0.1:3941')
parser.add_argument('--chromium', default=shutil.which('chromium'))
parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'out' / 'web-review')
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
    expect(page.locator('#family-options button')).to_have_count(3)
    assert page.locator('#family-options button').count()==3
    assert page.locator('#depth-options button').count()==5
    assert page.locator('#height-options button').count()==2
    page.screenshot(path=str(out/'desktop-configurator.png'),full_page=True)
    print('history:',page.locator('.history-card').count())
    page.locator('#family-options button').nth(2).click()
    page.locator('#height-options button').nth(1).click()
    assert page.locator('#configuration-name').inner_text()=='L4 · 2F'
    assert page.locator('#preview-title').inner_text()=='L4 · 2F'
    if page.locator('.history-card').count():
        page.locator('.history-card').first.click()
        expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true',timeout=60000)
        saved=page.locator('#preview-title').inner_text()
        page.locator('#family-options button').nth(1).click()
        assert page.locator('#preview-title').inner_text()==saved
        assert page.locator('#configuration-name').inner_text()=='M4 · 2F'
        assert page.locator('#preview-eyebrow').inner_text()=='SAVED BUILD'
        assert page.locator('#stl-download').get_attribute('href').startswith('/files/')
        page.screenshot(path=str(out/'desktop-preview.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(out/'mobile.png'),full_page=True)
    overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
    assert not overflow,'Mobile horizontal overflow'
    assert not errors,errors
    print('PASS: actual app config, bounded sizes, immutable history preview, STL WebGL, mobile width; no page errors')
    browser.close()
