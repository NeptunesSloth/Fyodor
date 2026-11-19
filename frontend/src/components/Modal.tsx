import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "./Icon";

interface Props {
  title?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
  footer?: React.ReactNode;
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

/**
 * A focused dialog: focus moves in (to what the content autofocuses, else the dialog itself), Tab and Shift+Tab stay inside
 * while it is the topmost dialog, Escape closes it, and focus goes back to what opened it.
 */
export function Modal({ title, onClose, children, wide, footer }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const [opener] = useState(() => (document.activeElement instanceof HTMLElement ? document.activeElement : null)); // before autofocus moves it
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);
  useEffect(() => {
    const el = box.current;
    if (el && !el.contains(document.activeElement)) el.focus({ preventScroll: true });
    return () => {
      // back to the opener, unless focus has already gone somewhere else on purpose (another dialog, a field)
      const now = document.activeElement;
      if (opener?.isConnected && (!now || now === document.body || el?.contains(now))) opener.focus({ preventScroll: true });
    };
  }, [opener]);
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Tab") return;
    const el = box.current;
    const dialogs = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
    if (!el || dialogs[dialogs.length - 1] !== el) return; // a dialog opened over this one keeps its own
    const items = [...el.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((x) => x.getClientRects().length > 0);
    if (!items.length) return;
    const first = items[0]!;
    const last = items[items.length - 1]!;
    const at = document.activeElement;
    if (e.shiftKey && (at === first || at === el)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && at === last) {
      e.preventDefault();
      first.focus();
    }
  };
  return (
    <div className="modal-backdrop" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={box} className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={title ? titleId : undefined}
        tabIndex={-1} onKeyDown={onKeyDown}>
        <header className="modal-head">
          <div className="modal-title" id={titleId}>{title}</div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="close" size={16} />
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  );
}
