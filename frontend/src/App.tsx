import { useEffect, useState } from "react";
import { getHealth, type Health } from "./services/api";

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getHealth().then(setHealth, (e: unknown) => setError(String(e)));
  }, []);
  return (
    <main className="page">
      <h1>Fyodor</h1>
      <p>Offline MTG tabletop</p>
      {health && <p className="ok">Backend {health.version}: {health.status}</p>}
      {error && <p className="error">Backend unreachable: {error}</p>}
    </main>
  );
}
