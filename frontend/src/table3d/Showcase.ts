/** The launcher's backdrop: the selected plane's table, slowly circled by the camera. */
import * as THREE from "three";
import type { PlaneTheme } from "../theme/planes";
import { buildEnvironment, type Environment } from "./environment";
import { CARD_H, CARD_W } from "./layout";
import { backCanvas, canvasTexture, textCardCanvas } from "./textures";

export class Showcase {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(38, 1, 0.1, 400);
  private env: Environment | null = null;
  private props = new THREE.Group();
  private raf = 0;
  private clock = new THREE.Clock();
  private disposables: { dispose(): void }[] = [];

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
    // a few cards mid-game: a small battlefield, a library and a fanned hand
    const geo = new THREE.PlaneGeometry(CARD_W, CARD_H);
    geo.rotateX(-Math.PI / 2);
    this.disposables.push(geo);
    const back = new THREE.MeshStandardMaterial({ map: canvasTexture(backCanvas(plane.ui.accent)), roughness: 0.6 });
    this.disposables.push(back);
    const names = ["Sol Ring", "Command Tower", "Arcane Signet", "Swords to Plowshares", "Counterspell", "Lightning Bolt"];
    const colors = [[], [], [], ["W"], ["U"], ["R"]];
    names.forEach((name, i) => {
      const card = { name, type_line: i < 3 ? "Artifact" : "Instant", colors: colors[i], mana_cost: "", oracle_text: "" };
      const mat = new THREE.MeshStandardMaterial({ map: canvasTexture(textCardCanvas(card as never, 0, name)), roughness: 0.5 });
      this.disposables.push(mat);
      const m = new THREE.Mesh(geo, mat);
      m.position.set(-3.2 + i * 1.25, 0.01, 4 + (i % 2) * 0.2);
      m.rotation.y = i === 1 ? -Math.PI / 2 : (i - 2.5) * 0.02;
      this.props.add(m);
    });
    for (let i = 0; i < 40; i++) {
      const m = new THREE.Mesh(geo, back);
      m.position.set(5.6, 0.01 + i * 0.012, 4.2);
      this.props.add(m);
    }
    for (let i = 0; i < 7; i++) {
      const m = new THREE.Mesh(geo, back);
      const t = i / 6 - 0.5;
      m.position.set(t * 2.6, 0.02 + i * 0.004, -6 + Math.abs(t) * 0.3);
      m.rotation.y = Math.PI - t * 0.5;
      this.props.add(m);
    }
  }

  resize(w: number, h: number): void {
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / Math.max(1, h);
    this.camera.updateProjectionMatrix();
  }

  dispose(): void {
    cancelAnimationFrame(this.raf);
    this.env?.dispose();
    for (const d of this.disposables) d.dispose();
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
