/**
 * -- Teach Fyodor -- teaching the engine a new mechanic (a keyword like "Plunge N", a keyword action like "dive" — "it dives") or one
 * card's line it still plays by hand, by snapping pieces together like a children's coding app (docs/TEACH_FYODOR.md). Left: the
 * script workspace; right: the COMMANDS palette; top: back, the big ▶ Try it, help, and the taught things as avatars to switch
 * between. Under the workspace: what Fyodor reads the pieces as, in plain words, checked live by the engine itself. Everything saved
 * is data, never code.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CardSearchBox } from "../components/CardSearchBox";
import { Icon } from "../components/Icon";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { navigate } from "../hooks/useHashRoute";
import { rememberSeat } from "../services/games";
import { cardLines, checkEntry, createTaught, deleteTaught, enableTaught, exportUrl, getVocabulary, importTaught, listTaught, tryIt, updateTaught } from "../services/teach";
import { type DragItem, under, useDrag } from "../teach/drag";
import { Palette } from "../teach/Palette";
import { actionPhrase, actionSentences, compileEntry, keywordLine, selfWord } from "../teach/sentence";
import { actionHat, addAbility, asKind, emptyScript, find, fromEntry, hasWork, insert, move, newNode, nodeAt, order, remove, removeAbility, setValue, toEntry, type Path, type Script } from "../teach/script";
import { chipFits, firstSpot, spots } from "../teach/snap";
import { chipKey, spotKey, Workspace } from "../teach/Workspace";
import type { CardLines, CheckResult, Kind, Piece, TaughtRow, Value, Vocabulary } from "../teach/types";

const KIND_LABEL: Record<Kind, string> = { keyword: "Keyword", action: "Action", card: "Card line" };
import type { CardData } from "../types/cards";
import "./teach.css";

const parseSpot = (key: string): Path => {
  const [a, rest] = key.split(":");
  return { ability: Number(a), index: rest ? rest.split(".").map(Number) : [] };
};

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function TeachPage() {
  const [voc, setVoc] = useState<Vocabulary | null>(null);
  const [rows, setRows] = useState<TaughtRow[]>([]);
  const [script, setScript] = useState<Script>(() => emptyScript());
  const [editing, setEditing] = useState<string | null>(null); // the library row being edited
  const [active, setActive] = useState(0);
  const [focusUid, setFocusUid] = useState<string | null>(null);
  const [check, setCheck] = useState<CheckResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [card, setCard] = useState<CardLines | null>(null);
  const [help, setHelp] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getVocabulary().then(setVoc, toastError);
    listTaught().then(setRows, toastError);
  }, []);

  const pieces = useMemo(() => Object.fromEntries((voc?.pieces ?? []).map((p) => [p.id, p])) as Record<string, Piece>, [voc]);
  const me = script.kind === "action" ? "it" : selfWord(script.kind === "card" ? script.card?.type_line : "Creature");
  const entry = useMemo(() => (voc ? toEntry(script, voc) : null), [script, voc]);
  const lines = useMemo(() => (voc && entry ? compileEntry(entry, voc, { me }) : []), [entry, voc, me]);
  const linesN2 = useMemo(() => (voc && entry && script.param ? compileEntry(entry, voc, { me, n: 2 }) : null), [entry, voc, me, script.param]);
  // an action's stack always starts with the action hat (removed by hand: put back)
  useEffect(() => {
    if (script.kind === "action" && script.abilities.some((a) => !a.hat)) {
      setScript({ ...script, abilities: script.abilities.map((a) => (a.hat ? a : { ...a, hat: actionHat() })) });
    }
  }, [script]);

  // live check by the engine, a moment after the last change
  const debounced = useDebounced(entry, 350);
  useEffect(() => {
    if (!debounced || !hasWork(script)) { setCheck(null); return; }
    let gone = false;
    setChecking(true);
    checkEntry(debounced, script.card?.type_line).then((r) => { if (!gone) { setCheck(r); setChecking(false); } }, () => { if (!gone) setChecking(false); });
    return () => { gone = true; };
  }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------------------------------------------ dragging
  const scriptWithout = useCallback((uid: string): Script => {
    const p = find(script, uid);
    return p ? remove(script, p) : script;
  }, [script]);

  const allowedFor = useCallback((item: DragItem): Set<string> => {
    if (!voc || item.kind === "chip") return new Set();
    const base = item.kind === "node" ? scriptWithout(item.uid) : script;
    return new Set(spots(item.piece, base, voc).map((s) => spotKey(s.path)));
  }, [script, voc, scriptWithout]);

  const chipTargetsFor = useCallback((item: DragItem): Set<string> => {
    if (item.kind !== "chip") return new Set();
    const out = new Set<string>();
    for (const { uid, path } of order(script)) {
      const node = nodeAt(script, path);
      const piece = node ? pieces[node.id] : undefined;
      for (const [k, slot] of Object.entries(piece?.slots ?? {})) if (chipFits(item.value, slot, script.param)) out.add(chipKey(uid, k));
    }
    return out;
  }, [script, pieces]);

  const resolve = useCallback((item: DragItem, x: number, y: number): string | null => {
    if (item.kind === "chip") {
      const el = under(x, y, "data-chip");
      const key = el?.dataset.chip;
      return key && chipTargetsFor(item).has(key) ? `chip:${key}` : null;
    }
    if (item.kind === "node" && under(x, y, "data-trash")) return "trash";
    const allowed = allowedFor(item);
    const direct = under(x, y, "data-spot")?.dataset.spot;
    if (direct && allowed.has(direct)) return `spot:${direct}`;
    // over a row: the slot just above or below it, whichever is nearer
    const row = under(x, y, "data-row");
    if (row) {
      const r = row.getBoundingClientRect();
      const wrap = row.parentElement;
      const near = y < r.top + r.height / 2 ? wrap?.previousElementSibling?.querySelector?.("[data-spot]") ?? wrap?.querySelector("[data-spot]") : wrap?.nextElementSibling?.querySelector?.("[data-spot]");
      const key = (near as HTMLElement | null)?.dataset?.spot;
      if (key && allowed.has(key)) return `spot:${key}`;
    }
    return null;
  }, [allowedFor, chipTargetsFor]);

  const onDrop = useCallback((item: DragItem, target: string | null) => {
    if (!target || !voc) return;
    if (target === "trash" && item.kind === "node") {
      const p = find(script, item.uid);
      if (p) setScript(remove(script, p));
      return;
    }
    if (target.startsWith("chip:") && item.kind === "chip") {
      const [uid, slot] = target.slice(5).split("/");
      const p = uid ? find(script, uid) : null;
      if (p && slot) setScript(setValue(script, p, slot, item.value));
      return;
    }
    if (target.startsWith("spot:")) {
      const path = parseSpot(target.slice(5));
      if (item.kind === "piece") {
        const node = newNode(item.piece);
        setScript(insert(script, path, node));
        setFocusUid(node.uid);
      } else if (item.kind === "node") {
        const from = find(script, item.uid);
        if (from) setScript(move(script, from, path));
      }
      setActive(path.ability);
    }
  }, [script, voc]);

  const { drag, start, ghost } = useDrag(resolve, onDrop);
  const allowed = useMemo(() => (drag ? allowedFor(drag.item) : new Set<string>()), [drag, allowedFor]);
  const chipTargets = useMemo(() => (drag ? chipTargetsFor(drag.item) : new Set<string>()), [drag, chipTargetsFor]);

  // ------------------------------------------------------------------------------------------------------ clicks and keys
  const addPiece = (piece: Piece) => {
    if (!voc) return;
    const spot = firstSpot(piece, script, voc, active);
    if (!spot) { toast(`Nowhere to put “${piece.label}” yet${piece.role === "static" ? ": start with the Always piece" : piece.role === "cost" ? ": start with Pay to use it" : piece.after ? `: it follows ${pieces[piece.after]?.label}` : piece.hats ? `: it goes under ${piece.hats.map((h) => pieces[h]?.label ?? h).join(" or ")}` : ""}`, "error"); return; }
    const node = newNode(piece);
    setScript(insert(script, spot.path, node));
    setActive(spot.path.ability);
    setFocusUid(node.uid);
  };
  const addChip = (value: Value) => {
    // the focused row's first fitting setting, else the first anywhere
    const list = order(script);
    const start = Math.max(0, list.findIndex((o) => o.uid === focusUid));
    for (const { path } of [...list.slice(start), ...list.slice(0, start)]) {
      const node = nodeAt(script, path);
      const piece = node ? pieces[node.id] : undefined;
      const slot = Object.entries(piece?.slots ?? {}).find(([, s]) => chipFits(value, s, script.param));
      if (slot) { setScript(setValue(script, path, slot[0], value)); setFocusUid(node!.uid); return; }
    }
    toast(value === "N" ? "No piece here takes N yet" : "No piece here takes that yet", "error");
  };
  const moveKey = (path: Path, dir: -1 | 1) => {
    const node = nodeAt(script, path);
    if (!node || !voc) return;
    const piece = pieces[node.id];
    if (!piece) return;
    const without = remove(script, path);
    const options = spots(piece, without, voc).filter((s) => s.kind !== "hat");
    // where the node sits now, counted in the script without it
    const here = spotKey(path);
    const keys = options.map((s) => spotKey(s.path));
    const at = keys.indexOf(here);
    const pick = at >= 0 ? options[at + dir] : (dir > 0 ? options.find((s) => spotKey(s.path) > here) : [...options].reverse().find((s) => spotKey(s.path) < here));
    if (!pick) return;
    setScript(insert(without, pick.path, node));
    setFocusUid(node.uid);
  };
  const usable = useCallback((piece: Piece) => !!voc && spots(piece, script, voc).length > 0, [script, voc]);

  // ------------------------------------------------------------------------------------------------------ the library
  const refresh = () => listTaught().then(setRows, toastError);
  const load = (row: TaughtRow) => {
    setScript(fromEntry(row.entry));
    setEditing(row.id);
    setActive(0);
    setCard(null);
  };
  const fresh = (kind: Kind = "keyword") => { setScript(emptyScript(kind)); setEditing(null); setCard(null); setCheck(null); };
  const switchKind = (kind: Kind) => { if (script.kind !== kind) { setScript(asKind(script, kind)); if (kind !== "card") setCard(null); } };
  const save = async () => {
    if (!entry) return;
    setBusy("save");
    try {
      const row = editing ? await updateTaught(editing, entry) : await createTaught(entry);
      setEditing(row.id);
      toast(`Taught: ${row.name}. New games know it.`, "info");
      await refresh();
    } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  const tryNow = async () => {
    if (!entry) return;
    setBusy("try");
    try {
      const res = await tryIt(entry, card?.card.id);
      if (res.seat) rememberSeat(res.game.id, res.seat.token);
      navigate(`/game/${res.game.id}`);
    } catch (e) { toastError(e); setBusy(null); }
  };
  const pickCard = async (c: CardData) => {
    try {
      const got = await cardLines(c.id);
      setCard(got);
      setScript((s) => ({ ...s, kind: "card", card: { oracle_id: got.card.oracle_id, line: "", card_name: got.card.name, type_line: got.card.type_line ?? "" } }));
      setEditing(null);
    } catch (e) { toastError(e); }
  };
  const teachLine = (text: string, typeLine: string | null) => {
    if (!card) return;
    const existing = card.lines.find((l) => l.text === text)?.taught_id;
    const row = existing ? rows.find((r) => r.id === existing) : null;
    if (row && row.kind === "card") { load(row); setCard(card); return; }
    setScript({ ...emptyScript("card"), card: { oracle_id: card.card.oracle_id, line: text, card_name: card.card.name, type_line: typeLine ?? card.card.type_line ?? "" } });
    setEditing(null);
  };
  const teachKeyword = (name: string, param: boolean, kind: "keyword" | "action" = "keyword") => {
    const row = rows.find((r) => r.kind === kind && r.name.toLowerCase() === name.toLowerCase());
    if (row) { load(row); return; }
    setScript({ ...emptyScript(kind), name, param });
    setEditing(null);
    setCard(null);
  };
  const onImport = async (file: File) => {
    try {
      const r = await importTaught(file);
      toast(`Imported ${r.imported} new, ${r.replaced} updated.`, "info");
      setRows(r.entries);
    } catch (e) { toastError(e); }
  };

  if (!voc) return <div className="page teach-page"><p className="t-loading">Loading the pieces…</p></div>;

  const ready = !!check?.ok && hasWork(script) && (script.kind === "card" ? !!script.card?.line : !!script.name.trim());
  const problems = check?.problems ?? [];
  const nameProblem = script.kind === "keyword" && hasWork(script) && !script.name.trim() ? "Give the keyword a name."
    : script.kind === "action" && hasWork(script) && !script.name.trim() ? "Give the action its verb (cards say “it dives”: the verb is dive)." : null;
  const verb = script.name.trim().toLowerCase() || "dive";
  const actionEntry = script.kind === "action" && entry?.kind === "action" ? entry : null;
  const lineProblem = script.kind === "card" && hasWork(script) && !script.card?.line ? "Pick the card's line to teach." : null;
  // why ▶ Try it can't run yet, in the verdict's own words
  const tryWhy = !hasWork(script) ? "Try it opens a test table once there's an ability: start with a When piece, or pick a card's line."
    : checking ? "Checking with the engine…" : `Not ready to try: ${nameProblem ?? lineProblem ?? problems[0]?.message ?? "finish the ability first."}`;

  return (
    <div className="page teach-page" data-testid="teach-page">
      <header className="t-top">
        <a className="t-back" href="#/cards" aria-label="Back to Cards"><Icon name="left" size={18} /></a>
        <h1>Teach Fyodor</h1>
        {/* (not ready: dimmed flat, still focusable; a click or the tooltip says what's missing) */}
        <button type="button" className="t-play" onClick={ready ? tryNow : () => toast(tryWhy, "info")} disabled={busy !== null} aria-disabled={!ready || undefined}
          data-testid="teach-try" title={ready ? "Open a test table with this card and a target dummy" : tryWhy}>
          <span className="t-play-tri" aria-hidden /> Try it
        </button>
        <button type="button" className="t-help" onClick={() => setHelp(true)} aria-label="Help">?</button>
        <div className="t-avatars" role="list" aria-label="Taught so far">
          {rows.map((r) => (
            <button key={r.id} type="button" role="listitem" className={`t-avatar ${r.kind} ${editing === r.id ? "on" : ""} ${r.enabled ? "" : "off"}`} onClick={() => load(r)}
              title={`${r.name}${r.enabled ? "" : " (off)"}: ${r.lines.join(" ")}`}>
              <span>{r.kind === "card" ? r.name.split(/[ ,]/)[0]?.slice(0, 2) : r.name.slice(0, 2)}</span>
            </button>
          ))}
          <button type="button" className="t-avatar t-new" onClick={() => fresh()} title="Teach something new" aria-label="Teach something new"><Icon name="plus" size={16} /></button>
        </div>
      </header>

      <div className="t-main">
        <div className="t-left">
          <section className="t-what" aria-label="What you are teaching">
            <div className="seg t-seg" role="group" aria-label="Teach">
              <button type="button" className={script.kind === "keyword" ? "on" : ""} aria-pressed={script.kind === "keyword"} onClick={() => switchKind("keyword")}>A keyword</button>
              <button type="button" className={script.kind === "action" ? "on" : ""} aria-pressed={script.kind === "action"} onClick={() => switchKind("action")} data-testid="teach-kind-action">An action</button>
              <button type="button" className={script.kind === "card" ? "on" : ""} aria-pressed={script.kind === "card"} onClick={() => switchKind("card")}>One card's line</button>
            </div>
            {script.kind === "action" ? (
              <div className="t-kw">
                <label className="t-field">
                  <span>Action (the verb)</span>
                  <input value={script.name} placeholder="dive" maxLength={30} data-testid="teach-name" onChange={(e) => setScript({ ...script, name: e.target.value })} />
                </label>
                <label className="t-check">
                  <input type="checkbox" checked={script.param} data-testid="teach-param" onChange={(e) => setScript({ ...script, param: e.target.checked })} />
                  <span>has a number <b>N</b> (“{verb} 2”)</span>
                </label>
                <label className="t-field t-wide">
                  <span>Reminder text (optional)</span>
                  <input value={script.reminder} maxLength={400} placeholder="What the card says in brackets" onChange={(e) => setScript({ ...script, reminder: e.target.value })} />
                </label>
                <p className="t-phrases">Cards say <b>{actionPhrase({ name: verb, param: script.param }, script.param ? 2 : null)}</b>
                  {!script.param && <>, <b>target creature {verb}s</b></>}; the Do pieces below are what happens to that creature (“it”).</p>
              </div>
            ) : script.kind === "keyword" ? (
              <div className="t-kw">
                <label className="t-field">
                  <span>Keyword</span>
                  <input value={script.name} placeholder="Dive" maxLength={50} data-testid="teach-name" onChange={(e) => setScript({ ...script, name: e.target.value })} />
                </label>
                <label className="t-check">
                  <input type="checkbox" checked={script.param} data-testid="teach-param" onChange={(e) => setScript({ ...script, param: e.target.checked })} />
                  <span>has a number <b>N</b> (“Dive 2”)</span>
                </label>
                <label className="t-field t-wide">
                  <span>Reminder text (optional)</span>
                  <input value={script.reminder} maxLength={400} placeholder="What the card says in brackets" onChange={(e) => setScript({ ...script, reminder: e.target.value })} />
                </label>
              </div>
            ) : (
              <div className="t-cardpick">
                <CardSearchBox placeholder="Find the card…" onPick={(c) => void pickCard(c)} />
                {card && (
                  <div className="t-cardlines">
                    <div className="t-cardname">{card.card.name} <small>{card.card.type_line}</small>
                      <span className={`t-level lv-${card.level_taught.toLowerCase()}`} title="How much of the card Fyodor plays by itself (with what is taught)">{card.level_taught}</span>
                    </div>
                    <ul>
                      {card.lines.map((l, i) => {
                        const chosen = script.card?.line === l.text;
                        return (
                          <li key={i} className={`${l.manual ? "manual" : "auto"} ${l.taught_id ? "taught" : ""} ${chosen ? "on" : ""}`}>
                            <span className="t-dot" aria-hidden />
                            <span className="t-linetext">{l.text}</span>
                            {l.taught_id ? <button type="button" className="btn small" onClick={() => teachLine(l.text, l.type_line)}>Edit what you taught</button>
                              : l.manual ? (
                                <span className="t-lineacts">
                                  {l.keyword && <button type="button" className="btn small" onClick={() => teachKeyword(l.keyword!.name, l.keyword!.param)}>Teach “{l.keyword.name}” as a keyword</button>}
                                  {l.action && <button type="button" className="btn small" onClick={() => teachKeyword(l.action!.name, l.action!.param, "action")}>Teach “{l.action.name}” as an action</button>}
                                  {l.action && <button type="button" className="btn small" onClick={() => teachKeyword(l.action!.name, l.action!.param, "action")}>Teach “{l.action.name}” as an action</button>}
                                  <button type="button" className="btn small primary" onClick={() => teachLine(l.text, l.type_line)}>Teach this line</button>
                                </span>
                              ) : <span className="t-auto">Fyodor plays this</span>}
                          </li>
                        );
                      })}
                    </ul>
                    {script.card?.line && <p className="t-chosen">Teaching: <q>{script.card.line}</q></p>}
                  </div>
                )}
                {!card && script.card?.line && <p className="t-chosen">{script.card.card_name}: <q>{script.card.line}</q></p>}
              </div>
            )}
          </section>

          <Workspace script={script} voc={voc} pieces={pieces} active={active} setActive={setActive} drag={drag} allowed={allowed} chipTargets={chipTargets}
            onStartDrag={start} onSetValue={(p, k, v) => setScript(setValue(script, p, k, v))} onRemove={(p) => setScript(remove(script, p))}
            onMoveKey={moveKey} onRemoveAbility={(i) => { setScript(removeAbility(script, i)); setActive(0); }} onAddAbility={() => { setScript(addAbility(script)); setActive(script.abilities.length); }}
            focusUid={focusUid} me={me} />

          <div className={`t-trash ${drag?.item.kind === "node" ? "show" : ""} ${drag?.target === "trash" ? "hot" : ""}`} data-trash aria-hidden>
            <Icon name="trash" size={22} />
          </div>

          <section className="t-read" aria-live="polite" aria-label="What Fyodor reads">
            <h2>Fyodor reads it as</h2>
            {hasWork(script) ? (
              <>
                {lines.map((l, i) => <p key={i} className="t-sentence" data-testid="teach-sentence">{l}</p>)}
                {script.kind === "keyword" && script.name.trim() && (
                  <p className="t-printed">On a card: <b>{keywordLine(script.name.trim(), script.param, linesN2 ?? lines)}</b></p>
                )}
                {actionEntry && (
                  <p className="t-printed" data-testid="teach-phrase">On a card: <b>When this creature enters, {actionPhrase(actionEntry, script.param ? 2 : null)}.</b> Fyodor reads it
                    as <q>When this creature enters, {actionSentences(actionEntry, voc, { me: "it", n: script.param ? 2 : null })}.</q></p>
                )}
                <div className={`t-verdict ${checking ? "wait" : check?.ok && !nameProblem && !lineProblem ? "ok" : check ? "bad" : ""}`} data-testid="teach-verdict">
                  {checking ? "Checking with the engine…" : nameProblem ?? lineProblem ?? (check?.ok ? "Fyodor understands this and will play it by itself." : problems[0]?.message ?? "")}
                  {!checking && problems.length > 1 && <ul>{problems.slice(1).map((p, i) => <li key={i}>{p.where ? `${p.where}: ` : ""}{p.message}</li>)}</ul>}
                </div>
                {check?.abilities.some((a) => a.definition) && (
                  <details className="t-def">
                    <summary>The engine's own definition (for the curious)</summary>
                    <pre>{JSON.stringify(check.abilities.map((a) => a.definition), null, 1)}</pre>
                  </details>
                )}
              </>
            ) : <p className="t-hint">Snap a <b>When</b> piece on top, then <b>Do</b> pieces under it. Drag from the Commands, or click a command to add it; arrows move a row, Delete removes it.</p>}
            <div className="t-actions">
              <button type="button" className="btn primary" onClick={save} disabled={!ready || busy !== null} data-testid="teach-save">{editing ? "Save changes" : "Teach it"}</button>
              {editing && <button type="button" className="btn" onClick={() => fresh(script.kind)}>Start another</button>}
            </div>
          </section>
        </div>

        <Palette voc={voc} param={script.param} kind={script.kind} usable={usable} onAdd={addPiece} onChip={addChip} onStartDrag={start} />
      </div>

      <section className="t-library" aria-label="Taught so far">
        <header>
          <h2>Taught so far</h2>
          <div className="t-libacts">
            <a className="btn small" href={exportUrl()} download aria-disabled={!rows.length}>Export all</a>
            <button type="button" className="btn small" onClick={() => fileInput.current?.click()}>Import a file…</button>
            <input ref={fileInput} type="file" accept=".json,application/json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void onImport(f); e.target.value = ""; }} />
          </div>
        </header>
        {rows.length === 0 ? <p className="t-hint">Nothing yet. Anything you teach shows here, applies to new games, and is in every backup.</p> : (
          <ul className="t-rows">
            {rows.map((r) => (
              <li key={r.id} className={`${r.enabled ? "" : "off"} ${editing === r.id ? "on" : ""}`}>
                <span className={`t-kind ${r.kind}`}>{KIND_LABEL[r.kind]}</span>
                <span className="t-rowname">{r.name}{r.kind === "card" && r.line ? <small> — {r.line}</small> : null}</span>
                <span className="t-rowlines">{r.lines.join(" ")}</span>
                <span className="t-rowacts">
                  <label className="t-switch" title={r.enabled ? "On: new games use it" : "Off: new games ignore it"}>
                    <input type="checkbox" role="switch" checked={r.enabled} onChange={(e) => enableTaught(r.id, e.target.checked).then(refresh, toastError)} aria-label={`${r.name} on`} />
                    <i aria-hidden />
                  </label>
                  <button type="button" className="btn small" onClick={() => load(r)}>Edit</button>
                  <a className="btn small" href={exportUrl([r.id])} download>Export</a>
                  <button type="button" className="btn small danger" onClick={() => { if (confirm(`Forget ${r.name}? Games in progress keep it.`)) deleteTaught(r.id).then(() => { if (editing === r.id) fresh(); return refresh(); }, toastError); }}>Delete</button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div ref={ghost} className={`t-ghost ${drag ? "show" : ""} cat-${drag ? (drag.item.kind === "chip" ? drag.item.cat : drag.item.piece.cat) : ""}`} aria-hidden>
        {drag && (drag.item.kind === "chip" ? drag.item.label : drag.item.piece.label)}
      </div>

      {help && (
        <Modal title="Teach Fyodor" onClose={() => setHelp(false)}>
          <div className="t-helptext">
            <p>When a new set brings a mechanic Fyodor doesn't know yet, teach it here and every card with that keyword or action plays by itself in new games — this one and the ones the next card update brings.</p>
            <ol>
              <li><b>Name it.</b> A keyword like <i>Plunge</i> (tick <i>has a number</i> if cards say “Plunge 2”); an action like <i>dive</i>, the verb cards use (“it dives”, “target creature dives”); or pick a card and one of the lines Fyodor plays by hand.</li>
              <li><b>Start with a When piece</b> — <i>Enters</i>, <i>Attacks</i>, <i>Pay to use it</i>, <i>Always</i> … An action skips this: its Do pieces are what happens to the creature the card names.</li>
              <li><b>Put Do pieces under it.</b> Tap a white chip to change a number or a choice; drop a <i>Target</i> or a <i>Value</i> chip on one; use <b>N</b> where the keyword's number goes.</li>
              <li><b>Read it back</b> under the workspace: Fyodor checks it with its own rules engine as you build.</li>
              <li><b>▶ Try it</b> opens a test table with the card in hand and a target dummy. <b>Teach it</b> saves it for new games.</li>
            </ol>
            <p>Keyboard: Enter on a command adds it; on a row, ↑ ↓ move it, Delete removes it, Enter edits its first chip. Taught things are data (never code), live in app.sqlite with your decks, go into every backup, and can be exported as a small file for the pod.</p>
          </div>
        </Modal>
      )}
    </div>
  );
}
