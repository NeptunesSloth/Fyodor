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

/** Card-menu entries for a token stack's controller: split it, spread it out, and (sandbox only) stack identical tokens. */
export function tokenStackItems(card: GameCard, view: GameView, me: string, selection: string[] = []): MenuItem[] {
  if (!stackable(card) || card.controller !== me) return [];
  const items: MenuItem[] = [];
  const n = stackSize(card);
  const sandbox = !view.rules; // automation on: the server keeps every token its own object
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
