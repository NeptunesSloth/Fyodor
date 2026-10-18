"""-- keyword soups (wave 50J) -- "creatures you control gain first strike until end of turn if a creature you control has first strike. The same is
true for flying, deathtouch, …" (Odric, Lunarch Marshal; Majestic Myriarch, Bleeding Effect, Concerted Effort), "each other creature you control gets
+1/+1 if it has flying, +1/+1 if it has first strike, and so on for …" (Akroma, Vision of Ixidor), "the number of abilities from among flying, … found
among creatures you control" (Odric, Blood-Cursed), "put a flying counter on any creature you control if a creature card in your graveyard has flying. Repeat this
process for …" (Kathril, Aspect Warper: a keyword counter, 122.1b, on a creature of the controller's choice for each keyword, then +1/+1 counters for the number put).

Each listed keyword is its own check, all made as the ability resolves (611.2c: the creatures affected and what they gain are fixed then; Odric's rulings).
A creature "has" a keyword by any variant of it (702.11d: "hexproof from white" is a variant of hexproof) and the objects gain the variant as the holder
has it (the ruling of 2020-01-24); several creatures with the same ability are the one ability. "Partner" is partner and partner with, not "Partner—Character
select" (Akroma's ruling). The lines come from ``oracle.keyword_pieces``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import oracle, selectors

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

Context = dict[str, Any]
WORDS = frozenset({"flying", "first strike", "double strike", "deathtouch", "haste", "hexproof", "indestructible", "lifelink", "menace", "reach", "skulk",
                   "trample", "vigilance", "fear", "landwalk", "protection", "partner"})
_LIST = r"(?P<ks>[a-z ]+(?:, [a-z ]+)*(?:,? and [a-z ]+)?)"
_SRC = {"a creature you control has": "creature you control", "a creature card in your graveyard has": "creature card in your graveyard",
        "you control a creature with": "creature you control"}
_GRANT = re.compile(rf"^(?P<who>[Cc]reatures you control|~|[Tt]his creature|[Ii]t) gains? (?P<k>[a-z ]+?) until end of turn if (?P<src>{'|'.join(_SRC)}) (?P=k)\. "
                    rf"The same is true for {_LIST}\.$")
_PUMP = re.compile(rf"^(?:[Uu]ntil end of turn, )?each other creature you control gets \+1/\+1 if it has (?P<k>[a-z ]+?), \+1/\+1 if it has (?P<k2>[a-z ]+?), "
                   rf"and so on for {_LIST}\.$")


_COUNTERS = re.compile(rf"^[Pp]ut an? (?P<k>[a-z ]+?) counter on any creature you control if a creature card in your graveyard has (?P=k)\. Repeat this process for {_LIST}\. "
                       r"Then put a \+1/\+1 counter on (?:~|this creature) for each counter put on a creature this way\.$")


def words(text: str) -> list[str] | None:
    """"a, b, and c" → the keywords, when every one is read."""
    found = [w.strip() for w in re.split(r", and |, | and ", text) if w.strip()]
    return found if found and len(set(found)) == len(found) and set(found) <= WORDS else None


def bind(body: str, it: str | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The effects of a keyword soup sentence pair (scripts._parse_effects_plain), or None."""
    if (m := _GRANT.match(body.strip())) is not None:
        ks = words(", ".join([m["k"], m["ks"]]))
        who = m["who"].lower()
        you = selectors.parse("creature you control")
        src = selectors.parse(_SRC[m["src"]])
        if ks is None or you is None or src is None or (who == "it" and it != "self"):
            return None
        return [{"do": "keyword_soup", "mode": "grant", "keywords": ks, "from": src.key(),
                 "who": you.key() if who == "creatures you control" else "self"}], None, False
    if (m := _PUMP.match(body.strip())) is not None:
        ks = words(", ".join([m["k"], m["k2"], m["ks"]]))
        other = selectors.parse("other creature you control")
        return None if ks is None or other is None else ([{"do": "keyword_soup", "mode": "pump", "keywords": ks, "who": other.key()}], None, False)
    if (m := _COUNTERS.match(body.strip())) is not None:  # Kathril, Aspect Warper
        from app.game.rules_state import KEYWORD_COUNTERS

        ks, you, gy = words(", ".join([m["k"], m["ks"]])), selectors.parse("creature you control"), selectors.parse("creature card in your graveyard")
        if ks is None or you is None or gy is None or not set(ks) <= KEYWORD_COUNTERS:
            return None
        return [{"do": "keyword_soup", "mode": "counters", "keywords": ks, "from": gy.key(), "who": you.key()}], None, False
    return None


def _matches(word: str, name: str, text: str) -> bool:
    if word == "partner":  # (Akroma's ruling: not "Partner—Character select", "Partner—Friends forever")
        return bool(re.fullmatch(r"partner(?: with .+)?", text.lower()))
    return name == word or (word == "hexproof" and name == "hexproof from") or (word == "landwalk" and name.endswith("walk"))


def lines(plan: Plan, card: CardInstance, ks: list[str]) -> dict[str, dict[str, bool]]:
    """The abilities ``card`` has among ``ks``: word → {the ability as written → whether it is the plain keyword (granted as a keyword, not a line)}."""
    ch = plan.ch(card)
    found: dict[str, dict[str, bool]] = {}
    for ab in ch.abilities:  # (a face-down permanent's characteristics are the face-down ones: 708.2, ``characteristics.of``)
        if ab.kind != "keywords":
            continue
        pieces = oracle.keyword_pieces(ab.text) if len(ab.keywords) > 1 else [ab.text]
        if len(pieces) != len(ab.keywords):  # (a line whose pieces can't be told apart: not read)
            continue
        for name, piece in zip(ab.keywords, pieces, strict=True):
            for w in ks:
                if name in ch.keywords and _matches(w, name, piece.strip()):
                    found.setdefault(w, {})[piece.strip(" .")] = piece.strip(" .").lower() == name
    for name in ch.granted & ch.keywords:  # (a keyword granted by a static or an effect: no line)
        for w in ks:
            if _matches(w, name, name):
                found.setdefault(w, {})[name] = True
    return found


def soup(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects, layers

    holders = [plan.state.cards[c] for c in effects._cards(plan, ctx, e.get("from") or e["who"])]
    if e["mode"] == "grant":
        got: dict[str, tuple[str, bool]] = {}  # (several creatures with an ability are the one ability)
        for holder in holders:
            for found in lines(plan, holder, e["keywords"]).values():
                for text, plain in found.items():
                    got[text.lower()] = (text, plain or got.get(text.lower(), ("", False))[1])
        if got:  # (a plain keyword is granted as one, the rest as the lines they are)
            effects.grant(plan, ctx, {"do": "grant", "who": e["who"], "keywords": [k for k, (_, plain) in got.items() if plain],
                                      "abilities": [t for t, plain in got.values() if not plain]})
        return True
    if e["mode"] == "counters":
        return _counters(plan, ctx, e, holders)
    if e["mode"] == "put":
        return _put(plan, ctx, e)
    if e["mode"] == "tally":  # "Then put a +1/+1 counter on Kathril for each counter put on a creature this way": the counters of those kinds the creatures have gained since
        n = _kinds(plan, ctx, e["who"], e["kinds"]) - ctx.pop("soup_before", 0)
        _splice(ctx, [{"do": "add_counters", "who": "self", "kind": "+1/+1", "n": n}] if n > 0 else [])
        return True
    groups: dict[int, list[str]] = {}  # the bonus is the number of listed abilities each has, counted now (611.2c)
    for card in holders:
        if n := len(lines(plan, card, e["keywords"])):
            groups.setdefault(n, []).append(card.id)
    for n, ids in sorted(groups.items()):
        layers.add_effect(plan, affected=[plan.oid(c) for c in ids], layer="7c", source=ctx.get("source_object"), controller=ctx["controller"], power=n,
                          toughness=n, duration="end_of_turn", label=f"+{n}/+{n} until end of turn ({ctx.get('name', '')})")
        effects._mark(plan, ids, f"+{n}/+{n}")
    return True


def count(plan: Plan, ctx: Context, key: str, ks: list[str]) -> int:
    """"the number of abilities from among … found among <creatures>": the listed abilities any of them has (Odric, Blood-Cursed's ruling)."""
    found: set[str] = set()
    for c in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], ctx.get("source_card")):
        found |= set(lines(plan, plan.state.cards[c], ks))
    return len(found)


# -- Kathril, Aspect Warper: "put a flying counter on any creature you control if a creature card in your graveyard has flying. Repeat this process for …" ---------------------
def _splice(ctx: Context, new: list[dict[str, Any]]) -> None:
    i = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:i], *new, *ctx["effects"][i:]]


def _kinds(plan: Plan, ctx: Context, who: str, kinds: list[str]) -> int:
    from app.rules import effects

    return sum(plan.state.cards[c].counters.get(k, 0) for c in effects._cards(plan, ctx, who) for k in kinds)


def _counters(plan: Plan, ctx: Context, e: dict[str, Any], holders: list[CardInstance]) -> bool:
    """One check for each keyword (the graveyard as the ability resolves): a counter of that kind on a creature of the controller's choice (122.1b; not a target), then the
    +1/+1 counters for the number put. A variant ("hexproof from white", 702.11d) would be a counter of its own kind, which the engine doesn't model: resolved by hand."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    todo = []
    for w in e["keywords"]:
        got = {t: p for h in holders for t, p in lines(plan, h, [w]).get(w, {}).items()}
        if not all(got.values()):
            decide(plan, player=ctx["controller"], kind="manual_resolution", options=[DecisionOption(id="done", label="Done")],
                   prompt=f"{ctx.get('name') or 'It'}: a creature card in your graveyard has a variant of {w} (702.11d), whose counter isn't automated. Put the counters and the "
                          "+1/+1 counters by hand, then press Done", resume={"step": "room_by_hand", "ctx": ctx})
            return False
        todo += [w] * bool(got)
    if todo:
        ctx["soup_before"] = _kinds(plan, ctx, e["who"], todo)
        _splice(ctx, [*({"do": "keyword_soup", "mode": "put", "kind": w, "who": e["who"]} for w in todo),
                      {"do": "keyword_soup", "mode": "tally", "kinds": todo, "who": e["who"]}])
    return True


def _put(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    mine = effects._cards(plan, ctx, e["who"])
    if len(mine) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: put a {e['kind']} counter on which creature?",
               options=[DecisionOption(id=c, label=plan.ch(plan.state.cards[c]).name) for c in mine], resume={"step": "keyword_soup", "ctx": ctx, "e": e})
        return False
    _splice(ctx, [{"do": "add_counters", "who": f"obj:{plan.oid(mine[0])}", "kind": e["kind"], "n": 1}] if mine else [])
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if len(chosen) != 1 or chosen[0] not in effects._cards(plan, ctx, e["who"]):
        raise ActionError("Choose one of your creatures")
    plan.note(f"{plan.name(d.player)} puts a {e['kind']} counter on {plan.ch(plan.state.cards[chosen[0]]).name}", actor=d.player)
    _splice(ctx, [{"do": "add_counters", "who": f"obj:{plan.oid(chosen[0])}", "kind": e["kind"], "n": 1}])
    effects.continue_effects(plan, ctx)
