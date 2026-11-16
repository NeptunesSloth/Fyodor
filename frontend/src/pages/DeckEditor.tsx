import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { ManaText } from "../cards/ManaText";
import { GLYPHS } from "../cards/proxy";
import { CardSearchBox } from "../components/CardSearchBox";
import { ColorPips } from "../components/ColorPips";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { getPrintings } from "../services/cards";
import { type ArtStatus, applySource, artStatus, cacheArt, checkSource, exportDeck, getDeck, ignoreSource, importIntoDeck, resetDeckRows, unlinkSource, updateDeck, waitForJob } from "../services/decks";
import { askText } from "../components/Prompt";
import { refreshCards, requestCards, useCardCache } from "../state/cardCache";
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
import { SECTION_LABEL, SECTIONS, type Deck, type DeckEntry, type DeckFormat, type Job, type Section, type SourceDiff } from "../types/decks";
import { artFirst, checkSummary, curveStats, groupGlyph, groupTitle, savedRows } from "./deckBits";
import { DeckArt, DeckMenu, type DeckMenuItem } from "./DeckParts";
import "./decks.css";

/**
 * A deck, read as a deck: its commander's art, name, colours, size and check state at the head with Play; the list in
 * sections and type groups (the proxy cards' type marks, counts) whose rows keep their editing controls quiet until hovered
 * or focused; beside it the card under the pointer (its scan when cached, else its proxy), the mana curve, the checks,
 * artwork caching and notes.
 */
export function DeckEditor({ id, jobId }: { id: string; jobId?: string | null }) {
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
  const [groupBy, setGroupBy] = useState<"type" | "category">(() => (localStorage.getItem("fyodor.deck.groupBy") === "category" ? "category" : "type"));
  const [exportFormat, setExportFormat] = useState<"archidekt" | "plain">("archidekt");
  const [art, setArt] = useState<ArtStatus | null>(null);
  const [artJob, setArtJob] = useState<Job | null>(null);
  const [sourceDiff, setSourceDiff] = useState<{ diff: SourceDiff; local_edits: boolean } | null>(null);
  const [sourceBusy, setSourceBusy] = useState(false);
  const cards = useCardCache((s) => s.cards);
  const checksRef = useRef<HTMLElement>(null);

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

  const refreshArt = useCallback(() => artStatus(id).then(setArt, () => setArt(null)), [id]);
  useEffect(() => void refreshArt(), [refreshArt]);

  const tracked = useRef(new Set<string>());
  const trackJob = useCallback(
    (jid: string) => {
      if (tracked.current.has(jid)) return;
      tracked.current.add(jid);
      void waitForJob(jid, setArtJob).then((job) => {
        if (job.state === "done") toast(`Artwork: ${job.message}`);
        else toast(`Artwork caching failed: ${job.message}`, "error");
        void refreshArt();
        refreshCards(entries.map((e) => e.printing_id).filter((x): x is string => !!x));
      }, toastError);
    },
    [refreshArt, entries],
  );
  useEffect(() => {
    if (jobId) trackJob(jobId);
  }, [jobId, trackJob]);

  const startArt = async () => {
    try {
      const job = await cacheArt(id);
      setArtJob(job);
      trackJob(job.id);
    } catch (e) {
      toastError(e);
    }
  };

  const onCheckSource = async () => {
    setSourceBusy(true);
    try {
      const res = await checkSource(id);
      setSourceDiff(res);
      if (!res.diff.changed) toast("The deck matches Archidekt");
    } catch (e) {
      toastError(e);
    } finally {
      setSourceBusy(false);
    }
  };

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
      load(await updateDeck(id, { name: name.trim() || "Untitled deck", format, notes, entries, categories: mergedCategories(deck, entries) }));
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
        const g =
          groupBy === "category"
            ? r.entry.categories?.[0] ?? "Uncategorized"
            : typeGroup(r.entry.printing_id ? cards[r.entry.printing_id]?.type_line : null);
        byType.set(g, [...(byType.get(g) ?? []), r]);
      }
      const order = groupBy === "category" ? [...byType.keys()].sort((a, b) => (a === "Uncategorized" ? 1 : b === "Uncategorized" ? -1 : a.localeCompare(b))) : TYPE_GROUP_ORDER;
      const groups = order.filter((g) => byType.has(g)).map((label) => ({
        label,
        rows: byType.get(label)!.sort((a, b) => a.entry.name.localeCompare(b.entry.name)),
      }));
      out.push({ section, groups });
    }
    return out;
  }, [entries, cards, format, groupBy]);

  const curve = useMemo(() => curveStats(entries, cards), [entries, cards]);

  if (!deck) return <div className="page de-page de-loading">Loading…</div>;
  const commanderIds = entries.filter((e) => e.section === "commander" && e.printing_id).map((e) => e.printing_id!);
  const commanderNames = entries.filter((e) => e.section === "commander").map((e) => e.name);
  const shownId = hover ?? commanderIds[0];
  const hovered = shownId ? cards[shownId] : undefined;
  const total = sectionCount(entries, "main") + sectionCount(entries, "commander");
  const maxCurve = Math.max(1, ...curve.buckets);
  const checks = checkSummary(deck.warnings);
  const showChecks = () => {
    checksRef.current?.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    checksRef.current?.focus({ preventScroll: true });
  };

  return (
    <div className="page de-page deck-editor">
      <header className="de-head">
        <DeckArt ids={commanderIds} className="de-art" />
        <div className="de-id">
          <label className="de-title">
            <input className="deck-title" aria-label="Deck name" value={name} maxLength={120} spellCheck={false} onChange={(e) => { setName(e.target.value); setDirty(true); }} />
            <Icon name="pen" size={16} className="de-title-pen" />
          </label>
          <p className={`de-cmdr ${commanderNames.length ? "" : "none"}`}>
            {commanderNames.length ? commanderNames.join(" & ") : format === "commander" ? "No commander yet: choose one with the crown on a card's row" : "No commander"}
          </p>
          <p className="de-facts">
            <ColorPips colors={deck.summary.color_identity} />
            <span className="de-total">{total} cards</span>
            <button type="button" className={`de-check ${checks.level}`} onClick={showChecks} title={dirty ? "Checks refresh when you save" : "Show the deck checks"}>
              {checks.level === "ok" ? <Icon name="check" size={14} /> : <span className="de-check-mark" aria-hidden>!</span>}
              {checks.text}
            </button>
          </p>
        </div>
        <div className="de-acts">
          <button className="tt-btn ghost" onClick={() => setImportOpen(true)}>Import text</button>
          <button className="tt-btn ghost" onClick={() => exportDeck(id, exportFormat).then(setExportText, toastError)} title="Archidekt-compatible text">Export</button>
          <button className={`tt-btn de-play ${dirty ? "" : "brass"}`} onClick={() => navigate(`/play?deck=${id}`)} disabled={dirty} title={dirty ? "Save the deck to play it" : undefined}>
            <Icon name="swords" size={15} />Play
          </button>
          <button className={`tt-btn de-save ${dirty ? "brass" : ""}`} onClick={save} disabled={!dirty || saving}>
            {!dirty && !saving && <Icon name="check" size={15} />}
            {saving ? "Saving…" : dirty ? "Save" : "Saved"}
          </button>
        </div>
      </header>

      <div className="de-grid">
        <div className="de-list">
          <div className="de-add">
            <CardSearchBox onPick={(c) => { edit((l) => addCard(l, c, addSection)); requestCards([c.id]); }} onHover={(c) => setHover(c?.id ?? null)} />
            <select value={addSection} aria-label="Add cards to" onChange={(e) => setAddSection(e.target.value as Section)}>
              {SECTIONS.map((s) => <option key={s} value={s}>to {SECTION_LABEL[s]}</option>)}
            </select>
            <div className="de-seg" role="group" aria-label="Group the deck" title="Group the deck by card type or by Archidekt category">
              {(["type", "category"] as const).map((g) => (
                <button key={g} type="button" className={groupBy === g ? "on" : ""} aria-pressed={groupBy === g}
                  onClick={() => { setGroupBy(g); try { localStorage.setItem("fyodor.deck.groupBy", g); } catch { /* ignore */ } }}>
                  {g === "type" ? "By type" : "By category"}
                </button>
              ))}
            </div>
          </div>
          {grouped.map(({ section, groups }) => (
            <section key={section} className={`de-section de-sec-${section}`} aria-label={SECTION_LABEL[section]}>
              <h2 className="de-sec-head">
                {SECTION_LABEL[section]} <span className="de-n">{sectionCount(entries, section)}</span>
              </h2>
              {groups.every((g) => g.rows.length === 0) && (
                <p className="de-empty">{section === "commander" ? "Choose “Make commander” in a card's menu (or right-click it), or use its crown button." : "No cards yet: add some with the search above."}</p>
              )}
              <div className={section === "main" ? "de-groups" : undefined}>
                {groups.map((g) => {
                  const glyph = groupBy === "type" ? groupGlyph(g.label) : null;
                  return (
                    <div key={g.label} className="de-group">
                      {g.label && (
                        <h3 className="de-group-head">
                          {glyph && <svg className="de-glyph" viewBox="0 0 24 24" aria-hidden><path d={GLYPHS[glyph]} /></svg>}
                          {groupBy === "type" ? groupTitle(g.label) : g.label} <span className="de-n">{g.rows.reduce((n, r) => n + r.entry.quantity, 0)}</span>
                        </h3>
                      )}
                      <ul className="de-rows">
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
                            onCategories={async () => {
                              const v = await askText(`Categories for ${entry.name} (comma separated, first is primary)`, (entry.categories ?? []).join(", "));
                              if (v !== null) edit((l) => l.map((x, i) => (i === index ? { ...x, categories: v.split(",").map((c) => c.trim()).filter(Boolean) } : x)));
                            }}
                            onFinish={(finish) => edit((l) => l.map((x, i) => (i === index ? { ...x, finish } : x)))}
                          />
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>

        <aside className="de-side" aria-label="Deck details">
          <div className="de-preview">{hovered ? <CardFace card={hovered} size="normal" /> : <div className="card-face card-back" />}</div>

          <section className="de-panel de-curve" aria-labelledby="de-curve-title">
            <h2 id="de-curve-title">Mana curve
              {curve.average !== null && <span className="de-panel-aside">Average {curve.average.toFixed(2)}</span>}
            </h2>
            <div className="de-bars" role="img" aria-label={`Nonland cards by mana value: ${curve.buckets.map((n, i) => `${n} at ${i}${i === 7 ? " or more" : ""}`).join(", ")}`}>
              {curve.buckets.map((n, i) => (
                <div key={i} className={`de-bar ${n ? "" : "zero"}`} title={`${n} card${n === 1 ? "" : "s"} at mana value ${i}${i === 7 ? " or more" : ""}`}>
                  <span className="de-bar-n">{n || ""}</span>
                  <div className="de-bar-fill" style={{ "--h": n / maxCurve } as React.CSSProperties} />
                  <span className="de-bar-mv">{i === 7 ? "7+" : i}</span>
                </div>
              ))}
            </div>
            <p className="de-curve-foot"><span>{curve.spells} nonland</span><span>{curve.lands} land{curve.lands === 1 ? "" : "s"}</span></p>
          </section>

          <section className="de-panel de-checks" id="deck-checks" ref={checksRef} tabIndex={-1} aria-labelledby="de-checks-title">
            <h2 id="de-checks-title">Checks {dirty && <span className="de-panel-aside">save to refresh</span>}</h2>
            {deck.warnings.length === 0 && <p className="de-ok"><Icon name="check" size={15} />No problems found.</p>}
            {deck.warnings.length > 0 && (
              <ul className="de-warnings">
                {deck.warnings.map((w, i) => <li key={i} className={w.level}><span className="de-wmark" aria-hidden>{w.level === "info" ? "i" : "!"}</span>{w.message}</li>)}
              </ul>
            )}
            <p className="de-note">Checks are advisory: nothing stops you from playing.</p>
          </section>

          <section className="de-panel" aria-labelledby="de-art-title">
            <h2 id="de-art-title">Artwork</h2>
            {art && (
              <p className="de-panel-text">
                {art.missing === 0 ? <span className="de-ok"><Icon name="check" size={15} />All {art.printings} printings cached for offline play.</span> : <ArtSummary art={art} />}
              </p>
            )}
            {artJob?.state === "running" ? (
              <div className="de-progress" role="progressbar" aria-label="Caching artwork" aria-valuemin={0} aria-valuemax={artJob.total || 1} aria-valuenow={artJob.done}>
                <div style={{ width: `${artJob.total ? (artJob.done / artJob.total) * 100 : 5}%` }} />
                <span>{artJob.done}/{artJob.total || "…"}</span>
              </div>
            ) : (
              art && art.missing > 0 && <button className="tt-btn" onClick={() => void startArt()}><Icon name="download" size={15} />Cache entire deck artwork</button>
            )}
            {artJob && artJob.state !== "running" && <p className="de-note">{artJob.message}</p>}
          </section>

          {deck.source?.kind === "archidekt" && (
            <section className="de-panel" aria-labelledby="de-src-title">
              <h2 id="de-src-title">Archidekt</h2>
              <p className="de-panel-text">
                Imported from{" "}
                {deck.source.url ? <a href={deck.source.url} target="_blank" rel="noreferrer noopener">{deck.source.name ?? `deck ${deck.source.id}`}</a> : deck.source.name}
                {deck.source.imported_at && <span className="de-dim"> on {deck.source.imported_at.slice(0, 10)}</span>}
              </p>
              <div className="de-panel-acts">
                <button className="tt-btn" disabled={sourceBusy} onClick={() => void onCheckSource()}>{sourceBusy ? "Checking…" : "Check for updates"}</button>
                <button className="tt-btn ghost" onClick={async () => { await unlinkSource(id).catch(toastError); load(await getDeck(id)); }}>Unlink</button>
              </div>
              <p className="de-note">This is a normal local deck: it never needs Archidekt to play.</p>
            </section>
          )}

          {savedRows(deck.row_overrides).length > 0 && ( /* -- saved rows -- learned at the table, shown only once there are some */
            <section className="de-panel de-saved-rows" aria-labelledby="de-rows-title" data-testid="deck-saved-rows">
              <h2 id="de-rows-title">Table rows</h2>
              <p className="de-note">Cards you moved into another row at the table enter there in later games.</p>
              <dl className="de-rows-list">
                {savedRows(deck.row_overrides).map((g) => (
                  <div key={g.row}><dt>{g.label}</dt><dd>{g.names.join(", ")}</dd></div>
                ))}
              </dl>
              <div className="de-panel-acts">
                <button className="tt-btn ghost" data-testid="deck-reset-rows" onClick={async () => {
                  try {
                    await resetDeckRows(id);
                    setDeck((d) => (d ? { ...d, row_overrides: {} } : d));
                    toast("Saved rows reset: cards enter in their type's row again");
                  } catch (e) { toastError(e); }
                }}>Reset saved rows</button>
              </div>
            </section>
          )}

          <section className="de-panel">
            <h2><label htmlFor="de-notes">Notes</label></h2>
            <textarea id="de-notes" rows={4} value={notes} maxLength={10000} placeholder="Game plan, mulligan rules, cards to swap…" onChange={(e) => { setNotes(e.target.value); setDirty(true); }} />
          </section>
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
          <>
            <div className="de-seg">
              {(["archidekt", "plain"] as const).map((f) => (
                <button key={f} type="button" className={exportFormat === f ? "on" : ""} aria-pressed={exportFormat === f} onClick={() => { setExportFormat(f); exportDeck(id, f).then(setExportText, toastError); }}>
                  {f === "archidekt" ? "Archidekt" : "Plain (sections)"}
                </button>
              ))}
            </div>
            <span className="spacer" />
            <button className="tt-btn brass" onClick={() => navigator.clipboard?.writeText(exportText).then(() => toast("Copied"), toastError)}>Copy</button>
          </>
        }>
          <p className="hint">{exportFormat === "archidekt" ? "Paste into Archidekt’s Import. Categories, commander, sideboard, maybeboard, printings and foils are kept." : "Section headers format for other sites."}</p>
          <textarea className="deck-text" readOnly value={exportText} rows={20} onFocus={(e) => e.target.select()} />
        </Modal>
      )}
      {sourceDiff && sourceDiff.diff.changed && (
        <SourceDiffDialog
          diff={sourceDiff.diff}
          localEdits={sourceDiff.local_edits}
          onClose={() => setSourceDiff(null)}
          onApply={async () => {
            try {
              const d = await applySource(id);
              load(d);
              toast(d.conflicts?.length ? `Updated — ${d.conflicts.length} local edit(s) kept` : "Deck updated from Archidekt");
              setSourceDiff(null);
            } catch (e) {
              toastError(e);
            }
          }}
          onIgnore={async () => {
            try {
              load(await ignoreSource(id));
              setSourceDiff(null);
            } catch (e) {
              toastError(e);
            }
          }}
        />
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
  onCategories: () => void;
  onFinish: (finish: "nonfoil" | "foil" | "etched") => void;
}) {
  const { entry, card } = props;
  const fallback = entry.resolution === "fallback" || entry.resolution === "set";
  const [menu, setMenu] = useState(false);
  // (built only while the menu is open: a hundred rows render on every edit)
  const items = (): DeckMenuItem[] => [
    { label: "Make commander", icon: "crown", onClick: () => props.onCommander(false) },
    { label: "Add as partner commander", onClick: () => props.onCommander(true) },
    "separator",
    ...SECTIONS.filter((s) => s !== entry.section).map((s) => ({ label: `Move to ${SECTION_LABEL[s]}`, onClick: () => props.onMove(s) })),
    "separator",
    { label: "Choose printing…", onClick: props.onPrinting },
    { label: "Edit categories…", onClick: props.onCategories },
    ...(["nonfoil", "foil", "etched"] as const).filter((f) => f !== (entry.finish ?? "nonfoil")).map((f) => ({ label: `Mark ${f === "nonfoil" ? "non-foil" : f}`, onClick: () => props.onFinish(f) })),
    "separator",
    { label: "Remove", icon: "trash", danger: true, onClick: props.onRemove },
  ];
  return (
    <li className={`de-row ${entry.printing_id ? "" : "unresolved"} ${menu ? "menu-open" : ""}`} onPointerEnter={props.onHover} onFocus={props.onHover}
      onContextMenu={(e) => { e.preventDefault(); setMenu(true); }}>
      <span className="de-qty">
        <button className="de-step" onClick={() => props.onQty(-1)} aria-label="Remove one">−</button>
        <span className={`de-q ${entry.quantity > 1 ? "many" : ""}`}>{entry.quantity}</span>
        <button className="de-step" onClick={() => props.onQty(1)} aria-label="Add one">+</button>
      </span>
      <span className="de-name" title={entry.printing_id ? undefined : "Not found in local database"}>{entry.name}</span>
      {entry.categories && entry.categories.length > 0 && (
        <span className="de-cats" onClick={props.onCategories} title="Archidekt categories — click to edit">
          {entry.categories.slice(0, 2).map((c) => <span key={c} className="de-cat">{c}</span>)}
          {entry.categories.length > 2 && <span className="de-cat">+{entry.categories.length - 2}</span>}
        </span>
      )}
      {entry.finish && entry.finish !== "nonfoil" && <span className={`finish ${entry.finish}`} title={entry.finish}>{entry.finish === "foil" ? "F" : "E"}</span>}
      {fallback && (
        <span className="de-fallback" title={`Requested ${[entry.requested?.set_code?.toUpperCase(), entry.requested?.collector_number && `#${entry.requested.collector_number}`].filter(Boolean).join(" ") || "a printing"} that isn't in the local card data; using ${entry.set_code?.toUpperCase()} #${entry.collector_number}`} aria-label="Printing substituted">!</span>
      )}
      <span className="de-cost"><ManaText text={card?.mana_cost} /></span>
      <button className="de-set" onClick={props.onPrinting} title="Choose printing">{entry.set_code?.toUpperCase() ?? "?"}</button>
      {entry.section !== "commander" ? (
        <button className="tt-icon de-crown" aria-label="Make commander" title="Make commander (shift: add as partner)" onClick={(e) => props.onCommander(e.shiftKey)}>
          <Icon name="crown" size={16} />
        </button>
      ) : <span className="de-crown-gap" />}
      <DeckMenu label="More" items={menu ? items() : []} open={menu} onOpenChange={setMenu} className="de-more" />
    </li>
  );
}

/** The deck's artwork in words: printings without their own picture, and how many of those show another printing's instead. */
function ArtSummary({ art }: { art: ArtStatus }) {
  const borrowed = Math.min(art.borrowed ?? 0, art.missing);
  const proxies = art.missing - borrowed;
  if (borrowed === 0) return <>{art.missing} of {art.printings} printings have no cached image. Cards without one play as readable proxies.</>;
  return (
    <>
      {art.missing} of {art.printings} printings have no cached image of their own; {borrowed === art.missing ? (borrowed === 1 ? "it shows" : "they show") : `${borrowed} show`} another printing's art of the same card.
      {proxies > 0 && <> {proxies === 1 ? "1 plays" : `${proxies} play`} as a readable proxy.</>}
    </>
  );
}

function PrintingPicker({ entry, onPick, onClose }: { entry: DeckEntry; onPick: (c: CardData) => void; onClose: () => void }) {
  const [printings, setPrintings] = useState<CardData[] | null>(null);
  useEffect(() => {
    if (entry.printing_id) getPrintings(entry.printing_id).then((ps) => setPrintings(artFirst(ps)), toastError);
  }, [entry.printing_id]);
  const byId = new Map((printings ?? []).map((p) => [p.id, p]));
  const withArt = printings?.filter((p) => p.own_image ?? p.has_image).length ?? 0;
  return (
    <Modal title={`Printings of ${entry.name}`} onClose={onClose} wide>
      {!entry.printing_id && <p>This card is not in the local database. Remove it or re-add it from search.</p>}
      {printings === null && entry.printing_id && <p>Loading…</p>}
      {printings && printings.length > 1 && withArt < printings.length && (
        <p className="de-note de-printings-note">
          {withArt === 0
            ? "No printing of this card has art on this computer: it plays as a readable proxy."
            : `${withArt} of ${printings.length} printings have art on this computer. The others show that art until their own is downloaded.`}
        </p>
      )}
      <div className="card-grid small de-printings">
        {printings?.map((p) => {
          const own = p.own_image ?? p.has_image;
          const from = !own && p.art_from ? byId.get(p.art_from) : undefined;
          const title = `${p.set_name} #${p.collector_number}${own ? " — art on this computer" : from ? ` — no art on this computer; shows ${from.set_code.toUpperCase()} #${from.collector_number}'s art` : " — no art on this computer"}`;
          return (
            <button key={p.id} className={`grid-card ${p.id === entry.printing_id ? "selected" : ""} ${own ? "de-art-here" : "de-art-elsewhere"}`} onClick={() => onPick(p)} title={title} aria-pressed={p.id === entry.printing_id}>
              <CardFace card={p} size="small" />
              <span className="caption">{p.set_code.toUpperCase()} #{p.collector_number}</span>
              {own
                ? <span className="caption de-art-tag">Art here</span>
                : <span className="caption de-art-tag">{from ? `No art here · shows ${from.set_code.toUpperCase()} #${from.collector_number}` : "No art here"}</span>}
            </button>
          );
        })}
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
        <div className="de-seg">
          <button type="button" className={mode === "append" ? "on" : ""} aria-pressed={mode === "append"} onClick={() => setMode("append")}>Append</button>
          <button type="button" className={mode === "replace" ? "on" : ""} aria-pressed={mode === "replace"} onClick={() => setMode("replace")}>Replace all</button>
        </div>
        <span className="spacer" />
        <button className="tt-btn brass" disabled={!text.trim()} onClick={submit}>Import</button>
      </>
    }>
      <textarea className="deck-text" autoFocus rows={16} value={text} onChange={(e) => setText(e.target.value)} placeholder="1 Sol Ring" aria-label="Deck list" />
    </Modal>
  );
}

function mergedCategories(deck: Deck | null, entries: DeckEntry[]) {
  const out = [...(deck?.categories ?? [])];
  const known = new Set(out.map((c) => c.name.toLowerCase()));
  for (const e of entries) {
    for (const c of e.categories ?? []) {
      if (!known.has(c.toLowerCase())) {
        known.add(c.toLowerCase());
        out.push({ name: c, included_in_deck: true, premier: false });
      }
    }
  }
  return out;
}

function SourceDiffDialog({ diff, localEdits, onApply, onIgnore, onClose }: { diff: SourceDiff; localEdits: boolean; onApply: () => void; onIgnore: () => void; onClose: () => void }) {
  return (
    <Modal
      title="Archidekt changes"
      onClose={onClose}
      footer={
        <>
          <button className="tt-btn ghost" onClick={onClose}>Review later</button>
          <button className="tt-btn" onClick={onIgnore}>Ignore</button>
          <button className="tt-btn brass" onClick={onApply}>Apply</button>
        </>
      }
    >
      <ul className="diff-list">
        {diff.added.map((a, i) => <li key={`a${i}`} className="ok">+ {a.quantity} {a.name}{a.section !== "main" ? ` (${a.section})` : ""}</li>)}
        {diff.removed.map((a, i) => <li key={`r${i}`} className="error">− {a.quantity} {a.name}{a.section !== "main" ? ` (${a.section})` : ""}</li>)}
        {diff.printing_changed.map((p, i) => <li key={`p${i}`}>Printing changed: {p.name} ({p.from} → {p.to})</li>)}
        {diff.section_changed.map((p, i) => <li key={`s${i}`}>{p.name}: {p.from} → {p.to}</li>)}
        {diff.category_changed.map((p, i) => <li key={`c${i}`} className="hint">{p.name}: categories {p.from.join(", ") || "—"} → {p.to.join(", ") || "—"}</li>)}
      </ul>
      {localEdits && <p className="warn small">You changed this deck locally since import. Apply keeps your local edits where they conflict.</p>}
      <p className="hint">Nothing is changed until you choose Apply. Ignore keeps your deck and hides these changes.</p>
    </Modal>
  );
}
