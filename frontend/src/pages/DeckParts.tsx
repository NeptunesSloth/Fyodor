import { useEffect, useLayoutEffect, useRef } from "react";
import { Icon, type IconName } from "../components/Icon";
import { CommanderArt } from "./CommanderArt";

/** Pieces shared by the Decks page, the deck editor and the import dialog. */

/** A commander's art window: one commander fills it, partners share it side by side (decks.css crops the scans). */
export function DeckArt({ ids, className }: { ids: (string | null | undefined)[]; className?: string }) {
  const shown = ids.filter((x): x is string => !!x).slice(0, 2);
  return (
    <span className={`dk-art ${shown.length > 1 ? "two" : ""} ${className ?? ""}`} aria-hidden>
      {shown.length === 0 ? <CommanderArt back /> : shown.map((id) => <CommanderArt key={id} id={id} className={shown.length > 1 ? "dk-half" : ""} />)}
    </span>
  );
}

export type DeckMenuItem = { label: string; onClick: () => void; danger?: boolean; icon?: IconName } | "separator";

/** Three dots, drawn like the icon set (Icon has no "more" glyph). */
export function Dots({ size = 18 }: { size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <circle cx="5.5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="18.5" cy="12" r="1.6" />
    </svg>
  );
}

/**
 * A small "more" menu for a deck or a card row: the quieter actions behind one button. Keyboard: Enter/Space opens it with
 * focus on the first item, arrows move, Escape closes it and returns focus to the button, Tab away closes it.
 * `open`/`onOpenChange` let a right-click open it too.
 */
export function DeckMenu({ label, items, open, onOpenChange, className }: {
  label: string;
  items: DeckMenuItem[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  className?: string;
}) {
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  // fixed to the viewport, beside its button: clear of the editor's columns (which clip what rises above them) and of the next
  // tile. Placed straight on the element before paint, so focus can move into it at once.
  const change = useRef(onOpenChange);
  change.current = onOpenChange; // (a parent's inline callback: the effects below run only when `open` changes)
  useLayoutEffect(() => {
    const el = menu.current;
    if (!open || !el || !btn.current) return;
    const b = btn.current.getBoundingClientRect();
    const m = el.getBoundingClientRect();
    const below = b.bottom + 4;
    el.style.left = `${Math.max(8, Math.min(b.right - m.width, window.innerWidth - m.width - 8))}px`;
    el.style.top = `${below + m.height > window.innerHeight - 8 ? Math.max(8, b.top - 4 - m.height) : below}px`;
    el.dataset.placed = "";
    el.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: Event) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !btn.current?.contains(t)) change.current(false);
    };
    const away = () => change.current(false);
    // Tab away (focus lands outside) closes it too; a click on an item never moves focus outside. Scrolling closes it.
    window.addEventListener("pointerdown", onDown, true);
    window.addEventListener("focusin", onDown);
    window.addEventListener("scroll", away, true);
    window.addEventListener("resize", away);
    return () => {
      window.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("focusin", onDown);
      window.removeEventListener("scroll", away, true);
      window.removeEventListener("resize", away);
    };
  }, [open]);
  const onKey = (e: React.KeyboardEvent) => {
    const list = [...(menu.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
    const i = list.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "Escape") {
      e.stopPropagation();
      onOpenChange(false);
      btn.current?.focus();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      list[(i + (e.key === "ArrowDown" ? 1 : -1) + list.length) % list.length]?.focus();
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      list[e.key === "Home" ? 0 : list.length - 1]?.focus();
    }
  };
  return (
    <span className={`dmenu ${className ?? ""}`}>
      <button ref={btn} type="button" className="tt-icon dmenu-btn" aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open}
        onClick={() => onOpenChange(!open)}>
        <Dots />
      </button>
      {open && (
        <div ref={menu} role="menu" aria-label={label} className="dmenu-list" onKeyDown={onKey}>
          {items.map((item, i) =>
            item === "separator" ? <div key={i} className="dmenu-sep" role="separator" /> : (
              <button key={i} type="button" role="menuitem" tabIndex={-1} className={item.danger ? "danger" : ""}
                onClick={() => { onOpenChange(false); item.onClick(); }}>
                {item.icon ? <Icon name={item.icon} size={15} /> : <span className="dmenu-gap" />}
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </span>
  );
}
