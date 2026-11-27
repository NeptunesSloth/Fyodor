import { useEffect, useState } from "react";
import { Icon } from "./Icon";
import { toast } from "./Toasts";

/** Copies `text`, saying so on the button for a moment; falls back to a selection copy where the clipboard API is missing. */
export function CopyButton({ text, label, done, className, testId }: { text: string; label: React.ReactNode; done: string; className?: string; testId?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 1800);
    return () => window.clearTimeout(t);
  }, [copied]);
  const copy = async () => {
    try {
      if (navigator.clipboard) await navigator.clipboard.writeText(text);
      else {
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        const ok = document.execCommand("copy");
        area.remove();
        if (!ok) throw new Error("copy");
      }
      setCopied(true);
    } catch {
      toast("Couldn't copy: select the text and copy it", "warn");
    }
  };
  return (
    <button type="button" className={`tt-btn ${className ?? ""}`} data-testid={testId} onClick={() => void copy()} aria-live="polite">
      {copied ? <><Icon name="check" size={14} />{done}</> : label}
    </button>
  );
}
