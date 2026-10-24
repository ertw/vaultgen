"""Browser checks against a running local Vault generator; no real builds submitted."""
import argparse
from pathlib import Path
import shutil

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', default='http://127.0.0.1:3941')
parser.add_argument('--chromium', default=shutil.which('chromium'))
args = parser.parse_args()
if not args.chromium:
    parser.error('Chromium is required; enter the cad-tooling Nix environment or pass --chromium.')

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    fixture={'job':None,'status':'running','count':0,'hold':True,'pending':None}
    builds=page.request.get(args.base_url.rstrip('/')+'/api/builds').json()['builds']
    assert len(builds)>=2, 'Create at least two successful builds before running the failure checks.'
    def route_jobs(route):
        request=route.request
        if request.method=='POST':
            fixture['count']+=1
            fixture['job']={'id':'fixture'+str(fixture['count']),'status':'queued','configuration':request.post_data_json,'created_at':'2026-10-23T23:00:00Z','logs':'','error':None,'builds':[],'bundle_url':None}
            if fixture['hold']:
                fixture['pending']=route
            else:
                route.fulfill(json=fixture['job'],status=202)
        elif request.url.endswith('/api/jobs'):
            route.fulfill(json={'jobs':[fixture['job']] if fixture['job'] else []})
        else:
            job=fixture['job']
            job['status']=fixture['status']; job['logs']='Building native CAD\nChecking STEP and print mesh\n'
            if job['status'] in ('completed','failed'):
                job['builds']=builds[:2]
                job['error']='Synthetic export failure for recovery coverage' if job['status']=='failed' else None
                job['bundle_url']='/api/jobs/'+job['id']+'/bundle.zip' if job['status']=='completed' else None
            route.fulfill(json=job)
    page.route('**/api/jobs*',route_jobs)
    page.route('**/api/jobs/**',route_jobs)
    page.goto(args.base_url.rstrip('/')+'/')
    expect(page.locator('#build-button')).to_be_enabled()
    page.locator('.history-card').first.click()
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true',timeout=60000)
    expect(page.locator('#envelope')).to_be_hidden()
    page.locator('#build-button').click()
    if fixture['hold']:
        page.locator('#family-options button').nth(2).click()
        expect(page.locator('#build-button')).to_be_disabled()
        page.locator('#configuration-form').dispatch_event('submit')
        assert fixture['count']==1, 'Duplicate POST while submission pending'
        fixture['hold']=False
        fixture['pending'].fulfill(json=fixture['job'],status=202)
    expect(page.locator('#job-status')).to_have_text('Running')
    expect(page.locator('#build-button')).to_be_disabled()
    page.locator('.history-card').nth(1).click()
    saved=page.locator('#preview-title').inner_text()
    fixture['status']='completed'
    expect(page.locator('#job-status')).to_have_text('Completed',timeout=10000)
    expect(page.locator('#preview-title')).to_have_text(saved)
    expect(page.locator('#job-bundle-download')).to_be_visible()
    page.locator('#job-artifacts-button').click()
    expect(page.locator('#bundle-download')).to_be_visible()
    assert page.locator('#artifact-tabs button').count()==sum(len(b['parts']) for b in builds[:2])
    page.reload()
    expect(page.locator('#job-status')).to_have_text('Completed')
    expect(page.locator('#bundle-download')).to_be_visible()
    fixture['status']='running'
    page.locator('#build-button').click()
    if fixture['hold']:
        page.locator('#family-options button').nth(2).click()
        expect(page.locator('#build-button')).to_be_disabled()
        page.locator('#configuration-form').dispatch_event('submit')
        assert fixture['count']==1, 'Duplicate POST while submission pending'
        fixture['hold']=False
        fixture['pending'].fulfill(json=fixture['job'],status=202)
    expect(page.locator('#job-status')).to_have_text('Running')
    fixture['status']='failed'
    expect(page.locator('#job-status')).to_have_text('Failed',timeout=10000)
    expect(page.locator('#job-artifacts-button')).to_have_text('View completed parts ')
    expect(page.locator('#build-button')).to_be_enabled()
    expect(page.locator('#job-bundle-download')).to_be_hidden()
    page.locator('#job-artifacts-button').click()
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true',timeout=60000)
    page.route('**/files/**',lambda route:route.fulfill(status=503,body='temporary preview failure'))
    page.locator('#artifact-tabs button').nth(1).click()
    expect(page.locator('#viewer-message')).to_contain_text('could not be loaded')
    expect(page.locator('#model-canvas')).to_be_hidden()
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','false')
    expect(page.locator('#stl-download')).to_be_visible()
    assert not errors,errors
    print('PASS: isolated job routes; progress, history navigation, accessible result/ZIP, reload restore, partial failure/retry, preview failure clears stale canvas; zero page errors')
    browser.close()
