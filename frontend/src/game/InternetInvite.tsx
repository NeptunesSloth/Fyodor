import { useEffect, useState } from "react";
import { CopyButton } from "../components/CopyButton";
import { Icon } from "../components/Icon";
import { toastError } from "../components/Toasts";
import { getShare, startShare, stopShare, type ShareStatus } from "../services/share";

export type InviteStep = "unavailable" | "button" | "password" | "starting" | "link" | "failed";

/** Which part of the section shows: `pressed` is the host having pressed the button at a table that has no password yet. */
export function inviteStep(status: ShareStatus, pressed: boolean): InviteStep {
  if (!status.available) return "unavailable";
  if (status.state === "starting") return "starting";
  if (status.state === "failed") return "failed";
  if (status.state === "running" && status.shared && status.link) return "link";
  return pressed && !status.has_password ? "password" : "button";
}

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
}

/** The section's looks (no state of its own: rendered directly in the tests). */
export function InternetInviteView({ status, pressed, password, busy, onPress, onPassword, onStart, onStop }: ViewProps) {
  const step = inviteStep(status, pressed);
  return (
    <section className="net-invite" data-testid="internet-invite" aria-labelledby="net-invite-title">
      <h3 id="net-invite-title"><Icon name="globe" size={15} />Invite over the internet</h3>
      {step === "unavailable" && <p className="net-note">{status.reason}</p>}
      {step === "button" && (
        <button type="button" className="tt-btn brass" disabled={busy} onClick={onPress}>Invite over the internet</button>
      )}
      {step === "password" && (
        <form className="net-form" onSubmit={(e) => { e.preventDefault(); onStart(); }}>
          <label className="field">
            Table password (friends need it to join)
            <input type="password" value={password} minLength={8} maxLength={100} required autoFocus autoComplete="new-password"
              onChange={(e) => onPassword(e.target.value)} />
          </label>
          <button type="submit" className="tt-btn brass" disabled={busy || password.length < 8}>Share with this password</button>
        </form>
      )}
      {step === "starting" && <p className="net-note" role="status">Starting the link… the first time downloads the tunnel program (about 40 MB).</p>}
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
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const reread = () => getShare(gameId).then(setStatus, () => undefined);
  useEffect(() => { void getShare(gameId).then(setStatus, () => undefined); }, [gameId]);
  // the link takes a moment (and the first time downloads the tunnel program): ask again every 2 s while it starts
  const starting = status?.state === "starting";
  useEffect(() => {
    if (!starting) return;
    const t = window.setInterval(() => void reread(), 2000);
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
  const start = () => run(async () => { const s = await startShare(gameId, password || undefined); setPassword(""); setPressed(false); return s; });
  return (
    <InternetInviteView status={status} pressed={pressed} password={password} busy={busy}
      onPress={() => { if (status.has_password) void start(); else setPressed(true); }}
      onPassword={setPassword} onStart={() => void start()}
      onStop={() => void run(() => stopShare(gameId))} />
  );
}
