# -- piles (wave 53D) --
"""Piles: "Separate all permanents target player controls into two piles. That player sacrifices all permanents in the pile of their choice."
(Liliana of the Veil), "Separate all creatures target player controls into two piles. Destroy all creatures in the pile of that player's choice."
(Do or Die), "Each opponent separates the creatures they control into two piles. For each opponent, you choose one of their piles. Each opponent
sacrifices the creatures in their chosen pile." (Make an Example), "Separate all creature cards in your graveyard into two piles. Exile the pile of an
opponent's choice and return the other to the battlefield." (Death or Glory), "Starting with you, each player separates all permanents they control
into three piles. Then each player chooses one of their piles at random and sacrifices those permanents." (Whims of the Fates). Researched against CR
2026-09-25 and the cards' rulings. (The piles of library cards just revealed are looking.py's, and their exiled face-down ones facedown piles': 18A.)

* 700.3a-d: each object of the group goes into exactly one pile, a pile may be empty, a pile is no object, and objects grouped into piles stay in their
  zone (nothing moves until the effect says so). The piles are public: the cards (or permanents) are, so the separation is logged with the names.
* Who separates and who chooses is the card's: ``split`` "you" (the ability's controller) or "owner" (each player separates their own group); ``pick``
  "you", "owner", "opponent" (an opponent of the controller, who chooses which one as it resolves: 608.2d, as the rulings of Intrude on the Mind, Split the
  Spoils and Boneyard Parley say) or "random" (every pile is equally likely, an empty one too: Whims of the Fates ruling). All the separations come first
  (in APNAP order, or ``start`` "you" then turn order, 101.4), then all the choices, then what the piles do happens to every group at once (101.4).
* A pile is chosen even when one is empty (the chooser may take the empty one: Liliana ruling "A pile can be empty. If the player chooses an empty pile,
  no permanents will be sacrificed"); a group with no objects has nothing to separate or choose.

State (``ctx["pile"]``, in the resolution context of the pending decision: saved, replayed; old saves have none): ``groups`` ({"owner", "cards",
"piles"}), ``stage`` / ``g`` (where it is).
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
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


def bind(body: str, parse: Any, split_sentences: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The effects of a piles body, or None when it isn't one (or isn't read)."""
    sentences = split_sentences(body.strip())
    m = _SEPARATE.match(sentences[0]) if sentences else None
    if m is None:
        return None
    what = m["what"] or m["what2"]
    after = next((a for a in _AFTER if tuple(sentences[1:]) == a[0] or tuple([sentences[1][:1].upper() + sentences[1][1:], *sentences[2:]]) == a[0]), None) \
        if len(sentences) > 1 else None
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


# -- carrying it out ------------------------------------------------------------------------------------------------
def _names(plan: Plan, cards: list[str]) -> str:
    return ", ".join(plan.state.cards[c].name or "a card" for c in cards) or "no cards"


def pile_deal(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import selectors
    from app.rules.effects import _players

    owners = [p for p in plan.apnap() if p in _players(plan, ctx, e["who"])]
    if e.get("start") and owners:  # 101.4: "starting with you", then turn order
        at = owners.index(ctx["controller"]) if ctx["controller"] in owners else 0
        owners = owners[at:] + owners[:at]
    sel = selectors.from_key(e["sel"])
    found = selectors.candidates(plan, sel, ctx["controller"], ctx.get("source_card"))
    ctx["pile"] = {"stage": "split", "g": 0, "groups": [
        {"owner": p, "cards": [c for c in found if plan.state.cards[c].zone.split(":")[0] == p], "piles": []} for p in owners]}
    return _run(plan, ctx, e)


def _run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    st = ctx["pile"]
    groups = st["groups"]
    n = int(e["n"])
    while st["stage"] == "split" and st["g"] < len(groups):
        grp = groups[st["g"]]
        cards = [c for c in grp["cards"] if c in plan.state.cards]
        split_by = ctx["controller"] if e["split"] == "you" else grp["owner"]
        if not cards or split_by not in plan.live():
            grp["piles"] = [cards] + [[] for _ in range(n - 1)] if cards else []
            st["g"] += 1
            continue
        placed = [c for p in grp["piles"] for c in p]
        rest = [c for c in cards if c not in placed]
        if len(grp["piles"]) == n - 1:  # the last pile is what is left (700.3a)
            grp["piles"].append(rest)
            plan.note(f"{plan.name(split_by)} separates {plan.name(grp['owner'])}'s {e['say']} into piles: "
                      + " / ".join(f"{_names(plan, p)}" for p in grp["piles"]), cards, actor=split_by)
            st["g"] += 1
            continue
        decide(plan, player=split_by, kind="choose_cards",
               prompt=f"{ctx.get('name') or 'Piles'}: separate {plan.name(grp['owner'])}'s {e['say']} into {'two' if n == 2 else 'three'} piles — "
                      f"choose the {'first' if not grp['piles'] else 'second'} pile (a pile may be empty)",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in rest],
               min_choices=0, max_choices=len(rest),
               resume={"step": "pile_split", "ctx": ctx, "e": e, "rest": [], "picked": []})  # (rest, picked: engine._settle_decision)
        return False
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
        chooser = _chooser(plan, ctx, e, grp, st)
        if chooser is None:
            return False  # (waiting for which opponent chooses)
        if chooser not in plan.live():  # (nobody to choose, or the chooser left the game: 800.4a, the first pile)
            grp["pick"] = 0
            st["g"] += 1
            continue
        decide(plan, player=chooser, kind="choose_one",
               prompt=f"{ctx.get('name') or 'Piles'}: choose one of {plan.name(grp['owner'])}'s piles",
               options=[DecisionOption(id=str(i), label=f"Pile {i + 1}: {_names(plan, p)}") for i, p in enumerate(grp["piles"])],
               resume={"step": "pile_pick", "ctx": ctx, "e": e, "rest": [], "picked": []})
        return False
    return _apply(plan, ctx, e)


def _chooser(plan: Plan, ctx: Context, e: dict[str, Any], grp: dict[str, Any], st: dict[str, Any]) -> str | None:
    """Who chooses this group's pile ("" if there is nobody); for "an opponent" the controller names which one first (608.2d), once for the effect.
    None: that question is asked, the effect waits."""
    from app.rules.plan import decide

    if e["pick"] == "you":
        return str(ctx["controller"])
    if e["pick"] == "owner":
        return str(grp["owner"])
    opponents = [p for p in plan.live() if p != ctx["controller"]]
    if not opponents:
        return ""
    if len(opponents) == 1:
        st["opponent"] = opponents[0]
    if "opponent" not in st:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Piles'}: choose an opponent to choose a pile",
               options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents],
               resume={"step": "pile_opponent", "ctx": ctx, "e": e, "rest": [], "picked": []})
        return None
    return str(st["opponent"])


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
    if chosen:
        ctx["pile"]["opponent"] = chosen[0]
        plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])} to choose a pile", actor=d.player)
    else:
        ctx["pile"]["opponent"] = ""
    if _run(plan, ctx, e):
        continue_effects(plan, ctx)


def resume_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    st = ctx["pile"]
    grp = st["groups"][st["g"]]
    grp["pick"] = int(chosen[0]) if chosen else 0
    plan.note(f"{plan.name(d.player)} chooses pile {grp['pick'] + 1} of {plan.name(grp['owner'])}'s: {_names(plan, grp['piles'][grp['pick']])}",
              grp["piles"][grp["pick"]], actor=d.player)
    st["g"] += 1
    if _run(plan, ctx, e):
        continue_effects(plan, ctx)


def _apply(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Every group's piles are made and chosen: what the chosen piles and the others do, all at once (101.4)."""
    groups = ctx["pile"]["groups"]
    chosen = [c for g in groups if g.get("pick") is not None for c in g["piles"][g["pick"]]]
    other = [c for g in groups if g.get("pick") is not None for i, p in enumerate(g["piles"]) if i != g["pick"] for c in p]
    del ctx["pile"]
    for op, cards in ((e.get("chosen"), chosen), (e.get("other"), other)):
        if op and cards:
            _do(plan, ctx, e, op, [c for c in cards if c in plan.state.cards])
    return True


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
    else:  # "battlefield": the cards return under their owners' control (400.3); "hand" / "graveyard": their owners'
        effects._return_cards(plan, ctx, {"to": op, **({"under": "owner"} if op == "battlefield" else {})}, cards)


PRIMITIVES = {"pile_deal": pile_deal}
RESUME = {"pile_split": resume_split, "pile_pick": resume_pick, "pile_opponent": resume_opponent}
