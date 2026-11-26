import { useEffect, useRef, useState } from "react";
import { toastError } from "../components/Toasts";
import { ApiError } from "../services/api";
import { HOST_ONLY_NOTE } from "../services/hostSession";
import { applyUpdate, discardUpdate, updateStatus, uploadUpdate, type UpdateStatus, type UpdateSummary } from "../services/update";
import { installedText, percent, planLines, resultText, sizeText, waitForRestart } from "./updateBits";
import { SettingsSection } from "./SettingsSection";

type Phase =
  | { at: "idle" }
  | { at: "sending"; name: string; size: number; done: number }
  | { at: "checking"; name: string }
  | { at: "ready"; plan: UpdateSummary }
  | { at: "installing"; plan: UpdateSummary }
  | { at: "restarting"; plan: UpdateSummary; closes: boolean; stuck?: string; done?: string };

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const healthy = () => fetch("/api/health", { cache: "no-store" }).then((r) => r.ok, () => false);

/**
 * -- install update -- Settings → Update Fyodor (host computer only): pick an update zip, see what it replaces, install it. Fyodor saves the
 * games, tells everyone at the tables, closes, the updater copies the files (backing up what it replaces) and starts Fyodor again; this page
 * waits for it and reloads. In a source checkout the button is off, with the reason.
 */
export function UpdateSection() {
  const [st, setSt] = useState<UpdateStatus | null>(null);
  const [denied, setDenied] = useState(false);
  const [phase, setPhase] = useState<Phase>({ at: "idle" });
  const file = useRef<HTMLInputElement>(null);
  const load = () => updateStatus().then((s) => {
    setSt(s);
    if (s.pending) setPhase((p) => (p.at === "idle" ? { at: "ready", plan: s.pending! } : p)); // (checked earlier, never installed)
  }, (e: unknown) => {
    if (e instanceof ApiError && e.status === 403) setDenied(true);
  });
  useEffect(() => void load(), []);

  const pick = async (f: File) => {
    setPhase({ at: "sending", name: f.name, size: f.size, done: 0 });
    try {
      const plan = await uploadUpdate(f, (fraction) => setPhase((p) => (p.at === "sending" ? (fraction >= 1 ? { at: "checking", name: p.name } : { ...p, done: fraction }) : p)));
      setPhase({ at: "ready", plan });
    } catch (e) {
      setPhase({ at: "idle" });
      toastError(e);
    }
  };
  const cancel = async () => {
    setPhase({ at: "idle" });
    await discardUpdate().catch(() => undefined);
  };
  const install = async (plan: UpdateSummary) => {
    setPhase({ at: "installing", plan });
    let closes = plan.closes_window;
    try {
      closes = (await applyUpdate()).closes_window;
    } catch (e) {
      setPhase({ at: "ready", plan });
      toastError(e);
      return;
    }
    setPhase({ at: "restarting", plan, closes });
    // (the updater stops a Fyodor that hasn't closed after 90 s: "stuck" only after that)
    const how = await waitForRestart(healthy, sleep, { downWithin: 120_000 });
    if (how === "back" && closes) {
      // the update replaced Fyodor's own window and the new Fyodor opened a new one: this page (another browser) stays as it is, not a twin
      setPhase({ at: "restarting", plan, closes, done: "Fyodor is back with the update, in a new window. You can close this one." });
      return;
    }
    if (how === "back") {
      window.location.reload();
      return;
    }
    setPhase({ at: "restarting", plan, closes, stuck: how === "stuck"
      ? "Fyodor didn't close for the update. Close its window (the one with the black console) and start Fyodor again."
      : `Fyodor hasn't come back yet. Start Fyodor again; if the update failed, the old version is back. What happened is in ${st?.log ?? "update.log"}.` });
  };

  const available = !!st?.available;
  const busy = phase.at !== "idle" && phase.at !== "ready";
  const last = resultText(st?.last, (iso) => new Date(iso).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }));
  return (
    <SettingsSection id="st-update" testId="update">
      {denied ? (
        <p className="st-note st-away">Updates are installed on the host computer (the one running Fyodor). {HOST_ONLY_NOTE}</p>
      ) : (
        <div className="st-plate">
          {st && (st.available || last) && (
            <div className="update-now" data-testid="update-installed">
              {st.available && <p>{installedText(st)}</p>}
              {last && <p className={st.last?.ok ? "hint" : "warn"} data-testid="update-last">{last}{st.last?.ok ? "" : <> The log: <code>{st.log}</code></>}</p>}
            </div>
          )}
          <div className="st-backup-acts">
            <button className="tt-btn brass" data-testid="update-pick" disabled={!available || busy} aria-describedby="update-why"
              onClick={() => file.current?.click()}>Install update…</button>
            <input ref={file} type="file" hidden accept=".zip,application/zip" data-testid="update-file" onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void pick(f);
            }} />
            <span className="st-note" id="update-why" data-testid="update-why">
              {st && !available ? st.reason : <>Choose a <i>Fyodor-update</i> zip. Fyodor checks it and shows what it replaces before anything changes.</>}
            </span>
          </div>

          {phase.at === "sending" && (
            <div className="update-progress" role="status" data-testid="update-progress">
              <progress max={100} value={percent(phase.done)} aria-label="Sending the update to Fyodor" />
              <span>Reading {phase.name} into Fyodor… {percent(phase.done)}% of {sizeText(phase.size)}</span>
            </div>
          )}
          {phase.at === "checking" && (
            <div className="update-progress" role="status" data-testid="update-progress">
              <progress aria-label="Checking the update" />
              <span>Checking every file in {phase.name}…</span>
            </div>
          )}
          {(phase.at === "ready" || phase.at === "installing") && <PlanView plan={phase.plan} installing={phase.at === "installing"}
            onInstall={() => void install(phase.plan)} onCancel={() => void cancel()} />}
          {phase.at === "restarting" && (
            <div className="update-restart" role="status" aria-live="polite" data-testid="update-restarting">
              <span className="autobackup-lamp" aria-hidden />
              <div>
                <p><b>Updating — Fyodor will restart.</b> Games are saved, and the players at your tables were told; their tables come back when it starts again.</p>
                <p className="hint">{phase.closes ? "This window closes while the files are copied; a new one opens with the new version." : "This page comes back by itself in a minute."}</p>
                {phase.stuck && <p className="warn">{phase.stuck}</p>}
                {phase.done && <p data-testid="update-done"><b>{phase.done}</b></p>}
              </div>
            </div>
          )}
        </div>
      )}
    </SettingsSection>
  );
}

function PlanView({ plan, installing, onInstall, onCancel }: { plan: UpdateSummary; installing: boolean; onInstall: () => void; onCancel: () => void }) {
  const l = planLines(plan);
  return (
    <div className="update-plan" data-testid="update-plan">
      <p className="update-title"><b>{l.title}</b></p>
      <p data-testid="update-counts">{l.counts}</p>
      <ul className="update-groups">{l.groups.map((g) => <li key={g}>{g}</li>)}</ul>
      <p className={l.checkOk ? "update-ok" : "hint"} data-testid="update-check"><span aria-hidden>{l.checkOk ? "✓ " : ""}</span>{l.check}</p>
      {l.removed && <p className="hint">{l.removed}</p>}
      {plan.warnings.map((w) => <p key={w} className="warn">{w}</p>)}
      <p className="hint">
        Installing closes Fyodor for everyone playing: games are saved first and come back when it restarts. {l.window ?? ""} The files it
        replaces are kept in <code>_update_backup</code>; if copying fails, they're put back and the old version starts.
      </p>
      <div className="st-backup-acts">
        <button className="tt-btn brass" data-testid="update-install" disabled={installing} onClick={onInstall}>
          {installing ? "Saving games and unpacking…" : "Install and restart Fyodor"}
        </button>
        <button className="tt-btn" data-testid="update-cancel" disabled={installing} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
