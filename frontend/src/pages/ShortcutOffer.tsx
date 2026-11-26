import { useEffect, useState } from "react";
import { toast, toastError } from "../components/Toasts";
import { api } from "../services/api";

const ASKED = "fyodor.shortcutAsked";

const asked = () => {
  try {
    return localStorage.getItem(ASKED) === "1";
  } catch {
    return true; // (no storage: don't nag every start)
  }
};

/** -- desktop shortcut -- the first start of the Fyodor app (host, Windows) offers one, once (backend app/api/shortcut.py). */
export function ShortcutOffer() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (asked()) return;
    api.get<{ supported: boolean; exists: boolean }>("/shortcut").then((s) => setShow(s.supported && !s.exists), () => undefined);
  }, []);
  if (!show) return null;
  const done = () => {
    try { localStorage.setItem(ASKED, "1"); } catch { /* fine */ }
    setShow(false);
  };
  const make = () => api.post("/shortcut", {}).then(() => { toast("Fyodor is on your desktop"); done(); }, toastError);
  return (
    <div className="home-shortcut" role="region" aria-label="Desktop shortcut">
      <span>Put a Fyodor shortcut on your desktop?</span>
      <button className="tt-btn primary" onClick={() => void make()}>Create shortcut</button>
      <button className="tt-btn ghost" onClick={done}>No thanks</button>
    </div>
  );
}
