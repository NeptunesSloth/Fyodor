/** Promise-based prompt dialog (number / text), replacing window.prompt with a styled modal. */
import { useEffect, useRef, useState } from "react";
import { create } from "zustand";
import { Modal } from "./Modal";

interface PromptRequest {
  title: string;
  label?: string;
  kind: "number" | "text";
  initial: string;
  min?: number;
  max?: number;
  multiline?: boolean;
  resolve: (value: string | null) => void;
}

const usePrompt = create<{ req: PromptRequest | null; set: (r: PromptRequest | null) => void }>((set) => ({
  req: null,
  set: (req) => set({ req }),
}));

export function askNumber(title: string, initial = 1, opts: { min?: number; max?: number; label?: string } = {}): Promise<number | null> {
  return new Promise((resolve) =>
    usePrompt.getState().set({
      title,
      kind: "number",
      initial: String(initial),
      ...opts,
      resolve: (v) => {
        const n = v == null ? NaN : Number(v);
        resolve(Number.isFinite(n) ? Math.trunc(n) : null);
      },
    }),
  );
}

export function askText(title: string, initial = "", opts: { label?: string; multiline?: boolean } = {}): Promise<string | null> {
  return new Promise((resolve) => usePrompt.getState().set({ title, kind: "text", initial, ...opts, resolve }));
}

export function PromptHost() {
  const req = usePrompt((s) => s.req);
  const [value, setValue] = useState("");
  const input = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  useEffect(() => {
    if (req) {
      setValue(req.initial);
      setTimeout(() => input.current?.select(), 0);
    }
  }, [req]);
  if (!req) return null;
  const finish = (v: string | null) => {
    usePrompt.getState().set(null);
    req.resolve(v);
  };
  return (
    <Modal
      title={req.title}
      onClose={() => finish(null)}
      footer={
        <>
          <button className="btn" onClick={() => finish(null)}>Cancel</button>
          <button className="btn primary" onClick={() => finish(value)}>OK</button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          finish(value);
        }}
      >
        <label className="field">
          {req.label}
          {req.multiline ? (
            <textarea ref={input} rows={4} value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
          ) : (
            <input
              ref={input}
              autoFocus
              type={req.kind === "number" ? "number" : "text"}
              min={req.min}
              max={req.max}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          )}
        </label>
      </form>
    </Modal>
  );
}
