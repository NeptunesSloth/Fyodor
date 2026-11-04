/**
 * The room's own light, shared by every surface of a plane's set (env/sets.ts), its floor and the props on the table:
 * - practicals: the hearth, candle clusters, lanterns and braziers light the room around them (a cheap, soft falloff
 *   computed in the room's shaders, not three.js lights, so a room of fires costs no extra light passes on the table);
 * - pulses: the self-lit parts (embers, flames' cups, lantern glass, glowing windows) breathe with their light;
 * - depth: the room falls away into the plane's dark with distance from the table (layers of atmosphere that don't
 *   depend on how far back the camera stands), so the lit table always reads first.
 *
 * Each environment build owns one RoomLight; materials join it with `decorate` (onBeforeCompile on a stock
 * MeshStandardMaterial, so shadows, fog and the key light still apply).
 */
import * as THREE from "three";
import { flicker, hearth } from "./flicker";

export const MAX_PRACTICALS = 8;
export const MAX_WINDOWS = 2;

/** A window's light pattern (the panes and bars its light keeps): see windowMask in the GLSL. */
export const WINDOW = { none: 0, casement: 1, tracery: 2, shoji: 3, arch: 4 } as const;

/**
 * A window letting light into the room: its centre, its horizontal (u) and vertical (v) axes with their half sizes,
 * the direction its light travels (into the room, downward), the light's colour and strength, and its pattern.
 */
export interface WindowSpec {
  centre: THREE.Vector3;
  u: THREE.Vector3;
  v: THREE.Vector3;
  halfU: number;
  halfV: number;
  dir: THREE.Vector3;
  color: THREE.ColorRepresentation;
  intensity: number;
  pattern: number;
}

/** How a practical's brightness moves: a candle's flutter, a hearth's breathing, or steady (glass, moonlight). */
export type PracticalKind = "candle" | "hearth" | "steady";

/** Pulse channels for self-lit parts: 0 steady, 1 the hearth, 2 candles, 3 lanterns and braziers. */
export const PULSE = { steady: 0, hearth: 1, candle: 2, lantern: 3 } as const;

interface Practical { pos: THREE.Vector3; color: THREE.Color; intensity: number; radius: number; kind: PracticalKind; phase: number; amount: number }

export class RoomLight {
  readonly uniforms = {
    uPracPos: { value: Array.from({ length: MAX_PRACTICALS }, () => new THREE.Vector4(0, -999, 0, 0.001)) },
    uPracCol: { value: Array.from({ length: MAX_PRACTICALS }, () => new THREE.Vector3()) },
    uPulse: { value: new THREE.Vector4(1, 1, 1, 1) },
    /** From .x to .y (distance from the table's middle) the room fades into uFadeCol, by at most .z. */
    uFade: { value: new THREE.Vector3(30, 70, 0.85) },
    uFadeCol: { value: new THREE.Color(0, 0, 0) },
    uTime: { value: 0 },
    uWinO: { value: Array.from({ length: MAX_WINDOWS }, () => new THREE.Vector4()) },
    uWinU: { value: Array.from({ length: MAX_WINDOWS }, () => new THREE.Vector4(1, 0, 0, 1)) },
    uWinV: { value: Array.from({ length: MAX_WINDOWS }, () => new THREE.Vector4(0, 1, 0, 1)) },
    uWinL: { value: Array.from({ length: MAX_WINDOWS }, () => new THREE.Vector4(0, -1, 0, 0)) },
    uWinC: { value: Array.from({ length: MAX_WINDOWS }, () => new THREE.Vector3()) },
  };
  readonly windows: WindowSpec[] = [];
  /**
   * The cutaway (decorate's `cutaway`): the table's reach from its middle (world units), how far past it a piece may
   * stand on the camera's side before it goes, and how far below the sightline to the table's near edge to cut.
   */
  readonly cut = { value: new THREE.Vector3(12, 3, 1.5) };
  private list: Practical[] = [];
  private amount: number;

  constructor(fadeColor: THREE.ColorRepresentation, flickerAmount: number) {
    this.uniforms.uFadeCol.value.set(fadeColor);
    this.amount = flickerAmount;
  }

  /** A light in the room (world position, colour, strength, reach). Past MAX_PRACTICALS the weakest are dropped. */
  add(pos: THREE.Vector3, color: THREE.ColorRepresentation, intensity: number, radius: number, kind: PracticalKind = "candle", phase = 0): void {
    this.list.push({ pos: pos.clone(), color: new THREE.Color(color), intensity, radius, kind, phase, amount: kind === "steady" ? 0 : this.amount });
    this.list.sort((a, b) => b.intensity * b.radius - a.intensity * a.radius);
    this.list.length = Math.min(this.list.length, MAX_PRACTICALS);
    this.update(0);
  }

  /** A window's light (at most MAX_WINDOWS; later ones are ignored). */
  addWindow(w: WindowSpec): void {
    const i = this.windows.length;
    if (i >= MAX_WINDOWS) return;
    this.windows.push(w);
    const u = this.uniforms;
    const L = w.dir.clone().normalize();
    u.uWinO.value[i]!.set(w.centre.x, w.centre.y, w.centre.z, w.pattern);
    u.uWinU.value[i]!.set(w.u.x, w.u.y, w.u.z, w.halfU);
    u.uWinV.value[i]!.set(w.v.x, w.v.y, w.v.z, w.halfV);
    u.uWinL.value[i]!.set(L.x, L.y, L.z, w.intensity);
    const c = new THREE.Color(w.color);
    u.uWinC.value[i]!.set(c.r, c.g, c.b);
  }

  /** How many practicals the room has (the shaders loop over these only). */
  get count(): number {
    return this.list.length;
  }

  setFade(near: number, far: number, max = 0.85): void {
    this.uniforms.uFade.value.set(near, far, max);
  }

  update(t: number): void {
    const u = this.uniforms;
    u.uTime.value = t;
    for (let i = 0; i < MAX_PRACTICALS; i++) {
      const p = this.list[i];
      if (!p) {
        u.uPracPos.value[i]!.set(0, -999, 0, 0.001);
        u.uPracCol.value[i]!.set(0, 0, 0);
        continue;
      }
      const f = p.kind === "hearth" ? hearth(t, p.phase, p.amount * 1.6) : p.kind === "candle" ? flicker(t, p.phase, p.amount) : 1;
      u.uPracPos.value[i]!.set(p.pos.x, p.pos.y, p.pos.z, p.radius);
      u.uPracCol.value[i]!.set(p.color.r * p.intensity * f, p.color.g * p.intensity * f, p.color.b * p.intensity * f);
    }
    u.uPulse.value.set(1, hearth(t, 0.37, this.amount * 1.8), flicker(t, 1.9, this.amount * 1.2), flicker(t, 4.1, this.amount * 0.6));
  }
}

/**
 * GLSL (vertex): GPU motion for parts built with a sway code (batch.ts SWAY): a lantern swinging on its chain about its
 * pivot (flicker.ts sway, the same sums of sines), a stone adrift or hovering (bobbing, turning slowly). `n` turns along.
 */
export const SWAY_GLSL = /* glsl */ `
vec3 swayPos(vec3 p, vec4 s, inout vec3 n, float t) {
  if (s.w < 0.0) return p;
  float kind = floor(s.w / 100.0);
  float ph = s.w - kind * 100.0;
  vec3 d = p - s.xyz;
  if (kind < 1.5) {
    float a = (sin(t * 1.35 + ph) * 0.75 + sin(t * 0.53 + ph * 2.1) * 0.25) * 0.055;
    float b = (sin(t * 1.05 + ph * 1.7) * 0.6 + sin(t * 0.41 + ph * 0.6) * 0.4) * 0.055 * 0.6;
    float ca = cos(a), sa = sin(a), cb = cos(b), sb = sin(b);
    d = vec3(d.x, d.y * ca - d.z * sa, d.y * sa + d.z * ca);
    d = vec3(d.x * cb - d.y * sb, d.x * sb + d.y * cb, d.z);
    n = vec3(n.x, n.y * ca - n.z * sa, n.y * sa + n.z * ca);
    n = vec3(n.x * cb - n.y * sb, n.x * sb + n.y * cb, n.z);
    return s.xyz + d;
  }
  float amp = kind < 2.5 ? 0.6 : 0.05;
  float spin = t * (kind < 2.5 ? 0.06 : 0.3) + ph;
  float cs = cos(spin), sn = sin(spin);
  d = vec3(d.x * cs - d.z * sn, d.y, d.x * sn + d.z * cs);
  n = vec3(n.x * cs - n.z * sn, n.y, n.x * sn + n.z * cs);
  return s.xyz + d + vec3(0.0, sin(t * 0.6 + ph) * amp, 0.0);
}
`;

/** GLSL: the practicals' light at a world point with a world normal (soft wrap, smooth falloff to its reach). */
/** PRACTICAL_GLSL for a room, its loops bounded by the practicals and windows it really has (fewer per pixel). */
export function practicalGlsl(room: RoomLight): string {
  return PRACTICAL_GLSL.replace("PRAC_COUNT", String(Math.max(1, room.count))).replace("WIN_COUNT", String(room.windows.length));
}

export const PRACTICAL_GLSL = /* glsl */ `
uniform vec4 uPracPos[${MAX_PRACTICALS}];
uniform vec3 uPracCol[${MAX_PRACTICALS}];
uniform vec4 uPulse;
uniform vec3 uFade;
uniform vec3 uFadeCol;
uniform float uTime;
uniform vec3 uCut;
uniform vec4 uWinO[${MAX_WINDOWS}];
uniform vec4 uWinU[${MAX_WINDOWS}];
uniform vec4 uWinV[${MAX_WINDOWS}];
uniform vec4 uWinL[${MAX_WINDOWS}];
uniform vec3 uWinC[${MAX_WINDOWS}];
// a window's glazing at (a, b) across it (-1..1 each way): 1 where light passes, 0 on the frame and bars
float windowMask(float a, float b, float pattern) {
  float edge = 0.03;
  float inside = smoothstep(1.0, 1.0 - edge, abs(a)) * smoothstep(1.0, 1.0 - edge, abs(b));
  if (pattern < 0.5) return 0.0;
  if (pattern < 1.5) {
    // a casement: a stout middle mullion and transoms, small leaded panes
    float m = smoothstep(0.035, 0.06, abs(a));
    float tb = abs(fract(b * 2.0 + 0.5) - 0.5);
    m *= smoothstep(0.02, 0.045, tb);
    float la = abs(fract(a * 3.0) - 0.5), lb = abs(fract(b * 4.0) - 0.5);
    m *= 1.0 - 0.55 * (1.0 - smoothstep(0.015, 0.04, 0.5 - max(la, lb)));
    return inside * m;
  }
  if (pattern < 2.5) {
    // gothic tracery: two pointed lancets under a rose
    float arch = step(length(vec2(abs(a) + 0.55, b - 0.25)), 1.55) * step(b, 0.98);
    float lancet = abs(a) > 0.08 ? 1.0 : 0.0;
    float la = abs(a) - 0.5;
    float lanArch = b < 0.3 ? smoothstep(0.42, 0.38, abs(la)) : step(length(vec2(abs(la) + 0.25, b - 0.3)), 0.66) * step(abs(la), 0.42);
    vec2 rc = vec2(a, b - 0.68);
    float rose = smoothstep(0.3, 0.27, length(rc)) * smoothstep(0.035, 0.06, abs(length(rc) - 0.16)) * smoothstep(0.02, 0.04, abs(sin(atan(rc.y, rc.x) * 3.0)) * length(rc));
    float m = max(lancet * lanArch, rose) * arch;
    return smoothstep(1.0, 0.97, abs(a)) * step(-1.0, b) * m;
  }
  if (pattern < 3.5) {
    // shoji: a fine square grid of bars over paper (the light comes through soft)
    float ga = abs(fract(a * 3.0) - 0.5), gb = abs(fract(b * 5.0) - 0.5);
    return inside * (0.55 + 0.45 * smoothstep(0.42, 0.46, 0.5 - max(0.5 - ga, 0.5 - gb) + 0.5 - 0.5));
  }
  // a round-headed arch with one mullion
  float r = step(length(vec2(a, max(b - 0.4, 0.0) / 0.6)), 1.0);
  return smoothstep(1.0, 0.97, abs(a)) * step(-1.0, b) * r * smoothstep(0.03, 0.06, abs(a));
}
// how much of window i's light reaches point p (its pattern, projected along its light)
float windowAt(int i, vec3 p) {
  vec3 L = uWinL[i].xyz;
  vec3 N = normalize(cross(uWinU[i].xyz, uWinV[i].xyz));
  float den = dot(L, N);
  if (abs(den) < 1e-4 || uWinL[i].w <= 0.0) return 0.0;
  float s = dot(p - uWinO[i].xyz, N) / den; // how far back along the light the window is
  if (s < 0.0) return 0.0;
  vec3 h = p - L * s - uWinO[i].xyz;
  return windowMask(dot(h, uWinU[i].xyz) / uWinU[i].w, dot(h, uWinV[i].xyz) / uWinV[i].w, uWinO[i].w);
}
vec3 windowLight(vec3 p, vec3 n) {
  vec3 acc = vec3(0.0);
  for (int i = 0; i < WIN_COUNT; i++) {
    float m = windowAt(i, p);
    acc += uWinC[i] * uWinL[i].w * m * max(dot(n, -uWinL[i].xyz), 0.0);
  }
  return acc;
}
vec3 practicalLight(vec3 p, vec3 n) {
  vec3 acc = vec3(0.0);
  for (int i = 0; i < PRAC_COUNT; i++) {
    vec3 d = uPracPos[i].xyz - p;
    float dist = length(d);
    float k = clamp(1.0 - dist / uPracPos[i].w, 0.0, 1.0);
    float wrap = dot(n, d / max(dist, 1e-3)) * 0.6 + 0.4;
    acc += uPracCol[i] * (k * k) * max(wrap, 0.0);
  }
  return acc;
}
float roomFade(vec3 p) {
  return smoothstep(uFade.x, uFade.y, length(p.xz)) * uFade.z;
}
float hash13(vec3 p3) {
  p3 = fract(p3 * 0.1031);
  p3 += dot(p3, p3.zyx + 31.32);
  return fract((p3.x + p3.y) * p3.z);
}
float vnoise(vec3 p) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), f.x), mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), f.x), mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
`;

export interface DecorateOptions {
  /** Cache key (one per distinct option set). */
  key: string;
  /** Per-vertex surface: attribute `aSurf` (roughness, metalness, self-light, pulse channel). */
  surf?: boolean;
  /** Large-scale tone variation by world position (0: none), so repeats and flat faces don't read as copies. */
  macro?: number;
  /** The macro variation's scale (world units per blotch). */
  macroScale?: number;
  /** How much the practicals light this surface (1: fully). */
  practical?: number;
  /** Fade into the room's dark with distance (default on). */
  fade?: boolean;
  /** Scale on the scene's direct light (the key and the table's pool): below 1 keeps the room out of the table's light. */
  direct?: number;
  /** Scale on the scene's fill (hemisphere and environment light). */
  indirect?: number;
  /**
   * Dollhouse cutaway: whatever stands between the camera and the table (the near wall, the shelves behind my chair)
   * is cut down to below the line of sight to the table's near edge, wherever the camera is orbited to.
   */
  cutaway?: boolean;
  /**
   * Image-based light from the scene's environment map (default on). The room's own surfaces go without: they are lit
   * by the room's practicals and the fill light, and sampling the environment was the costliest part of their shading.
   */
  ibl?: boolean;
  /** A soft shadow cast on this surface by the table (centre x, z; half width, half depth; softness; darkness). */
  under?: { x: number; z: number; hw: number; hd: number; soft: number; dark: number };
}



/** Join a stock material to a room's light (see the file comment). Returns the same material. */
export function decorate<M extends THREE.MeshStandardMaterial>(mat: M, room: RoomLight, o: DecorateOptions): M {
  const macro = o.macro ?? 0;
  const prac = o.practical ?? 1;
  const direct = o.direct ?? 1;
  const fade = o.fade !== false;
  mat.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, room.uniforms, { uCut: room.cut });
    sh.vertexShader = sh.vertexShader
      .replace("#include <common>", `#include <common>\nvarying vec3 vRoomPos;\nvarying vec3 vRoomNormal;\n${o.surf ? `attribute vec4 aSurf;\nattribute vec4 aSway;\nvarying vec4 vSurf;\nuniform float uTime;\n${SWAY_GLSL}` : ""}${o.cutaway ? "\nattribute vec2 aAnchor;\nuniform vec3 uCut;" : ""}`)
      .replace("#include <beginnormal_vertex>", `#include <beginnormal_vertex>\n${o.surf ? "vec3 swayN = objectNormal; vec3 swayP = swayPos(position, aSway, swayN, uTime); objectNormal = swayN;" : ""}`)
      .replace("#include <begin_vertex>", `#include <begin_vertex>\n${o.surf ? "transformed = swayP;" : ""}`)
      .replace("#include <fog_vertex>", `#include <fog_vertex>
        {
          vec4 rp = vec4(transformed, 1.0);
          vec3 rn = objectNormal;
          #ifdef USE_INSTANCING
            rp = instanceMatrix * rp;
            rn = mat3(instanceMatrix) * rn;
          #endif
          rp = modelMatrix * rp;
          vRoomPos = rp.xyz;
          vRoomNormal = normalize(mat3(modelMatrix) * rn);
          ${o.surf ? "vSurf = aSurf;" : ""}
        }
        ${o.cutaway ? `{
          // the dollhouse cutaway: a piece standing between the camera and the table goes whole (its triangles
          // collapse to nothing, so no fragment is shaded or thrown away)
          vec2 cxz = cameraPosition.xz;
          float cl = length(cxz);
          if (cl > 1.0 && dot(aAnchor, cxz / cl) > uCut.x + uCut.y) gl_Position = vec4(0.0, 0.0, -2.0, 1.0);
        }` : ""}`);
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <common>", `#include <common>\nvarying vec3 vRoomPos;\nvarying vec3 vRoomNormal;\n${o.surf ? "varying vec4 vSurf;" : ""}\n${o.ibl === false ? "#undef USE_ENVMAP\n" : ""}${practicalGlsl(room)}`)
      .replace("#include <color_fragment>", `#include <color_fragment>
        ${macro > 0 ? `diffuseColor.rgb *= 1.0 + (vnoise(vRoomPos / ${(o.macroScale ?? 3).toFixed(2)}) - 0.5) * ${(macro * 2).toFixed(3)};` : ""}`)
      .replace("#include <roughnessmap_fragment>", `#include <roughnessmap_fragment>
        ${o.surf ? "roughnessFactor *= vSurf.x;" : ""}`)
      .replace("#include <metalnessmap_fragment>", `#include <metalnessmap_fragment>
        ${o.surf ? "metalnessFactor *= vSurf.y;" : ""}`)
      .replace("#include <emissivemap_fragment>", `#include <emissivemap_fragment>
        ${o.surf ? "{ int ch = int(vSurf.w + 0.5); float pulse = ch == 1 ? uPulse.y : ch == 2 ? uPulse.z : ch == 3 ? uPulse.w : 1.0; totalEmissiveRadiance += diffuseColor.rgb * vSurf.z * pulse; }" : ""}`)
      .replace("#include <lights_fragment_end>", `#include <lights_fragment_end>
        ${direct !== 1 ? `reflectedLight.directDiffuse *= ${direct.toFixed(3)}; reflectedLight.directSpecular *= ${direct.toFixed(3)};` : ""}
        ${(o.indirect ?? 1) !== 1 ? `reflectedLight.indirectDiffuse *= ${(o.indirect ?? 1).toFixed(3)}; reflectedLight.indirectSpecular *= ${(o.indirect ?? 1).toFixed(3)};` : ""}
        vec3 roomPrac = (practicalLight(vRoomPos, normalize(vRoomNormal)) + windowLight(vRoomPos, normalize(vRoomNormal))) * ${prac.toFixed(3)};
        reflectedLight.indirectDiffuse += material.diffuseColor * roomPrac;`)
      .replace("#include <opaque_fragment>", `${o.under ? `{
          vec2 q = abs(vRoomPos.xz - vec2(${o.under.x.toFixed(3)}, ${o.under.z.toFixed(3)})) - vec2(${o.under.hw.toFixed(3)}, ${o.under.hd.toFixed(3)});
          float sd = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0);
          outgoingLight *= 1.0 - ${o.under.dark.toFixed(3)} * (1.0 - smoothstep(-${o.under.soft.toFixed(3)}, ${o.under.soft.toFixed(3)}, sd));
        }` : ""}
        ${fade ? `{
          // the room falls away into the dark, except where its own lights (and the moon) fall, and its embers and
          // lamps keep most of their glow: points of light in a dim room
          float lit = smoothstep(0.0, 0.45, dot(roomPrac, vec3(0.3, 0.5, 0.2)));
          float f = roomFade(vRoomPos) * (1.0 - lit * 0.8);
          vec3 selfLit = min(totalEmissiveRadiance, outgoingLight);
          outgoingLight = mix(outgoingLight - selfLit, uFadeCol, f) + selfLit * (1.0 - f * 0.4);
        }` : ""}\n#include <opaque_fragment>`);
  };
  mat.customProgramCacheKey = () => `room:${o.key}:${o.surf ? 1 : 0}:${macro}:${o.macroScale ?? 3}:${prac}:${direct}:${fade ? 1 : 0}:${o.cutaway ? 1 : 0}:${o.indirect ?? 1}:${o.under ? JSON.stringify(o.under) : ""}:${room.count}:${room.windows.length}:${o.ibl === false ? 0 : 1}`;
  return mat;
}
