import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { create } from "zustand";

export type MenuItem =
  | { label: string; onClick?: () => void; submenu?: MenuItem[]; danger?: boolean; disabled?: boolean; hint?: string }
  | "separator";

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
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    const onDown = (e: PointerEvent) => {
      if (!(e.target as HTMLElement).closest(".ctx-menu")) close();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown, true);
    window.addEventListener("blur", close);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("blur", close);
    };
  }, [menu, close]);
  if (!menu) return null;
  return <MenuPanel x={menu.x} y={menu.y} items={menu.items} title={menu.title} onDone={close} />;
}

function MenuPanel({ x, y, items, title, onDone }: { x: number; y: number; items: MenuItem[]; title?: string | undefined; onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });
  const [openSub, setOpenSub] = useState<number | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos({
      left: Math.max(4, Math.min(x, window.innerWidth - r.width - 4)),
      top: Math.max(4, Math.min(y, window.innerHeight - r.height - 4)),
    });
  }, [x, y, items]);
  return (
    <div className="ctx-menu" ref={ref} style={pos} onContextMenu={(e) => e.preventDefault()}>
      {title && <div className="ctx-title">{title}</div>}
      {items.map((item, i) =>
        item === "separator" ? (
          <div key={i} className="ctx-sep" />
        ) : (
          <div key={i} className="ctx-item-wrap" onPointerEnter={() => setOpenSub(item.submenu ? i : null)}>
            <button
              className={`ctx-item ${item.danger ? "danger" : ""}`}
              disabled={item.disabled}
              onClick={() => {
                if (item.submenu) {
                  setOpenSub(i);
                  return;
                }
                onDone();
                item.onClick?.();
              }}
            >
              <span>{item.label}</span>
              {item.hint && <span className="ctx-hint">{item.hint}</span>}
              {item.submenu && <span className="ctx-arrow">›</span>}
            </button>
            {item.submenu && openSub === i && <SubMenu items={item.submenu} onDone={onDone} />}
          </div>
        ),
      )}
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
    const r = el.getBoundingClientRect();
    setFlip({ x: r.right > window.innerWidth - 4, y: Math.min(0, window.innerHeight - r.bottom - 4) });
  }, [items]);
  return (
    <div
      ref={ref}
      className="ctx-menu ctx-sub"
      style={{ top: flip.y, ...(flip.x ? { right: "100%" } : { left: "100%" }) }}
    >
      {items.map((item, i) =>
        item === "separator" ? (
          <div key={i} className="ctx-sep" />
        ) : (
          <div key={i} className="ctx-item-wrap" onPointerEnter={() => setOpenSub(item.submenu ? i : null)}>
            <button
              className={`ctx-item ${item.danger ? "danger" : ""}`}
              disabled={item.disabled}
              onClick={() => {
                if (item.submenu) {
                  setOpenSub(i);
                  return;
                }
                onDone();
                item.onClick?.();
              }}
            >
              <span>{item.label}</span>
              {item.hint && <span className="ctx-hint">{item.hint}</span>}
              {item.submenu && <span className="ctx-arrow">›</span>}
            </button>
            {item.submenu && openSub === i && <SubMenu items={item.submenu} onDone={onDone} />}
          </div>
        ),
      )}
    </div>
  );
}
