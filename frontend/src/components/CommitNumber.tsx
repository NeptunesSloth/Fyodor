import { useState } from "react";

/** The number a typed entry means: blank, non-numeric or zero or less is refused (`ok: false`, the previous value kept); the rest is rounded and clamped. */
export function commitNumber(text: string, prev: number, min: number, max: number): { value: number; ok: boolean } {
  const n = Number(text);
  if (text.trim() === "" || !Number.isFinite(n) || n <= 0) return { value: prev, ok: false };
  return { value: Math.max(min, Math.min(max, Math.round(n))), ok: true };
}

/**
 * A number field that can be cleared while typing: it commits on blur or Enter, and an empty or invalid entry falls back to the
 * previous value (`onInvalid` says so, when the caller wants to).
 */
export function CommitNumber({ value, min, max, onCommit, onInvalid, label, width = 56, disabled }: {
  value: number; min: number; max: number; onCommit: (n: number) => void; onInvalid?: () => void; label: string; width?: number;
  disabled?: boolean;
}) {
  const [text, setText] = useState<string | null>(null);
  const commit = () => {
    if (text === null) return;
    const r = commitNumber(text, value, min, max);
    setText(null);
    if (!r.ok) onInvalid?.();
    else if (r.value !== value) onCommit(r.value);
  };
  return (
    <input type="number" min={min} max={max} value={text ?? String(value)} style={{ width }} aria-label={label} disabled={disabled}
      onChange={(e) => setText(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }} />
  );
}
