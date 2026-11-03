/**
 * Attachment lines on the 3D table (game/attachments.ts decides which): a thin bone-coloured cord from an Aura,
 * Equipment or Fortification to what it's attached to, with a small ring on the host. Quiet on purpose: no glow,
 * no pulse, no arrowhead (the target and combat beams own those); it shows only while either end is hovered or
 * selected. One draw call per cord and per end mark; rebuilt only when a line changes.
 */
import * as THREE from "three";

export const TETHER_COLOR = "#e6dcc6";

const ringGeo = new THREE.RingGeometry(0.11, 0.15, 28).rotateX(-Math.PI / 2);
const dotGeo = new THREE.CircleGeometry(0.06, 16).rotateX(-Math.PI / 2);

/** A cord from the attachment (a) to its host (b): a low arc just over the cards. userData.dispose frees it. */
export function makeTether(a: THREE.Vector3, b: THREE.Vector3, color: THREE.ColorRepresentation = TETHER_COLOR): THREE.Group {
  const dist = Math.hypot(a.x - b.x, a.z - b.z);
  const mid = a.clone().lerp(b, 0.5);
  mid.y = Math.max(a.y, b.y) + 0.12 + Math.min(1.2, dist * 0.12);
  const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
  const tube = new THREE.TubeGeometry(curve, Math.max(8, Math.min(48, Math.round(dist * 8))), 0.018, 5, false);
  // drawn over the cards (as the 2D table's SVG line is): it ends on a card face that a hover may have just lifted
  const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85, depthWrite: false, depthTest: false });
  const cord = new THREE.Mesh(tube, mat);
  const ring = new THREE.Mesh(ringGeo, mat);
  ring.position.copy(b);
  const dot = new THREE.Mesh(dotGeo, mat);
  dot.position.copy(a);
  const g = new THREE.Group();
  for (const m of [cord, ring, dot]) {
    m.renderOrder = 7;
    m.frustumCulled = false;
    g.add(m);
  }
  g.userData.dispose = () => {
    tube.dispose();
    mat.dispose();
  };
  return g;
}
