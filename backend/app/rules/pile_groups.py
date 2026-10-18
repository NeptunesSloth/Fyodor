# -- piles (wave 53D) --
"""Piles: "Separate all permanents target player controls into two piles. That player sacrifices all permanents in the pile of their choice."
(Liliana of the Veil), "Separate all creatures target player controls into two piles. Destroy all creatures in the pile of that player's choice."
(Do or Die), "Each opponent separates the creatures they control into two piles. For each opponent, you choose one of their piles. Each opponent
sacrifices the creatures in their chosen pile." (Make an Example), "Separate all creature cards in your graveyard into two piles. Exile the pile of an
opponent's choice and return the other to the battlefield." (Death or Glory), "Starting with you, each player separates all permanents they control
into three piles. Then each player chooses one of their piles at random and sacrifices those permanents." (Whims of the Fates), and piles of the cards
just revealed or exiled: "Reveal the top five cards of your library and separate them into two piles. An opponent chooses one of those piles. Put that
pile into your hand and the other into your graveyard. …" (Intrude on the Mind), "… Put a card from the chosen pile into your hand, then put all other
cards revealed this way on the bottom of your library in any order." (Truth or Tale), "Exile up to five target permanent cards from your graveyard and
separate them into two piles. …" (Split the Spoils), "Exile up to five target creature cards from graveyards. An opponent separates those cards into two
piles. Put all cards from the pile of your choice onto the battlefield under your control and the rest into their owners' graveyards." (Boneyard Parley).
Researched against CR 2026-09-25 and the cards' rulings. (Fact or Fiction's and Steam Augury's wording is looking.py's, and the face-down piles of
exiled cards are facedown piles': 18A, 53D face-down.)

* 700.3a-d: each object of the group goes into exactly one pile, a pile may be empty, a pile is no object, and objects grouped into piles stay in their
  zone (nothing moves until the effect says so). The piles are public: the cards (or permanents) are, so the separation is logged with the names.
* Who separates and who chooses is the card's: ``split`` "you" (the ability's controller), "owner" (each player separates their own group) or "opponent";
  ``pick`` "you", "owner", "opponent" or "random" (every pile is equally likely, an empty one too: Whims of the Fates ruling). "An opponent" is the one
  the controller names as it resolves, once for the whole effect (608.2d, as the rulings of Intrude on the Mind, Split the Spoils, Boneyard Parley and
  Jace, Architect of Thought say). All the separations come first (in APNAP order, or ``start`` "you" then turn order, 101.4), then all the choices, then
  what the piles do happens to every group at once (101.4).
* A pile is chosen even when one is empty (Liliana ruling: "A pile can be empty. If the player chooses an empty pile, no permanents will be sacrificed";
  Intrude on the Mind: all the cards in one pile and an empty other is allowed); a group with no objects has nothing to separate or choose.
* The groups: the permanents a player controls / the cards in your graveyard that a selector names (``sel``), the cards just revealed (``src`` "looked",
  the controller's library) or the objects an earlier instruction bound (``src`` "ref:<name>", e.g. the cards a Split the Spoils exiled).
* What a pile does (``chosen``, ``other``): sacrifice, destroy, exile, tap, hand ("your hand": the cards' owner's, 400.3), graveyard (their owners'),
  battlefield (their owners' control) / battlefield_you (under your control), bottom (the bottom of the library, in the order the controller picks: 401.4;
  always the last step), pick_hand (the controller picks one card of the pile for their hand; the rest of that pile join the next step).

State (``ctx["pile"]``, in the resolution context of the pending decision: saved, replayed; old saves have none): ``groups`` ({"owner", "cards", "piles",
"pick"}), ``stage`` / ``g`` (where it is), ``opponent`` (the one named), ``steps`` (what is left to do).
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Found = tuple[list[dict[str, Any]], Any, bool]
_SEPARATE = re.compile(r"^(?:(?P<start>Starting with you), )?(?:[Ss]eparate all (?P<what>[a-z ]+?) (?P<who>target player controls|in your graveyard)|"
                       r"[Ee]ach (?P<each>player|opponent) separates (?:all |the )?(?P<what2>[a-z ]+?) they control) into (?P<n>two|three) piles\.$")
_NOUN = {"permanents": "", "creatures": "creature", "creature cards": "creature card", "nontoken lands": "nontoken land", "lands": "land"}
# the sentences after the separation, each: (how the pile is chosen, what is done to the chosen pile, to the others)
_AFTER = (
    (("That player sacrifices all permanents in the pile of their choice.",), ("owner", "sacrifice", None, "permanents")),
    (("Destroy all creatures in the pile of that player's choice.", "They can't be regenerated."), ("owner", "destroy", None, "creatures")),
    (("For each opponent, you choose one of their piles.", "Each opponent sacrifices the creatures in their chosen pile."), ("you", "sacrifice", None, "creatures")),
    (("Exile the pile of an opponent's choice and return the other to the battlefield.",), ("opponent", "exile", "battlefield", "creature cards")),
    (("Then each player chooses one of their piles at random and sacrifices those permanents.",), ("random", "sacrifice", None, "permanents")),
)
# piles of cards just revealed or exiled: who separates and who chooses, then what the piles do
_REVEAL = re.compile(r"^Reveal the top (?P<n>\w+) cards of your library(?P<sep> and separate them into two piles)?\.$")
_EXILE = re.compile(r"^(?P<ex>Exile up to \w+ target (?:permanent|creature) cards from (?:your graveyard|graveyards))(?P<sep> and separate them into two piles)?\.$")
_OPP_CHOOSES = "An opponent chooses one of those piles."
_OPP_SEPARATES = ("An opponent separates those cards into two piles.",)
_DEST = {  # the sentence -> (chosen op, other op, who chooses)
    "Put that pile into your hand and the other into your graveyard.": ("hand", "graveyard", "opponent"),
    "Put a card from the chosen pile into your hand, then put all other cards revealed this way on the bottom of your library in any order.":
        ("pick_hand", "bottom", "opponent"),
    "Put one pile into your hand and the other on the bottom of your library in any order.": ("hand", "bottom", "you"),
    "Put all cards from the pile of your choice onto the battlefield under your control and the rest into their owners' graveyards.":
        ("battlefield_you", "graveyard", "you"),
}
_THOPTER = ("Create a 0/0 colorless Thopter artifact creature token with flying, then put a +1/+1 counter on it for each card put into your graveyard "
            "this way.")


def bind(body: str, parse: Any, split_sentences: Any) -> Found | None:
    """The effects of a piles body, or None when it isn't one (or isn't read)."""
    sentences = split_sentences(body.strip())
    if not sentences:
        return None
    first = sentences[0]
    if _SEPARATE.match(first):
        return _permanents(sentences)
    if _REVEAL.match(first) or _EXILE.match(first):
        return _cards(sentences, parse)
    return None


def _permanents(sentences: list[str]) -> Found | None:
    m = _SEPARATE.match(sentences[0])
    assert m is not None
    what = m["what"] or m["what2"]
    after = next((a for a in _AFTER if tuple(sentences[1:]) == a[0]), None)
    if after is None or after[1][3] != what or what not in _NOUN:
        return None
    pick, chosen, other, _ = after[1]
    n = 3 if m["n"] == "three" else 2
    # who is grouped, who separates: "target player controls" (you separate), "in your graveyard" (you), "each opponent / player … they control" (each one)
    group = {"who": "target", "split": "you"} if m["who"] == "target player controls" else {"who": "you", "split": "you"} if m["who"] else \
        {"who": "each_opponent" if m["each"] == "opponent" else "each_player", "split": "owner"}
    if (pick == "random") != (n == 3) or (pick == "owner") != (m["who"] == "target player controls") or (pick == "opponent") != (m["who"] == "in your graveyard"):
        return None
    zone = "graveyard" if m["who"] == "in your graveyard" else "battlefield"
    noun = _NOUN[what]
    from app.rules import selectors

    sel = selectors.parse(f"{noun} in your graveyard" if zone == "graveyard" else noun) if noun else selectors.Selector()
    if sel is None:
        return None
    effect = {"do": "pile_deal", **group, "sel": sel.key(), "zone": zone, "pick": pick, "n": n, "chosen": chosen, "other": other, "say": what,
              **({"start": "you"} if m["start"] else {})}
    return [effect, *([{"do": "no_regen"}] if chosen == "destroy" else [])], "player" if group["who"] == "target" else None, False


def _cards(sentences: list[str], parse: Any) -> Found | None:
    """"Reveal the top N cards of your library [and separate them into two piles]. …" / "Exile up to N target … cards from … [and separate them into
    two piles]. …": the cards revealed or exiled, who separates them, who chooses, what the piles do, then (Intrude on the Mind) the rest."""
    rest = list(sentences[1:])
    m = _REVEAL.match(sentences[0]) or _EXILE.match(sentences[0])
    assert m is not None
    reveal = "n" in m.groupdict()
    found = parse(f"Reveal the top {m['n']} cards of your library." if reveal else f"{m['ex']}.")
    if found is None or found[2] or len(found[0]) != 1:
        return None
    effects, groups = found[0], found[1]
    if m["sep"]:  # "and separate them into two piles": you separate, an opponent chooses
        if not rest or rest.pop(0) != _OPP_CHOOSES:
            return None
        split, who = "you", "opponent"
    else:  # "An opponent separates those cards into two piles.": the pile of your choice
        if not rest or tuple(rest[:1]) != _OPP_SEPARATES:
            return None
        rest.pop(0)
        split, who = "opponent", "you"
    dest = _DEST.get(rest.pop(0)) if rest else None
    if dest is None or dest[2] != who:
        return None
    tail: list[dict[str, Any]] = []
    name = "pq"
    if rest:  # Intrude on the Mind: a Thopter with a +1/+1 counter for each card put into your graveyard this way
        if rest != [_THOPTER] or dest[:2] != ("hand", "graveyard"):
            return None
        token = parse("Create a 0/0 colorless Thopter artifact creature token with flying.")
        if token is None or len(token[0]) != 1 or token[0][0]["do"] != "create_token":
            return None
        tail = [{**token[0][0], "as": "pt"}, {"do": "add_counters", "who": "ref:pt", "kind": "+1/+1",
                                              "n": {"this_way": "your_graveyard", "of": None, "ref_count": name}}]
    if not reveal:
        effects = [{**effects[0], "as": "px"}]
    pile = {"do": "pile_deal", "src": "looked" if reveal else "ref:px", "split": split, "pick": who, "n": 2, "chosen": dest[0], "other": dest[1], "say": "cards",
            **({"as": name} if tail else {})}
    return [*effects, pile, *tail], groups, False


# -- carrying it out ------------------------------------------------------------------------------------------------
def _names(plan: Plan, cards: list[str]) -> str:
    return ", ".join(plan.state.cards[c].name or "a card" for c in cards) or "no cards"


def _group_cards(plan: Plan, ctx: Context, e: dict[str, Any]) -> list[dict[str, Any]]:
    """The groups to separate: one for each player whose permanents / cards a selector names, or one of the controller's revealed / bound cards."""
    from app.rules import context, selectors
    from app.rules.effects import _looked, _players

    me = ctx["controller"]
    if e.get("src") == "looked":
        return [{"owner": me, "cards": _looked(plan, ctx)[1], "piles": []}]
    if e.get("src"):
        return [{"owner": me, "cards": context.objects(plan, ctx, e["src"][len(context.PREFIX):]), "piles": []}]
    owners = [p for p in plan.apnap() if p in _players(plan, ctx, e["who"])]
    if e.get("start") and owners:  # 101.4: "starting with you", then turn order
        at = owners.index(me) if me in owners else 0
        owners = owners[at:] + owners[:at]
    found = selectors.candidates(plan, selectors.from_key(e["sel"]), me, ctx.get("source_card"))
    return [{"owner": p, "cards": [c for c in found if plan.state.cards[c].zone.split(":")[0] == p], "piles": []} for p in owners]


def pile_deal(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    ctx["pile"] = {"stage": "split", "g": 0, "groups": _group_cards(plan, ctx, e)}
    return _run(plan, ctx, e)


def _opponent(plan: Plan, ctx: Context, e: dict[str, Any]) -> str | None:
    """The opponent who separates / chooses (the same one for the whole effect): the only one, or the one the controller names (608.2d). "" if
    there is none left (800.4a); None while the controller is asked."""
    from app.rules.plan import decide

    st = ctx["pile"]
    opponents = [p for p in plan.live() if p != ctx["controller"]]
    if len(opponents) <= 1:
        return opponents[0] if opponents else ""
    if "opponent" not in st:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Piles'}: choose an opponent for the piles",
               options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents],
               resume={"step": "pile_opponent", "ctx": ctx, "e": e, "rest": [], "picked": []})
        return None
    return str(st["opponent"])


def _run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    st = ctx["pile"]
    groups = st["groups"]
    n = int(e["n"])
    while st["stage"] == "split" and st["g"] < len(groups):
        grp = groups[st["g"]]
        cards = [c for c in grp["cards"] if c in plan.state.cards]
        if not cards:
            st["g"] += 1
            continue
        split_by = ctx["controller"] if e["split"] == "you" else grp["owner"] if e["split"] == "owner" else _opponent(plan, ctx, e)
        if split_by is None:
            return False  # (waiting for which opponent separates)
        placed = [c for p in grp["piles"] for c in p]
        rest = [c for c in cards if c not in placed]
        if split_by not in plan.live():  # (the separator left the game: 800.4a, everything in the first pile)
            grp["piles"] = [cards, *([] for _ in range(n - 1))]
        elif len(grp["piles"]) == n - 1:  # the last pile is what is left (700.3a)
            grp["piles"].append(rest)
        else:
            decide(plan, player=split_by, kind="choose_cards",
                   prompt=f"{ctx.get('name') or 'Piles'}: separate {plan.name(grp['owner']) + chr(39) + 's ' if e.get('who') else ''}{e['say']} into "
                          f"{'two' if n == 2 else 'three'} piles — choose the {'first' if not grp['piles'] else 'second'} pile (a pile may be empty)",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in rest],
                   min_choices=0, max_choices=len(rest),
                   resume={"step": "pile_split", "ctx": ctx, "e": e, "rest": [], "picked": []})  # (rest, picked: engine._settle_decision)
            return False
        plan.note(f"{plan.name(split_by)} separates {plan.name(grp['owner']) + chr(39) + 's ' if e.get('who') else ''}{e['say']} into piles: "
                  + " / ".join(_names(plan, p) for p in grp["piles"]), cards, actor=split_by if split_by in plan.live() else None)
        st["g"] += 1
    if st["stage"] == "split":
        st.update(stage="pick", g=0)
    while st["stage"] == "pick" and st["g"] < len(groups):
        grp = groups[st["g"]]
        if not any(grp["piles"]):  # (nothing to choose among: no objects)
            st["g"] += 1
            continue
        if e["pick"] == "random":  # every pile equally likely, an empty one too
            grp["pick"] = (plan.rng or secrets.SystemRandom()).choice(range(n))
            plan.note(f"{plan.name(grp['owner'])}'s pile {grp['pick'] + 1} is chosen at random: {_names(plan, grp['piles'][grp['pick']])}",
                      grp["piles"][grp["pick"]])
            st["g"] += 1
            continue
        chooser = ctx["controller"] if e["pick"] == "you" else grp["owner"] if e["pick"] == "owner" else _opponent(plan, ctx, e)
        if chooser is None:
            return False  # (waiting for which opponent chooses)
        if not chooser or chooser not in plan.live():  # (nobody to choose, or the chooser left the game: 800.4a, the first pile)
            grp["pick"] = 0
            st["g"] += 1
            continue
        decide(plan, player=chooser, kind="choose_one",
               prompt=f"{ctx.get('name') or 'Piles'}: choose one of {plan.name(grp['owner']) + chr(39) + 's ' if e.get('who') else 'the '}piles",
               options=[DecisionOption(id=str(i), label=f"Pile {i + 1}: {_names(plan, p)}") for i, p in enumerate(grp["piles"])],
               resume={"step": "pile_pick", "ctx": ctx, "e": e, "rest": [], "picked": []})
        return False
    return _apply(plan, ctx, e)


def resume_split(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    st = ctx["pile"]
    grp = st["groups"][st["g"]]
    grp["piles"].append([c for c in grp["cards"] if c in chosen])
    if _run(plan, ctx, e):
        continue_effects(plan, ctx)


def resume_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    ctx["pile"]["opponent"] = chosen[0] if chosen else ""
    if chosen:
        plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])} for the piles", actor=d.player)
    if _run(plan, ctx, e):
        continue_effects(plan, ctx)


def resume_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    st = ctx["pile"]
    grp = st["groups"][st["g"]]
    grp["pick"] = int(chosen[0]) if chosen else 0
    plan.note(f"{plan.name(d.player)} chooses pile {grp['pick'] + 1}: {_names(plan, grp['piles'][grp['pick']])}", grp["piles"][grp["pick"]], actor=d.player)
    st["g"] += 1
    if _run(plan, ctx, e):
        continue_effects(plan, ctx)


def _apply(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Every group's piles are made and chosen: what the chosen piles and the others do, all at once (101.4)."""
    st = ctx["pile"]
    groups = st["groups"]
    chosen = [c for g in groups if g.get("pick") is not None for c in g["piles"][g["pick"]]]
    other = [c for g in groups if g.get("pick") is not None for i, p in enumerate(g["piles"]) if i != g["pick"] for c in p]
    st["steps"] = [[op, cards] for op, cards in ((e.get("chosen"), chosen), (e.get("other"), other)) if op]
    return _steps(plan, ctx, e)


def _steps(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    st = ctx["pile"]
    while st["steps"]:
        op, cards = st["steps"].pop(0)
        cards = [c for c in cards if c in plan.state.cards]
        if not cards:
            continue
        if op == "pick_hand":  # the controller picks one card of the pile; the others go on with the next step
            decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'Piles'}: choose a card of the chosen pile for your hand",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards],
                   min_choices=1, max_choices=1, resume={"step": "pile_card", "ctx": ctx, "e": e, "cards": cards, "rest": [], "picked": []})
            return False
        if op == "bottom":  # always the last step: the order is the controller's private choice (401.4), then the resolution goes on
            del ctx["pile"]
            return _bottom(plan, ctx, cards)
        _do(plan, ctx, e, op, cards)
    del ctx["pile"]
    return True


def resume_card(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    st = ctx["pile"]
    cards = [c for c in d.resume["cards"] if c in plan.state.cards]
    picked = [c for c in cards if c in chosen] or cards[:1]  # (the chooser left the game: the first)
    _do(plan, ctx, e, "hand", picked)
    if st["steps"]:
        st["steps"][0][1] = [*st["steps"][0][1], *(c for c in cards if c not in picked)]
    if _steps(plan, ctx, e):
        continue_effects(plan, ctx)


def _bottom(plan: Plan, ctx: Context, cards: list[str]) -> bool:
    from app.rules import effects

    owner = plan.state.cards[cards[0]].owner
    if len(cards) == 1:
        effects.bottom_at_random(plan, owner, cards, actor=ctx["controller"])
        return True
    effects._ask_order(plan, ctx, ctx["controller"], owner, cards, "bottom")
    return False


def _do(plan: Plan, ctx: Context, e: dict[str, Any], op: str, cards: list[str]) -> None:
    from app.rules import effects

    if op == "sacrifice":
        effects._sacrifice_cards(plan, cards, ctx["controller"], ctx)  # 701.21a: by each one's controller, all at once
    elif op == "destroy":
        effects._destroy_cards(plan, ctx, {}, [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield")])
    elif op == "exile":
        effects.exile_cards(plan, ctx, {}, cards)
    elif op == "tap":
        plan.do({"type": "tap", "card_ids": cards, "tapped": True}, actor=ctx["controller"])
    else:  # the cards return under their owners' control (400.3), or yours; "hand" / "graveyard": their owners'
        to = "battlefield" if op.startswith("battlefield") else op
        effects._return_cards(plan, ctx, {"to": to, **({"under": "you" if op == "battlefield_you" else "owner"} if to == "battlefield" else {}),
                                          **({"as": e["as"]} if op == "graveyard" and e.get("as") else {})}, cards)


PRIMITIVES = {"pile_deal": pile_deal}
RESUME = {"pile_split": resume_split, "pile_pick": resume_pick, "pile_opponent": resume_opponent, "pile_card": resume_card}
