import { useCallback, useEffect, useMemo, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { ManaText } from "../cards/ManaText";
import { CardSearchBox } from "../components/CardSearchBox";
import { ColorPips } from "../components/ColorPips";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { getPrintings } from "../services/cards";
import { exportDeck, getDeck, importIntoDeck, updateDeck } from "../services/decks";
import { requestCards, useCardCache } from "../state/cardCache";
import {
  addCard,
  changeQuantity,
  moveToSection,
  removeEntry,
  sectionCount,
  setCommander,
  setPrinting,
  TYPE_GROUP_ORDER,
  typeGroup,
} from "../state/deckEdit";
import type { CardData } from "../types/cards";
import { SECTION_LABEL, SECTIONS, type Deck, type DeckEntry, type DeckFormat, type Section } from "../types/decks";

export function DeckEditor({ id }: { id: string }) {
  const [deck, setDeck] = useState<Deck | null>(null);
  const [entries, setEntries] = useState<DeckEntry[]>([]);
  const [name, setName] = useState("");
  const [format, setFormat] = useState<DeckFormat>("commander");
  const [notes, setNotes] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const [printingFor, setPrintingFor] = useState<number | null>(null);
  const [exportText, setExportText] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [addSection, setAddSection] = useState<Section>("main");
  const cards = useCardCache((s) => s.cards);

  const load = useCallback((d: Deck) => {
    setDeck(d);
    setEntries(d.entries);
    setName(d.name);
    setFormat(d.format);
    setNotes(d.notes);
    setDirty(false);
    requestCards(d.entries.map((e) => e.printing_id).filter((x): x is string => !!x));
  }, []);

  useEffect(() => {
    getDeck(id).then(load, toastError);
  }, [id, load]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const edit = (fn: (list: DeckEntry[]) => DeckEntry[]) => {
    setEntries((list) => fn(list));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      load(await updateDeck(id, { name: name.trim() || "Untitled deck", format, notes, entries }));
      toast("Deck saved");
    } catch (e) {
      toastError(e);
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (dirty) void save();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const grouped = useMemo(() => {
    const out: { section: Section; groups: { label: string; rows: { entry: DeckEntry; index: number }[] }[] }[] = [];
    for (const section of SECTIONS) {
      const rows = entries.map((entry, index) => ({ entry, index })).filter((r) => r.entry.section === section);
      if (!rows.length && section !== "main" && !(section === "commander" && format === "commander")) continue;
      if (section !== "main") {
        out.push({ section, groups: [{ label: "", rows }] });
        continue;
      }
      const byType = new Map<string, { entry: DeckEntry; index: number }[]>();
      for (const r of rows) {
        const g = typeGroup(r.entry.printing_id ? cards[r.entry.printing_id]?.type_line : null);
        byType.set(g, [...(byType.get(g) ?? []), r]);
      }
      const groups = TYPE_GROUP_ORDER.filter((g) => byType.has(g)).map((label) => ({
        label,
        rows: byType.get(label)!.sort((a, b) => a.entry.name.localeCompare(b.entry.name)),
      }));
      out.push({ section, groups });
    }
    return out;
  }, [entries, cards, format]);

  const curve = useMemo(() => {
    const buckets = Array.from({ length: 8 }, () => 0);
    for (const e of entries) {
      if (e.section !== "main") continue;
      const c = e.printing_id ? cards[e.printing_id] : undefined;
      if (!c || (c.type_line ?? "").includes("Land")) continue;
      buckets[Math.min(7, Math.floor(c.cmc ?? 0))]! += e.quantity;
    }
    return buckets;
  }, [entries, cards]);

  if (!deck) return <div className="page">Loading…</div>;
  const commanderId = entries.find((e) => e.section === "commander" && e.printing_id)?.printing_id;
  const shownId = hover ?? commanderId;
  const hovered = shownId ? cards[shownId] : undefined;
  const total = sectionCount(entries, "main") + sectionCount(entries, "commander");
  const maxCurve = Math.max(1, ...curve);

  return (
    <div className="page deck-editor">
      <div className="toolbar">
        <input className="deck-title" value={name} maxLength={120} onChange={(e) => { setName(e.target.value); setDirty(true); }} />
        <select value={format} onChange={(e) => { setFormat(e.target.value as DeckFormat); setDirty(true); }}>
          <option value="commander">Commander</option>
          <option value="constructed">Constructed</option>
          <option value="sandbox">Sandbox</option>
        </select>
        <ColorPips colors={deck.summary.color_identity} />
        <span className="hint">{total} cards</span>
        <span className="spacer" />
        <button className="btn" onClick={() => setImportOpen(true)}>Import text</button>
        <button className="btn" onClick={() => exportDeck(id).then(setExportText, toastError)}>Export</button>
        <button className="btn" onClick={() => navigate(`/play?deck=${id}`)} disabled={dirty}>Play</button>
        <button className="btn primary" onClick={save} disabled={!dirty || saving}>{saving ? "Saving…" : dirty ? "Save" : "Saved"}</button>
      </div>

      <div className="editor-grid">
        <div className="editor-list">
          <div className="add-row">
            <CardSearchBox onPick={(c) => { edit((l) => addCard(l, c, addSection)); requestCards([c.id]); }} onHover={(c) => setHover(c?.id ?? null)} />
            <select value={addSection} onChange={(e) => setAddSection(e.target.value as Section)}>
              {SECTIONS.map((s) => <option key={s} value={s}>to {SECTION_LABEL[s]}</option>)}
            </select>
          </div>
          {grouped.map(({ section, groups }) => (
            <section key={section} className="deck-section">
              <h3>
                {SECTION_LABEL[section]} <span className="hint">{sectionCount(entries, section)}</span>
              </h3>
              {groups.every((g) => g.rows.length === 0) && (
                <p className="hint">{section === "commander" ? "Right-click a card below and choose “Make commander”, or use the ★ button." : "Empty."}</p>
              )}
              {groups.map((g) => (
                <div key={g.label} className="type-group">
                  {g.label && <h4>{g.label} <span className="hint">{g.rows.reduce((n, r) => n + r.entry.quantity, 0)}</span></h4>}
                  {g.rows.map(({ entry, index }) => (
                    <EntryRow
                      key={`${entry.section}-${entry.printing_id ?? entry.name}-${index}`}
                      entry={entry}
                      card={entry.printing_id ? cards[entry.printing_id] : undefined}
                      onHover={() => setHover(entry.printing_id)}
                      onQty={(d) => edit((l) => changeQuantity(l, index, d))}
                      onRemove={() => edit((l) => removeEntry(l, index))}
                      onMove={(s) => edit((l) => moveToSection(l, index, s))}
                      onCommander={(keep) => edit((l) => setCommander(l, index, keep))}
                      onPrinting={() => setPrintingFor(index)}
                    />
                  ))}
                </div>
              ))}
            </section>
          ))}
        </div>
        <aside className="editor-side">
          <div className="preview-card">{hovered ? <CardFace card={hovered} size="normal" /> : <div className="card-face card-back" />}</div>
          <div className="panel">
            <h4>Mana curve</h4>
            <div className="curve">
              {curve.map((n, i) => (
                <div key={i} className="bar" title={`${n} at ${i}${i === 7 ? "+" : ""}`}>
                  <div style={{ height: `${(n / maxCurve) * 100}%` }} />
                  <span>{i === 7 ? "7+" : i}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="panel">
            <h4>Checks {dirty && <span className="hint">(save to refresh)</span>}</h4>
            {deck.warnings.length === 0 && <p className="ok">No warnings.</p>}
            <ul className="warnings">
              {deck.warnings.map((w, i) => <li key={i} className={w.level}>{w.message}</li>)}
            </ul>
            <p className="hint">Checks are advisory — nothing stops you from playing.</p>
          </div>
          <div className="panel">
            <h4>Notes</h4>
            <textarea rows={4} value={notes} maxLength={10000} onChange={(e) => { setNotes(e.target.value); setDirty(true); }} />
          </div>
        </aside>
      </div>

      {printingFor !== null && entries[printingFor] && (
        <PrintingPicker
          entry={entries[printingFor]!}
          onClose={() => setPrintingFor(null)}
          onPick={(c) => {
            edit((l) => setPrinting(l, printingFor, c));
            useCardCache.getState().put([c]);
            setPrintingFor(null);
          }}
        />
      )}
      {exportText !== null && (
        <Modal title="Export" onClose={() => setExportText(null)} footer={
          <button className="btn primary" onClick={() => navigator.clipboard?.writeText(exportText).then(() => toast("Copied"), toastError)}>Copy</button>
        }>
          <textarea className="deck-text" readOnly value={exportText} rows={20} onFocus={(e) => e.target.select()} />
        </Modal>
      )}
      {importOpen && <ImportInto id={id} onClose={() => setImportOpen(false)} onDone={(d) => { load(d); setImportOpen(false); }} />}
    </div>
  );
}

function EntryRow(props: {
  entry: DeckEntry;
  card: CardData | undefined;
  onHover: () => void;
  onQty: (delta: number) => void;
  onRemove: () => void;
  onMove: (s: Section) => void;
  onCommander: (keepExisting: boolean) => void;
  onPrinting: () => void;
}) {
  const { entry, card } = props;
  const [menu, setMenu] = useState(false);
  return (
    <div className={`entry-row ${entry.printing_id ? "" : "unresolved"}`} onPointerEnter={props.onHover} onContextMenu={(e) => { e.preventDefault(); setMenu(true); }}>
      <button className="qty-btn" onClick={() => props.onQty(-1)} aria-label="Remove one">−</button>
      <span className="qty">{entry.quantity}</span>
      <button className="qty-btn" onClick={() => props.onQty(1)} aria-label="Add one">+</button>
      <span className="name" title={entry.printing_id ? undefined : "Not found in local database"}>{entry.name}</span>
      <span className="cost"><ManaText text={card?.mana_cost} /></span>
      <button className="set-btn" onClick={props.onPrinting} title="Choose printing">{entry.set_code?.toUpperCase() ?? "?"}</button>
      {entry.section !== "commander" && (
        <button className="icon-btn" title="Make commander (shift: add as partner)" onClick={(e) => props.onCommander(e.shiftKey)}>★</button>
      )}
      <button className="icon-btn" onClick={() => setMenu((m) => !m)} aria-label="More">⋯</button>
      {menu && (
        <div className="row-menu" onPointerLeave={() => setMenu(false)}>
          <button onClick={() => { props.onCommander(false); setMenu(false); }}>Make commander</button>
          <button onClick={() => { props.onCommander(true); setMenu(false); }}>Add as partner commander</button>
          {SECTIONS.filter((s) => s !== entry.section).map((s) => (
            <button key={s} onClick={() => { props.onMove(s); setMenu(false); }}>Move to {SECTION_LABEL[s]}</button>
          ))}
          <button onClick={() => { props.onPrinting(); setMenu(false); }}>Choose printing…</button>
          <button className="danger" onClick={() => { props.onRemove(); setMenu(false); }}>Remove</button>
        </div>
      )}
    </div>
  );
}

function PrintingPicker({ entry, onPick, onClose }: { entry: DeckEntry; onPick: (c: CardData) => void; onClose: () => void }) {
  const [printings, setPrintings] = useState<CardData[] | null>(null);
  useEffect(() => {
    if (entry.printing_id) getPrintings(entry.printing_id).then(setPrintings, toastError);
  }, [entry.printing_id]);
  return (
    <Modal title={`Printings of ${entry.name}`} onClose={onClose} wide>
      {!entry.printing_id && <p>This card is not in the local database. Remove it or re-add it from search.</p>}
      {printings === null && entry.printing_id && <p>Loading…</p>}
      <div className="card-grid small">
        {printings?.map((p) => (
          <button key={p.id} className={`grid-card ${p.id === entry.printing_id ? "selected" : ""}`} onClick={() => onPick(p)} title={`${p.set_name} #${p.collector_number}`}>
            <CardFace card={p} size="small" />
            <span className="caption">{p.set_code.toUpperCase()} #{p.collector_number}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
}

function ImportInto({ id, onClose, onDone }: { id: string; onClose: () => void; onDone: (d: Deck) => void }) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"replace" | "append">("append");
  const submit = async () => {
    try {
      const d = await importIntoDeck(id, text, mode);
      const bad = d.import_report?.unresolved.length ?? 0;
      toast(bad ? `${bad} card(s) not found` : "Imported", bad ? "warn" : "info");
      onDone(d);
    } catch (e) {
      toastError(e);
    }
  };
  return (
    <Modal title="Import text into deck" onClose={onClose} footer={
      <>
        <div className="seg">
          <button className={mode === "append" ? "on" : ""} onClick={() => setMode("append")}>Append</button>
          <button className={mode === "replace" ? "on" : ""} onClick={() => setMode("replace")}>Replace all</button>
        </div>
        <span className="spacer" />
        <button className="btn primary" disabled={!text.trim()} onClick={submit}>Import</button>
      </>
    }>
      <textarea className="deck-text" autoFocus rows={16} value={text} onChange={(e) => setText(e.target.value)} placeholder="1 Sol Ring" />
    </Modal>
  );
}
