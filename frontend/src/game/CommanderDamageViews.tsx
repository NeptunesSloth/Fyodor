/**
 * Commander damage at a glance (TABLETOP_QOL_MILESTONE #6), from game/commanderDamage.ts: what a hovered commander
 * has dealt to each opponent (in the card inspector), and the whole table's matrix (opened from a seat plaque's
 * player panel). Public information only. Each player is named, never only coloured.
 */
import { useState } from "react";
import { useGame } from "../state/gameStore";
import type { PlayerView } from "../types/game";
import { commanderDealt, commanderMatrix, LETHAL_COMMANDER } from "./commanderDamage";

/** In the inspector, for a commander: "Commander damage dealt: Bob 8 · Cara 21". */
export function DealtNote({ commander }: { commander: string }) {
  const players = useGame((s) => s.view?.players);
  return players ? <DealtList players={players} commander={commander} /> : null;
}

export function DealtList({ players, commander }: { players: PlayerView[]; commander: string }) {
  const rows = commanderDealt(players, commander);
  if (!rows.length) return null;
  return (
    <div className="insp-note cmdr-dealt" data-testid="cmdr-dealt">
      <span className="cmdr-dealt-label">Commander damage dealt</span>
      {rows.map((r) => (
        <span key={r.player} className={`cmdr-dealt-row ${r.damage >= LETHAL_COMMANDER ? "lethal" : r.damage ? "" : "zero"}`}
          title={r.damage >= LETHAL_COMMANDER ? `${r.name}: ${r.damage}, lethal (21 or more)` : `${r.name}: ${r.damage}`}>
          <i className="cmdr-dealt-chip" style={{ ["--player-color" as string]: r.color }} aria-hidden>{r.name.slice(0, 1).toUpperCase()}</i>
          {r.name} <b>{r.damage}</b>
        </span>
      ))}
    </div>
  );
}

/** The matrix, behind a toggle: a row per commander, a column per player, the damage it dealt them. */
export function CommanderMatrixToggle() {
  const players = useGame((s) => s.view?.players);
  const [open, setOpen] = useState(false);
  if (!players?.some((p) => p.commanders.length)) return null;
  return (
    <div className="cmd-matrix-wrap">
      <button className="cmd-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid="cmd-matrix-toggle"
        title="Every commander's damage to every player">
        <span>Whole table</span> {open ? "▴" : "▾"}
      </button>
      {open && <CommanderMatrix players={players} />}
    </div>
  );
}

export function CommanderMatrix({ players }: { players: PlayerView[] }) {
  const { cols, rows } = commanderMatrix(players);
  return (
    <div className="cmd-matrix" data-testid="cmd-matrix">
      <table>
        <caption>Commander damage: each commander (row) to each player (column)</caption>
        <thead>
          <tr>
            <td />
            {cols.map((c) => (
              <th key={c.id} scope="col" title={c.name}>
                <i className="cmdr-dealt-chip" style={{ ["--player-color" as string]: c.color }} aria-hidden>{c.name.slice(0, 1).toUpperCase()}</i>
                <span className="sr-only">{c.name}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <th scope="row" title={`${r.name} (${r.owner.name})`}>
                <span className="cmd-matrix-cmdr">
                  <i className="cmdr-dealt-chip" style={{ ["--player-color" as string]: r.owner.color }} aria-hidden>{r.owner.name.slice(0, 1).toUpperCase()}</i>
                  <span className="cmd-matrix-cname">{r.name.split(",")[0]}</span>
                </span>
              </th>
              {r.cells.map((c) => (
                <td key={c.player} className={c.damage >= LETHAL_COMMANDER ? "lethal" : c.own && !c.damage ? "own" : c.damage ? "" : "zero"}>
                  {c.own && !c.damage ? <><span aria-hidden>·</span><span className="sr-only">its owner</span></> : c.damage >= LETHAL_COMMANDER ? <>{c.damage}<span className="sr-only"> lethal</span></> : c.damage}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
