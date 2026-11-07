/**
 * Targeting where the board is the picker (MTG Arena's grammar on Fyodor's table): while I choose targets, or cards and
 * players for any choose-one / choose-cards decision, no panel covers the table. A slim bar docks over my hand with the
 * source's art and name, what to choose in words, Cancel and (multi-choice) Done, and a tray of the candidates as art
 * thumbnails by seat, each told apart from its namesakes. On the table the candidates lift in a brass ring, the rest
 * dims, targetable players light up on their plaque, and hovering (or Tab-ing to) a candidate draws the arrow from the
 * source to it. Display only: answers go through the same `choose` intent as the panel's buttons did.
 */
import { memo, useCallback, useEffect, useId, useLayoutEffect, useRef } from "react";
import { useCardCache } from "../../state/cardCache";
import { useGame } from "../../state/gameStore";
import { usePrefs } from "../../state/prefs";
import { resolveRenderer } from "../../table3d/renderer";
import { isVisible, type GameView } from "../../types/game";
import { GameCardFace } from "../GameCardFace";
import { choose } from "../rules/intents";
import { canSubmitChoice, doneLabel } from "../rules/RulesHud";
import { pickNumber, useTargeting, type Pick } from "./store";
import { progress, ptOf, step, traySeats, type Candidate, type Targeting } from "./targeting";
import { TargetArrows } from "./TargetArrows";
import { useHoverCard } from "../hoverCard";
import "../targeting.css";

const NONE: Pick[] = [];

/** Choose (one) or toggle (multi) a candidate: the same answer the panel's button gave. */
function answer(t: Targeting, c: Candidate): void {
  if (t.multi) useTargeting.getState().toggle(t.decision.id, { opt: c.option.id, ref: c.ref }, t.max);
  else void choose(t.decision.id, [c.option.id]);
}

export function TargetingBar({ t, view, me }: { t: Targeting; view: GameView; me: string }) {
  const d = t.decision;
  const picked = useTargeting((s) => (s.decision === d.id ? s.picked : NONE));
  const three = resolveRenderer(usePrefs((s) => s.renderer)) === "3d";
  const bar = useRef<HTMLElement>(null);
  const art = useRef<HTMLDivElement>(null);
  const tray = useRef<HTMLDivElement>(null);
  // the source's art shows the card preview while hovered (and lets it go if the bar closes under the pointer)
  const srcHover = useHoverCard()(t.source ?? "");
  const artRef = useCallback((el: HTMLDivElement | null) => {
    art.current = el;
    return t.source ? srcHover.ref(el) : undefined;
  }, [srcHover, t.source]);
  // a tray longer than the bar fades out at the edge it continues past
  useLayoutEffect(() => {
    const el = tray.current;
    if (!el) return;
    const mark = () => {
      const more = el.scrollWidth - el.clientWidth - el.scrollLeft > 4;
      const before = el.scrollLeft > 4;
      el.dataset.more = more && before ? "both" : more ? "end" : before ? "start" : "";
    };
    mark();
    el.addEventListener("scroll", mark, { passive: true });
    window.addEventListener("resize", mark);
    return () => {
      el.removeEventListener("scroll", mark);
      window.removeEventListener("resize", mark);
    };
  }, [d.id, t.candidates.length]);
  const canDone = canSubmitChoice(picked.length, t.min, t.max, t.exactly);
  const done = () => void choose(d.id, picked.map((p) => p.opt));
  const cancel = () => void choose(d.id, ["cancel"]);

  useEffect(() => {
    useTargeting.getState().reset(d.id);
    return () => useTargeting.getState().reset(null);
  }, [d.id]);
  useBoardMarks(t, view, picked);
  useKeys(t, bar, picked, canDone, done, cancel);
  useLookAtHot(t, me, three);

  const srcObj = t.source ? view.cards[t.source] : undefined;
  const from = srcObj && isVisible(srcObj) ? srcObj.ability?.source_id : null; // an ability on the stack: its card
  const src = (from && view.cards[from]) || srcObj;
  const dock = t.candidates.some((c) => c.where === "hand") ? "above-hand" : "hand";
  const groups = traySeats(t, view, me);
  return (
    <>
      <section ref={bar} className="tgt-bar" data-testid="decision-panel" data-kind={d.kind} data-targeting="" data-dock={dock}
        aria-label={`${t.sourceName ? `${t.sourceName}: ` : ""}${t.instruction}`}
        onKeyDown={(e) => { if (e.key === " " || e.key === "Enter") e.stopPropagation(); /* not the table's T/Space keys */ }}>
        <div ref={artRef} className="tgt-source" data-tgt-origin="" aria-hidden
          {...(t.source ? { onPointerEnter: srcHover.onPointerEnter, onPointerLeave: srcHover.onPointerLeave } : {})}>
          {src ? <GameCardFace card={src} size="small" /> : <span className="tgt-source-none" />}
        </div>
        <div className="tgt-main">
          <div className="tgt-head">
            <p className="tgt-words">
              {t.sourceName && <span className="tgt-name">{t.sourceName}</span>}
              <span className="tgt-what" data-testid="targeting-instruction">{t.instruction}</span>
            </p>
            {t.multi && <span className="tgt-count" aria-live="polite" data-testid="targeting-count">{progress(picked.length, t)}</span>}
            <span className="tgt-actions">
              {t.others.map((o) => (
                <button key={o.id} className="tt-btn ghost" data-testid={`option-${o.id}`} onClick={() => void choose(d.id, [o.id])}>{o.label}</button>
              ))}
              {d.cancelable && (
                <button className="tt-btn ghost tgt-cancel" data-testid="option-cancel" onClick={cancel}>
                  Cancel <kbd aria-hidden>Esc</kbd>
                </button>
              )}
              {t.multi && (
                <button className="tt-btn brass tgt-done" data-testid="decision-done" disabled={!canDone} onClick={done}>
                  {doneLabel(picked.length, t.min, t.max)}
                </button>
              )}
            </span>
          </div>
          <div ref={tray} className="tgt-tray" role="group" data-dense={t.candidates.length > 12 ? "" : undefined} aria-label="Choices: Tab or the arrow keys step through them, Enter chooses"
            onWheel={(e) => { if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) e.currentTarget.scrollLeft += e.deltaY; }}>
            {groups.map((g) => {
              const p = view.players.find((x) => x.id === g.seat);
              return (
                <div key={g.seat ?? "-"} className="tgt-seat" style={p ? { ["--player-color" as string]: p.color } : undefined}>
                  {p && !(g.runs.length === 1 && g.runs[0]![0]!.kind === "player") && ( /* (a player alone is their own chip) */
                    <span className="tgt-chip" title={p.name} aria-hidden>{p.name.slice(0, 1).toUpperCase()}</span>
                  )}
                  {g.runs.map((run) => run.length === 1 ? <Thumb key={run[0]!.ref} {...thumbOf(t, run[0]!, pickNumber(picked, run[0]!.ref), 0, me)} /> : (
                    // alike candidates fan out like a pile: each is its own button (and its own card on the table)
                    <span key={run[0]!.ref} className="tgt-fan" style={{ ["--n" as string]: run.length }}>
                      {run.map((c, i) => <Thumb key={c.ref} {...thumbOf(t, c, pickNumber(picked, c.ref), i === run.length - 1 ? run.length : 0, me)} />)}
                    </span>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      </section>
      {!three && <TargetArrows t={t} origin={art} picked={picked} />}
    </>
  );
}

/** What a tray thumbnail needs, all plain values, so a table update that doesn't touch it doesn't redraw it. */
interface ThumbProps {
  decision: string; multi: boolean; max: number; opt: string; refId: string; kind: "card" | "player";
  label: string; note: string; where: string | null; n: number; twins: number; mine: boolean;
}

const thumbOf = (t: Targeting, c: Candidate, n: number, twins: number, me: string): ThumbProps => ({
  decision: t.decision.id, multi: t.multi, max: t.max, opt: c.option.id, refId: c.ref, kind: c.kind,
  label: c.label, note: c.note, where: c.where, n, twins, mine: c.kind === "player" && c.ref === me,
});

/** One candidate in the tray: its art, P/T, counters and tapped state, its name and what tells it apart. */
const Thumb = memo(function Thumb({ decision, multi, max, opt, refId, kind, label, note, where, n, twins, mine }: ThumbProps) {
  const noteId = useId();
  const card = useGame((g) => (kind === "card" ? g.view?.cards[refId] : undefined));
  const player = useGame((g) => (kind === "player" ? g.view?.players.find((p) => p.id === refId) : undefined));
  useCardCache((c) => (card && isVisible(card) && card.card_id ? c.cards[card.card_id] : undefined)); // printed P/T arrives with the card's data
  const pt = useGame((g) => (kind === "card" && g.view ? ptOf(g.view, refId) : ""));
  const plus = card ? (card.counters?.["+1/+1"] ?? 0) - (card.counters?.["-1/-1"] ?? 0) : 0;
  const s = useTargeting.getState;
  // pointed at on the table: lit here too, and brought into view in a long tray
  const live = useGame((g) => g.hover === refId);
  const self = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (live && !self.current?.matches(":hover")) self.current?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [live]);
  // a card candidate shows the card preview while hovered (and lets it go if the tray closes under the pointer)
  const cardHover = useHoverCard()(refId);
  const selfRef = useCallback((el: HTMLButtonElement | null) => {
    self.current = el;
    return kind === "card" ? cardHover.ref(el) : undefined;
  }, [cardHover, kind]);
  const enter = (e: React.PointerEvent<HTMLButtonElement>) => {
    s().setHot(refId);
    if (kind === "card") cardHover.onPointerEnter(e);
  };
  const leave = (e: React.PointerEvent<HTMLButtonElement>) => {
    s().setHot(null);
    if (kind === "card") cardHover.onPointerLeave(e);
  };
  const choose1 = () => {
    if (multi) s().toggle(decision, { opt, ref: refId }, max);
    else void choose(decision, [opt]);
  };
  const shownNote = twins > 1 ? `${twins} alike` : note || (where && where !== "battlefield" ? (where === "stack" ? "on the stack" : `in ${where}`) : "");
  return (
    <button ref={selfRef} className="tgt-thumb" data-kind={kind} data-testid={`option-${opt}`} data-ref={refId}
      data-tapped={card?.tapped ? "" : undefined} data-n={n || undefined}
      data-whole={card && where && where !== "battlefield" && where !== "stack" ? "" : undefined /* a card you're searching for: the whole face, not the art crop */} data-live={live ? "" : undefined}
      aria-label={label} aria-describedby={shownNote ? noteId : undefined} aria-pressed={multi ? n > 0 : undefined}
      title={note ? `${label} · ${note}` : label}
      onClick={choose1}
      onPointerEnter={enter} onPointerLeave={leave}
      onFocus={() => { s().setFocus(refId); if (kind === "card") useGame.getState().setHover(refId); }}
      onBlur={() => { s().setFocus(null); if (useGame.getState().hover === refId) useGame.getState().setHover(null); }}>
      <span className="tgt-art" aria-hidden>
        {card ? <GameCardFace card={card} size="small" />
          : <span className="tgt-player" style={{ ["--player-color" as string]: player?.color }}>{(player?.name ?? label).slice(0, 1).toUpperCase()}</span>}
        {pt && <span className={`tgt-pt ${plus > 0 ? "up" : plus < 0 ? "down" : ""}`}>{pt}</span>}
        {player && <span className="tgt-pt tgt-life" title="Life">{player.life}</span>}
        {card?.tapped && <span className="tgt-tapped" title="Tapped">↷</span>}
        {n > 0 && <b className="tgt-n">{n}</b>}
        {twins > 1 && <span className="tgt-twins">×{twins}</span>}
      </span>
      <span className="tgt-label" aria-hidden>{mine ? `${label} (you)` : label}</span>
      {shownNote && <span className="tgt-note" id={noteId}>{shownNote}</span>}
    </button>
  );
});

/**
 * The table while choosing: the rest dims (body.targeting), targetable players' plaques and the piles that hold a
 * candidate light up, and the source stays bright. Plaques and piles are other components' elements: they get a data
 * attribute here (React leaves attributes it doesn't own alone) and lose it when the choice ends.
 */
function useBoardMarks(t: Targeting, view: GameView, picked: Pick[]): void {
  useEffect(() => {
    document.body.classList.add("targeting");
    return () => document.body.classList.remove("targeting");
  }, []);
  // what to mark, as text: a table update that changes none of it touches no element
  const marks: string[] = [];
  for (const c of t.candidates) {
    const chosen = pickNumber(picked, c.ref) > 0 ? "chosen" : "cand";
    if (c.kind === "player") marks.push(`seat|${c.ref}|${chosen}`);
    else if (c.where && c.where !== "battlefield" && c.where !== "hand" && view.cards[c.ref]) marks.push(`pile|${view.cards[c.ref]!.zone}|${chosen}`);
  }
  if (t.source) marks.push(`source|${t.source}|`);
  const key = [...new Set(marks)].join("\n");
  useEffect(() => {
    const wanted = (key ? key.split("\n") : []).map((line) => {
      const [what, id, value] = line.split("|") as [string, string, string];
      const e = CSS.escape(id);
      const sel = what === "seat" ? `.t3d-seat[data-player-id="${e}"]` : what === "pile" ? `[data-drop="${e}"]`
        : `.battlefield [data-card-id="${e}"], .command-zone [data-card-id="${e}"]`;
      return { sel, attr: what === "source" ? "data-tgt-source" : "data-tgt", value };
    });
    const marked = new Set<[Element, string]>();
    const apply = () => {
      for (const w of wanted) document.querySelectorAll(w.sel).forEach((el) => {
        if (el.getAttribute(w.attr) === w.value) return;
        el.setAttribute(w.attr, w.value);
        marked.add([el, w.attr]);
      });
    };
    apply();
    // plaques and piles that mount later (the 3D table's plaques arrive with it) are marked as they appear
    let raf = 0;
    const watch = new MutationObserver(() => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; apply(); }); });
    watch.observe(document.body, { childList: true, subtree: true });
    return () => {
      watch.disconnect();
      cancelAnimationFrame(raf);
      marked.forEach(([el, attr]) => el.removeAttribute(attr));
    };
  }, [key]);
  // a click on a targetable player's plaque chooses them (before the plaque's own life and panel buttons see it)
  const latest = useRef(t);
  latest.current = t;
  useEffect(() => {
    const seatOf = (e: Event) => {
      const el = (e.target as Element | null)?.closest?.(".t3d-seat[data-player-id]");
      const pid = el?.getAttribute("data-player-id");
      return pid ? latest.current.candidates.find((c) => c.kind === "player" && c.ref === pid) : undefined;
    };
    const onClick = (e: MouseEvent) => {
      const c = seatOf(e);
      if (!c || e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      answer(latest.current, c);
    };
    const onOver = (e: PointerEvent) => {
      const c = seatOf(e);
      const s = useTargeting.getState();
      if (c) s.setHot(c.ref);
      else if (s.hot && latest.current.candidates.some((x) => x.kind === "player" && x.ref === s.hot) && !(e.target as Element | null)?.closest?.(".tgt-bar")) s.setHot(null);
    };
    window.addEventListener("click", onClick, true);
    window.addEventListener("pointerover", onOver, true);
    return () => {
      window.removeEventListener("click", onClick, true);
      window.removeEventListener("pointerover", onOver, true);
    };
  }, []);
}

/**
 * Keys while choosing: Tab / Shift+Tab step through the candidates and then the bar's buttons (wrapping), the arrow keys
 * through the candidates only, Enter or Space chooses the focused one (a button's own keys), Esc cancels when the choice
 * can be taken back (a multi-choice clears its picks first). Typing in a field is left alone.
 */
function useKeys(t: Targeting, bar: React.RefObject<HTMLElement | null>, picked: Pick[], canDone: boolean, done: () => void, cancel: () => void): void {
  const latest = useRef({ t, picked, canDone, done, cancel });
  latest.current = { t, picked, canDone, done, cancel };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      // typing, a dialog or an open menu keeps its own keys (Esc closes the menu, not the choice)
      if (target?.closest?.("input, textarea, select, [contenteditable]") || document.querySelector(".modal-backdrop, .ctx-menu")) return;
      const root = bar.current;
      if (!root) return;
      const { t, picked, canDone, done, cancel } = latest.current;
      const thumbs = [...root.querySelectorAll<HTMLElement>(".tgt-thumb")];
      const actions = [...root.querySelectorAll<HTMLElement>(".tgt-actions button:not(:disabled)")];
      const active = document.activeElement as HTMLElement | null;
      const inside = !!active && root.contains(active);
      if (e.key === "Tab" && !e.altKey && !e.ctrlKey && !e.metaKey) {
        const next = step([...thumbs, ...actions], inside ? active : null, e.shiftKey ? -1 : 1);
        if (!next) return;
        e.preventDefault();
        next.focus();
        return;
      }
      if (/^Arrow(Left|Right|Up|Down)$/.test(e.key) && (inside || !active || active === document.body)) {
        const next = step(thumbs, inside && thumbs.includes(active!) ? active : null, e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1);
        if (!next) return;
        e.preventDefault();
        e.stopPropagation();
        next.focus();
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        if (t.multi && picked.length) useTargeting.getState().reset(t.decision.id);
        else if (t.decision.cancelable) cancel();
        else active?.blur?.();
        return;
      }
      if (e.key === "Enter" && !inside && t.multi && canDone && !active?.closest?.("button, a, [role=button]")) {
        e.preventDefault();
        done();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [bar]);
}

/**
 * An opponent's card too small to make out (or off screen) on the 2D table: hovering or focusing its thumbnail for a
 * moment Looks at that board (as keys 2–6 do); the view I had comes back when the choice ends.
 */
function useLookAtHot(t: Targeting, me: string, three: boolean): void {
  const hot = useTargeting((s) => s.hot ?? s.focus);
  const back = useRef<{ prev: string | null; set: string } | null>(null);
  const latest = useRef(t);
  latest.current = t;
  useEffect(() => {
    if (three || !hot) return;
    const c = latest.current.candidates.find((x) => x.ref === hot);
    if (!c || c.kind !== "card" || c.where !== "battlefield" || !c.seat || c.seat === me) return;
    const seat = c.seat;
    const timer = window.setTimeout(() => {
      const r = document.querySelector(`.battlefield [data-card-id="${CSS.escape(c.ref)}"]`)?.getBoundingClientRect();
      const tooSmall = !r || r.width < 44 || r.bottom < 0 || r.top > window.innerHeight || r.right < 0 || r.left > window.innerWidth;
      const s = useGame.getState();
      if (!tooSmall || s.focus === seat) return;
      back.current = { prev: back.current?.prev ?? s.focus, set: seat };
      s.setLayout({ focus: seat });
    }, 600);
    return () => window.clearTimeout(timer);
  }, [hot, me, three]);
  useEffect(() => () => {
    const b = back.current;
    if (b && useGame.getState().focus === b.set) useGame.getState().setLayout({ focus: b.prev });
  }, []);
}
