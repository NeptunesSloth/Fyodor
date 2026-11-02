/**
 * END-OF-GAME TABLE SCENE on the 3D table (the beats are game/motion/endScene.ts): the room's light drops and takes the
 * result's colour (one full-screen multiply, a little stronger toward the edges so the battlefield stays the brightest
 * thing), the camera eases a few percent toward the board or away from it, one soft ring of light (or shadow) crosses
 * the battlefields, and a handful of motes rise from the felt.
 *
 * Stepped from the table's one frame loop (TableScene.loop) and only while a scene plays (``active``). Three draw
 * calls at most, made once on the first scene and reused (nothing is allocated per frame); hidden again when the
 * table has settled back. The camera's push is applied over where the table's own camera is this frame, so it never
 * touches the camera's goal: the player keeps control, and it comes back by itself.
 */
import * as THREE from "three";
import { endAt, endFrame, endSceneTime, moteAt, moteFrame, type EndCue } from "../game/motion/endScene";
import { CARD_H } from "./layout";

const MAX_MOTES = 16;
/** How much of the dim the middle of the screen gets, and how much deeper the edges go. */
const CENTRE = 0.65;
const EDGE = 0.85;
const frame = endFrame();
const mote = moteFrame();
const color = new THREE.Color();
const offset = new THREE.Vector3();

/** One triangle that covers the screen, drawn straight in clip space (no camera maths; the view offset doesn't matter). */
const SHADE_VERT = /* glsl */ `
  varying vec2 vPos;
  void main() { vPos = position.xy; gl_Position = vec4(position.xy, 0.0, 1.0); }`;
/** The colour the scene is multiplied by: ``shade`` in the middle, ``edge`` toward the screen's edges. */
const SHADE_FRAG = /* glsl */ `
  uniform vec3 shade;
  uniform vec3 edge;
  varying vec2 vPos;
  void main() {
    float r = smoothstep(0.25, 1.25, length(vPos * vec2(1.0, 1.15)));
    gl_FragColor = vec4(mix(shade, edge, r), 1.0);
  }`;

function ringTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d")!;
  // a soft band of light, brightest a little inside the rim: as it grows it reads as light passing over the table
  const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grad.addColorStop(0, "rgba(255,255,255,0)");
  grad.addColorStop(0.45, "rgba(255,255,255,0.04)");
  grad.addColorStop(0.64, "rgba(255,255,255,0.32)");
  grad.addColorStop(0.75, "rgba(255,255,255,1)");
  grad.addColorStop(0.85, "rgba(255,255,255,0.28)");
  grad.addColorStop(0.96, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function dotTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(16, 16, 0, 16, 16, 16);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.35, "rgba(255,255,255,0.55)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 32, 32);
  return new THREE.CanvasTexture(c);
}

interface Parts {
  shade: THREE.Mesh<THREE.BufferGeometry, THREE.ShaderMaterial>;
  pulse: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>;
  motes: THREE.Points<THREE.BufferGeometry, THREE.PointsMaterial>;
  positions: Float32Array;
  colors: Float32Array;
}

export class EndScene3D {
  /** A scene is playing or settling back (the frame loop steps it only then). */
  active = false;
  private cue: EndCue | null = null;
  private parts: Parts | null = null;
  private scene: THREE.Scene;
  /** The table's size (world units) and its middle. */
  private size: () => { w: number; d: number };

  constructor(scene: THREE.Scene, size: () => { w: number; d: number }) {
    this.scene = scene;
    this.size = size;
  }

  /** The cue changed (game/motion/endScene.ts): a new scene, its release, or nothing. */
  play(cue: EndCue | null): void {
    this.cue = cue;
    if (cue) {
      this.build();
      this.active = true;
    } else {
      this.hide();
    }
  }

  /**
   * One frame: the dim, the pulse, the motes, and the camera's push over where the table's camera is this frame
   * (``cam`` is moved along its line to ``look``; the caller calls lookAt after). The pulse and the motes centre on
   * ``centre``: where the camera is headed (the winner's seat, or the middle of the view), so they are always in sight.
   */
  update(now: number, reduced: boolean, cam: THREE.Vector3, look: THREE.Vector3, centre: THREE.Vector3): void {
    const c = this.cue;
    const p = this.parts;
    if (!c || !p) return this.hide();
    const beats = c.look;
    const t = endSceneTime(c, now);
    endAt(beats, t, c.release, reduced, frame);
    if (frame.done) return this.hide();
    // the light drops toward the kind's colour (stronger at the screen's edges, the room falling away)
    const d = frame.dim;
    const [tr, tg, tb] = beats.tint;
    const k = beats.dim;
    // full dim multiplies the light by dim × tint; the middle of the screen keeps a third of what it loses
    p.shade.material.uniforms.shade!.value.setRGB(1 - d * (1 - k * tr) * CENTRE, 1 - d * (1 - k * tg) * CENTRE, 1 - d * (1 - k * tb) * CENTRE);
    p.shade.material.uniforms.edge!.value.setRGB(1 - d * (1 - k * tr * EDGE), 1 - d * (1 - k * tg * EDGE), 1 - d * (1 - k * tb * EDGE));
    p.shade.visible = d > 0.001;
    // the pulse: a ring that spreads from the middle of the table out over every battlefield
    const pulse = beats.pulse;
    p.pulse.visible = !!pulse && frame.pulse > 0.002;
    if (pulse && p.pulse.visible) {
      const { w, d: depth } = this.size();
      const s = 0.3 + 0.85 * frame.spread;
      p.pulse.scale.set(w * s, 1, depth * s);
      p.pulse.position.set(centre.x, 0.04, centre.z);
      p.pulse.material.opacity = frame.pulse;
    }
    // the motes: specks rising off the felt over the battlefields
    const m = beats.motes;
    let n = 0;
    if (m && !reduced) {
      const { w, d: depth } = this.size();
      color.set(m.color);
      for (let i = 0; i < Math.min(m.count, MAX_MOTES); i++) {
        moteAt(beats, i, t, frame.fade, reduced, mote);
        if (mote.alpha <= 0.002) continue;
        p.positions[n * 3] = centre.x + mote.x * w * 0.36;
        p.positions[n * 3 + 1] = 0.12 + mote.rise * m.rise * CARD_H;
        p.positions[n * 3 + 2] = centre.z + mote.z * depth * 0.3;
        // additive: a dimmer colour is a fainter mote
        const a = mote.alpha * mote.size;
        p.colors[n * 3] = color.r * a;
        p.colors[n * 3 + 1] = color.g * a;
        p.colors[n * 3 + 2] = color.b * a;
        n++;
      }
    }
    p.motes.visible = n > 0;
    if (n > 0) {
      p.motes.geometry.setDrawRange(0, n);
      p.motes.geometry.attributes.position!.needsUpdate = true;
      p.motes.geometry.attributes.color!.needsUpdate = true;
    }
    // the camera eases along its line of sight: a small push in (victory), a small pull back (defeat)
    if (frame.push !== 0 || frame.lift !== 0) {
      offset.copy(cam).sub(look);
      const dist = offset.length();
      cam.copy(look).addScaledVector(offset, 1 - frame.push);
      cam.y += frame.lift * dist;
    }
  }

  dispose(): void {
    const p = this.parts;
    if (!p) return;
    this.scene.remove(p.shade, p.pulse, p.motes);
    p.shade.geometry.dispose();
    p.shade.material.dispose();
    p.pulse.geometry.dispose();
    p.pulse.material.map?.dispose();
    p.pulse.material.dispose();
    p.motes.geometry.dispose();
    p.motes.material.map?.dispose();
    p.motes.material.dispose();
    this.parts = null;
  }

  private hide(): void {
    this.active = false;
    const p = this.parts;
    if (!p) return;
    p.shade.visible = false;
    p.pulse.visible = false;
    p.motes.visible = false;
  }

  /** The three parts, made on the first scene of this table and kept (hidden) for the next. */
  private build(): void {
    const cue = this.cue;
    if (!this.parts) {
      const tri = new THREE.BufferGeometry();
      tri.setAttribute("position", new THREE.Float32BufferAttribute([-1, -1, 0, 3, -1, 0, -1, 3, 0], 3));
      const shade = new THREE.Mesh(tri, new THREE.ShaderMaterial({
        uniforms: { shade: { value: new THREE.Color(1, 1, 1) }, edge: { value: new THREE.Color(1, 1, 1) } },
        vertexShader: SHADE_VERT, fragmentShader: SHADE_FRAG,
        // a multiply: result = this colour × what is drawn (alpha kept)
        blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.DstColorFactor, blendDst: THREE.ZeroFactor,
        blendSrcAlpha: THREE.ZeroFactor, blendDstAlpha: THREE.OneFactor,
        transparent: true, depthTest: false, depthWrite: false,
      }));
      shade.frustumCulled = false;
      shade.renderOrder = 30;
      const plane = new THREE.PlaneGeometry(1, 1);
      plane.rotateX(-Math.PI / 2);
      const pulse = new THREE.Mesh(plane, new THREE.MeshBasicMaterial({ map: ringTexture(), transparent: true, depthTest: false, depthWrite: false, opacity: 0 }));
      pulse.position.y = 0.04;
      pulse.frustumCulled = false;
      pulse.renderOrder = 31;
      const positions = new Float32Array(MAX_MOTES * 3);
      const colors = new Float32Array(MAX_MOTES * 3);
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
      geo.setAttribute("color", new THREE.BufferAttribute(colors, 3).setUsage(THREE.DynamicDrawUsage));
      geo.setDrawRange(0, 0);
      const motes = new THREE.Points(geo, new THREE.PointsMaterial({
        size: 0.3, map: dotTexture(), vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true,
      }));
      motes.frustumCulled = false;
      motes.renderOrder = 32;
      this.scene.add(shade, pulse, motes);
      this.parts = { shade, pulse, motes, positions, colors };
    }
    const p = this.parts;
    const pulse = cue?.look.pulse;
    if (pulse) {
      p.pulse.material.color.set(pulse.color);
      // light adds to the table; a dark pulse is a shadow passing over it
      p.pulse.material.blending = pulse.light ? THREE.AdditiveBlending : THREE.NormalBlending;
    }
    this.hide();
    this.active = true;
  }
}
