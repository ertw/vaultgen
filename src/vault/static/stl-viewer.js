/* Dependency-free STL preview. Assembly placements come from the CAD definition. */
const VERTICAL_FOV = 0.64;
const FIT_MARGIN = 1.1;
const IDENTITY = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
const MAX_VERTICES = 15000000;

function readPositions(arrayBuffer) {
  const data = new DataView(arrayBuffer);
  let positions;
  const binaryCount = data.byteLength >= 84 ? data.getUint32(80, true) : 0;
  if (binaryCount > 0 && 84 + binaryCount * 50 === data.byteLength) {
    if (binaryCount * 3 > MAX_VERTICES) throw new Error('This mesh is too large to preview. Download STL or STEP to inspect it locally.');
    positions = new Float32Array(binaryCount * 9);
    for (let face = 0; face < binaryCount; face++) {
      const base = 84 + face * 50 + 12;
      for (let vertex = 0; vertex < 9; vertex++) positions[face * 9 + vertex] = data.getFloat32(base + vertex * 4, true);
    }
  } else {
    const text = new TextDecoder().decode(arrayBuffer);
    const matches = [...text.matchAll(/vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)/g)];
    if (!matches.length || matches.length % 3 !== 0) throw new Error('The model could not be previewed. CAD downloads remain available.');
    if (matches.length > MAX_VERTICES) throw new Error('This mesh is too large to preview. Download STL or STEP to inspect it locally.');
    positions = new Float32Array(matches.flatMap(match => match.slice(1).map(Number)));
  }
  if (!positions.every(Number.isFinite)) throw new Error('The preview contains invalid coordinates.');
  return positions;
}
function normalsFor(positions) {
  const normals = new Float32Array(positions.length);
  for (let i = 0; i < positions.length; i += 9) {
    const ax = positions[i + 3] - positions[i], ay = positions[i + 4] - positions[i + 1], az = positions[i + 5] - positions[i + 2];
    const bx = positions[i + 6] - positions[i], by = positions[i + 7] - positions[i + 1], bz = positions[i + 8] - positions[i + 2];
    const nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
    const length = Math.hypot(nx, ny, nz) || 1;
    for (let v = 0; v < 3; v++) normals.set([nx / length, ny / length, nz / length], i + v * 3);
  }
  return normals;
}
function rgb(hex) {
  return /^#[a-f\d]{6}$/i.test(hex || '') ? [1,3,5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255) : [.60,.71,.81];
}

export class STLViewer {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext('webgl', { antialias: true, alpha: true });
    if (!this.gl) throw new Error('3D preview requires WebGL. CAD downloads remain available.');
    const gl = this.gl;
    const shader = (type, source) => {
      const item = gl.createShader(type);
      gl.shaderSource(item, source); gl.compileShader(item);
      if (!gl.getShaderParameter(item, gl.COMPILE_STATUS)) throw new Error('The 3D preview could not initialize.');
      return item;
    };
    this.program = gl.createProgram();
    gl.attachShader(this.program, shader(gl.VERTEX_SHADER, `
      attribute vec3 position; attribute vec3 normal;
      uniform mat4 projection; uniform mat4 view; uniform vec3 offset;
      varying vec3 surfaceNormal;
      void main(){ surfaceNormal=mat3(view)*normal; gl_Position=projection*view*vec4(position+offset,1.0); }
    `));
    gl.attachShader(this.program, shader(gl.FRAGMENT_SHADER, `
      precision mediump float; varying vec3 surfaceNormal; uniform vec3 color; uniform bool picking;
      void main(){ if(picking){ gl_FragColor=vec4(color,1.0); return; }
        vec3 n=normalize(surfaceNormal); if(!gl_FrontFacing)n=-n;
        float key=max(dot(n,normalize(vec3(-0.5,0.8,1.0))),0.0);
        float fill=max(dot(n,normalize(vec3(0.7,-0.2,0.3))),0.0);
        gl_FragColor=vec4(color*(0.52+0.43*key+0.18*fill),1.0);
      }
    `));
    gl.linkProgram(this.program);
    if (!gl.getProgramParameter(this.program, gl.LINK_STATUS)) throw new Error('The 3D preview could not initialize.');
    this.attributes = Object.fromEntries(['position', 'normal'].map(name => [name, gl.getAttribLocation(this.program, name)]));
    this.uniforms = Object.fromEntries(['projection', 'view', 'offset', 'color', 'picking'].map(name => [name, gl.getUniformLocation(this.program, name)]));
    this.meshes = []; this.count = 0; this.explosion = 0; this.selected = null;
    this.fitDistance = FIT_MARGIN / Math.sin(VERTICAL_FOV / 2);
    this.reset();
    let drag = null;
    canvas.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      drag = { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, moved: false };
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', event => {
      if (!drag) return;
      drag.moved ||= Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 4;
      if (drag.moved) {
        this.yaw += (event.clientX - drag.x) * 0.008;
        this.pitch = Math.max(-1.5, Math.min(1.5, this.pitch + (event.clientY - drag.y) * 0.008));
        this.render();
      }
      drag.x = event.clientX; drag.y = event.clientY;
    });
    canvas.addEventListener('pointerup', event => {
      if (drag && !drag.moved && this.onSelect) this.onSelect(this.pick(event.clientX, event.clientY));
      drag = null;
    });
    for (const type of ['pointercancel', 'lostpointercapture']) canvas.addEventListener(type, () => { drag = null; });
    canvas.addEventListener('wheel', event => {
      event.preventDefault(); this.zoom = Math.max(.3, Math.min(30, this.zoom * Math.exp(event.deltaY * 0.001))); this.render();
    }, { passive: false });
    canvas.addEventListener('keydown', event => {
      const actions = { ArrowLeft: () => { this.yaw -= 0.12; }, ArrowRight: () => { this.yaw += 0.12; },
        ArrowUp: () => { this.pitch = Math.max(-1.5, this.pitch - 0.12); }, ArrowDown: () => { this.pitch = Math.min(1.5, this.pitch + 0.12); },
        '+': () => { this.zoom = Math.max(.3, this.zoom * 0.9); }, '-': () => { this.zoom = Math.min(30, this.zoom * 1.1); },
        Home: () => this.reset() };
      if (actions[event.key]) { event.preventDefault(); actions[event.key](); this.render(); }
    });
    this.observer = new ResizeObserver(() => this.render()); this.observer.observe(canvas);
  }

  reset() { this.yaw = this.defaultYaw ?? -0.63; this.pitch = 0.54; this.fitCurrent(); }

  load(arrayBuffer) {
    return this.loadScene([{ id: 'print', bytes: arrayBuffer, transform: IDENTITY, explode: [0,0,0] }], { assembly: false });
  }

  loadScene(instances, { assembly = true } = {}) {
    const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
    const assembledLow = [...low], assembledHigh = [...high];
    let totalVertices = 0;
    const prepared = instances.map(instance => {
      const positions = readPositions(instance.bytes), m = instance.transform, explode = instance.explode;
      if (!Array.isArray(m) || m.length !== 16 || !m.every(Number.isFinite) ||
          !Array.isArray(explode) || explode.length !== 3 || !explode.every(Number.isFinite)) {
        throw new Error('Assembly placement metadata is invalid; rebuild the affected parts.');
      }
      totalVertices += positions.length / 3;
      if (totalVertices > MAX_VERTICES) throw new Error('This assembly is too large to preview. Select individual parts to inspect them.');
      for (let i = 0; i < positions.length; i += 3) {
        const x = positions[i], y = positions[i + 1], z = positions[i + 2];
        for (let axis = 0; axis < 3; axis++) {
          const value = m[axis]*x + m[axis+4]*y + m[axis+8]*z + m[axis+12];
          if (!Number.isFinite(value)) throw new Error('Assembly placement contains invalid coordinates.');
          positions[i+axis] = value;
          assembledLow[axis] = Math.min(assembledLow[axis], value); assembledHigh[axis] = Math.max(assembledHigh[axis], value);
          low[axis] = Math.min(low[axis], value, value + explode[axis]); high[axis] = Math.max(high[axis], value, value + explode[axis]);
        }
      }
      return { ...instance, positions };
    });
    if (!prepared.length) { this.clear(); return [0,0,0]; }
    const scale = 2 / Math.max(...high.map((value, i) => value - low[i]));
    if (!Number.isFinite(scale)) throw new Error('The preview has no measurable geometry.');
    const center = low.map((value, i) => (value + high[i]) / 2);
    for (const mesh of prepared) {
      const { positions, explode } = mesh;
      mesh.low = [Infinity, Infinity, Infinity]; mesh.high = [-Infinity, -Infinity, -Infinity];
      for (let i = 0; i < positions.length; i += 3) {
        const x = (positions[i] - center[0]) * scale, y = (positions[i+1] - center[1]) * scale, z = (positions[i+2] - center[2]) * scale;
        // Assembly and print Z are screen-up; screen-forward is negative Y.
        positions[i] = x; positions[i+1] = z; positions[i+2] = -y;
        for (let axis = 0; axis < 3; axis++) {
          mesh.low[axis] = Math.min(mesh.low[axis], positions[i+axis]);
          mesh.high[axis] = Math.max(mesh.high[axis], positions[i+axis]);
        }
      }
      mesh.offset = [explode[0]*scale, explode[2]*scale, -explode[1]*scale];
    }
    // The coordinate scale stays fixed. Only explicit fit/reset actions move the camera.
    this.clear();
    const gl = this.gl;
    this.meshes = prepared.map(mesh => {
      const positionBuffer = gl.createBuffer(), normalBuffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer); gl.bufferData(gl.ARRAY_BUFFER, mesh.positions, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, normalBuffer); gl.bufferData(gl.ARRAY_BUFFER, normalsFor(mesh.positions), gl.STATIC_DRAW);
      return { id: mesh.id, colorKey: mesh.color_key || mesh.id, color: rgb(mesh.color), offset: mesh.offset, low: mesh.low, high: mesh.high, count: mesh.positions.length / 3, positionBuffer, normalBuffer, visible: true };
    });
    this.count = totalVertices; this.explosion = 0; this.selected = null;
    // Assembly front is +Y. Print previews retain their original camera angle.
    this.defaultYaw = assembly ? Math.PI - 0.63 : -0.63;
    this.reset(); return assembledHigh.map((value, i) => value - assembledLow[i]);
  }

  clear() {
    for (const mesh of this.meshes) {
      this.gl.deleteBuffer(mesh.positionBuffer); this.gl.deleteBuffer(mesh.normalBuffer);
    }
    this.meshes = []; this.count = 0; this.render();
  }
  setExplosion(value) { this.explosion = Math.max(0, Math.min(1, Number(value) || 0)); this.render(); }
  setVisible(id, visible) { for (const mesh of this.meshes) if (mesh.id === id) mesh.visible = visible; this.render(); }
  setColors(colors) {
    for (const mesh of this.meshes) if (Object.hasOwn(colors, mesh.colorKey)) mesh.color = rgb(colors[mesh.colorKey]);
    this.render();
  }
  select(id) { this.selected = id; this.render(); }

  fitCurrent() {
    const visible = this.meshes.filter(mesh => mesh.visible);
    if (visible.length) {
      const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
      for (const mesh of visible) for (let axis = 0; axis < 3; axis++) {
        const offset = mesh.offset[axis] * this.explosion;
        low[axis] = Math.min(low[axis], mesh.low[axis] + offset);
        high[axis] = Math.max(high[axis], mesh.high[axis] + offset);
      }
      this.target = low.map((value, axis) => (value + high[axis]) / 2);
      this.fitDistance = Math.hypot(...high.map((value, axis) => (value - low[axis]) / 2)) / Math.sin(VERTICAL_FOV / 2) * FIT_MARGIN;
    } else this.target ||= [0,0,0];
    this.zoom = this.fitDistance; this.render();
  }

  pick(clientX, clientY) {
    const gl = this.gl, width = this.canvas.width, height = this.canvas.height;
    const framebuffer = gl.createFramebuffer(), texture = gl.createTexture(), depth = gl.createRenderbuffer();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.bindRenderbuffer(gl.RENDERBUFFER, depth); gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16, width, height);
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
    gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, depth);
    let id = null;
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE) {
      this.render(true);
      const rect = this.canvas.getBoundingClientRect(), pixel = new Uint8Array(4);
      const x = Math.max(0, Math.min(width-1, Math.floor((clientX-rect.left)*width/rect.width)));
      const y = Math.max(0, Math.min(height-1, height-1-Math.floor((clientY-rect.top)*height/rect.height)));
      gl.readPixels(x, y, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      id = this.meshes[pixel[0] + pixel[1]*256 + pixel[2]*65536 - 1]?.id || null;
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.deleteFramebuffer(framebuffer); gl.deleteTexture(texture); gl.deleteRenderbuffer(depth); this.render();
    return id;
  }

  render(picking = false) {
    if (!this.gl || !this.program) return;
    const gl = this.gl, canvas = this.canvas;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio)), height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    gl.viewport(0, 0, width, height); gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); gl.enable(gl.DEPTH_TEST);
    if (!this.count) return;
    picking ? gl.disable(gl.DITHER) : gl.enable(gl.DITHER);
    gl.useProgram(this.program);
    const aspect = width / height, f = 1 / Math.tan(VERTICAL_FOV / 2), near = 0.01, far = 1000;
    const projection = new Float32Array([f/aspect,0,0,0, 0,f,0,0, 0,0,(far+near)/(near-far),-1, 0,0,2*far*near/(near-far),0]);
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cx = Math.cos(this.pitch), sx = Math.sin(this.pitch);
    const [tx,ty,tz] = this.target || [0,0,0];
    const view = new Float32Array([cy,sx*sy,-cx*sy,0, 0,cx,sx,0, sy,-sx*cy,cx*cy,0,
      -cy*tx-sy*tz, -sx*sy*tx-cx*ty+sx*cy*tz, cx*sy*tx-sx*ty-cx*cy*tz-this.zoom*Math.max(1,1/aspect),1]);
    gl.uniformMatrix4fv(this.uniforms.projection, false, projection); gl.uniformMatrix4fv(this.uniforms.view, false, view);
    gl.uniform1i(this.uniforms.picking, picking ? 1 : 0);
    for (const [index, mesh] of this.meshes.entries()) {
      if (!mesh.visible) continue;
      for (const [name, buffer] of [['position', mesh.positionBuffer], ['normal', mesh.normalBuffer]]) {
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        const attribute = this.attributes[name]; gl.enableVertexAttribArray(attribute); gl.vertexAttribPointer(attribute, 3, gl.FLOAT, false, 0, 0);
      }
      const encoded = index + 1;
      const color = picking ? [(encoded&255)/255, ((encoded>>8)&255)/255, ((encoded>>16)&255)/255]
        : mesh.color.map(value => this.selected === mesh.id ? value*.65+.35 : this.selected ? value*.5 : value);
      gl.uniform3fv(this.uniforms.color, color);
      gl.uniform3fv(this.uniforms.offset, mesh.offset.map(value => value * this.explosion));
      gl.drawArrays(gl.TRIANGLES, 0, mesh.count);
    }
  }
}
