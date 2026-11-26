import { useEffect, useRef, useState } from "react";
import { cardDbState, type Health } from "../services/api";
import { lanInfo } from "../services/games";
import { usePrefs } from "../state/prefs";
import { CardUpdateProgress, useCardData } from "./CardDataPanel";

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
  // (a dialog over the launcher: the keyboard starts in it, at the name, and Esc closes it as Close does)
  const nameField = useRef<HTMLInputElement>(null);
  useEffect(() => nameField.current?.focus({ preventScroll: true }), []);
  const finishRef = useRef(finish);
  finishRef.current = finish;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finishRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <section className="welcome panel" data-testid="welcome" role="dialog" aria-modal="true" aria-labelledby="welcome-title">
      <h2 id="welcome-title">Welcome to the table</h2>
      <ol className="welcome-steps">
        <li className="done">
          <b>Who's sitting here?</b>
          <input ref={nameField} value={name} maxLength={40} onChange={(e) => setName(e.target.value)} data-testid="welcome-name" aria-label="Your name"
            onKeyDown={(e) => { if (e.key === "Enter") { finish(); window.location.hash = "#/play"; } }} />
          <span className="hint">Saved in this browser only — there are no accounts.</span>
        </li>
        {/* (a guest isn't told about the host's card database: no step, rather than a "not downloaded yet") */}
        {cardDbState(health) !== "not-told" && <CardDatabaseStep available={!!db?.available} cards={db?.oracle_cards ?? 0} />}
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
            <span>Only this computer can connect right now. Start Fyodor without <code>--local</code> so phones and laptops can join.</span>
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

/** The card database step: on the host, a missing database downloads from here (no script to run). */
function CardDatabaseStep({ available, cards }: { available: boolean; cards: number }) {
  const { info, denied, job, running, start } = useCardData();
  const ready = info?.current.available ?? available;
  const count = info?.current.available ? info.current.oracle_cards : cards;
  return (
    <li className={ready ? "done" : "todo"}>
      <b>Card database</b>{" "}
      {ready ? (
        <span>{count.toLocaleString()} cards ready — works offline.</span>
      ) : running && job ? (
        <CardUpdateProgress job={job} />
      ) : denied || !info ? (
        <span>Not downloaded yet. The host downloads it once while online; after that no Internet is needed.</span>
      ) : (
        <span>
          Not downloaded yet: about 80 MB, once, while online. After that no Internet is needed.{" "}
          <button className="btn small primary" disabled={!info.network} onClick={() => void start()} data-testid="welcome-card-download">Download now</button>
          {job?.state === "failed" && <span className="warn"> {job.message}</span>}
        </span>
      )}
    </li>
  );
}
