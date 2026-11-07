import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { create } from "zustand";
import { ManaText } from "../cards/ManaText";

/** An activated ability shown as cost + effect (symbols drawn, effect never cut off), with why it is greyed out. */
export interface AbilityRow { cost: string; effect: string; why?: string }

export type MenuItem =
  | { label: string; onClick?: () => void; submenu?: MenuItem[]; danger?: boolean; disabled?: boolean; hint?: string;
      ability?: AbilityRow; section?: string }
  | "separator";

/** The enabled ability rows, in order: keys 1–9 activate them while the menu is open. */
const abilityKeys = (items: MenuItem[]) => items.filter((i): i is Exclude<MenuItem, "separator"> => i !== "separator" && !!i.ability && !i.disabled);

interface MenuState {
  menu: { x: number; y: number; title?: string; items: MenuItem[] } | null;
  open: (x: number, y: number, items: MenuItem[], title?: string) => void;
  close: () => void;
}

export const useMenu = create<MenuState>((set) => ({
  menu: null,
  open: (x, y, items, title) => set({ menu: { x, y, items, title } }),
  close: () => set({ menu: null }),
}));

export const openMenu = (e: { clientX: number; clientY: number }, items: MenuItem[], title?: string) =>
  useMenu.getState().open(e.clientX, e.clientY, items, title);

export function ContextMenuHost() {
  const menu = useMenu((s) => s.menu);
  const close = useMenu((s) => s.close);
  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      else if (/^[1-9]$/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const item = abilityKeys(menu.items)[Number(e.key) - 1];
        if (!item) return;
        e.preventDefault();
        e.stopPropagation();
        close();
        item.onClick?.();
      }
    };
    const onDown = (e: PointerEvent) => {
      if (!(e.target as HTMLElement).closest(".ctx-menu")) close();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onDown, true);
    window.addEventListener("blur", close);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("blur", close);
    };
  }, [menu, close]);
  if (!menu) return null;
  return <MenuPanel x={menu.x} y={menu.y} items={menu.items} title={menu.title} onDone={close} />;
}

function Rows({ items, onDone, openSub, setOpenSub }: { items: MenuItem[]; onDone: () => void; openSub: number | null; setOpenSub: (i: number | null) => void }) {
  const keyed = abilityKeys(items);
  return (
    <>
      {items.map((item, i) => {
        if (item === "separator") return <div key={i} className="ctx-sep" />;
        const prev = items[i - 1];
        const heading = item.section && (prev === undefined || prev === "separator" || prev.section !== item.section) ? item.section : null;
        const key = keyed.indexOf(item);
        return (
          <div key={i} className="ctx-item-wrap" onPointerEnter={() => setOpenSub(item.submenu ? i : null)}>
            {heading && <div className="ctx-section">{heading}</div>}
            <button
              className={`ctx-item ${item.danger ? "danger" : ""} ${item.ability ? "ctx-ability" : ""}`}
              disabled={item.disabled}
              aria-label={item.ability ? item.label : undefined}
              title={item.ability && item.disabled && item.ability.why ? item.ability.why : undefined}
              onClick={() => {
                if (item.submenu) {
                  setOpenSub(i);
                  return;
                }
                onDone();
                item.onClick?.();
              }}
            >
              {item.ability ? (
                <>
                  <span className="ctx-ab-cost"><ManaText text={item.ability.cost} /></span>
                  <span className="ctx-ab-effect">
                    <ManaText text={item.ability.effect} />
                    {item.disabled && item.ability.why && <span className="ctx-ab-why">{item.ability.why}</span>}
                  </span>
                  {key >= 0 && key < 9 && <kbd className="ctx-key" aria-hidden>{key + 1}</kbd>}
                </>
              ) : (
                <>
                  <span>{item.label}</span>
                  {item.hint && <span className="ctx-hint">{item.hint}</span>}
                  {item.submenu && <span className="ctx-arrow">›</span>}
                </>
              )}
            </button>
            {item.submenu && openSub === i && <SubMenu items={item.submenu} onDone={onDone} />}
          </div>
        );
      })}
    </>
  );
}

function MenuPanel({ x, y, items, title, onDone }: { x: number; y: number; items: MenuItem[]; title?: string | undefined; onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });
  const [openSub, setOpenSub] = useState<number | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    // its laid-out size (offset*, not the bounding box: the opening animation scales it down for a frame)
    const r = { width: el.offsetWidth, height: el.offsetHeight };
    setPos({
      left: Math.max(4, Math.min(x, window.innerWidth - r.width - 4)),
      top: Math.max(4, Math.min(y, window.innerHeight - r.height - 4)),
    });
  }, [x, y, items]);
  return (
    <div className="ctx-menu" ref={ref} style={pos} onContextMenu={(e) => e.preventDefault()}>
      {title && <div className="ctx-title">{title}</div>}
      <Rows items={items} onDone={onDone} openSub={openSub} setOpenSub={setOpenSub} />
    </div>
  );
}

function SubMenu({ items, onDone }: { items: MenuItem[]; onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [flip, setFlip] = useState({ x: false, y: 0 });
  const [openSub, setOpenSub] = useState<number | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect(); // (its top-left corner; the size from layout, in case anything is scaling it)
    setFlip({ x: r.left + el.offsetWidth > window.innerWidth - 4, y: Math.min(0, window.innerHeight - (r.top + el.offsetHeight) - 4) });
  }, [items]);
  return (
    <div
      ref={ref}
      className="ctx-menu ctx-sub"
      style={{ top: flip.y, ...(flip.x ? { right: "100%" } : { left: "100%" }) }}
    >
      <Rows items={items} onDone={onDone} openSub={openSub} setOpenSub={setOpenSub} />
    </div>
  );
}
