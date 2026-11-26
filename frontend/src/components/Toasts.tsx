import { create } from "zustand";
import { ManaText } from "../cards/ManaText";

export interface ToastAction { label: string; run: () => void }

interface Toast {
  id: number;
  text: string;
  kind: "info" | "error" | "warn";
  action?: ToastAction | undefined;
  /** Stays until dismissed (a refused action: the reason must not vanish before it is read, playtest B5). */
  sticky?: boolean | undefined;
  at?: number;
}

export interface ToastOptions { sticky?: boolean }

interface ToastState {
  toasts: Toast[];
  push: (text: string, kind?: Toast["kind"], action?: ToastAction, options?: ToastOptions) => void;
  dismiss: (id: number) => void;
  /** -- sweep B (nov 18) -- the refusals on screen go once the player's next action goes through: "Tap your mana first: {6}{G}{U} isn't paid
   * yet" stayed up, sticky, after the spell was paid, cast and resolved. */
  clearRefusals: () => void;
}

let nextId = 1;
export const useToasts = create<ToastState>((set, get) => ({
  toasts: [],
  push: (text, kind = "info", action, options) => {
    const id = nextId++;
    const sticky = options?.sticky === true;
    // -- second pass (nov 17) -- the same message again replaces the one on screen (five clicks on Pay stacked five identical toasts over the plaque)
    set((s) => ({ toasts: [...s.toasts.filter((t) => t.text !== text).slice(-4), { id, text, kind, action, sticky, at: Date.now() }] }));
    if (!sticky) setTimeout(() => get().dismiss(id), action ? 10000 : kind === "error" ? 8000 : 3500);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  clearRefusals: () => {
    // (one shown in the last moment stays: an action sent right behind the refused one, without the player, mustn't take it away unread)
    const stale = (t: Toast) => t.sticky && t.kind === "error" && Date.now() - (t.at ?? 0) > 1500;
    if (get().toasts.some(stale)) set((s) => ({ toasts: s.toasts.filter((t) => !stale(t)) }));
  },
}));

export const toast = (text: string, kind?: Toast["kind"], action?: ToastAction, options?: ToastOptions) => useToasts.getState().push(text, kind, action, options);
export const toastError = (err: unknown) => toast(err instanceof Error ? err.message : String(err), "error");

/** A card symbol in a toast's text: "{2}", "{T}", "{W/U}" (a toast with none stays plain text). */
const MANA_SYMBOL = /\{[0-9A-Za-z/½∞]{1,6}\}/;

/** A toast's words, with its card symbols drawn (ManaText) when it has any. */
export function ToastText({ text }: { text: string }) {
  return <span className="toast-text">{MANA_SYMBOL.test(text) ? <ManaText text={text} /> : text}</span>;
}

export function Toasts() {
  const toasts = useToasts((s) => s.toasts);
  const dismiss = useToasts((s) => s.dismiss);
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
          {/* -- playtest (nov 17) -- a refusal naming a cost ("Add {2} to your mana pool first…", "{T}") shows the symbols, not braces */}
          <ToastText text={t.text} />
          {t.action && (
            <button className="tt-btn toast-action" onClick={() => { dismiss(t.id); t.action!.run(); }}>{t.action.label}</button>
          )}
          <button className="tt-icon toast-close" aria-label="Dismiss" title="Dismiss" onClick={() => dismiss(t.id)}>✕</button>
        </div>
      ))}
    </div>
  );
}
