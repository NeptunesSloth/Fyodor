import { beforeEach, expect, test, vi } from "vitest";
import { isSoftwareRendererName, softwareGraphicsDefault } from "./renderer";

const store = new Map<string, string>();
beforeEach(() => {
  store.clear();
  vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) });
});

test("software WebGL renderers are recognised, graphics cards are not", () => {
  expect(isSoftwareRendererName("ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)")).toBe(true);
  expect(isSoftwareRendererName("ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)")).toBe(true);
  expect(isSoftwareRendererName("llvmpipe (LLVM 15.0.7, 256 bits)")).toBe(true);
  expect(isSoftwareRendererName("ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)")).toBe(false);
  expect(isSoftwareRendererName("ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)")).toBe(false);
});

test("software WebGL switches to Low once per device; a later choice sticks", () => {
  expect(softwareGraphicsDefault("high", false)).toBeNull();
  expect(softwareGraphicsDefault("high", true)).toBe("low");
  expect(softwareGraphicsDefault("high", true)).toBeNull(); // (the player picked High again in Settings)
  store.clear();
  expect(softwareGraphicsDefault("low", true)).toBeNull();
});
