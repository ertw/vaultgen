/* Dependency-free STL preview. The exported print coordinates are preserved. */
const VERTICAL_FOV = 0.64;
const FIT_MARGIN = 1.1;

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
      uniform mat4 projection; uniform mat4 view;
      varying vec3 surfaceNormal;
      void main(){ surfaceNormal=mat3(view)*normal; gl_Position=projection*view*vec4(position,1.0); }
    `));
    gl.attachShader(this.program, shader(gl.FRAGMENT_SHADER, `
      precision mediump float; varying vec3 surfaceNormal;
      void main(){ vec3 n=normalize(surfaceNormal); if(!gl_FrontFacing)n=-n;
        float key=max(dot(n,normalize(vec3(-0.5,0.8,1.0))),0.0);
        float fill=max(dot(n,normalize(vec3(0.7,-0.2,0.3))),0.0);
        vec3 color=vec3(0.60,0.71,0.81)*(0.52+0.43*key+0.18*fill);
        gl_FragColor=vec4(color,1.0);
      }
    `));
    gl.linkProgram(this.program);
    if (!gl.getProgramParameter(this.program, gl.LINK_STATUS)) throw new Error('The 3D preview could not initialize.');
    this.positionBuffer = gl.createBuffer(); this.normalBuffer = gl.createBuffer();
    this.count = 0;
    this.fitDistance = FIT_MARGIN / Math.sin(VERTICAL_FOV / 2);
    this.reset();
    let drag = null;
    canvas.addEventListener('pointerdown', event => {
      drag = [event.clientX, event.clientY]; canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', event => {
      if (!drag) return;
      this.yaw += (event.clientX - drag[0]) * 0.008;
      this.pitch = Math.max(-1.5, Math.min(1.5, this.pitch + (event.clientY - drag[1]) * 0.008));
      drag = [event.clientX, event.clientY]; this.render();
    });
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) canvas.addEventListener(type, () => { drag = null; });
    canvas.addEventListener('wheel', event => {
      event.preventDefault(); this.zoom = Math.max(1.25, Math.min(10, this.zoom * Math.exp(event.deltaY * 0.001))); this.render();
    }, { passive: false });
    canvas.addEventListener('keydown', event => {
      const actions = { ArrowLeft: () => { this.yaw -= 0.12; }, ArrowRight: () => { this.yaw += 0.12; },
        ArrowUp: () => { this.pitch = Math.max(-1.5, this.pitch - 0.12); }, ArrowDown: () => { this.pitch = Math.min(1.5, this.pitch + 0.12); },
        '+': () => { this.zoom = Math.max(1.25, this.zoom * 0.9); }, '-': () => { this.zoom = Math.min(10, this.zoom * 1.1); },
        Home: () => this.reset() };
      if (actions[event.key]) { event.preventDefault(); actions[event.key](); this.render(); }
    });
    this.observer = new ResizeObserver(() => this.render()); this.observer.observe(canvas);
  }

  reset() { this.yaw = -0.63; this.pitch = 0.54; this.zoom = this.fitDistance; this.render(); }

  load(arrayBuffer) {
    const data = new DataView(arrayBuffer);
    let positions, count;
    const binaryCount = data.byteLength >= 84 ? data.getUint32(80, true) : 0;
    if (binaryCount > 0 && 84 + binaryCount * 50 === data.byteLength) {
      count = binaryCount * 3;
      if (count > 15000000) throw new Error('This mesh is too large to preview. Download STL or STEP to inspect it locally.');
      positions = new Float32Array(count * 3);
      for (let face = 0; face < binaryCount; face++) {
        const base = 84 + face * 50 + 12;
        for (let vertex = 0; vertex < 9; vertex++) positions[face * 9 + vertex] = data.getFloat32(base + vertex * 4, true);
      }
    } else {
      const text = new TextDecoder().decode(arrayBuffer);
      const matches = [...text.matchAll(/vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)/g)];
      if (!matches.length || matches.length % 3 !== 0) throw new Error('The model could not be previewed. CAD downloads remain available.');
      count = matches.length; positions = new Float32Array(matches.flatMap(match => match.slice(1).map(Number)));
    }
    const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < positions.length; i++) {
      const value = positions[i]; if (!Number.isFinite(value)) throw new Error('The preview contains invalid coordinates.');
      const axis = i % 3; low[axis] = Math.min(low[axis], value); high[axis] = Math.max(high[axis], value);
    }
    const size = high.map((value, i) => value - low[i]);
    const scale = 2 / Math.max(...size);
    let radius = 0;
    for (let i = 0; i < positions.length; i += 3) {
      const x = (positions[i] - (low[0] + high[0]) / 2) * scale;
      const y = (positions[i + 1] - (low[1] + high[1]) / 2) * scale;
      const z = (positions[i + 2] - (low[2] + high[2]) / 2) * scale;
      // Print Z is screen-up; screen-forward is negative print Y.
      positions[i] = x; positions[i + 1] = z; positions[i + 2] = -y;
      radius = Math.max(radius, Math.hypot(x, y, z));
    }
    // Fitting a sphere keeps every orbit angle within the perspective frustum.
    // render() additionally compensates for a viewport narrower than it is tall.
    this.fitDistance = radius / Math.sin(VERTICAL_FOV / 2) * FIT_MARGIN;
    const normals = new Float32Array(positions.length);
    for (let i = 0; i < positions.length; i += 9) {
      const ax = positions[i + 3] - positions[i], ay = positions[i + 4] - positions[i + 1], az = positions[i + 5] - positions[i + 2];
      const bx = positions[i + 6] - positions[i], by = positions[i + 7] - positions[i + 1], bz = positions[i + 8] - positions[i + 2];
      const nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
      const length = Math.hypot(nx, ny, nz) || 1;
      for (let v = 0; v < 3; v++) normals.set([nx / length, ny / length, nz / length], i + v * 3);
    }
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.positionBuffer); gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.normalBuffer); gl.bufferData(gl.ARRAY_BUFFER, normals, gl.STATIC_DRAW);
    this.count = count; this.reset(); return size;
  }

  render() {
    if (!this.gl || !this.program) return;
    const gl = this.gl, canvas = this.canvas;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    gl.viewport(0, 0, width, height); gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); gl.enable(gl.DEPTH_TEST);
    if (!this.count) return;
    gl.useProgram(this.program);
    for (const [name, buffer] of [['position', this.positionBuffer], ['normal', this.normalBuffer]]) {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      const attribute = gl.getAttribLocation(this.program, name);
      gl.enableVertexAttribArray(attribute); gl.vertexAttribPointer(attribute, 3, gl.FLOAT, false, 0, 0);
    }
    const aspect = width / height, f = 1 / Math.tan(VERTICAL_FOV / 2), near = 0.1, far = 100;
    const projection = new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, 2 * far * near / (near - far), 0]);
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cx = Math.cos(this.pitch), sx = Math.sin(this.pitch);
    const view = new Float32Array([cy, sx * sy, -cx * sy, 0, 0, cx, sx, 0, sy, -sx * cy, cx * cy, 0, 0, 0, -this.zoom * Math.max(1, 1 / aspect), 1]);
    gl.uniformMatrix4fv(gl.getUniformLocation(this.program, 'projection'), false, projection);
    gl.uniformMatrix4fv(gl.getUniformLocation(this.program, 'view'), false, view);
    gl.drawArrays(gl.TRIANGLES, 0, this.count);
  }
}
