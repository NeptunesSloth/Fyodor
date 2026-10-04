"""Putting a permanent card from your hand onto the battlefield (wave 5J), researched against CR 2026-09-25.

"{1}{W}, {T}: You may put an Equipment card from your hand onto the battlefield." (Stoneforge Mystic), "{G}, {T}: You
may put a creature card from your hand onto the battlefield." (Elvish Piper, Quicksilver Amulet), "{T}: You may put a
land card from your hand onto the battlefield." (Sakura-Tribe Scout), Sneak Attack, Dragon Arch …

* The card isn't cast (601.1: no cast triggers, no costs) and a land put onto the battlefield this way isn't played
  (305.4: it doesn't use a land play). It enters as any permanent does (entry replacements 614.12, "As ~ enters"
  choices, enters triggers): ``attachments.enter``; an Aura chooses what it enchants without targeting (303.4f), and
  with nothing to enchant it stays in the hand (303.4g). An Equipment enters unattached (301.5b).
* The choice is made from a hidden zone: only the player choosing sees the options (the decision is private,
  app/rules/view.py), and "you may" lets them put nothing (no one learns whether a matching card was there).
* What it put is recorded for a later "That creature gains haste. Sacrifice the creature at the beginning of the next
  end step." (Sneak Attack): the permanent it became (400.7).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_PERMANENT_TYPES = frozenset({"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"})
# (-- triggers (wave 19B) -- "any number of creature cards", "a permanent card with mana value less than or equal to the number of lands you
# control / that damage": the count is read as the card is chosen, 608.2h)
PATTERN = (r"put (?P<q>an?|any number of) (?P<what>[^.]+?) cards?(?: with mana value (?P<op>less than or equal to|less than) "
           r"(?P<v>that damage|the number of [^.]+?))? from your hand onto the battlefield(?P<tapped> tapped(?P<atk> and attacking)?)?")


def parse(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any] | None:
    """The effect, or None (manual) when the card it names could be something that can't enter the battlefield."""
    from app.rules import selectors

    sel = selectors.parse(f"{m['what']} card from your hand")
    if sel is None or sel.zones != ("hand",) or sel.zone_owner != "you" or sel.player is not None or sel.extras:
        return None
    if not sel.types and not sel.subtypes:
        return None  # ("a card": an instant or sorcery can't be put onto the battlefield)
    if sel.types and not set(sel.types) <= _PERMANENT_TYPES:
        return None
    effect: dict[str, Any] = {"do": "put_from_hand", "sel": sel.key(), "label": m["what"]}
    if m["op"]:
        from app.rules import values

        value = {"event_amount": 1} if m["v"] == "that damage" else values.parse_count(m["v"])
        if value is None:
            return None
        effect["mv"] = ["<=" if m["op"].endswith("equal to") else "<", value]
    if m["q"] == "any number of":
        effect["many"] = True
    if m["tapped"]:
        effect["tapped"] = True
    if m["atk"]:  # -- trigger tail (wave 15B) -- 508.4: its controller chooses whom it attacks (looking.attack_with_entered)
        effect["attacking"] = True
    return [effect], None


def put_from_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Its controller chooses up to one matching card in their hand (privately), then it enters."""
    from app.rules import effects, selectors
    from app.rules.plan import decide

    pid = ctx["controller"]
    options = [c for c in selectors.candidates(plan, selectors.from_key(e["sel"]), pid, ctx.get("source_card"))
               if plan.state.cards[c].zone == f"{pid}:hand" and _permanent_card(plan, c) and _mv_ok(plan, ctx, e, c)]
    if not options:
        effects._remember(plan, ctx, e, [])
        return True  # (nothing is announced: the hand is hidden)
    may = bool(e.get("optional")) or bool(e.get("many"))  # ("you may": none is a choice; a trigger's "you may" was asked already, 603.5)
    decide(plan, player=pid, kind="choose_cards",
           prompt=f"{ctx.get('name') or 'It'}: {'you may ' if may else ''}put a {e.get('label') or 'permanent'} card from "
                  "your hand onto the battlefield",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
           min_choices=0 if may else 1, max_choices=len(options) if e.get("many") else 1,
           resume={"step": "put_from_hand", "ctx": ctx, "e": e})
    return False


def _mv_ok(plan: Plan, ctx: Context, e: dict[str, Any], cid: str) -> bool:
    """-- triggers (wave 19B) -- the mana value limit of "with mana value less than or equal to …" (read now, 608.2h)."""
    if not e.get("mv"):
        return True
    from app.rules import characteristics as chars
    from app.rules import effects

    op, value = e["mv"]
    mv, limit = chars.of(plan.state.cards[cid], plan.info).mana_value, effects._amount(plan, ctx, value)
    return mv <= limit if op == "<=" else mv < limit


def _permanent_card(plan: Plan, cid: str) -> bool:
    from app.rules import characteristics as chars

    ch = chars.of(plan.state.cards[cid], plan.info)
    return bool(ch.types & _PERMANENT_TYPES) and not ch.is_instant_or_sorcery


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import attachments, effects, selectors
    from app.rules import characteristics as chars

    ctx, e = d.resume["ctx"], d.resume["e"]
    pid = ctx["controller"]
    sel = selectors.from_key(e["sel"])
    cards = []
    for cid in chosen[: 999 if e.get("many") else 1]:
        card = plan.state.cards.get(cid)
        if card is None or card.zone != f"{pid}:hand" or not _permanent_card(plan, cid) or not _mv_ok(plan, ctx, e, cid) \
                or not selectors.matches(plan, sel, card, chars.of(card, plan.info), pid, ctx.get("source_card")):
            raise ActionError("Choose a matching card from your hand")
        cards.append(cid)
    before = effects._remember(plan, ctx, e, cards)
    entries = [{"card": c, "player": pid, "actor": pid, "tapped": bool(e.get("tapped"))} for c in cards]
    if entries and not attachments.enter(plan, entries, ctx):
        return  # (an Aura chooses what it enchants; the resolution goes on from there)
    effects._moved(plan, ctx, e, before)
    if e.get("attacking"):  # -- trigger tail (wave 15B) -- 508.4 (the choice of whom, if any, goes on from token_attack)
        from app.rules import looking

        if not looking.attack_with_entered(plan, ctx, cards):
            return
    effects.continue_effects(plan, ctx)


# -- other players' choices (wave 12D) -- "Each opponent may put a creature card from their hand onto the battlefield." (Hunted
# Wumpus, Iwamori of the Open Fist), "Each player may put an artifact, creature, enchantment, or land card from their hand onto
# the battlefield." (Show and Tell), "… any number of … cards …" (Tempting Wurm), "That player may put …" (Braids, Conjurer
# Adept). 101.4: each player makes the choice in turn order (the active player first), knowing the earlier choices, and then
# the cards enter the battlefield at the same time (614.12, one event). The choice is from a hidden zone and every player is
# asked, whether or not they hold a matching card, so nobody learns that from the question. Each enters under its chooser's
# control (110.2) and is not cast (601.1).
EACH_PATTERN = (r"(?P<who>each opponent|each other player|each player|that player) may put (?P<q>an?|any number of) "
                r"(?P<what>[^.]+?) cards? (?:from their hand onto the battlefield|onto the battlefield from their hand)")
_EACH_WHO = {"each opponent": "each_opponent", "each other player": "each_opponent", "each player": "each_player",
             "that player": "that_player"}


def parse_each(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any] | None:
    inner = re.fullmatch(PATTERN, f"put a {m['what']} card from your hand onto the battlefield")  # (wave 19B: PATTERN's "a")
    one = parse(inner) if inner is not None else None
    if one is None:
        return None
    return [{"do": "each_put", "who": _EACH_WHO[m["who"]], "sel": one[0][0]["sel"], "label": m["what"],
             "many": m["q"] == "any number of"}], None


def each_put(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    who = [p for p in plan.apnap() if p in effects._players(plan, ctx, e["who"])]
    return _ask_each(plan, ctx, e, who, [])


def _ask_each(plan: Plan, ctx: Context, e: dict[str, Any], who: list[str], picks: list[dict[str, Any]]) -> bool:
    from app.rules import attachments, selectors
    from app.rules.plan import decide

    if not who:
        return not picks or attachments.enter(plan, picks, ctx)  # (an Aura chooses what it enchants: the resolution goes on after)
    pid = who[0]
    options = [c for c in selectors.candidates(plan, selectors.from_key(e["sel"]), pid, ctx.get("source_card"))
               if plan.state.cards[c].zone == f"{pid}:hand" and _permanent_card(plan, c)]
    decide(plan, player=pid, kind="choose_cards",
           prompt=f"{ctx.get('name') or 'It'}: you may put {'any number of ' if e.get('many') else 'a '}{e.get('label') or 'permanent'} "
                  "card from your hand onto the battlefield",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
           min_choices=0, max_choices=len(options) if e.get("many") else min(1, len(options)),
           resume={"step": "each_put", "ctx": ctx, "e": e, "who": who[1:], "picks": picks})
    return False


def resume_each(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    picks = [*r["picks"], *({"card": c, "player": d.player, "actor": d.player, "tapped": False} for c in chosen)]
    if _ask_each(plan, r["ctx"], r["e"], r["who"], picks):
        effects.continue_effects(plan, r["ctx"])


PRIMITIVES = {"put_from_hand": put_from_hand, "each_put": each_put}
RESUME = {"put_from_hand": resume, "each_put": resume_each}
