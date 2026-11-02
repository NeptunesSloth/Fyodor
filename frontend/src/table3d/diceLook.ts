/**
 * What the dice are made of (Settings → Dice): glossy resin (the default), a marble swirl, enamelled metal, or a
 * gemstone. Every player's dice take their seat colour; the ink in the engraving is ivory or near-black, whichever
 * reads better on that colour. One physical material per look, colour and kind of die, built on three's
 * MeshPhysicalMaterial with a small shader patch: the ink comes from the atlas's alpha (table3d/diceArt.ts), the
 * swirl is solid noise in the die's own space (so it runs over edges and corners unbroken), and a die the rules
 * ignored is drawn greyed and darker. Materials are cached per tray and disposed with it.
 */
import * as THREE from "three";

import type { DiceLook } from "../game/dice";

export type { DiceLook } from "../game/dice";

const IVORY = new THREE.Color("#f4ecdc");
const SOOT = new THREE.Color("#17120d");

/** WCAG relative luminance of a linear colour. */
function luminance(c: THREE.Color): number {
  return 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
}
const contrast = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);

/** The body colour a seat's dice are cast in (a little deeper than the seat colour, so it reads as resin). */
export function bodyColor(seat: string, look: DiceLook): THREE.Color {
  const c = new THREE.Color(seat);
  const hsl = { h: 0, s: 0, l: 0 };
  // in sRGB terms, as the seat colour was chosen
  c.getHSL(hsl, THREE.SRGBColorSpace);
  const set = (s: number, l: number) => c.setHSL(hsl.h, Math.max(0, Math.min(1, s)), Math.max(0, Math.min(1, l)), THREE.SRGBColorSpace);
  if (look === "metal") return set(hsl.s * 0.7, 0.62);
  if (look === "gem") return set(hsl.s * 1.1 + 0.15, 0.5);
  if (look === "marble") return set(hsl.s * 1.05 + 0.08, 0.4);
  return set(hsl.s * 1.1 + 0.12, 0.42);
}

/** Ivory or soot ink, whichever has the stronger contrast against the body. */
export function inkFor(body: THREE.Color): THREE.Color {
  const l = luminance(body);
  return contrast(l, luminance(IVORY)) >= contrast(l, luminance(SOOT)) ? IVORY.clone() : SOOT.clone();
}

const NOISE = /* glsl */ `
varying vec3 vDiceObj;
uniform vec3 uDiceInk;
uniform vec3 uDiceTone;
uniform float uDiceDim;
uniform float uDiceSeed;
float dHash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float dNoise(vec3 x) {
  vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(dHash(i), dHash(i + vec3(1, 0, 0)), f.x), mix(dHash(i + vec3(0, 1, 0)), dHash(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(dHash(i + vec3(0, 0, 1)), dHash(i + vec3(1, 0, 1)), f.x), mix(dHash(i + vec3(0, 1, 1)), dHash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
float dFbm(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * dNoise(p); p = p * 2.03 + 1.7; a *= 0.5; } return s; }
`;

interface Spec { look: DiceLook; seat: string; ignored: boolean; atlas: THREE.Texture; envMap: THREE.Texture | null; transmission: boolean; seed: number }

/** One die material (see the module comment). */
export function diceMaterial(spec: Spec): THREE.MeshPhysicalMaterial {
  const body = bodyColor(spec.seat, spec.look);
  const ink = inkFor(body);
  const tone = body.clone().lerp(spec.look === "marble" ? IVORY : body.clone().multiplyScalar(0.55), spec.look === "marble" ? 0.72 : 1);
  const m = new THREE.MeshPhysicalMaterial({ color: body, normalMap: spec.atlas, normalScale: new THREE.Vector2(1, 1), envMap: spec.envMap, envMapIntensity: 1 });
  switch (spec.look) {
    case "resin":
      Object.assign(m, { roughness: 0.3, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.07, sheen: 0, specularIntensity: 0.7, envMapIntensity: 0.5 });
      break;
    case "marble":
      Object.assign(m, { roughness: 0.34, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.05, envMapIntensity: 0.5 });
      break;
    case "metal":
      Object.assign(m, { roughness: 0.3, metalness: 1, clearcoat: 0, envMapIntensity: 1.0 });
      break;
    case "gem":
      if (spec.transmission) {
        Object.assign(m, { roughness: 0.04, metalness: 0, transmission: 1, thickness: 0.7, ior: 1.6, attenuationColor: body.clone(), attenuationDistance: 0.55, specularIntensity: 1, envMapIntensity: 1.4, color: body.clone().lerp(IVORY, 0.55) });
      } else {
        // no transmission pass (medium and low graphics): a deep, glossy translucent-looking stone
        Object.assign(m, { roughness: 0.06, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.02, iridescence: 0.35, iridescenceIOR: 1.6, specularIntensity: 1, envMapIntensity: 1.6, color: body.clone().multiplyScalar(0.8) });
      }
      break;
  }
  const uniforms = {
    uDiceInk: { value: ink.clone() },
    uDiceTone: { value: tone },
    uDiceDim: { value: spec.ignored ? 1 : 0 },
    uDiceSeed: { value: spec.seed },
  };
  const marble = spec.look === "marble";
  const gem = spec.look === "gem" && spec.transmission;
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, uniforms);
    sh.vertexShader = sh.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vDiceObj;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvDiceObj = position;");
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <common>", `#include <common>\n${NOISE}`)
      .replace("#include <map_fragment>", /* glsl */ `
        float diceInk = texture2D(normalMap, vNormalMapUv).a;
        ${marble ? `
        vec3 mp = vDiceObj * 2.6 + uDiceSeed;
        float sw = dFbm(mp + 1.8 * vec3(dFbm(mp * 0.9), dFbm(mp * 0.9 + 4.1), dFbm(mp * 0.9 + 8.3)));
        float band = smoothstep(0.38, 0.62, sw);
        float vein = 1.0 - smoothstep(0.0, 0.035, abs(sw - 0.5));
        diffuseColor.rgb = mix(diffuseColor.rgb, uDiceTone, band * 0.85);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(1.0, 0.97, 0.9), vein * 0.55);` : ""}
        diffuseColor.rgb = mix(diffuseColor.rgb, uDiceInk, diceInk);
        if (uDiceDim > 0.5) {
          float grey = dot(diffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722));
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(grey), 0.8) * 0.55;
        }`)
      .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.62, diceInk);")
      .replace("#include <metalnessmap_fragment>", "#include <metalnessmap_fragment>\nmetalnessFactor = mix(metalnessFactor, 0.0, diceInk);");
    if (gem) {
      sh.fragmentShader = sh.fragmentShader.replace("#include <transmission_fragment>",
        THREE.ShaderChunk.transmission_fragment.replace("material.transmission = transmission;", "material.transmission = transmission * (1.0 - diceInk) * (1.0 - 0.7 * uDiceDim);"));
    }
    sh.fragmentShader = sh.fragmentShader.replace("#include <lights_physical_fragment>",
      THREE.ShaderChunk.lights_physical_fragment.replace("material.clearcoat = clearcoat;", "material.clearcoat = clearcoat * (1.0 - 0.6 * diceInk);"));
  };
  m.customProgramCacheKey = () => `dice-${spec.look}${gem ? "-tx" : ""}`;
  m.userData.diceUniforms = uniforms;
  return m;
}

/** The coin: brass struck in relief, the sunk field enamelled in the seat colour, a milled edge. */
export function coinMaterial(seat: string, atlas: THREE.Texture, envMap: THREE.Texture | null, ignored: boolean): THREE.MeshPhysicalMaterial {
  const enamel = bodyColor(seat, "resin");
  const m = new THREE.MeshPhysicalMaterial({ color: new THREE.Color("#c9a35c"), metalness: 1, roughness: 0.28, normalMap: atlas, normalScale: new THREE.Vector2(1, 1), envMap, envMapIntensity: 1.3 });
  const uniforms = { uDiceInk: { value: enamel }, uDiceTone: { value: enamel }, uDiceDim: { value: ignored ? 1 : 0 }, uDiceSeed: { value: 0 } };
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, uniforms);
    sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vDiceObj;").replace("#include <begin_vertex>", "#include <begin_vertex>\nvDiceObj = position;");
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <common>", `#include <common>\n${NOISE}`)
      .replace("#include <map_fragment>", /* glsl */ `
        float diceInk = texture2D(normalMap, vNormalMapUv).a;
        diffuseColor.rgb = mix(diffuseColor.rgb, uDiceInk, diceInk);
        if (uDiceDim > 0.5) { float grey = dot(diffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722)); diffuseColor.rgb = mix(diffuseColor.rgb, vec3(grey), 0.8) * 0.55; }`)
      .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.4, diceInk);")
      .replace("#include <metalnessmap_fragment>", "#include <metalnessmap_fragment>\nmetalnessFactor = mix(metalnessFactor, 0.0, diceInk);");
  };
  m.customProgramCacheKey = () => "dice-coin";
  return m;
}
