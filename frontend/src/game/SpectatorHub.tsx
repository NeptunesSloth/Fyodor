import { useCallback, useState } from "react";
import { SPECTATOR, type GameView } from "../types/game";
import { DamageSandbox } from "./DamageSandbox";
import { NextGameDialog } from "./NextGame";
import { PredictionsDialog } from "./Predictions";
import "./elimination.css";

/*
 * Spectator side activities (docs/SPECTATOR_ACTIVITIES_MILESTONE.md), shared by the elimination hub (players who are out)
 * and spectators: the damage sandbox, predictions and the next-game queue. They extend the elimination hub; they are not
 * a second one. Each is a dialog over the live table, which keeps updating underneath, and none of them sends a game action.
 */

export type SideActivity = "sandbox" | "predictions" | "next";

/** The dialog for one activity. `viewer`: the seat, at a hot-seat table. */
export function SideActivityDialog({ activity, view, viewer, onClose }: {
  activity: SideActivity | null;
  view: GameView;
  viewer?: string;
  onClose: () => void;
}) {
  const id = view.game.id;
  const result = view.game.night?.result;
  if (activity === "sandbox") return <DamageSandbox gameId={id} viewer={viewer} onClose={onClose} />;
  if (activity === "predictions") {
    return <PredictionsDialog gameId={id} spectator={view.viewer === SPECTATOR} onClose={onClose}
      resultKey={`${view.game.night?.number ?? 1}:${result ? "over" : "on"}`} />;
  }
  if (activity === "next") return <NextGameDialog gameId={id} onClose={onClose} />;
  return null;
}

/** Predictions and the next-game queue need seat tokens: LAN tables only (a hot-seat table has neither). */
export const lanOnly = (view: GameView) => view.game.mode === "lan";

/**
 * A spectator's way in: a small pill under the top bar, opening a compact hub (watching stays the main thing). Gone once
 * the game has a result, when the result and the rematch vote take over.
 */
export function SpectatorHub({ view }: { view: GameView }) {
  const [open, setOpen] = useState(false);
  const [activity, setActivity] = useState<SideActivity | null>(null);
  const close = useCallback(() => setActivity(null), []);
  if (view.viewer !== SPECTATOR || view.game.mode !== "lan" || view.game.practice) return null;
  const over = !!view.game.night?.result;
  const start = (what: SideActivity) => {
    setOpen(false);
    setActivity(what);
  };
  return (
    <>
      {!over && !activity && !open && (
        <button className="night-pill tt-btn" data-testid="spectator-pill" onClick={() => setOpen(true)}
          title="Damage sandbox, predictions, your deck for the next game">
          Watching · Things to do
        </button>
      )}
      {open && !over && (
        <div className="night-result plaque-wrap" data-testid="spectator-hub">
          <div className="plaque night-result-body">
            <div className="night-result-head">
              <span className="night-result-word winner">Spectating</span>
              <span className="night-result-line">You see what everyone at the table sees.</span>
            </div>
            <div className="night-actions">
              <button className="tt-btn" onClick={() => start("sandbox")} title="Try out a combat on the public board; the game never changes">Damage sandbox</button>
              <button className="tt-btn" onClick={() => start("predictions")} title="Fake points: who wins, who goes out next">Predictions</button>
              <button className="tt-btn" onClick={() => start("next")} title="Queue the deck you want to bring when you take a seat in the lobby">Next game</button>
              <button className="tt-btn brass" onClick={() => setOpen(false)}>Keep watching</button>
            </div>
          </div>
        </div>
      )}
      <SideActivityDialog activity={activity} view={view} onClose={close} />
    </>
  );
}
