"""Cost changers (wave 4I): "costs {N} less / more", per count, with a condition, of the chosen type …

Rules (stored Comprehensive Rules, 2026-09-25):

* 601.2f — the total cost is the mana cost or an alternative cost, plus additional costs and cost
  increases, minus cost reductions (in any order the player likes); the mana part can't go below
  {0}; once determined it is "locked in" and later changes have no effect. 602.2b: the same for an
  activated ability, its activation cost standing for the mana cost ("This ability costs {1} less
  to activate for each legendary creature you control").
* 118.7a — a reduction by generic mana touches only the generic component. 118.7b/c — a reduction
  by colored mana takes that color's symbols away; what it can't take away (the cost has fewer
  symbols of that color) reduces the generic component instead ("costs {G} less for each green
  creature you control").
* 107.3a / 601.2b — X is announced before the total cost is determined; the amounts here are read
  as the total cost is determined (601.2f), so "for each creature you control" counts the table at
  that moment.

Everything here is a closed grammar read into data (``parse_change``); an unknown wording returns
None and the line stays manual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.rules import conditions, values
from app.rules import mana as M

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.plan import Plan

Change = dict[str, Any]

_SYMBOL = r"\{(?P<n>\d+|X|[WUBRG])\}"
# "~'s power" / "this creature's power" ("this creature" is written ~ already: scripts.self_text)
_SELF_STAT = re.compile(r"^~'s (?P<stat>power|toughness)$")
_REST = re.compile(r"^(?:(?P<each> for each (?P<what>.+))|(?P<if> if (?P<cond>.+))|(?P<long> as long as (?P<cond2>.+))"
                   r"|(?P<turn> during your turn)|(?P<x>, where X is (?P<v>.+)))?$")


def _value(phrase: str) -> values.Value | None:
    """A quantity a cost change reads: "the total power of creatures you control", "~'s power"."""
    m = _SELF_STAT.fullmatch(phrase.strip())
    if m:
        return {m["stat"]: "self"}
    found = values.parse_count(phrase, it="self")
    if isinstance(found, dict) and ({"x", "event_amount", "ref_amount", "event_count", "kicked", "colors_spent"} & set(found)
                                    or "hand" in found and found["hand"] not in ("you",) or "life" in found and found["life"] == "target"):
        return None  # (nothing here has an X, a trigger event, targets or a payment to read)
    return found


def parse_change(symbol: str, direction: str, rest: str) -> Change | None:
    """The change a cost-changing sentence makes, from its parts: ``symbol`` ("1", "X", "G"), ``direction``
    ("less" / "more") and the rest of the sentence after "to cast" / "to activate" ("" / " for each …" /
    " if …" / " as long as …" / " during your turn" / ", where X is …"). None when it isn't read."""
    m = _REST.fullmatch(rest.rstrip("."))
    if m is None:
        return None
    out: Change = {"dir": -1 if direction == "less" else 1}
    if symbol == "X":
        if not m["x"]:
            return None
        v = _value(m["v"])
        if v is None:
            return None
        out["value"] = v
        return out
    if m["x"]:
        return None
    if symbol.isdigit():
        out["n"] = int(symbol)
    else:
        out["n"], out["mana"] = 1, symbol  # (118.7b/c: a colored amount)
    if m["each"]:
        v = _value(m["what"])
        if v is None:
            return None
        out["value"] = v
    cond_text = m["cond"] or m["cond2"]
    if cond_text:
        cond = conditions.parse(cond_text)
        if cond is None or "succeeded" in cond:
            return None
        out["cond"] = cond
    if m["turn"]:
        out["cond"] = {"turn": "yours"}
    return out


def amount(view: Plan, ctx: dict[str, Any], change: Change) -> int:
    """How much the change takes off (or adds), unsigned, read now (601.2f); 0 when its condition fails."""
    if change.get("cond") is not None and not conditions.holds(view, ctx, change["cond"]):
        return 0
    if "value" in change:
        return int(change.get("n", 1)) * values.evaluate(view, ctx, change["value"])
    return int(change.get("n", 0))


def context(state: GameState, player: str, source: CardInstance) -> dict[str, Any]:
    r = state.rules
    return {"controller": player, "source_card": source.id,
            "source_object": r.object_id(source.id) if r is not None else None}


def on_stack(state: GameState, card: CardInstance) -> GameState:
    """The table as 601.2f reads it for a spell being cast: 601.2a has moved the card onto the stack already, so a
    count of "cards in your graveyard" / "in your hand" doesn't include the spell itself (a shallow probe, never kept)."""
    from app.game.state import STACK

    if card.zone == STACK or card.id not in state.cards:
        return state
    zones = {k: [c for c in v if c != card.id] if k == card.zone else v for k, v in state.zones.items()}
    zones[STACK] = [*state.zones.get(STACK, []), card.id]
    return state.model_copy(update={"cards": {**state.cards, card.id: card.model_copy(update={"zone": STACK})}, "zones": zones})


def view_of(state: GameState, player: str, info: CardInfo) -> Plan:
    from app.rules.plan import Plan

    return Plan.view(state, player, info)


# -- activated abilities: "This ability costs {1} less to activate for each …" (602.2b → 601.2f) ----------------------
ABILITY_SENTENCE = re.compile(rf"^This ability costs {_SYMBOL} (?P<dir>less|more) to activate(?P<rest>.*?)\.?$")


def split_ability(body: str) -> tuple[str, str | None]:
    """An activated ability's effect text without its "This ability costs …" sentence, and that sentence (or None)."""
    from app.rules.oracle import split_sentences

    sentences = split_sentences(body.strip())
    found = [s for s in sentences if s.startswith("This ability costs ")]
    if len(found) != 1:
        return body, None
    return " ".join(s for s in sentences if s is not found[0]), found[0]


def ability_change(text: str) -> Change | None:
    """The change an activated ability's own "This ability costs …" sentence makes (``text``: the ability's whole
    text, its name written as ~), {} when it has none, None when it has one this grammar doesn't read."""
    body = text.split(":", 1)[1] if ":" in text else text
    _, sentence = split_ability(body)
    if sentence is None:
        return {}
    m = ABILITY_SENTENCE.fullmatch(sentence.strip())
    if m is None or m["n"] in "WUBRG":
        return None  # (a colored change to an activation cost isn't printed on any card the grammar was checked with)
    return parse_change(m["n"], m["dir"], m["rest"])


def ability_delta(state: GameState, player: str, card: CardInstance, ch: Characteristics, text: str, info: CardInfo) -> int:
    """The signed generic change the ability's own sentence makes now (−N: costs {N} less)."""
    from app.rules.scripts import self_text

    change = ability_change(self_text(text, ch.name or ""))
    if not change:
        return 0
    return change["dir"] * amount(view_of(state, player, info), context(state, player, card), change)


# -- spells: their own "This spell costs …" and the table's "<spells> cost …" -----------------------------------------
SELF_SENTENCE = re.compile(rf"^(?:this spell|~) costs {_SYMBOL} (?P<dir>less|more) to cast(?P<rest>.*)$")


_SELF_IF_FIRST = re.compile(rf"^if (?P<cond>[^,]+), (?P<rest>(?:this spell|~) costs {_SYMBOL} less to cast)$")


def is_self(t: str) -> bool:
    """Is this line the spell's own cost change ("This spell costs …", "If …, this spell costs {6} less to cast")?"""
    return bool(SELF_SENTENCE.fullmatch(t) or _SELF_IF_FIRST.fullmatch(t))


def self_change(t: str) -> Change | None:
    """"This spell costs {X} less to cast, where X is the total power of creatures you control." (Ghalta) → change.
    "If an opponent controls seven or more lands, this spell costs {6} less to cast." (Avatar of Fury) reads as the
    same sentence with its condition last."""
    first = _SELF_IF_FIRST.fullmatch(t)
    if first:
        t = f"{first['rest']} if {first['cond']}"
    m = SELF_SENTENCE.fullmatch(t)
    if m is None:
        return None
    return parse_change(m["n"], m["dir"], m["rest"])


@dataclass
class Changes:
    """What a spell's total cost gets from cost changers, besides the generic modifiers (601.2f)."""

    increase: int = 0
    reduction: int = 0
    colored_more: tuple[str, ...] = ()
    colored_less: tuple[str, ...] = ()

    def add(self, delta: int, mana: str | None) -> None:
        if mana:
            n = abs(delta)
            if delta > 0:
                self.colored_more += (mana,) * n
            else:
                self.colored_less += (mana,) * n
        elif delta > 0:
            self.increase += delta
        else:
            self.reduction -= delta


def own_changes(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo,
                definitions: dict[int, dict[str, Any]]) -> Changes:
    """The spell's own changes ("This spell costs {1} less to cast for each …"), read as its total cost is determined."""
    out = Changes()
    view = None
    for d in definitions.values():
        change = d.get("change") if d.get("static") == "self_cost" else None
        if not change:
            continue
        view = view or view_of(on_stack(state, card), player, info)
        n = amount(view, context(state, player, card), change)
        if n:
            out.add(change["dir"] * n, change.get("mana"))
    return out


def reduce_colored(cost: M.ManaCost, colors: tuple[str, ...]) -> M.ManaCost:
    """118.7b/c: each colored reduction takes one symbol of that color away; with none left, one generic."""
    colored = list(cost.colored)
    generic = cost.generic
    for c in colors:
        if c in colored:
            colored.remove(c)
        elif generic:
            generic -= 1
    return M.ManaCost(generic, tuple(colored), cost.hybrid, cost.phyrexian, cost.x, cost.unsupported)


def add_colored(cost: M.ManaCost, colors: tuple[str, ...]) -> M.ManaCost:
    return M.ManaCost(cost.generic, cost.colored + colors, cost.hybrid, cost.phyrexian, cost.x, cost.unsupported)


# -- the table's cost changers ---------------------------------------------------------------------------------------
# "Creature spells of the chosen type cost {2} less to cast." (Urza's Incubator) / "Each spell costs {3} more to cast
# except during its controller's turn." (Defense Grid) / "During turns other than yours, spells you cast cost {1} less
# to cast." (Geyser Drake) / "Creature spells you cast cost {1} less to cast for each +1/+1 counter on ~." (Animar) /
# "Instant and sorcery spells you cast cost {X} less to cast, where X is ~'s power." (Vadrik) / "White spells you cast
# cost {W} more to cast." (Alabaster Leech) / "Spells you cast from your graveyard cost {1} less to cast." (Gravebreaker
# Lamia) / "Spells your opponents cast from graveyards or from exile cost {2} more to cast." (Aven Interrupter)
_FROM = {"from your graveyard": ("your_graveyard",), "from graveyards": ("graveyard",), "from exile": ("exile",),
         "from your graveyard or from exile": ("your_graveyard", "exile"), "from graveyards or from exile": ("graveyard", "exile"),
         "from anywhere other than your hand": ("not_hand",)}
STATIC = re.compile(
    r"^(?P<during>during your turn, |during turns other than yours, )?(?:each )?(?:(?P<sel>[A-Za-z][A-Za-z' ,-]*?) )?spells? "
    r"(?:(?P<with>with (?:flying|flash)) )?(?P<who>you cast |your opponents cast )?(?P<chosen>of the chosen type )?"
    r"(?:(?P<from>from (?:your graveyard or from exile|graveyards or from exile|your graveyard|graveyards|exile"
    r"|anywhere other than your hand)) )?"
    rf"costs? {_SYMBOL} (?P<dir>less|more) to cast(?P<rest>.*)$")
_EXCEPT = " except during its controller's turn"
# "The first creature spell you cast each turn costs {2} less to cast." (Shadow in the Warp) / "The second spell you cast
# each turn costs {1} less to cast." (Raging Battle Mouse): read against this turn's casts (history.py, 601.2i)
ORDINAL = re.compile(rf"^the (?P<ord>first|second) (?:(?P<sel>[A-Za-z][A-Za-z' -]*?) )?spell you cast each turn costs {_SYMBOL} "
                     r"less to cast$")


def special(t: str) -> bool:
    """Is this a table cost changer with more than the plain "<spells> cost {N} less/more to cast" (which
    permissions.STATIC_COST reads)? Then :func:`static_definition` reads it or nothing does."""
    if ORDINAL.fullmatch(t) or TARGETING.fullmatch(t):
        return True
    m = STATIC.fullmatch(t)
    return m is not None and bool(m["during"] or m["with"] or m["chosen"] or m["from"] or m["rest"] or not m["n"].isdigit())


def static_definition(t: str, lines: tuple[str, ...]) -> dict[str, Any] | None:
    """A table cost changer the plain grammar (permissions.STATIC_COST) doesn't read, or None."""
    from app.rules.permissions import spell_filter

    t = re.sub(r"^(\w+) spells and (\w+) spells ", r"\1 or \2 spells ", t)
    o = ORDINAL.fullmatch(t)
    if o:
        return _ordinal_definition(o)
    tm = TARGETING.fullmatch(t)
    if tm:
        return _targeting_definition(tm)
    m = STATIC.fullmatch(t)
    if m is None:
        return None
    rest = m["rest"]
    turn = {"during your turn, ": "yours", "during turns other than yours, ": "not_yours", None: None}[m["during"]]
    if rest.endswith(_EXCEPT):
        if turn is not None:
            return None
        turn, rest = "not_caster", rest[: -len(_EXCEPT)]
    change = parse_change(m["n"], m["dir"], rest)
    if change is None or change.get("mana") and change.get("value"):
        return None
    # ("… as long as there are three or more Lesson cards in your graveyard": the static's condition, read with its
    # source's controller as "you" each time a total cost is determined: amount())
    # the chosen type is the permanent's "As ~ enters, choose a creature type." answer (614.12a): only with that line
    if m["chosen"] and not any(re.fullmatch(r"As .+ enters, choose a creature type\.?", x.strip()) for x in lines):
        return None
    sel = m["sel"]
    key = spell_filter(sel, m["with"]) if sel or m["with"] else None
    if (sel or m["with"]) and key is None:
        return None
    caster = {None: "any", "you cast ": "you", "your opponents cast ": "opponent"}[m["who"]]
    out: dict[str, Any] = {"kind": "static", "static": "cost_modifier", "delta": change["dir"] * int(change.get("n", 0)),
                           "caster": caster, "filter": key, "change": change, "effects": []}
    if m["chosen"]:
        # "of the chosen type": wave 4J's selector extra, read from the source permanent's own enters choice (614.12a;
        # scripts checks the card has exactly that one choice: chosen.chosen_value_ok). Kept as "spell", not "filter",
        # since only static_delta knows the source
        from dataclasses import replace

        from app.rules import selectors

        base = selectors.from_key(key) if key is not None else selectors.parse("spell")
        if base is None:
            return None
        out["spell"] = replace(base, extras=(*base.extras, "chosen_type")).key()
        out["filter"] = None
    if turn:
        out["turn"] = turn
    if m["from"]:
        out["from"] = list(_FROM[m["from"]])
    return out


# "Spells your opponents cast that target ~ cost {2} more to cast." (Charix) / "Spells you cast that target a creature cost
# {2} less to cast." (Killian) / "Spells your opponents cast that target a creature or planeswalker you control cost {2}
# more to cast." (Kasmina) / "Spells that target this creature cost {2} less to cast." (Spellwild Ouphe). 601.2c: the
# targets are chosen before the total cost is determined (601.2f), so the change reads them.
TARGETING = re.compile(rf"^spells (?P<who>you cast |your opponents cast )?that target (?P<what>[^.]+?) costs? {_SYMBOL} "
                       r"(?P<dir>less|more) to cast$")


def _targeting_definition(m: re.Match[str]) -> dict[str, Any] | None:
    from app.rules import selectors

    if not m["n"].isdigit():
        return None
    what = m["what"]
    if what == "~":
        target = "self"
    else:
        phrase = re.sub(r"^(?:a|an|one or more) ", "", what)
        sel = selectors.parse(phrase)
        if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.extras \
                or sel.attacking or sel.blocking or sel.other:
            return None
        target = sel.key()
    n = int(m["n"])
    sign = -1 if m["dir"] == "less" else 1
    caster = {None: "any", "you cast ": "you", "your opponents cast ": "opponent"}[m["who"]]
    return {"kind": "static", "static": "cost_modifier", "delta": sign * n, "caster": caster, "filter": None,
            "change": {"dir": sign, "n": n}, "target": target, "effects": []}


def _targets_match(state: GameState, info: CardInfo, src: CardInstance, target: str, targets: tuple[str, ...]) -> bool:
    """Does one of the spell's chosen targets fit "that target …"? ("~": the source itself; else a permanent, read
    relative to the source's controller: "a Merfolk you control" is one the changer's controller controls.)"""
    from app.rules import selectors

    view = None
    for tid in targets:
        card = state.cards.get(tid)
        if card is None or not card.zone.endswith(":battlefield"):
            continue
        if target == "self":
            if tid == src.id:
                return True
            continue
        view = view or view_of(state, src.controller, info)
        if selectors.matches(view, selectors.from_key(target), card, view.ch(card), src.controller, src.id):
            return True
    return False


def _ordinal_definition(o: re.Match[str]) -> dict[str, Any] | None:
    from app.rules import history, selectors
    from app.rules.permissions import spell_filter

    if not o["n"].isdigit():
        return None
    key = spell_filter(o["sel"]) if o["sel"] else None
    if o["sel"] and (key is None or not history.note_selector_ok(selectors.from_key(key))):
        return None  # (a kind of spell the turn's cast records can't answer: "kicked", "face-down", "with flying")
    if o["ord"] == "second" and key is not None:
        return None
    n = int(o["n"])
    return {"kind": "static", "static": "cost_modifier", "delta": -n, "caster": "you", "filter": key,
            "change": {"dir": -1, "n": n}, "ordinal": 1 if o["ord"] == "first" else 2, "effects": []}


def _ordinal_ok(state: GameState, info: CardInfo, player: str, d: dict[str, Any]) -> bool:
    """Is this the first such spell (none of its kind cast yet this turn) / the second spell (one cast so far)?"""
    from app.rules import history, selectors

    log = history.log_for(view_of(state, player, info))
    sel = selectors.from_key(d["filter"]) if d.get("filter") else None
    before = sum(1 for note in log.casts if note.player == player
                 and (sel is None or history.note_matches(sel, note.types, note.subtypes, note.supertypes, note.colors, note.mv)))
    return before == d["ordinal"] - 1


# -- review (Codex) -- the ``targets`` a castability hint passes for a spell that has targets: "spells that target …"
# reductions count and such increases don't, so a spell castable with some target is offered (the cast itself checks
# the real targets and refuses with nothing changed when it can't be paid).
ANY_TARGET: tuple[str, ...] = ("*any target*",)


def static_delta(state: GameState, info: CardInfo, src: CardInstance, d: dict[str, Any], player: str,
                 card: CardInstance, ch: Characteristics, targets: tuple[str, ...] = ()) -> int | None:
    """The signed change a table cost changer makes to this spell now, or None when it doesn't apply to it."""
    if "change" not in d:
        return int(d["delta"])
    if d.get("target"):
        if targets == ANY_TARGET:  # -- review (Codex) -- a castability hint, before targets: the best case
            if d["change"]["dir"] > 0:
                return None
        elif not _targets_match(state, info, src, d["target"], targets):
            return None
    if d.get("ordinal") and not _ordinal_ok(state, info, player, d):
        return None
    turn = d.get("turn")
    active = state.turn.active_player
    if turn == "yours" and active != src.controller or turn == "not_yours" and active == src.controller \
            or turn == "not_caster" and active == player:
        return None
    if d.get("spell"):  # "<spells> of the chosen type": the source's choice (selectors._chosen_ok; none recorded: no match)
        from app.game.state import STACK
        from app.rules import selectors

        probe = card.model_copy(update={"zone": STACK, "controller": player})
        if not selectors.matches(view_of(state, player, info), selectors.from_key(d["spell"]), probe, ch, player, src.id):
            return None
    zones = d.get("from")
    if zones:
        where = card.zone.rsplit(":", 1)[-1]  # (the zone it's cast from: 601.2a)
        if not (where in zones or "your_graveyard" in zones and card.zone == f"{player}:graveyard"
                or "not_hand" in zones and card.zone != f"{player}:hand"):
            return None
    n = amount(view_of(on_stack(state, card), src.controller, info), context(state, src.controller, src), d["change"])
    return d["change"]["dir"] * n if n else None


def stored_mana(d: dict[str, Any]) -> str:
    """The colored symbol a table changer adds or takes ("{W} more"), or ""."""
    return str((d.get("change") or {}).get("mana") or "")




# -- optional additional costs on other spells (Defiler of Vigor) ---------------------------------------------------
# "As an additional cost to cast green permanent spells, you may pay 2 life. Those spells cost {G} less to cast if you
# paid life this way. This effect reduces only the amount of green mana you pay." 601.2b: announced as the spell is
# cast (the intent's ``optional_costs`` names the permanents whose cost is paid); 601.2f: the reduction applies to
# that color's symbols only (never the generic part: the card says so, overriding 118.7c).
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
DEFILER = re.compile(
    r"^as an additional cost to cast (?P<color>white|blue|black|red|green) permanent spells, you may pay (?P<life>\d+) life\. "
    r"those spells cost \{(?P<sym>[WUBRG])\} less to cast if you paid life this way\. "
    r"this effect reduces only the amount of (?P<color2>white|blue|black|red|green) mana you pay$", re.IGNORECASE)


def optional_definition(t: str) -> dict[str, Any] | None:
    from app.rules.permissions import spell_filter

    m = DEFILER.fullmatch(t)
    if m is None or m["color"].lower() != m["color2"].lower() or _COLORS[m["color"].lower()] != m["sym"]:
        return None
    key = spell_filter(f"{m['color'].lower()} permanent")
    if key is None:
        return None
    return {"kind": "static", "static": "optional_additional", "life": int(m["life"]), "mana": m["sym"], "filter": key,
            "effects": []}


@dataclass(frozen=True)
class Optional:
    source: str
    label: str
    life: int
    mana: str
    kind: str = ""  # -- static_other sweep (wave 17C) -- "conspire" / "teamwork": a cost of tapped creatures (``n``: teamwork's power)
    n: int = 0


def keyword_component(o: Optional) -> Any:
    """-- static_other sweep (wave 17C) -- the cost part a keyword's optional cost is: conspire 702.78a ("tap two untapped creatures you
    control that each share a color with it") / teamwork 702.194a ("tap any number of creatures you control with total power N or
    more"), paid with the rest of the additional costs (601.2f-h) once the caster announced it (601.2b)."""
    from app.rules import costs as C
    from app.rules.selectors import Selector

    untapped = Selector(types=("Creature",), controller="you", tapped=False)
    if o.kind == "casualty":  # -- casting extras (wave 18E) -- 702.153a: "you may sacrifice a creature with power N or greater"
        key = C._selector(f"creature you control with power {o.n} or greater", zone="battlefield")
        return C.CostComponent(C.SACRIFICE, amount=1, selector=key, text=f"Sacrifice a creature with power {o.n} or greater")
    if o.kind == "conspire":
        key = Selector(types=("Creature",), controller="you", tapped=False, extras=("shares_color_source",)).key()
        return C.CostComponent(C.TAP_OTHER, amount=2, selector=key, text="Tap two untapped creatures you control that share a color with it")
    return C.CostComponent("TAP_POWER", amount=o.n, selector=untapped.key(),
                           text=f"Tap any number of untapped creatures you control with total power {o.n} or more")


def optional_offers(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo) -> list[Optional]:
    """The optional additional costs the table offers ``player`` for this spell (one per permanent)."""
    import re

    from app.rules import cast_limits, permissions

    out: list[Optional] = []
    for src, _, d in permissions._table_statics(state, info, {"optional_additional"}):
        if src.controller == player and permissions.spell_matches(state, player, card, ch, d["filter"], info):
            out.append(Optional(src.id, f"{src.name}: pay {d['life']} life", int(d["life"]), d["mana"]))
    # -- static_other sweep (wave 17C) -- conspire (its own, or given by a permanent) and teamwork N (702.78a, 702.194a)
    own = [ab.text.strip().rstrip(".") for ab in ch.abilities if ab.kind == "keywords"]
    if "Conspire" in own or any(d.get("keyword") == "conspire" and src.controller == player
                                and (d.get("filter") is None or permissions.spell_matches(state, player, card, ch, d["filter"], info))
                                and cast_limits.from_ok(d, card) for src, d in cast_limits._statics(state, info, "spell_keyword")):
        out.append(Optional(f"{card.id}:conspire", "Conspire: tap two untapped creatures that share a color with it", 0, "", "conspire"))
    for text in own:
        # -- casting extras (wave 18E) -- 702.153a casualty (one instance: 702.153b's several are refused)
        if (m := re.fullmatch(r"Casualty (\d+)", text)) is not None and sum(t.startswith("Casualty") for t in own) == 1:
            out.append(Optional(f"{card.id}:casualty", f"Casualty {m[1]}: sacrifice a creature with power {m[1]} or greater", 0, "",
                                "casualty", int(m[1])))
        if (m := re.fullmatch(r"Teamwork (\d+)", text)) is not None:
            out.append(Optional(f"{card.id}:teamwork", f"Teamwork {m[1]}: tap creatures with total power {m[1]} or more", 0, "", "teamwork",
                                int(m[1])))
    return out


def chosen_optional(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo,
                    ids: list[str]) -> list[Optional]:
    """The optional costs the intent names, each checked now (601.2b), or an ActionError."""
    from app.game.errors import ActionError

    if len(set(ids)) != len(ids):
        raise ActionError("Name each optional cost once")
    offers = {o.source: o for o in optional_offers(state, player, card, ch, info)}
    out = []
    for sid in ids:
        if sid not in offers:
            raise ActionError("That optional additional cost doesn't apply to this spell")
        out.append(offers[sid])
    return out


def reduce_only(cost: M.ManaCost, colors: tuple[str, ...]) -> M.ManaCost:
    """Take one symbol of each color away, never anything else ("reduces only the amount of green mana you pay"). A
    hybrid or Phyrexian symbol of that color isn't read (which part the player pays isn't known yet): refused."""
    from app.game.errors import ActionError

    colored = list(cost.colored)
    for c in (x for x in colors if x):  # (wave 17C: a keyword's optional cost reduces no color)
        if any(c in h for h in cost.hybrid) or c in cost.phyrexian:
            raise ActionError("A hybrid or Phyrexian mana symbol with that reduction: pay it by hand with the table tools")
        if c in colored:
            colored.remove(c)
    return M.ManaCost(cost.generic, tuple(colored), cost.hybrid, cost.phyrexian, cost.x, cost.unsupported)
