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
    if not stacks(plan.state):
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
    for ab in ch.abilities:
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
    def __init__(self, plan: Plan, stack_ids: list[str]) -> None:
        self.plan = plan
        self.stacks = [(plan.state.cards[cid], plan.ch(plan.state.cards[cid])) for cid in stack_ids]
        self.words = tuple(sorted({w for _, ch in self.stacks for w in _words(ch)}))

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
            if kind == "triggered":
                trigger = {k: v for k, v in d.items() if k not in ("kind", "effects", "optional", "target")}
                if trigger.get("trigger") in _PHASE_TRIGGERS and set(trigger) == {"trigger"} or trigger.get("trigger") == "enters_self" and set(trigger) == {"trigger"}:
                    pass
                elif trigger.get("trigger") == "enters_other" and set(trigger) <= {"trigger", "filter"} and not d.get("optional") \
                        and d.get("target") is None and all(isinstance(e, dict) and e.get("do") in ("gain_life", "lose_life", "draw")
                                                            for e in d.get("effects") or []):
                    pass  # 603.2c: one trigger per member that entered (triggers._other_enters reads token_stacks.weight)
                elif not self.blind(trigger):
                    return False
            if not _cost_ok(d.get("cost"), self.words):
                return False
            return all(isinstance(e, dict) and self.effect_ok(e, observer) for e in d.get("effects") or [])
        return self.blind(d)

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


def problems(plan: Plan, stack_ids: list[str] | None = None) -> list[str]:
    """Why the engine can't treat the stacks (``stack_ids``, default every stack) exactly right now: public names only. Empty: it can.

    Read: each stack itself; every other permanent; everything on the stack; emblems; the abilities of graveyard and face-up exile cards;
    the rules records that react to future events. Hidden cards are never read (a refusal that depended on one would reveal it)."""
    ids = stacks(plan.state) if stack_ids is None else [cid for cid in stack_ids if cid in plan.state.cards]
    if not ids:
        return []
    out: list[str] = []
    for cid in ids:
        stack = plan.state.cards[cid]
        why = _stack_problem(plan, stack, plan.ch(stack))
        if why is not None:
            out.append(f"{label(stack)}: {why}")
    audit = _Audit(plan, ids)
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


# -- formation ----------------------------------------------------------------------------------------------------------------------
def may_stack(plan: Plan, player: str, token: dict[str, Any]) -> str | None:
    """Could ``count`` tokens of ``token`` be made as one stack for ``player`` now? None: yes; else why not (public)."""
    from app.game.state import TokenDef, zone_key

    spec = {k: v for k, v in token.items() if not k.startswith("_")}
    try:
        tdef = TokenDef.model_validate({**spec, "name": spec.get("name") or "Token"})
    except Exception:  # noqa: BLE001
        return "the token can't be read"
    probe = CardInstance(id="__stack_probe__", name=tdef.name, owner=player, controller=player, zone=zone_key(player, "battlefield"),
                         is_token=True, token=tdef, quantity=2, card_id=tdef.card_id)
    plan.state.cards[probe.id] = probe
    plan.state.zone(probe.zone).append(probe.id)
    try:
        found = problems(plan, [probe.id])
    finally:
        plan.state.zone(probe.zone).remove(probe.id)
        del plan.state.cards[probe.id]
        _forget_probe(plan, probe.id)
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
