/**
 * The launcher's backdrop: the selected plane's table, slowly circled by the camera, mid-game. The pod's latest
 * commanders lie on the near mat in their real art from the host's cache (a text card if one's art isn't cached),
 * beside a library; across the table a fanned hand. Every back is the host's Magic card back (the drawn one until
 * it has it), and every card is trimmed to a card's rounded corners.
 */
import * as THREE from "three";
import { CARD_BACK_URL, checkCardBack, onCardBack } from "../cards/cardBack";
import { imageUrl } from "../services/cards";
import type { PlaneTheme } from "../theme/planes";
import { buildEnvironment, type Environment } from "./environment";
import { CARD_H, CARD_W } from "./layout";
import { backCanvas, canvasTexture, cardCornerMask, cardImageTexture, matTexture, textCardTexture } from "./textures";

/** A card to lay on the showcase's mat: a printing (its art from the host's cache) and its name (the text card's). */
export interface ShowcaseCard { id: string; name: string }

const PILE_H = 0.42;

function roundedCard(w: number, h: number, r: number): THREE.Shape {
  const s = new THREE.Shape();
  s.moveTo(-w / 2 + r, -h / 2);
  s.lineTo(w / 2 - r, -h / 2);
  s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  s.lineTo(w / 2, h / 2 - r);
  s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  s.lineTo(-w / 2 + r, h / 2);
  s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  s.lineTo(-w / 2, -h / 2 + r);
  s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  return s;
}

export class Showcase {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(38, 1, 0.1, 400);
  private env: Environment | null = null;
  private props = new THREE.Group();
  private raf = 0;
  private clock = new THREE.Clock();
  private disposables: { dispose(): void }[] = [];
  /** Bumped by every plane change and by dispose: a card back that arrives for an older scene is dropped. */
  private generation = 0;
  private unwatch: (() => void) | null = null;
  private cards: ShowcaseCard[] = [];
  private battlefield = new THREE.Group();
  private battlefieldTrash: { dispose(): void }[] = [];
  private cardGeo: THREE.PlaneGeometry | null = null;

  constructor(private host: HTMLElement, plane: PlaneTheme) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "low-power" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.35;
    this.renderer.shadowMap.enabled = true;
    this.renderer.domElement.className = "showcase-canvas";
    host.appendChild(this.renderer.domElement);
    this.scene.add(this.props);
    this.setPlane(plane);
    this.loop();
  }

  setPlane(plane: PlaneTheme): void {
    if (this.env) {
      this.scene.remove(this.env.group);
      this.env.dispose();
    }
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
    this.props.clear();
    this.scene.fog = new THREE.Fog(plane.env.fog, 30, 95);
    this.scene.background = new THREE.Color(plane.env.skyBottom);
    this.env = buildEnvironment(plane, { w: 30, d: 24 }, "medium");
    this.scene.add(this.env.group);
    // two seats' playmats, so the launcher shows the same cloth as the game table
    for (const [z, rot] of [[4.2, 0], [-6, Math.PI]] as const) {
      const matTex = matTexture(plane.env.felt, plane.env.feltNap, plane.ui.accent);
      const matMat = new THREE.MeshStandardMaterial({ map: matTex, transparent: true, depthWrite: false, roughness: 1, envMapIntensity: 0.15 });
      const matGeo = new THREE.PlaneGeometry(10.5, 6.5);
      this.disposables.push(matTex, matMat, matGeo);
      const m = new THREE.Mesh(matGeo, matMat);
      m.rotation.set(-Math.PI / 2, 0, rot);
      m.position.set(0, 0.004, z);
      m.receiveShadow = true;
      this.props.add(m);
    }
    // a few cards mid-game: the pod's commanders on the near mat, a library beside them, a fanned hand across the table
    const geo = new THREE.PlaneGeometry(CARD_W, CARD_H);
    geo.rotateX(-Math.PI / 2);
    this.cardGeo = geo;
    this.disposables.push(geo);
    const back = new THREE.MeshStandardMaterial({ map: canvasTexture(backCanvas()), roughness: 0.6, alphaMap: cardCornerMask(), alphaTest: 0.5 });
    this.disposables.push(back, back.map!);
    this.useRealBack(back);
    this.props.add(this.battlefield);
    this.layCards();
    // the library: a block of card stock with the back on top
    const body = new THREE.ExtrudeGeometry(roundedCard(CARD_W, CARD_H, 0.045), { depth: PILE_H, bevelEnabled: false, curveSegments: 6 });
    body.rotateX(-Math.PI / 2);
    const bodyMat = new THREE.MeshStandardMaterial({ color: "#4b4741", roughness: 0.85 }); // a deck's edge: dark card stock
    this.disposables.push(body, bodyMat);
    const pile = new THREE.Mesh(body, bodyMat);
    pile.position.set(5.6, 0.004, 4.2);
    pile.castShadow = pile.receiveShadow = true;
    const top = new THREE.Mesh(geo, back);
    top.position.set(5.6, PILE_H + 0.006, 4.2);
    this.props.add(pile, top);
    for (let i = 0; i < 7; i++) {
      const m = new THREE.Mesh(geo, back);
      const t = i / 6 - 0.5;
      m.position.set(t * 2.6, 0.02 + i * 0.006, -6 + Math.abs(t) * 0.3);
      m.rotation.y = Math.PI - t * 0.5;
      this.props.add(m);
    }
  }

  /** The cards to lay on the near mat (the pod's latest commanders): up to five, in their art when the host has it. */
  setCards(cards: ShowcaseCard[]): void {
    this.cards = cards.slice(0, 5);
    this.layCards();
  }

  private layCards(): void {
    for (const d of this.battlefieldTrash) d.dispose();
    this.battlefieldTrash = [];
    this.battlefield.clear();
    const geo = this.cardGeo;
    if (!geo) return;
    const gen = this.generation;
    const n = this.cards.length;
    this.cards.forEach((card, i) => {
      // a text card until (or unless) its art comes from the host's cache
      const mat = new THREE.MeshStandardMaterial({ map: textCardTexture(undefined, 0, card.name), roughness: 0.5, alphaMap: cardCornerMask(), alphaTest: 0.5 });
      this.battlefieldTrash.push(mat, mat.map!);
      cardImageTexture(imageUrl(card.id), undefined, (tex) => {
        if (gen !== this.generation || !this.battlefield.children.some((c) => (c as THREE.Mesh).material === mat)) return void tex.dispose();
        tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
        mat.map = tex;
        mat.needsUpdate = true;
        this.battlefieldTrash.push(tex);
      });
      const m = new THREE.Mesh(geo, mat);
      const x = (i - (n - 1) / 2) * 1.32 - 0.6;
      m.position.set(x, 0.01, 4 + (i % 2) * 0.18);
      // the second one tapped, the others squared by hand
      m.rotation.y = n > 2 && i === 1 ? -Math.PI / 2 : (i - (n - 1) / 2) * 0.025;
      m.castShadow = true;
      this.battlefield.add(m);
    });
  }

  /** The Magic card back once the host has it (cards/cardBack.ts), as on the game table; the drawn one until then. */
  private useRealBack(back: THREE.MeshStandardMaterial): void {
    const gen = ++this.generation;
    const load = () => {
      if (gen !== this.generation || !checkCardBack.ready()) return;
      cardImageTexture(CARD_BACK_URL, undefined, (tex) => {
        if (gen !== this.generation) return void tex.dispose();
        tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
        back.map = tex;
        back.needsUpdate = true;
        this.disposables.push(tex);
      });
    };
    this.unwatch?.();
    this.unwatch = onCardBack(load);
    void checkCardBack().then(load);
  }

  resize(w: number, h: number): void {
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / Math.max(1, h);
    this.camera.updateProjectionMatrix();
  }

  dispose(): void {
    cancelAnimationFrame(this.raf);
    this.generation++;
    this.unwatch?.();
    this.env?.dispose();
    for (const d of [...this.disposables, ...this.battlefieldTrash]) d.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
    void this.host;
  }

  private loop = (): void => {
    this.raf = requestAnimationFrame(this.loop);
    const t = this.clock.getElapsedTime();
    const a = 0.35 + Math.sin(t * 0.05) * 0.35;
    this.camera.position.set(Math.sin(a) * 19, 11.5, Math.cos(a) * 19);
    this.camera.lookAt(-2, 0, 1);
    this.env?.update(t);
    this.renderer.render(this.scene, this.camera);
  };
}
