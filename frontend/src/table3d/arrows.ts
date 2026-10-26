/**
 * Combat and targeting arrows in the style of MTG Arena: a beam of light arcing over the table
 * (a bright tapered core inside a soft coloured halo, with a pulse travelling toward the target),
 * ending in a small crystal hovering over the target with a glow ring beneath it.
 *
 * Purely cosmetic: the arrows are drawn from the server's view (attackers, blockers, targets).
 * Three draw calls per arrow (beam, crystal, ring); they are rebuilt only when an arrow changes.
 */
import * as THREE from "three";

const WIDTH = 0.5; // halo width at the target end (world units)
const SAMPLES = 48;

const beamVertex = /* glsl */ `
  attribute vec2 band; // x: 0..1 from source to target, y: -1..1 across
  varying vec2 vBand;
  #include <common>
  #include <fog_pars_vertex>
  void main() {
    vBand = band;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    #include <fog_vertex>
  }`;

const beamFragment = /* glsl */ `
  uniform vec3 color;
  uniform float time;
  uniform float flow;
  varying vec2 vBand;
  #include <common>
  #include <fog_pars_fragment>
  void main() {
    float across = abs(vBand.y);
    float halo = pow(1.0 - across, 2.2);
    float core = 1.0 - smoothstep(0.0, 0.16, across);
    // a pulse of light travelling to the target
    float p = fract(vBand.x - time * 0.55 * flow);
    float pulse = flow * smoothstep(0.18, 0.0, abs(p - 0.5) * 2.0 - 0.82);
    // fade in from the source, full strength over the target
    float ends = smoothstep(0.0, 0.12, vBand.x);
    vec3 col = color * halo * (0.55 + pulse * 0.8) + vec3(1.0) * core * (0.75 + pulse * 0.5);
    gl_FragColor = vec4(col * ends, 1.0);
    #include <colorspace_fragment>
    #include <fog_fragment>
  }`;

export interface ArrowStyle { color: string; flow: boolean }

/** Shared clock for every arrow's pulse (set each frame by the scene). */
export const arrowTime = { value: 0 };

const crystalGeo = new THREE.OctahedronGeometry(0.13, 0).scale(1, 1.9, 1);
const ringGeo = new THREE.RingGeometry(0.2, 0.27, 40).rotateX(-Math.PI / 2);

function beamGeometry(curve: THREE.Curve<THREE.Vector3>): THREE.BufferGeometry {
  const pos: number[] = [];
  const band: number[] = [];
  const idx: number[] = [];
  const up = new THREE.Vector3(0, 1, 0);
  const side = new THREE.Vector3();
  for (let i = 0; i <= SAMPLES; i++) {
    const u = i / SAMPLES;
    const p = curve.getPointAt(u);
    side.crossVectors(curve.getTangentAt(u), up);
    if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
    // tapered: thin at the source, full width as it lands
    side.normalize().multiplyScalar((WIDTH / 2) * (0.35 + 0.65 * u));
    pos.push(p.x - side.x, p.y - side.y, p.z - side.z, p.x + side.x, p.y + side.y, p.z + side.z);
    band.push(u, -1, u, 1);
    if (i > 0) {
      const a = (i - 1) * 2;
      idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("band", new THREE.Float32BufferAttribute(band, 2));
  geo.setIndex(idx);
  return geo;
}

/** A beam from a to b. userData.dispose frees what the group owns (the shared shapes stay). */
export function makeArrow(a: THREE.Vector3, b: THREE.Vector3, style: ArrowStyle): THREE.Group {
  const mid = a.clone().lerp(b, 0.5);
  mid.y += 1.3 + a.distanceTo(b) * 0.16;
  const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
  const color = new THREE.Color(style.color);
  const beamMat = new THREE.ShaderMaterial({
    vertexShader: beamVertex,
    fragmentShader: beamFragment,
    uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, { color: { value: color }, flow: { value: style.flow ? 1 : 0 } }]),
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
    fog: true,
    toneMapped: false,
  });
  beamMat.uniforms.time = arrowTime; // shared object: one write per frame animates every beam
  const beam = new THREE.Mesh(beamGeometry(curve), beamMat);
  beam.frustumCulled = false;
  beam.renderOrder = 6;

  // the crystal hovers over the target, pointing down at it
  const crystal = new THREE.Mesh(crystalGeo, new THREE.MeshStandardMaterial({
    color: color.clone().lerp(new THREE.Color("#ffffff"), 0.35), emissive: color, emissiveIntensity: 1.1, roughness: 0.15, metalness: 0.2,
  }));
  crystal.position.copy(b).setY(b.y + 0.42);
  crystal.renderOrder = 6;
  const ring = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.4, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
  ring.position.copy(b).setY(b.y + 0.02);
  ring.renderOrder = 6;

  const g = new THREE.Group();
  g.add(beam, crystal, ring);
  g.userData.dispose = () => {
    beam.geometry.dispose();
    beamMat.dispose();
    (crystal.material as THREE.Material).dispose();
    (ring.material as THREE.Material).dispose();
  };
  return g;
}
