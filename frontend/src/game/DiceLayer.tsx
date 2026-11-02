import { useState } from "react";
import { useGame } from "../state/gameStore";
import { DICE_HOLD_MS, DICE_SHOWN, rollSummary, useDiceFeed, type DiceShow } from "./dice";

interface Shown extends DiceShow { x: number; y: number; fx: number; fy: number; color: string; name: string }

const SHAPE: Record<number, string> = { 4: "d4", 6: "d6", 8: "d8", 10: "d10", 12: "d12", 100: "d10" };

/**
 * The 2D table's dice (game/dice.ts): each roll tumbles from the roller's plaque onto the middle of their mat and
 * rests there, numbers up, with the total under it, then fades. Everyone at the table sees it.
 */
export function DiceLayer() {
  const [rolls, setRolls] = useState<Shown[]>([]);
  useDiceFeed((r) => {
    const view = useGame.getState().view;
    const who = view?.players.find((p) => p.id === r.actor);
    const mat = document.querySelector(`[data-drop="${r.actor}:battlefield"]`)?.getBoundingClientRect();
    const plaque = document.querySelector(`.seat-2d[data-player-id="${r.actor}"]`)?.getBoundingClientRect();
    const x = mat ? mat.left + mat.width / 2 : window.innerWidth / 2;
    const y = mat ? mat.top + mat.height / 2 : window.innerHeight / 2;
    const fx = plaque ? plaque.left + plaque.width / 2 - x : -160;
    const fy = plaque ? plaque.top + plaque.height / 2 - y : 120;
    const shown: Shown = { ...r, x, y, fx, fy, color: who?.color ?? "#d7ae63", name: who?.name ?? "" };
    setRolls((all) => [...all, shown]);
    window.setTimeout(() => setRolls((all) => all.filter((s) => s !== shown)), 1100 + DICE_HOLD_MS + 700);
  });
  if (!rolls.length) return null;
  return (
    <div className="dice-layer" aria-hidden>
      {rolls.map((r) => (
        <div key={r.key} className="dice-throw" style={{ left: r.x, top: r.y, ["--seat" as string]: r.color }} data-testid="dice-throw">
          <div className="dice-row">
            {r.results.slice(0, DICE_SHOWN).map((v, i) => (
              <span key={i} className={`die2d-wrap${r.ignored?.includes(i) ? " ignored" : ""}`} title={r.ignored?.includes(i) ? "Ignored (the rules ignore this roll)" : undefined} style={{ ["--i" as string]: i, ["--fx" as string]: `${r.fx}px`, ["--fy" as string]: `${r.fy}px` }}>
                <span className={`die2d ${r.coin ? "coin" : SHAPE[r.sides] ?? "d20"}`}>{r.coin ? (v ? "H" : "T") : v}</span>
              </span>
            ))}
          </div>
          <span className="dice-total">
            {r.name} · {r.coin ? (r.results.length > 1 ? `${r.results.length} coins` : "coin") : `${r.results.length - (r.ignored?.length ?? 0) > 1 ? r.results.length - (r.ignored?.length ?? 0) : ""}d${r.sides}`}: <b>{rollSummary(r)}</b>
          </span>
        </div>
      ))}
    </div>
  );
}
