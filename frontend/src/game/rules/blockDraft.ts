import { create } from "zustand";
import { perspective, useGame } from "../../state/gameStore";
import type { DecisionOptionView, DecisionView, GameView } from "../../types/game";
import { toast } from "../../components/Toasts";
import { combatStats, numberedNames } from "./blockerLabels";

/*
 * -- playtest (nov 18) -- the blocks being put together, before they are declared: one pending plan ("b:<blocker>" → ["a:<attacker>", …])
 * shared by the declare-blockers prompt (DeclareBlockers.tsx) and a creature dragged onto an attacker on the 2D or 3D table. The first
 * attacker is the one the blocker stands in front of; a creature that "can block an additional creature" gets more by a Shift-drop (or the
 * prompt's "also blocks" list). The decision carries no per-pair legality, only each creature's power/toughness and combat keywords: the
 * one hint read from them is flying (509.1b, 702.9b); everything else is the server's to judge when the prompt's main button declares.
 */

export interface BlockDraft {
  /** The declare-blockers decision this plan answers (another decision: the plan is stale and ignored). */
  decision: string | null;
  plan: Record<string, string[]>;
  /** While a creature is dragged during the decision: what letting go does, and where the pointer is. */
  hint: { x: number; y: number; text: string; kind: "block" | "home" | "refuse" } | null;
}

export const useBlockDraft = create<BlockDraft>(() => ({ decision: null, plan: {}, hint: null }));

// Shift held: a drop adds this attacker to what the creature already blocks (the caption says so while dragging)
let shiftHeld = false;
if (typeof window !== "undefined") {
  const track = (e: KeyboardEvent | PointerEvent) => { shiftHeld = e.shiftKey; };
  window.addEventListener("keydown", track, true);
  window.addEventListener("keyup", track, true);
  window.addEventListener("pointermove", track, { capture: true, passive: true });
  window.addEventListener("blur", () => { shiftHeld = false; });
}
export const shiftDown = (): boolean => shiftHeld;

/** The declare-blockers decision the local seat is making now, if any. */
export function myBlockDecision(view: GameView | null | undefined, actingAs: string | null = useGame.getState().actingAs): DecisionView | null {
  const d = view?.rules?.decision;
  if (!view || !d || d.kind !== "declare_blockers" || !d.options) return null;
  return d.player === perspective(view, actingAs) ? d : null;
}

/** Start (or keep) the draft for this decision: a new decision starts with no blocks. */
export function openBlockDraft(d: DecisionView): BlockDraft {
  const s = useBlockDraft.getState();
  if (s.decision === d.id) return s;
  const next = { decision: d.id, plan: {}, hint: null };
  useBlockDraft.setState(next);
  return next;
}

/** The plan the table draws: the draft of the decision I'm making now, else nothing. */
export function liveBlocks(view: GameView | null | undefined, draft: BlockDraft = useBlockDraft.getState()): Record<string, string[]> {
  const d = myBlockDecision(view);
  return d && draft.decision === d.id ? draft.plan : EMPTY;
}
const EMPTY: Record<string, string[]> = {};

export const blockerOptions = (d: DecisionView): DecisionOptionView[] => (d.options ?? []).filter((o) => o.id.startsWith("b:"));
export const attackerOptions = (d: DecisionView): DecisionOptionView[] => (d.options ?? []).filter((o) => o.id.startsWith("a:"));

/** This blocker ("b:…") blocks this attacker ("a:…"): alone (`add` false: instead of what it blocked) or as well (`add`). "" : none. */
export function withBlock(plan: Record<string, string[]>, blocker: string, attacker: string, add = false): Record<string, string[]> {
  const next = { ...plan };
  if (!attacker) delete next[blocker];
  else if (add) next[blocker] = [...(next[blocker] ?? []).filter((a) => a !== attacker), attacker];
  else next[blocker] = [attacker];
  return next;
}

/** This blocker stops blocking one attacker (the others stay; the next one becomes where it stands). */
export function withoutBlock(plan: Record<string, string[]>, blocker: string, attacker: string): Record<string, string[]> {
  const rest = (plan[blocker] ?? []).filter((a) => a !== attacker);
  const next = { ...plan };
  if (rest.length) next[blocker] = rest;
  else delete next[blocker];
  return next;
}

export function setBlocks(d: DecisionView, plan: Record<string, string[]>): void {
  openBlockDraft(d);
  useBlockDraft.setState({ plan });
}

/** The declaration the server gets: one line per blocker and attacker it blocks. */
export function blockDeclarations(plan: Record<string, string[]>): { blocker_id: string; attacker_id: string }[] {
  return Object.entries(plan).flatMap(([b, list]) => list.map((a) => ({ blocker_id: b.slice(2), attacker_id: a.slice(2) })));
}

/**
 * The client's one sure hint (no per-pair legality is sent): an attacker with flying, a blocker with neither flying nor reach (509.1b,
 * 702.9b). Null: maybe legal (the server decides). Unknown stats (an older table): null.
 */
export function blockRefusal(d: DecisionView, blocker: string, attacker: string): string | null {
  const stats = combatStats(d);
  const a = stats[attacker.slice(2)];
  const b = stats[blocker.slice(2)];
  if (!a || !b) return null;
  if (a.keywords.includes("flying") && !b.keywords.includes("flying") && !b.keywords.includes("reach")) return "flying";
  return null;
}

/** A note on a legal-looking plan: an attacker with menace blocked by just one creature (702.111b), by attacker option id. */
export function menaceShort(d: DecisionView, plan: Record<string, string[]>): string[] {
  const stats = combatStats(d);
  const count = new Map<string, number>();
  for (const list of Object.values(plan)) for (const a of list) count.set(a, (count.get(a) ?? 0) + 1);
  return [...count].filter(([a, n]) => n === 1 && stats[a.slice(2)]?.keywords.includes("menace")).map(([a]) => a);
}

/** "2 blocking · Serra Angel blocked by 2"; empty with no blocks. */
export function blockSummary(d: DecisionView, plan: Record<string, string[]>): string {
  const blockers = Object.keys(plan).length;
  if (!blockers) return "";
  const names = blockNames(d);
  const per = new Map<string, number>();
  for (const list of Object.values(plan)) for (const a of list) per.set(a, (per.get(a) ?? 0) + 1);
  const order = (d.options ?? []).map((o) => o.id);
  const parts = [...per].sort((x, y) => order.indexOf(x[0]) - order.indexOf(y[0])).map(([a, n]) => `${names[a] ?? "?"}${n > 1 ? ` ×${n}` : ""}`);
  return `${blockers} blocking · ${parts.join(", ")}`;
}

/** The names the prompt lists creatures by: the face that is up, two of one name numbered (each side apart). */
export const blockNames = (d: DecisionView): Record<string, string> => numberedNames(d.options ?? []);

// ------------------------------------------------------------------ the table: drag a creature onto an attacker to block it

/** What a drop of these cards means while I declare blockers: an attacker's card id, "home" (my own battlefield), "board" (the attacking
 * player's battlefield, not on an attacker: nothing happens), or null (anywhere else: the drag does what it always does). */
export type BlockSpot = string | "home" | "board" | null;

/** The dragged cards that are offered as blockers ("b:…"). */
function draggedBlockers(d: DecisionView, ids: string[]): string[] {
  return ids.map((id) => `b:${id}`).filter((b) => d.options!.some((o) => o.id === b));
}

/** The caption a drag shows over this spot (null: the drag isn't about blocking). */
export function blockHint(ids: string[], spot: BlockSpot, add: boolean = shiftHeld): Omit<NonNullable<BlockDraft["hint"]>, "x" | "y"> | null {
  const view = useGame.getState().view;
  const d = myBlockDecision(view);
  if (!d) return null;
  const mine = draggedBlockers(d, ids);
  if (!mine.length) {
    // one of my creatures that isn't offered (tapped, say) over an attacker: say so rather than let it move onto their board
    const own = ids.some((id) => view?.cards[id]?.zone === `${d.player}:battlefield`);
    if (own && spot && spot !== "home" && spot !== "board") {
      return { text: ids.some((id) => view?.cards[id]?.tapped) ? "Can't block: tapped" : "Can't block now", kind: "refuse" };
    }
    return null;
  }
  const plan = useBlockDraft.getState().decision === d.id ? useBlockDraft.getState().plan : {};
  if (!spot) return { text: "Drag onto an attacker to block", kind: "home" };
  if (spot === "board") return { text: "Drop onto an attacker to block it", kind: "home" };
  if (spot === "home") {
    return mine.some((b) => plan[b]?.length) ? { text: "Back in your row: doesn't block", kind: "home" } : { text: "Drag onto an attacker to block", kind: "home" };
  }
  const a = `a:${spot}`;
  const names = blockNames(d);
  const label = names[a];
  if (!label) return null;
  const able = mine.filter((b) => !blockRefusal(d, b, a));
  if (!able.length) return { text: `Can't block ${label}: ${blockRefusal(d, mine[0]!, a)}`, kind: "refuse" };
  const also = add && able.some((b) => plan[b]?.length && !plan[b]!.includes(a));
  return { text: `${also ? "Also block" : "Block"} ${label}${mine.length > 1 ? ` with ${able.length}` : ""}`, kind: "block" };
}

/**
 * Letting go of dragged cards during my declare-blockers decision. An attacker: each dragged creature that may block it does (instead of
 * what it blocked; with Shift, as well); the others (flying) are named in a toast. "home": they stop blocking. "board": nothing (the
 * creature stays mine). True when the drop was about blocking (nothing moves); false: the drag does what it always does.
 */
export function blockDrop(ids: string[], spot: BlockSpot, add: boolean = shiftHeld): boolean {
  const view = useGame.getState().view;
  const d = myBlockDecision(view);
  useBlockDraft.setState({ hint: null });
  if (!d || !spot) return false;
  const mine = draggedBlockers(d, ids);
  if (!mine.length) {
    const own = ids.some((id) => view?.cards[id]?.zone === `${d.player}:battlefield`);
    if (own && spot !== "home" && spot !== "board") {
      toast("That creature can't block now", "info");
      return true; // (dropped on an attacker: it doesn't move onto the attacking player's board)
    }
    return false;
  }
  let plan = { ...openBlockDraft(d).plan };
  if (spot === "home") {
    const had = mine.filter((b) => plan[b]?.length);
    if (!had.length) return false;
    for (const b of had) delete plan[b];
    useBlockDraft.setState({ plan });
    return true;
  }
  if (spot === "board") return true;
  const a = `a:${spot}`;
  if (!d.options!.some((o) => o.id === a)) return false;
  const names = blockNames(d);
  const refused: string[] = [];
  for (const b of mine) {
    const why = blockRefusal(d, b, a);
    if (why) refused.push(`${names[b] ?? "It"} (${why})`);
    else plan = withBlock(plan, b, a, add);
  }
  useBlockDraft.setState({ plan });
  if (refused.length) toast(`${refused.join(", ")} can't block ${names[a] ?? "that"}`, "info");
  return true;
}

/** 2D: the attacker under the pointer; my own battlefield: "home"; the attacking player's battlefield: "board". */
export function blockSpot2D(view: GameView, zone: string | null, clientX: number, clientY: number, dragged: string[] = []): BlockSpot {
  const d = myBlockDecision(view);
  if (!d) return null;
  const attackers = new Set(attackerOptions(d).map((o) => o.id.slice(2)));
  const stack = typeof document !== "undefined" && document.elementsFromPoint ? document.elementsFromPoint(clientX, clientY) : [];
  for (const el of stack) {
    if (!(el instanceof HTMLElement)) continue;
    const card = el.closest<HTMLElement>("[data-card-id]")?.dataset.cardId;
    if (card && !dragged.includes(card) && attackers.has(card)) return card;
  }
  return spotForZone(view, d, zone);
}

/** The spot for a drop on a zone that isn't an attacker: my battlefield "home", an attacking player's "board". */
export function spotForZone(view: GameView, d: DecisionView, zone: string | null): BlockSpot {
  if (!zone) return null;
  if (zone === `${d.player}:battlefield`) return "home";
  const owner = zone.split(":")[0];
  const attacking = new Set(attackerOptions(d).map((o) => view.cards[o.id.slice(2)]?.controller));
  return zone.endsWith(":battlefield") && owner && attacking.has(owner) ? "board" : null;
}
