/**
 * Combat and targeting arrows in the style of the digital card games (Arena, Master Duel): a flat
 * ribbon arcing over the table with chevrons flowing toward the target, a bright core, a dark rim
 * so it reads over pale cards, and a broad arrowhead. One mesh (one draw call) per arrow.
 *
 * Purely cosmetic: the arrows are drawn from the server's view (attackers, blockers, targets).
 */
import * as THREE from "three";

const WIDTH = 0.36; // shaft width (world units)
const HEAD_LEN = 0.62;
const HEAD_W = 2.5; // head width × shaft width
const SAMPLES = 40;

const vertexShader = /* glsl */ `
  attribute vec3 band; // x: distance from the tail (world units), y: -1..1 across, z: 1 on the head
  varying vec3 vBand;
  #include <common>
  #include <fog_pars_vertex>
  void main() {
    vBand = band;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    #include <fog_vertex>
  }`;

const fragmentShader = /* glsl */ `
  uniform vec3 color;
  uniform float time;
  uniform float flow;
  uniform float len;
  varying vec3 vBand;
  #include <common>
  #include <fog_pars_fragment>
  void main() {
    float across = abs(vBand.y);
    float head = vBand.z;
    // dark rim outside the coloured body
    float body = 1.0 - smoothstep(0.62, 0.72, across);
    float rimA = 1.0 - smoothstep(0.86, 1.0, across);
    // chevrons pointing at the target, flowing along the shaft
    float c = fract((vBand.x - across * 0.32) * 1.15 - time * 0.9 * flow);
    float chevron = smoothstep(0.0, 0.08, c) * (1.0 - smoothstep(0.3, 0.42, c));
    float core = 1.0 - smoothstep(0.0, 0.32, across);
    vec3 shaft = color * (0.55 + 0.75 * chevron) + vec3(1.0) * core * chevron * 0.25;
    vec3 tip = color * 1.2 + vec3(1.0) * (1.0 - across) * 0.22;
    vec3 col = mix(shaft, tip, head);
    // fade in from the source; brighten toward the head
    float tail = smoothstep(0.0, 0.9, vBand.x);
    col *= 0.8 + 0.35 * smoothstep(len * 0.4, len, vBand.x);
    vec3 outC = mix(vec3(0.03, 0.02, 0.015), col, body);
    float a = rimA * mix(0.55, 1.0, body) * tail;
    gl_FragColor = vec4(outC, a);
    #include <colorspace_fragment>
    #include <fog_fragment>
  }`;

export interface ArrowStyle { color: string; flow: boolean }

/** Shared clock for every arrow's flow (set each frame by the scene). */
export const arrowTime = { value: 0 };

export function makeArrow(curve: THREE.Curve<THREE.Vector3>, style: ArrowStyle): THREE.Mesh {
  const len = curve.getLength();
  const headLen = Math.min(HEAD_LEN, len * 0.35);
  const headAt = 1 - headLen / len;
  // shaft samples up to the head base, then the head (base duplicated: the width jumps there)
  const us: { u: number; w: number; head: number }[] = [];
  for (let i = 0; i <= SAMPLES; i++) us.push({ u: (i / SAMPLES) * headAt, w: 1, head: 0 });
  for (let i = 0; i <= 6; i++) {
    const t = i / 6;
    us.push({ u: headAt + t * (1 - headAt), w: HEAD_W * (1 - t) + 0.001, head: 1 });
  }
  const pos: number[] = [];
  const band: number[] = [];
  const idx: number[] = [];
  const up = new THREE.Vector3(0, 1, 0);
  const side = new THREE.Vector3();
  us.forEach(({ u, w, head }, i) => {
    const p = curve.getPointAt(u);
    const tan = curve.getTangentAt(u);
    side.crossVectors(tan, up);
    if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
    side.normalize().multiplyScalar((WIDTH * w) / 2);
    pos.push(p.x - side.x, p.y - side.y, p.z - side.z, p.x + side.x, p.y + side.y, p.z + side.z);
    const d = u * len;
    band.push(d, -1, head, d, 1, head);
    if (i > 0 && !(us[i - 1]!.head === 0 && head === 1)) {
      const a = (i - 1) * 2;
      idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("band", new THREE.Float32BufferAttribute(band, 3));
  geo.setIndex(idx);
  const mat = new THREE.ShaderMaterial({
    vertexShader,
    fragmentShader,
    uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, {
      color: { value: new THREE.Color(style.color) },
      flow: { value: style.flow ? 1 : 0 },
      len: { value: len },
    }]),
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    fog: true,
    toneMapped: false,
  });
  mat.uniforms.time = arrowTime; // shared object: one write per frame animates every arrow
  const mesh = new THREE.Mesh(geo, mat);
  mesh.renderOrder = 5;
  mesh.frustumCulled = false;
  return mesh;
}
