/**
 * -- planechase -- the face-up plane on the 3D table (CR 901; the table's procedure: app/game/handlers/planechase.py). A landscape card
 * lying face up in the aisle between the rows (layout.ts planarSpot: on no mat, clear of the stack and of every heart and plate), its
 * picture loaded like any card's (textures.ts cardImageTexture) and turned the way the plaque turns it (game/planechase.ts
 * planarRotation: an upright scan a quarter clockwise, so its text reads left to right). Clicking it opens the plaque's full text
 * (game/PlanechasePlaque.tsx, through showPlanarText).
 *
 * Motion (docs/GAME_UI_MOTION_RESEARCH.md): a planeswalk slides the old plane off to the left as it fades while the new one turns over
 * onto the table; chaos pulses the plane (a brass glow and a small swell). Display only: the table already holds the new plane, the game
 * never waits, any click or key finishes it (TableScene: onMotionSkip), durations follow the player's animation speed (motionMs), and
 * reduced motion keeps only the fades and the glow. Stepped from the table's one frame loop; nothing runs while idle.
 */
import * as THREE from "three";
import { MOTION, motionMs, motionOn } from "../game/motion/timing";
import { planarRotation, planechaseCue } from "../game/planechase";
import { imageUrl } from "../services/cards";
import { requestCards, useCardCache } from "../state/cardCache";
import type { PlanarCardView, PlanechaseView } from "../types/game";
import { CARD_H, CARD_W } from "./layout";
import { cardCornerMask, cardImageTexture, contactShadowTexture, textCardTexture } from "./textures";

/** One plane lying on the table: a holder (moved by the motion) with the card and its contact shadow. */
interface Face {
  id: string;
  holder: THREE.Group;
  card: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshStandardMaterial>;
  shadow: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>;
  /** How its picture is turned (planarRotation); "text": no picture, its text card lies upright instead. */
  turn: 0 | 90 | "text";
  /** Half its depth on the table (toward me): how high its near edge must ride while it turns over. */
  half: number;
}

interface Walk { from: Face | null; t0: number; dur: number; skipped: boolean }
interface Pulse { t0: number; dur: number; skipped: boolean }

const LIE = 0.008; // just over the felt (the cards on the mats lie at 0.004)
const GLOW = new THREE.Color("#c9a24f"); // the table's restrained brass
const SHADOW_OPACITY = 0.55;

const reducedNow = () => typeof document !== "undefined" && document.body.classList.contains("reduced-motion");
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

export class PlanarTable {
  readonly group = new THREE.Group();
  private geo = new THREE.PlaneGeometry(1, 1);
  private shadowTex = contactShadowTexture();
  private face: Face | null = null;
  private walk: Walk | null = null;
  private pulse: Pulse | null = null;
  private prev: PlanechaseView | null = null;
  private scale = 1.8;

  constructor() {
    this.group.name = "planar";
    this.group.visible = false;
  }

  /** Anything to step this frame. */
  get active(): boolean {
    return !!this.walk || !!this.pulse;
  }

  /**
   * A new view: where the plane lies (my frame turned by my seat's rotation, world units) and which plane it is; a planeswalk or a chaos
   * roll since the last view plays its motion (planechaseCue: nothing on first sight).
   */
  sync(pc: PlanechaseView | null | undefined, spot: { x: number; z: number; scale: number }, myRot: number, now: number): void {
    const before = this.prev;
    this.prev = pc ?? null;
    if (!pc) {
      this.finish();
      this.step(now);
      if (this.face) this.drop(this.face);
      this.face = null;
      this.group.visible = false;
      return;
    }
    this.group.visible = true;
    this.group.position.set(spot.x * Math.cos(myRot) + spot.z * Math.sin(myRot), 0, -spot.x * Math.sin(myRot) + spot.z * Math.cos(myRot));
    this.group.rotation.set(0, myRot, 0);
    if (spot.scale !== this.scale) {
      this.scale = spot.scale;
      if (this.face) this.shape(this.face);
    }
    const cue = planechaseCue(before, pc);
    const animate = !!cue && motionOn();
    if (!this.face || this.face.id !== pc.current.printing_id) {
      if (this.walk) { // (a planeswalk still playing: it ends now, the next one starts from here)
        this.walk.skipped = true;
        this.step(now);
      }
      const old = this.face;
      this.face = this.make(pc.current);
      if (old && animate && cue.walk) this.walk = { from: old, t0: now, dur: motionMs(MOTION.cardTravel + 160), skipped: false };
      else if (old) this.drop(old);
    }
    if (animate && cue.chaos) this.pulse = { t0: now, dur: motionMs(700, false), skipped: false };
    this.step(now);
  }

  /** Any click or key: the motion ends now. */
  finish(): void {
    if (this.walk) this.walk.skipped = true;
    if (this.pulse) this.pulse.skipped = true;
  }

  /** Step the motion (the table's frame loop). */
  update(now: number): void {
    if (this.active) this.step(now);
  }

  /** What a click can hit: the plane (its userData says so). */
  targets(): THREE.Object3D[] {
    return this.group.visible && this.face?.card.visible ? [this.face.card] : [];
  }

  dispose(): void {
    if (this.walk?.from) this.drop(this.walk.from);
    if (this.face) this.drop(this.face);
    this.walk = this.pulse = this.face = null;
    this.geo.dispose();
    this.shadowTex.dispose();
    this.group.removeFromParent();
  }

  // ------------------------------------------------------------------ the planes

  private make(card: PlanarCardView): Face {
    const mat = new THREE.MeshStandardMaterial({
      color: 0xffffff, roughness: 0.62, metalness: 0, transparent: true, alphaMap: cardCornerMask(), alphaTest: 0.02,
      emissive: GLOW, emissiveIntensity: 0,
    });
    const shadowMat = new THREE.MeshBasicMaterial({ map: this.shadowTex, transparent: true, opacity: SHADOW_OPACITY, depthWrite: false });
    const holder = new THREE.Group();
    const face: Face = { id: card.printing_id, holder, card: new THREE.Mesh(this.geo, mat), shadow: new THREE.Mesh(this.geo, shadowMat), turn: 90,
      half: (CARD_W * this.scale) / 2 };
    face.card.userData = { planar: true };
    face.card.position.y = LIE;
    face.shadow.position.y = LIE / 2;
    face.card.visible = face.shadow.visible = false; // (until its picture is in: an upright scan never shows unturned)
    holder.add(face.shadow, face.card);
    this.group.add(holder);
    const show = () => {
      if (this.face !== face && this.walk?.from !== face) return; // (gone meanwhile: drop disposed it)
      face.card.visible = face.shadow.visible = true;
      this.shape(face);
    };
    const text = () => {
      // no picture (offline, never downloaded): its name, type and text drawn as a card, lying upright (card data when it's in)
      requestCards([card.printing_id]);
      mat.map?.dispose();
      mat.map = textCardTexture(useCardCache.getState().cards[card.printing_id], 0, card.name);
      mat.needsUpdate = true;
      face.turn = "text";
      show();
    };
    mat.map = cardImageTexture(imageUrl(card.printing_id, 0, "normal"), text, (t) => {
      const img = t.image as { width: number; height: number };
      face.turn = planarRotation(img.width, img.height);
      show();
    });
    return face;
  }

  /**
   * Lay a plane flat, landscape: an upright scan (turn 90) is turned a quarter clockwise as seen from above (its left edge, where the
   * name runs, becomes the far edge); a landscape scan isn't turned; a text card lies upright, a little smaller (portrait).
   */
  private shape(face: Face): void {
    const s = this.scale;
    const [w, h, spin] = face.turn === 90 ? [CARD_W * s, CARD_H * s, -Math.PI / 2]
      : face.turn === 0 ? [CARD_H * s, CARD_W * s, 0]
      : [CARD_W * s * 0.8, CARD_H * s * 0.8, 0];
    for (const m of [face.card, face.shadow]) m.rotation.set(-Math.PI / 2, 0, spin); // (flat, its picture up; then the turn in its own plane)
    face.card.scale.set(w, h, 1);
    face.half = (spin ? w : h) / 2;
    face.shadow.scale.set(w * 1.18, h * 1.22, 1);
  }

  private drop(face: Face): void {
    face.holder.removeFromParent();
    face.card.material.map?.dispose();
    face.card.material.dispose();
    face.shadow.material.dispose();
  }

  // ------------------------------------------------------------------ the motion

  private step(now: number): void {
    const reduced = reducedNow();
    const face = this.face;
    const w = this.walk;
    if (w) {
      const t = w.skipped ? 1 : Math.min(1, Math.max(0, (now - w.t0) / Math.max(1, w.dur)));
      const out = Math.min(1, t * 1.6); // the old plane is off in the first part of the move
      if (w.from) {
        const slide = reduced ? 0 : easeOut(out) * CARD_H * this.scale * 1.1;
        w.from.holder.position.set(-slide, reduced ? 0 : Math.sin(out * Math.PI) * 0.12, 0);
        this.fade(w.from, 1 - out);
      }
      if (face) {
        const k = easeOut(Math.max(0, (t - 0.25) / 0.75)); // the new one turns over onto the table after it
        const angle = reduced ? 0 : (1 - k) * (Math.PI / 2 - 0.1); // (edge on, its face toward me, then flat: no back face to show)
        face.holder.rotation.x = angle;
        face.holder.position.y = reduced ? 0 : face.half * Math.sin(angle) + Math.sin(k * Math.PI) * 0.15; // (its near edge over the felt)
        this.fade(face, reduced ? k : Math.min(1, k * 2));
      }
      if (t >= 1) {
        if (w.from) this.drop(w.from);
        this.walk = null;
        if (face) this.rest(face);
      }
    }
    const p = this.pulse;
    if (p) {
      const t = p.skipped ? 1 : Math.min(1, Math.max(0, (now - p.t0) / Math.max(1, p.dur)));
      const swell = Math.sin(t * Math.PI); // up and back down
      if (face) {
        face.card.material.emissiveIntensity = 0.45 * swell;
        if (!reduced && !this.walk) face.holder.scale.setScalar(1 + 0.05 * swell);
      }
      if (t >= 1) {
        this.pulse = null;
        if (face && !this.walk) this.rest(face);
      }
    }
  }

  private fade(face: Face, o: number): void {
    face.card.material.opacity = o;
    face.shadow.material.opacity = SHADOW_OPACITY * o;
  }

  private rest(face: Face): void {
    face.holder.position.set(0, 0, 0);
    face.holder.rotation.set(0, 0, 0);
    face.holder.scale.setScalar(1);
    face.card.material.emissiveIntensity = 0;
    this.fade(face, 1);
  }
}
