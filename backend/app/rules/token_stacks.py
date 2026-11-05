"""Token stacks: one token permanent standing for N identical tokens (``CardInstance.quantity`` = N). Design: docs/TOKEN_STACKS.md.

A token is an object (109.1), each token on the battlefield is a permanent (110.1), and a token is subject to everything that affects
permanents (111.6). Sixteen token doublers turned one Goblin into 65,536 objects and froze the server, so the engine also knows a *stack*:
one object whose members are identical in everything the rules can see (characteristics, controller, tapped and summoning-sickness state,
counters, damage, attacking target, continuous effects: they share one rules object id). Reading one member then stands for reading each.

The rest of the engine sees a stack as one object. That is exact only where one member stands for each member, so:

* **formation** (:func:`may_stack`, ``replace._make_tokens``): only one instruction creating more than :data:`STACK_FROM` tokens of a kind
  that may stack, on a board the audit accepts;
* **the audit** (:func:`problems`): every ability that could observe a stack must be blind to it or one of the whitelisted shapes whose
  stack handling is implemented (counts in ``values``, anthems, all-at-once effects, token-creation replacements);
* **the touch guard** (:func:`guard`, called by ``Plan._do``): a step that changes a stack outside code known to treat it as N identical
  members (:func:`whole`) stops the action instead of acting on "one creature";
* **splitting** (:func:`single_out`): a choice that names a stack (a target, a sacrifice, a blocker) splits one member off first, keeping
  the chosen card id on that member;
* when the audit or the guard fails, a stack of at most :data:`INDIVIDUAL_LIMIT` is spread into individual tokens (:func:`spread`) and the
  action runs on those, exactly as before stacks existed; a bigger stack can't be spread without freezing the server, so the action is
  refused and the players finish it by hand (automation paused: the sandbox works on the stack).

Spreading or splitting is no event: the tokens were already there. Each new object gets no "enters" event (nothing triggers, no token is
"created" this turn) and inherits the stack's rules history instead (:func:`adopt`): how long it has been under its controller's control
(302.6), its manual/assisted mode, its entry this turn and "created a token" facts, and the continuous effects that affected it (611.2c).
"""

from __future__ import annotations

import functools
import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar, cast

from app.game.errors import ActionError
from app.game.state import CardInstance, GameState

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

STACK_FROM = 100  # one instruction making more than this many identical tokens makes a stack (when the token and the board allow it)
INDIVIDUAL_LIMIT = 256  # the most tokens made or spread one object each (the engine's cost grows with every object on the battlefield)
MAX_QUANTITY = 10 ** 15  # (a create_token step's ceiling: 2**50 is beyond any real table)

# Keywords a stack may have: each only affects the token that has it, in the same way for every member (combat evasion and damage
# results that need no separate events). Lifelink (a life gain event per member, 119.9/120.3f), toxic, afflict, annihilator, myriad,
# exalted, battle cry, … are not here: a stack with them is never made, and one that gains them is spread or refused.
SAFE_KEYWORDS = frozenset({"flying", "haste", "vigilance", "reach", "trample", "menace", "defender", "first strike", "double strike",
                           "deathtouch", "indestructible", "hexproof", "shroud", "intimidate", "fear", "shadow", "horsemanship",
                           "skulk", "changeling"})
# Keywords another permanent may have while a stack is around: they never look at other objects (ward and protection look at what
# targets or damages their own permanent; a stack splits before it targets).
SAFE_OBSERVER_KEYWORDS = SAFE_KEYWORDS | frozenset({"ward", "flash", "protection", "prowess", "lifelink", "partner", "partner with",
                                                    "companion", "infect", "wither", "toxic", "devoid", "storm"})

# Steps after which the audit runs again while a stack exists: an object that may see the stack appeared, or control changed.
NEW_OBJECT_STEPS = frozenset({"move", "mill", "create_token", "copy_card", "set_controller", "spawn_card", "set_face", "flip", "face_down",
                              "merge", "meld", "phase_shift", "return_to_owner", "turn_face_up"})
# Steps that never change a permanent's state, or that change every permanent alike (the untap step's untap, cleanup's damage removal).
FREE_STEPS = frozenset({"rules_log", "note", "create_arrow", "remove_arrow", "set_position", "rules_sync", "copy_card", "create_token",
                        "split_stack", "expand_stack", "add_effect", "remove_effect", "set_choice", "set_stack_info", "untap_all",
                        "cleanup", "phase", "next_turn", "create_ability", "renumber", "rules_mana", "rules_life_changes", "life",
                        "set_life", "draw", "shuffle", "reveal", "hide", "end_view", "look_top", "reveal_top"})
# The primitives that act on every member at once when their group includes a stack (whitelisted: docs/TOKEN_STACKS.md section 5).
GROUP_DOS = frozenset({"destroy_all", "damage", "pump", "grant"})
_PLAYER_WHO = frozenset({"you", "each_opponent", "each_player", "opponent", "target_player", "that_player", "defending_player",
                         "controller", "owner", "self", "it"})
_DENY = ("permanent", "token", "creature", "artifact", "enchantment", "land", "planeswalker", "battle", "any", "all", "each",
         "every", "other", "count", "number", "power", "toughness", "devotion", "party", "domain", "coven", "attack", "block", "combat",
         "sacrific", "destroy", "exile", "return", "bounce", "tap", "dies", "die", "enter", "leave", "counter", "control", "target",
         "choose", "chosen", "convoke", "improvise", "crew", "goad", "fight", "copy", "phase", "regenerat", "damage", "greatest", "least",
         "total", "x")


class StackGate(Exception):  # noqa: N818  (not an ActionError: engine code that tries something and catches ActionError must not hide it)
    """A step would touch a stack where the engine can't treat it as N identical members, or the audit refused a stack.
    ``compile_intent`` retries the action with every stack spread (when they are small enough) or refuses it."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# -- reading ----------------------------------------------------------------------------------------------------------------------
def stacks(state: GameState) -> list[str]:
    """The permanents standing for more than one token (the table's order). A token anywhere else ceases to exist (111.7)."""
    return [cid for cid, c in state.cards.items() if c.is_token and c.quantity > 1 and c.zone.endswith((":battlefield", ":phased"))]


def weight(state: GameState, card_id: str) -> int:
    """How many objects ``card_id`` stands for when the rules count (a stack: its members; anything else: one)."""
    card = state.cards.get(card_id)
    if card is None or not card.is_token or card.quantity <= 1 or not card.zone.endswith(":battlefield"):
        return 1
    return card.quantity


def count(state: GameState, card_ids: Any) -> int:
    """The number of objects among ``card_ids``, a stack counting as its members."""
    return sum(weight(state, cid) for cid in card_ids)


def label(card: CardInstance) -> str:
    return f"{card.name} ×{card.quantity:,}"


# -- whole-stack contexts and the touch guard -------------------------------------------------------------------------------------
@contextmanager
def whole(plan: Plan) -> Iterator[None]:
    """Code that treats a stack as its N identical members (state-based actions, turn-based actions, all-at-once effects)."""
    depth = getattr(plan, "stack_whole", 0)
    plan.stack_whole = depth + 1
    try:
        yield
    finally:
        plan.stack_whole = depth


_F = TypeVar("_F", bound=Callable[..., Any])


def whole_call(fn: _F) -> _F:
    """A rules procedure that treats every permanent alike (state-based actions, a turn-based action): it runs inside :func:`whole`."""

    @functools.wraps(fn)
    def run(plan: Plan, *args: Any, **kw: Any) -> Any:
        with whole(plan):
            return fn(plan, *args, **kw)

    return cast(_F, run)


@contextmanager
def group_effect(plan: Plan, e: dict[str, Any]) -> Iterator[None]:
    """A whitelisted all-at-once primitive (its group may include a stack): every member is affected alike."""
    who = e.get("who")
    if e.get("do") in GROUP_DOS and (e.get("do") == "destroy_all" or who == "each_creature"
                                      or (isinstance(who, str) and who.startswith("sel:"))):
        with whole(plan):
            yield
    else:
        yield


def _touched(payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("card_ids", "tap"):
        value = payload.get(key)
        if isinstance(value, list):
            ids.update(x for x in value if isinstance(x, str))
    for key in ("card_id", "to", "attached_to"):
        value = payload.get(key)
        if isinstance(value, str):
            ids.add(value)
    if payload.get("type") == "rules_damage":
        for key in ("creatures", "wither", "planeswalkers"):
            ids.update((payload.get(key) or {}).keys())
    return ids


def guard(plan: Plan, payload: dict[str, Any]) -> None:
    """Before a step: a stack may only be changed by code that treats it as N identical members."""
    kind = payload.get("type")
    if kind in FREE_STEPS or getattr(plan, "stack_whole", 0) > 0:
        return
    touched = _touched(payload)
    if not touched:
        return
    for cid in touched:
        card = plan.state.cards.get(cid)
        if card is not None and card.is_token and card.quantity > 1 and card.zone.endswith((":battlefield", ":phased")):
            raise StackGate(f"{label(card)} is a stack of tokens, and this would treat it as one token ({kind}).")


# -- splitting ----------------------------------------------------------------------------------------------------------------------
def single_out(plan: Plan, card_id: str) -> None:
    """Make ``card_id`` stand for exactly one member: the other members move to a new object (the same tokens, already there)."""
    card = plan.state.cards.get(card_id)
    if card is not None and card.zone == "stack":
        single_out_fold(plan, card_id)  # -- token stack folds (wave TS2) -- one instance of a folded triggered ability
        return
    keep(plan, card_id, 1)


def keep(plan: Plan, card_id: str, count: int) -> None:
    """Make ``card_id`` stand for exactly ``count`` of its members (an attack with part of a stack): the others move to a new object."""
    card = plan.state.cards.get(card_id)
    if card is None or not card.is_token or card.quantity <= count:
        return
    before = set(plan.state.cards)
    with whole(plan):
        plan.do({"type": "split_stack", "card_id": card_id, "count": card.quantity - count})
    adopt(plan.state, card_id, [c for c in plan.state.cards if c not in before])


def check_targets(plan: Plan, entry: Any) -> None:
    """As a spell or ability resolves: a target that is still a whole stack was chosen past the points that split one member off
    (an engine-made choice): stop rather than act on every member (or, small, retry with the stack spread: each target then is one)."""
    refs = [*entry.targets, *(r for g in entry.groups for r in g), *(r for s in entry.slots for r in s)]
    for ref in refs:
        card = plan.state.cards.get(ref.id)
        if card is not None and card.is_token and card.quantity > 1 and card.zone.endswith(":battlefield"):
            raise StackGate(f"{label(card)} is a stack of tokens, and a target must be one of them.")
        if card is not None and card.zone == "stack" and _fold_of(plan, ref.id) is not None:  # -- token stack folds (wave TS2) --
            raise ActionError(f"{plan.rules.stack[ref.id].name} stands for several identical triggered abilities, and a target must be "
                              f"one of them. Pause automation and do this by hand.")


def single_out_all(plan: Plan, ids: Any) -> None:
    for cid in list(dict.fromkeys(i for i in ids if isinstance(i, str))):
        single_out(plan, cid)


def _intent_ids(intent: Any) -> list[str]:
    """The card ids an intent names one object each (targets, mana sources, crew, cost choices, a blocker and the attacker it blocks).
    A declared *attacker* that is a stack attacks with all its members (docs/TOKEN_STACKS.md) and isn't here."""
    out: list[str] = []
    for key in ("targets", "sources", "crew", "splice", "replicate_from"):
        value = getattr(intent, key, None)
        if isinstance(value, list):
            out += [x for x in value if isinstance(x, str)]
    for choice in getattr(intent, "cost_choices", None) or []:
        data = choice.model_dump() if hasattr(choice, "model_dump") else {}
        for value in data.values():
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, list):
                out += [x for x in value if isinstance(x, str)]
    if intent.type == "declare_blockers":
        for block in getattr(intent, "blocks", None) or []:
            out += [x for x in (getattr(block, "blocker_id", None), getattr(block, "attacker_id", None)) if isinstance(x, str)]
    if intent.type == "activate_ability" and isinstance(getattr(intent, "card_id", None), str):
        out.append(intent.card_id)
    return out


def single_out_intent(plan: Plan, intent: Any) -> None:
    """Before an intent runs: each card id it names as one object stands for one member (601.2c, 602.2b, 509.1a)."""
    if not stacks(plan.state) and not folds_on_stack(plan):  # (-- token stack folds (wave TS2) -- or a folded triggered ability)
        return
    ids = _intent_ids(intent)
    if intent.type == "choose" and plan.rules.decision is not None:
        options = {o.id: o for o in plan.rules.decision.options}
        for oid in getattr(intent, "option_ids", None) or []:
            option = options.get(oid)
            if option is not None and option.card_id:
                ids.append(option.card_id)
            elif oid in plan.state.cards:
                ids.append(oid)
    single_out_all(plan, [cid for cid in ids if cid in plan.state.cards])


def spread(plan: Plan, *, limit: int | None = None) -> None:
    """Spread every token stack (up to ``limit`` members) into separate objects (recorded steps of the intent or reconciliation)."""
    for cid in stacks(plan.state):
        if limit is not None and plan.state.cards[cid].quantity > limit:
            continue
        before = set(plan.state.cards)
        with whole(plan):
            plan.do({"type": "expand_stack", "card_id": cid})
        adopt(plan.state, cid, [c for c in plan.state.cards if c not in before])


def adopt(state: GameState, source: str, new_ids: list[str]) -> None:
    """``new_ids`` were split off the stack ``source``: they are tokens that were already there, not new ones (see above)."""
    rules = state.rules
    if rules is None or not new_ids or source not in state.cards:
        return
    new = set(new_ids)
    src_oid = rules.object_id(source)
    rules.events = [e for e in rules.events if e.card not in new]
    log = rules.turn_log
    current = log.turn == state.turn.number
    if current:
        log.entered = [e for e in log.entered if e.card not in new]
    entry = next((e for e in log.entered if e.object_id == src_oid), None) if current else None
    facts = [f for f in log.facts if f.object_id == src_oid and f.kind == "token"] if current else []
    new_oids = {rules.object_id(cid) for cid in new_ids}
    origin = src_oid in rules.entry_life_origins
    rules.entry_life_origins = [o for o in rules.entry_life_origins if o not in new_oids]
    mark = rules.controlled_since.get(source)
    mode = rules.card_modes.get(source)
    for cid in new_ids:
        oid = rules.object_id(cid)
        if mark is not None:
            rules.controlled_since[cid] = mark.model_copy()
        if mode is not None:
            rules.card_modes[cid] = mode
        if entry is not None:
            log.entered.append(entry.model_copy(update={"card": cid, "object_id": oid}))
        log.facts.extend(f.model_copy(update={"object_id": oid}) for f in facts)
        if origin:
            rules.entry_life_origins.append(oid)
    # -- engine token stacks -- 611.2c: a continuous effect that affected the stack affected each of its members
    for effect in rules.effects:
        if src_oid in effect.affected:
            effect.affected += [o for o in sorted(new_oids) if o not in effect.affected]


# -- the audit ----------------------------------------------------------------------------------------------------------------------
def _stack_problem(plan: Plan, card: CardInstance, ch: Characteristics) -> str | None:
    """Can this token be a stack (made as one, or kept as one)? None: yes."""
    if "Legendary" in ch.supertypes:
        return "legendary tokens each follow the legend rule"
    if card.face_down or card.copy_of is not None:
        return "it isn't a plain token"
    if card.attached_to is not None or card.attached_player is not None:
        return "it is attached to something"
    if any(c.attached_to == card.id for c in plan.state.cards.values()):
        return "something is attached to it"
    defs = _defs(ch) if any(ab.kind == "triggered" for ab in ch.abilities) else {}
    for ab in ch.abilities:
        if ab.kind == "triggered" and fold_shape(defs.get(ab.index)) is not None:
            continue  # -- token stack folds (wave TS2) -- every member's trigger is folded into one (fold_pending, docs/TOKEN_STACKS.md 9)
        if ab.kind != "keywords" or not set(ab.keywords) <= SAFE_KEYWORDS:
            return f"it has the ability “{ab.text}”"
    if not ch.keywords <= SAFE_KEYWORDS:
        return f"it has {', '.join(sorted(ch.keywords - SAFE_KEYWORDS))}"
    if ch.imposed:
        return "a rule applies to it on its own"
    return None


def _strip_sels(value: Any, sels: list[str]) -> Any:
    if isinstance(value, str):
        if value.startswith("sel:"):
            sels.append(value)
            return "§"
        if value.startswith("except:") and "|sel:" in value:
            sels.append(value.split("|", 1)[1])
            return "§"
        return value
    if isinstance(value, dict):
        return {k: _strip_sels(v, sels) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_strip_sels(v, sels) for v in value]
    return value


def _words(ch: Characteristics) -> tuple[str, ...]:
    """The words that could name a stack of this kind."""
    words = {w.lower() for w in (*ch.types, *ch.subtypes, *ch.supertypes)}
    words |= {w.lower() for w in re.findall(r"[A-Za-z]{3,}", ch.name)}
    colors = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
    words |= {colors[c] for c in ch.colors if c in colors}
    if ch.colors:
        words |= {"colored", "monocolored", "multicolored"}
    else:
        words.add("colorless")
    return tuple(sorted(words))


def _lexically_blind(text: str, extra: tuple[str, ...]) -> bool:
    low = text.lower()
    return not any(re.search(rf"(?<![a-z]){re.escape(w)}", low) for w in (*_DENY, *extra))


def _matches(plan: Plan, key: str, card: CardInstance, ch: Characteristics, you: str, source: str | None) -> bool:
    from app.rules import selectors

    try:
        return selectors.matches(plan, selectors.from_key(key), card, ch, you, source)
    except Exception:  # noqa: BLE001  (a selector that can't be read here might match: refuse)
        return True


class _Audit:
    def __init__(self, plan: Plan, stack_ids: list[str], chs: dict[str, Characteristics] | None = None, fold: bool = False) -> None:
        self.plan = plan
        chs = chs or {}
        self.stacks = [(plan.state.cards[cid], chs.get(cid) or plan.ch(plan.state.cards[cid])) for cid in stack_ids]
        self.words = tuple(sorted({w for _, ch in self.stacks for w in _words(ch)}))
        self.fold = fold  # -- token stack folds (wave TS2) -- auditing the tokens a folded trigger makes, not a stack (fold_problems)

    def refers(self, sels: list[str], observer: CardInstance) -> bool:
        return any(_matches(self.plan, key, card, ch, observer.controller, observer.id) for key in sels for card, ch in self.stacks)

    def blind(self, value: Any) -> bool:
        sels: list[str] = []
        stripped = _strip_sels(value, sels)
        if sels:
            return False
        if isinstance(stripped, dict) and stripped.get("who") in _PLAYER_WHO:
            stripped = {k: v for k, v in stripped.items() if k != "who"}
        return _lexically_blind(json.dumps(stripped), self.words)

    def amount_ok(self, value: Any, observer: CardInstance) -> bool:
        """An amount: a number, or a count (``values`` counts every member of a stack)."""
        if value is None or isinstance(value, int):
            return True
        if isinstance(value, dict) and set(value) == {"count"} and isinstance(value["count"], str):
            return True
        return self.blind(value)

    def effect_ok(self, e: dict[str, Any], observer: CardInstance) -> bool:
        do, who = e.get("do"), e.get("who")
        sels: list[str] = []
        _strip_sels(e, sels)
        if do in ("gain_life", "lose_life", "draw") and who in _PLAYER_WHO and set(e) <= {"do", "who", "n"}:
            return self.amount_ok(e.get("n"), observer)
        if do == "no_regen" and set(e) == {"do"}:
            return True
        if do == "search" and who == "you" and set(e) <= {"do", "who", "filter", "to", "reveal", "n"} \
                and e.get("to") in ("hand", "battlefield", "battlefield_tapped", "top", "graveyard"):
            return True  # -- token stack folds (wave TS2) -- 701.23: cards found in a library (Rampant Growth); new lands are audited as they arrive
        if do == "create_token" and who == "you" and set(e) <= {"do", "who", "n", "token"}:
            return self.amount_ok(e.get("n"), observer)
        if do == "destroy_all" and set(e) <= {"do", "who", "types"} and who == "all":
            return True
        if do == "damage" and who == "each_creature" and isinstance(e.get("n"), int) and set(e) <= {"do", "who", "n"}:
            return True
        if do in ("pump", "grant") and isinstance(who, str) and who.startswith("sel:") \
                and set(e) <= {"do", "who", "p", "t", "keywords"} and set(e.get("keywords") or ()) <= SAFE_KEYWORDS:
            return self.amount_ok(e.get("p"), observer) and self.amount_ok(e.get("t"), observer)
        if who == "target" and do in _TARGET_DOS and set(e.get("keywords") or ()) <= SAFE_KEYWORDS:
            # one target: a stack member it names was split off as it was chosen (single_out_intent); an engine-made choice that
            # bypasses that hits the touch guard
            return self.blind({k: v for k, v in e.items() if k not in ("do", "who", "keywords")})
        return self.blind(e)

    def definition_ok(self, d: dict[str, Any], observer: CardInstance) -> bool:
        kind = d.get("kind")
        if kind == "static":
            if d.get("static") == "replace" and d.get("event") == "tokens" and (d.get("op") or {}).get("do") == "mul" and not d.get("effects"):
                return True  # 614.1a: a token-creation replacement acts on creation, before any stack exists (replace._make_tokens)
            if d.get("static") == "replace" and d.get("event") == "counters" and (d.get("op") or {}).get("do") in ("mul", "add") \
                    and not d.get("effects"):
                return True  # 614.1a: counters put on a stack are put on each member alike, and each member's event is replaced alike
            # -- token stack folds (wave TS2) --
            if d.get("static") == "trigger_multiplier" and d.get("cause") == "enter" and not d.get("effects"):
                return True  # 603.2d: one more instance of each trigger an entering object causes (trigger_multipliers.multiply copies it)
            if d.get("static") == "permission" and d.get("zone") in ("library_top", "graveyard") and not d.get("effects"):
                return True  # (playing or casting cards from a library or a graveyard: never a token on the battlefield)
            if d.get("static") == "no_legend_rule" and not d.get("effects"):
                return True  # 704.5j: a stack is never legendary; the legendary tokens a fold makes are judged in fold_problems
            if d.get("static") == "grant" and not d.get("conditions") and not d.get("grants") and not d.get("rules") \
                    and d.get("base") is None and d.get("attached_kind") is None and not d.get("effects") \
                    and set(d.get("keywords") or ()) <= SAFE_KEYWORDS:
                return self.amount_ok(d.get("p"), observer) and self.amount_ok(d.get("t"), observer)
            return self.blind(d)
        if kind == "replacement" and d.get("replacement") == "enter_as_copy":
            return True  # (it only applies as its own permanent enters: a copy reads copiable values, the same for each member)
        if kind in ("spell", "activated", "triggered"):
            target = d.get("target")
            if target not in (None, {"what": "player"}) and not self.blind(target):
                # a target that may be a stack member: the intent's / decision's choice splits it off first (single_out_intent), and
                # an engine-made choice that bypasses that hits the touch guard
                pass
            if kind == "triggered" and fold_shape(d) is not None:  # -- token stack folds (wave TS2) --
                return self.fold_observer_ok(d, observer)
            if kind == "triggered":
                trigger = {k: v for k, v in d.items() if k not in ("kind", "effects", "optional", "target")}
                if trigger.get("trigger") in _PHASE_TRIGGERS and set(trigger) == {"trigger"} or trigger.get("trigger") == "enters_self" and set(trigger) == {"trigger"}:
                    pass
                elif trigger.get("trigger") == "enters_other" and set(trigger) <= {"trigger", "filter"} and not d.get("optional") \
                        and d.get("target") is None and all(isinstance(e, dict) and e.get("do") in ("gain_life", "lose_life", "draw")
                                                            for e in d.get("effects") or []):
                    # 603.2c: one trigger per member that entered (triggers._other_enters reads token_stacks.weight)
                    if self.fold and not (all(e.get("do") in FOLD_DOS for e in d.get("effects") or []) and not _life_readers(self.plan)):
                        return False  # -- token stack folds (wave TS2) -- a draw between two folded resolutions could matter
                    pass
                elif not self.blind(trigger):
                    return False
            if not _cost_ok(d.get("cost"), self.words):
                return False
            return all(isinstance(e, dict) and self.effect_ok(e, observer) for e in d.get("effects") or [])
        return self.blind(d)

    def fold_observer_ok(self, d: dict[str, Any], observer: CardInstance) -> bool:
        """-- token stack folds (wave TS2) -- a foldable trigger (fold_shape) of another permanent while a stack exists: its condition
        doesn't count the stack, and no stack is a land (a landfall trigger per member). Its own instances fold (fold_pending)."""
        if self.refers(_cond_sels(d), observer):
            return False
        return not (d.get("trigger") == "landfall" and any(ch.is_land for _, ch in self.stacks))

    def observer_problem(self, card: CardInstance, ch: Characteristics) -> str | None:
        from app.rules import oracle, scripts

        if not ch.keywords <= SAFE_OBSERVER_KEYWORDS:
            return f"{ch.name or card.name}'s {', '.join(sorted(ch.keywords - SAFE_OBSERVER_KEYWORDS))}"
        try:
            defs = scripts.definitions(ch)
        except Exception:  # noqa: BLE001
            defs = {}
        for ab in ch.abilities:
            if ab.kind == "keywords":
                continue
            d = defs.get(ab.index)
            if d is None:
                text = oracle.strip_reminders(ab.text)
                for name in {ch.name, card.name}:
                    if name:
                        text = text.replace(name, "~")
                text = re.sub(r"\bthis (creature|permanent|artifact|enchantment|land|card|token|spell)\b", "~", text, flags=re.I)
                if not _lexically_blind(text, self.words):
                    return ch.name or card.name
                continue
            if not self.definition_ok(d, card):
                return ch.name or card.name
        if ch.is_instant_or_sorcery or card.zone == "stack":
            try:
                spell = scripts.spell_definition(ch)
            except Exception:  # noqa: BLE001
                spell = None
            if spell is not None and not self.definition_ok(spell, card):
                return ch.name or card.name
        return None


_TARGET_DOS = frozenset({"damage", "destroy", "exile", "bounce", "pump", "grant", "tap", "untap"})
_SACRIFICE_ONE = re.compile(r"^sacrifice (?:a|an|another) [a-z ,'-]+$", re.IGNORECASE)
_MANA_OR_TAP = re.compile(r"^(?:\{[^}]+\})+$")


def _cost_ok(cost: Any, words: tuple[str, ...]) -> bool:
    """An activation cost: mana and {T}, or "Sacrifice a creature" (602.2b: the creature chosen is one member, split off as it's
    chosen, single_out_intent), or one that can't name a stack."""
    if cost is None:
        return True
    if not isinstance(cost, str):
        return False
    for part in (p.strip() for p in cost.split(",")):
        if _MANA_OR_TAP.match(part) or _SACRIFICE_ONE.match(part) or _lexically_blind(part, words):
            continue
        return False
    return True


_PHASE_TRIGGERS = frozenset({"upkeep", "your_upkeep", "each_upkeep", "end_step", "your_end_step", "each_end_step", "draw_step",
                             "your_draw_step", "precombat_main", "your_precombat_main"})
# The rules records that react to future events or change future results. A stack is kept only while none of them can reach it.
_REACTIVE = ("delayed", "replacements", "prevention", "prevention_riders", "regen_shields", "regeneration_riders",
             "destruction_replacements", "exile_if_leaves", "player_shields", "wipe_shields110o", "pending_triggers", "permissions",
             "cost_modifiers", "cast_limits", "graveyard_grants", "linked_exile", "exiled_with", "aura_links", "protectors", "pairs",
             "chosen_objects", "attack_piles", "block_piles110f", "free_casts", "deferred_payments")


def problems(plan: Plan, stack_ids: list[str] | None = None, *, chs: dict[str, Characteristics] | None = None,
             recipes: dict[str, Any] | None = None, fold: bool = False) -> list[str]:
    """Why the engine can't treat the stacks (``stack_ids``, default every stack) exactly right now: public names only. Empty: it can.

    Read: each stack itself; every other permanent; everything on the stack; emblems; the abilities of graveyard and face-up exile cards;
    the rules records that react to future events. Hidden cards are never read (a refusal that depended on one would reveal it).
    (-- token stack folds (wave TS2) -- ``chs`` / ``recipes``: a probe's characteristics and copiable values; ``fold``: the ids are the
    tokens a folded trigger makes, judged by fold_problems rather than as stacks.)"""
    ids = stacks(plan.state) if stack_ids is None else [cid for cid in stack_ids if cid in plan.state.cards]
    if not ids:
        return []
    with plan.reading():  # -- token stack folds (wave TS2) -- each permanent derived once per audit (a big board: 150 objects)
        return _problems(plan, ids, chs or {}, recipes, fold)


def _problems(plan: Plan, ids: list[str], chs: dict[str, Characteristics], recipes: dict[str, Any] | None, fold: bool) -> list[str]:
    out: list[str] = []
    for cid in ids if not fold else ():
        stack = plan.state.cards[cid]
        sch = chs.get(cid) or plan.ch(stack)
        why = _stack_problem(plan, stack, sch)
        if why is not None:
            out.append(f"{label(stack)}: {why}")
            continue
        # -- token stack folds (wave TS2) -- a stack keeps a foldable trigger only while folding it is exact
        for d in _fold_defs(sch):
            out += [f"{label(stack)}: {why}" for why in fold_problems_once(plan, stack.controller, d, stack.id, plan.oid(stack), recipes=recipes)]
    audit = _Audit(plan, ids, chs, fold)
    stack_set = set(ids)
    seen: set[str] = set()
    for key, zone_ids in plan.state.zones.items():
        zone = key.split(":")[-1]
        if zone not in ("battlefield", "stack", "command", "graveyard", "exile", "phased"):
            continue
        for cid in zone_ids:
            card = plan.state.cards.get(cid)
            if card is None or cid in stack_set or not plan.in_game(card):
                continue
            if zone == "command" and not (card.token and card.token.type_line == "Emblem"):
                continue  # (a commander's abilities don't work from the command zone; an emblem's do, 114.4)
            if zone in ("graveyard", "exile") and (card.face_down or not _works_there(plan, card)):
                continue
            entry = plan.rules.stack.get(cid) if zone == "stack" else None
            if entry is not None and card.ability is not None:  # an ability on the stack: what it will do (its source was read as a permanent)
                d = {"kind": "activated", "effects": entry.effects, "target": entry.target_spec}
                if entry.kind == "trigger" and entry.target_spec is None and not entry.targets and not entry.optional:
                    d = _entry_fold_def(entry) or d  # -- token stack folds (wave TS2) -- a foldable trigger, folded or not
                why = None if audit.definition_ok(d, card) else (entry.name or card.name)
                if why is not None and why not in seen:
                    seen.add(why)
                    out.append(why)
                continue
            if zone == "stack" and card.ability is not None:
                continue  # (an ability still being put on the stack: its entry, read above, comes as its costs are paid)
            ch = plan.ch(card)
            why = audit.observer_problem(card, ch)
            if why is not None and why not in seen:
                seen.add(why)
                out.append(why)
    rules = plan.rules
    oids = {rules.object_id(cid) for cid in ids}
    for name in _REACTIVE:
        value = getattr(rules, name, None)
        if not value:
            continue
        dumped = json.dumps(_dump(value), default=str)
        if any(cid in dumped for cid in ids) or any(o in dumped for o in oids):
            out.append(f"an effect waiting to act on {label(plan.state.cards[ids[0]])}")
            break
        sels = re.findall(r'"(sel:(?:[^"\\]|\\.)*)"', dumped)
        keys = [json.loads(f'"{s}"') for s in sels]
        if keys and any(_matches(plan, k, c, ch, c.controller, None) for k in keys for c, ch in audit.stacks):
            out.append("an effect waiting to act on creatures like these")
            break
    return out


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _dump(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_dump(v) for v in value]
    return value


def _works_there(plan: Plan, card: CardInstance) -> bool:
    """Has this graveyard / exile card an ability that works there (a trigger or static naming its own zone)?"""
    ch = plan.ch(card)
    text = ch.oracle_text.lower()
    return any(ab.kind in ("triggered", "static", "activated") for ab in ch.abilities) and (
        "graveyard" in text or "exile" in text or "from your hand" in text)


# -- per-member triggers ------------------------------------------------------------------------------------------------------------
FOLD_DOS = frozenset({"gain_life", "lose_life"})


def member_triggers(plan: Plan, watcher: CardInstance, d: dict[str, Any], entered: CardInstance,
                    name: str) -> tuple[int, dict[str, Any], str]:
    """603.2c: a stack of N entering triggers "whenever another creature enters" N times. Returns (how many triggers to add, the
    definition, the name). A trigger that only gains or loses a fixed amount of life is *folded* into one trigger doing it N times over,
    when nothing on the table reads life gain or loss (no "whenever you gain life", no "if you would gain life"): N separate life
    changes and one change of N times as much then end the same, and the players skip passing priority N times (732.2a: the shortcut
    of letting the identical triggers resolve). Otherwise up to INDIVIDUAL_LIMIT separate triggers; beyond that the action stops."""
    n = weight(plan.state, entered.id)
    if n <= 1:
        return 1, d, name
    effects = d.get("effects") or []
    if (effects and all(isinstance(e, dict) and e.get("do") in FOLD_DOS and isinstance(e.get("n"), int) and e.get("who") in _PLAYER_WHO
                        and set(e) <= {"do", "who", "n"} for e in effects)
            and not d.get("optional") and d.get("target") is None and not _life_readers(plan)):
        folded = {**d, "effects": [{**e, "n": int(e["n"]) * n} for e in effects]}
        return 1, folded, f"{name} (×{n:,})"
    if n > INDIVIDUAL_LIMIT:
        raise StackGate(f"{label(entered)} entering would trigger {name} {n:,} times, one at a time.")
    return n, d, name


_LIFE_WORDS = re.compile(r"\blife\b", re.IGNORECASE)


def _life_readers(plan: Plan) -> list[str]:
    """Public abilities that could see a life gain or loss event (anything mentioning life that isn't itself a foldable enters trigger)."""
    from app.rules import oracle, scripts

    out: list[str] = ["a life rule"] if plan.rules.cant_gain else []
    for key, ids in plan.state.zones.items():
        zone = key.split(":")[-1]
        if zone not in ("battlefield", "stack", "command", "graveyard", "exile"):
            continue
        for cid in ids:
            card = plan.state.cards.get(cid)
            if card is None or card.face_down:
                continue
            if zone == "command" and not (card.token and card.token.type_line == "Emblem"):
                continue
            ch = plan.ch(card)
            if not _LIFE_WORDS.search(ch.oracle_text or "") and not any(_LIFE_WORDS.search(a.text) for a in ch.abilities):
                continue
            defs = scripts.definitions(ch)
            for ab in ch.abilities:
                if not _LIFE_WORDS.search(oracle.strip_reminders(ab.text)):
                    continue
                d = defs.get(ab.index) or {}
                if d.get("kind") == "triggered" and d.get("trigger") == "enters_other" \
                        and all(isinstance(e, dict) and e.get("do") in FOLD_DOS for e in d.get("effects") or []):
                    continue
                if zone in ("graveyard", "exile", "stack") and ab.kind not in ("triggered", "static"):
                    continue
                out.append(ch.name or card.name)
    return out


# -- token stack folds (wave TS2) ----------------------------------------------------------------------------------------------------
# docs/TOKEN_STACKS.md section 9. N identical triggered abilities that only create tokens ("Landfall — … create a token that's a copy of
# this creature", Scute Swarm; "At the beginning of your upkeep, if …, create a token that's a copy of this creature", Biowaste Blob) are
# put on the stack as ONE ability "Scute Swarm (×N)" that resolves as the N would, one after another with every player passing (the 732.2a
# shortcut the Soul Warden fold already takes): its condition is checked as it resolves (603.4, 608.2c), and it makes N times the tokens
# in one creation event. That is exact only when nothing can tell the difference, which fold_problems checks:
#
# * the N resolutions are identical: the same definition, sources with the same copiable values (707.2), no target, no choice (an
#   optional ability's "you may" is answered for each instance, Ancient Greenwarden ruling 2020-09-25), no event information read;
# * nothing happens between them: no ability triggers on the tokens being created or entering one batch at a time (the audit refuses
#   any observer but a folded fixed life gain), no ability watches triggers or the stack, and the condition can't count the tokens made;
# * one creation event of N×k tokens ends as N events of k: the only token replacements the audit lets through multiply ("twice that
#   many", 616.1 / 616.1f: 2·(N·k) = N·(2·k), in any order); an additive one ("plus an additional token", "first time each turn") is
#   refused, as is a batch observer ("whenever you create one or more tokens", 603.2c: one event, not N);
# * the controller has no other trigger to order between them (603.3b: they would be ordered as a block).
FOLD_TRIGGERS = frozenset({"landfall", "upkeep_you", "end_step_you", "step:begin_combat:you"})
_FOLD_KEYS = frozenset({"kind", "trigger", "effects", "optional", "target", "if", "members"})
_ABILITY_WORDS = re.compile(r"\btrigger|\bstack\b|\babilit(?:y|ies)\b", re.IGNORECASE)


def _defs(ch: Characteristics) -> dict[int, dict[str, Any]]:
    from app.rules import scripts

    try:
        return scripts.definitions(ch)
    except Exception:  # noqa: BLE001
        return {}


def _fold_cond_ok(c: Any) -> bool:
    """A condition the engine reads the same way before and after the tokens are made (checked against them in fold_problems):
    "if you control six or more lands" (a count), "if you control a commander", "if you've cast a noncreature spell this turn"."""
    if not isinstance(c, dict):
        return False
    if set(c) == {"not"}:
        return _fold_cond_ok(c["not"])
    if set(c) == {"value", "op", "n"} and isinstance(c["n"], int) and isinstance(c["value"], dict) and set(c["value"]) == {"count"} \
            and isinstance(c["value"]["count"], str) and c["value"]["count"].startswith("sel:"):
        return True
    return c.get("history") == "cast" and set(c) <= {"history", "who", "sel", "n", "op"} and c.get("who") == "you"


def _cond_sels(d: dict[str, Any]) -> list[str]:
    sels: list[str] = []
    for c in [d.get("if"), *(e.get("cond") for e in d.get("effects") or [] if isinstance(e, dict) and e.get("do") == "only_if")]:
        if c is not None:
            _strip_sels(c, sels)
    return sels


def fold_shape(d: Any) -> list[dict[str, Any]] | None:
    """The token creations of a triggered ability the engine can fold (None: it can't): a phase or landfall trigger, no target, not
    optional, whose effects are only "create [n] [fixed token]" and "create [n] token[s] that's a copy of this creature", gated by
    conditions read the same way each time (_fold_cond_ok; Scute Swarm's "If you control six or more lands, … instead")."""
    if not isinstance(d, dict) or d.get("kind") != "triggered" or d.get("trigger") not in FOLD_TRIGGERS or not set(d) <= _FOLD_KEYS:
        return None
    if d.get("optional") or d.get("target") is not None or (d.get("if") is not None and not _fold_cond_ok(d["if"])):
        return None
    return _fold_effects(d.get("effects"))


def _fold_effects(effects: Any) -> list[dict[str, Any]] | None:
    makes: list[dict[str, Any]] = []
    flags: set[str] = set()
    for e in effects if isinstance(effects, list) else ():
        if not isinstance(e, dict):
            return None
        do = e.get("do")
        if do == "only_if" and set(e) <= {"do", "cond", "skip", "bind"} and isinstance(e.get("skip"), int):
            c = e.get("cond")
            if not (isinstance(c, dict) and set(c) <= {"flag", "negate"} and c.get("flag") in flags) and not _fold_cond_ok(c):
                return None
            if isinstance(e.get("bind"), str):
                flags.add(e["bind"])
        elif _fold_make(e):
            makes.append(e)
        else:
            return None
    return makes or None


def _fold_make(e: dict[str, Any]) -> bool:
    """"Create [n] [fixed token]" for you, or "create [n] token(s) that's a copy of this creature"."""
    if type(e.get("n")) is not int or e["n"] <= 0:
        return False
    if e.get("do") == "create_token":
        return e.get("who") == "you" and set(e) <= {"do", "who", "n", "token"} and isinstance(e.get("token"), dict) \
            and not any(str(k).startswith("_") for k in e["token"])
    return e.get("do") == "token_copy" and e.get("who") == "self" and set(e) <= {"do", "who", "n"}


def _fold_defs(ch: Characteristics) -> list[dict[str, Any]]:
    if not any(ab.kind == "triggered" for ab in ch.abilities):
        return []
    defs = _defs(ch)
    return [d for ab in ch.abilities if ab.kind == "triggered" and (d := defs.get(ab.index)) is not None and fold_shape(d) is not None]


def _entry_fold_def(entry: Any) -> dict[str, Any] | None:
    """A trigger on the stack that is a foldable shape (folded or not), as a definition the audit reads. It already triggered: its
    trigger condition is no longer read (a phase trigger stands in for it)."""
    effects = list(entry.effects or [])
    if effects and isinstance(effects[0], dict) and effects[0].get("do") == "fold_check":
        d = effects[0].get("def")
        return {**d, "trigger": "upkeep_you"} if isinstance(d, dict) and fold_shape({**d, "trigger": "upkeep_you"}) is not None else None
    d = {"kind": "triggered", "trigger": "upkeep_you", "effects": effects, "optional": False, "target": None}
    return d if fold_shape(d) is not None else None


def _source_recipe(plan: Plan, source_card: str | None, source_object: str | None, recipes: dict[str, Any] | None = None) -> Any:
    """The copiable values (707.2) of a trigger's source: on the battlefield, else as it last existed there (608.2h). None: unknown."""
    from app.game.rules_state import CopyRecipe
    from app.rules import copying

    if recipes and source_card in recipes:
        return recipes[source_card]
    card = plan.state.cards.get(source_card or "")
    if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == source_object:
        if card.face_down or card.merged:
            return None
        return copying.recipe_of(plan, card)
    snap = plan.rules.lki.get(source_object or "")
    if snap is None or not snap.zone.endswith("battlefield") or snap.face_down:
        return None
    if snap.copy_recipe is not None:
        return snap.copy_recipe
    return CopyRecipe(printing=snap.printing, face=snap.face, source=snap.name[:200]) if snap.printing else None


def _fingerprint(recipe: Any) -> str:
    return json.dumps(recipe.model_dump(mode="json", exclude={"source"}), sort_keys=True) if recipe is not None else ""


@contextmanager
def _probe(plan: Plan, player: str, token: dict[str, Any]) -> Iterator[CardInstance | None]:
    """A token of this kind, for a moment, on ``player``'s battlefield as a stack of two (nothing recorded; None: it can't be read)."""
    from app.game.state import TokenDef, zone_key

    spec = {k: v for k, v in token.items() if not k.startswith("_")}
    try:
        tdef = TokenDef.model_validate({**spec, "name": spec.get("name") or "Token"})
    except Exception:  # noqa: BLE001
        yield None
        return
    n = 0
    while f"__stack_probe{n or ''}__" in plan.state.cards:  # (a probe inside another probe's audit: a stack's own fold)
        n += 1
    probe = CardInstance(id=f"__stack_probe{n or ''}__", name=tdef.name, owner=player, controller=player,
                         zone=zone_key(player, "battlefield"), is_token=True, token=tdef, quantity=2, card_id=tdef.card_id)
    from app.rules import read_pass

    outer = getattr(read_pass._PASS, "cur", None)  # (a read pass open around this one never sees the probe: its own pass, below)
    read_pass._PASS.cur = None
    plan.state.cards[probe.id] = probe
    plan.state.zone(probe.zone).append(probe.id)
    try:
        with read_pass.scope(plan.state, plan.info):
            yield probe
    finally:
        plan.state.zone(probe.zone).remove(probe.id)
        del plan.state.cards[probe.id]
        read_pass._PASS.cur = outer
        _forget_probe(plan, probe.id)


def _copy_problem(plan: Plan, recipe: Any) -> str | None:
    """A token copy the engine can treat exactly in a stack or a fold: its copiable values are a recipe whose exceptions (707.9) are
    copiable values too ("except it isn't legendary", "except it's a 1/1"). One filled in as each copy enters, or a double-faced or
    melded original, is refused."""
    from app.rules import copying

    if recipe is None:
        return "its copiable values aren't known"
    if any(ex.pt_self110a or ex.enter_counters for ex in recipe.excepts):
        return "each copy is finished as it enters"
    layout = (plan.info.get(recipe.printing) or {}).get("layout") if recipe.printing else None
    if layout in copying.DOUBLE_FACED or layout == "meld":
        return "it copies a double-faced card"
    return None


def copy_spec(plan: Plan, recipe: Any) -> tuple[dict[str, Any], Characteristics]:
    """The token spec of a copy made from ``recipe`` (as copying.token_copy_request makes it) and its copiable characteristics."""
    from app.rules import copying

    ch = copying.characteristics(recipe, plan.info)
    if recipe.printing and plan.info.get(recipe.printing) is not None:
        spec: dict[str, Any] = {"card_id": recipe.printing, "name": (ch.name or "Token")[:80]}
    else:
        spec = {k: (recipe.token or {}).get(k) for k in ("name", "power", "toughness", "colors", "type_line", "text")}
    return {**spec, "type_line": copying.type_line(ch)}, ch


def _kinds(plan: Plan, d: dict[str, Any], source_card: str | None, source_object: str | None,
           recipes: dict[str, Any] | None = None) -> list[tuple[dict[str, Any], Characteristics | None, Any]] | str:
    """The kinds of token the ability ``d`` of this source can make (its fixed tokens, copies of its source): (token spec, copiable
    characteristics or None, copy recipe or None). A str: why they can't be known."""
    makes = fold_shape(d)
    if makes is None:
        return "it isn't an ability the engine folds"
    kinds: list[tuple[dict[str, Any], Characteristics | None, Any]] = []
    for m in makes:
        if m["do"] == "create_token":
            kinds.append((dict(m["token"]), None, None))
            continue
        recipe = _source_recipe(plan, source_card, source_object, recipes)
        why = _copy_problem(plan, recipe)
        if why is not None:
            return f"a copy of it: {why}"
        spec, ch = copy_spec(plan, recipe)
        kinds.append((spec, ch, recipe))
    return kinds


def _crossed(plan: Plan, controller: str, groups: list[Any]) -> bool:
    """Several groups of foldable triggers of one controller go on the stack as blocks in an order the controller picks (603.3b). That
    takes no option away only if no group's tokens could change another group's condition (Scute Swarm counts lands: a fold making land
    tokens would)."""
    if len(groups) < 2:
        return False
    made = [_kinds(plan, g[0].ability, g[0].source_card, g[0].source_object) for g in groups]
    for i, g in enumerate(groups):
        sels = _cond_sels(g[0].ability)
        for j, kinds in enumerate(made):
            if i == j or not sels:
                continue
            if isinstance(kinds, str):
                return True
            for spec, ch, _ in kinds:
                with _probe(plan, controller, spec) as probe:
                    if probe is None or any(_matches(plan, k, probe, ch or plan.ch(probe), controller, g[0].source_card) for k in sels):
                        return True
    return False


def fold_problems(plan: Plan, controller: str, d: dict[str, Any], source_card: str | None, source_object: str | None, *,
                  recipes: dict[str, Any] | None = None) -> list[str]:
    """Why N instances of the triggered ability ``d`` (of this source) can't be resolved as one folded ability now (public reasons;
    empty: they can). See the section comment above."""
    kinds = _kinds(plan, d, source_card, source_object, recipes)
    if isinstance(kinds, str):
        return [kinds]
    out = _ability_readers(plan)
    sels = _cond_sels(d)
    for spec, ch, recipe in kinds:
        with _probe(plan, controller, spec) as probe:
            if probe is None:
                out.append("its token can't be read")
                continue
            pch = ch or plan.ch(probe)
            if any(_matches(plan, key, probe, pch, controller, source_card) for key in sels):
                out.append("the tokens it makes would change its condition")  # 603.4, 608.2c: the N checks could differ
            if "Legendary" in pch.supertypes and not any(dd.get("static") == "no_legend_rule" and dd.get("scope") in ("creatures", "all", "permanents", "tokens")
                                                         for dd in _defs(pch).values()):
                out.append("its legendary tokens would follow the legend rule one at a time")  # 704.5j between the resolutions
            out += _next_entry_waiting(plan, probe, pch)  # -- token stack folds review (wave TS2R) --
            pdefs = _defs(pch)
            for ab in pch.abilities:
                if ab.kind == "triggered" and fold_shape(pdefs.get(ab.index)) is None:
                    out.append(f"each token it makes has the ability “{ab.text}”")  # (it would trigger between the resolutions)
            audit = _Audit(plan, [probe.id], {probe.id: pch}, fold=True)
            why = audit.observer_problem(probe, pch)
            if why is not None:
                out.append(why)
            out += problems(plan, [probe.id], chs={probe.id: pch}, recipes={probe.id: recipe} if recipe is not None else None, fold=True)
    return list(dict.fromkeys(out))


# -- token stack folds review (wave TS2R) --
def _next_entry_waiting(plan: Plan, probe: CardInstance, pch: Characteristics) -> list[str]:
    """One-shot replacement effects of resolved spells waiting for "the next time one or more … enter this turn" (614.5, 614.12): the
    first of the N creation events uses one up, so one event of N·k tokens would give all of them what only the first k get. Mystic
    Reflection (``TurnLog.mirror110b``: they enter as copies of the chosen creature), Storyweave (an ``entry_once110e`` effect: two
    additional +1/+1 counters). Both are public (a resolved spell's effect)."""
    out: list[str] = []
    log = plan.rules.turn_log
    if log.turn == plan.state.turn.number and log.mirror110b and (pch.is_creature or "Planeswalker" in pch.types):
        out.append("Mystic Reflection waits for the next creatures to enter (only the first of the resolutions would be copies)")
    for fx in plan.rules.effects:
        if fx.entry_once110e and (not fx.who or _matches(plan, fx.who, probe, pch, fx.controller, fx.source_card)):
            out.append(f"{fx.label or 'an effect'} waits for the next of these to enter (only the first of the resolutions would get it)")
    return out


def fold_problems_once(plan: Plan, controller: str, d: dict[str, Any], source_card: str | None, source_object: str | None, *,
                       recipes: dict[str, Any] | None = None) -> list[str]:
    """``fold_problems``, worked out once per read pass for each kind of source (the stacks and identical permanents of a big board
    share it: the same definition, controller and copiable values)."""
    from app.rules import read_pass

    sels = _cond_sels(d)
    own = source_card if any('"other"' in s or '"self"' in s or "another" in s for s in sels) else None
    key = ("ts2_fold", controller, json.dumps(d, sort_keys=True), _fingerprint(_source_recipe(plan, source_card, source_object, recipes)), own)
    return list(read_pass.once(plan.state, plan.info, key,
                               lambda: tuple(fold_problems(plan, controller, d, source_card, source_object, recipes=recipes))))


def _ability_readers(plan: Plan) -> list[str]:
    """Public abilities that could see how many triggered abilities there are or what is on the stack ("whenever an ability triggers",
    "counter target triggered ability" on a permanent): a fold puts one object on the stack for N. Trigger multipliers (603.2d) are read
    exactly (they act on each instance as it triggers). Hidden cards are never read: a target choice that names a folded ability splits
    one instance off (single_out)."""
    from app.rules import oracle

    out: list[str] = []
    for key, ids in plan.state.zones.items():
        zone = key.split(":")[-1]
        if zone not in ("battlefield", "stack", "command", "graveyard", "exile"):
            continue
        for cid in ids:
            card = plan.state.cards.get(cid)
            if card is None or card.face_down or card.ability is not None or not plan.in_game(card):
                continue
            if zone == "command" and not (card.token and card.token.type_line == "Emblem"):
                continue
            ch = plan.ch(card)
            if not any(ab.kind != "keywords" and _ABILITY_WORDS.search(ab.text) for ab in ch.abilities):
                continue
            defs = _defs(ch)
            for ab in ch.abilities:
                if ab.kind == "keywords" or not _ABILITY_WORDS.search(oracle.strip_reminders(ab.text)):
                    continue
                dd = defs.get(ab.index) or {}
                if dd.get("static") == "trigger_multiplier" and dd.get("cause") == "enter":
                    continue
                if zone in ("graveyard", "exile", "stack") and ab.kind not in ("triggered", "static"):
                    continue
                out.append(ch.name or card.name)
    return out


def _weight_of(plan: Plan, t: Any) -> int:
    """How many identical instances this pending trigger stands for: a stack's members each triggered (603.2c)."""
    src = plan.state.cards.get(t.source_card or "")
    if src is None or not src.is_token or src.quantity <= 1:
        return 1
    if plan.oid(src) != t.source_object:
        raise StackGate(f"{label(src)} triggered, and the engine can't tell how many of its members did.")
    return src.quantity


def fold_pending(plan: Plan) -> None:
    """Before triggered abilities go on the stack (603.3b): fold each group of identical foldable triggers of one controller (and a
    stack's members' instances) into one "Name (×N)". A stack whose triggers can't fold triggers once per member (up to
    INDIVIDUAL_LIMIT, else the action stops: StackGate)."""
    r = plan.rules
    shapes = {t.id: fold_shape(t.ability) is not None for t in r.pending_triggers if not t.ordered and "fold" not in t.ability}
    if not any(shapes.values()):
        return
    with plan.reading():
        r.pending_triggers = _folded_pending(plan, shapes)


def _folded_pending(plan: Plan, shapes: dict[str, bool]) -> list[Any]:
    import secrets

    r = plan.rules
    out = list(r.pending_triggers)
    for controller in dict.fromkeys(t.controller for t in r.pending_triggers):
        mine = [t for t in r.pending_triggers if t.controller == controller]
        if not any(shapes.get(t.id) for t in mine):
            continue
        alone = all(shapes.get(t.id) for t in mine)  # (603.3b: another trigger to order among them: no fold)
        groups: dict[tuple[str, str], list[Any]] = {}
        for t in mine:
            if shapes.get(t.id):
                fp = _fingerprint(_source_recipe(plan, t.source_card, t.source_object))
                plain = {k: v for k, v in t.ability.items() if k != "members"}
                groups.setdefault((json.dumps(plain, sort_keys=True), fp), []).append(t)
        alone = alone and not _crossed(plan, controller, list(groups.values()))
        for (_, fp), group in groups.items():
            weights = [int(t.ability.get("members") or 0) or _weight_of(plan, t) for t in group]
            w = sum(weights)
            if w <= 1:
                continue
            rep = group[0]
            d = {k: v for k, v in rep.ability.items() if k != "members"}
            why = ["another triggered ability to order among them"] if not alone else [] if fp else ["its source's copiable values aren't known"]
            why = why or fold_problems_once(plan, controller, d, rep.source_card, rep.source_object)
            if not why:
                sources = list(dict.fromkeys((t.source_card, t.source_object) for t in group))
                folded = rep.model_copy(update={"ability": folded_ability(d, w, rep.name, sources),
                                                "name": f"{rep.name} (×{w:,})"}, deep=True)
                at = out.index(rep)
                out = [x for x in out if x not in group]
                out.insert(min(at, len(out)), folded)
                continue
            for t, n in zip(group, weights, strict=True):  # 603.2c: each member's own trigger
                if n <= 1:
                    continue
                if n > INDIVIDUAL_LIMIT:
                    raise StackGate(f"{rep.name}'s ability would trigger {n:,} times, one at a time ({'; '.join(why)}).")
                at = out.index(t)
                one = {**t.ability, "members": 1}
                out[at:at + 1] = [t.model_copy(update={"id": t.id if i == 0 else secrets.token_hex(4), "ability": one}, deep=True)
                                  for i in range(n)]
    return out


def folded_ability(d: dict[str, Any], w: int, name: str, sources: list[tuple[str | None, str | None]]) -> dict[str, Any]:
    """The ability ``w`` instances of ``d`` fold into: each creation makes w times as many, after a resolution check (fold_check)."""
    effects = [{**e, "n": int(e["n"]) * w} if e.get("do") in ("create_token", "token_copy") else e for e in d.get("effects") or []]
    check = {"do": "fold_check", "def": d, "w": w, "name": name, "sources": [list(s) for s in sources]}
    return {**d, "effects": [check, *effects], "fold": w}


def fold_check(plan: Plan, ctx: Any, e: dict[str, Any]) -> bool:
    """As a folded ability resolves: still exact? Its sources have the same copiable values as when it triggered (or as they last
    existed, 608.2h), and fold_problems finds nothing (something may have arrived in response). Otherwise the action is refused: the
    instances can't be taken apart again here (docs/TOKEN_STACKS.md 9)."""
    d = e["def"]
    src_card, src_oid = ctx.get("source_card"), ctx.get("source_object")
    with plan.reading():
        why = fold_problems_once(plan, ctx["controller"], d, src_card, src_oid)
        if any(m.get("do") == "token_copy" for m in fold_shape(d) or []):
            fp = _fingerprint(_source_recipe(plan, src_card, src_oid))
            if not fp or any(_fingerprint(_source_recipe(plan, c, o)) != fp for c, o in e.get("sources") or []):
                why.append("its sources no longer have the same copiable values")
    if why:
        raise ActionError(f"{e.get('name') or 'This'} (×{int(e['w']):,}) stands for {int(e['w']):,} identical triggered abilities, and the "
                          f"engine can't resolve them together exactly any more ({'; '.join(why)}). Pause automation and resolve them by hand.")
    return True


def _fold_of(plan: Plan, card_id: str) -> dict[str, Any] | None:
    entry = plan.rules.stack.get(card_id)
    effects = entry.effects if entry is not None else []
    first = effects[0] if effects else None
    return first if isinstance(first, dict) and first.get("do") == "fold_check" and int(first.get("w", 1)) > 1 else None


def folds_on_stack(plan: Plan) -> bool:
    return any(_fold_of(plan, cid) is not None for cid in plan.state.zones.get("stack", []))


def single_out_fold(plan: Plan, card_id: str) -> None:
    """A choice names a folded ability (a target: "counter target triggered ability", "copy target triggered ability"): it means one
    of the N identical instances. ``card_id`` keeps one instance; the other N-1 become a new ability object above it (they are
    identical and next to each other on the stack, so which one was named doesn't matter). Only for the topmost object: placing the
    rest anywhere else isn't modelled, so the action is refused."""
    from app.game.rules_state import StackEntry

    fold = _fold_of(plan, card_id)
    if fold is None:
        return
    stack = plan.state.zones.get("stack", [])
    entry = plan.rules.stack[card_id]
    if not stack or stack[-1] != card_id:
        raise ActionError(f"{entry.name} stands for {int(fold['w']):,} identical triggered abilities, and the engine can only single one "
                          f"of them out while it is on top of the stack. Pause automation to do this by hand.")
    w, d, name = int(fold["w"]), fold["def"], str(fold.get("name") or entry.name)
    source = entry.source_card if entry.source_card in plan.state.cards else None
    created = plan.do({"type": "create_ability", "text": f"{name} (×{w - 1:,})’s ability", "source_id": source, "kind": "triggered"},
                      actor=entry.controller)
    new_ids = getattr(created, "r", None)
    if new_ids is None or not new_ids.ids:
        raise ActionError(f"{entry.name} couldn't be split.")
    rest = folded_ability(d, w - 1, name, fold.get("sources") or []) if w - 1 > 1 else d
    one: dict[str, Any] = d
    plan.rules.stack[new_ids.ids[0]] = StackEntry.model_validate({**entry.model_dump(), "effects": rest["effects"],
                                                                  "name": f"{name} (×{w - 1:,})" if w - 1 > 1 else name})
    plan.rules.stack[card_id] = StackEntry.model_validate({**entry.model_dump(), "effects": one["effects"], "name": name})


# -- formation ----------------------------------------------------------------------------------------------------------------------
def may_stack(plan: Plan, player: str, token: dict[str, Any]) -> str | None:
    """Could ``count`` tokens of ``token`` be made as one stack for ``player`` now? None: yes; else why not (public).
    (-- token stack folds (wave TS2) -- a token copy, ``_copy``: judged with the copiable values it will have, 707.2.)"""
    from app.game.rules_state import CopyRecipe

    recipe = CopyRecipe.model_validate(token["_copy"]) if token.get("_copy") else None
    if token.get("_copy"):
        why = _copy_problem(plan, recipe)
        if why is not None:
            return why
    with _probe(plan, player, token) as probe:
        if probe is None:
            return "the token can't be read"
        if recipe is None:
            found = problems(plan, [probe.id])
        else:
            from app.rules import copying

            found = problems(plan, [probe.id], chs={probe.id: copying.characteristics(recipe, plan.info)}, recipes={probe.id: recipe})
    return "; ".join(found) if found else None


def _forget_probe(plan: Plan, card_id: str) -> None:
    from app.rules import read_pass

    current = read_pass.current(plan.state, plan.info)
    if current is not None:
        plan.writes = getattr(plan, "writes", 0) + 1  # (a kept read pass saw the probe: read afresh)


def refusal(cards: list[CardInstance], why: list[str]) -> str:
    what = ", ".join(label(c) for c in cards)
    return (f"{what} is too big for the rules engine to handle one token at a time, and it can't treat the stack exactly here "
            f"({'; '.join(why)}). Pause automation and do this by hand: the table can split, move and remove tokens from the stack.")


def gate(plan: Plan, *, force_spread: bool = False) -> None:
    """Before an intent: keep each stack the audit accepts, spread the small ones it doesn't, refuse when a big one can't stay."""
    spread(plan, limit=STACK_FROM)  # (small stacks, e.g. made by hand in the sandbox: one object per token, as always)
    ids = stacks(plan.state)
    if not ids:
        return
    why = ["the engine had to treat it as one token"] if force_spread else problems(plan, ids)
    if not why:
        plan.stack_watch = True
        return
    big = [plan.state.cards[cid] for cid in ids if plan.state.cards[cid].quantity > INDIVIDUAL_LIMIT]
    if big:
        raise ActionError(refusal(big, why))
    spread(plan)


def check_new(plan: Plan) -> None:
    """During an intent, after an object appeared or changed control: the stacks must still pass the audit."""
    ids = stacks(plan.state)
    if ids:
        why = problems(plan, ids)
        if why:
            raise StackGate("; ".join(why))
