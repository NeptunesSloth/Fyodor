import { useEffect, useState } from "react";
import { useGame } from "../state/gameStore";
import { isVisible, type GameCard, type GameView } from "../types/game";
import { GameCardFace } from "./GameCardFace";

/*
 * Combat lane view (TABLETOP_QOL_MILESTONE.md #9): an optional, temporary presentation of combat.
 * Each attacker sits over its blocker(s), grouped by the player, planeswalker or battle it attacks.
 * It never moves a card on the table; closing it (or combat ending) leaves every position as it was.
 * Works the same over the 2D and the 3D table.
 */

interface Lane { attacker: GameCard; blockers: GameCard[] }
interface Front { key: string; label: string; lanes: Lane[] }

export function combatFronts(view: GameView): Front[] {
  const onField = Object.values(view.cards).filter((c) => c.zone.endsWith(":battlefield"));
  const nameOf = (id: string) => view.players.find((p) => p.id === id)?.name ?? (view.cards[id] && isVisible(view.cards[id]!) ? view.cards[id]!.name : null) ?? "Unknown";
  const fronts = new Map<string, Front>();
  for (const a of onField) {
    if (!a.attacking && !a.attacking_without_target) continue;
    const key = a.attacking ? `${a.attacking.kind}:${a.attacking.id}` : "none";
    const label = a.attacking ? nameOf(a.attacking.id) : "No target yet";
    const front = fronts.get(key) ?? { key, label, lanes: [] };
    front.lanes.push({ attacker: a, blockers: onField.filter((b) => b.blocking === a.id || b.blocking_more?.includes(a.id)) });
    fronts.set(key, front);
  }
  return [...fronts.values()];
}

export function CombatLanes() {
  const view = useGame((s) => s.view);
  const [open, setOpen] = useState(false);
  const fronts = view ? combatFronts(view) : [];
  const attackers = fronts.reduce((n, f) => n + f.lanes.length, 0);
  useEffect(() => {
    if (!attackers) setOpen(false);
  }, [attackers]);
  if (!view || !attackers) return null;
  const { setHover, select } = useGame.getState();
  const blocked = fronts.reduce((n, f) => n + f.lanes.filter((l) => l.blockers.length).length, 0);
  return (
    <>
      <button className={`combat-pill tt-btn ${open ? "on" : ""}`} data-testid="combat-view-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        title="Show combat as lanes: each attacker over its blockers (cards stay where they are)">
        Combat · {attackers} attacking{blocked ? ` · ${blocked} blocked` : ""}
      </button>
      {open && (
        <div className="combat-lanes plaque-wrap" data-testid="combat-lanes" role="region" aria-label="Combat lanes">
          <div className="plaque combat-lanes-body">
            <div className="combat-lanes-head">
              <b>Combat</b>
              <button className="tt-btn ghost" onClick={() => setOpen(false)}>Close</button>
            </div>
            {fronts.map((f) => (
              <section key={f.key} className="combat-front">
                <h3>Attacking {f.label}</h3>
                <div className="combat-row">
                  {f.lanes.map(({ attacker, blockers }) => (
                    <div key={attacker.id} className="combat-lane">
                      <LaneCard card={attacker} onHover={setHover} onPick={(id) => select([id])} />
                      <span className={`combat-vs ${blockers.length ? "" : "open"}`}>{blockers.length ? `Blocked by ${blockers.length}` : "Unblocked"}</span>
                      <div className="combat-blockers">
                        {blockers.map((b) => <LaneCard key={b.id} card={b} small onHover={setHover} onPick={(id) => select([id])} />)}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function LaneCard({ card, small, onHover, onPick }: { card: GameCard; small?: boolean; onHover: (id: string | null) => void; onPick: (id: string) => void }) {
  return (
    <button className={`combat-card ${small ? "small" : ""}`} onPointerEnter={() => onHover(card.id)} onPointerLeave={() => onHover(null)} onClick={() => onPick(card.id)}
      aria-label={isVisible(card) ? card.name : "Face-down card"}>
      <GameCardFace card={card} size="small" />
    </button>
  );
}
