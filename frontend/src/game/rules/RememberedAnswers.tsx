import { openMenu, type MenuItem } from "../../components/ContextMenu";
import { isVisible, type GameView } from "../../types/game";
import { setPrefs } from "./intents";

type Yield = { kind: string; key: string; answer?: string };

/** A remembered answer in words: "Soul Warden: Yes (this game)", "Commander to the command zone: always". */
export function rememberedLabel(y: Yield, view?: GameView): string {
  const src = y.key.startsWith("may:") ? y.key.slice(4).replace(/:\d+$/, "") : "";
  const card = src ? view?.cards[src] : undefined; // (the key names the card itself: its name, if this viewer can see it)
  const what = src ? (card && isVisible(card) && card.name ? card.name : "A card's “you may”")
    : y.key.startsWith("commander_zone:") ? "Commander to the command zone" : y.key.replace(/^[a-z_]+:/, "");
  const answer = y.answer === "yes" ? "Yes" : y.answer === "no" ? "No" : "Always";
  return `${what}: ${answer} (${y.kind === "always_yield" ? "this game" : "this turn"})`;
}

/**
 * -- "Always do this" -- the answers this table remembers for you (the "Always for this card this game" box on a repeating "you may"),
 * from the turn dial: each one shown, a click forgets it (the question is asked again), and "Forget all". Only your own (the view's prefs).
 */
export function RememberedAnswers({ yields, view }: { yields: readonly Yield[]; view: GameView }) {
  if (!yields.length) return null;
  const items: MenuItem[] = [
    ...yields.map((y) => ({ label: rememberedLabel(y, view), hint: "Click to forget: it asks again", onClick: () => void setPrefs({ cancel_yield: y.key }) })),
    "separator",
    { label: "Forget all", danger: true, onClick: () => void setPrefs({ cancel_all_yields: true }) },
  ];
  return (
    <div className="td-remembered-row"><button type="button" className="td-remembered" data-testid="remembered-answers" title="Answers remembered for you: view or forget them"
      onClick={(e) => openMenu(e, items, "Remembered answers")}>
      Remembered answers · {yields.length}
    </button></div>
  );
}
