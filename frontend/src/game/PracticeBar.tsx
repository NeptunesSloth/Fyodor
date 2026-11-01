import { useEffect, useState } from "react";
import { toast } from "../components/Toasts";
import { GameConnection } from "../services/gameSocket";
import { seatToken } from "../services/games";
import { closePractice } from "../services/night";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { EventTracker, liveHash, liveLine, liveOver, practiceLink } from "./eliminationHub";
import "./elimination.css";

/**
 * The practice table's link to the live game (docs/ELIMINATION_HUB.md): a small pill with the live turn, the major
 * public events as they happen, and RETURN TO LIVE GAME. The live seat stays connected (others see you at the table,
 * not "disconnected"), and receives only the public view it always had. When the live game ends, or the pod moves on,
 * the player is taken back to the result; the practice table is put away.
 */
export function PracticeBar({ id }: { id: string }) {
  const fromView = useGame((s) => (s.view?.game.id === id ? s.view.game.practice : undefined));
  const link = fromView ?? practiceLink(id);
  if (!link) return null;
  return <PracticePill of={link.of} seat={link.seat} game={link.game} local={link.local} />;
}

const NEWS_MS = 9000;

function PracticePill({ of, seat, game, local }: { of: string; seat: string; game: number; local: boolean }) {
  const [line, setLine] = useState("Connecting to the live game…");
  const [news, setNews] = useState<{ text: string; at: number } | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  const speed = usePrefs((s) => s.animationSpeed) || 1;
  const back = liveHash({ of, seat, local });

  useEffect(() => {
    const tracker = new EventTracker();
    let done = false;
    const conn = new GameConnection(of, { token: seatToken(of), viewer: local ? seat : null }, {
      onState: (live) => {
        const fresh = tracker.take(live.game.events);
        if (fresh.length) setNews({ text: fresh[fresh.length - 1]!.text, at: Date.now() });
        if (liveOver({ game }, live)) return leave(live.game.night?.result ? "The live game is over" : "The pod has started the next game");
        setLine(liveLine(live));
      },
      onLobby: () => leave("The pod is back in the lobby"),
      onStatus: (status, detail) => {
        if (status === "reconnecting") setLine("Reconnecting to the live game…");
        if (status === "closed" && !done) setGone(detail ?? "The live game can't be reached");
      },
      onClosedByServer: (reason) => {
        done = true;
        setGone(reason);
      },
    });
    function leave(why: string) {
      if (done) return;
      done = true;
      conn.close();
      void closePractice(of, local ? seat : undefined).catch(() => undefined);
      toast(`${why}: back to the table.`);
      window.location.hash = back;
    }
    conn.connect();
    return () => {
      done = true;
      conn.close();
    };
  }, [of, seat, game, local, back]);

  useEffect(() => {
    if (!news) return;
    const t = window.setTimeout(() => setNews(null), NEWS_MS / speed);
    return () => window.clearTimeout(t);
  }, [news, speed]);

  return (
    <div className="practice-pill" role="region" aria-label="Practice table" data-testid="practice-pill">
      <span className="practice-tag" title="Only you see this table. Nothing here reaches the live game.">Practice</span>
      <span className={`practice-live ${news ? "news" : ""}`} aria-live="polite">
        {gone ?? (news ? news.text : `Live game · ${line}`)}
      </span>
      <a className="tt-btn brass" href={gone ? "#/play" : back} data-testid="return-live">{gone ? "Back to Play" : "Return to live game"}</a>
    </div>
  );
}
