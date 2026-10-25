"""-- chosen player (wave 4J) -- the player a permanent's "As ~ enters, choose an opponent / a player" chose
(614.12a: the choice is made as it enters and belongs to that object; 400.7: a new object has no such choice).
Researched against CR 2026-09-25.

The choice is recorded twice: the permanent's public ``choices`` entry ("Chosen opponent: Bob", the display, which a
player may also edit by hand) and ``RulesState.chosen_players`` (object id -> player id, what the rules read). A
reading is trusted only while both agree; a save from before the id was kept has only the display name, resolved when
exactly one player has that name. Anything else reads as no chosen player (the ability does nothing automatically).

Read by: step triggers "At the beginning of the chosen player's upkeep" (Black Vise, The Rack; triggers._whose_step),
and the effect subject "the chosen player" (``who: "chosen_player"``, effects._players).

-- chosen filters (wave 53B) -- a chosen value used as a filter, for every kind of value (creature type, color, card type, basic land type, number, card name):
* State: none new beyond the permanent's public ``choices`` entries ("Chosen color / creature type / card type / basic land type / second basic land type / number / card name",
  614.12a; a second one per extra answer) and, for an in-resolution choice, the instructions after it (bind_effects rewrites the selector extras ``chosen_*`` into the answer,
  608.2c-d). ``RulesState.permissions`` gets a ``nth`` default (None) for "the next spell of the chosen type".
* Who is asked: the controller, publicly (a choice of a value is never hidden: 614.12a, 201.4); a card name is typed (card_names.FREE_TEXT) or, where the text restricts it, picked
  from the revealed nonland cards (Alhammarret). Looking at a hand (Arachne) shows the cards only in the chooser's own decision (701.20e), as ``group="seen"`` options that are
  not answers.
* Where it is used: ``chosen_value_ok`` accepts a definition only if every use has its choice (one entering choice of that kind for the source's own abilities and statics, or
  exactly one earlier choice of the same resolution); anything else stays manual. ``rewrite`` turns "of that color / type", "that many", "the number" after a Choose sentence
  into "the chosen …". ``retag`` reads the ambiguous "of the chosen type" as a card type or a basic land type where that is the one choice there is.
* Hidden information: names, types, colors and numbers are public; a hand is revealed to everyone only when the text says "reveals" (Alhammarret, Darigaaz, Brain Pry); "looks at"
  stays private.
* Rules: 608.2c-d (instructions in order, choices on resolution), 614.12a (as it enters), 201.4 (names), 205.2a / 205.3m (types), 105.1 (colors), 107.1b-c (numbers), 305.7 and
  613.1d-e (land types, colors), 601.2f (costs), 702.16 (protection), 702.11d (hexproof from), 705.2 (several flips), 709.4a (names).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

LABELS = ("Chosen opponent", "Chosen player")  # effects.CHOICE_LABELS for "opponent" / "player"
WHO = "chosen_player"


def chooses_player(ch: Characteristics) -> bool:
    """Whether the object has exactly one "As ~ enters, choose an opponent / a player." (what "the chosen player" in
    its other abilities names)."""
    from app.rules.language import ENTERS_CHOICE
    from app.rules.scripts import self_text

    found = [m for ab in ch.abilities if (m := ENTERS_CHOICE.match(self_text(ab.text, ch.name))) is not None]
    from app.rules import keyed_player_bindings

    return (len(found) == 1 and found[0]["what"] in ("opponent", "player", "color and an opponent")) or (not found and keyed_player_bindings.remembers_combat(ch))


# -- chosen type (wave 4J) ------------------------------------------------------------------------------------------
# "of the chosen type / color" (selectors.CHOSEN_EXTRAS) names one of two choices:
# * the source permanent's "As ~ enters, choose a creature type / a color." (614.12a) — read by selectors.matches from
#   the source's record. Only where the source is the permanent itself: its statics' affected objects (layers), its
#   trigger conditions, its targets and its resolving instructions; never inside a counted value (a static's count
#   is evaluated for another object) and never on a card without that one enters choice.
# * a "Choose a creature type." instruction earlier in the same resolution (Kindred Dominance, Bloodline Bidding) —
#   bind_effects puts the answer into the instructions after it as the choice is made (effects.resume_choose_value).
RULE_PREFIX = "cant_be_blocked_by:"
_CHOSEN_COLOR_LINE = re.compile(r"(?:Protection|Hexproof) from the chosen color")
_SOURCE_KEYS = frozenset({"who", "sel", "spell", "obj", "what", "source"})  # (wave 43A: "source": a trigger multiplier's sources — Roaming Throne, read against its own choice)


def split_key(node: str) -> tuple[str, str] | None:
    """(head, selector key) of a string that is a selector key, alone or after the group head of a "controlled:target|sel:…" / "them:graveyard|sel:…" reference."""
    from app.rules import selectors

    if node.startswith(selectors.PREFIX):
        return "", node
    head, bar, rest = node.partition("|")
    return (head + bar, rest) if bar and rest.startswith(selectors.PREFIX) and re.fullmatch(r"[a-z_]+(?::[\w.-]+)?", head) else None


def _uses(node: Any, key: str = "") -> list[tuple[str, str]]:
    """(the JSON key, "creature type" / "color") for every selector in the definition that reads a chosen value."""
    from app.rules import selectors

    if isinstance(node, dict):
        return ([(key, "number")] if CHOSEN_N in node else []) + [u for k, v in node.items() for u in _uses(v, k)]  # (wave 53B: the chosen number as an amount)
    if isinstance(node, list):
        return [u for v in node for u in _uses(v, key)]
    if isinstance(node, str) and node.startswith(RULE_PREFIX):  # -- chosen type (wave 50J) -- "can't be blocked by creatures of the chosen color": the rule carries the selector
        node = node[len(RULE_PREFIX):]
    if isinstance(node, str) and "chosen_" in node and (split := split_key(node)) is not None:  # (wave 53B: "controlled:target|sel:…")
        sel = selectors.from_key(split[1])
        what = selectors.chosen_what(sel)
        return [(key, what or "?")] if any(e in selectors.CHOSEN_EXTRAS for e in sel.extras) else []
    return []


# -- chosen filters (wave 53B) -- "When this land enters, choose a land card name." (Petrified Hamlet): a trigger, so the name is chosen as it resolves (608.2d), not as it enters; the
# permanent keeps it (its public choice, 607.2a: the statics after it are linked to it), as an entering choice would be
NAME_TRIGGER = re.compile(r"^When ~ enters, choose (?:a|an) (?P<what>(?:non)?(?:land|artifact|creature|enchantment|instant|sorcery|planeswalker|basic)? ?card name)\.$")


def remember_name(d: dict[str, Any] | None, text: str) -> dict[str, Any] | None:
    """The definition of a lone "When ~ enters, choose a … card name." trigger with the answer recorded on the permanent (effects.resume_choose_value ``remember``)."""
    effects = d.get("effects") if d is not None else None
    if d is None or d.get("kind") != "triggered" or NAME_TRIGGER.match(text) is None or not effects or len(effects) != 1 or effects[0].get("do") != "choose_value":
        return d
    return {**d, "effects": [{**effects[0], "remember": True}]}


def _enters_choices(ch: Characteristics) -> list[str]:
    from app.rules import (
        card_names,  # -- card names (wave 22B) -- "As ~ enters, choose a card name." counts as a card name choice
    )
    from app.rules.language import ENTERS_CHOICE
    from app.rules.scripts import self_text

    texts = [choice_head(self_text(ab.text, ch.name)) for ab in ch.abilities]  # (wave 53B: a line that also puts counters on it)
    named = [e["what"] for t in texts if (d := card_names.enters_choice(t)) is not None for e in d["effects"] if card_names.is_choice(e["what"])]
    named += [m["what"] for t in texts if (m := NAME_TRIGGER.match(t)) is not None]  # (wave 53B: "When ~ enters, choose a land card name." — recorded on the permanent as the trigger resolves, Petrified Hamlet)
    pairs = [k for t in texts if (m := ENTERS_CHOICE.match(t)) is not None and re.fullmatch(PAIRS, m["what"]) for k in ("color", "creature type")]  # (wave 53B: Sarpadian Empires)
    pairs += [k for t in texts if (m := ENTERS_CHOICE.match(t)) is not None and m["what"] == "two basic land types" for k in ("basic land type", "second basic land type")]  # (Illusionary Terrain)
    singles = ["card type" if m["what"].startswith("card type") or type_choice(m["what"]) is not None else "number" if m["what"].startswith("number") else "abilities" if m["what"].startswith("two abilities") else "basic land type" if re.fullmatch(r"\w+ or \w+", m["what"]) and m["what"][:1].isupper() else "creature type" if m["what"][:1].isupper() else m["what"] for t in texts if (m := ENTERS_CHOICE.match(t)) is not None and m["what"] not in ("color and a creature type", "color and an opponent", "two basic land types", "two colors") and not re.fullmatch(PAIRS, m["what"])]
    both = [k for t in texts if (m := ENTERS_CHOICE.match(t)) is not None and m["what"] == "color and a creature type" for k in ("color", "creature type")]  # (wave 53B: "choose a color and a creature type")
    both += [k for t in texts if (m := ENTERS_CHOICE.match(t)) is not None and m["what"] == "color and an opponent" for k in ("color", "opponent")]
    typed = ["card type" for ab in ch.abilities if self_text(ab.text, ch.name) == "As ~ enters, look at an opponent's hand, then choose a card type other than creature."]  # (wave 53B: Arachne)
    color_pairs = ["color pair" for t in texts if (m := ENTERS_CHOICE.match(t)) is not None and m["what"] == "two colors"]
    return singles + both + pairs + typed + color_pairs + ["card name" for _ in named] \
        + (["creature type"] if any(ab.text == "As an additional cost to cast this spell, choose a creature type." for ab in ch.abilities) else [])  # (wave 110E: Caller of the Hunt)  # (wave 47A: the card type choices, Umori, Stenn, Cloud Key)


def _kind(what: str | None) -> str | None:
    from app.rules import (
        card_names,  # -- card names (wave 22B) -- every "… card name" choice is the one "card name" value
    )

    return "card name" if card_names.is_choice(what) else what


def _reflexives(d: dict[str, Any]) -> list[dict[str, Any]]:
    return [e["ability"] for e in d.get("effects") or [] if e.get("do") == "reflexive" and isinstance(e.get("ability"), dict)]


def chosen_value_ok(d: dict[str, Any], ch: Characteristics) -> bool:
    """Whether every "of the chosen type / color" in this definition names a choice the engine knows (see above)."""
    from app.rules import color_comparisons

    if not color_comparisons.linked_ok(d, ch):
        return False
    if nested := _reflexives(d):  # -- chosen filters (wave 53B) -- 603.12: the reflexive ability is its own run of instructions ("When you do, choose a nonland card name, then …")
        outer = {**d, "effects": [{k: v for k, v in e.items() if k != "ability"} if e.get("do") == "reflexive" else e for e in d["effects"]]}
        return chosen_value_ok(outer, ch) and all(chosen_value_ok(n, ch) for n in nested)
    if d.get("modes"):  # -- chosen filters (wave 53B) -- 700.2: each mode is its own run of instructions (a choice made in a mode serves that mode only)
        rest = {k: v for k, v in d.items() if k != "modes"}
        return chosen_value_ok(rest, ch) and all(chosen_value_ok({"kind": d.get("kind"), **m}, ch) for m in d["modes"])
    if d.get("chosen_type") and _enters_choices(ch).count("basic land type" if d["chosen_type"] == "land" else "creature type") != 1:
        return False  # (wave 11E: "~ is the chosen type in addition to its other types" needs that one choice)

    if d.get("chosen_color") and _enters_choices(ch).count("color") != 1:
        return False  # (wave 53B: "All nonland permanents are the chosen color." needs that one choice, Shifting Sky)
    marked = json.dumps(d)
    if (MARK_LAND in marked and _enters_choices(ch).count("basic land type") != 1) or (MARK_COLOR in marked and _enters_choices(ch).count("color") != 1) \
            or (MARK_LAND2 in marked and _enters_choices(ch).count("second basic land type") != 1):
        return False  # (wave 53B: "Enchanted land is the chosen type / color.", "This creature is the chosen color." need that one choice)

    if d.get("chosen_keywords") and _enters_choices(ch).count("abilities") != 1:
        return False  # (wave 49B: "Humans you control have each of the chosen abilities." needs that one choice, Greymond)

    if d.get("counters"):  # -- chosen filters (wave 53B) -- "enters with a counter for each creature you control of the chosen type": counted with the answer of the same line
        return all(w == d["counters_choice"] for _, w in _uses(d["counters"]))
    dumped = json.dumps(d)
    if '"source_choice_color": true' in dumped and (d.get("kind") == "spell" or _enters_choices(ch).count("color") != 1):
        return False
    if any(isinstance(e.get("token"), dict) and e["token"].get("chosen") for e in d.get("effects") or []):  # -- chosen filters (wave 53B) -- "a token of the chosen color and type": the source's own entering choices of both
        return d.get("kind") in ("activated", "triggered") and {"color", "creature type"} <= set(_enters_choices(ch)) and _enters_choices(ch).count("color") == 1 and _enters_choices(ch).count("creature type") == 1
    for line, (kind, _) in PROTECTION.items():  # -- attached events (wave 25D) -- an Aura's static: its own enters choice (wave 53B: a card type, a creature type)
        if line in dumped and d.get("static") == "grant":
            return _enters_choices(ch).count(kind) == 1
    if _CHOSEN_COLOR_LINE.search(dumped):  # -- chosen type (wave 20E) -- only in the instructions after a "Choose a color." of this resolution (wave 50J: and hexproof from it)
        effects = d.get("effects") or []
        picks = [i for i, e in enumerate(effects) if e.get("do") == "choose_value" and e.get("what") == "color" and not e.get("remember")]
        if len(picks) != 1 or any(_CHOSEN_COLOR_LINE.search(json.dumps(e)) for e in effects[: picks[0]]) \
                or _CHOSEN_COLOR_LINE.search(json.dumps({k: v for k, v in d.items() if k != "effects"})):
            return False
    if ('"hand": "chosen"' in dumped or '\\"controller\\":\\"chosen\\"' in dumped or '\\"zone_owner\\":\\"chosen\\"' in dumped) \
            and not chooses_player(ch):
        return False  # (wave 16F: "the chosen player" needs the one "As ~ enters, choose an opponent / a player.")
    if '"chosen_color": true' in dumped:  # -- prevention riders (wave 17A) -- "sources of the chosen color": this permanent's own choice
        return d.get("kind") != "spell" and _enters_choices(ch).count("color") == 1
    if '"chosen_name": true' in dumped:  # -- chosen filters (wave 53B) -- "sources with the chosen name": this permanent's own choice
        return d.get("kind") != "spell" and _enters_choices(ch).count("card name") == 1
    uses = _uses(d)
    if not uses:
        return True
    effects = d.get("effects") or []
    for what in {w for _, w in uses}:
        if what == "?":
            return False
        inside = [i for i, e in enumerate(effects) if e.get("do") in ("choose_value", "gc_choose") and _kind(e.get("what")) == what
                  and not e.get("remember")]  # (wave 53D: gc_choose, every player's choice)
        if inside:  # a choice made as it resolves: only in the instructions after it
            if len(inside) != 1 or what in _enters_choices(ch):
                return False
            rest = {k: v for k, v in d.items() if k != "effects"}
            if any(w == what for _, w in _uses(rest)) or any(w == what for _, w in _uses(effects[:inside[0]])):
                return False
            continue
        if d.get("kind") == "spell" or _enters_choices(ch).count(what) != 1:
            return False
        counted = d.get("kind") in ("triggered", "activated") or d.get("static") == "cda"  # -- chosen filters (wave 53B) -- a count of an ability or a characteristic-defining ability is read for its own permanent (the source), not for each object a static modifies
        if any(w == what and k not in _SOURCE_KEYS and not (k == "filter" and d.get("static") in ("cast_limit", "ability_cost_modifier")) and not (counted and k in ("count", "of")) for k, w in uses):  # (wave 22B)
            return False
    return True


def bind_effects(effects: list[dict[str, Any]], what: str, value: str) -> list[dict[str, Any]]:
    """The instructions with "of the chosen <what>" replaced by the answer just given (``value``)."""
    from app.rules import selectors

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if what == "number" and set(node) == {CHOSEN_N} and value.isdigit():
                return int(value)  # -- chosen filters (wave 53B) -- "that many": the number just chosen
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str) and node.startswith(RULE_PREFIX) and "chosen_" in node:  # (wave 50J: a restriction's rule carries its selector)
            return RULE_PREFIX + walk(node[len(RULE_PREFIX):])
        if isinstance(node, str) and "chosen_" in node and (split := split_key(node)) is not None:
            sel = selectors.from_key(split[1])
            if selectors.chosen_what(sel) == what and (bound := selectors.bind_chosen(sel, value)) is not None:
                return split[0] + bound.key()
        if node == "Protection from the chosen color" and what == "color":  # (wave 20E: protection_grants.CHOSEN_LINE)
            return f"Protection from {value.lower()}"
        if node == "Hexproof from the chosen color" and what == "color":  # (wave 50J: protection_grants.CHOSEN_HEXPROOF)
            return f"Hexproof from {value.lower()}"
        return node

    return [walk(e) for e in effects]
# -- end chosen type (wave 4J) --------------------------------------------------------------------------------------


def record(plan: Plan, card_id: str, player: str) -> None:
    """Remember the player this object chose (its object id now)."""
    r = plan.rules
    on_field = {plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith(":battlefield")}
    r.chosen_players = {oid: p for oid, p in r.chosen_players.items() if oid in on_field or oid in r.lki}  # (400.7)
    r.chosen_players[plan.oid(card_id)] = player


def _shown(card: CardInstance) -> str | None:
    found = [card.choices[k] for k in LABELS if card.choices.get(k)]
    return found[0] if len(found) == 1 else None


def player_of(plan: Plan, card_id: str, object_id: str | None = None) -> str | None:
    """The player the object chose, or None. ``object_id``: the object asked about (default: what the card is now);
    once it has left the battlefield, its recorded choice as it last existed (608.2h)."""
    card = plan.state.cards.get(card_id)
    oid = object_id or (plan.oid(card_id) if card is not None else "")
    pid = plan.rules.chosen_players.get(oid)
    current = card is not None and plan.oid(card) == oid and card.zone.endswith(":battlefield")
    if not current:
        return pid if pid in plan.state.players else None
    assert card is not None
    shown = _shown(card)
    if shown is None:
        return None
    if pid is not None:
        return pid if pid in plan.state.players and plan.state.players[pid].name == shown else None
    named = [p for p, player in plan.state.players.items() if player.name == shown]  # (an older save: a name only)
    return named[0] if len(named) == 1 else None


# -- linked words (wave 33B) --------------------------------------------------------------------------------------------
# 607.2f: "As this enchantment enters, choose Khans or Dragons." is a choice between words that have no rules meaning; the abilities
# printed after it ("• Khans — …", ``AbilityText.linked``, app/rules/oracle.py) are linked to it and each refers only to a choice involving
# its own word. The choice is made as it enters (614.12a), by its controller, and belongs to that object (400.7): ``RulesState.chosen_words``
# (object id -> word, what the rules read; ``copying.with_level`` puts it in ``Characteristics.word``) and the permanent's public ``choices``
# entry ("Chosen word: Khans", the display). An object with no recorded word has none of the linked abilities (a token copy is asked as it enters, wave 34A:
# replacements.token_choices; one made by a site that can't pause is left to the players, copying.token_copy).
WORDS = "word: "  # the entering choice's name: "word: Khans or Dragons"
WORD_LABEL = "Chosen word"
ENTERS_WORDS = re.compile(r"^As ~ enters, choose (?P<a>[A-Z][\w'’-]*) or (?P<b>[A-Z][\w'’-]*)\.$")


def words_header(text: str, ch: Characteristics) -> dict[str, Any] | None:
    """The entering choice of "As ~ enters, choose A or B." when the object has exactly one linked ability for each word."""
    m = ENTERS_WORDS.match(text)
    if m is None or sorted(a.linked for a in ch.abilities if a.linked) != sorted((m["a"], m["b"])):
        return None
    return {"kind": "replacement", "replacement": "enters_choice",
            "effects": [{"do": "choose_value", "who": "you", "what": f"{WORDS}{m['a']} or {m['b']}", "remember": True}]}


def words(what: str) -> list[str] | None:
    return what[len(WORDS):].split(" or ") if what.startswith(WORDS) else None


def record_word(plan: Plan, card_id: str, word: str) -> None:
    """Remember the word this object chose (its object id now)."""
    r = plan.rules
    on_field = {plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith(":battlefield")}
    r.chosen_words = {oid: w for oid, w in r.chosen_words.items() if oid in on_field or oid in r.lki}  # (400.7)
    r.chosen_words[plan.oid(card_id)] = word


# -- chosen filters (wave 53B) ---------------------------------------------------------------------------------------------
# A value chosen as the ability resolves ("Choose a color / a creature type / a card type / artifact, creature, or land / a
# number / a card name.", 608.2c-d: the instruction is reached, the chooser answers, public) and then used as the filter of the
# instructions after it ("all cards of the chosen type revealed this way", "discards all cards of that color", "creatures with power
# greater than or equal to the chosen number"). State: none beyond the answer, which ``bind_effects`` writes into the selectors after
# the choice (a resolution is one run; nothing is kept). Chooser: the controller (or the target player, "Target player chooses a card
# name"); the answer is public. A choice listing its own words ("artifact, creature, or land") offers only those; a permanent type
# is the six permanent card types (205.2a). All card-type family choices are the one value "card type"; the grammar's "of the chosen
# type" is a creature type unless the choice that goes with it is a card type (``retag``, 205.3m vs 205.2a).
_TYPE_WORD = "artifact|battle|creature|enchantment|instant|kindred|land|planeswalker|sorcery"
TYPE_CHOICE = rf"(?:card type|permanent type|(?:{_TYPE_WORD})(?:, (?:{_TYPE_WORD}))*,? or (?:{_TYPE_WORD}))"
# -- chosen filters (wave 53B) -- "As ~ enters, choose white Citizen, blue Camarid, black Thrull, red Goblin, or green Saproling." (Sarpadian Empires, Vol. VII): one answer that is both a
# color and a creature type, each its own public record ("Chosen color", "Chosen creature type"), 614.12a
_PAIR = r"(?:white|blue|black|red|green) [A-Z][a-z]+"
PAIRS = rf"{_PAIR}(?:, {_PAIR})*,? or {_PAIR}"
PAIR_WHAT = "color and creature type pair"
PERMANENT_TYPES = ["Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"]  # 205.2a


def type_choice(text: str) -> dict[str, Any] | None:
    """The ``choose_value`` instruction for "card type" / "permanent type" / "artifact, creature, or land" (None: not one of them)."""
    if text == "card type":
        return {"do": "choose_value", "who": "you", "what": "card type"}
    if text == "permanent type":
        return {"do": "choose_value", "who": "you", "what": "card type", "options": PERMANENT_TYPES}
    if re.fullmatch(TYPE_CHOICE, text):
        return {"do": "choose_value", "who": "you", "what": "card type", "options": [w.capitalize() for w in re.findall(_TYPE_WORD, text)]}
    return None


# A number: "Choose a number." (any number 107.1b-c; ponytail: offered 0-40, as X is, casting.py), "a number between 0 and 10", "a number greater than 0".
NUMBER_CHOICE = r"number(?: between \d+ and \d+| greater than \d+)?"
CHOSEN_N = "chosen_n"  # the placeholder of the chosen number in an amount ({"chosen_n": 1}) and a comparison (selectors.compare), written in by bind_effects
NUMBER_TOP = 40


def number_choice(text: str) -> dict[str, Any] | None:
    """The ``choose_value`` instruction for "number" / "number between 0 and 10" / "number greater than 0" (None: not one of them)."""
    m = re.fullmatch(r"number(?: between (?P<lo>\d+) and (?P<hi>\d+)| greater than (?P<gt>\d+))?", text)
    if m is None:
        return None
    lo, hi = (int(m["lo"]), int(m["hi"])) if m["lo"] else (int(m["gt"]) + 1, NUMBER_TOP) if m["gt"] else (0, NUMBER_TOP)
    return {"do": "choose_value", "who": "you", "what": "number", "options": [str(n) for n in range(lo, max(lo, hi) + 1)]}


def _walk_keys(node: Any, fn: Any, skip: str | None = None) -> Any:
    if isinstance(node, dict):
        return {k: v if k == skip else _walk_keys(v, fn, skip) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk_keys(v, fn, skip) for v in node]
    return fn(node) if isinstance(node, str) else node


def retag(d: dict[str, Any], ch: Characteristics) -> dict[str, Any]:
    """"of the chosen type" is read as a creature type; where the one choice it can mean is a card type (an earlier "Choose a card type."
    of the resolution, or the object's one "As ~ enters, choose a card type"), it is the card type (205.2a)."""
    if _reflexives(d):  # (a reflexive ability on its own; the rest of this one below)
        d = {**d, "effects": [{**e, "ability": retag(e["ability"], ch)} if e.get("do") == "reflexive" and isinstance(e.get("ability"), dict) else e for e in d["effects"]]}
    if d.get("modes"):  # (each mode on its own: the choice of one mode isn't the other modes')
        return {**d, "modes": [{k: v for k, v in retag({**m, "kind": d.get("kind")}, ch).items() if k in m} for m in d["modes"]]}
    effects = d.get("effects") or []
    picks = {_kind(e.get("what")) for e in effects if e.get("do") == "choose_value" and not e.get("remember")} | set(_enters_choices(ch))
    if "card type" in picks and not picks & {"creature type", "basic land type", "land type"}:
        kind = "card"
    elif "basic land type" in picks and not picks & {"creature type", "card type", "land type"}:
        kind = "land"  # (wave 53B: "a land of the chosen type", Roots of Life)
    elif "land type" in picks and not picks & {"creature type", "card type", "basic land type"}:
        kind = "any_land"
    else:
        return d
    return _walk_keys(d, lambda s: s.replace('"chosen_type"', f'"chosen_{kind}_type"').replace('"not_chosen_type"', f'"not_chosen_{kind}_type"') if "chosen_type" in s else s, skip="ability")  # (a reflexive ability was read on its own)


_CHOOSE_SENTENCE = re.compile(rf"(?:^|(?<=\. ))(?:[Yy]ou may )?[Cc]hoose (?:an? )?(?P<what>color|creature type|{TYPE_CHOICE}|{NUMBER_CHOICE})\.")
_CHOOSE_THEN = re.compile(rf"(?:^|(?<=\. ))(?P<c>[Cc])hoose (?:an? )?(?P<what>{TYPE_CHOICE}), then (?P<r>\w)")
_THAT = re.compile(r"\b(?:of their choice )?of that (color|type)\b")  # ("sacrifices a permanent of their choice of that type": the permanent they choose is of the chosen type)


def rewrite(body: str) -> str:
    """"Choose a card type, then reveal …" is two sentences; after a "Choose a color / creature type / card type." sentence, "of that color /
    type" is "of the chosen color / type" (the value just chosen: 608.2c)."""
    body = re.sub(r"(, then c|(?<=\. )C|^C)hoose a color\. ((?:This [a-z]+|~) becomes) the chosen color\b",  # (Puca's Eye: nothing comes between the choice and the change, so it is "the color of your choice")
                  lambda m: (". " if m[1].startswith(",") else "") + f"{m[2]} the color of your choice", body)
    body = _CHOOSE_THEN.sub(lambda m: f"{m['c']}hoose a {m['what']}. {m['r'].upper()}", body)
    body = re.sub(r"((?:If you do, )?)(that player reveals their hand) and (~ deals damage) to the player (equal to the number of [^.]* revealed this way)",
                  r"\1\2. \1\3 to that player \4", body)  # (Darigaaz: two instructions, one after the other, the second under the same "If you do")
    if (u := re.search(r"until you reveal (?:X|two|three|four|five|six|seven) (?P<sel>[a-z]+ cards? of the chosen (?:type|color))\b", body)) is not None:
        body = re.sub(r"\bPut those cards (onto|into) ", f"Put all {u['sel']} revealed this way \\1 ", body)  # (Kindred Summons: "those cards" are the matches the reveal stopped at)
    body = re.sub(r"(That player discards a card with (?:that|the chosen) name)\. If they can't, you draw a card", r"\1, and if they can't, you draw a card", body)
    if len(re.findall(r"[Tt]arget (?:player|opponent)", body)) == 1:  # "Search that player's graveyard, hand, and library …": the one player this spell targets (Thought Hemorrhage; name_search reads the target)
        body = body.replace("Search that player's graveyard, hand, and library for", "Search the targeted player's graveyard, hand, and library for")
    body = re.sub(r", and (you lose \w+ life) for each of the exiled cards", r". \1 for each card exiled this way", body)  # (Spoils of the Vault: the cards the exile before it moved)
    body = re.sub(r"(This creature gains hexproof from that color until end of turn) and (can't be blocked by creatures of that color this turn)", r"\1. This creature \2", body)  # (Sungold Sentinel: two instructions of the one creature)
    body = re.sub(r"\bput all of them with (?:that|the chosen) name into\b", "put all cards with the chosen name revealed this way into", body)  # (Desperate Research: the top seven just revealed)
    body = re.sub(r"\b(It gets) an additional (?=[+-]\d)", r"\1 ", body)  # (Growth Cycle: a second pump of the same creature, 611.2a: they add up)
    m = _CHOOSE_SENTENCE.search(body)
    if m is None:
        return body
    tail = _THAT.sub(r"of the chosen \1", body[m.end():])
    if m["what"] == "color":  # (wave 53B: "gains hexproof from that color until end of turn", Sungold Sentinel, Skrelv)
        tail = re.sub(r"\b(hexproof|protection) from that color\b", r"\1 from the chosen color", tail)
    if m["what"].startswith("number"):  # "that many creatures", "mana value equal to that number" / "to the number": the chosen number
        tail = re.sub(r"\b(?:that many|that number|the number(?! of\b))", "the chosen number", tail)
    return body[: m.end()] + tail


# Protection from a chosen quality, granted by a static ability (702.16a): the granted line names the quality, which the source's own entering choice fills in as the
# grant is applied (layers; the choice is public, 614.12a). A card type is protected from by its plural name (702.16a: "protection from artifacts"), a creature type as
# "creatures of that type" ("Elf creatures"); the line stays unwritten (no protection) when the source recorded no choice.
PROTECTION = {"Protection from the chosen player": ("player", "Chosen player"), "Protection from the chosen color": ("color", "Chosen color"), "Protection from the chosen card type": ("card type", "Chosen card type"),
              "Protection from creatures of the chosen type": ("creature type", "Chosen creature type")}


def protection_line(text: str, choices: dict[str, str], *, player_id: str | None = None) -> str | None:
    """"Protection from the chosen card type" + the source's choices → "Protection from creatures" (None: no usable choice)."""
    from app.rules import protection

    kind, label = PROTECTION[text]
    if kind == 'player':
        return f'Protection from player {player_id}' if player_id else None
    value = (choices.get(label) or "").strip()
    if kind == "color":
        return f"Protection from {value.lower()}" if value.lower() in protection.COLORS else None
    if kind == "card type":
        plural = next((k for k, v in protection.CARD_TYPES.items() if v == value), None)
        return f"Protection from {plural}" if plural else None
    return f"Protection from {value.lower()} creatures" if value else None


# "As ~ enters, choose a creature type. ~ enters with a fellowship counter on it for each creature you control of the chosen type." (Banner of Kinship): one entering
# replacement (614.12a, 614.1c): the choice first, then the counters, counted with the answer (replacements.entering_counters binds it).
_ENTERS_WITH = re.compile(r"^(?P<head>As ~ enters, choose (?:a|an) (?:creature type|color))\. (?P<tail>~ enters with .+)$")
_ENTERS_LIFE = re.compile(r"^(?P<head>As ~ enters, choose a basic land type)\. Then you may pay (?P<n>\d+) life\. If you don't, it enters tapped\.$")


def choice_head(text: str) -> str:
    """The "As ~ enters, choose …" sentence of an entering line, or the line as it is."""
    m = _ENTERS_WITH.match(text)
    if m is None:
        m = _ENTERS_LIFE.match(text)
    return m["head"] + "." if m else text


def enters_with_life(text: str) -> dict[str, Any] | None:
    from app.rules import language

    m = _ENTERS_LIFE.fullmatch(text)
    head = language.enters_choice(m['head'] + '.') if m else None
    return {**head, 'life': int(m['n']), 'pay_life_or_tapped': True} if head is not None and m else None


def enters_with_choice(text: str, define: Any) -> dict[str, Any] | None:
    """The entering replacement of the two-sentence line above (``define``: the reader of "~ enters with … counters"), or None."""
    from app.rules import language

    m = _ENTERS_WITH.match(text)
    head = language.enters_choice(m["head"] + ".") if m else None
    counters = define(m["tail"]) if m else None
    if head is None or counters is None or counters.get("replacement") != "enters_with_counters" or set(counters) - {"kind", "replacement", "counter", "n", "effects", "self_sels"}:
        return None
    return {**head, "counters": {k: v for k, v in counters.items() if k in ("counter", "n", "self_sels")}, "counters_choice": head["effects"][0]["what"]}


# "That player discards a card with that name. If they can't, you draw a card." (Brain Pry): one card of the revealed hand with the chosen name (701.9a: the discarding player picks it,
# and any of them is the same to the table); "if they can't" is when none is there (or a prohibition stops it, 614.17).
DISCARD_PATTERN = r"that player discards a card with (?:that|the chosen) name(?P<draw>, and if they can't, you draw a card)?"


def build_discard(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language, selectors

    sel = selectors.parse("card with the chosen name")
    if sel is None:
        raise language._Fail
    return [{"do": "discard_named", "who": "revealed", "sel": sel.key(), "n": 1, **({"else_draw": True} if m["draw"] else {})}], None


def chosen_token(plan: Plan, source: str | None, token: dict[str, Any]) -> dict[str, Any] | None:
    """The token spec of "a creature token of the chosen color and type" with the source's own answers written in (614.12a; 111.4: its name is its creature type), or None."""
    from app.rules import protection

    card = plan.state.cards.get(source or "")
    color = ((card.choices.get("Chosen color") if card is not None else "") or "").strip().lower()
    kind = ((card.choices.get("Chosen creature type") if card is not None else "") or "").strip()
    if color not in protection.COLORS or not kind:
        return None
    return {**token, "chosen": False, "name": kind, "colors": [protection.COLORS[color]], "type_line": f"Token Creature — {kind}"}


# A static that sets a type or a color to "the chosen type / color" carries a mark where the answer goes (the table is built from the printed lines): ``@land`` in
# ``layer4.set_land_types`` (the basic land type), ``@color`` in ``set_colors``. The answer is the source's own entering choice (614.12a, public); with none recorded the
# static does nothing (``resolve_marks`` returns None).
MARK_LAND, MARK_COLOR, MARK_LAND2 = "@land", "@color", "@land2"  # (@land2: the second of "two basic land types", Illusionary Terrain)


def resolve_marks(d: dict[str, Any], source: CardInstance) -> dict[str, Any] | None:
    text = json.dumps(d)
    if MARK_LAND not in text and MARK_COLOR not in text and MARK_LAND2 not in text:
        return d
    from app.rules import protection

    land = (source.choices.get("Chosen basic land type") or "").strip()
    land2 = (source.choices.get("Chosen second basic land type") or "").strip()
    color = protection.COLORS.get((source.choices.get("Chosen color") or "").strip().lower())

    def fill(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: fill(v) for k, v in node.items()}
        if isinstance(node, list):
            return [x for v in node for x in ([land] if v == MARK_LAND else [land2] if v == MARK_LAND2 else [color] if v == MARK_COLOR else [fill(v)])]
        return node

    if (MARK_LAND in text and not land) or (MARK_COLOR in text and not color) or (MARK_LAND2 in text and not land2):
        return None
    return fill(d)
# -- end chosen filters (wave 53B) -----------------------------------------------------------------------------------------
