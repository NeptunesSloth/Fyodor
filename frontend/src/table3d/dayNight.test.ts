import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { DayNightLight, easeInOut, mixAt, NIGHT, nightIntensity } from "./dayNight";
import { dayNightMoment } from "../game/dayNight";
import type { Environment } from "./environment";

function env(): Environment {
  return {
    group: new THREE.Group(),
    tableY: 0,
    update() {},
    dispose() {},
    lights: {
      hemi: new THREE.HemisphereLight("#ffeedd", "#332211", 1),
      key: new THREE.DirectionalLight("#fff4e0", 2),
      pool: new THREE.PointLight("#ffbb77", 10),
      rim: new THREE.DirectionalLight("#ffffff", 1),
    },
  };
}

describe("day and night: the moment", () => {
  it("marks a change to day or night, in the rules' words", () => {
    expect(dayNightMoment(null, "day")).toEqual({ to: "day", from: null, line: "It becomes day" });
    expect(dayNightMoment("day", "night")).toEqual({ to: "night", from: "day", line: "It becomes night" });
    expect(dayNightMoment("night", "day")?.line).toBe("It becomes day");
  });
  it("shows nothing when nothing changed or day and night ended", () => {
    expect(dayNightMoment("night", "night")).toBeNull();
    expect(dayNightMoment("night", null)).toBeNull();
    expect(dayNightMoment(null, null)).toBeNull();
  });
});

describe("day and night: the 3D room's light", () => {
  it("eases in and out between the ends", () => {
    expect(easeInOut(0)).toBe(0);
    expect(easeInOut(1)).toBe(1);
    expect(easeInOut(0.5)).toBeCloseTo(0.5);
    expect(easeInOut(0.25)).toBeLessThan(0.25);
    expect(mixAt(0, 1, 100, 1000, 100)).toBe(0);
    expect(mixAt(0, 1, 100, 1000, 1100)).toBe(1);
    expect(mixAt(1, 0, 0, 0, 0)).toBe(0);
    expect(nightIntensity(2, 0.8, 1)).toBeCloseTo(1.6);
    expect(nightIntensity(2, 0.8, 0)).toBe(2);
  });

  it("a table loading at night is night at once; a change turns over the duration, then rests", () => {
    const e = env();
    const d = new DayNightLight();
    d.attach(e);
    d.set("night", 0, 0);
    expect(d.active).toBe(false);
    expect(e.lights.key.intensity).toBeCloseTo(2 * NIGHT.key);
    expect(e.lights.pool.intensity).toBeCloseTo(10 * NIGHT.pool);
    expect(e.lights.key.color.b).toBeGreaterThan(e.lights.key.color.r - 0.2); // cooler
    d.set("day", 1000, 0);
    expect(d.active).toBe(true);
    d.update(500, false);
    expect(e.lights.key.intensity).toBeGreaterThan(2 * NIGHT.key);
    expect(e.lights.key.intensity).toBeLessThan(2);
    d.update(1000, false);
    expect(d.active).toBe(false);
    expect(e.lights.key.intensity).toBe(2);
    expect(e.lights.key.color.getHexString()).toBe(new THREE.Color("#fff4e0").getHexString());
  });

  it("a rebuilt room keeps the night; reduced motion and a skip jump to the end", () => {
    const d = new DayNightLight();
    d.attach(env());
    d.set("night", 1000, 0);
    d.update(100, true);
    expect(d.active).toBe(false);
    const fresh = env();
    d.attach(fresh);
    expect(fresh.lights.hemi.intensity).toBeCloseTo(NIGHT.hemi);
    expect(fresh.lights.rim.intensity).toBeCloseTo(NIGHT.rim);
    d.set(null, 1000, 0);
    d.finish();
    expect(d.active).toBe(false);
    expect(fresh.lights.hemi.intensity).toBe(1);
  });
});
