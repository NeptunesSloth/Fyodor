import { useEffect, useState } from "react";
import type { Health } from "../services/api";
import { lanInfo } from "../services/games";
import { usePrefs } from "../state/prefs";

const DONE_KEY = "fyodor.welcomeDone";

export function welcomeDone(): boolean {
  try {
    return localStorage.getItem(DONE_KEY) === "1";
  } catch {
    return false;
  }
}

function markDone(done: boolean) {
  try {
    if (done) localStorage.setItem(DONE_KEY, "1");
    else localStorage.removeItem(DONE_KEY);
  } catch {
    /* private window: the guide just shows again next time */
  }
}

/**
 * First-run guide on the host computer: name, card database, a first deck and how the rest of
 * the pod joins. Nothing here needs an account; it only checks this machine.
 */
export function Welcome({ health, onClose }: { health: Health | null; onClose: () => void }) {
  const prefs = usePrefs();
  const profile = prefs.profiles.find((p) => p.id === prefs.active)!;
  const [name, setName] = useState(profile.name);
  const [lan, setLan] = useState<{ addresses: string[]; port: number; reachable: boolean } | null | "remote">(null);
  useEffect(() => {
    lanInfo().then(setLan, () => setLan("remote"));
  }, []);
  const db = health?.card_database;
  const finish = () => {
    if (name.trim()) prefs.updateProfile(profile.id, { name: name.trim().slice(0, 40) });
    markDone(true);
    onClose();
  };

  return (
    <section className="welcome panel" data-testid="welcome">
      <h2>Welcome to the table</h2>
      <ol className="welcome-steps">
        <li className="done">
          <b>Who's sitting here?</b>
          <input value={name} maxLength={40} onChange={(e) => setName(e.target.value)} data-testid="welcome-name" aria-label="Your name" />
          <span className="hint">Saved in this browser only — there are no accounts.</span>
        </li>
        <li className={db?.available ? "done" : "todo"}>
          <b>Card database</b>{" "}
          {db?.available ? (
            <span>{db.oracle_cards.toLocaleString()} cards ready — works offline.</span>
          ) : (
            <span>Not downloaded yet. Run <code>scripts/update-cards.sh</code> once while online; after that no Internet is needed.</span>
          )}
        </li>
        <li>
          <b>Bring a deck</b> <a href="#/decks">Import a list or an Archidekt link</a>, or let each player bring their own in the LAN lobby.
        </li>
        <li className={lan && lan !== "remote" && lan.reachable ? "done" : ""}>
          <b>Invite the pod</b>{" "}
          {lan === "remote" ? (
            <span>You're on a player device — ask the host for the room code.</span>
          ) : lan?.reachable ? (
            <span>Others open {lan.addresses.map((a) => <code key={a}>http://{a}:{lan.port}</code>)} on the same network.</span>
          ) : (
            <span>Only this computer can connect right now. Start with <code>scripts/start.sh --lan</code> so phones and laptops can join.</span>
          )}
        </li>
      </ol>
      <div className="row">
        <a className="btn primary" href="#/play" onClick={finish} data-testid="welcome-done">Let's play</a>
        <button className="btn" onClick={finish}>Close</button>
      </div>
    </section>
  );
}

export const resetWelcome = () => markDone(false);
