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
# (-- cant restrictions (wave 46A) -- several colored symbols for a table changer: "cost {W}{U}{B}{R}{G} less" (Morophon, the Boundless), 118.7b/c, one reduction each: ``n`` is "W}{U}{B}{R}{G")
_SYMBOLS = r"\{(?P<n>\d+|X|[WUBRG](?:\}\{[WUBRG])*)\}"
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
    # -- cost self reduction (wave 21F) -- Valiant Changeling: "This effect can't reduce the amount of mana this spell costs by more than {5}."
    capped = re.fullmatch(r"(?P<rest>.*?)\. [Tt]his effect can't reduce the amount of mana this spell costs by more than \{(?P<cap>\d+)\}\.?", rest)
    if capped is not None:
        rest = capped["rest"]
    # -- cant restrictions (wave 46A) -- "This effect reduces only the amount of colored mana you pay." (Morophon, Edgewalker): a colored reduction that never spills over
    # into the generic part of the cost (it replaces the reading of 118.7b/c for that changer)
    only = re.fullmatch(r"(?P<rest>.*?)\. [Tt]his effect reduces only the amount of colored mana you pay\.?", rest)
    if only is not None:
        if direction != "less" or symbol.isdigit() or symbol == "X":
            return None
        rest = only["rest"]
    m = _REST.fullmatch(rest.rstrip("."))
    if m is None:
        return None
    out: Change = {"dir": -1 if direction == "less" else 1, **({"cap": int(capped["cap"])} if capped and direction == "less" else {})}
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
        out["n"], out["mana"] = 1, ("!" if only is not None else "") + "".join(symbol.split("}{"))  # (118.7b/c: a colored amount; "!": only colored, wave 46A)
    if m["each"]:
        v = _value(m["what"])
        if v is None:
            return None
        out["value"] = v
    cond_text = m["cond"] or m["cond2"]
    if cond_text and cond_text.startswith("it targets "):  # -- casting costs (wave 22F) -- 601.2f: read once the targets are chosen
        from app.rules import selectors

        sel = selectors.parse(re.sub(r"^(?:a|an) ", "", cond_text[len("it targets "):]))
        if sel is None or sel.player is not None or m["x"] or m["each"] or m["long"]:
            return None
        out["targets"] = sel.key()
        return out
    if cond_text:
        cond = conditions.parse(cond_text, objects=True)  # (wave 20E: "as long as ~ is tapped": the source itself)
        if cond is None or "succeeded" in cond or set(conditions.objects_in(cond)) - {"self"}:
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
    found = parse_change(m["n"], m["dir"], m["rest"])
    return None if found and found.get("targets") else found  # (wave 22F: an ability's cost isn't read against its targets yet)


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
    colored_only: tuple[str, ...] = ()  # (wave 46A: reductions of colored mana that don't spill over into the generic part)

    def add(self, delta: int, mana: str | None) -> None:
        if mana:
            n = abs(delta)
            if delta > 0:
                self.colored_more += tuple(mana) * n
            elif mana[0] == "!":
                self.colored_only += tuple(mana[1:]) * n
            else:
                self.colored_less += tuple(mana) * n
        elif delta > 0:
            self.increase += delta
        else:
            self.reduction -= delta


def targets_fit(view: Plan, card: CardInstance, player: str, key: str, targets: tuple[str, ...]) -> bool:
    """-- casting costs (wave 22F) -- "if it targets a tapped creature": does one of the chosen targets fit (read relative to the
    caster, 601.2f)? Before targets exist (ANY_TARGET, a castability hint) a reduction counts and an increase doesn't."""
    from app.rules import selectors

    sel = selectors.from_key(key)
    return any((t := view.state.cards.get(tid)) is not None and selectors.matches(view, sel, t, view.ch(t), player, card.id)
               for tid in targets)


def own_changes(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo,
                definitions: dict[int, dict[str, Any]], targets: tuple[str, ...] = ()) -> Changes:
    """The spell's own changes ("This spell costs {1} less to cast for each …"), read as its total cost is determined."""
    out = Changes()
    view = None
    for d in definitions.values():
        change = d.get("change") if d.get("static") == "self_cost" else None
        if not change:
            continue
        view = view or view_of(on_stack(state, card), player, info)
        if change.get("targets") and ((targets == ANY_TARGET and change["dir"] > 0) or (
                targets != ANY_TARGET and not targets_fit(view, card, player, change["targets"], targets))):
            continue  # "… if it targets …": the chosen targets (601.2c comes before 601.2f)
        n = amount(view, context(state, player, card), change)
        n = min(n, change["cap"]) if "cap" in change else n
        if n:
            out.add(change["dir"] * n, change.get("mana"))
    return out


def reduce_colored(cost: M.ManaCost, colors: tuple[str, ...], only: bool = False) -> M.ManaCost:
    """118.7b/c: each colored reduction takes one symbol of that color away; with none left, one generic (``only``: "reduces only the amount
    of colored mana you pay", wave 46A: nothing more)."""
    colored = list(cost.colored)
    generic = cost.generic
    for c in colors:
        if c in colored:
            colored.remove(c)
        elif generic and not only:
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
    r"(?:(?P<chosen1>of the chosen type) )?"  # (wave 46A: "Spells of the chosen type you cast cost …", Morophon)
    r"(?:(?P<with>with (?:flying|flash|mana value \d+ or (?:greater|less))) )?(?P<who>you cast |your opponents cast )?(?:(?P<with2>with (?:mana value \d+ or (?:greater|less)|toughness greater than its power)) )?(?P<own>but don't own )?(?P<chosen>of the chosen type )?"
    r"(?:(?P<from>from (?:your graveyard or from exile|graveyards or from exile|your graveyard|graveyards|exile"
    r"|anywhere other than your hand)) )?"
    rf"costs? {_SYMBOLS} (?P<dir>less|more) to cast(?P<rest>.*)$")
_EXCEPT = " except during its controller's turn"
# "The first creature spell you cast each turn costs {2} less to cast." (Shadow in the Warp) / "The second spell you cast
# each turn costs {1} less to cast." (Raging Battle Mouse): read against this turn's casts (history.py, 601.2i)
# -- spell grants (wave 30T) -- "… costs {2} less to cast and can be cast as though it had flash." (Radagast of Rhosgobel): the first one's flash too
# -- cost changers (wave 44D) -- "The first spell you cast with {X} in its mana cost each turn costs {1} less to cast for each +1/+1 counter on ~." (Zimone, Infinite Analyst): the
# turn's cast records say whether a spell had {X} in its mana cost (history.CastNote.x_cost)
# (-- cant restrictions (wave 46A) -- "The first non-Lemur creature spell with flying you cast during each of your turns costs {1} less to cast." (Momo, Friendly Flier): a keyword
# the spell had as it was cast, and only the turns of the source's controller)
ORDINAL = re.compile(rf"^the (?P<ord>first|second) (?:(?P<sel>[A-Za-z][A-Za-z' -]*?) )?spell(?P<kw> with (?:flying|flash|haste|trample|vigilance|reach|menace|deathtouch|lifelink|first strike))? you cast"
                     rf"(?P<xc> with \{{X\}} in its mana cost)?(?P<when> each turn| during each of your turns) costs {_SYMBOL} "
                     r"less to cast(?P<each> for each [^.]+?)?(?P<flash> and can be cast as though it had flash)?$")


# -- casting costs (wave 22F) -- Damping Sphere: "Each spell a player casts costs {1} more to cast for each other spell that player has cast this
# turn." — the count is the caster's own (601.2f reads the turn's record, which doesn't include the spell being cast: 601.2i)
PER_CASTER = re.compile(rf"^each spell a player casts costs {_SYMBOL} more to cast for each other spell that player has cast this turn$")


def special(t: str) -> bool:
    """Is this a table cost changer with more than the plain "<spells> cost {N} less/more to cast" (which
    permissions.STATIC_COST reads)? Then :func:`static_definition` reads it or nothing does."""
    if ORDINAL.fullmatch(t) or TARGETING.fullmatch(t) or TARGETING_LIFE.fullmatch(t) or PER_CASTER.fullmatch(t):
        return True
    m = STATIC.fullmatch(t)
    return m is not None and bool(m["during"] or m["with"] or m["with2"] or m["chosen"] or m["chosen1"] or m["from"] or m["rest"] or m["own"] or not m["n"].isdigit())


def static_definition(t: str, lines: tuple[str, ...]) -> dict[str, Any] | None:
    """A table cost changer the plain grammar (permissions.STATIC_COST) doesn't read, or None."""
    from app.rules.permissions import spell_filter

    t = re.sub(r"^(\w+) spells and (\w+) spells ", r"\1 or \2 spells ", t)
    o = ORDINAL.fullmatch(t)
    if o:
        return _ordinal_definition(o)
    if (pc := PER_CASTER.fullmatch(t)) is not None and pc["n"].isdigit():
        return {"kind": "static", "static": "cost_modifier", "delta": int(pc["n"]), "caster": "any", "filter": None,
                "change": {"dir": 1, "n": int(pc["n"]), "per_caster": True}, "effects": []}
    tm = TARGETING.fullmatch(t) or TARGETING_LIFE.fullmatch(t)
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
    if change is None:  # (-- cant restrictions (wave 46A) -- a colored amount per count is read too: Eluge, 118.7b/c)
        return None
    # ("… as long as there are three or more Lesson cards in your graveyard": the static's condition, read with its
    # source's controller as "you" each time a total cost is determined: amount())
    # the chosen type is the permanent's "As ~ enters, choose a creature type." answer (614.12a): only with that line
    card_type = (m["chosen"] or m["chosen1"]) and any(re.fullmatch(r"As .+ enters, choose (?:a card type(?: other than creature or land)?|artifact, creature, enchantment, instant, or sorcery)\.?", x.strip()) for x in lines)  # (wave 47A: Umori, Stenn)
    if (m["chosen"] or m["chosen1"]) and not card_type and not any(re.fullmatch(r"As .+ enters, choose a creature type\.?", x.strip()) for x in lines):
        return None
    sel = m["sel"]
    if card_type and (sel or m["with"] or m["with2"]):
        return None  # ("creature spells of the chosen type" with a card type chosen: the type words would be the chosen one's and another's)
    with_ = m["with"] or m["with2"]  # (-- cost changers (wave 44D) -- "Instant and sorcery spells you cast with mana value 4 or greater cost {X} less …", The Scarlet Witch)
    key = spell_filter(sel, with_) if sel or with_ else None
    if (sel or with_) and key is None:
        return None
    caster = {None: "any", "you cast ": "you", "your opponents cast ": "opponent"}[m["who"]]
    out: dict[str, Any] = {"kind": "static", "static": "cost_modifier", "delta": change["dir"] * int(change.get("n", 0)),
                           "caster": caster, "filter": key, "change": change, "effects": []}
    if m["own"]:  # -- cost changers (wave 20E) -- "Spells you cast but don't own" (Gonti): the spell's owner is another player (108.3)
        if m["who"] != "you cast ":
            return None
        from dataclasses import replace as _replace

        from app.rules import selectors as _sel

        base = _sel.from_key(key) if key is not None else _sel.parse("spell")
        if base is None:
            return None
        out["filter"] = _replace(base, owner="opponent").key()
    if m["chosen"] or m["chosen1"]:
        # "of the chosen type": wave 4J's selector extra, read from the source permanent's own enters choice (614.12a;
        # scripts checks the card has exactly that one choice: chosen.chosen_value_ok). Kept as "spell", not "filter",
        # since only static_delta knows the source
        from dataclasses import replace

        from app.rules import selectors

        base = selectors.from_key(key) if key is not None else selectors.parse("spell")
        if base is None:
            return None
        out["spell"] = replace(base, extras=(*base.extras, "chosen_card_type" if card_type else "chosen_type")).key()
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


# -- casting costs (wave 22F) -- "Spells your opponents cast that target this creature cost an additional 3 life to cast." (Terror of the Peaks):
# an additional cost (118.8) chosen by the targets (601.2c), paid with the rest (601.2h) — life can be paid only up to the life total (119.4)
TARGETING_LIFE = re.compile(r"^spells (?P<who>you cast |your opponents cast )?that target (?P<what>[^.]+?) cost an additional (?P<life>\d+) life to cast$")


def _targeting_definition(m: re.Match[str]) -> dict[str, Any] | None:
    if "life" in m.groupdict():
        d = _targeting_definition_of(m["who"], m["what"])
        return {**d, "delta": 0, "change": {"dir": 1, "n": 0}, "life": int(m["life"])} if d is not None else None
    if not m["n"].isdigit():
        return None
    d = _targeting_definition_of(m["who"], m["what"])
    if d is None:
        return None
    n = int(m["n"])
    sign = -1 if m["dir"] == "less" else 1
    return {**d, "delta": sign * n, "change": {"dir": sign, "n": n}}


def _targeting_definition_of(who: str | None, what: str) -> dict[str, Any] | None:
    from app.rules import selectors

    you = what.startswith("you or ")  # -- most-played cards III (wave 46C) -- "Spells your opponents cast that target you or a permanent you control cost {2} more to cast." (Monastery Siege): the player is a target too
    if you:
        what = what[len("you or "):]
    if what == "~":
        target = "self"
    else:
        phrase = re.sub(r"^(?:a|an|one or more) ", "", what)
        sel = selectors.parse(phrase)
        if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.extras \
                or sel.attacking or sel.blocking or sel.other:
            return None
        target = sel.key()
    caster = {None: "any", "you cast ": "you", "your opponents cast ": "opponent"}[who]
    return {"kind": "static", "static": "cost_modifier", "caster": caster, "filter": None, "target": target, "effects": [], **({"target_you": True} if you else {})}


def targeting_life(state: GameState, player: str, card: CardInstance, ch: Characteristics, info: CardInfo,
                   targets: tuple[str, ...]) -> int:
    """-- casting costs (wave 22F) -- the life the table adds to this spell's cost because of its targets (Terror of the Peaks)."""
    from app.rules import permissions

    total = 0
    for src, _, d in permissions._table_statics(state, info, {"cost_modifier"}):
        if not d.get("life") or (d["caster"] == "you" and src.controller != player) or (d["caster"] == "opponent" and src.controller == player):
            continue
        if targets != ANY_TARGET and _targets_match(state, info, src, d["target"], targets, d.get("target_you", False)):
            total += int(d["life"])
    return total


def _targets_match(state: GameState, info: CardInfo, src: CardInstance, target: str, targets: tuple[str, ...], you: bool = False) -> bool:
    """Does one of the spell's chosen targets fit "that target …"? ("~": the source itself; else a permanent, read
    relative to the source's controller: "a Merfolk you control" is one the changer's controller controls; ``you``: or the changer's controller, a player.)"""
    from app.rules import selectors

    view = None
    for tid in targets:
        if you and tid == src.controller:
            return True
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

    if o["xc"] and o["kw"]:
        return None
    tail = "with {X} in its mana cost" if o["xc"] else o["kw"].strip() if o["kw"] else None
    key = spell_filter(o["sel"], tail) if o["sel"] or tail else None
    if (o["sel"] or tail) and (key is None or not history.note_selector_ok(selectors.from_key(key), spell=True, kept=True)):
        return None  # (a kind of spell the turn's cast records can't answer: "kicked", "face-down", "with flying")
    if o["ord"] == "second" and key is not None:
        return None
    n = int(o["n"]) if o["n"].isdigit() else 1  # (wave 46A: a colored symbol, "{U} less for each …", Eluge)
    if o["flash"] and o["ord"] != "first":
        return None
    change = parse_change(o["n"], "less", o["each"] or "")
    if change is None:
        return None
    from app.rules import cast_limits

    return {"kind": "static", "static": "cost_modifier", "delta": -n, "caster": "you", "filter": key,
            "change": change, "ordinal": 1 if o["ord"] == "first" else 2, "effects": [], **({"turn": "yours"} if o["when"] != " each turn" else {}),
            **({"flash_perm": cast_limits.flash_def(key, first=True)} if o["flash"] else {})}  # (read by permissions.grants: 601.3b)


def _ordinal_ok(state: GameState, info: CardInfo, player: str, d: dict[str, Any]) -> bool:
    """Is this the first such spell (none of its kind cast yet this turn) / the second spell (one cast so far)?"""
    from app.rules import history, selectors

    log = history.log_for(view_of(state, player, info))
    sel = selectors.from_key(d["filter"]) if d.get("filter") else None
    before = sum(1 for note in log.casts if note.player == player
                 and (sel is None or history.note_matches(sel, note.types, note.subtypes, note.supertypes, note.colors, note.mv, x_cost=note.x_cost,
                                                              keywords=note.keywords, face_down=note.face_down)))
    return before == d["ordinal"] - 1


def first_ok(state: GameState, info: CardInfo, player: str, key: str | None) -> bool:
    """-- spell grants (wave 30T) -- "the first <kind> spell you cast each turn": none of that kind (None: any spell) cast by ``player`` earlier
    this turn — the whole turn's casts count, whenever the source arrived (Radagast of Rhosgobel's rulings, 2026-06-29), 601.2i."""
    return _ordinal_ok(state, info, player, {"filter": key, "ordinal": 1})


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
        elif not _targets_match(state, info, src, d["target"], targets, d.get("target_you", False)):
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
    if d["change"].get("per_caster"):  # -- casting costs (wave 22F) -- the spells this caster has cast so far this turn
        from app.rules import history

        log = history.log_for(view_of(state, player, info))
        n = int(d["change"]["n"]) * sum(1 for note in log.casts if note.player == player)
        return d["change"]["dir"] * n if n else None
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


# -- casting costs (wave 22F) -- 601.2b: "As an additional cost to cast this spell, you may collect evidence 6." (701.59a) / "… you may behold a
# Dragon." (701.4a): the caster announces it with the other optional costs and pays it with the rest (601.2h); the spell's own "if evidence
# was collected" / "if a Dragon was beheld" read the record of that choice (conditions._cast_how)
OWN_OPTIONAL = re.compile(r"^as an additional cost to cast this spell, you may (?P<cost>collect evidence \d+|behold an? [A-Z][a-z]+)\.?(?: \(.*\))?$")


def own_cost(text: str) -> Any:
    """The one cost part "Collect evidence 6" / "Behold a Dragon" is (None when the grammar can't pay it)."""
    from app.rules import costs as C

    parsed = C.parse_ability_cost(text) if text.startswith("Collect") else C.parse_additional_cost(text)
    return parsed.components[0] if parsed is not None and not parsed.unsupported and len(parsed.components) == 1 else None


def optional_definition(t: str) -> dict[str, Any] | None:
    from app.rules.permissions import spell_filter

    if (own := OWN_OPTIONAL.fullmatch(t)) is not None:
        text = own["cost"][0].upper() + own["cost"][1:]
        parsed = own_cost(text)
        if parsed is None:
            return None
        kind = "evidence" if text.startswith("Collect") else "behold"
        return {"kind": "static", "static": "own_optional", "optional": kind, "cost": text, "effects": []}
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
    text: str = ""  # -- casting costs (wave 22F) -- "evidence" / "behold": the cost part as the cost grammar reads it ("Collect evidence 6")


def keyword_component(o: Optional) -> Any:
    """-- static_other sweep (wave 17C) -- the cost part a keyword's optional cost is: conspire 702.78a ("tap two untapped creatures you
    control that each share a color with it") / teamwork 702.194a ("tap any number of creatures you control with total power N or
    more"), paid with the rest of the additional costs (601.2f-h) once the caster announced it (601.2b)."""
    from app.rules import costs as C
    from app.rules.selectors import Selector

    untapped = Selector(types=("Creature",), controller="you", tapped=False)
    if o.kind == "gift":  # -- gift (wave 23D) -- choosing the opponent costs nothing (702.174a)
        return None
    if o.kind == "bargain":  # -- keywords (wave 30E) -- 702.166a: "you may sacrifice an artifact, enchantment, or token" (you control, 701.21a)
        either = tuple(Selector(controller="you", **kw).key() for kw in ({"types": ("Artifact",)}, {"types": ("Enchantment",)}, {"token": True}))
        return C.CostComponent(C.SACRIFICE, amount=1, selector=Selector(either=either).key(), text="Sacrifice an artifact, enchantment, or token")
    if o.kind in ("evidence", "behold"):  # -- casting costs (wave 22F) --
        return own_cost(o.text)
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
    # -- casting extras (wave 18E) -- 702.153a casualty (one instance: 702.153b's several are refused); -- spell grants (wave 30T) -- its own or one a
    # static gives it as it is cast ("The first instant or sorcery spell you cast each turn has casualty 2.": the spell isn't counted yet, 601.2i)
    casualty = [int(m[1]) for t in own if (m := re.fullmatch(r"Casualty (\d+)", t)) is not None]
    if len(casualty) == sum(t.startswith("Casualty") for t in own):
        if not casualty:  # (a spell with casualty of its own keeps that one: a second instance, 702.153b, isn't offered)
            casualty = [int(d["n"]) for src, d in cast_limits._statics(state, info, "spell_keyword")
                        if d.get("keyword") == "casualty" and src.controller == player and cast_limits.from_ok(d, card, state, info, player)
                        and (d.get("filter") is None or permissions.spell_matches(state, player, card, ch, d["filter"], info))]
        if len(casualty) == 1:
            out.append(Optional(f"{card.id}:casualty", f"Casualty {casualty[0]}: sacrifice a creature with power {casualty[0]} or greater", 0, "",
                                "casualty", casualty[0]))
    for text in own:
        if text == "Bargain":  # -- keywords (wave 30E) -- 702.166a-b: an optional additional cost; "bargained" is the intent to pay it
            out.append(Optional(f"{card.id}:bargain", "Bargain: sacrifice an artifact, enchantment, or token", 0, "", "bargain"))
        if (m := re.fullmatch(r"Teamwork (\d+)", text)) is not None:
            out.append(Optional(f"{card.id}:teamwork", f"Teamwork {m[1]}: tap creatures with total power {m[1]} or more", 0, "", "teamwork",
                                int(m[1])))
    from app.rules import gift

    if gift.offered(ch):  # -- gift (wave 23D) -- 702.174a: "As an additional cost to cast this spell, you may choose an opponent."
        out.append(Optional(f"{card.id}:gift", "Gift: promise an opponent a gift", 0, "", "gift"))
    for d in permissions._definitions(ch).values():  # -- casting costs (wave 22F) -- collect evidence / behold on the spell itself
        if d.get("static") == "own_optional":
            out.append(Optional(f"{card.id}:{d['optional']}", f"{d['cost']} (additional cost)", 0, "", d["optional"], text=d["cost"]))
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
        if any(c in h for h in cost.hybrid) or any(c in p.split("/") for p in cost.phyrexian):
            raise ActionError("A hybrid or Phyrexian mana symbol with that reduction: pay it by hand with the table tools")
        if c in colored:
            colored.remove(c)
    return M.ManaCost(cost.generic, tuple(colored), cost.hybrid, cost.phyrexian, cost.x, cost.unsupported)
