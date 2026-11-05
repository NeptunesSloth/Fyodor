/**
 * Token stacks ("Goblin ×10"): one card on the table standing for N identical tokens, the server's `quantity`. Creating more tokens
 * than the "Collapse identical tokens above" setting makes one; the card shows ×N (game/piles.ts countMark) and its controller splits
 * it from the card menu. With rules automation on, the server keeps tokens as separate objects, except that one instruction making more
 * than 100 identical tokens makes one engine stack the rules treat as that many (docs/TOKEN_STACKS.md); there it never merges tokens,
 * splitting off is exact, and a stack bigger than ENGINE_SPREAD_MAX can't be spread into one card per token.
 */
import type { MenuItem } from "../components/ContextMenu";
import { askNumber } from "../components/Prompt";
import { isVisible, type GameCard, type GameView, type VisibleCard } from "../types/game";
import { send } from "./actions";

/** How many tokens this card stands for (1 for anything that isn't a stack). */
export const stackSize = (card: GameCard | undefined): number => Math.max(1, card?.quantity ?? 1);

/** With automation on, the server spreads at most this many tokens into separate cards (app/rules/token_stacks.py INDIVIDUAL_LIMIT). */
export const ENGINE_SPREAD_MAX = 256;

/** The server merges at most this many objects at once (actions.MergeTokens). */
const MERGE_MAX = 250;

/** What the server compares before merging (handlers/objects.py _token_signature): the same token, controller, zone, tapped and
 * face-down state, counters and copy. */
function signature(c: VisibleCard): string {
  const counters = Object.entries(c.counters ?? {}).sort(([a], [b]) => a.localeCompare(b));
  return JSON.stringify([c.card_id, c.token ?? null, c.controller, c.zone, !!c.tapped, !!c.face_down, counters, c.copy_of?.source_name ?? null]);
}

const stackable = (c: GameCard | undefined): c is VisibleCard =>
  !!c && isVisible(c) && c.is_token && !c.protected && c.zone.endsWith(":battlefield");

/**
 * The tokens "Stack identical tokens" merges, this one first (it stays, the others join it): the identical tokens among `among`
 * (a selection of two or more), or else among every token on its battlefield. Empty when there is nothing to stack.
 */
export function identicalTokens(card: GameCard, view: GameView, among: string[] = []): string[] {
  if (!stackable(card)) return [];
  const key = signature(card);
  const pool = among.length > 1 ? among : ((view.zones[card.zone] as string[] | undefined) ?? []);
  const others = pool.filter((id) => {
    const c = view.cards[id];
    return id !== card.id && stackable(c) && signature(c) === key;
  });
  return others.length ? [card.id, ...others].slice(0, MERGE_MAX) : [];
}

/**
 * How many tokens to split off a ×n stack so that the card itself stands for exactly k of them (0: it already does). The server's
 * split_stack moves `count` tokens to a NEW card beside it and the card keeps the rest, so acting on "k of the stack" splits n − k off
 * and then acts on the card: its id is known before the split, and it stays where it is.
 */
export function splitForPart(n: number, k: number): number {
  return k >= n ? 0 : n - Math.max(1, Math.floor(k));
}

/** Make `card` stand for exactly k of its tokens (split the rest off), then act on it. Two table actions, two undo steps. */
export async function withPart(card: GameCard, k: number, act: (id: string) => Promise<boolean> | void): Promise<boolean> {
  const off = splitForPart(stackSize(card), k);
  if (off && !(await send({ type: "split_stack", card_id: card.id, count: off }))) return false;
  await act(card.id);
  return true;
}

/** Ask how many of a ×n stack (1..n), then act on exactly that many. */
async function askPart(card: VisibleCard, verb: string, act: (id: string) => Promise<boolean> | void): Promise<void> {
  const n = stackSize(card);
  const k = await askNumber(`${verb} how many of the ${n.toLocaleString("en-US")} ${card.name} tokens?`, n, { min: 1, max: n });
  if (k && k >= 1) await withPart(card, Math.min(k, n), act);
}

/**
 * "Attack with some of the ×N" in the card menu's Attack entries: how many attack, then the table's attack (the sandbox, and the manual
 * attack arrows with automation on; the rules engine's own declaration takes a count per attacker: RulesHud DeclareAttackers).
 */
export function attackSomeItem(card: GameCard, me: string, targets: { label: string; target: { kind: "player" | "card"; id: string } }[]): Exclude<MenuItem, "separator"> | null {
  const n = stackSize(card);
  if (!stackable(card) || card.controller !== me || n < 2 || !targets.length) return null;
  return {
    label: `Attack with some of the ×${n.toLocaleString("en-US")}`,
    submenu: targets.map((t) => ({
      label: `${t.label}…`,
      onClick: () => void askPart(card, "Attack with", (id) => send({ type: "attack", card_ids: [id], target: t.target })),
    })),
  };
}

/** Card-menu entries for a token stack's controller: split it, spread it out, and (sandbox only) stack identical tokens. */
export function tokenStackItems(card: GameCard, view: GameView, me: string, selection: string[] = []): MenuItem[] {
  if (!stackable(card) || card.controller !== me) return [];
  const items: MenuItem[] = [];
  const n = stackSize(card);
  const sandbox = !view.rules; // automation on: the server keeps every token its own object
  const manual = sandbox || !!view.rules?.paused; // the players run the table by hand: a sacrifice is a move to the graveyard
  if (n > 1 && selection.length <= 1) {
    const split = (count: number) => void send({ type: "split_stack", card_id: card.id, count });
    items.push({
      label: `Token stack ×${n.toLocaleString("en-US")}`,
      submenu: [
        { label: "Split one off", onClick: () => split(1) },
        ...(n > 2
          ? [{
              label: "Split off…",
              onClick: async () => {
                const k = await askNumber(`Split how many ${card.name} tokens off the stack?`, Math.floor(n / 2), { min: 1, max: n - 1 });
                if (k && k < n) split(k);
              },
            }]
          : []),
        ...(sandbox || n <= ENGINE_SPREAD_MAX
          ? [{ label: `Split into ${n} tokens`, hint: "one card each", onClick: () => void send({ type: "expand_stack", card_id: card.id }) }]
          : []),
        "separator" as const,
        // part of the stack: split the rest off first (with automation on that is the engine-exact split the rules make themselves)
        {
          label: card.tapped ? "Untap some…" : "Tap some…",
          onClick: () => void askPart(card, card.tapped ? "Untap" : "Tap", (id) => send({ type: "tap", card_ids: [id], tapped: !card.tapped })),
        },
        ...(manual
          ? [{
              label: "Sacrifice some…",
              hint: "to the graveyard",
              onClick: () => void askPart(card, "Sacrifice", (id) => send({ type: "move", card_ids: [id], to: { zone: "graveyard", player: card.owner } })),
            }]
          : []),
        ...(sandbox
          ? [
              "separator" as const,
              { label: "Add one", onClick: () => void send({ type: "stack_adjust", card_id: card.id, delta: 1 }) },
              { label: "Remove one", onClick: () => void send({ type: "stack_adjust", card_id: card.id, delta: -1 }) },
            ]
          : []),
      ],
    });
  }
  if (sandbox) {
    const same = identicalTokens(card, view, selection);
    if (same.length > 1) {
      const total = same.reduce((sum, id) => sum + stackSize(view.cards[id]), 0);
      items.push({
        label: `Stack identical tokens (×${total})`,
        hint: `${same.length} cards → 1`,
        onClick: () => void send({ type: "merge_tokens", card_ids: same }),
      });
    }
  }
  return items;
}
