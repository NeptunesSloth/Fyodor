import { useEffect, useState } from "react";
import { getHealth, type Health } from "../services/api";

export function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getHealth().then(setHealth, (e: unknown) => setError(String(e)));
  }, []);
  const db = health?.card_database;
  return (
    <div className="page home">
      <section className="hero">
        <h1>Fyodor</h1>
        <p>An offline tabletop for Magic: The Gathering. You play the rules; the table handles the rest.</p>
        <div className="hero-actions">
          <a className="btn primary" href="#/play">Play</a>
          <a className="btn" href="#/decks">Decks</a>
          <a className="btn" href="#/cards">Card browser</a>
        </div>
      </section>
      <section className="status-panel">
        <h2>Status</h2>
        {error && <p className="error">Backend unreachable: {error}</p>}
        {health && (
          <ul>
            <li>Backend <b>{health.version}</b> — {health.status}</li>
            {db?.available ? (
              <li>
                Card database: <b>{db.oracle_cards.toLocaleString()}</b> cards, {db.printings.toLocaleString()} printings,{" "}
                {db.tokens.toLocaleString()} tokens · {db.images.toLocaleString()} images cached
                {db.bulk_updated_at && <> · Scryfall data from {db.bulk_updated_at.slice(0, 10)}</>}
              </li>
            ) : (
              <li className="warn">
                No card database yet. Run <code>scripts/update-cards.sh</code> once while online.
              </li>
            )}
          </ul>
        )}
      </section>
    </div>
  );
}
