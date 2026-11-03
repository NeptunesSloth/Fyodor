import { useCallback, useEffect, useRef, useState } from "react";
import { KeepArtSetting } from "./ArtKeeper";
import { toast, toastError } from "../components/Toasts";
import { ApiError } from "../services/api";
import {
  bulkName, cardData, checkCardData, progressFraction, progressText, scryfallDay, startCardUpdate,
  type CardCheck, type CardDataInfo, type CardJob,
} from "../services/cardData";

/** The host's card database and its update job, polled while the update runs. */
export function useCardData() {
  const [info, setInfo] = useState<CardDataInfo | null>(null);
  const [denied, setDenied] = useState(false);
  const [check, setCheck] = useState<CardCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const wasRunning = useRef(false);
  const refresh = useCallback(() => cardData().then(setInfo, (e: unknown) => {
    if (e instanceof ApiError && e.status === 403) setDenied(true);
  }), []);
  useEffect(() => void refresh(), [refresh]);
  const job = info?.job ?? null;
  const running = job?.state === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => void refresh(), 700);
    return () => clearInterval(timer);
  }, [running, refresh]);
  useEffect(() => {
    if (wasRunning.current && job && job.state !== "running") {
      if (job.state === "done") toast(job.message);
      else toastError(new Error(`Card update failed: ${job.message}`));
    }
    wasRunning.current = running;
  }, [job, running]);
  const start = async (force = false) => {
    try {
      const started = await startCardUpdate(force);
      setCheck(null);
      setInfo((i) => (i ? { ...i, job: started } : i));
    } catch (e) {
      toastError(e);
    }
  };
  const lookForNew = async () => {
    setChecking(true);
    try {
      setCheck(await checkCardData());
    } catch (e) {
      toastError(e);
    } finally {
      setChecking(false);
    }
  };
  return { info, denied, check, checking, job, running, start, lookForNew };
}

export function CardUpdateProgress({ job }: { job: CardJob }) {
  const fraction = progressFraction(job);
  return (
    <div className="carddata-progress" data-testid="card-update-progress" role="status">
      <span>{progressText(job)}</span>
      <div className={`carddata-bar ${fraction === null ? "unknown" : ""}`} aria-hidden>
        <i style={{ width: `${Math.round((fraction ?? 1) * 100)}%` }} />
      </div>
    </div>
  );
}

/** Settings → Card database: what the host has, and a workshop-style "update available" flow. */
export function CardDataSection() {
  const { info, denied, check, checking, job, running, start, lookForNew } = useCardData();
  const db = info?.current;
  return (
    <section id="card-data" data-testid="card-data">
      <h2>Card database</h2>
      {denied ? (
        <p className="hint">Card data is downloaded and updated on the host computer (the one running Fyodor).</p>
      ) : db && info ? (
        <div className="carddata">
          {db.available ? (
            <>
              <p className="carddata-count"><span className="numeral">{db.oracle_cards.toLocaleString()}</span> cards
                <span className="hint"> · {db.printings.toLocaleString()} printings · {db.images.toLocaleString()} images cached</span></p>
              <p className="hint">Scryfall data from {scryfallDay(db.bulk_updated_at)}{db.bulk_type ? ` (${bulkName(db.bulk_type)})` : ""}.</p>
            </>
          ) : (
            <p><b>No card database yet.</b> Download it once while online (about 80 MB); after that Fyodor works without the Internet.</p>
          )}
          {running && job ? <CardUpdateProgress job={job} /> : (
            <>
              {job && job.state === "failed" && <p className="warn">The last update failed: {job.message}</p>}
              {job && job.state === "done" && <p className="hint">{job.message}</p>}
              <div className="row carddata-actions">
                {!db.available ? (
                  <button className="btn primary" disabled={!info.network} onClick={() => void start()} data-testid="card-download">Download card database</button>
                ) : check?.available ? (
                  <>
                    <span className="carddata-new" data-testid="card-update-available">
                      New card data from {scryfallDay(check.remote_updated_at)}{check.size ? ` · about ${Math.round(check.size / 1e6)} MB` : ""}
                    </span>
                    <button className="btn primary" onClick={() => void start()} data-testid="card-update">Update now</button>
                  </>
                ) : check ? (
                  <span className="carddata-current" data-testid="card-up-to-date">Up to date with Scryfall.</span>
                ) : null}
                {db.available && (
                  <button className="btn" disabled={checking || !info.network} onClick={() => void lookForNew()} data-testid="card-check">
                    {checking ? "Checking…" : "Check for new cards"}
                  </button>
                )}
              </div>
            </>
          )}
          {!info.network && <p className="hint">Network access is turned off on this computer (FYODOR_ALLOW_NETWORK=0).</p>}
          <p className="hint">Tables keep playing while it updates.</p>
          <KeepArtSetting />
        </div>
      ) : null}
    </section>
  );
}
