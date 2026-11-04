/**
 * The room's drifting particles, moved on the GPU (one draw call per kind, nothing updated per frame but the clock):
 * dust that glints only where a window's light catches it, embers rising off a hearth, low mist, motes, stars,
 * fireflies blinking, petals tumbling, sand on the wind, spores, oil drips and pollen. Sized in world units through the
 * table's long lens (three's own points ignore the lens and came out a pixel wide).
 */
import * as THREE from "three";
import type { Particles } from "../../theme/planes";
import { PRACTICAL_GLSL, type RoomLight } from "./roomShader";

const KIND: Record<Particles, number> = { dust: 0, embers: 1, fog: 2, motes: 3, stars: 4, fireflies: 5, petals: 6, sand: 7, spores: 8, oil: 9, pollen: 10 };

const VERT = /* glsl */ `
${PRACTICAL_GLSL}
attribute vec4 aSeed;
uniform float uKind;
uniform vec3 uBoxMin;
uniform vec3 uBoxSize;
uniform float uSize;
uniform float uPxScale;
uniform float uBeam;
uniform vec3 uKeepOut;
varying float vAlpha;
varying float vSpin;
varying float vGlow;
vec3 wrapBox(vec3 p) { return uBoxMin + mod(p - uBoxMin, uBoxSize); }
void main() {
  float t = uTime;
  vec3 p = position;
  vec4 s = aSeed;
  float alpha = 1.0;
  float glow = 0.0;
  float k = uKind;
  if (k < 0.5) { // dust: a slow, aimless drift
    p += vec3(sin(t * 0.11 + s.x * 6.28) * 1.2, sin(t * 0.07 + s.y * 6.28) * 0.6 + t * 0.03 * (s.z - 0.5), cos(t * 0.09 + s.z * 6.28) * 1.2);
  } else if (k < 1.5) { // embers: rising and fading, a cycle each
    float life = fract(t * (0.12 + s.x * 0.1) + s.y);
    p += vec3(sin(t * 1.3 + s.z * 9.0) * 0.6 * life, life * uBoxSize.y, cos(t * 1.1 + s.x * 7.0) * 0.6 * life);
    alpha = smoothstep(0.0, 0.08, life) * (1.0 - smoothstep(0.45, 1.0, life));
    glow = 1.0;
  } else if (k < 2.5) { // mist: big, slow, low
    p += vec3(sin(t * 0.03 + s.x * 6.28) * 4.0, sin(t * 0.05 + s.y * 6.28) * 0.3, cos(t * 0.025 + s.z * 6.28) * 4.0);
  } else if (k < 3.5) { // motes: hovering, bobbing
    p += vec3(sin(t * 0.25 + s.x * 6.28) * 0.9, sin(t * 0.5 + s.y * 6.28) * 0.5, cos(t * 0.21 + s.z * 6.28) * 0.9);
    alpha = 0.6 + 0.4 * sin(t * (0.8 + s.w) + s.x * 20.0);
    glow = 0.8;
  } else if (k < 4.5) { // stars: still, twinkling
    alpha = 0.35 + 0.65 * pow(0.5 + 0.5 * sin(t * (1.5 + s.w * 2.5) + s.y * 40.0), 3.0);
    glow = 1.0;
  } else if (k < 5.5) { // fireflies: wandering, blinking on and off
    p += vec3(sin(t * 0.35 + s.x * 6.28) * 1.6, sin(t * 0.8 + s.y * 6.28) * 0.6, cos(t * 0.3 + s.z * 6.28) * 1.6);
    float blink = fract(t * (0.18 + s.w * 0.12) + s.x);
    alpha = smoothstep(0.0, 0.08, blink) * (1.0 - smoothstep(0.18, 0.4, blink));
    glow = 1.0;
  } else if (k < 6.5) { // petals: falling, fluttering
    p += vec3(sin(t * 0.6 + s.x * 6.28) * 1.4 + t * 0.4, -t * (0.35 + s.y * 0.3), cos(t * 0.5 + s.z * 6.28) * 1.0);
  } else if (k < 7.5) { // sand: on the wind
    p += vec3(t * (2.0 + s.x * 2.0), sin(t * 2.0 + s.y * 9.0) * 0.15, sin(t * 0.7 + s.z * 6.28) * 0.6);
    alpha = 0.6 + 0.4 * s.w;
  } else if (k < 8.5) { // spores: rising slowly
    p += vec3(sin(t * 0.3 + s.x * 6.28) * 0.7, t * (0.12 + s.y * 0.15), cos(t * 0.27 + s.z * 6.28) * 0.7);
    glow = 0.6;
  } else if (k < 9.5) { // oil: drops falling, fast at the end
    float life = fract(t * (0.08 + s.x * 0.06) + s.y);
    p.y -= life * life * uBoxSize.y;
    alpha = smoothstep(0.0, 0.1, life);
  } else { // pollen: drifting up and across
    p += vec3(sin(t * 0.2 + s.x * 6.28) * 1.4 + t * 0.15, t * 0.06 + sin(t * 0.4 + s.y * 6.28) * 0.3, cos(t * 0.17 + s.z * 6.28) * 1.4);
    glow = 0.5;
  }
  p = wrapBox(p);
  // dust and mist glint where a window's light passes, and stay faint elsewhere
  float lit = 0.0;
  for (int i = 0; i < ${2}; i++) lit += windowAt(i, p) * uWinL[i].w;
  vGlow = glow + lit * uBeam;
  // fade near the box's edges, so the wrap never pops
  vec3 e = min(p - uBoxMin, uBoxMin + uBoxSize - p) / (uBoxSize * 0.12);
  alpha *= clamp(min(min(e.x, e.y), e.z), 0.0, 1.0);
  // and never over the table itself (the cards stay clear)
  vec2 ko = abs(p.xz) - uKeepOut.xy;
  float outside = max(ko.x, ko.y);
  alpha *= max(smoothstep(-0.5, 1.5, outside), smoothstep(uKeepOut.z - 2.0, uKeepOut.z, p.y));
  vAlpha = alpha;
  vSpin = s.w * 6.28 + t * (0.6 + s.x);
  vec4 mv = viewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * (0.6 + s.z * 0.8) * uPxScale * projectionMatrix[1][1] / max(-mv.z, 0.1);
}`;

const FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacity;
uniform float uKind;
uniform float uBase;
varying float vAlpha;
varying float vSpin;
varying float vGlow;
void main() {
  vec2 q = gl_PointCoord - 0.5;
  float a;
  if (uKind > 5.5 && uKind < 6.5) {
    // a petal: a small rotated ellipse, notched
    float c = cos(vSpin), s = sin(vSpin);
    vec2 r = vec2(c * q.x - s * q.y, s * q.x + c * q.y);
    a = 1.0 - smoothstep(0.32, 0.4, length(r * vec2(1.0, 2.1)));
  } else if (uKind > 1.5 && uKind < 2.5) {
    a = exp(-dot(q, q) * 9.0);
  } else {
    float d = length(q) * 2.0;
    a = exp(-d * d * 5.0) + (1.0 - smoothstep(0.1, 0.25, d)) * 0.6;
  }
  float bright = uBase + vGlow;
  gl_FragColor = vec4(uColor * bright, a * vAlpha * uOpacity * min(1.0, bright));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

export interface ParticleOptions {
  kind: Particles;
  color: THREE.ColorRepresentation;
  count: number;
  /** The volume they live in (world units). */
  min: THREE.Vector3;
  max: THREE.Vector3;
  /** Diameter (world units). */
  size: number;
  opacity: number;
  /** Brightness away from any light (the window's light adds `beam`). */
  base?: number;
  beam?: number;
  additive?: boolean;
  seed: () => number;
  /** Half extents (x, z) of the table and a height: no particle shows over the table below that height. */
  keepOut?: [number, number, number];
}

export function buildParticles(room: RoomLight, o: ParticleOptions): THREE.Points | null {
  if (o.count <= 0) return null;
  const pos = new Float32Array(o.count * 3);
  const seed = new Float32Array(o.count * 4);
  const size = o.max.clone().sub(o.min);
  for (let i = 0; i < o.count; i++) {
    pos[i * 3] = o.min.x + o.seed() * size.x;
    pos[i * 3 + 1] = o.min.y + o.seed() * size.y;
    pos[i * 3 + 2] = o.min.z + o.seed() * size.z;
    seed.set([o.seed(), o.seed(), o.seed(), o.seed()], i * 4);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aSeed", new THREE.BufferAttribute(seed, 4));
  const kind = KIND[o.kind];
  const pxScale = { value: 500 };
  const mat = new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: {
      ...room.uniforms,
      uKind: { value: kind },
      uBoxMin: { value: o.min.clone() },
      uBoxSize: { value: size },
      uSize: { value: o.size },
      uPxScale: pxScale,
      uColor: { value: new THREE.Color(o.color) },
      uOpacity: { value: o.opacity },
      uBase: { value: o.base ?? 1 },
      uBeam: { value: o.beam ?? 0 },
      uKeepOut: { value: new THREE.Vector3(...(o.keepOut ?? [0, 0, -100])) },
    },
    transparent: true,
    depthWrite: false,
    blending: o.additive === false ? THREE.NormalBlending : THREE.AdditiveBlending,
    fog: false,
  });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  points.renderOrder = 4;
  const v = new THREE.Vector2();
  // the point size in pixels per world unit at unit distance: half the drawing buffer's height
  points.onBeforeRender = (renderer) => {
    renderer.getDrawingBufferSize(v);
    pxScale.value = v.y / 2;
  };
  return points;
}
