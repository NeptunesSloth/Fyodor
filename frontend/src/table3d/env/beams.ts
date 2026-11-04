/**
 * Shafts of light through a room's windows: for each window, the volume its light sweeps to the floor, drawn by marching
 * the view ray through it and gathering the window's own pattern (roomShader.ts windowAt), so the mullions and tracery
 * show as darker bars in the haze and dust drifts through it. Additive and faint; one draw call for every window.
 */
import * as THREE from "three";
import { PRACTICAL_GLSL, type RoomLight } from "./roomShader";

const VERT = /* glsl */ `
varying vec3 vWorld;
void main() {
  vec4 w = modelMatrix * vec4(position, 1.0);
  vWorld = w.xyz;
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

const FRAG = /* glsl */ `
${PRACTICAL_GLSL}
uniform float uFloor;
uniform float uStrength;
uniform float uMotion;
uniform vec3 uKeepOut;
varying vec3 vWorld;
void main() {
  vec3 rd = normalize(vWorld - cameraPosition);
  float jitter = hash13(vec3(gl_FragCoord.xy, 1.0));
  vec3 acc = vec3(0.0);
  const int STEPS = 24;
  float len = 30.0;
  for (int i = 0; i < STEPS; i++) {
    float s = (float(i) + jitter) / float(STEPS) * len;
    vec3 p = vWorld + rd * s;
    if (p.y < uFloor) break;
    for (int k = 0; k < ${2}; k++) {
      if (uWinL[k].w <= 0.0) continue;
      float m = windowAt(k, p);
      if (m <= 0.0) continue;
      // thicker near the glass, thinning to the floor; dust stirring in it
      vec3 N = normalize(cross(uWinU[k].xyz, uWinV[k].xyz));
      float back = abs(dot(p - uWinO[k].xyz, N) / dot(uWinL[k].xyz, N));
      float dens = exp(-back / 26.0) * smoothstep(uFloor, uFloor + 3.0, p.y);
      // no haze over the table, nor between it and the camera
      vec2 ko = abs(p.xz) - uKeepOut.xy;
      dens *= smoothstep(-0.5, 2.5, max(ko.x, ko.y));
      if (p.y > -0.5 && cameraPosition.y > p.y + 0.1) {
        vec3 hit = cameraPosition + (p - cameraPosition) * (cameraPosition.y / (cameraPosition.y - p.y));
        vec2 kh = abs(hit.xz) - uKeepOut.xy;
        dens *= smoothstep(-0.5, 2.5, max(kh.x, kh.y));
      }
      dens *= 0.65 + 0.7 * vnoise(p * 0.45 + vec3(0.0, uTime * 0.05 * uMotion, uTime * 0.03 * uMotion));
      acc += uWinC[k] * uWinL[k].w * m * dens;
    }
  }
  vec3 col = acc * (len / float(STEPS)) * uStrength;
  gl_FragColor = vec4(col, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

/** The beams for a room's windows (null when it has none). */
export function buildBeams(room: RoomLight, floorY: number, strength: number, keepOut: [number, number]): THREE.Mesh | null {
  if (!room.windows.length) return null;
  const pos: number[] = [];
  const idx: number[] = [];
  for (const w of room.windows) {
    const L = w.dir.clone().normalize();
    const corners: THREE.Vector3[] = [];
    for (const [a, b] of [[-1, -1], [1, -1], [1, 1], [-1, 1]] as const) corners.push(w.centre.clone().addScaledVector(w.u, a * w.halfU).addScaledVector(w.v, b * w.halfV));
    const ends = corners.map((c) => c.clone().addScaledVector(L, (floorY - c.y) / Math.min(-1e-3, L.y)));
    const base = pos.length / 3;
    for (const p of [...corners, ...ends]) pos.push(p.x, p.y, p.z);
    // the prism's six faces (winding fixed up below so each faces out)
    const quads = [[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]];
    const centre = new THREE.Vector3();
    for (const p of [...corners, ...ends]) centre.add(p);
    centre.multiplyScalar(1 / 8);
    const all = [...corners, ...ends];
    for (const q of quads) {
      const [a, b, c, d] = q.map((i) => all[i]!);
      const n = b!.clone().sub(a!).cross(c!.clone().sub(a!));
      const out = a!.clone().add(c!).multiplyScalar(0.5).sub(centre);
      const flip = n.dot(out) < 0;
      const tri = flip ? [q[0]!, q[2]!, q[1]!, q[0]!, q[3]!, q[2]!] : [q[0]!, q[1]!, q[2]!, q[0]!, q[2]!, q[3]!];
      void d;
      for (const i of tri) idx.push(base + i);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setIndex(idx);
  geo.computeBoundingSphere();
  const mat = new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: { ...room.uniforms, uFloor: { value: floorY }, uStrength: { value: strength }, uMotion: { value: 1 }, uKeepOut: { value: new THREE.Vector3(keepOut[0], keepOut[1], 0) } },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.FrontSide,
    fog: false,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.renderOrder = 3;
  return mesh;
}
