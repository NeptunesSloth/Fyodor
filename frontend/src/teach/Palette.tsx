/**
 * -- Teach Fyodor -- the COMMANDS column: each category a coloured pill bar (icon, name, ▾ to fold), its pieces as smaller
 * pills under it. Drag one onto the workspace, or click / press Enter to snap it into the first place it fits.
 */

import { useState } from "react";
import type { DragItem } from "./drag";
import type { Category, Kind, Piece, Value, Vocabulary } from "./types";

interface Props {
  voc: Vocabulary;
  param: boolean;
  kind: Kind; // (an action has no When or If pieces: the card's own words say when it happens)
  usable: (piece: Piece) => boolean; // has somewhere to snap right now
  onAdd: (piece: Piece) => void;
  onChip: (value: Value) => void;
  onStartDrag: (e: React.PointerEvent, item: DragItem) => void;
}

const GLYPH: Record<string, string> = { when: "⚡", if: "?", cost: "◆", do: "▶", always: "∞", then: "⤵", target: "◎", value: "#" };

export function Palette({ voc, param, kind, usable, onAdd, onChip, onStartDrag }: Props) {
  const [folded, setFolded] = useState<Record<string, boolean>>({});
  const toggle = (id: string) => setFolded((f) => ({ ...f, [id]: !f[id] }));
  const targets = Object.entries(voc.options).filter(([, o]) => o.cat === "target");
  const section = (cat: Category, body: React.ReactNode, count: number) => (
    <section key={cat.id} className={`t-cat cat-${cat.id}`} aria-labelledby={`t-cat-${cat.id}`}>
      <button type="button" id={`t-cat-${cat.id}`} className="t-cathead" aria-expanded={!folded[cat.id]} onClick={() => toggle(cat.id)} title={cat.hint}>
        <span className="t-sq" aria-hidden>{GLYPH[cat.id] ?? ""}</span>
        <span className="t-catname">{cat.label}</span>
        <span className="t-catcount">{count}</span>
        <span className={`t-caret ${folded[cat.id] ? "closed" : ""}`} aria-hidden>▾</span>
      </button>
      {!folded[cat.id] && <div className="t-pills">{body}</div>}
      {!folded[cat.id] && <p className="t-cathint">{cat.hint}</p>}
    </section>
  );
  return (
    <aside className="t-palette" aria-label="Commands">
      <h2>Commands</h2>
      {voc.categories.map((cat) => {
        if (kind === "action" && (cat.id === "when" || cat.id === "if" || cat.id === "always")) return null;
        if (cat.id === "target") {
          return section(cat, targets.map(([id, o]) => (
            <button key={id} type="button" className="t-pill cat-target" onClick={() => onChip(id)}
              onPointerDown={(e) => onStartDrag(e, { kind: "chip", value: id, label: o.text.replace("{self}", "itself"), cat: "target" })}
              title="Drop on an orange setting of a piece">{o.text.replace("{self}", "itself")}</button>
          )), targets.length);
        }
        if (cat.id === "value") {
          const chips = voc.values.filter((v) => v !== "N" || param);
          return section(cat, chips.map((v) => (
            <button key={String(v)} type="button" className={`t-pill cat-value ${v === "N" ? "t-n" : ""}`} onClick={() => onChip(v)}
              onPointerDown={(e) => onStartDrag(e, { kind: "chip", value: v, label: String(v), cat: "value" })}
              title={v === "N" ? "The number after the keyword (Dive 2 → 2)" : "Drop on a white number of a piece"}>{String(v)}</button>
          )), chips.length);
        }
        const pieces = voc.pieces.filter((p) => p.cat === cat.id && !p.hidden);
        return section(cat, pieces.map((p) => {
          const can = usable(p);
          return (
            <button key={p.id} type="button" className={`t-pill cat-${p.cat} ${can ? "" : "dim"}`} onClick={() => onAdd(p)}
              onPointerDown={(e) => onStartDrag(e, { kind: "piece", piece: p })} aria-disabled={!can}
              title={can ? p.text.replace(/\{self\}/g, "this card").replace(/\{[a-z]+(?::[a-z]+)?\}/g, "…") : "Nowhere to put this yet"}>
              {p.label}
            </button>
          );
        }), pieces.length);
      })}
    </aside>
  );
}
