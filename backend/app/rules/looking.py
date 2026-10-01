"""-- refused look/cast-free (wave 3R5) -- Separating revealed cards into two piles (CR 700.3), and picking
one card of each listed kind ("a creature card and/or a land card", "for each card type").

"Reveal the top five cards of your library. An opponent separates those cards into two piles. Put one
pile into your hand and the other into your graveyard." (Fact or Fiction) and "Reveal the top five cards
of your library and separate them into two piles. An opponent chooses one of those piles. Put that pile
into your hand and the other into your graveyard." (Steam Augury), read against the stored Comprehensive
Rules (2026-09-25):

* 700.3a-d — every card goes into exactly one pile; a pile may be empty; the piles aren't objects and the
  cards don't leave the library while they're grouped (700.3c).
* 701.20a — the cards were revealed: everyone sees them, so the piles are public too.
* 608.2d — "an opponent": a choice the effect offers, made by the spell's controller as it resolves.

Only cards just revealed from the controller's own library are separated (``scripts._piles`` refuses
the rest), so nothing hidden is shown to the separating or choosing opponent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _cards(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    owner = ctx.get("looked_owner") or ctx["controller"]
    library = plan.state.zones.get(zone_key(owner, "library"), [])
    return [c for c in ctx.get("looked") or [] if c in library]


def piles(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Start: which opponent takes part (the controller chooses, 608.2d), then the separation."""
    from app.rules.effects import decide

    pid = ctx["controller"]
    if not _cards(plan, ctx):
        return True
    opponents = [p for p in plan.live() if p != pid]
    if not opponents:
        return True
    if len(opponents) == 1:
        return _separate(plan, ctx, e, opponents[0])
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'Piles'}: choose an opponent to "
           + ("separate the cards into two piles" if e["separator"] == "opponent" else "choose one of the piles"),
           options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": "piles_opponent", "ctx": ctx, "e": e})
    return False


def _separate(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], opponent: str) -> bool:
    from app.rules.effects import decide

    cards = _cards(plan, ctx)
    separator = opponent if e["separator"] == "opponent" else ctx["controller"]
    decide(plan, player=separator, kind="choose_cards",
           prompt=f"{ctx.get('name') or 'Piles'}: separate the revealed cards into two piles — choose the cards of the "
                  "first pile (the others are the second; a pile may be empty)",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards],
           min_choices=0, max_choices=len(cards), resume={"step": "piles_split", "ctx": ctx, "e": e, "opponent": opponent})
    return False


def resume_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}")
    if _separate(plan, r["ctx"], r["e"], chosen[0]):
        effects.continue_effects(plan, r["ctx"])


def resume_split(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import decide

    r = d.resume
    ctx, e = r["ctx"], r["e"]
    cards = _cards(plan, ctx)
    first = [c for c in cards if c in chosen]
    second = [c for c in cards if c not in chosen]
    names = [", ".join(plan.state.cards[c].name or "a card" for c in pile) or "no cards" for pile in (first, second)]
    plan.note(f"{plan.name(d.player)} separates the cards: {names[0]} / {names[1]}")
    chooser = ctx["controller"] if e["chooser"] == "you" else r["opponent"]
    decide(plan, player=chooser, kind="choose_one",
           prompt=f"{ctx.get('name') or 'Piles'}: choose the pile {plan.name(ctx['controller'])} puts into their hand "
                  "(the other goes to their graveyard)",
           options=[DecisionOption(id="1", label=f"Pile 1: {names[0]}"), DecisionOption(id="2", label=f"Pile 2: {names[1]}")],
           resume={"step": "piles_pick", "ctx": ctx, "piles": [first, second]})


def resume_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    ctx = r["ctx"]
    pid = ctx["controller"]
    first, second = r["piles"]
    keep, rest = (first, second) if chosen[0] == "1" else (second, first)
    plan.note(f"{plan.name(d.player)} chooses pile {chosen[0]}")
    library = set(_cards(plan, ctx))
    keep, rest = [c for c in keep if c in library], [c for c in rest if c in library]
    if keep:
        plan.do({"type": "move", "card_ids": keep, "to": {"player": pid, "zone": "hand"}}, actor=pid)
    if rest:
        plan.do({"type": "move", "card_ids": rest, "to": {"player": plan.state.cards[rest[0]].owner, "zone": "graveyard"}}, actor=pid)
    ctx["looked"] = []
    effects.continue_effects(plan, ctx)


# -- one card of each kind ---------------------------------------------------------------------------------
def kinds_of(plan: Plan, pid: str, card_id: str, sels: list[str]) -> list[int]:
    """The listed kinds (by index) a card is: "a creature card and/or a land card" (an artifact creature
    is either an artifact or a creature card for "each card type", never both at once)."""
    from app.rules import characteristics as chars
    from app.rules import selectors

    card = plan.state.cards[card_id]
    ch = chars.of(card, plan.info)
    return [k for k, key in enumerate(sels) if selectors.matches(plan, selectors.from_key(key), card, ch, pid)]


def distinct_kinds(plan: Plan, pid: str, chosen: list[str], sels: list[str]) -> bool:
    """Can each chosen card stand for a different listed kind (one card of each)? A small matching."""
    if len(set(chosen)) != len(chosen) or len(chosen) > len(sels):
        return False
    options = [kinds_of(plan, pid, c, sels) for c in chosen]

    def assign(i: int, used: frozenset[int]) -> bool:
        return i == len(options) or any(k not in used and assign(i + 1, used | {k}) for k in options[i])

    return assign(0, frozenset())
