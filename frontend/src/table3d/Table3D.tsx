/**
 * The 3D table on the game screen: the three.js scene plus DOM overlays that must stay crisp
 * (seat plates with life totals, camera presets). Falls back to the 2D table when WebGL is
 * unavailable (see GameScreen).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { setDropResolver3D } from "../game/dnd";
import { LETHAL_COMMANDER, LETHAL_POISON, PlayerPanel } from "../game/PlayerPanel";
import { plane } from "../theme/planes";
import { isVisible, type GameView } from "../types/game";
import { ERROR_MS, TableScene, type CameraPreset, type Quality } from "./TableScene";
import { startAmbience } from "./ambience";
import "./table3d.css";

declare global {
  interface Window {
    /** Test and diagnostics hooks (no game data beyond what the page already shows). */
    __fyodor3d?: {
      stats: () => TableScene["stats"];
      camera: (p: CameraPreset) => void;
      cardAt: (id: string) => { x: number; y: number } | null;
      battlefieldAt: (player: string, x: number, y: number) => { x: number; y: number } | null;
    };
  }
}

export function Table3D({ me }: { me: string }) {
  const host = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<TableScene | null>(null);
  const planeId = usePrefs((s) => s.plane);
  const graphics = usePrefs((s) => s.graphics);
  const ambienceOn = usePrefs((s) => s.ambience && !s.sound.muted);
  const ambientVol = usePrefs((s) => s.sound.master * s.sound.ambient);
  const players = useGame((s) => s.view?.seat_order ?? []);
  const [preset, setPreset] = useState<CameraPreset>("seat");
  const [open, setOpen] = useState<string | null>(null);
  const plates = useRef<Record<string, HTMLDivElement | null>>({});
  const tags = useRef<Record<string, HTMLDivElement | null>>({});
  const tagView = useGame((s) => s.view);
  const selection = useGame((s) => s.selection);
  const [allNames, setAllNames] = useState(false);
  const tagged = useMemo(() => nameTags(tagView, selection, allNames), [tagView, selection, allNames]);

  // create / destroy the scene (quality changes need a new renderer)
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const quality: Quality = graphics === "low" ? "low" : graphics === "medium" ? "medium" : "high";
    const scene = new TableScene(el, plane(usePrefs.getState().plane), quality);
    sceneRef.current = scene;
    const resize = () => scene.resize(el.clientWidth, el.clientHeight);
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();
    const sync = () => {
      const s = useGame.getState();
      if (s.view) scene.update(s.view, me);
    };
    sync();
    const unGame = useGame.subscribe((s, prev) => {
      if (s.view !== prev.view || s.selection !== prev.selection || s.pendingPositions !== prev.pendingPositions || s.errorCard !== prev.errorCard) sync();
      if (s.errorCard && s.errorCard !== prev.errorCard) setTimeout(sync, ERROR_MS + 50);
    });
    const unCards = useCardCache.subscribe((s, prev) => {
      if (s.cards !== prev.cards) sync();
    });
    setDropResolver3D((x, y) => scene.resolveDrop(x, y));
    window.__fyodor3d = {
      stats: () => scene.stats,
      camera: (p) => scene.setCamera(p),
      cardAt: (id) => scene.screenOfCard(id),
      battlefieldAt: (player, x, y) => scene.screenOfBattlefield(player, x, y),
    };
    // keep the seat plates glued to the table, stepping out from over fixed chrome (camera strip,
    // turn dial, stack panels) and the battlefield cards, and never past the screen edge
    let frame = 0;
    type Box = { left: number; top: number; right: number; bottom: number };
    let cards: Box[] = [];
    let chrome: Box[] = [];
    const follow = () => {
      const host = el.getBoundingClientRect();
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (frame++ % 20 === 0) {
        chrome = [...document.querySelectorAll(".t3d-cams, .turn-dial-wrap, .stack-widget.open, .rules-stack-wrap, .t3d-coach")].map((n) => {
          const r = n.getBoundingClientRect();
          return { left: r.left - host.left, top: r.top - host.top, right: r.right - host.left, bottom: r.bottom - host.top };
        });
        cards = scene.battlefieldRects(w, h);
      }
      for (const [pid, node] of Object.entries(plates.current)) {
        if (!node) continue;
        const pt = scene.seatScreen(pid, w, h);
        if (!pt) continue;
        // sizes are measured in each form, so the compact switch doesn't flicker
        const form = node.classList.contains("compact") ? "small" : "full";
        if (node.offsetWidth) node.dataset[form] = `${node.offsetWidth},${node.offsetHeight}`;
        const size = (f: string) => (node.dataset[f] ?? "160,56").split(",").map(Number) as [number, number];
        const place = ([pw, ph]: [number, number]) => {
          let { x, y } = pt;
          const hits = (r: Box) => !(x + pw / 2 < r.left || x - pw / 2 > r.right || y + ph / 2 < r.top || y - ph / 2 > r.bottom);
          const fits = (v: number) => v >= ph / 2 + 8 && v <= h - ph / 2 - 8;
          const stepOff = (boxes: Box[]) => {
            let moved = false;
            for (const r of boxes) {
              if (!hits(r)) continue;
              // to whichever edge of the obstacle is nearer, unless that leaves the screen
              const up = r.top - ph / 2 - 6;
              const down = r.bottom + ph / 2 + 6;
              y = (y - r.top < r.bottom - y && fits(up)) || !fits(down) ? up : down;
              moved = true;
            }
            return moved;
          };
          // cards first (a few passes: stepping off one card can land on its neighbour); a plaque
          // that would have to wander from its seat stays put instead; the fixed panels go last, so
          // a plaque is never hidden under one
          for (let pass = 0; pass < 4 && stepOff(cards); pass++);
          const far = Math.abs(y - pt.y) > MAX_DRIFT;
          if (far) y = pt.y;
          x = Math.max(pw / 2 + 8, Math.min(w - pw / 2 - 8, x));
          y = Math.max(ph / 2 + 8, Math.min(h - ph / 2 - 8, y));
          for (let pass = 0; pass < 3 && stepOff(chrome); pass++);
          return { x, y, covers: far || cards.some(hits) };
        };
        // no free spot near the seat (a crowded table): the compact form, which keeps life and any
        // commander damage or poison, and shows the rest on hover or focus
        if (frame % 20 === 1) node.classList.toggle("compact", place(size("full")).covers);
        const { x, y } = place(size(node.classList.contains("compact") ? "small" : "full"));
        node.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
        node.style.visibility = pt.visible ? "visible" : "hidden";
      }
      // name tags under the selected cards (the card faces are too small to read at seat distance)
      for (const [cid, node] of Object.entries(tags.current)) {
        if (!node) continue;
        const r = scene.cardRect(cid, w, h);
        if (!r) { node.style.visibility = "hidden"; continue; }
        node.style.transform = `translate(${Math.round((r.left + r.right) / 2)}px, ${Math.round(r.bottom + 4)}px) translateX(-50%)`;
        node.style.visibility = "visible";
      }
    };
    scene.onFrame = follow; // runs inside the three.js loop: one animation loop for the whole table
    return () => {
      scene.onFrame = null;
      unGame();
      unCards();
      setDropResolver3D(null);
      ro.disconnect();
      scene.dispose();
      sceneRef.current = null;
      delete window.__fyodor3d;
    };
  }, [me, graphics]);

  useEffect(() => sceneRef.current?.setPlane(plane(planeId)), [planeId]);
  useEffect(() => useGame.getState().setLayout({ stackOpen: false }), []); // the stack lies on the table itself
  useEffect(() => sceneRef.current?.setCamera(preset), [preset]);
  // camera keys (game/hotkeys.ts): 1 seat, 2–6 other players, 0 whole table, C focus the hovered card, Home back
  const back = useRef<CameraPreset>("seat");
  useEffect(() => {
    const onCam = (e: Event) => {
      const { id, digit, hover, player } = (e as CustomEvent<{ id: string; digit: number; hover: string | null; player?: string }>).detail;
      const others = players.filter((p) => p !== me);
      if (id === "cam_names") return setAllNames((x) => !x);
      setPreset((cur) => {
        if (id === "cam_seat" || id === "cam_reset") return "seat";
        if (id === "cam_table") return "overview";
        // the winner spotlight turns the camera toward the winning seat (your own seat: your usual view)
        if (id === "cam_focus_player") return player && player !== me && players.includes(player) ? { focus: player } : "seat";
        if (id === "cam_player") return others[digit - 2] ? { focus: others[digit - 2]! } : cur;
        if (id === "cam_focus") {
          if (typeof cur === "object" && "card" in cur) return back.current;
          if (hover && sceneRef.current?.screenOfCard(hover)) {
            back.current = cur;
            return { card: hover };
          }
        }
        return cur;
      });
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPreset((cur) => (typeof cur === "object" && "card" in cur ? back.current : cur));
    };
    window.addEventListener("fyodor:camera", onCam);
    window.addEventListener("keydown", onEsc);
    return () => {
      window.removeEventListener("fyodor:camera", onCam);
      window.removeEventListener("keydown", onEsc);
    };
  }, [players, me]);
  useAutoCenter(me, setPreset);
  useEffect(() => {
    if (!ambienceOn || ambientVol <= 0) return;
    return startAmbience(plane(planeId).ambience, ambientVol);
  }, [planeId, ambienceOn, ambientVol]);

  const others = players.filter((p) => p !== me);
  const names = useGame((s) => s.view?.players);
  const nameOf = (pid: string) => names?.find((p) => p.id === pid)?.name ?? pid;
  return (
    <div className="table3d" ref={host} data-testid="table-3d">
      <div className="t3d-plates">
        {players.map((pid) => (
          <div key={pid} className="t3d-plate-anchor" ref={(n) => { plates.current[pid] = n; }}>
            <SeatPlate player={pid} me={me} open={open === pid} onToggle={() => setOpen(open === pid ? null : pid)} />
          </div>
        ))}
      </div>
      <div className="t3d-tags" role="list" aria-label="Names of selected cards">
        {tagged.map(([cid, name]) => (
          <div key={cid} className="t3d-tag" role="listitem" ref={(n) => { tags.current[cid] = n; }}>{name}</div>
        ))}
      </div>
      <CoachTips />
      <MomentTips me={me} />
      <div className="t3d-cams frame" role="toolbar" aria-label="Camera">
        <button className={preset === "seat" ? "on" : ""} onClick={() => setPreset("seat")} title="Look from your seat (1)">Seat <kbd className="cam-key">1</kbd></button>
        {others.map((pid, i) => (
          <button key={pid} className={typeof preset === "object" && "focus" in preset && preset.focus === pid ? "on" : ""} onClick={() => setPreset({ focus: pid })}
            aria-label={`Look at ${nameOf(pid)}'s side`} title={`Look at ${nameOf(pid)}'s side (${i + 2})`}>
            <PlayerChip player={pid} /> <kbd className="cam-key">{i + 2}</kbd>
          </button>
        ))}
        <button className={preset === "overview" ? "on" : ""} onClick={() => setPreset("overview")} title="Look down on the whole table (0)">Table <kbd className="cam-key">0</kbd></button>
        <button className={allNames ? "on" : ""} aria-pressed={allNames} onClick={() => setAllNames(!allNames)} title="Show the names of all cards on the table (V)">Names <kbd className="cam-key">V</kbd></button>
      </div>
    </div>
  );
}

/**
 * Names for the selected battlefield cards. A face-down card is labelled as face down (never by its
 * name: the table screen is public), and the server never sends a hidden card's name anyway.
 */
function nameTags(view: GameView | null, selection: string[], all: boolean): [string, string][] {
  if (!view || (!all && selection.length > 12)) return EMPTY_TAGS;
  const out: [string, string][] = [];
  // ponytail: one DOM tag per card; fine to ~150 permanents, a canvas label layer if boards get bigger
  for (const id of all ? Object.keys(view.cards) : selection) {
    if (out.length >= 150) break;
    const c = view.cards[id];
    if (!c?.zone.endsWith(":battlefield")) continue;
    out.push([id, c.face_down || !isVisible(c) ? `Face down${c.face_down_as ? `: ${c.face_down_as}` : ""}` : c.name]);
  }
  return out.length ? out : EMPTY_TAGS;
}
const EMPTY_TAGS: [string, string][] = [];
/** How far (px) a seat plaque may move off its seat to clear cards before it goes compact instead. */
const MAX_DRIFT = 110;

const TIPS = [
  { title: "Players", text: "Click a player's plaque to see their counters, commander damage and actions." },
  { title: "Your turn", text: "The dial at the bottom right says whose turn it is, and its big button says what pressing it will do." },
  { title: "Playing cards", text: "Drag a card from your hand onto the table, or focus it and press Enter. Hold Alt as you drop to place it by hand." },
];
const COACH_KEY = "fyodor.coach3d";

/** Three short tips on a player's first 3D game; dismissed for good on this device. */
function CoachTips() {
  const [step, setStep] = useState(() => {
    try { return localStorage.getItem(COACH_KEY) === "done" ? -1 : 0; } catch { return -1; }
  });
  // tips are for the first turn; after that the table is the player's
  const early = useGame((s) => (s.view?.turn.number ?? 1) <= 1);
  if (step < 0 || step >= TIPS.length || !early) return null;
  const done = () => {
    try { localStorage.setItem(COACH_KEY, "done"); } catch { /* private mode: show again next time */ }
    setStep(-1);
  };
  const tip = TIPS[step]!;
  return (
    <aside className="t3d-coach plaque-wrap" aria-label="Tip">
      <div className="plaque t3d-coach-body">
        <p className="t3d-coach-title">{tip.title} <span className="t3d-coach-count">{step + 1} of {TIPS.length}</span></p>
        <p className="t3d-coach-text">{tip.text}</p>
        <div className="t3d-coach-actions">
          {step < TIPS.length - 1 && <button className="tt-btn" onClick={() => setStep(step + 1)}>Next tip</button>}
          <button className="tt-btn ghost" onClick={done}>{step < TIPS.length - 1 ? "Skip tips" : "Got it"}</button>
        </div>
      </div>
    </aside>
  );
}

const MOMENTS = {
  combat: { title: "Combat", text: "Drag your creatures toward a player or their plaque to attack, or right-click a creature for Attack. The dial's button moves on to blocks." },
  priority: { title: "Something is on the stack", text: "You can respond: cast an instant or use an ability now, and it resolves first. Otherwise press Pass (P) and the top of the stack resolves." },
  target: { title: "Choose a target", text: "Glowing cards and plaques are legal choices: click one. Esc cancels." },
} as const;
type Moment = keyof typeof MOMENTS;
const MOMENT_KEY = "fyodor.tips.seen";

/** A short tip the first time each moment comes up (after the first-turn tips); each shows once on this device. */
function MomentTips({ me }: { me: string }) {
  const [seen, setSeen] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(MOMENT_KEY) ?? "[]") as string[]; } catch { return Object.keys(MOMENTS); }
  });
  const moment = useGame((s): Moment | null => {
    const v = s.view;
    if (!v) return null;
    const d = v.rules?.decision;
    if (s.pick || (d && d.player === me && d.kind === "choose_cards")) return "target";
    if (v.rules?.priority === me && v.stack.length) return "priority";
    if (v.turn.active_player === me && (v.turn.phase === "begin_combat" || v.turn.phase === "declare_attackers")) return "combat";
    return null;
  });
  const save = (list: string[]) => {
    setSeen(list);
    try { localStorage.setItem(MOMENT_KEY, JSON.stringify(list)); } catch { /* private mode */ }
  };
  const firstTurn = useGame((s) => (s.view?.turn.number ?? 1) <= 1);
  let coaching = false;
  try { coaching = firstTurn && localStorage.getItem(COACH_KEY) !== "done"; } catch { /* private mode */ }
  if (!moment || coaching || seen.includes(moment) || seen.includes("off")) return null;
  const tip = MOMENTS[moment];
  return (
    <aside className="t3d-coach plaque-wrap" aria-label="Tip" aria-live="polite">
      <div className="plaque t3d-coach-body">
        <p className="t3d-coach-title">{tip.title}</p>
        <p className="t3d-coach-text">{tip.text}</p>
        <div className="t3d-coach-actions">
          <button className="tt-btn" onClick={() => save([...seen, moment])}>Got it</button>
          <button className="tt-btn ghost" onClick={() => save([...seen, "off"])}>No more tips</button>
        </div>
      </div>
    </aside>
  );
}

function PlayerChip({ player }: { player: string }) {
  const p = useGame((s) => s.view?.players.find((x) => x.id === player));
  return (
    <span className="cam-player">
      <i className="cam-chip" style={{ ["--player-color" as string]: p?.color }} aria-hidden>{p?.name.slice(0, 1).toUpperCase()}</i>
      {p?.name ?? "?"}
    </span>
  );
}

/** Portrait, name and life on the table next to each seat; click for the full player panel. */
function SeatPlate({ player, me, open, onToggle }: { player: string; me: string; open: boolean; onToggle: () => void }) {
  const p = useGame((s) => s.view?.players.find((x) => x.id === player));
  const active = useGame((s) => s.view?.turn.active_player === player);
  const priority = useGame((s) => s.view?.rules?.priority === player);
  const monarch = useGame((s) => s.view?.table.monarch === player);
  if (!p) return null;
  // the numbers that decide a Commander game, shown only when they matter
  const cmd = Math.max(0, ...Object.values(p.commander_damage));
  const poison = p.resources.poison ?? 0;
  // the same three stats on every plaque; a zero is dimmed, not hidden
  const stats = [
    { key: "cmd", text: `Cmdr dmg ${cmd}/${LETHAL_COMMANDER}`, title: `Most damage taken from one commander: ${cmd} of ${LETHAL_COMMANDER}`, n: cmd, lethal: cmd >= LETHAL_COMMANDER },
    { key: "poison", text: `Poison ${poison}/${LETHAL_POISON}`, title: `${poison} of ${LETHAL_POISON} poison counters`, n: poison, lethal: poison >= LETHAL_POISON },
    { key: "hand", text: `Hand ${p.hand_count}`, title: `${p.hand_count} cards in hand`, n: p.hand_count, lethal: false },
  ];
  return (
    <div className={`t3d-seat ${active ? "active" : ""} ${priority ? "priority" : ""}`} style={{ ["--player-color" as string]: p.color }} data-player-id={player}>
      {(active || priority) && (
        <span className="t3d-seat-flags" aria-live="polite">
          {active && <span className="t3d-flag turn">Turn</span>}
          {priority && <span className="t3d-flag prio">Priority</span>}
        </span>
      )}
      <button className="t3d-seat-main" onClick={onToggle} data-testid={`seat-${player}`} aria-label={`${p.name}${player === me ? " (you)" : ""}: ${p.life} life. Open player panel`} aria-expanded={open}>
        <span className={`portrait ${active ? "active" : ""}`} style={{ ["--size" as string]: "46px", borderColor: p.color }}>{p.name.slice(0, 1).toUpperCase()}</span>
        <span className="t3d-seat-text">
          <span className="t3d-seat-name">{p.name}{player === me ? " (you)" : ""}{monarch ? " ♚" : ""}</span>
          <span className="t3d-seat-life" data-testid={`life3d-${player}`}>{p.life}</span>
          <span className="t3d-seat-stats">
            {stats.map((x) => <span key={x.key} className={`t3d-stat t3d-stat-${x.key} ${x.lethal ? "lethal" : x.n ? "" : "zero"}`} title={x.title}>{x.text}{x.lethal ? " · lethal" : ""}</span>)}
          </span>
        </span>
      </button>
      {open && (
        <div className="t3d-seat-panel frame">
          <PlayerPanel player={player} me={me} />
        </div>
      )}
    </div>
  );
}

/**
 * Auto-center (TABLETOP_QOL_MILESTONE #11), off unless the player turns it on: a commander cast or
 * an elimination turns the camera toward that seat for a moment, then back. Any input of the
 * player's own cancels it at once; reduced motion disables it. Camera only, never game state.
 */
function useAutoCenter(me: string, setPreset: React.Dispatch<React.SetStateAction<CameraPreset>>) {
  const mode = usePrefs((s) => s.autoCenter);
  const reduced = usePrefs((s) => s.reducedMotion);
  const prev = useRef<{ stack: Set<string>; out: Set<string> } | null>(null);
  useEffect(() => {
    if (mode === "off" || reduced) {
      prev.current = null;
      return;
    }
    let timer = 0;
    let restore: CameraPreset | null = null;
    const cancel = () => {
      window.clearTimeout(timer);
      if (restore) setPreset(restore);
      restore = null;
    };
    const unsub = useGame.subscribe((s) => {
      const v = s.view;
      if (!v) return;
      const stack = new Set(v.stack);
      const out = new Set([...(v.rules?.conceded ?? []), ...Object.keys(v.rules?.lost ?? {})]);
      const before = prev.current;
      prev.current = { stack, out };
      if (!before) return;
      let focus: string | null = null;
      for (const pid of out) if (!before.out.has(pid)) focus = pid;
      for (const id of stack) {
        const c = v.cards[id];
        if (!before.stack.has(id) && c && "commander_key" in c && c.commander_key) focus = c.controller;
      }
      if (!focus || focus === me) return;
      window.clearTimeout(timer);
      setPreset((cur) => {
        if (!restore) restore = cur;
        return { focus: focus! };
      });
      timer = window.setTimeout(cancel, 2600 / (usePrefs.getState().animationSpeed || 1));
    });
    const input = () => {
      if (restore) cancel();
    };
    window.addEventListener("pointerdown", input, true);
    window.addEventListener("wheel", input, true);
    window.addEventListener("keydown", input, true);
    return () => {
      unsub();
      window.clearTimeout(timer);
      window.removeEventListener("pointerdown", input, true);
      window.removeEventListener("wheel", input, true);
      window.removeEventListener("keydown", input, true);
    };
  }, [mode, reduced, me, setPreset]);
}
