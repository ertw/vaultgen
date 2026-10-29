"""Assembly-view regression checks with deterministic meshes; no CAD jobs submitted."""
import argparse
import copy
from pathlib import Path
import shutil
import struct
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright, expect
from vault.generator import catalog

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--chromium', default=shutil.which('chromium'))
parser.add_argument('--output', type=Path, default=Path('/tmp/vault-assembly-browser'))
args = parser.parse_args()
if not args.chromium:
    parser.error('Pass --chromium or add Chromium to PATH')
args.output.mkdir(parents=True, exist_ok=True)
STATIC = Path(__file__).resolve().parents[1] / 'src/vault/static'

vertices = [(0,0,0),(10,0,0),(10,10,0),(0,10,0),(0,0,10),(10,0,10),(10,10,10),(0,10,10)]
faces = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(2,3,7),(2,7,6),(1,2,6),(1,6,5),(3,0,4),(3,4,7)]
def box_mesh(dimensions=(10,10,10)):
    return bytes(80) + struct.pack('<I',len(faces)) + b''.join(
        struct.pack('<12fH',0,0,1,*[coordinate*dimensions[axis]/10
                    for index in face for axis,coordinate in enumerate(vertices[index])],0)
        for face in faces)

mesh = box_mesh()
def transform(x=0,y=0,z=0):
    return [1,0,0,0, 0,1,0,0, 0,0,1,0, x,y,z,1]

# The native module's latch side faces down in the finished assembly. Rotate
# only that component 180° about Y; the box keeps its open side upward.
module_transform = [-1,0,0,0, 0,1,0,0, 0,0,-1,0, 0,0,10,1]
freshness = dict(warning=True, reasons=['Cached build is from a different commit; rebuild for the current revision.'])
scene = dict(name='S4 · 1F complete set', complete=False,
             missing=[dict(kind='facade',label='Facade',reason='Rebuild this part to generate its finished assembly mesh.')],
             warnings=['These cached components were generated from different source revisions.'],
             omissions=['Screws'], validation=None, validation_scope='drawer_components',
             instances=[
                 dict(id='module',label='Module',kind='module',group='shell',mesh_url='/files/test/module.stl',transform=module_transform,explode=[0,0,0],color='#8ba9c1',build_id='module-build',freshness=freshness),
                 dict(id='box',label='Box',kind='box',group='drawer',mesh_url='/files/test/box.stl',transform=transform(12,12,0),explode=[0,25,0],color='#8ba9c1',build_id='box-build',freshness=freshness),
                 dict(id='rail_left',label='Left geared rail',kind='rails',group='drawer',mesh_url='/files/test/rail.stl',transform=transform(12,0,0),explode=[20,25,0],color='#e0b570',build_id='rails-build',freshness=freshness),
                 dict(id='rail_right',label='Right geared rail',kind='rails',group='drawer',mesh_url='/files/test/rail.stl',transform=transform(0,12,0),explode=[-20,25,15],color='#e0b570',build_id='rails-build',freshness=freshness),
             ])
# Small deterministic solids represent each accessory group without generating CAD.
# Repeated caps/stops retain independent placements but reuse their download.
accessory_meshes = {
    'key':box_mesh((4,8,4)), 'spring':box_mesh((4,2,2)), 'latch':box_mesh((4,2,1)),
    'runner_stop':box_mesh((2,2,3)), 'facade_cap':box_mesh((2,1,2)), 'key_cap':box_mesh((4,2,4)),
}
accessories = [
    ('key','Key with drive pinion','key',(8,24,4),(0,45,0)),
    ('spring_left','Left spring','spring',(4,20,6),(-10,35,15)),
    ('spring_right','Right spring','spring',(14,20,6),(10,35,15)),
    ('latch','Latch','latch',(9,22,0),(0,35,-15)),
    ('runner_stop_left_1','Left runner stop · tier 1','runner_stop',(0,0,12),(-20,0,0)),
    ('runner_stop_right_1','Right runner stop · tier 1','runner_stop',(20,0,12),(20,0,0)),
    ('facade_cap_left_1','Left facade cap · tier 1','facade_cap',(2,22,2),(-10,45,0)),
    ('facade_cap_right_1','Right facade cap · tier 1','facade_cap',(18,22,2),(10,45,0)),
    ('key_cap','Key cap','key_cap',(8,32,4),(0,55,0)),
]
for identifier,label,kind,placement,explode in accessories:
    placement_transform = transform(*placement)
    if identifier == 'spring_right':
        # Shared mesh downloads must retain each instance's own installed
        # rotation. This synthetic opposite-facing pair exercises a half turn.
        placement_transform[5] = placement_transform[10] = -1
    scene['instances'].append(dict(id=identifier,label=label,kind=kind,component='single',
        group='shell' if kind in {'runner_stop','latch'} else 'drawer',mesh_url=f'/files/test/{kind}.stl',
        transform=placement_transform,explode=explode,color='#8ba9c1',build_id=f'{kind}-build',freshness=freshness))
scene['instances'].append(dict(id='facade', label='Facade', kind='facade', group='drawer',
    mesh_url='/files/test/facade.stl', transform=transform(12,22,0), explode=[0,35,0],
    build_id='facade-build', freshness=freshness, material_meshes=[
        dict(name=name, role=role, mesh_url=f'/files/test/facade_{name}.stl')
        for name,role in [('body','primary'),('locked','secondary'),('unlocked','secondary')]]))
instance_count = len(scene['instances'])
builds = [dict(id='rails-build',kind='rails',name='S geared rails',configuration=dict(family='S'),
               created_at='2026-10-24T00:00:00Z',freshness=freshness,
               parts=[dict(name='rails',stl_url='/files/test/rail.stl',step_url='/files/test/rail.step',print_bbox_mm=[10,10,10])])]
default_palette = dict(primary='#f2f0eb',secondary='#303030',highlight='#e7a6bd')
palette = default_palette.copy()
kind_roles = dict(facade='primary',module='primary',box='secondary',rails='highlight',key='secondary',
                  spring='highlight',latch='highlight',runner_stop='highlight',facade_cap='primary',key_cap='primary')
instance_roles = {instance['id']:kind_roles[instance['kind']] for instance in scene['instances']}

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.chromium, headless=True,
        args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport=dict(width=1440,height=1150))
    errors, requests = [], []
    fixture = dict(hold=False,pending=None,fail_mesh=False,corrupt_mesh=False)
    page.on('pageerror',lambda error: errors.append(str(error)))
    def route(request):
        parsed = urlsplit(request.request.url)
        path = parsed.path
        requests.append(path)
        if path == '/api/assembly':
            if fixture['hold']:
                fixture['pending'] = request
                return
            result = copy.deepcopy(scene)
            family = parse_qs(parsed.query)['family'][0]
            if family == 'L':
                result['instances'] = []
                result['complete'] = False
                result['validation'] = None
                result['missing'] = [dict(kind='facade',label='Facade',reason='Rebuild this part to generate its finished assembly mesh.')]
            return request.fulfill(json=result)
        payload = {'/api/config':catalog(),'/api/jobs':{'jobs':[]},
                   '/api/builds':{'builds':builds,'repository':{'commit':'newcommit','dirty':True}}}.get(path)
        if payload is not None:
            return request.fulfill(json=payload)
        if path.startswith('/files/'):
            if fixture['fail_mesh'] and path.endswith('module.stl'):
                return request.fulfill(status=503,body='Fixture mesh unavailable')
            if fixture['corrupt_mesh'] and path.endswith('module.stl'):
                return request.fulfill(body=b'Invalid STL fixture',content_type='application/octet-stream')
            return request.fulfill(body=accessory_meshes.get(Path(path).stem,mesh),content_type='application/octet-stream')
        file = STATIC / ('index.html' if path == '/' else path.removeprefix('/static/'))
        body = file.read_bytes()
        if path.endswith('stl-viewer.js'):
            # Inspect camera and uploaded vertex positions without production test hooks.
            body += b'''\nconst originalLoadScene=STLViewer.prototype.loadScene;
STLViewer.prototype.loadScene=function(...args){
  window.testViewer=this;window.sceneLoads=(window.sceneLoads||0)+1;
  const uploads=[],originalBufferData=this.gl.bufferData;
  this.gl.bufferData=function(target,data,...rest){uploads.push(Array.from(data));return originalBufferData.call(this,target,data,...rest);};
  try {
    const result=originalLoadScene.apply(this,args);
    window.sceneVertexBuffers=Object.fromEntries(args[0].map((instance,index)=>[instance.id,uploads[index*2]]));
    return result;
  } finally {this.gl.bufferData=originalBufferData;}
};\n'''
        mime = {'.js':'text/javascript','.css':'text/css','.html':'text/html'}.get(file.suffix,'text/plain')
        request.fulfill(body=body,content_type=mime)
    page.route('**/*',route)
    def assert_palette():
        for role, color in palette.items():
            picker = page.locator(f'#assembly-{role}-color')
            expect(picker).to_have_attribute('type','color')
            expect(picker).to_have_value(color)
        for instance in page.evaluate('testViewer.meshes.map(({id,color,colorKey})=>({id,color,colorKey}))'):
            role = 'secondary' if instance['colorKey'] in ('facade:locked','facade:unlocked') else instance_roles[instance['id']]
            color = palette[role]
            channels = [int(color[index:index+2],16) for index in (1,3,5)]
            assert all(abs(value-channel/255) < 1e-6 for value,channel in zip(instance['color'],channels)), instance
            swatch = page.locator(f'.assembly-instance[data-instance="{instance["id"]}"] .instance-color')
            swatch_channels = [int(palette[instance_roles[instance['id']]][index:index+2],16) for index in (1,3,5)]
            expect(swatch).to_have_css('background-color',f'rgb({swatch_channels[0]}, {swatch_channels[1]}, {swatch_channels[2]})')

    def assert_palette_bounds():
        controls = page.locator('#assembly-colors')
        expect(controls).to_be_visible()
        bounds = controls.bounding_box()
        assert bounds and bounds['width'] > 0 and bounds['height'] > 0
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= page.viewport_size['width'], bounds
        circles = []
        for role in palette:
            picker = page.locator(f'#assembly-{role}-color')
            expect(picker).to_be_visible()
            circle = picker.bounding_box()
            assert circle and circle['width'] > 0 and circle['height'] > 0
            assert bounds['x'] <= circle['x'] and circle['x'] + circle['width'] <= bounds['x'] + bounds['width'] + 1, circle
            assert bounds['y'] <= circle['y'] and circle['y'] + circle['height'] <= bounds['y'] + bounds['height'] + 1, circle
            if circles:
                assert circles[-1]['x'] + circles[-1]['width'] <= circle['x'], circles
            circles.append(circle)

    page.goto('http://vault.test/')
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true',timeout=15000)
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(instance_count)
    expect(page.locator('#assembly-controls')).to_be_visible()
    expect(page.locator('#fit-view + #assembly-colors')).to_have_attribute('role','group')
    assert_palette()
    assert_palette_bounds()
    expect(page.locator('#assembly-missing')).to_contain_text('Rebuild this part')
    expect(page.locator('#assembly-warnings')).to_contain_text('different source revisions')
    expect(page.locator('#assembly-omissions')).to_contain_text('Screws')
    expect(page.locator('#assembly-summary')).to_contain_text('Fit not verified')
    expect(page.locator('#print-note')).to_contain_text('Accessory placement and retention are not fit checked')
    expect(page.locator('#build-freshness')).to_contain_text('⚠ Uncommitted changes')
    assert requests.count('/files/test/rail.stl') == 1, 'Repeated instances should share a mesh request'
    for kind in accessory_meshes:
        assert requests.count(f'/files/test/{kind}.stl') == 1, f'{kind} instances should share a mesh request'
    assert page.evaluate('testViewer.meshes.length') == instance_count + 2
    facade_row = page.locator('.assembly-instance[data-instance="facade"]')
    facade_row.locator('input').uncheck()
    assert page.evaluate('testViewer.meshes.filter(m=>m.id==="facade").every(m=>!m.visible)')
    facade_row.locator('input').check()
    assert page.evaluate('testViewer.meshes.filter(m=>m.id==="facade").every(m=>m.visible)')
    expect(page.locator('#metric-width')).to_have_text('32 mm')
    # First/third triangles begin on native Z=0/Z=10. Renderer Y is assembly
    # up: native module Z must descend while native box Z must ascend.
    orientation = page.evaluate('Object.fromEntries(["module","box"].map(id=>[id,sceneVertexBuffers[id][19]-sceneVertexBuffers[id][1]]))')
    assert orientation['module'] < 0 < orientation['box'], orientation
    spring_orientation = page.evaluate('Object.fromEntries(["spring_left","spring_right"].map(id=>[id,sceneVertexBuffers[id][19]-sceneVertexBuffers[id][1]]))')
    assert spring_orientation['spring_right'] < 0 < spring_orientation['spring_left'], spring_orientation
    camera = page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]')
    loads = page.evaluate('sceneLoads')
    meshes_requested = len([path for path in requests if path.startswith('/files/')])
    assembled_image = page.locator('#model-canvas').screenshot()
    page.locator('#explosion').fill('100')
    expect(page.locator('#explosion-value')).to_have_text('100%')
    assert page.evaluate('testViewer.explosion') == 1
    for identifier,*_ in accessories:
        offset = page.evaluate('(id)=>testViewer.meshes.find(mesh=>mesh.id===id).offset',identifier)
        assert any(abs(value) > 0 for value in offset), f'{identifier} needs an exploded placement'
    assert page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]') == camera
    assert page.locator('#model-canvas').screenshot() != assembled_image, 'Exploding must visibly change mesh placements'
    page.locator('#assemble-view').click()
    expect(page.locator('#explosion-value')).to_have_text('0%')
    assert page.evaluate('testViewer.explosion') == 0
    assert page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]') == camera
    assert page.locator('#model-canvas').screenshot() == assembled_image, 'Assembled must restore every installed accessory pose'
    assert page.evaluate('sceneLoads') == loads
    assert len([path for path in requests if path.startswith('/files/')]) == meshes_requested
    page.locator('#explode-view').click()
    assert page.evaluate('testViewer.fitDistance') != camera[-1], 'Endpoint action should fit its current pose'
    camera = page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]')
    page.locator('#explosion').fill('46')
    assert page.evaluate('testViewer.explosion') == .46
    assert page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]') == camera
    expect(page.locator('#preview-badge')).to_have_text('Exploded · 46%')
    assert len([path for path in requests if path.startswith('/files/')]) == meshes_requested
    # Every accessory is selectable and independently visible, including shared meshes.
    for identifier,label,kind,*_ in accessories:
        accessory_row = page.locator(f'.assembly-instance[data-instance="{identifier}"]')
        accessory_row.locator('button').click()
        expect(accessory_row).to_have_attribute('data-selected','true')
        assert page.evaluate('testViewer.selected') == identifier
        expect(page.locator('#assembly-selection')).to_contain_text(f'{kind}-build')
        accessory_row.locator('input').uncheck()
        assert page.evaluate('(id)=>testViewer.meshes.find(mesh=>mesh.id===id).visible',identifier) is False
        assert page.evaluate('(id)=>testViewer.meshes.filter(mesh=>mesh.id!==id).every(mesh=>mesh.visible)',identifier)
        assert page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]') == camera
        accessory_row.locator('input').check()
    row = page.locator('.assembly-instance[data-instance="rail_left"]')
    row.locator('button').click()
    expect(row).to_have_attribute('data-selected','true')
    assert page.evaluate('testViewer.selected') == 'rail_left'
    expect(page.locator('#assembly-selection')).to_contain_text('rails-build')
    row.locator('input').uncheck()
    assert page.evaluate('testViewer.meshes.find(mesh=>mesh.id==="rail_left").visible') is False
    assert page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]') == camera
    page.locator('#fit-view').click()
    assert page.evaluate('testViewer.fitDistance') != camera[-1], 'Fit view should frame the currently visible parts'
    # Refresh metadata without reloading geometry, resetting controls, or moving the camera.
    page.locator('#model-canvas').focus()
    page.keyboard.press('ArrowRight')
    camera = page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]')
    # Color edits update every matching material without rebuilding the scene or resetting inspection state.
    before_colors = page.locator('#model-canvas').screenshot()
    for role,color in dict(primary='#b2c48a',secondary='#645473',highlight='#ef9777').items():
        palette[role] = color
        page.locator(f'#assembly-{role}-color').fill(color)
        assert_palette()
        assert page.evaluate('sceneLoads') == loads
        assert len([path for path in requests if path.startswith('/files/')]) == meshes_requested
        assert page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]') == camera
        assert page.evaluate('testViewer.explosion') == .46
        assert page.evaluate('testViewer.selected') == 'rail_left'
        assert page.evaluate('testViewer.meshes.find(mesh=>mesh.id==="rail_left").visible') is False
    assert page.locator('#model-canvas').screenshot() != before_colors, 'Palette edits must visibly recolor the existing scene'
    scene['validation'] = dict(passed=True)
    scene['complete'] = True
    scene['missing'] = []
    page.locator('#refresh-history').click()
    expect(page.locator('#assembly-summary')).to_contain_text('✓ Drawer fit checked · accessory fit not checked')
    assert page.evaluate('sceneLoads') == loads
    assert page.evaluate('[testViewer.yaw,testViewer.pitch,testViewer.zoom,testViewer.fitDistance]') == camera
    expect(row.locator('input')).not_to_be_checked()
    expect(page.locator('#explosion-value')).to_have_text('46%')
    assert page.evaluate('testViewer.selected') == 'rail_left'
    assert_palette()
    page.locator('#show-all-instances').click()
    expect(row.locator('input')).to_be_checked()
    page.screenshot(path=str(args.output/'desktop.png'),full_page=True)
    # Picking should return an actual mesh ID; background clears selection.
    picked = page.evaluate('''() => {
      const viewer=testViewer,rect=viewer.canvas.getBoundingClientRect();
      for(let y=.1;y<.9;y+=.08)for(let x=.1;x<.9;x+=.08){
        const id=viewer.pick(rect.left+rect.width*x,rect.top+rect.height*y);
        if(id)return {id,x:rect.left+rect.width*x,y:rect.top+rect.height*y};
      } return null;
    }''')
    assert picked, 'Mesh picking must find visible geometry'
    page.mouse.click(picked['x'],picked['y'])
    assert page.evaluate('testViewer.selected') == picked['id']
    # Missing and legacy assembly meshes never fall back to print coordinates.
    page.locator('#family-options button[data-value="L"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('not been generated yet')
    expect(page.locator('#model-canvas')).to_be_hidden()
    # A late assembly response cannot replace a manually selected print preview.
    fixture['hold'] = True
    page.locator('#family-options button[data-value="M"]').click()
    expect(page.locator('#viewer-message')).to_have_text('Loading assembled parts…')
    page.locator('.history-card').first.click()
    expect(page.locator('#preview-title')).to_have_text('S geared rails')
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true')
    assert fixture['pending'], 'Expected deferred assembly response'
    fixture['pending'].fulfill(json=scene)
    fixture['hold'] = False
    page.wait_for_timeout(100)
    expect(page.locator('#preview-title')).to_have_text('S geared rails')
    expect(page.locator('#assembly-controls')).to_be_hidden()
    expect(page.locator('#assembly-colors')).to_be_hidden()
    assert page.evaluate('testViewer.meshes.map(mesh=>mesh.color)') == [[.60,.71,.81]], 'Print previews retain their existing material'
    expect(page.locator('#stl-download')).to_have_attribute('href','/files/test/rail.stl')
    # One failed download must leave other components inspectable and flag the gap.
    fixture['fail_mesh'] = True
    page.locator('#family-options button[data-value="S"]').click()
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(instance_count - 1)
    expect(page.locator('#assembly-missing')).to_contain_text('could not be loaded')
    expect(page.locator('#assembly-summary')).to_contain_text('Fit not verified for this view')
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true')
    assert_palette()
    # Malformed geometry must not reveal an old scene beneath a new selection.
    fixture['fail_mesh'] = False
    fixture['corrupt_mesh'] = True
    page.locator('#family-options button[data-value="L"]').click()
    expect(page.locator('#model-canvas')).to_be_hidden()
    page.locator('#family-options button[data-value="S"]').click()
    expect(page.locator('#viewer-message')).to_contain_text('could not be previewed')
    expect(page.locator('#model-canvas')).to_be_hidden()
    fixture['corrupt_mesh'] = False
    page.locator('#refresh-history').click()
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true')
    expect(page.locator('#assembly-instances .assembly-instance')).to_have_count(instance_count)
    assert_palette()
    page.set_viewport_size(dict(width=390,height=844))
    assert_palette_bounds()
    for identifier,*_ in accessories:
        accessory_row = page.locator(f'.assembly-instance[data-instance="{identifier}"]')
        expect(accessory_row).to_be_visible()
        bounds = accessory_row.bounding_box()
        assert bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= page.viewport_size['width'], bounds
    page.screenshot(path=str(args.output/'mobile.png'),full_page=True)
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), 'Mobile horizontal overflow'
    # Palette choices last for this page only.
    page.reload()
    expect(page.locator('#model-canvas')).to_have_attribute('data-model-ready','true')
    palette = default_palette.copy()
    assert_palette()
    assert_palette_bounds()
    # Springs follow drawer count; latches follow the module's connector banks.
    page.locator('#part-options button[data-value="spring"]').click()
    expect(page.locator('#part-hint')).to_contain_text('Print two per drawer')
    page.locator('#part-options button[data-value="latch"]').click()
    expect(page.locator('#part-hint')).to_contain_text('Print one, one per module connector bank')
    page.locator('#family-options button[data-value="L"]').click()
    expect(page.locator('#part-hint')).to_contain_text('Print two, one per module connector bank')
    page.locator('#height-options button[data-value="2"]').click()
    for layout,springs in ((2,4),(4,8)):
        page.locator(f'#drawer-layout-options button[data-value="{layout}"]').click()
        expect(page.locator('#part-hint')).to_contain_text('Print two, one per module connector bank')
        page.locator('#part-options button[data-value="spring"]').click()
        expect(page.locator('#part-hint')).to_contain_text(f'Print {springs}, two per drawer')
        page.locator('#part-options button[data-value="latch"]').click()
    assert not errors, errors
    browser.close()
print('Assembly browser checks passed: six accessory groups, rotated accessory transforms, shared meshes, explode and assembled restoration, visibility, picking, provenance, scoped fit status, palette defaults and edits, print color isolation, refresh stability, missing parts, response races, partial failures, mobile layout')
