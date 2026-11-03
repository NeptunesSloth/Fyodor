/**
 * Games on your network: the LAN tables other computers running Fyodor answer with (GET /api/lan/nearby, this computer
 * only). The Play page lists them with Join and Watch; the launcher shows one line when a lobby has a free seat. Join opens
 * the host computer's Play page with the room code and your name (`#/play?code=…&name=…&join=1`), and your deck library goes
 * along for your seat, as players bring their decks to a game night (POST /api/lan/send-decks: server to server, LAN only).
 */
import { useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { lanInfo, nearbyGames, sendMyDecks } from "../services/games";
import { activeProfile } from "../state/prefs";
import { firstOpenLobby, joinLink, nearbyRows, tableStatus, type NearbyRow, type NearbyServer } from "./lanBits";
import { TableMosaic } from "./tableBits";

const POLL_MS = 4000;

/**
 * The servers found on the network, asked every few seconds while this page is visible (never while it's hidden), or null
 * before the first answer. The state only changes when the answer does, so the page doesn't redraw for nothing.
 */
export function useNearby(enabled: boolean): NearbyServer[] | null {
  const [servers, setServers] = useState<NearbyServer[] | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let busy = false;
    let timer: number | undefined;
    let last = "";
    const poll = async () => {
      if (!alive || busy || document.hidden) return;
      busy = true;
      try {
        const found = await nearbyGames();
        const key = JSON.stringify(found);
        if (alive && key !== last) {
          last = key;
          setServers(found);
        }
      } catch {
        if (alive) setServers((s) => s ?? []);
      } finally {
        busy = false;
      }
      if (alive && !document.hidden) timer = window.setTimeout(() => void poll(), POLL_MS);
    };
    const onVisibility = () => {
      window.clearTimeout(timer);
      if (!document.hidden) void poll();
    };
    void poll();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      alive = false;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled]);
  return servers;
}

/** Go to the table's computer: bring this computer's decks for a Join (not to watch), then open its Play page. */
async function goTo(row: NearbyRow, watch: boolean): Promise<void> {
  let handoff: string | null = null;
  if (!watch) {
    try {
      handoff = (await sendMyDecks(row.server.url)).token;
    } catch {
      handoff = null; // their computer couldn't take the decks: join anyway (a list can still be pasted there)
    }
  }
  window.location.assign(joinLink(row.server.url, row.table.code, { name: activeProfile().name, watch, handoff }));
}

/** The Play page's section, on the computer you run Fyodor on. `deckCount`: your library, which goes along when you join. */
export function NearbyGames({ deckCount }: { deckCount: number }) {
  const servers = useNearby(true);
  const [off, setOff] = useState(false);
  const [going, setGoing] = useState<string | null>(null);
  useEffect(() => {
    lanInfo().then((i) => setOff(i.discovery === false), () => undefined);
  }, []);
  const rows = nearbyRows(servers ?? []);
  const go = (row: NearbyRow, watch: boolean) => {
    if (going) return;
    setGoing(`${row.server.url} ${row.table.id} ${watch}`);
    void goTo(row, watch).catch(() => setGoing(null));
  };

  return (
    <section className="pg-near" aria-labelledby="pg-near-title" data-testid="nearby-games">
      <h2 id="pg-near-title"><Icon name="table" size={18} />Games on your network</h2>
      {off ? (
        <p className="pg-empty">Searching the network is turned off on this computer (FYODOR_DISCOVERY=0).</p>
      ) : servers === null ? (
        <p className="pg-empty" role="status">Looking for games on your network…</p>
      ) : rows.length === 0 ? (
        <p className="pg-empty" role="status">No games found yet. When a friend opens a LAN table on their computer it shows up here.</p>
      ) : (
        <ul className="pg-tiles" aria-label="Tables on other computers">
          {rows.map((row) => {
            const t = row.table;
            const seats = t.phase === "lobby"
              ? [...t.players.map((name) => ({ name })), ...Array.from({ length: Math.max(0, t.open) }, () => ({ name: "Open seat", open: true }))]
              : t.players.map((name) => ({ name }));
            const key = `${row.server.url} ${t.id}`;
            return (
              <li key={key} className="pg-tile pg-near-tile" data-testid="nearby-table">
                <TableMosaic seats={seats.slice(0, Math.max(1, t.seats))} />
                <div className="pg-tile-main">
                  <h3>
                    <span className="pg-tile-name">{t.name}</span>
                    {t.has_password && <Icon name="lock" size={14} label="Password" className="pg-lock" />}
                  </h3>
                  <p className="pg-meta">
                    <span className="pg-host" title={row.server.url}>{row.server.name}</span>
                    <span>{tableStatus(t)}</span>
                  </p>
                  {t.players.length > 0 && <p className="pg-who">{t.players.join(", ")}</p>}
                </div>
                <div className="pg-tile-acts">
                  {t.open > 0 && (
                    <button className="tt-btn pg-go" disabled={!!going} onClick={() => go(row, false)} aria-label={`Join “${t.name}” on ${row.server.name}`}>
                      {going === `${key} false` ? "Joining…" : "Join"}
                    </button>
                  )}
                  <button className="tt-btn" disabled={!!going} onClick={() => go(row, true)} aria-label={`Watch “${t.name}” on ${row.server.name}`}>Watch</button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {deckCount > 0 && (
        <p className="pg-bring" data-testid="bring-decks">
          <Icon name="cards" size={15} />
          <span>
            {deckCount === 1 ? "Your deck comes" : `Your ${deckCount} decks come`} with you when you join: the host's computer shows{" "}
            {deckCount === 1 ? "it" : "them"} at your seat only, until the game starts.
          </span>
        </p>
      )}
      <p className="pg-near-hint">
        Both computers need to be on the same network. If a friend's table doesn't show up, their firewall may be blocking Fyodor:
        they allow it for private networks, or tell you the address on their screen.
      </p>
    </section>
  );
}

/** The launcher's line: a lobby with a free seat on another computer, one click from joining. */
export function NearbyLine({ enabled }: { enabled: boolean }) {
  const servers = useNearby(enabled);
  const row = firstOpenLobby(servers);
  const [going, setGoing] = useState(false);
  if (!row) return null;
  return (
    <p className="home-nearby" data-testid="home-nearby">
      <Icon name="table" size={16} />
      <span className="home-nearby-text"><b>{row.table.name}</b> is open on {row.server.name}</span>
      <button className="tt-link home-nearby-join" disabled={going}
        onClick={() => { setGoing(true); void goTo(row, false).catch(() => setGoing(false)); }}>
        {going ? "Joining…" : "Join"}
      </button>
    </p>
  );
}
