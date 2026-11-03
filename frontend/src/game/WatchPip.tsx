import { useEffect, useState } from "react";
import { watchLive, type LiveSummary } from "../services/spectate";
import { LETHAL_COMMANDER, pipHeadline, pipRows, pipStack } from "./spectate";

const MIN_KEY = "fyodor.practice.pipMinimized";

function storedMin(): boolean {
  try {
    return localStorage.getItem(MIN_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * WATCH + PRACTICE (docs/SPECTATOR_ACTIVITIES_MILESTONE.md §1): the live game in the practice table's corner. A compact
 * public summary (life, poison, the heaviest commander damage, whose turn, the stack, the latest public log lines) rather
 * than a second live table: the server builds it from the spectator view. It refreshes after each live update (``tick``),
 * minimizes to a chip, and a click anywhere on it goes back to the live table.
 */
export function WatchPip({ of, seat, local, tick, back }: { of: string; seat: string; local: boolean; tick: number; back: string }) {
  const [summary, setSummary] = useState<LiveSummary | null>(null);
  const [failed, setFailed] = useState(false);
  const [min, setMin] = useState(storedMin);

  useEffect(() => {
    let live = true;
    // a burst of live updates (a combat, a resolving stack) asks once
    const t = window.setTimeout(() => {
      watchLive(of, local ? seat : undefined).then((s) => {
        if (!live) return;
        setSummary(s);
        setFailed(false);
      }, () => live && setFailed(true));
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [of, seat, local, tick]);

  const toggle = () => {
    setMin((m) => {
      try {
        localStorage.setItem(MIN_KEY, m ? "0" : "1");
      } catch {
        /* this page only */
      }
      return !m;
    });
  };

  if (min || !summary) {
    return (
      <div className="watch-pip mini" role="region" aria-label="Live game">
        <a className="watch-chip" href={back} title="Return to the live game">
          <span className="watch-tag">Live</span>
          {summary ? pipHeadline(summary) : failed ? "Live game unavailable" : "Loading the live game…"}
        </a>
        {summary && <button className="tt-icon" onClick={toggle} aria-label="Show the live game" title="Show the live game">▢</button>}
      </div>
    );
  }
  const stack = pipStack(summary);
  return (
    <div className="watch-pip" role="region" aria-label="Live game" data-testid="watch-pip">
      <div className="watch-head">
        <span className="watch-tag">Live</span>
        <span className="watch-line">{pipHeadline(summary)}</span>
        <button className="tt-icon" onClick={toggle} aria-label="Minimize the live game" title="Minimize">–</button>
      </div>
      <a className="watch-body" href={back} title="Return to the live game">
        <ul className="watch-players">
          {pipRows(summary).map((r) => (
            <li key={r.id} className={`${r.out ? "out" : ""} ${r.active ? "active" : ""}`} style={{ ["--seat" as string]: r.color ?? "var(--frame)" }}>
              <span className="watch-dot" aria-hidden />
              <span className="watch-name">{r.name}{r.active ? <span className="sr-only"> (their turn)</span> : null}</span>
              {r.out ? <span className="watch-out">out</span> : <b className="watch-life" aria-label={`${r.life} life`}>{r.life}</b>}
              {!r.out && r.poison > 0 && <span className="watch-poison" title="Poison counters">☠ {r.poison}</span>}
              {!r.out && r.commander && (
                <span className={`watch-cmd ${r.commander.damage >= LETHAL_COMMANDER - 5 ? "warn" : ""}`} title={`Commander damage from ${r.commander.name}`}>
                  ⚔ {r.commander.damage}
                </span>
              )}
            </li>
          ))}
        </ul>
        {(stack || summary.waiting) && <p className="watch-stack">{[stack, summary.waiting].filter(Boolean).join(" · ")}</p>}
        {summary.log.length > 0 && (
          <ol className="watch-log" aria-label="Latest log lines">
            {summary.log.slice(-3).map((line, i) => <li key={`${summary.revision}-${i}`}>{line}</li>)}
          </ol>
        )}
      </a>
    </div>
  );
}
