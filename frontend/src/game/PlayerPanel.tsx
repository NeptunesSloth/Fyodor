import { useState } from "react";
import { openMenu, type MenuItem } from "../components/ContextMenu";
import { askNumber, askText } from "../components/Prompt";
import { useGame, usePlayer } from "../state/gameStore";
import type { ManaUnit, PlayerView } from "../types/game";
import { changeLife, changeResource, send } from "./actions";

const LIFE_STEPS = [-10, -5, -1, 1, 5, 10];
/** Colorblind-safe seat markers: a distinct shape per seat alongside the color. */
const SEAT_GLYPHS = ["●", "▲", "■", "◆", "★", "✚"];
const RESOURCE_ICON: Record<string, string> = { poison: "☠", energy: "⚡", experience: "★", rad: "☢", ticket: "🎟" };
export const LETHAL_COMMANDER = 21;
export const LETHAL_POISON = 10;

export function PlayerPanel({ player, me, compact }: { player: string; me: string; compact?: boolean }) {
  const p = usePlayer(player);
  const active = useGame((s) => s.view?.turn.active_player === player);
  const monarch = useGame((s) => s.view?.table.monarch === player);
  const initiative = useGame((s) => s.view?.table.initiative === player);
  const seat = useGame((s) => s.view?.game.seats[player]);
  const mode = useGame((s) => s.view?.game.mode);
  const [showHistory, setShowHistory] = useState(false);
  if (!p) return null;

  const maxCmd = Math.max(0, ...Object.values(p.commander_damage));
  const poison = p.resources.poison ?? 0;
  const danger = p.life <= 0 || maxCmd >= LETHAL_COMMANDER || poison >= LETHAL_POISON;

  return (
    <div className={`player-panel ${active ? "active" : ""} ${danger ? "danger" : ""} ${compact ? "compact" : ""}`} style={{ ["--player-color" as string]: p.color }}
      data-player-id={player}>
      <div className="pp-head">
        <span className="pp-dot" />
        <span className="seat-glyph" aria-hidden>{SEAT_GLYPHS[(Number(player.slice(1)) - 1) % SEAT_GLYPHS.length]}</span>
        <span className="pp-name" title={p.deck_name ?? undefined}>{p.name}{player === me ? " (you)" : ""}</span>
        {mode === "lan" && seat && (
          <span className={`presence-label ${seat.presence ?? (seat.connected ? "connected" : "disconnected")}`} data-testid={`presence-${player}`}>
            {{ connected: "Connected", reconnecting: "Reconnecting…", disconnected: "Disconnected", open: "Open seat" }[seat.presence ?? (seat.connected ? "connected" : "disconnected")]}
          </span>
        )}
        {monarch && <span className="marker" title="The Monarch">♚</span>}
        {initiative && <span className="marker" title="Has the initiative">⚑</span>}
        {p.city_blessing && <span className="marker" title="City's blessing">✦</span>}
        <button className="icon-btn small" onClick={(e) => openMenu(e, playerMenu(p), p.name)} aria-label="Player menu">⋯</button>
      </div>
      <div className="life-line">
        <button className="life-step" aria-label="Lose 1 life" data-testid={`life-minus-${player}`} onClick={() => void changeLife(player, -1)}>−</button>
        <button
          className="life"
          data-testid={`life-${player}`}
          title="Click for quick adjust · right-click for history"
          onClick={(e) =>
            openMenu(e, [
              ...LIFE_STEPS.map((d) => ({ label: d > 0 ? `+${d}` : `${d}`, onClick: () => void changeLife(player, d) })),
              "separator" as const,
              {
                label: "Set life…",
                onClick: async () => {
                  const v = await askNumber(`Set ${p.name}'s life`, p.life);
                  if (v !== null) void send({ type: "set_life", player, value: v });
                },
              },
              { label: showHistory ? "Hide history" : "Life history", onClick: () => setShowHistory((x) => !x) },
            ], `${p.name} · ${p.life} life`)
          }
          onContextMenu={(e) => {
            e.preventDefault();
            setShowHistory((x) => !x);
          }}
        >
          {p.life}
        </button>
        <button className="life-step" aria-label="Gain 1 life" data-testid={`life-plus-${player}`} onClick={() => void changeLife(player, 1)}>+</button>
      </div>
      {showHistory && (
        <div className="life-history" onClick={() => setShowHistory(false)}>
          {p.life_history.length === 0 && <span className="hint">No changes yet</span>}
          {p.life_history.slice(-12).map((h, i) => (
            <div key={i}>
              <span className="hint">T{h.turn}</span> {h.before} → {h.after}
            </div>
          ))}
        </div>
      )}
      <Resources p={p} />
      <CommanderDamage p={p} />
      <div className="pp-foot hint">
        Hand {p.hand_count} · Library {p.library_count}
        {p.mulligans > 0 && ` · Mulligans ${p.mulligans}`}
      </div>
      <ManaPool player={player} mana={p.mana ?? {}} units={p.mana_units ?? []} />
      {p.commanders.length > 0 && (
        <div className="pp-cmds" data-testid={`commanders-${p.id}`}>
          {p.commanders.map((c) => (
            <span key={c.key} className={`pp-cmd ${c.zone?.endsWith(":command") ? "home" : ""}`} title={`${c.name} — commander tax ${c.tax}, cast ${c.casts ?? 0}× from the command zone`}>
              ♛ {c.name.split(",")[0]} <b>+{c.tax}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Resources({ p }: { p: PlayerView }) {
  const entries = Object.entries(p.resources).filter(([k, v]) => v !== 0 || !["poison", "energy", "experience"].includes(k));
  return (
    <div className="resources">
      {entries.map(([k, v]) => (
        <span
          key={k}
          className={`res ${k} ${k === "poison" && v >= LETHAL_POISON ? "lethal" : ""}`}
          title={`${k}: click +1, right-click −1`}
          onClick={() => void changeResource(p.id, k, 1)}
          onContextMenu={(e) => {
            e.preventDefault();
            void changeResource(p.id, k, -1);
          }}
        >
          {RESOURCE_ICON[k] ?? k.slice(0, 6)} {v}
        </span>
      ))}
      <button
        className="res add"
        title="Add a counter (poison, energy, experience, custom…)"
        onClick={(e) =>
          openMenu(e, [
            ...["poison", "energy", "experience", "rad", "ticket"].map((k) => ({ label: `${RESOURCE_ICON[k] ?? ""} ${k}`, onClick: () => void changeResource(p.id, k, 1) })),
            "separator" as const,
            {
              label: "Custom counter…",
              onClick: async () => {
                const k = await askText("Counter name", "");
                if (k) void changeResource(p.id, k, 1);
              },
            },
          ])
        }
      >
        +
      </button>
    </div>
  );
}

function CommanderDamage({ p }: { p: PlayerView }) {
  const view = useGame((s) => s.view);
  const [open, setOpen] = useState(false);
  if (!view) return null;
  const sources = view.players.filter((o) => o.id !== p.id).flatMap((o) => o.commanders.map((c) => ({ ...c, owner: o })));
  if (!sources.length) return null;
  const taken = sources.filter((c) => (p.commander_damage[c.key] ?? 0) > 0);
  return (
    <div className="cmd-damage">
      <button className="cmd-toggle" onClick={() => setOpen((o) => !o)}>
        Commander damage {taken.length ? taken.map((c) => p.commander_damage[c.key]).join(" · ") : "—"} {open ? "▴" : "▾"}
      </button>
      {open && (
        <div className="cmd-list">
          {sources.map((c) => {
            const dmg = p.commander_damage[c.key] ?? 0;
            return (
              <div key={c.key} className={`cmd-row ${dmg >= LETHAL_COMMANDER ? "lethal" : ""}`}>
                <span className="cmd-name" style={{ color: c.owner.color }} title={`${c.owner.name}'s commander`}>{c.name}</span>
                <button className="life-btn" onClick={() => void send({ type: "commander_damage", player: p.id, commander: c.key, delta: -1 })}>−</button>
                <span className="cmd-val">{dmg}</span>
                <button className="life-btn" onClick={() => void send({ type: "commander_damage", player: p.id, commander: c.key, delta: 1 })}>+</button>
                <button
                  className="life-btn"
                  title="Deal N commander damage"
                  onClick={async () => {
                    const n = await askNumber(`Commander damage from ${c.name}`, 1);
                    if (n) void send({ type: "commander_damage", player: p.id, commander: c.key, delta: n });
                  }}
                >
                  …
                </button>
              </div>
            );
          })}
          <div className="hint">Commander damage also reduces life. 21+ from one commander is marked.</div>
        </div>
      )}
    </div>
  );
}

function playerMenu(p: PlayerView): MenuItem[] {
  const view = useGame.getState().view;
  const items: MenuItem[] = [
    { label: "Set life…", onClick: async () => {
      const v = await askNumber(`Set ${p.name}'s life`, p.life);
      if (v !== null) void send({ type: "set_life", player: p.id, value: v });
    } },
    { label: "Rename…", onClick: async () => {
      const n = await askText("Player name", p.name);
      if (n) void send({ type: "rename_player", player: p.id, name: n });
    } },
    "separator",
    { label: view?.table.monarch === p.id ? "Remove monarch" : "Becomes the monarch", onClick: () => void send({ type: "set_monarch", player: view?.table.monarch === p.id ? null : p.id }) },
    { label: view?.table.initiative === p.id ? "Remove initiative" : "Takes the initiative", onClick: () => void send({ type: "set_initiative", player: view?.table.initiative === p.id ? null : p.id }) },
    { label: p.city_blessing ? "Remove city's blessing" : "Gets the city's blessing", onClick: () => void send({ type: "city_blessing", player: p.id, value: !p.city_blessing }) },
    "separator",
    { label: "Untap all permanents", onClick: () => void send({ type: "untap_all", player: p.id }) },
    { label: "View sideboard", onClick: () => useGame.getState().openBrowser({ zone: `${p.id}:sideboard`, title: `${p.name}'s sideboard` }) },
    { label: "View foretold / face-down exile", onClick: () => useGame.getState().openBrowser({ zone: `${p.id}:foretell`, title: `${p.name}'s foretold cards` }) },
    { label: "View phased-out permanents", onClick: () => useGame.getState().openBrowser({ zone: `${p.id}:phased`, title: `${p.name}'s phased-out permanents` }) },
    { label: "View companion zone", onClick: () => useGame.getState().openBrowser({ zone: `${p.id}:companion`, title: `${p.name}'s companion` }) },
  ];
  for (const c of p.commanders) {
    items.push({
      label: `${c.name}: tax ${c.tax}${c.casts ? ` · cast ${c.casts}×` : ""}`,
      submenu: [
        { label: "+2", onClick: () => void send({ type: "commander_tax", commander: c.key, delta: 2 }) },
        { label: "−2", onClick: () => void send({ type: "commander_tax", commander: c.key, delta: -2 }) },
        { label: "Reset to 0", onClick: () => void send({ type: "commander_tax", commander: c.key, value: 0 }) },
      ],
    });
  }
  return items;
}

const MANA = ["W", "U", "B", "R", "G", "C"] as const;

/** Temporary mana pool: click +1, right-click −1, the × clears. Nothing is spent automatically. */
function ManaPool({ player, mana, units }: { player: string; mana: Record<string, number>; units: ManaUnit[] }) {
  const [open, setOpen] = useState(false);
  const total = Object.values(mana).reduce((a, b) => a + b, 0) + units.length;
  const add = (color: string, delta: number) => void send({ type: "add_mana", player, mana: { [color]: delta } });
  if (!open && !total) {
    return <button className="mana-toggle" data-testid={`mana-open-${player}`} onClick={() => setOpen(true)} title="Mana pool">◇ mana</button>;
  }
  return (
    <div className="mana-pool" data-testid={`mana-${player}`}>
      {MANA.map((c) => (
        <button key={c} className={`mana-pip ${c.toLowerCase()} ${mana[c] ? "on" : ""}`} title={`${c}: click +1, right-click −1`}
          onClick={() => add(c, 1)} onContextMenu={(e) => { e.preventDefault(); if (mana[c]) add(c, -1); }}>
          {c}<b>{mana[c] ?? 0}</b>
        </button>
      ))}
      {units.map((u) => (
        <span key={u.id} className={`mana-unit ${u.sym.toLowerCase()}`} data-testid={`mana-unit-${player}`}
          title={[u.note || "Remembers where it came from", u.tags.length ? `Source: ${u.tags.join(" ")}` : ""].filter(Boolean).join(" — ")}>
          {u.sym}
        </span>
      ))}
      <button className="mana-clear" title="Clear mana pool" onClick={() => { if (total) void send({ type: "clear_mana", player }); setOpen(false); }}>×</button>
    </div>
  );
}
