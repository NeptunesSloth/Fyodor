/**
 * High-quality post-processing for the 3D table: a multisampled render, tone mapping, then one
 * cheap pass that darkens the room toward the screen edges and gives a slight warm grade, so the
 * table sits in a pool of light. Medium and low render directly (no composer at all).
 *
 * Everything comes from three's own examples/jsm: no extra dependency.
 */
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";

const VignetteGrade = {
  name: "VignetteGrade",
  uniforms: {
    tDiffuse: { value: null as THREE.Texture | null },
    strength: { value: 0.55 },
    warmth: { value: 0.035 },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform float strength;
    uniform float warmth;
    varying vec2 vUv;
    void main() {
      vec4 c = texture2D(tDiffuse, vUv);
      vec2 d = (vUv - 0.5) * vec2(1.25, 1.0);
      float v = smoothstep(0.85, 0.25, length(d));
      c.rgb *= mix(1.0 - strength, 1.0, v);
      c.rgb += vec3(warmth, warmth * 0.45, -warmth * 0.4) * (1.0 - v);
      gl_FragColor = vec4(max(c.rgb, 0.0), c.a);
    }`,
};

export interface Post {
  render(): void;
  setSize(w: number, h: number): void;
  dispose(): void;
}

export function createPost(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.Camera): Post {
  const size = renderer.getDrawingBufferSize(new THREE.Vector2());
  const target = new THREE.WebGLRenderTarget(size.x, size.y, { type: THREE.HalfFloatType, samples: 4 });
  const composer = new EffectComposer(renderer, target);
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(new OutputPass()); // tone mapping + sRGB, as the direct render would do
  const grade = new ShaderPass(VignetteGrade);
  composer.addPass(grade);
  return {
    render: () => composer.render(),
    setSize: (w, h) => {
      composer.setPixelRatio(renderer.getPixelRatio());
      composer.setSize(w, h);
    },
    dispose: () => {
      grade.dispose();
      composer.dispose();
    },
  };
}
