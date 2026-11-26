import { useEffect, useState } from "react";
import { CopyButton } from "../components/CopyButton";
import { Icon } from "../components/Icon";
import { toastError } from "../components/Toasts";
import { getShare, startShare, stopShare, type ShareStatus } from "../services/share";

export type InviteStep = "unavailable" | "button" | "existing" | "password" | "starting" | "link" | "failed";

/** Which part of the section shows: `pressed` is the host having pressed the button; `replacing`, having chosen to set a new password
 *  at a table that already has one (the server can't tell how strong that one is, so the host is asked). */
export function inviteStep(status: ShareStatus, pressed: boolean, replacing = false): InviteStep {
  if (!status.available) return "unavailable";
  if (status.state === "starting") return "starting";
  if (status.state === "running" && status.shared && status.link) return "link";
  // (also after a failure: "Invite again" asks again, for a password or which one)
  if (pressed) return status.has_password && !replacing ? "existing" : "password";
  return status.state === "failed" ? "failed" : "button";
}

/** Setting a new password changes it for the whole table, not only the link. */
export const NEW_PASSWORD_NOTE = "A new password is needed by everyone who joins from now on, on this network too. Players already seated keep their seats.";

/** Every viewer's note that the table can be reached from outside the network (icon and text, focusable for its title). */
export function SharedChip() {
  return (
    <span className="shared-chip" tabIndex={0} title="Anyone with the link and the password can join this table from the internet.">
      <Icon name="globe" size={15} />Shared over the internet
    </span>
  );
}

interface ViewProps {
  status: ShareStatus;
  pressed: boolean;
  password: string;
  busy: boolean;
  onPress: () => void;
  onPassword: (p: string) => void;
  onStart: () => void;
  onStop: () => void;
  /** show the typed password (default hidden) */
  reveal?: boolean;
  onReveal?: () => void;
  /** a status read that kept failing while the link starts */
  error?: string | null;
  /** the host chose to set a new password at a table that has one */
  replacing?: boolean;
  /** share with the table's own password */
  onShareExisting?: () => void;
  /** set a new password instead */
  onReplace?: () => void;
}

/** The section's looks (no state of its own: rendered directly in the tests). */
export function InternetInviteView({ status, pressed, password, busy, onPress, onPassword, onStart, onStop, reveal = false, onReveal, error = null,
  replacing = false, onShareExisting, onReplace }: ViewProps) {
  const step = inviteStep(status, pressed, replacing);
  return (
    <section className="net-invite" data-testid="internet-invite" aria-labelledby="net-invite-title">
      <h3 id="net-invite-title"><Icon name="globe" size={15} />Invite over the internet</h3>
      {step === "unavailable" && <p className="net-note">{status.reason}</p>}
      {step === "button" && (
        <button type="button" className="tt-btn brass" disabled={busy} onClick={onPress}>Invite over the internet</button>
      )}
      {step === "existing" && (
        <>
          <p className="net-note">This table already has a password.</p>
          <div className="row wrap">
            <button type="button" className="tt-btn brass" disabled={busy} onClick={onShareExisting}>Share with it</button>
            <button type="button" className="tt-btn ghost" disabled={busy} onClick={onReplace}>Set a new password</button>
          </div>
          <p className="net-note">{NEW_PASSWORD_NOTE}</p>
        </>
      )}
      {step === "password" && (
        <form className="net-form" onSubmit={(e) => { e.preventDefault(); onStart(); }}>
          {replacing && status.has_password && <p className="net-note">{NEW_PASSWORD_NOTE}</p>}
          <label className="field">
            {replacing && status.has_password ? "New table password (friends need it to join)" : "Table password (friends need it to join)"}
            <input type={reveal ? "text" : "password"} value={password} minLength={8} maxLength={100} required autoFocus autoComplete="new-password"
              onChange={(e) => onPassword(e.target.value)} />
          </label>
          <button type="button" className="tt-btn ghost" aria-pressed={reveal} onClick={onReveal}>
            <Icon name={reveal ? "lock" : "hand"} size={14} />{reveal ? "Hide password" : "Show password"}
          </button>
          <button type="submit" className="tt-btn brass" disabled={busy || password.length < 8}>Share with this password</button>
        </form>
      )}
      {step === "starting" && <p className="net-note" role="status">Starting the link… the first time downloads the tunnel program (about 55 MB).</p>}
      {step === "starting" && error && <p className="net-note net-failed" role="alert">{error}</p>}
      {step === "link" && (
        <>
          <div className="invite-row">
            <input readOnly value={status.link ?? ""} aria-label="Internet invite link" onFocus={(e) => e.currentTarget.select()} />
            <CopyButton text={status.link ?? ""} label="Copy link" done="Copied" className="brass" />
          </div>
          <p className="net-note">Send the password separately.</p>
          <button type="button" className="tt-btn ghost" disabled={busy} onClick={onStop}>Stop sharing</button>
        </>
      )}
      {step === "failed" && (
        <>
          <p className="net-note net-failed" role="alert">{status.reason}</p>
          <button type="button" className="tt-btn brass" disabled={busy} onClick={onPress}>Invite again</button>
        </>
      )}
    </section>
  );
}

/** The host's internet invite: a section of the lobby's Invite popover and of Host tools. Reads the table's share status. */
export function InternetInvite({ gameId }: { gameId: string }) {
  const [status, setStatus] = useState<ShareStatus | null>(null);
  const [pressed, setPressed] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [reveal, setReveal] = useState(false);
  const [pollError, setPollError] = useState<string | null>(null);
  const reread = () => getShare(gameId).then(setStatus, () => undefined);
  useEffect(() => { void getShare(gameId).then(setStatus, () => undefined); }, [gameId]);
  // the link takes a moment (and the first time downloads the tunnel program): ask again every 2 s while it starts
  const starting = status?.state === "starting";
  useEffect(() => {
    if (!starting) return;
    let misses = 0;
    const t = window.setInterval(() => {
      getShare(gameId).then(
        (s) => { misses = 0; setPollError(null); setStatus(s); },
        (e) => {
          if (++misses < 3) return;
          window.clearInterval(t); // (stop asking; say why)
          setPollError("Can't read the link's status: " + (e instanceof Error ? e.message : "no answer"));
        },
      );
    }, 2000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [starting, gameId]);
  if (!status) return null;

  const run = async (fn: () => Promise<ShareStatus>) => {
    setBusy(true);
    try {
      setStatus(await fn());
    } catch (e) {
      toastError(e);
      await reread(); // (a failed start leaves the table unshared and with no password: has_password says which)
    } finally {
      setBusy(false);
    }
  };
  // (a failed start keeps the typed password in state so "Invite again" can send it again)
  const start = (withPassword: string | undefined) => run(async () => {
    const s = await startShare(gameId, withPassword);
    setPassword(""); setPressed(false); setReplacing(false);
    return s;
  });
  return (
    <InternetInviteView status={status} pressed={pressed} password={password} busy={busy}
      onPress={() => setPressed(true)}
      onPassword={setPassword} onStart={() => void start(password || undefined)}
      onShareExisting={() => void start(undefined)} onReplace={() => setReplacing(true)} replacing={replacing}
      onStop={() => void run(() => stopShare(gameId))}
      reveal={reveal} onReveal={() => setReveal((r) => !r)} error={pollError} />
  );
}
