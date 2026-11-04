/**
 * Every flame in the room in one draw call: an instanced, camera-facing quad per wick, drawn as a flame by its shader
 * (a teardrop with a blue root, a white-gold core and an orange skirt, its tip fluttering, and a soft halo around it),
 * standing on the wick whatever the camera's angle (seen from above it shortens, as a real flame does). The flutter
 * follows env/flicker.ts's flicker. Additive, so it never darkens what is behind it.
 */
import * as THREE from "three";
import { SWAY_GLSL } from "./roomShader";

const VERT = /* glsl */ `
attribute vec2 aFlame; // phase, height (as a share of the halo's radius)
attribute vec4 aSway; // rides a swinging lantern (roomShader.ts SWAY_GLSL)
uniform float uTime;
${SWAY_GLSL}
varying vec2 vUv;
varying vec3 vTint;
varying float vPhase;
varying float vFore;
varying float vHeight;
void main() {
  vec3 base = (modelMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
  vec3 swayN = vec3(0.0, 1.0, 0.0);
  base = swayPos(base, aSway, swayN, uTime);
  float size = length((modelMatrix * instanceMatrix * vec4(1.0, 0.0, 0.0, 0.0)).xyz);
  vec3 toCam = normalize(cameraPosition - base);
  vec3 up = vec3(0.0, 1.0, 0.0);
  // the flame's axis as the screen shows it, and how much of its height survives being seen from above
  vec3 axis = up - toCam * dot(up, toCam);
  float fore = length(axis);
  axis = fore > 1e-3 ? axis / fore : vec3(0.0, 0.0, -1.0);
  vec3 right = normalize(cross(axis, toCam));
  float h = aFlame.y;
  // the halo is centred on the flame's body, a little above the wick
  vec3 centre = base + up * size * h * 0.42;
  vec3 p = centre + (right * position.x + axis * position.y) * size;
  vUv = position.xy;
  vTint = instanceColor;
  vPhase = aFlame.x;
  vFore = max(fore, 0.35);
  vHeight = h;
  gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
}`;

const FRAG = /* glsl */ `
uniform float uTime;
uniform float uMotion;
varying vec2 vUv;
varying vec3 vTint;
varying float vPhase;
varying float vFore;
varying float vHeight;
float hash1(float n) { return fract(sin(n * 127.1 + 311.7) * 43758.5453123); }
float noise1(float x) { float i = floor(x); float f = fract(x); float u = f * f * (3.0 - 2.0 * f); return mix(hash1(i), hash1(i + 1.0), u); }
void main() {
  float t = uTime * uMotion;
  float n = noise1(t * 6.3 + vPhase * 17.0) * 0.55 + noise1(t * 13.7 + vPhase * 5.0) * 0.25 + noise1(t * 1.3 + vPhase) * 0.2;
  float f = 1.0 + (n * 2.0 - 1.0) * 0.22;
  // flame space: y from the wick (0) to the tip (1), x across, foreshortened when seen from above
  float h = vHeight * vFore * f;
  float y = (vUv.y + vHeight * 0.42 * vFore) / max(h, 1e-3);
  float sway = (noise1(t * 2.7 + vPhase * 3.0) - 0.5) * 0.35 * y * y;
  float w = 0.16 * vHeight / 0.62;
  float x = (vUv.x - sway * w * 2.0) / w;
  // a teardrop: round at the root, drawn out to a point at the tip
  float yy = clamp(y, 0.0, 1.2);
  float half_ = (y < 0.18) ? sqrt(max(0.0, 1.0 - pow((0.18 - y) / 0.2, 2.0))) : pow(max(0.0, 1.0 - (y - 0.18) / 0.82), 0.75);
  float d = abs(x) / max(half_, 1e-3);
  float body = (1.0 - smoothstep(0.55, 1.0, d)) * step(-0.02, y) * (1.0 - smoothstep(0.92, 1.02, yy));
  float core = (1.0 - smoothstep(0.0, 0.55, d)) * (1.0 - smoothstep(0.15, 0.62, y)) * step(0.02, y);
  float root = (1.0 - smoothstep(0.0, 0.18, y)) * body;
  vec3 skirt = vTint * vec3(1.0, 0.55, 0.22);
  vec3 col = mix(skirt, vTint * vec3(1.0, 0.86, 0.55), smoothstep(0.95, 0.35, d));
  col = mix(col, vec3(1.0, 0.97, 0.88), core);
  col = mix(col, vec3(0.32, 0.45, 1.0), root * 0.7);
  float a = body * (0.78 + core * 0.22);
  // the halo: a soft warm glow round the flame
  float r = length(vec2(vUv.x, (vUv.y - 0.1) * 0.85));
  float halo = exp(-r * r * 9.0) * 0.32 + exp(-r * r * 42.0) * 0.28;
  vec3 outc = col * a * 1.6 + vTint * vec3(1.0, 0.62, 0.3) * halo * f;
  gl_FragColor = vec4(outc, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

export class Flames {
  readonly mesh: THREE.InstancedMesh;
  private phases: Float32Array;
  private sways: Float32Array;
  private n = 0;
  private readonly cap: number;

  constructor(cap: number, time: { value: number }) {
    this.cap = cap;
    const geo = new THREE.PlaneGeometry(2, 2);
    this.phases = new Float32Array(cap * 2);
    geo.setAttribute("aFlame", new THREE.InstancedBufferAttribute(this.phases, 2));
    this.sways = new Float32Array(cap * 4);
    for (let i = 0; i < cap; i++) this.sways[i * 4 + 3] = -1;
    geo.setAttribute("aSway", new THREE.InstancedBufferAttribute(this.sways, 4));
    const mat = new THREE.ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG,
      uniforms: { uTime: time, uMotion: { value: 1 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false,
    });
    this.mesh = new THREE.InstancedMesh(geo, mat, cap);
    this.mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(cap * 3), 3);
    this.mesh.count = 0;
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 5;
  }

  /**
   * A flame standing on a wick at `base`: `size` is its halo's radius (world units), `height` the flame's length as a
   * share of that radius, `tint` its colour (candle gold by default).
   */
  add(base: THREE.Vector3, size: number, phase: number, tint: THREE.ColorRepresentation = "#ffb45a", height = 0.62, sway?: readonly [number, number, number, number]): void {
    if (this.n >= this.cap) return;
    const m = new THREE.Matrix4().compose(base, new THREE.Quaternion(), new THREE.Vector3(size, size, size));
    this.mesh.setMatrixAt(this.n, m);
    this.mesh.setColorAt(this.n, new THREE.Color(tint));
    this.phases[this.n * 2] = phase;
    this.phases[this.n * 2 + 1] = height;
    if (sway) this.sways.set(sway, this.n * 4);
    this.n++;
    this.mesh.count = this.n;
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
    (this.mesh.geometry.getAttribute("aFlame") as THREE.InstancedBufferAttribute).needsUpdate = true;
    (this.mesh.geometry.getAttribute("aSway") as THREE.InstancedBufferAttribute).needsUpdate = true;
  }

  get count(): number {
    return this.n;
  }

  dispose(): void {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}
