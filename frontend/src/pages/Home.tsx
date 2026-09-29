/**
 * The launcher: the selected plane's table in the background, the game's menu in front.
 * First-run setup opens on top until it is done.
 */
import { lazy, Suspense, useEffect, useState } from "react";
import { getHealth, type Health } from "../services/api";
import { listSaves } from "../services/games";
import { usePrefs } from "../state/prefs";
import { plane, PLANES } from "../theme/planes";
import { resolveRenderer } from "../table3d/renderer";
import { Welcome, resetWelcome, welcomeDone } from "./Welcome";
import "./home.css";

const ShowcaseView = lazy(() => import("./ShowcaseView"));

const MENU = [
  { href: "#/play", label: "Start New Game", icon: "⚔", testid: "menu-new" },
  { href: "#/play", label: "Resume Game", icon: "↺", testid: "menu-resume", resume: true },
  { href: "#/play?mode=lan", label: "LAN Lobby", icon: "⌂", testid: "menu-lan" },
  { href: "#/decks", label: "Deck Library", icon: "❖", testid: "menu-decks" },
  { href: "#/stats", label: "Pod Stats", icon: "♛", testid: "menu-stats" },
  { href: "#/settings", label: "Settings", icon: "⚙", testid: "menu-settings" },
];

export function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saves, setSaves] = useState(0);
  const planeId = usePrefs((s) => s.plane);
  const renderer = usePrefs((s) => s.renderer);
  const setPrefs = usePrefs((s) => s.set);
  const [showWelcome, setShowWelcome] = useState(!welcomeDone());
  useEffect(() => {
    getHealth().then(setHealth, (e: unknown) => setError(String(e)));
    listSaves().then((s) => setSaves(s.length), () => undefined);
  }, []);
  const p = plane(planeId);
  const idx = PLANES.findIndex((x) => x.id === p.id);
  const step = (d: number) => setPrefs({ plane: PLANES[(idx + d + PLANES.length) % PLANES.length]!.id });
  const db = health?.card_database;
  const three = resolveRenderer(renderer) === "3d";

  return (
    <div className="home-launch">
      {three && (
        <Suspense fallback={null}>
          <ShowcaseView planeId={p.id} />
        </Suspense>
      )}
      <div className="home-vignette" />
      <section className="home-menu frame ornate">
        <div className="home-star" aria-hidden>✦</div>
        <h1 className="home-title">Fyodor</h1>
        <div className="home-sub">Commander Tabletop</div>
        <nav className="home-items">
          {MENU.map((m) => (
            <a key={m.testid} href={m.resume && saves ? "#/play?tab=saves" : m.href} className="home-item" data-testid={m.testid}>
              <span className="home-icon" aria-hidden>{m.icon}</span>
              <span>{m.label}</span>
              {m.resume && saves > 0 && <span className="home-count">{saves}</span>}
            </a>
          ))}
        </nav>
        <p className="home-tag">Play Commander your way.<br />Tabletop feel. Arena convenience.</p>
        <div className="home-status">
          {error && <span className="error">Server unreachable</span>}
          {health && (
            <span title={db?.available ? `${db.printings.toLocaleString()} printings · ${db.images.toLocaleString()} images cached` : "Run scripts/update-cards.sh once while online"}>
              {db?.available ? `${db.oracle_cards.toLocaleString()} cards ready · offline` : "No card database yet"}
            </span>
          )}
          <span className="home-version">v{health?.version ?? "…"}</span>
        </div>
        {!showWelcome && <button className="tt-link home-guide" onClick={() => { resetWelcome(); setShowWelcome(true); }}>Setup guide</button>}
      </section>
      <section className="home-plane">
        <div className="home-plane-row">
          <button className="home-arrow" onClick={() => step(-1)} aria-label="Previous table theme">‹</button>
          <div>
            <div className="home-plane-label">Table</div>
            <div className="home-plane-name" data-testid="home-plane">{p.name}</div>
          </div>
          <button className="home-arrow" onClick={() => step(1)} aria-label="Next table theme">›</button>
        </div>
        <p className="home-plane-tag">{p.tagline}</p>
        <div className="home-plane-dots">{p.swatches.map((c) => <i key={c} style={{ background: c }} />)}</div>
      </section>
      {showWelcome && (
        <div className="home-welcome">
          <Welcome health={health} onClose={() => setShowWelcome(false)} />
        </div>
      )}
    </div>
  );
}
