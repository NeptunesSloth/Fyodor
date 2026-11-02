import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { GameView } from "../types/game";
import { dieSolid, tilt } from "./diceGeometry";
import { rollerEnv } from "./diceEnv";
import { throwRoll } from "./diceThrow";
import { CARD_H, CARD_W, PILES } from "./layout";
import { poseAt } from "./physics";

/** A view with p1's library and a battlefield of n cards in rows, every third tapped. */
function view(n: number): GameView {
  const ids = Array.from({ length: n }, (_, i) => `c${i}`);
  const cards = Object.fromEntries(ids.map((id, i) => [id, { id, owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false, x: 20 + (i % 9) * 105, y: 30 + Math.floor(i / 9) * 140, tapped: i % 3 === 0 }]));
  return { zones: { "p1:battlefield": ids, "p1:library": { count: 60, known: [] }, "p1:graveyard": [] }, cards } as unknown as GameView;
}

describe("the world a roll is thrown into", () => {
  it("stands the roller's piles and lays their cards on their mat, from the public view (the same on every screen)", () => {
    const env = rollerEnv(view(3), "p1");
    const deck = env.obstacles.find((o) => o.x === PILES.library[0] && o.z === PILES.library[1])!;
    expect(deck.h).toBeGreaterThan(0.5); // 60 cards
    expect(env.obstacles.filter((o) => o.h < 0.1)).toHaveLength(3); // the cards: thin slabs
    const tapped = env.obstacles.find((o) => o.h < 0.1)!;
    expect([tapped.w, tapped.d]).toEqual([CARD_H, CARD_W]);
    expect(rollerEnv(view(3), "p1")).toEqual(env);
  });

  it("lands dice flat on a crowded battlefield: on the felt or lying on a card", () => {
    const env = rollerEnv(view(27), "p1");
    for (const [sides, kind] of [[6, "d6"], [20, "d20"], [4, "d4"]] as const) {
      for (let k = 0; k < 6; k++) {
        const r = throwRoll({ key: `crowd:${sides}:${k}`, sides, results: [1, 2, 3], coin: false }, env);
        for (const d of r.dice) {
          const pos = new THREE.Vector3();
          const rot = new THREE.Quaternion();
          poseAt(d.track, d.track.count - 1, pos, rot);
          expect(tilt(dieSolid(kind), rot)).toBeLessThan(0.002);
          expect(pos.y - dieSolid(kind).inradius).toBeGreaterThan(-0.02);
          expect(pos.y - dieSolid(kind).inradius).toBeLessThan(0.12);
        }
      }
    }
  });
});
