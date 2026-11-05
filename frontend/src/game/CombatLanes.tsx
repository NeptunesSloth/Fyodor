import { useEffect, useState } from "react";
import { useGame } from "../state/gameStore";
import { isVisible, type GameCard, type GameView } from "../types/game";
import { GameCardFace } from "./GameCardFace";
import { useHoverCard } from "./hoverCard";
import { attackerDamage, frontTotal, totalText } from "./combatTotals";
import { stackSize } from "./tokenStacks";

/*
 * Combat lane view (TABLETOP_QOL_MILESTONE.md #9): an optional, temporary presentation of combat.
 * Each attacker sits over its blocker(s), grouped by the player, planeswalker or battle it attacks.
 * It never moves a card on the table; closing it (or combat ending) leaves every position as it was.
 * The 3D table opens it from a small button; the 2D table docks it as a strip between the
 * opponents and you (CombatStrip), open for as long as combat lasts.
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
  const { select } = useGame.getState();
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
                <h3>Attacking {f.label}<FrontTotalNote view={view} lanes={f.lanes} /></h3>
                <div className="combat-row">
                  {f.lanes.map(({ attacker, blockers }) => (
                    <div key={attacker.id} className="combat-lane">
                      <LaneCard card={attacker} onPick={(id) => select([id])} />
                      <span className={`combat-vs ${blockers.length ? "" : "open"}`}>{blockers.length ? `Blocked by ${blockers.length}` : "Unblocked"}<StackDamage view={view} card={attacker} blocked={blockers.length > 0} /></span>
                      <div className="combat-blockers">
                        {blockers.map((b) => <LaneCard key={b.id} card={b} small onPick={(id) => select([id])} />)}
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

function LaneCard({ card, small, onPick }: { card: GameCard; small?: boolean; onPick: (id: string) => void }) {
  const hover = useHoverCard();
  return (
    <button className={`combat-card ${small ? "small" : ""}`} {...hover(card.id)} onClick={() => onPick(card.id)}
      aria-label={isVisible(card) ? card.name : "Face-down card"}>
      <GameCardFace card={card} size="small" />
    </button>
  );
}

/** 2D: the fight, docked between the opponents and you while anything is attacking. */
export function CombatStrip() {
  const view = useGame((s) => s.view);
  const fronts = view ? combatFronts(view) : [];
  if (!view || !fronts.length) return null;
  const { select } = useGame.getState();
  return (
    <section className="combat-strip" data-testid="combat-strip" aria-label="Combat">
      <b className="combat-strip-title">Combat</b>
      {fronts.map((f) => (
        <div key={f.key} className="combat-strip-front">
          <span className="combat-strip-label">Attacking {f.label}<FrontTotalNote view={view} lanes={f.lanes} compact /></span>
          <div className="combat-strip-row">
            {f.lanes.map(({ attacker, blockers }) => (
              <div key={attacker.id} className="combat-strip-lane">
                <LaneCard card={attacker} onPick={(id) => select([id])} />
                {blockers.length ? (
                  <>
                    <span className="combat-strip-vs" aria-label="blocked by">vs</span>
                    {blockers.map((b) => <LaneCard key={b.id} card={b} small onPick={(id) => select([id])} />)}
                  </>
                ) : <span className="combat-vs open">Unblocked<StackDamage view={view} card={attacker} blocked={false} /></span>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

/** -- engine token stacks -- the total an attack's unblocked creatures deal (stack members × power), when a stack attacks there. */
function FrontTotalNote({ view, lanes, compact }: { view: GameView; lanes: Lane[]; compact?: boolean }) {
  const t = frontTotal(view, lanes);
  if (!t.stacked) return null;
  const attacking = `${t.attackers.toLocaleString("en-US")} attacking`;
  // (the 2D strip's narrow label: one fact per line)
  if (compact) return <span className="combat-total" data-testid="combat-total"><span>{attacking}</span><span>{totalText(t)}</span></span>;
  return <span className="combat-total" data-testid="combat-total"> · {attacking} · {totalText(t)}</span>;
}

/** An unblocked stack's own share: "×512 → 1,024". */
function StackDamage({ view, card, blocked }: { view: GameView; card: GameCard; blocked: boolean }) {
  const n = stackSize(card);
  if (n < 2 || blocked) return null;
  const dmg = attackerDamage(view, card);
  if (dmg == null) return null;
  return <span className="combat-stack-dmg" data-testid="combat-stack-damage"> · ×{n.toLocaleString("en-US")} → {dmg.toLocaleString("en-US")}</span>;
}
