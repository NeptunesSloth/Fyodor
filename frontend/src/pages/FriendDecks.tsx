/**
 * -- friends' decks -- the Decks page's section: other computers running Fyodor on this network (found the way Play → Games on
 * your network finds them, GET /api/lan/nearby) and the decks their owners share (GET /api/lan/friend-decks, server to server).
 * Copy imports a list through the normal deck import, into a "From <computer>" folder so the shelf shows whose it was.
 */
import { useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { toast, toastError } from "../components/Toasts";
import { createDeck, deckSharing, friendDecks, moveDeckToFolder, type FriendDeck, type Sharing } from "../services/decks";
import { lanInfo } from "../services/games";
import { friendAddress, friendFolder, listCount } from "./lanBits";
import { useNearby } from "./NearbyGames";

export function FriendDecks({ onCopied }: { onCopied: () => void }) {
  const [open, setOpen] = useState(false);
  const servers = useNearby(open); // the network is only searched while the section is open
  const [off, setOff] = useState(false);
  const [mine, setMine] = useState<Sharing | null>(null);
  const [addr, setAddr] = useState("");
  const [shown, setShown] = useState<{ from: string; url: string; decks: FriendDeck[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState<string[]>([]);
  useEffect(() => {
    if (!open) return;
    lanInfo().then((i) => setOff(i.discovery === false), () => undefined);
    deckSharing().then(setMine, () => undefined);
  }, [open]);

  const browse = async (url: string, name?: string) => {
    setBusy(url);
    setError(null);
    try {
      const r = await friendDecks(url);
      setShown({ ...r, from: r.from || name || url });
      setCopied([]);
    } catch (e) {
      setShown(null);
      setError(e instanceof Error ? e.message : "Couldn't reach that computer");
    } finally {
      setBusy(null);
    }
  };
  const copy = async (d: FriendDeck, from: string) => {
    const key = `${d.name}\n${d.text}`;
    setBusy(key);
    try {
      const deck = await createDeck({ name: d.name, text: d.text });
      await moveDeckToFolder(deck.id, friendFolder(from));
      setCopied((c) => [...c, key]);
      toast(`Copied ${d.name} from ${from} into “${friendFolder(from)}”`);
      onCopied();
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(null);
    }
  };
  const typed = friendAddress(addr);

  return (
    <section className="dk-friends" aria-labelledby="dk-friends-title" data-testid="friend-decks">
      <h2 className="dk-group-head" id="dk-friends-title">
        <button className="dk-group-toggle" aria-expanded={open} aria-controls="dk-friends-body" onClick={() => setOpen(!open)}
          aria-label={`${open ? "Hide" : "Show"} friends' decks`} data-testid="friend-decks-toggle">
          <Icon name={open ? "down" : "right"} size={16} />
        </button>
        <button className="tt-link" onClick={() => setOpen(!open)}><Icon name="cards" size={16} />Friends' decks</button>
      </h2>
      {open && (
        <div id="dk-friends-body" className="dk-friends-body">
          {mine && (
            <p className="dk-none">
              {mine.enabled ? (mine.all ? "You share all your decks with this network." : "You share the decks you marked Shared (a deck's ··· menu).")
                : "Your decks aren't shared."}{" "}
              <a href="#/settings" className="tt-link">Settings → Share my decks on the network</a>
            </p>
          )}
          <div className="dk-friend-hosts" role="group" aria-label="Computers running Fyodor on this network">
            {off ? (
              <p className="dk-none">Searching the network is turned off on this computer. Type a friend's address instead.</p>
            ) : servers === null ? (
              <p className="dk-none" role="status">Looking for friends on your network…</p>
            ) : servers.length === 0 ? (
              <p className="dk-none" role="status">No other Fyodor found on your network yet. A friend's computer shows up here while Fyodor runs on it for LAN play.</p>
            ) : servers.map((s) => (
              <button key={s.url} className={`dk-folder ${shown?.url === s.url ? "on" : ""}`} aria-pressed={shown?.url === s.url} disabled={!!busy}
                onClick={() => void browse(s.url, s.name)} title={s.url} data-testid="friend-host">
                <Icon name="table" size={15} />{s.name}
              </button>
            ))}
            <form className="dk-friend-addr" onSubmit={(e) => { e.preventDefault(); if (typed) void browse(typed); }}>
              <span>{servers?.length ? "or an address" : "A friend's address"}</span>
              <input value={addr} onChange={(e) => setAddr(e.target.value)} placeholder="192.168.1.20:8000" aria-label="A friend's address" data-testid="friend-address" />
              <button className="tt-btn ghost" disabled={!typed || !!busy}>Browse</button>
            </form>
          </div>
          {busy && !shown && <p className="dk-none" role="status">Asking…</p>}
          {error && <p className="dk-none dk-warn" role="alert">{error}</p>}
          {shown && (
            <div className="dk-friend-list">
              <h3>{shown.from}{shown.decks.length ? ` shares ${shown.decks.length === 1 ? "one deck" : `${shown.decks.length} decks`}` : " shares no decks right now"}</h3>
              <ul>
                {shown.decks.map((d, i) => {
                  const key = `${d.name}\n${d.text}`;
                  const done = copied.includes(key);
                  return (
                    <li key={i} data-testid="friend-deck">
                      <span className="dk-friend-name"><b>{d.name}</b>{d.commanders.length > 0 && d.commanders.join(" & ") !== d.name && <span>{d.commanders.join(" & ")}</span>}</span>
                      <span className="dk-friend-n">{listCount(d.text)} cards</span>
                      <button className="tt-btn" disabled={done || !!busy} onClick={() => void copy(d, shown.from)} aria-label={`Copy ${d.name} into my decks`}>
                        {done ? <><Icon name="check" size={14} />Copied</> : busy === key ? "Copying…" : "Copy to my decks"}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
