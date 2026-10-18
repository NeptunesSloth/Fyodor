"""-- refused look/cast-free (wave 3R5) -- Separating cards into a face-down and a face-up pile (CR 700.3), and picking
one card of each listed kind ("a creature card and/or a land card", "for each card type").

(Wave 53D: the piles of revealed cards -- Fact or Fiction, Steam Augury -- are app/rules/pile_groups.py's, with the piles of permanents and of
exiled cards; this module keeps the face-down / face-up piles of a look, 701.20e.)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.rules.plan import Plan


# (-- piles (wave 53D) -- the piles of revealed cards: app/rules/pile_groups.py)


# -- hidden exile (wave 18A) -- a face-down pile and a face-up pile (700.3) -------------------------------------------------
# "Target opponent looks at the top four cards of your library and separates them into a face-down pile and a face-up pile. Put one
# pile into your hand and the other into your graveyard." (Fortune's Favor, Atris, Sauron's Ransom: the opponent separates, you
# choose) / "Look at the top four cards of your library and separate them into a face-down pile and a face-up pile. An opponent
# chooses one of the piles. Put that pile into your hand and the other into your graveyard." (Riddles in the Dark, Curator of
# Destinies: you separate, an opponent chooses). Researched against the stored Comprehensive Rules (2026-09-25):
#
# * 700.3a-d — every card goes into exactly one pile, a pile may be empty, the piles aren't objects and the cards stay in the
#   library while they're grouped.
# * 701.20e — "looks at": only the separator sees all the cards. The face-up pile is shown to everyone; the face-down pile's
#   contents stay with the separator alone, so the chooser picks between "a face-down pile of N cards" and the face-up cards.
# * 608.2d — "an opponent" / "choose an opponent": the spell's controller picks which one as it resolves.
# * The piles are moved by the player the effect names ("Put one pile into your hand"): a face-down pile put into the graveyard is
#   public from then on (the cards are face up in a graveyard).
# Not read: the cards exiled in the piles (The Celestial Toymaker), library piles of ten (Phyrexian Portal), piles of exiled
# cards that are then cast (Hostile Negotiations, Abstract Performance).
def _down_cards(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> list[str]:
    from app.rules.effects import _amount

    return list(plan.state.zones.get(zone_key(ctx["controller"], "library"), [])[: _amount(plan, ctx, e["n"])])


def piles_down(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Start: which opponent takes part (a target, or the controller's choice, 608.2d), then the separation."""
    from app.rules import effects, pile_groups
    from app.rules.effects import decide

    pile_groups.note_grouping(plan, ctx)  # -- piles (wave 53D) -- The Celestial Toymaker counts spells and abilities that made piles
    pid = ctx["controller"]
    if not _down_cards(plan, ctx, e):
        return True
    if e.get("who") == "target":
        found = [p for p in effects._players(plan, ctx, "target") if p in plan.live() and p != pid]
        return bool(not found) or _down_separate(plan, ctx, e, found[0])
    opponents = [p for p in plan.live() if p != pid]
    if not opponents:
        return True
    if len(opponents) == 1:
        return _down_separate(plan, ctx, e, opponents[0])
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'Piles'}: choose an opponent",
           options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": "piles_down_opponent", "ctx": ctx, "e": e})
    return False


def resume_down_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}")
    if _down_separate(plan, r["ctx"], r["e"], chosen[0]):
        effects.continue_effects(plan, r["ctx"])


def _down_separate(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], opponent: str) -> bool:
    from app.rules.effects import decide

    pid = ctx["controller"]
    cards = _down_cards(plan, ctx, e)
    separator = opponent if e["by"] == "opponent" else pid
    plan.do({"type": "look_top", "player": pid, "count": len(cards)}, actor=separator)  # 701.20e: shown to the separator alone
    decide(plan, player=separator, kind="choose_cards",
           prompt=f"{ctx.get('name') or 'Piles'}: separate the cards into a face-down pile and a face-up pile — choose the cards of the "
                  "face-down pile (the others form the face-up pile; a pile may be empty)",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards],
           min_choices=0, max_choices=len(cards), resume={"step": "piles_down_split", "ctx": ctx, "e": e, "opponent": opponent,
                                                         "cards": cards})
    return False


def resume_down_split(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import decide

    r = d.resume
    ctx, e = r["ctx"], r["e"]
    cards = [c for c in r["cards"] if c in plan.state.cards]
    down = [c for c in cards if c in chosen]
    up = [c for c in cards if c not in chosen]
    plan.do({"type": "end_view", "zone": "library"}, actor=d.player)
    if up:
        plan.do({"type": "reveal", "card_ids": up}, actor=d.player)  # the face-up pile: shown to everyone
    plan.note(f"{plan.name(d.player)} separates the cards: {len(down)} face down, {len(up)} face up")
    chooser = ctx["controller"] if e["choose"] == "you" else r["opponent"]
    up_names = ", ".join(plan.state.cards[c].name or "a card" for c in up) or "no cards"
    decide(plan, player=chooser, kind="choose_one",
           prompt=f"{ctx.get('name') or 'Piles'}: choose the pile {plan.name(ctx['controller'])} puts into their hand "
                  "(the other goes to their graveyard)",
           options=[DecisionOption(id="down", label=f"Face-down pile: {len(down)} card{'s' if len(down) != 1 else ''}"),
                    DecisionOption(id="up", label=f"Face-up pile: {up_names}")],
           resume={"step": "piles_down_pick", "ctx": ctx, "piles": {"down": down, "up": up}})


def resume_down_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    ctx = r["ctx"]
    pid = ctx["controller"]
    keep, rest = (r["piles"]["down"], r["piles"]["up"]) if chosen[0] == "down" else (r["piles"]["up"], r["piles"]["down"])
    plan.note(f"{plan.name(d.player)} chooses the {'face-down' if chosen[0] == 'down' else 'face-up'} pile")
    library = set(plan.state.zones.get(zone_key(pid, "library"), []))
    keep, rest = [c for c in keep if c in library], [c for c in rest if c in library]
    if keep:
        plan.do({"type": "move", "card_ids": keep, "to": {"player": pid, "zone": "hand"}}, actor=pid)
    if rest:
        plan.do({"type": "move", "card_ids": rest, "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
    effects.continue_effects(plan, ctx)


def join_down_piles(body: str) -> str:
    """The sentences of a face-down / face-up pile spell as the one clause language._DOWN reads."""
    tail1 = ", then you put one pile into your hand and the other into your graveyard"
    body = re.sub(r"([Tt])arget opponent looks at the top (\w+) cards of your library and separates them into a face-down pile and a "
                  r"face-up pile\. Put one pile into your hand and the other into your graveyard\.",
                  lambda m: f"{m[1]}arget opponent separates the top {m[2]} cards of your library into a face-down pile and a face-up "
                            f"pile{tail1}.", body)
    body = re.sub(r"Choose an opponent\. They look at the top (\w+) cards of your library and separate them into a face-down pile and a "
                  r"face-up pile\. Put one pile into your hand and the other into your graveyard\.",
                  lambda m: f"An opponent separates the top {m[1]} cards of your library into a face-down pile and a face-up pile{tail1}.",
                  body)
    return re.sub(r"[Ll]ook at the top (\w+) cards of your library and separate them into a face-down pile and a face-up pile\. An "
                  r"opponent chooses one of (?:the|those) piles\. Put that pile into your hand and the other into your graveyard\.",
                  lambda m: f"You separate the top {m[1]} cards of your library into a face-down pile and a face-up pile, then an "
                            "opponent chooses one of them, then you put that pile into your hand and the other into your graveyard.",
                  body)


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


# -- "If X is greater than or equal to the number of cards in your library, you win the game." ---------------
def win_if_library(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Thassa's Oracle: X (the value the ability defined, read now: 107.3c, 608.2h) against the cards in its
    controller's library; the win (104.2b) is left to the players when a permanent says someone "can't win
    the game" (not modelled: an effect that stops a win would make an automatic win wrong)."""
    from app.rules import characteristics as chars
    from app.rules import values
    from app.rules.replace import _win

    pid = ctx["controller"]
    x = values.evaluate(plan, ctx, e["x"])
    if x < len(plan.state.zones.get(zone_key(pid, "library"), [])):
        return True
    blockers = [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and not c.face_down
                and "can't win the game" in " ".join(ab.text for ab in chars.of(c, plan.info).abilities)]
    if blockers:
        plan.note(f"{plan.name(pid)} would win the game, but {blockers[0].name} says a player can't: resolve it by hand")
        return True
    _win(plan, pid)
    return True


# -- "put it onto the battlefield tapped and attacking" (508.4) ------------------------------------------------
def attack_with_entered(plan: Plan, ctx: dict[str, Any], cards: list[str], at: dict[str, Any] | None = None) -> bool:
    """The creatures a look-and-distribute just put onto the battlefield tapped are attacking (508.4): the controller chooses which defending
    player, planeswalker a defending player controls, or battle a defending player protects each one attacks (in Commander every opponent is a
    defending player: 802.2) — token_grammar.enter_attacking, the one reading of it. They never "attacked" (no attack triggers); outside combat,
    or for a player who isn't the attacking player, they're simply not attacking (506.3b). False while that choice waits."""
    from app.rules import token_grammar

    return token_grammar.enter_attacking(plan, ctx, cards, at)
