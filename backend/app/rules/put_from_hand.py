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
from app.rules import context, values
from app.rules.token_grammar import AT, at_spec

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_PERMANENT_TYPES = frozenset({"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"})
# (-- triggers (wave 19B) -- "any number of creature cards", "a permanent card with mana value less than or equal to the number of lands you
# control / that damage": the count is read as the card is chosen, 608.2h)
_UPTO = r"\d+|" + "|".join(word for word in values.NUMBERS if word not in ("a", "an"))
PATTERN = (rf"put (?P<cnt>an?|any number of|up to (?P<upto>{_UPTO})) (?P<what>[^.]+?) cards?(?P<q> with total power and toughness \d+ or (?:less|greater)| of the chosen type)?"  # (wave 53B: "a creature card of the chosen type", Belbe's Portal)
           # -- put from hand (wave 30P) -- "with mana value 3 or less" / "X or less, where X is the number of attacking creatures you control"
           # (Kinscaer Sentry), "less than that creature's mana value" (Arni Metalbrow), "less than or equal to that creature's power" (Minn, Wily Illusionist; wave 44D), "with lesser power" (Shadowfax): the limit is read as the card is chosen
           r"(?: with (?:mana value (?:(?P<op>less than or equal to|less than|equal to) (?P<v>that damage|the number of [^.]+?|that creature's (?:mana value|power))"
           r"|(?P<n>\d+|X) or less)|(?P<lp>lesser power)|(?P<elv>equal or lesser mana value)))? from your hand "
           rf"onto the battlefield(?P<tapped> tapped(?P<atk> and attacking{AT})?)?(?:, where X is (?P<xdef>[^.]+))?")


def _selector(what: str, q: str) -> Any:
    from app.rules import selectors

    sel = selectors.parse(f"{what} card{q} from your hand")
    if sel is None or sel.zones != ("hand",) or sel.zone_owner != "you" or sel.player is not None or sel.either \
            or any(x not in ("historic", "all_types", "chosen_type") and not x.startswith("pts:") for x in sel.extras):  # (wave 53B: chosen_type, chosen.chosen_value_ok judges the source of the choice)  # (-- put from hand (wave 19E) -- historic: 700.6; "artifact creature")
        return None
    if not sel.types and not sel.subtypes:
        return None  # ("a card": an instant or sorcery can't be put onto the battlefield)
    return None if sel.types and not set(sel.types) <= _PERMANENT_TYPES else sel


def parse(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any] | None:
    """The effect, or None (manual) when the card it names could be something that can't enter the battlefield."""
    # -- put from hand (wave 19E) -- "a red creature card or an artifact creature card" (Purphoros): either kind
    sels = [_selector(w, m["q"] or "") for w in re.split(r" card or (?:an? )?", m["what"])]
    if None in sels:
        return None
    effect: dict[str, Any] = {"do": "put_from_hand", "sel": sels[0].key(), "label": m["what"]}
    if len(sels) > 1:
        effect["alt"] = [x.key() for x in sels[1:]]
    if m["op"]:
        from app.rules import language

        value = {"event_amount": 1} if m["v"] == "that damage" else values.parse_count(m["v"]) or language.x_definition(m["v"])
        if value is None:
            return None
        effect["mv"] = ["==" if m["op"] == "equal to" else "<=" if m["op"].endswith("equal to") else "<", value]
    if m["n"]:  # (a number, or X: "where X is …", defined once and read as the card is chosen)
        from app.rules import language

        value = int(m["n"]) if m["n"].isdigit() else language.x_definition(m["xdef"] or "") if m["xdef"] else {"x": 1}  # (wave 51G: no "where X is": the X of the spell, 107.3, Mind into Matter)
        if value is None:
            return None
        effect["mv"] = ["<=", value]
    elif m["xdef"]:
        return None  # (a "where X is" nothing here uses)
    if m["elv"]:  # -- trigger other (wave 51E) -- "a permanent card with equal or lesser mana value" (Kodama of the East Tree): than the permanent that entered, as it entered
        from app.rules import language

        if (value := language.x_definition("that creature's mana value")) is None:
            return None
        effect["mv"] = ["<=", value]
    if m["lp"]:  # "a creature card with lesser power" (Shadowfax): less than the source creature's power
        effect["pw"] = ["<", {"power": "self"}]
    if m["cnt"] == "any number of":
        effect["many"] = True
    if m["upto"]:  # -- if you do (wave 44A) -- "put up to X land cards from your hand onto the battlefield tapped" (The Gitrog, Ravenous Ride): at most X, read as they are chosen
        effect["many"], effect["cap"] = True, int(m["upto"]) if m["upto"].isdigit() else values.NUMBERS[m["upto"]]  # (wave 50I: "up to two")  # (X is the stand-in scripts._swap_x turns into the value, 608.2h)
    if m["tapped"]:
        effect["tapped"] = True
    if m["atk"]:  # -- trigger tail (wave 15B) -- 508.4: its controller chooses whom it attacks (looking.attack_with_entered)
        effect["attacking"] = True
        if (at := at_spec(m)) is not None:  # -- enter attacking (wave 30P) -- "… attacking that player": the effect says whom (508.4)
            effect["at"] = at
    return [effect], None


def _matches(plan: Plan, e: dict[str, Any], card: Any, ch: Any, pid: str, source: str | None) -> bool:
    from app.rules import selectors

    return any(selectors.matches(plan, selectors.from_key(k), card, ch, pid, source) for k in (e["sel"], *e.get("alt", ())))


def put_from_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Its controller chooses up to one matching card in their hand (privately), then it enters."""
    from app.rules import effects, selectors
    from app.rules.plan import decide

    pid = ctx["controller"]
    options = [c for k in (e["sel"], *e.get("alt", ()))
               for c in selectors.candidates(plan, selectors.from_key(k), pid, ctx.get("source_card"))
               if plan.state.cards[c].zone == f"{pid}:hand" and _permanent_card(plan, c) and _mv_ok(plan, ctx, e, c)]
    options = list(dict.fromkeys(options))
    may = bool(e.get("optional")) or bool(e.get("many"))  # ("you may": none is a choice; a trigger's "you may" was asked already, 603.5)
    cap = len(options) if e.get("cap") is None else max(0, effects._amount(plan, ctx, e["cap"]))
    if e.get("cap") is not None and cap == 0:  # ("up to 0": no choice to make, and nothing to ask: the hand's contents stay hidden)
        effects._remember(plan, ctx, e, [])
        if e.get("did"):
            context.bind_payment(ctx, e["did"], False)
        return True
    if not options and not (may and plan.state.zones.get(f"{pid}:hand")):
        effects._remember(plan, ctx, e, [])
        if e.get("did"):  # -- if you do (wave 26C) -- "If you do": no card was put onto the battlefield
            context.bind_payment(ctx, e["did"], False)
        return True  # (nothing is announced: the hand is hidden)
    # (-- review 25C -- a "you may" is asked whenever the hand holds cards, so whether the question appears doesn't tell the other
    # players that a matching card is there: the triggered abilities' "may" moved here, scripts._own_choice)
    decide(plan, player=pid, kind="choose_cards",
           prompt=f"{ctx.get('name') or 'It'}: {'you may ' if may else ''}put a {e.get('label') or 'permanent'} card from "
                  "your hand onto the battlefield",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
           min_choices=0 if may else 1, max_choices=min(len(options), cap) if e.get("many") else 1,
           resume={"step": "put_from_hand", "ctx": ctx, "e": e})
    return False


def _mv_ok(plan: Plan, ctx: Context, e: dict[str, Any], cid: str) -> bool:
    """-- triggers (wave 19B) -- the mana value limit of "with mana value less than or equal to …" (read now, 608.2h); wave 30P: "N or less",
    "equal to …", and "with lesser power" (less than the source's)."""
    from app.rules import characteristics as chars
    from app.rules import effects

    ch = chars.of(plan.state.cards[cid], plan.info)
    if e.get("pw"):  # -- put from hand (wave 30P) -- "with lesser power": the card's power is less than the source's
        pt = plan.ch(plan.state.cards[cid]).pt
        if pt is None or pt[0] >= effects._amount(plan, ctx, e["pw"][1]):
            return False
    if not e.get("mv"):
        return True
    op, value = e["mv"]
    mv, limit = ch.mana_value, effects._amount(plan, ctx, value)
    return mv == limit if op == "==" else mv <= limit if op == "<=" else mv < limit


def _permanent_card(plan: Plan, cid: str) -> bool:
    from app.rules import characteristics as chars

    ch = chars.of(plan.state.cards[cid], plan.info)
    return bool(ch.types & _PERMANENT_TYPES) and not ch.is_instant_or_sorcery


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import attachments, effects
    from app.rules import characteristics as chars

    ctx, e = d.resume["ctx"], d.resume["e"]
    pid = ctx["controller"]
    cards = []
    if e.get("cap") is not None and len(chosen) > max(0, effects._amount(plan, ctx, e["cap"])):
        raise ActionError("Choose no more cards than the effect allows")
    for cid in chosen[: 999 if e.get("many") else 1]:
        card = plan.state.cards.get(cid)
        if card is None or card.zone != f"{pid}:hand" or not _permanent_card(plan, cid) or not _mv_ok(plan, ctx, e, cid) \
                or not _matches(plan, e, card, chars.of(card, plan.info), pid, ctx.get("source_card")):
            raise ActionError("Choose a matching card from your hand")
        cards.append(cid)
    before = effects._remember(plan, ctx, e, cards)
    if e.get("did"):  # -- if you do (wave 26C) -- 608.2c: a card was chosen and entered (the grammar reads it only for cards that can't stay in the hand)
        context.bind_payment(ctx, e["did"], bool(cards))
    entries = [{"card": c, "player": pid, "actor": pid, "tapped": bool(e.get("tapped")), "via": ctx.get("source_object")} for c in cards]  # (wave 51E: Entry.via)
    if entries and not attachments.enter(plan, entries, ctx):
        return  # (an Aura chooses what it enchants; the resolution goes on from there)
    effects._moved(plan, ctx, e, before)
    if e.get("attacking"):  # -- trigger tail (wave 15B) -- 508.4 (the choice of whom, if any, goes on from token_attack)
        from app.rules import looking

        if not looking.attack_with_entered(plan, ctx, cards, e.get("at")):
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
    ctx["_each_put_who"] = list(who)  # -- trigger other (wave 44B) -- "then each opponent who didn't draws a card" (Kynaios and Tiro): who was asked, to tell who put nothing
    return _ask_each(plan, ctx, e, who, [])


def _ask_each(plan: Plan, ctx: Context, e: dict[str, Any], who: list[str], picks: list[dict[str, Any]]) -> bool:
    from app.rules import attachments, selectors
    from app.rules.plan import decide

    if not who:
        ctx["_put_none"] = [p for p in ctx.get("_each_put_who", ()) if not any(x["player"] == p for x in picks)]  # (wave 44B: players who put nothing)
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
