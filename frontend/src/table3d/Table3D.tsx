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
import { PlayerPanel } from "../game/PlayerPanel";
import { plane } from "../theme/planes";
import { TableScene, type CameraPreset, type Quality } from "./TableScene";
import { startAmbience } from "./ambience";
import "./table3d.css";

declare global {
  interface Window { __fyodor3d?: { stats: () => TableScene["stats"]; camera: (p: CameraPreset) => void } }
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
    window.__fyodor3d = { stats: () => scene.stats, camera: (p) => scene.setCamera(p) };
    // keep the seat plates glued to the table
    let raf = 0;
    const follow = () => {
      raf = requestAnimationFrame(follow);
      for (const [pid, node] of Object.entries(plates.current)) {
        if (!node) continue;
        const pt = scene.seatScreen(pid, el.clientWidth, el.clientHeight);
        if (!pt) continue;
        node.style.transform = `translate(${Math.round(pt.x)}px, ${Math.round(pt.y)}px)`;
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
  useEffect(() => {
    if (!ambienceOn || ambientVol <= 0) return;
    return startAmbience(plane(planeId).ambience, ambientVol);
  }, [planeId, ambienceOn, ambientVol]);

  const others = players.filter((p) => p !== me);
  return (
    <div className="table3d" ref={host} data-testid="table-3d">
      <div className="t3d-plates">
        {players.map((pid) => (
          <div key={pid} className="t3d-plate-anchor" ref={(n) => { plates.current[pid] = n; }}>
            <SeatPlate player={pid} me={me} open={open === pid} onToggle={() => setOpen(open === pid ? null : pid)} />
          </div>
        ))}
      </div>
      <div className="t3d-cams frame" role="toolbar" aria-label="Camera">
        <button className={preset === "seat" ? "on" : ""} onClick={() => setPreset("seat")} title="Your seat">Seat</button>
        <button className={preset === "overview" ? "on" : ""} onClick={() => setPreset("overview")} title="The whole table">Table</button>
        {others.map((pid) => (
          <button key={pid} className={typeof preset === "object" && preset.focus === pid ? "on" : ""} onClick={() => setPreset({ focus: pid })}>
            <PlayerInitial player={pid} />
          </button>
        ))}
      </div>
    </div>
  );
}

function PlayerInitial({ player }: { player: string }) {
  const name = useGame((s) => s.view?.players.find((p) => p.id === player)?.name ?? "?");
  return <span title={`Look at ${name}'s side`}>{name.slice(0, 1).toUpperCase()}</span>;
}

/** Portrait, name and life on the table next to each seat; click for the full player panel. */
function SeatPlate({ player, me, open, onToggle }: { player: string; me: string; open: boolean; onToggle: () => void }) {
  const p = useGame((s) => s.view?.players.find((x) => x.id === player));
  const active = useGame((s) => s.view?.turn.active_player === player);
  const priority = useGame((s) => s.view?.rules?.priority === player);
  const monarch = useGame((s) => s.view?.table.monarch === player);
  if (!p) return null;
  return (
    <div className={`t3d-seat ${active ? "active" : ""} ${priority ? "priority" : ""}`} style={{ ["--player-color" as string]: p.color }} data-player-id={player}>
      <button className="t3d-seat-main" onClick={onToggle} data-testid={`seat-${player}`}>
        <span className={`portrait ${active ? "active" : ""}`} style={{ ["--size" as string]: "46px", borderColor: p.color }}>{p.name.slice(0, 1).toUpperCase()}</span>
        <span className="t3d-seat-text">
          <span className="t3d-seat-name">{p.name}{player === me ? " (you)" : ""}{monarch ? " ♚" : ""}</span>
          <span className="t3d-seat-life" data-testid={`life3d-${player}`}>{p.life}</span>
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
