import { create } from "zustand";

export interface ToastAction { label: string; run: () => void }

interface Toast {
  id: number;
  text: string;
  kind: "info" | "error" | "warn";
  action?: ToastAction | undefined;
  /** Stays until dismissed (a refused action: the reason must not vanish before it is read, playtest B5). */
  sticky?: boolean | undefined;
}

export interface ToastOptions { sticky?: boolean }

interface ToastState {
  toasts: Toast[];
  push: (text: string, kind?: Toast["kind"], action?: ToastAction, options?: ToastOptions) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;
export const useToasts = create<ToastState>((set, get) => ({
  toasts: [],
  push: (text, kind = "info", action, options) => {
    const id = nextId++;
    const sticky = options?.sticky === true;
    // -- second pass (nov 17) -- the same message again replaces the one on screen (five clicks on Pay stacked five identical toasts over the plaque)
    set((s) => ({ toasts: [...s.toasts.filter((t) => t.text !== text).slice(-4), { id, text, kind, action, sticky }] }));
    if (!sticky) setTimeout(() => get().dismiss(id), action ? 10000 : kind === "error" ? 8000 : 3500);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export const toast = (text: string, kind?: Toast["kind"], action?: ToastAction, options?: ToastOptions) => useToasts.getState().push(text, kind, action, options);
export const toastError = (err: unknown) => toast(err instanceof Error ? err.message : String(err), "error");

export function Toasts() {
  const toasts = useToasts((s) => s.toasts);
  const dismiss = useToasts((s) => s.dismiss);
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
          <span className="toast-text">{t.text}</span>
          {t.action && (
            <button className="tt-btn toast-action" onClick={() => { dismiss(t.id); t.action!.run(); }}>{t.action.label}</button>
          )}
          <button className="tt-icon toast-close" aria-label="Dismiss" title="Dismiss" onClick={() => dismiss(t.id)}>✕</button>
        </div>
      ))}
    </div>
  );
}
