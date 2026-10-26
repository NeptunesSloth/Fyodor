/**
 * The 3D table on the game screen: the three.js scene plus DOM overlays that must stay crisp
 * (seat plates with life totals, camera presets). Falls back to the 2D table when WebGL is
 * unavailable (see GameScreen).
 */
import { useEffect, useRef, useState } from "react";
import { useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { setDropResolver3D } from "../game/dnd";
import { LETHAL_COMMANDER, LETHAL_POISON, PlayerPanel } from "../game/PlayerPanel";
import { plane } from "../theme/planes";
import { TableScene, type CameraPreset, type Quality } from "./TableScene";
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
      if (s.view !== prev.view || s.selection !== prev.selection || s.pendingPositions !== prev.pendingPositions) sync();
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
    // keep the seat plates glued to the table, stepping out from under fixed chrome (camera strip,
    // turn dial, stack panels) so no plaque is ever hidden
    let raf = 0;
    let frame = 0;
    let chrome: DOMRect[] = [];
    const follow = () => {
      raf = requestAnimationFrame(follow);
      const host = el.getBoundingClientRect();
      if (frame++ % 20 === 0) {
        chrome = [...document.querySelectorAll(".t3d-cams, .turn-dial-wrap, .stack-widget.open, .rules-stack-wrap, .t3d-coach")].map((n) => n.getBoundingClientRect());
      }
      for (const [pid, node] of Object.entries(plates.current)) {
        if (!node) continue;
        const pt = scene.seatScreen(pid, el.clientWidth, el.clientHeight);
        if (!pt) continue;
        const pw = node.offsetWidth || 160;
        const ph = node.offsetHeight || 56;
        let { x, y } = pt;
        for (const r of chrome) {
          const cx = x + host.left;
          const cy = y + host.top;
          if (cx + pw / 2 < r.left || cx - pw / 2 > r.right || cy + ph / 2 < r.top || cy - ph / 2 > r.bottom) continue;
          // move vertically to whichever edge of the obstacle is nearer
          y = cy - r.top < r.bottom - cy ? r.top - host.top - ph / 2 - 6 : r.bottom - host.top + ph / 2 + 6;
        }
        node.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
        node.style.visibility = pt.visible ? "visible" : "hidden";
      }
    };
    follow();
    return () => {
      cancelAnimationFrame(raf);
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
  useEffect(() => sceneRef.current?.setCamera(preset), [preset]);
  // camera keys (game/hotkeys.ts): 1 seat, 2–6 other players, 0 whole table, C focus the hovered card, Home back
  const back = useRef<CameraPreset>("seat");
  useEffect(() => {
    const onCam = (e: Event) => {
      const { id, digit, hover } = (e as CustomEvent<{ id: string; digit: number; hover: string | null }>).detail;
      const others = players.filter((p) => p !== me);
      setPreset((cur) => {
        if (id === "cam_seat" || id === "cam_reset") return "seat";
        if (id === "cam_table") return "overview";
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
      <CoachTips />
      <div className="t3d-cams frame" role="toolbar" aria-label="Camera">
        <button className={preset === "seat" ? "on" : ""} onClick={() => setPreset("seat")} title="Look from your seat (1)">Seat</button>
        {others.map((pid, i) => (
          <button key={pid} className={typeof preset === "object" && "focus" in preset && preset.focus === pid ? "on" : ""} onClick={() => setPreset({ focus: pid })}
            aria-label={`Look at ${nameOf(pid)}'s side`} title={`Look at ${nameOf(pid)}'s side (${i + 2})`}>
            <PlayerChip player={pid} />
          </button>
        ))}
        <button className={preset === "overview" ? "on" : ""} onClick={() => setPreset("overview")} title="Look down on the whole table (0)">Table</button>
      </div>
    </div>
  );
}

const TIPS = [
  { title: "Players", text: "Click a player's plaque to see their counters, commander damage and actions." },
  { title: "Your turn", text: "The dial at the bottom right says whose turn it is and what Pass will do. P passes priority." },
  { title: "Playing cards", text: "Drag a card from your hand onto the table to play it. Hold Alt as you drop to place it by hand." },
];
const COACH_KEY = "fyodor.coach3d";

/** Three short tips on a player's first 3D game; dismissed for good on this device. */
function CoachTips() {
  const [step, setStep] = useState(() => {
    try { return localStorage.getItem(COACH_KEY) === "done" ? -1 : 0; } catch { return -1; }
  });
  if (step < 0 || step >= TIPS.length) return null;
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
  const stats: { key: string; text: string; title: string; lethal: boolean }[] = [];
  if (cmd > 0) stats.push({ key: "cmd", text: `Cmdr ${cmd}`, title: `Most commander damage from one commander: ${cmd} of ${LETHAL_COMMANDER}`, lethal: cmd >= LETHAL_COMMANDER });
  if (poison > 0) stats.push({ key: "poison", text: `Poison ${poison}`, title: `${poison} of ${LETHAL_POISON} poison counters`, lethal: poison >= LETHAL_POISON });
  if (player !== me) stats.push({ key: "hand", text: `Hand ${p.hand_count}`, title: `${p.hand_count} cards in hand`, lethal: false });
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
          {stats.length > 0 && (
            <span className="t3d-seat-stats">
              {stats.map((x) => <span key={x.key} className={`t3d-stat ${x.lethal ? "lethal" : ""}`} title={x.title}>{x.text}{x.lethal ? " · lethal" : ""}</span>)}
            </span>
          )}
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
