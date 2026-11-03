/**
 * Keep deck art for offline play (backend app/cards/art_keeper.py): saving a deck while this computer is online downloads its
 * art in the background, so a game night with no internet still shows real cards. Settings has the switch (on by default);
 * the Decks page shows one quiet line while art is downloading.
 */
import { useEffect, useState } from "react";
import { toastError } from "../components/Toasts";
import { artKeeper, setArtKeeper, type ArtKeeperStatus } from "../services/decks";

/** The keeper's state, asked again every few seconds while it is working (null: not the host computer, or not known yet). */
function useArtKeeper(): [ArtKeeperStatus | null, (s: ArtKeeperStatus) => void] {
  const [status, setStatus] = useState<ArtKeeperStatus | null>(null);
  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    const poll = () => {
      artKeeper().then((s) => {
        if (!live) return;
        setStatus(s);
        if (s.running || (s.pending > 0 && s.network && s.enabled)) timer = window.setTimeout(poll, 3000);
      }, () => undefined);
    };
    poll();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, []);
  return [status, setStatus];
}

/** Decks page: "Keeping card art for offline play: Goblins, 40 of 98". Nothing when there is nothing to say. */
export function ArtKeeperLine() {
  const [s] = useArtKeeper();
  if (!s?.enabled || !s.running || !s.deck) return null;
  return (
    <p className="dk-art-line" role="status" data-testid="art-keeper">
      Keeping card art for offline play: {s.deck}{s.total ? `, ${s.done ?? 0} of ${s.total}` : ""}
    </p>
  );
}

/** Settings → Card database: the switch. */
export function KeepArtSetting() {
  const [s, setStatus] = useArtKeeper();
  if (!s) return null;
  return (
    <>
      <label className="check">
        <input type="checkbox" checked={s.enabled} data-testid="keep-art"
          onChange={(e) => setArtKeeper(e.target.checked).then(setStatus, toastError)} />
        {" "}Keep deck art for offline play: when you save a deck while online, its card art downloads in the background
      </label>
      {s.enabled && s.pending > 0 && (
        <p className="hint">{s.pending === 1 ? "One deck waits" : `${s.pending} decks wait`} for this computer to be online to fetch its art.</p>
      )}
    </>
  );
}
