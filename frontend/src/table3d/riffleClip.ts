/**
 * The library shuffle authored in Blender (packaging/blender/riffle.py → assets/riffle.glb): twelve card backs split,
 * bent under the thumbs and riffled together, then bridged and squared. It is a plain glTF clip (node transforms and
 * shape keys) played with three's own GLTFLoader and AnimationMixer: Blender is never needed at runtime. Loaded once,
 * when the 3D table starts; until it has loaded (or if it can't be), motion3d's drawn riffle plays instead. Display only.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import riffleUrl from "./assets/riffle.glb?url";

/** The material the script names for the cards' backs (the edges keep their own). */
const BACK = "FyodorCardBack";

export interface RiffleClip { scene: THREE.Group; clip: THREE.AnimationClip }

let loaded: RiffleClip | null = null;
let loading = false;

/** The clip, or null while it loads (the first call starts loading it). */
export function riffleClip(): RiffleClip | null {
  if (!loaded && !loading && typeof window !== "undefined") {
    loading = true;
    new GLTFLoader().load(riffleUrl, (gltf) => {
      const clip = gltf.animations[0];
      if (!clip) return;
      // glTF's texture rows run top-down; the table's card-back textures are flipped the other way (flipY): turn the
      // cards' UVs over once, here, so any back the table has drawn sits upright on them
      gltf.scene.traverse((o) => {
        const uv = (o as THREE.Mesh).isMesh ? (o as THREE.Mesh).geometry.getAttribute("uv") : undefined;
        if (!uv) return;
        for (let i = 0; i < uv.count; i++) uv.setY(i, 1 - uv.getY(i));
        uv.needsUpdate = true;
      });
      loaded = { scene: gltf.scene, clip };
    }, undefined, () => undefined); // (no file: the drawn riffle stays)
  }
  return loaded;
}

export interface RifflePlay { group: THREE.Group; mixer: THREE.AnimationMixer; duration: number; back: THREE.MeshStandardMaterial }

/** One playing copy for a library, its cards wearing the owner's back (geometry is shared with the loaded clip). */
export function playRiffle(c: RiffleClip, map: THREE.Texture | null): RifflePlay {
  const group = c.scene.clone(true);
  const back = new THREE.MeshStandardMaterial({ map, color: map ? 0xffffff : 0x2a1d14, roughness: 0.8, metalness: 0, envMapIntensity: 0.12 });
  group.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    const swap = (x: THREE.Material) => (x.name === BACK ? back : x);
    m.material = Array.isArray(m.material) ? m.material.map(swap) : swap(m.material);
  });
  const mixer = new THREE.AnimationMixer(group);
  const action = mixer.clipAction(c.clip);
  action.setLoop(THREE.LoopOnce, 1);
  action.clampWhenFinished = true;
  action.play();
  mixer.setTime(0);
  return { group, mixer, duration: c.clip.duration, back };
}

/** Pose a playing copy at progress p (0..1): the table's clock drives it, so speed, skip and catch-up all apply. */
export function poseRifflePlay(r: RifflePlay, p: number): void {
  r.mixer.setTime(Math.min(1, Math.max(0, p)) * r.duration);
}

export function endRifflePlay(r: RifflePlay): void {
  r.group.removeFromParent();
  r.mixer.stopAllAction();
  r.back.dispose();
}
