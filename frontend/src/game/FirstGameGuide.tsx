/**
 * -- first-game guide -- on a player's first Sandbox game, an offer to walk through one turn: play a land, cast a spell, attack,
 * pass. Each step rings the real control it is about (the hand, the turn dial's big button, End turn / Next turn) with a short note
 * beside it; nothing is pressed for the player and the table stays usable underneath. Offered once on this device (Help brings it
 * back: showFirstGameGuide). Static rings: nothing moves, so there is no motion to reduce.
 */
import { useEffect, useState } from "react";
import { useGame } from "../state/gameStore";
import { isSandbox } from "./tableFormat";

const KEY = "fyodor.firstGameGuide";
const OPEN = "fyodor:first-game-guide";

// (tried in turn: the first that is on the page is ringed, all of its matches together: every card in the hand)
const HAND = ".hand-empty|.hand .hand-card|.hand";
const STEPS = [
  { title: "Play a land", at: HAND, text: "Drag a land from your hand onto your side of the table, or focus it and press Enter. One land each turn. (No cards in hand? D draws one.)" },
  { title: "Cast a spell", at: HAND, text: "Drag a spell onto the table the same way. With rules automation on, Fyodor asks for the mana and any targets; in free play you tap your lands yourself (click one, or press T)." },
  { title: "Attack", at: ".turn-dial-wrap .td-pass", text: "The turn dial's big button moves the turn on. In combat, choose your attackers on the table (in free play, tap them)." },
  { title: "Pass the turn", at: "[data-testid='pass-turn']|.turn-dial-wrap .next-turn", text: "Done? End turn (Next turn in free play) hands the turn to the next player. That's a whole turn." },
];

const seen = () => { try { return localStorage.getItem(KEY) === "done"; } catch { return true; } };
const markSeen = () => { try { localStorage.setItem(KEY, "done"); } catch { /* private mode: offered again next time */ } };

/** Help's "Show the first-game guide": offered again, at once if a Sandbox table is open. */
export function showFirstGameGuide(): void {
  try { localStorage.removeItem(KEY); } catch { /* nothing kept */ }
  window.dispatchEvent(new Event(OPEN));
}

type Box = { left: number; top: number; width: number; height: number };

export function FirstGameGuide({ me }: { me: string }) {
  const sandbox = useGame((s) => isSandbox(s.view?.game.format));
  const seated = useGame((s) => !!s.view?.players.some((p) => p.id === me));
  const [step, setStep] = useState(() => (seen() ? -2 : -1)); // -2: off, -1: the offer, 0..: a step
  const [box, setBox] = useState<Box | null>(null);
  useEffect(() => {
    const open = () => setStep(-1);
    window.addEventListener(OPEN, open);
    return () => window.removeEventListener(OPEN, open);
  }, []);
  const target = step >= 0 ? STEPS[step]!.at : null;
  useEffect(() => {
    if (!target) return setBox(null);
    const measure = () => {
      const els = target.split("|").map((q) => [...document.querySelectorAll(q)]).find((l) => l.length) ?? [];
      const box = (e: Element) => { // (an empty hand's line spans the table: its words are what is ringed)
        if (!e.classList.contains("hand-empty")) return e.getBoundingClientRect();
        const range = document.createRange();
        range.selectNodeContents(e);
        return range.getBoundingClientRect();
      };
      const rs = els.map(box).filter((x) => x.width > 0);
      const left = Math.min(...rs.map((x) => x.left)), top = Math.min(...rs.map((x) => x.top));
      const r = rs.length ? { left, top, width: Math.max(...rs.map((x) => x.right)) - left, height: Math.max(...rs.map((x) => x.bottom)) - top } : null;
      setBox((b) => (!r || !r.width ? null : b && b.left === r.left && b.top === r.top && b.width === r.width && b.height === r.height ? b : { left: r.left, top: r.top, width: r.width, height: r.height }));
    };
    measure();
    const t = window.setInterval(measure, 500); // (the dial and the hand change size as the game goes: cheap, no rAF loop)
    window.addEventListener("resize", measure);
    return () => { window.clearInterval(t); window.removeEventListener("resize", measure); };
  }, [target]);
  useEffect(() => {
    if (step < -1) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { markSeen(); setStep(-2); } };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [step]);
  if (step < -1 || !sandbox || !seated) return null;
  const close = () => { markSeen(); setStep(-2); };
  if (step === -1) {
    return (
      <aside className="fg-guide plaque fg-offer" aria-label="First-game guide" data-testid="first-game-guide">
        <p className="fg-title">First game here?</p>
        <p className="fg-text">A quick walk through one turn: play a land, cast a spell, attack and pass, pointing at the real buttons.</p>
        <div className="fg-actions">
          <button className="tt-btn brass" data-testid="guide-start" onClick={() => setStep(0)}>Show me</button>
          <button className="tt-btn ghost" data-testid="guide-skip" onClick={close}>No thanks</button>
        </div>
      </aside>
    );
  }
  const s = STEPS[step]!;
  const W = 320;
  const above = box ? box.top > 190 : false;
  const style: React.CSSProperties = box
    ? { left: Math.round(Math.min(Math.max(16, box.left + box.width / 2 - W / 2), window.innerWidth - W - 16)), ...(above ? { bottom: Math.round(window.innerHeight - box.top + 14) } : { top: Math.round(box.top + box.height + 14) }) }
    : {};
  return (
    <>
      {box && <div className="fg-ring" aria-hidden style={{ left: box.left - 6, top: box.top - 6, width: box.width + 12, height: box.height + 12 }} />}
      <aside className={`fg-guide plaque${box ? "" : " fg-offer"}`} aria-label={`First-game guide: ${s.title}`} data-testid="first-game-guide" style={style}>
        <p className="fg-title">{s.title} <span className="fg-count">{step + 1} of {STEPS.length}</span></p>
        <p className="fg-text">{s.text}</p>
        <div className="fg-actions">
          {step > 0 && <button className="tt-btn ghost" onClick={() => setStep(step - 1)}>Back</button>}
          {step < STEPS.length - 1
            ? <button className="tt-btn brass" data-testid="guide-next" onClick={() => setStep(step + 1)}>Next</button>
            : <button className="tt-btn brass" data-testid="guide-done" onClick={close}>Done</button>}
          <button className="tt-btn ghost" onClick={close}>Close guide <kbd aria-hidden>Esc</kbd></button>
        </div>
      </aside>
    </>
  );
}
