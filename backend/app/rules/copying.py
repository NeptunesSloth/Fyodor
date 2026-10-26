"""The copy system (CR 707, 613.2 layer 1), researched against CR 2026-09-25.

One model for every kind of copy: a **recipe** (``CopyRecipe``, app/game/rules_state.py) — the
printed values of a card (the face that is up, 707.8) or the values a token's creating effect
defined (111.3), then each copy effect's exceptions in order (707.9). Never a snapshot of a live
object: counters, status and non-copy effects aren't copied (707.2), a later change to the
original doesn't reach the copy (707.2b), and a copy of a copy starts from the first copy's recipe
and adds its own exceptions (707.3).

* **Layer 1** (613.2): a copy effect is a ``ContinuousEffect`` with ``layer="1"`` and ``copy`` set,
  locked to the objects it affects (400.7); the latest by timestamp gives an object's copiable
  values (613.2a, 613.7). A face-down object keeps its face-down characteristics (613.2b, 708.2).
  :func:`layer1` is the first step of ``app.rules.layers.derive``; ``layers.copiable`` stops there
  (613.2c) and is what static abilities are read from, so a copy of an anthem works.
* **Copies of spells and abilities** (707.10): real stack objects. A spell copy is a card object on
  the stack (the ``copy_card`` table action: a spell, owned and controlled by the player who put it
  there, targetable and counterable like any spell); an ability copy is an ability object with the
  original's source (707.10b). Each gets a copy of the original's ``StackEntry``: its modes (700.2g),
  targets and their division (601.2d, 115.7f), X, kicker (702.33d), a triggered ability's trigger
  event. A copy isn't cast (no cast triggers, not counted by storm); the objects used to pay the
  original's costs are the copy's too, the mana isn't (707.10). "You may choose new targets"
  (707.10c, 115.7d): for each target, keep it (even if illegal now) or choose a new legal one; a
  division stays as announced (115.7f); the final set must obey 115.3 and "another target", else
  the choice starts over. A copy of a permanent spell becomes a token as it resolves (608.3f,
  707.10f). "Can't be copied" (113.6g) is obeyed. Storm (702.40) uses this path.
* **Token copies** ("create a token that's a copy of …"): one helper, :func:`token_copy_request`,
  on the token choke point (``replace.create_token_batch``: the ``create_token`` table action, then
  the entry replacements of app/rules/replacements.py), with the copy effect on each token before
  anything looks at it; a 616.1 order prompt pauses :func:`token_copy`, which runs again with it.
* **Entering as a copy** (707.5, 614.1c, 614.12a): a replacement effect whose choice is made
  before the permanent enters (:func:`entering`, called by ``replacements.entry_plan``); the
  permanent's other entry replacements are then read from the copied text (707.5), its "as
  enters" choices are made anew (707.6) and its enters abilities trigger. The copy effect is
  locked to the object the card becomes on the battlefield.
* **Becoming a copy** (707.4): a layer-1 effect on a permanent already there: no enters or leaves
  abilities trigger, and its other effects keep applying.

Refused — the engine asks for the copy to be made by hand, never guesses: face-down sources
(707.2, 708.2), melded or reversible sources of token copies and of permanent-spell copies
(707.8a, 712.8g), Aura spells, "for each player or object it could target" (707.10d), a copy
that specifies its new target (707.10e), casting a copy (707.12), Garth One-Eye and Magar of the
Magic Strings (707.13-707.14), exceptions that are additional effects of a token or a "becomes"
copy (707.9e: only an object entering as a copy "enters with" more) and copies of
linked abilities (707.7) — the grammar doesn't read those wordings, so the cards stay manual.

-- copy exceptions (wave 24A) -- 707.9: ``CopyExcept`` also carries the card types an exception sets ("it's an artifact", "it loses all
other card types", 707.9b), abilities gained only if the result is a creature / planeswalker (707.9f: Moritte), "it doesn't copy that
creature's color" (707.9c: the object's own colors, ``keep_colors``) and — read only for an object entering as a copy — "it enters with
an additional +1/+1 counter on it [if it's a creature]" (707.9e: an additional effect of the replacement, kept on the definition and
applied by ``entry_counters`` through ``replacements.entering_counters``; never a copiable value; the engine applies no later copy effect
as it enters, so they always happen). A character card's "he's / his name is" is read like "it". "Becomes a copy" accepts "another" / "up to one other"
targets, the object a trigger or earlier instruction names ("it", "that creature": as it last existed when it left, 608.2h), a card in a
graveyard (its printed values, 707.2) and a group ("each other creature [you control]", ``parse_become_group``: one effect on the group as
it is as it begins, 611.2c). "Enter as a copy of a creature card in a graveyard" reads public cards only.

-- becomes a copy (wave 31C) -- the duration may be "until your next turn" (500.4: ``ContinuousEffect.duration == "next_turn"``) and may lead the
sentence; the subject may be "it" or a target ("Target artifact you control becomes a copy of a second / another target artifact …", two target
groups: ``parse_become_targets``; the second may be a card in a graveyard or exile, its printed values, 707.2); "this ability" is written into the
copy with the card's name as "this permanent" (a copy has another name, so "Volrath becomes …" would name a stranger) and "its other abilities"
(Sakashima of a Thousand Faces) as the card's other lines that don't name it (707.9a).

-- refused copy/mana (wave 3R3) -- now automated: a token copy or a permanent spell's copy of a
transforming or modal double-faced object is a double-faced token (707.8a, 707.10g:
``TWO_FACED_TOKENS``); "copy that spell" / "copy it" in a cast trigger (the event's spell); the
"spell_copied" event feeds magecraft ("Whenever you cast or copy …", app/rules/events.py). Still
refused, with the reason: 707.10d/e need a target-legality check per player or object across
every word "target" and a per-copy target assignment (Zada, Ink-Treader Nephilim, Frontline
Heroism); 707.12 casts the copy mid-resolution from the card's zone (601.2a-h inside a resolving
ability: the casting path can't pause there yet; Mizzix's Mastery, Kaervek); 707.13-14 copy a
card by name from outside the game or a noted name (Garth One-Eye, Magar: no object to read);
707.7 linked abilities of a copy (the "exiled with" link would have to move to the copy); a cast
trigger's "first <type> spell each turn" (Double Vision) needs a per-type spell count this turn.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Literal

from app.game.rules_state import (
    ENTERING_COPY,
    CopyEntrySource,
    CopyExcept,
    CopyRecipe,
    DecisionOption,
    StackEntry,
    StackMemory,
    TargetRef,
    copy_recipe_of,
    emit,
)
from app.game.state import CardInstance, TokenDef
from app.rules import characteristics as chars
from app.rules.characteristics import CardInfo, Characteristics
from app.rules.oracle import parse_abilities, strip_reminders

if TYPE_CHECKING:
    from app.game.rules_state import ContinuousEffect, RulesState
    from app.game.state import GameState
    from app.rules.plan import Plan

Context = dict[str, Any]
Job = dict[str, Any]
Position = tuple[str, int, int]  # ("plain" | "slot" | "group", slot or group, index)

ENTERING = ENTERING_COPY  # ContinuousEffect.source of the copy effect of a permanent entering as a copy
TO_COPY = " to copy"  # the end of an "enter as a copy" choice's name ("creature to copy")
NONE = "none"  # the answer "copy nothing" (the permanent enters as itself)
DOUBLE_FACED = ("transform", "modal_dfc", "meld", "reversible_card")
# -- refused copy/mana (wave 3R3) -- 707.8a / 707.10g: a token copy (or a permanent spell's copy) of a transforming
# or modal double-faced object is a double-faced token: each face's values are the same face's of the original, and
# it is created with the face up that the original has up. The token is the original's printing with that face
# (``token_copy`` turns it over as needed); its copy effect follows the face that is up (``layer1``). Melded
# permanents (712.8g, a meld pair's combined face) and reversible cards stay refused.
TWO_FACED_TOKENS = ("transform", "modal_dfc")
_CH_CACHE: dict[str, Characteristics] = {}
_CH_MAX = 4000


# -- recipes and characteristics (707.2, 707.9, 613.2) ---------------------------------------------
def base_recipe(card: CardInstance) -> CopyRecipe:
    """The copiable values of an object no copy effect applies to: its printed values (the face
    that is up, 707.8) or, for a token without a printing, what its creating effect defined (111.3)."""
    token = None
    if card.token is not None and not card.card_id:
        t = card.token
        token = {"name": t.name, "power": t.power, "toughness": t.toughness, "colors": list(t.colors),
                 "type_line": t.type_line, "text": t.text, "mana_cost": t.mana_cost}
    return CopyRecipe(printing=card.card_id, face=card.face, token=token, source=card.name[:200])


def recipe_of(plan: Plan, card: CardInstance) -> CopyRecipe:
    """707.2 / 707.3: this object's copiable values as a recipe to copy from — the recipe of the
    copy effect that applies to it (with that effect's exceptions), else its printed values."""
    from app.rules import (
        prototype,  # -- casting extras (wave 18E) -- 718.3c-d: a prototyped object's copy is prototyped too
    )

    found = copy_recipe_of(plan.rules, plan.oid(card))
    recipe = found.model_copy(deep=True) if found is not None else base_recipe(card)
    return recipe.model_copy(update={"prototyped": True}) if prototype.is_prototyped(plan.state, card) else recipe


def with_excepts(recipe: CopyRecipe, excepts: list[CopyExcept]) -> CopyRecipe:
    """The recipe of a copy made with these exceptions (707.9a-b: they join the copiable values)."""
    kept = [ex for ex in excepts if ex != CopyExcept()]
    return recipe.model_copy(update={"excepts": [*recipe.excepts, *kept]}) if kept else recipe


def characteristics(recipe: CopyRecipe, info: CardInfo) -> Characteristics:
    """The characteristics a recipe defines: its base, then each exception in order (707.9)."""
    key = recipe.model_dump_json()
    hit = _CH_CACHE.get(key)
    if hit is not None:
        return hit
    ch = _base(recipe, info)
    for ex in recipe.excepts:
        ch = _apply(ch, ex)
    if len(_CH_CACHE) > _CH_MAX:
        _CH_CACHE.clear()
    _CH_CACHE[key] = ch
    return ch


def _base(recipe: CopyRecipe, info: CardInfo) -> Characteristics:
    if recipe.printing:
        data = info.get(recipe.printing)
        if data is not None:
            ch = chars.printed_from_data(data, recipe.face)
            if recipe.prototyped:  # -- casting extras (wave 18E) -- 718.2a
                from app.rules import prototype

                ch = prototype.overlay(ch)
            # -- review (casting) -- 202.3b / 712.8e: a copy of the back face of a transforming double-faced object has mana
            # value 0 (the printed back face reads its front face's cost only for the card itself, 712.8e)
            return replace(ch, mana_value=0.0) if recipe.face and data.get("layout") == "transform" else ch
    if recipe.token is not None:
        t = recipe.token
        probe = CardInstance(id="copy-probe", owner="", controller="", zone="", is_token=True,
                             token=TokenDef(name=str(t.get("name") or ""), power=t.get("power"), toughness=t.get("toughness"),
                                            colors=list(t.get("colors") or []), type_line=str(t.get("type_line") or ""),
                                            text=str(t.get("text") or ""), mana_cost=str(t.get("mana_cost") or "")))
        return chars.of(probe, info)
    return Characteristics(name=recipe.source)  # (unknown to the card database: typeless, as chars.of)


def renamed(text: str, old: str, new: str) -> str:
    """-- copied names (review 31) -- 201.5: "Text that refers to the object it's on by name means just that particular object …
    regardless of any name changes": a copy "except its name is …" (Sakashima the Impostor, Chameleon) reads the copied text's
    own name (its full name, the part before a comma, its 201.5c short name) as its new name, the way 201.5b treats a gained
    ability's. One pass, so a new name holding the old short name isn't renamed again; "a token named …" is another object."""
    from app.rules.scripts import _short_name

    short = _short_name(old, text)
    names = sorted({n for n in (old, old.split(",")[0].strip(), short) if n and len(n) >= 3}, key=len, reverse=True)
    if not names:
        return text
    alts = "|".join(re.escape(n) + (r"(?! (?:the|of) [A-Z])" if n == short else "") for n in names)
    # A fixed card/token name can contain the source's short name without
    # referring to the source (e.g. Hammer of Nazahn on Nazahn).
    parts = re.split(r"(?:(?<=token named )|(?<=tokens named )|(?<=card named )|(?<=cards named ))((?:[A-Z][\w'\-]*)(?: (?:(?:of|the|and|in) )?[A-Z][\w'\-]*)*)", text)
    return "".join(part if i % 2 else re.sub(rf"(?<![\w-])(?<!named )(?:{alts})(?!\w)", lambda _: new, part)
                   for i, part in enumerate(parts))


def _apply(ch: Characteristics, ex: CopyExcept) -> Characteristics:
    """One copy effect's exceptions (707.9a-d)."""
    from app.rules import scripts
    from app.rules.layers import _subtype_fits

    kept = [a for a in ch.abilities if not a.intrinsic]
    supertypes = (ch.supertypes | frozenset(ex.add_supertypes)) - frozenset(ex.remove_supertypes)
    types = (frozenset(ex.set_types) if ex.set_types is not None else ch.types) | frozenset(ex.add_types)  # (wave 24A: 707.9b)
    gained = [*ex.add_text, *(t for ty, ts in ex.text_if.items() if ty in types for t in ts)]  # (707.9f: as the copy would be)
    rewrite = bool(gained)
    if ex.remove_keywords:
        kept = [_without_keywords(a, set(ex.remove_keywords)) for a in kept]
        kept = [a for a in kept if a.text]
        rewrite = True
    if ex.power is not None or ex.toughness is not None:
        # 707.9d: a characteristic-defining ability that defines the power and toughness isn't copied
        cda = {i for i, d in scripts.definitions(ch).items() if d.get("static") == "cda"}
        if cda:
            kept = [a for a in kept if a.index not in cda]
            rewrite = True
    subtypes = frozenset(s for s in ch.subtypes | frozenset(ex.add_subtypes) if _subtype_fits(s, types))
    if ex.set_creature_types is not None:  # -- token copies & attach on entry (wave 5J) -- 205.1a, 707.9d
        from app.rules.creature_types import CREATURE_TYPES

        subtypes = frozenset(s for s in (subtypes - CREATURE_TYPES) | frozenset(ex.set_creature_types) if _subtype_fits(s, types))
        dropped = {"changeling", *(["devoid"] if ex.set_colors is not None else [])}
        if any(a.kind == "keywords" and dropped & set(a.keywords) for a in kept):
            kept = [_without_keywords(a, dropped) for a in kept]
            kept = [a for a in kept if a.text]
            rewrite = True
        every = f"{ch.name} is every creature type."  # (Mistform Ultimus: the same CDA, 604.3)
        if any(a.kind == "static" and a.text.startswith(every[:-1]) for a in kept):
            kept = [a for a in kept if not (a.kind == "static" and a.text.startswith(every[:-1]))]
            rewrite = True
    own = [a.text for a in kept]
    if ex.name is not None and ch.name and ex.name != ch.name:  # -- copied names (review 31) -- 201.5: the copied text's own name is this object
        was, own = own, [renamed(t, ch.name, ex.name) for t in own]
        rewrite = rewrite or own != was
    text = "\n".join([*own, *gained]) if rewrite else ch.oracle_text
    if rewrite:
        abilities = chars.with_intrinsic_mana(parse_abilities(text, spell=bool(types & {"Instant", "Sorcery"})), subtypes)
    elif subtypes != ch.subtypes:
        abilities = chars.with_intrinsic_mana(kept, subtypes)
    else:
        abilities = ch.abilities
    cost: dict[str, Any] = {"mana_cost": "", "mana_value": 0} if ex.no_mana_cost else {}  # (wave 15E: 707.9b)
    return replace(ch, **cost, name=ex.name if ex.name is not None else ch.name, supertypes=supertypes, types=types,
                   subtypes=chars.changeling(subtypes, abilities, ex.name if ex.name is not None else ch.name),
                   power=ex.power if ex.power is not None else ch.power,
                   toughness=ex.toughness if ex.toughness is not None else ch.toughness,
                   loyalty=str(ex.loyalty) if ex.loyalty is not None else ch.loyalty,
                   colors=(frozenset(ex.set_colors) if ex.set_colors is not None else ch.colors) | frozenset(ex.add_colors),
                   oracle_text=text, abilities=abilities, oracle_id=None if rewrite else ch.oracle_id)


def _without_keywords(a: Any, dropped: set[str]) -> Any:
    """-- token copies & attach on entry (wave 5J) -- a keyword line without these keywords (707.9d: a
    characteristic-defining ability for a characteristic the copy effect sets isn't copied); "" if none is left."""
    if "epic" in dropped and a.text == "Epic":
        return replace(a, text="")
    if a.kind != "keywords" or not dropped & set(a.keywords):
        return a
    from app.rules.oracle import strip_reminders

    parts = [p.strip() for p in re.split(r"[,;]\s*", strip_reminders(a.text)) if p.strip()]
    left = [p for p in parts if p.lower() not in dropped]
    return replace(a, text=", ".join(left))


def type_line(ch: Characteristics) -> str:
    left = " ".join([*sorted(ch.supertypes), *sorted(ch.types)])
    return f"{left} — {' '.join(sorted(ch.subtypes))}" if ch.subtypes else left


# -- layer 1 (613.2) ------------------------------------------------------------------------------
def layer1(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> Characteristics:
    """613.2a: the copy effect that applies to the object gives its copiable values (the latest
    by timestamp, 613.7); 613.2b: a face-down object keeps its face-down characteristics (708.2),
    which ``characteristics.of`` already gave. ``ch`` is the object's printed (or defined) values."""
    return with_level(state, card, _layer1(state, card, ch, info), info)


def with_level(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None = None,
               oid: str | None = None, printing: str | None = None) -> Characteristics:
    """-- Class (wave 16A) -- 716.2b: the object's own class level (never a copied one; 716.2d: none is level 1), so that
    ``scripts.definitions`` leaves out the abilities under a level bar it hasn't reached.
    -- Rooms (wave 18G) -- 709.5c: likewise the doors the object itself has unlocked (designations aren't copiable); on the
    stack only the half that was cast counts (709.3a); off the table both halves are there. ``oid`` / ``printing``: an object
    as it last existed (603.10a, 608.2h: its own designations then, and the card it was a copy of)."""
    r = state.rules
    if r is None:
        return ch
    oid = oid or r.object_id(card.id)
    if ch.doors is not None and info is not None:
        data = info.get(printing or room_printing(r, card, oid))
        if data is None or not chars.room(data):
            return ch
        if card.zone.endswith(":battlefield"):
            doors = frozenset(r.unlocked.get(oid, ()))
        else:
            doors = frozenset({card.face + 1}) if card.zone == "stack" else ch.doors
        return chars.with_doors(ch, data, doors)
    if ch.doors is None and any(a.section > 1 for a in ch.abilities):
        ch = replace(ch, level=r.levels.get(oid, 1))
    if any(a.linked for a in ch.abilities):  # -- linked words (wave 33B) -- 607.2f: the word it chose as it entered (none: no linked ability)
        ch = replace(ch, word=r.chosen_words.get(oid) or (card.choices.get("Chosen word", "") if card.zone.endswith(":battlefield") else ""))
        # (a permanent put onto the battlefield by hand made no choice the rules recorded: the table's "Chosen word" entry stands in, as for a color)
    return ch


def room_printing(r: RulesState, card: CardInstance, oid: str) -> str:
    """-- Rooms (review 18G) -- the card whose halves the object has: the one it copies (707.2, 709.5b), else its own."""
    recipe = copy_recipe_of(r, oid)
    return recipe.printing if recipe is not None and recipe.printing else card.card_id or ""


def _layer1(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> Characteristics:
    r = state.rules
    if r is None or not r.effects or info is None or card.face_down:
        return ch
    recipe = copy_recipe_of(r, r.object_id(card.id))
    if recipe is not None and card.is_token and recipe.printing and recipe.printing == card.card_id \
            and card.face != recipe.face and (info.get(card.card_id) or {}).get("layout") in TWO_FACED_TOKENS:
        recipe = recipe.model_copy(update={"face": card.face})  # (wave 3R3: 707.8a, the face that is up)
    if recipe is not None and recipe.printing and (info.get(recipe.printing) or {}).get("layout") == "flip":
        # (review 24C) 707.3, 110.5c: a copy of a flip card takes both halves; which one applies is the copy's own flipped status
        recipe = recipe.model_copy(update={"face": 1 if card.flipped and card.zone.endswith(":battlefield") else 0})
    return ch if recipe is None else characteristics(recipe, info)


def copy_index(rules: RulesState | None) -> dict[str, tuple[int, str]]:
    """Object id → (timestamp, recipe) of the latest copy effect that applies to it (for caches keyed
    by what's on the battlefield: a copy effect changes an object's abilities, 613.2a). The recipe is
    part of the key: after an undo, a new choice can reuse the same object id and timestamp."""
    out: dict[str, tuple[int, str]] = {}
    if rules is None:
        return out
    for e in rules.effects:
        if e.layer == "1" and e.copy_recipe is not None:
            for oid in e.affected:
                if oid not in out or e.timestamp >= out[oid][0]:
                    out[oid] = (e.timestamp, e.copy_recipe.model_dump_json())
    return out


def lki(plan: Plan, snap: Any, ch: Characteristics) -> Characteristics:
    """An object's last known information (608.2h) with its copiable values as they were: a dying
    Clone has the copied abilities (603.10a). ``snap`` is its ObjectSnapshot."""
    recipe = getattr(snap, "copy_recipe", None)
    if recipe is None or snap.face_down:
        return ch
    return characteristics(recipe, plan.info)


def add_copy_effect(plan: Plan, affected: list[str], recipe: CopyRecipe, controller: str, *,
                    duration: Literal["end_of_turn", "permanent", "next_turn"] = "permanent", source: str | None = None,
                    entry_source: CopyEntrySource | None = None) -> None:
    """A layer-1 copy effect (613.2a) on these objects, timestamped now (613.7)."""
    from app.rules import layers

    made = layers.add_effect(plan, affected=affected, layer="1", source=source, controller=controller, duration=duration,
                             label=f"Copy of {recipe.source}" if recipe.source else "Copy", copy_recipe=recipe, copy_entry_source=entry_source)
    from app.rules import text_global_word71

    text_global_word71.record_acquisition(plan, affected, made.id)
    if duration == "next_turn":  # -- becomes a copy (wave 31C) -- 500.4: "until your next turn" ends as the controller's next turn begins (delayed.turn_began)
        made.until_player, made.turn = controller, plan.state.turn.number


def supported_source(plan: Plan, card: CardInstance, *, token: bool = False) -> str | None:
    """Why this object's copiable values aren't copied automatically (None: they are). Face-down
    objects (707.2: a copy of one is a nameless 2/2 — not modelled), and for a token or a copy of
    a permanent spell, double-faced ones (707.8a, 707.10g: the copy would be double-faced too)."""
    if card.face_down:
        return "a face-down object (707.2)"
    if card.merged:  # -- merged permanents (wave 18D) -- 730.2a: the merge is a copiable effect; what a copy takes of it isn't modelled
        return "a merged or melded permanent (730.2a, 712.8g)"
    data = plan.info.get(card.card_id) if card.card_id else None
    layout = (data or {}).get("layout")
    if layout == "meld" and card.face:
        return "a melded permanent (707.8)"
    if token and layout in DOUBLE_FACED and layout not in TWO_FACED_TOKENS:
        return "a double-faced object (707.8a)"
    return None


# -- copying spells and abilities (707.10) --------------------------------------------------------------
def new_job(ctx: Context | None, *, controller: str, objects: list[tuple[str, str, int]], retarget: bool,
            label: str, excepts: list[CopyExcept] | None = None) -> Job:
    """A copying in progress, as JSON (it waits in a decision's resume): the objects to copy (card,
    the object it must still be, how many copies), who controls the copies, whether new targets
    may be chosen (707.10c), and the resolving ability's context to go on with afterwards."""
    return {"ctx": ctx, "controller": controller, "retarget": retarget, "label": label, "mode": None,
            "excepts": [ex.model_dump(mode="json") for ex in excepts or [] if ex != CopyExcept()],
            "queue": [{"object": c, "oid": oid, "left": n} for c, oid, n in objects if n > 0]}


def lki_spell(plan: Plan, card_id: str, oid: str) -> StackMemory | None:
    """-- spell copies (wave 31D) -- a spell that was this object on the stack and has left it (countered, returned to a hand …), as it last
    existed there (608.2h): copying it still makes a copy (707.10; the rulings of the Storm cycle, Krark, Thousand-Year Storm, Azula)."""
    r = plan.rules
    mem = r.stack_lki.get(oid)
    card = plan.state.cards.get(card_id)
    if mem is None or mem.card != card_id or card is None or oid not in r.lki or plan.oid(card) == oid:
        return None
    return mem



def source_entry102(plan: Plan, card: CardInstance, oid: str) -> StackEntry | None:
    """One native target view for scripted spells and entryless Aura spells, live or retained."""
    from app.rules import attachments, stack_interaction

    if plan.oid(card) == oid:
        return stack_interaction.target_entry(plan, card.id)
    mem = lki_spell(plan, card.id, oid)
    if mem is None:
        return None
    if mem.entry is not None:
        return mem.entry
    snap = plan.rules.lki.get(oid)
    if mem.aura_target102 is None or snap is None:
        return None
    from app.rules.triggers import _lki_characteristics

    ch = _lki_characteristics(plan, snap)
    selector = attachments.enchant_selector(ch)
    if selector is None:
        return None
    return StackEntry(kind='spell', controller=snap.controller, source_card=card.id, source_object=oid,
                      name=ch.name, targets=[mem.aura_target102], target_spec={'what': selector})

def lki_ability(plan: Plan, card_id: str, oid: str) -> StackMemory | None:
    mem = plan.rules.stack_lki.get(oid)
    if mem is None or mem.card != card_id or mem.ability_card is None:
        return None
    current = plan.state.cards.get(card_id)
    return mem if current is None or current.zone != "stack" or plan.oid(current) != oid else None


def run(plan: Plan, job: Job) -> bool:
    """Put the job's copies on the stack, one after another (each on top, 707.10). True when
    they're all there (the caller goes on); False while a decision is pending — its resume goes on
    with the job, then with the resolving ability (``job["ctx"]``)."""
    while job["queue"]:
        if job.get("choose_source_order") and len(job["queue"]) > 1 and not job.get("source_ready"):
            plan_decide(plan, player=job["controller"], kind="choose_one",
                        prompt="Choose the spell whose next copy goes on the stack",
                        options=[DecisionOption(id=item["object"], label=plan.state.cards[item["object"]].name or "Spell",
                                                card_id=item["object"]) for item in job["queue"]],
                        resume={"step": "copy_source_order", "job": job})
            return False
        cur = job["queue"][0]
        saved = cur.get("saved_stack")
        card = CardInstance.model_validate(saved["card"]) if saved is not None else plan.state.cards.get(cur["object"])
        mem = StackMemory.model_validate(saved["memory"]) if saved is not None else None
        if saved is None and (card is None or card.zone != "stack" or plan.oid(card) != cur["oid"]):
            # 608.2h, 707.10: use the exact departed stack object, including abilities that have ceased to exist.
            # An old save without its memory still requests manual resolution rather than silently losing the copy.
            mem = lki_ability(plan, cur["object"], cur["oid"])
            if mem is not None and mem.ability_card is not None:
                card = CardInstance.model_validate(mem.ability_card)
            elif card is not None:
                mem = lki_spell(plan, cur["object"], cur["oid"])
            snap = plan.rules.lki.get(cur["oid"])
            if mem is None or card is None or (snap is not None and snap.face_down):
                name = card.name if card is not None and card.name else "it"
                _next(job)
                _manual(plan, job, f"{job['label']}: {name} left the stack, so its copy isn't automated: make the copy by hand, then press Done")
                return False
        assert card is not None
        refused = uncopyable(plan, card, object_id=cur["oid"]) if saved is None else None
        if refused is not None:
            _next(job)
            if refused:
                _manual(plan, job, refused)
                return False
            continue
        entry = mem.entry if saved is not None and mem is not None else source_entry102(plan, card, cur["oid"])
        from app.rules import spell_copy_replacements

        spell_copy_replacements.prepare(plan, job, cur, ability=card.ability is not None)
        copy_kind = spell_copy_replacements.next_kind(plan, job, cur)
        if copy_kind is None:
            return False
        choosing = (job["retarget"] or copy_kind == "additional") and entry is not None and bool(positions(entry))
        if choosing and copy_kind == "original" and job["mode"] is None and cur["left"] > 1:
            name = entry.name if entry is not None and entry.name else card.name or "it"
            plan_decide(plan, player=job["controller"], kind="choose_one", prompt=f"{job['label']}: {cur['left']} copies of {name}",
                        options=[DecisionOption(id="same", label="Keep the targets for every copy"),
                                 DecisionOption(id="choose", label="Choose new targets for each copy")],
                        resume={"step": "copy_mode", "job": job})
            return False
        excepts = [CopyExcept.model_validate(x) for x in job["excepts"]]
        copy_id = (_copy_spell(plan, card, job["controller"], excepts, cur["oid"], saved=saved) if saved is not None else
                   make_copy(plan, card, job["controller"], excepts, cur["oid"]))
        if job.get("did") and job.get("ctx") is not None:
            from app.rules import context

            context.refs(job["ctx"])[job["did"]] = {"kind": "payment", "ok": True}

        same = copy_kind == "original" and job["mode"] == "same"
        cur.pop("next_kind", None)
        job.pop("source_ready", None)
        cur["additional" if copy_kind == "additional" else "left"] -= 1
        if cur["left"] <= 0 and cur.get("additional", 0) <= 0:
            _next(job)
        if copy_id is None:
            continue
        granted = list(job.get("gained_abilities", []))
        if plan.ch(plan.state.cards[copy_id]).is_permanent_card:
            granted += job.get("permanent_gained_abilities", [])
        if granted:
            from app.rules import layers

            layers.add_effect(plan, affected=[plan.oid(copy_id)], layer="6",
                              source=(job.get("ctx") or {}).get("source_object"), controller=job["controller"],
                              duration="permanent", add_abilities=granted, label=job["label"])
        if choosing and not same:
            if ask_targets(plan, job, copy_id, []):
                return False
            continue
        finalize(plan, copy_id, job["controller"])
    return True


def _next(job: Job) -> None:
    job.pop("source_ready", None)
    job["queue"].pop(0)
    job["mode"] = None


def plan_decide(plan: Plan, **kw: Any) -> None:
    from app.rules.plan import decide

    decide(plan, **kw)


def _manual(plan: Plan, job: Job, prompt: str) -> None:
    plan_decide(plan, player=job["controller"], kind="manual_resolution", prompt=prompt[:300],
                options=[DecisionOption(id="done", label="Done")], resume={"step": "copy_manual", "job": job})


def go_on(plan: Plan, job: Job) -> None:
    """The copies are on the stack: the resolving spell or ability goes on (608.2c)."""
    if job.get("after100o") is not None:  # -- retarget (wave 100O) -- the next player's copy (Hive Mind)
        from app.rules import retarget100o

        retarget100o.after_copy(plan, job["after100o"])
        return
    if job.get("after_each") is not None:
        parent = job["after_each"]
        if _each_run(plan, parent):
            go_on(plan, parent)
        return
    if job.get("ctx") is not None:
        from app.rules.effects import continue_effects

        continue_effects(plan, job["ctx"])


def resume_mode(plan: Plan, d: Any, chosen: list[str]) -> None:
    job = d.resume["job"]
    job["mode"] = chosen[0]
    if run(plan, job):
        go_on(plan, job)


def resume_source_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    job = d.resume["job"]
    at = next(i for i, item in enumerate(job["queue"]) if item["object"] == chosen[0])
    job["queue"].insert(0, job["queue"].pop(at))
    job["source_ready"] = True
    if run(plan, job):
        go_on(plan, job)


def resume_copy_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    job = d.resume["job"]
    job["queue"][0]["next_kind"] = chosen[0]
    if run(plan, job):
        go_on(plan, job)


def resume_manual(plan: Plan, d: Any, chosen: list[str]) -> None:
    job = d.resume["job"]
    plan.note(f"{plan.name(d.player)} finished the copy by hand", actor=d.player)
    if job.get("did"):  # (-- review 25C -- a paid cast made by hand: "If you don't, …" reads the answer, permissions.free_cast)
        from app.rules import context

        context.refs(job["ctx"])[job["did"]] = {"kind": "payment", "ok": chosen == ["done"]}
    if run(plan, job):
        go_on(plan, job)


def uncopyable(plan: Plan, card: CardInstance, *, object_id: str | None = None) -> str | None:
    """None: the engine copies this spell or ability. "": it can't be copied (113.6g), nothing
    happens. Otherwise: why the copy is made by hand (the prompt of that manual step)."""
    if card.ability is not None:
        if re.search(r"\bcan't be copied\b", card.ability.text, re.IGNORECASE):
            plan.note(f"{card.ability.source_name or 'That ability'}: this ability can't be copied (113.6g)", actor=plan.actor)
            return ""
        return None
    if card.face_down:
        return "Copying a face-down spell isn't automated (707.2): make the copy by hand, then press Done"
    ch = plan.ch(card)
    zone = card.zone
    if object_id is not None and object_id != plan.oid(card) and (snap := plan.rules.lki.get(object_id)) is not None:
        from app.rules.triggers import _lki_characteristics

        ch, zone = _lki_characteristics(plan, snap), snap.zone
    if any(re.search(r"\bcan't be copied\b", a.text, re.IGNORECASE)
           and (zone == "stack" or not re.search(r"\bthis spell\b", a.text, re.IGNORECASE)) for a in ch.abilities):
        plan.note(f"{ch.name or 'That spell'} can't be copied (113.6g)", [card.id], actor=plan.actor)
        return ""
    if "Aura" in ch.subtypes:
        from app.rules import attachments

        if attachments.enchant_selector(ch) is None:
            return f"Copying this Aura's unrecognized enchant restriction ({ch.name}) isn't automated"
    if ch.doors is not None:  # -- Rooms (review 18G) -- 709.5d unlocks the half that was *cast*; a copy isn't cast (707.10): unsettled
        return f"Copying a Room spell ({ch.name}) isn't automated (709.5d): make the copy by hand, then press Done"
    if plan.oid(card) in plan.rules.mutating:  # -- merged permanents (wave 18D) -- the copy is a mutating spell too (707.10, 702.140)
        return f"Copying {ch.name}, a mutating creature spell, isn't automated: make the copy by hand, then press Done"
    if ch.is_permanent_card and supported_source(plan, card, token=True) is not None:  # (707.10g: meld / reversible only)
        return f"Copying {ch.name}, a double-faced permanent spell, isn't automated (707.10g): make the copy by hand, then press Done"
    return None


def make_copy(plan: Plan, card: CardInstance, controller: str, excepts: list[CopyExcept], oid: str | None = None) -> str | None:
    """Put one copy of this spell or ability onto the stack under ``controller``'s control (707.10). ``oid``: the object the spell was
    (wave 31D: when it is no longer that object on the stack, the copy is made from how it last existed there, 608.2h)."""
    if card.ability is not None:
        return _copy_ability(plan, card, controller, oid)
    return _copy_spell(plan, card, controller, excepts, oid)


def _copy_spell(plan: Plan, card: CardInstance, controller: str, excepts: list[CopyExcept], oid: str | None = None,
                *, saved: dict[str, Any] | None = None) -> str | None:
    from app.game.state import StackInfo

    r = plan.rules
    orig_oid = oid or plan.oid(card)
    mem = StackMemory.model_validate(saved["memory"]) if saved is not None else lki_spell(plan, card.id, orig_oid) if orig_oid != plan.oid(card) else None  # it has left the stack: -- spell copies (wave 31D) --
    entry = mem.entry if saved is not None and mem is not None else source_entry102(plan, card, orig_oid)
    info = (StackInfo.model_validate(mem.info) if mem.info else None) if mem is not None else card.stack_info
    if mem is not None:  # (its copiable values as it was: a copy effect on it then, else its printing and face — 707.2)
        from app.game.rules_state import ObjectSnapshot

        snap = ObjectSnapshot.model_validate(saved["snapshot"]) if saved is not None else r.lki[orig_oid]
        base = snap.copy_recipe.model_copy(deep=True) if snap.copy_recipe is not None else CopyRecipe(printing=snap.printing, face=snap.face,
                                                                                                      source=snap.name[:200])
        record = r.payments.get(orig_oid)
        recipe = with_excepts(base.model_copy(update={"prototyped": True}) if record is not None and record.prototyped else base, excepts)
    else:
        recipe = with_excepts(recipe_of(plan, card), excepts)
    created = plan.do({"type": "copy_card", "card_id": card.id, "player": controller, "count": 1, **({"saved_stack": saved["snapshot"]} if saved is not None else {"last_known": orig_oid} if mem else {})},
                      actor=controller)
    new_ids = getattr(created, "r", None)
    if new_ids is None or not new_ids.ids:
        return None
    copy_id = new_ids.ids[0]
    oid = plan.oid(copy_id)
    add_copy_effect(plan, [oid], recipe, controller)
    if entry is not None:
        r.stack[copy_id] = _entry_copy(entry, controller=controller, source=(copy_id, oid), orig=orig_oid)
    if orig_oid in r.chosen_players:  # (wave 110F) 707.10: the copy has the same chosen player (the opponent who chose the modes, 700.2e)
        r.chosen_players[oid] = r.chosen_players[orig_oid]
    _payment_alias(plan, orig_oid, oid, copy_id, controller, saved=saved)
    payload: dict[str, Any] = {"type": "set_stack_info", "card_id": copy_id,
                               "tags": ["Copy", *(t for t in (info.tags if info else []) if t.startswith(("Kicked", "Evoked")))]}
    if info is not None and info.x is not None:
        payload["x"] = info.x
    if info is not None and info.modes:
        payload["modes"] = list(info.modes)
    plan.do(payload, actor=controller)
    # 707.10: the copy has the original's alternative costs: an evoked or dashed permanent spell's
    # copy is too (702.74a, 702.109a)
    for marks, kept in ((r.evoked, mem is not None and mem.evoked), (r.dashed, mem is not None and mem.dashed)):
        if card.id in marks or kept:
            marks.append(copy_id)
    emit(plan.state, "spell_copied", object_id=oid, card=copy_id, player=controller, source=orig_oid)
    return copy_id


def _copy_ability(plan: Plan, card: CardInstance, controller: str, oid: str | None = None) -> str | None:
    from app.game.state import StackInfo

    r = plan.rules
    ab = card.ability
    assert ab is not None
    orig_oid = oid or plan.oid(card)
    mem = lki_ability(plan, card.id, orig_oid)
    entry = mem.entry if mem is not None else r.stack.get(card.id)
    source = ab.source_id if ab.source_id and ab.source_id in plan.state.cards else None
    created = plan.do({"type": "create_ability", "text": (ab.text or "Ability")[:500], "source_id": source, "kind": ab.kind},
                      actor=controller)
    new_ids = getattr(created, "r", None)
    if new_ids is None or not new_ids.ids:
        return None
    copy_id = new_ids.ids[0]
    oid = plan.oid(copy_id)
    if entry is not None:  # 707.10b: the same source as the original
        r.stack[copy_id] = _entry_copy(entry, controller=controller, source=None, orig=orig_oid)
    _payment_alias(plan, orig_oid, oid, copy_id, controller)
    info = (StackInfo.model_validate(mem.info) if mem.info else None) if mem is not None else card.stack_info
    if info is not None and (info.x is not None or "Backup" in info.tags):
        plan.do({"type": "set_stack_info", "card_id": copy_id, "x": info.x,
                 "tags": ["Copy", *(["Backup"] if "Backup" in info.tags else [])]}, actor=controller)
    return copy_id


def _entry_copy(entry: StackEntry, *, controller: str, source: tuple[str, str] | None, orig: str) -> StackEntry:
    """The copy's rules metadata: everything decided for the original (707.10, 700.2g, 601.2d)."""
    out = entry.model_copy(deep=True)
    out.controller = controller
    if source is not None:  # a spell copy is itself the spell ("~ deals 3 damage": the copy deals it)
        out.source_card, out.source_object = source
    out.copy_of = orig
    return out


def _payment_alias(plan: Plan, orig_oid: str, oid: str, copy_id: str, controller: str,
                   *, saved: dict[str, Any] | None = None) -> None:
    """707.10: an effect of the copy that refers to objects used to pay its costs uses the objects
    that paid for the original (the sacrificed creature, the creatures that convoked it); mana
    isn't an object and isn't copied (the Dawnglow Infusion example), nor is life."""
    from app.game.rules_state import PaymentRecord

    record = PaymentRecord.model_validate(saved["payment"]) if saved is not None and saved.get("payment") else plan.rules.payments.get(orig_oid)
    if record is not None:
        plan.rules.payments[oid] = record.model_copy(
            deep=True, update={"card": copy_id, "controller": controller, "mana_spent": {}, "resolved_x": None, "activation_life_paid": 0, "x_black_spent": 0, "mana_tags": [], "snow_spent": {}, "mana_sources": [], "mana_riders": [], "life": 0, "tapped": [],
                               "total_cost": "", "cast_from": None, "cast_main": False})  # (wave 3R1: a copy wasn't cast)


# -- choosing new targets (707.10c, 115.7d-f) ------------------------------------------------------
def positions(entry: StackEntry) -> list[Position]:
    """Every target of a spell or ability, in order: each chosen mode's (700.2c), each target
    group's (601.2c), or its one plain target."""
    if entry.slot_specs:
        return [("slot", k, i) for k, (refs, spec) in enumerate(zip(entry.slots, entry.slot_specs, strict=False)) if spec
                for i in range(len(refs))]
    if entry.group_specs:
        return [("group", g, i) for g, refs in enumerate(entry.groups) for i in range(len(refs))]
    if entry.target_spec and entry.targets:
        return [("plain", 0, i) for i in range(len(entry.targets))]
    return []


def _spec(entry: StackEntry, pos: Position) -> dict[str, Any]:
    kind, g, _ = pos
    spec = entry.slot_specs[g] if kind == "slot" else entry.group_specs[g] if kind == "group" else entry.target_spec
    return spec or {}


def _current(entry: StackEntry, pos: Position) -> TargetRef:
    kind, g, i = pos
    return (entry.slots[g] if kind == "slot" else entry.groups[g] if kind == "group" else entry.targets)[i]


def _retargeted(entry: StackEntry, pos: list[Position], refs: list[TargetRef]) -> StackEntry:
    out = entry.model_copy(deep=True)
    for (kind, g, i), ref in zip(pos, refs, strict=True):
        if kind == "slot":
            out.slots[g][i] = ref
        elif kind == "group":
            out.groups[g][i] = ref
        else:
            out.targets[i] = ref
    if out.slot_specs:
        out.targets = [t for slot in out.slots for t in slot]
    elif out.group_specs:
        out.targets = [t for grp in out.groups for t in grp]
    return out


def _problem(plan: Plan, entry: StackEntry) -> str | None:
    """Is the final set of targets legal together (115.7d-e)? No object twice for one word
    "target" (115.3), "another target" not one of the earlier group's, one graveyard."""
    from app.rules.targets import relation_ok

    for g, (refs, spec) in enumerate(zip(entry.groups, entry.group_specs, strict=False)):
        ids = [t.id for t in refs]
        if len(set(ids)) != len(ids):
            return "the same target can't be chosen twice for one “target” (115.3)"
        banned = {t.id for d in spec.get("distinct_from") or [] if d < len(entry.groups) and d != g for t in entry.groups[d]}
        if banned & set(ids):
            return "“another target” can't be one of the other targets (115.3)"
        if spec.get("same_graveyard") and len({plan.state.cards[t].owner for t in ids if t in plan.state.cards}) > 1:
            return "those targets must be in a single graveyard"
        if not relation_ok(plan, spec, refs):  # -- group relations (wave 51A) -- 115.7e: the final set must still share a type / have different controllers
            return "those targets must share a type" if spec.get("shares") else "those targets must have the same controller" if spec.get("same_controller") else "those targets must have different controllers"
        if spec.get("of") is not None and refs:  # -- player-relative selectors (wave 53A) -- 115.7d: "that player controls" still holds for the new targets of the group it depends on
            from app.rules import player_relative, targets

            ok = targets.legal_targets(plan, player_relative.bind_what(plan, spec, entry.groups), entry.controller,
                                       targets.source_of(plan, entry.source_card, entry.kind == "spell", object_id=entry.source_object), entry.source_card, source_object=entry.source_object)
            if any(t.id not in ok for t in refs):
                if spec.get('object_of') is not None:
                    return 'Choose Equipment attached to the chosen creature.'
                return "those targets must satisfy the earlier target's quality restriction" if spec.get("relative_quality") else "those targets must be controlled by the player the earlier target names"
    return None


def _options(plan: Plan, entry: StackEntry, pos: Position, controller: str, copy_id: str,
             taken: set[str]) -> list[DecisionOption]:
    from app.rules import selectors, targets

    spec = _spec(entry, pos)
    current = _current(entry, pos)
    from app.rules import player_relative  # -- player-relative selectors (wave 53A) --

    legal = targets.legal_targets(plan, player_relative.bind_what(plan, spec, entry.groups) if spec.get("of") is not None else spec.get("what", "any"), controller, targets.source_of(plan, entry.source_card, entry.kind == "spell", object_id=entry.source_object),
                                  entry.source_card, selectors.attacker_of(entry.event), source_object=entry.source_object)
    keep = DecisionOption(id="keep", label=f"Keep {targets.label(plan, current.id)}"[:200],
                          card_id=current.id if current.id in plan.state.cards else None)
    # (115.5: a spell or ability on the stack is an illegal target for itself)
    return [keep, *(DecisionOption(id=x, label=targets.label(plan, x), card_id=x if x in plan.state.cards else None)
                    for x in legal if x not in (current.id, copy_id) and x not in taken)]


def ask_targets(plan: Plan, job: Job, copy_id: str, picks: list[str]) -> bool:
    """707.10c: the copy's controller keeps or changes each target in turn (``picks``: the answers
    so far). True while a question is open; False once the copy has its targets."""
    from app.rules import targets

    entry = plan.rules.stack.get(copy_id)
    if entry is None:
        return False
    pos = positions(entry)
    controller = job["controller"]
    while len(picks) < len(pos):
        k = len(picks)
        kind, g, _ = pos[k]
        chosen = [(q, _current(entry, q).id if p == "keep" else p) for p, q in zip(picks, pos, strict=False)]
        # (115.3: not twice for this word "target", nor the object an earlier "another target" names)
        others = set(_spec(entry, pos[k]).get("distinct_from") or []) if kind == "group" else set()
        taken = {x for q, x in chosen if q[0] == kind and (q[1] == g or q[1] in others)}
        so_far = _retargeted(entry, pos[:k], [_current(entry, q) if p == "keep" else targets.ref(plan, p) for p, q in zip(picks, pos, strict=False)]) \
            if any(sp.get("of") is not None for sp in entry.group_specs) else entry  # (-- player-relative selectors (wave 53A) -- a group that depends on an earlier one is offered what fits the new pick)
        options = _options(plan, so_far, pos[k], controller, copy_id, taken)
        if len(options) == 1:  # nothing else it could target: it keeps this one
            picks.append("keep")
            continue
        name = entry.name or "the spell"
        count = f" ({k + 1} of {len(pos)})" if len(pos) > 1 else ""
        plan_decide(plan, player=controller, kind="choose_one",
                    prompt=f"Copy of {name}: keep its target{count} or choose a new one (707.10c)", options=options,
                    resume={"step": "copy_target", "job": job, "copy": copy_id, "picks": picks})
        return True
    refs = [_current(entry, p) if pick == "keep" else targets.ref(plan, pick) for p, pick in zip(pos, picks, strict=True)]
    new = _retargeted(entry, pos, refs)
    problem = _problem(plan, new)
    if problem is not None:
        plan.note(f"Those targets aren't legal together: {problem}. Choose again", actor=controller)
        return ask_targets(plan, job, copy_id, [])
    plan.rules.stack[copy_id] = new
    finalize(plan, copy_id, controller)
    return False


def resume_target(plan: Plan, d: Any, chosen: list[str]) -> None:
    job = d.resume["job"]
    if ask_targets(plan, job, d.resume["copy"], [*d.resume["picks"], chosen[0]]):
        return
    if run(plan, job):
        go_on(plan, job)


def finalize(plan: Plan, copy_id: str, controller: str) -> None:
    """The copy is on the stack with its targets: they become its targets (115.10, 603.2e: "becomes
    the target" triggers, ward), shown with an arrow."""
    from app.game.visibility import publicly_visible
    from app.rules.triggers import targeted

    entry = plan.rules.stack.get(copy_id)
    if entry is None or not entry.targets:
        return
    ids = [t.id for t in entry.targets
           if (t.id in plan.state.players and not plan.state.players[t.id].left)
           or (t.id in plan.state.cards and publicly_visible(plan.state, plan.state.cards[t.id]))]
    plan.target_arrows(copy_id, ids, actor=controller)
    targeted(plan, copy_id, controller, entry.targets)
    if 'Aura' in plan.ch(plan.state.cards[copy_id]).subtypes:
        # The temporary target view is only for copy selection; normal Aura resolution
        # continues through the existing enchant/attachment path, not an empty scripted spell.
        plan.rules.aura_targets[copy_id] = entry.targets[0]
        plan.rules.stack.pop(copy_id, None)


# -- effect primitives ---------------------------------------------------------------------------------
def _retarget_follows(ctx: Context) -> bool:
    """"You may choose new targets for the copy." is the sentence right after the copy (a marker
    effect the grammar leaves there)."""
    effects = ctx.get("effects") or []
    k = int(ctx.get("next") or 0)
    while k < len(effects) and effects[k].get("do") in ("only_if", "copy_spell", "copy_ability"):  # -- spell copies (wave 31D) -- "If …, copy that
        k += 1  # spell twice instead. You may choose new targets for the copies": the sentence is about the copies of every branch (707.10c)
    return k < len(effects) and effects[k].get("do") == "copy_new_targets"


def _stack_objects(plan: Plan, ctx: Context, who: str) -> list[str]:
    from app.rules.effects import target_refs

    if who == "event_spell":  # -- refused copy/mana (wave 3R3): the spell a cast trigger is about (603.2) --
        from app.rules import context

        return [c for c in context.objects(plan, ctx, context.EVENT) if plan.state.cards[c].zone == "stack"]

    if who == "this_spell":  # -- chain spells (wave 52C) -- "copy this spell": the spell that is resolving, still on the stack (608.2)
        src = ctx.get("source_card")
        return [src] if src in plan.state.cards and plan.state.cards[src].zone == "stack" and plan.oid(src) == ctx.get("source_object") else []

    if who == "event_ability":  # -- copied abilities (wave 18F) -- the ability an activation trigger is about (603.2), while it's still on the stack
        src = (ctx.get("event") or {}).get("source") or {}
        return [src["card"]] if src.get("card") in plan.state.cards and plan.state.cards[src["card"]].zone == "stack" \
            and plan.oid(src["card"]) == src.get("object_id") else []

    return [t["id"] for t in target_refs(ctx, who) if t and t["id"] in plan.state.cards
            and plan.state.cards[t["id"]].zone == "stack" and plan.oid(t["id"]) == t.get("object_id")]


def copy_stack_object(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Copy target instant or sorcery spell [, except …]" / "Copy target triggered ability you
    control" (707.10), then "You may choose new targets for the copy" (707.10c)."""
    from app.rules import values

    n = values.evaluate(plan, ctx, e.get("n", 1))
    excepts = [CopyExcept.model_validate(x) for x in e.get("excepts") or []]
    who = e.get("who") or "target"
    objects = [(sid, oid, n) for sid, oid in _copy_sources(plan, ctx, who)]
    controller = ctx["controller"]
    if e.get("by"):  # -- chain spells (wave 52C) -- 707.10: "they may copy this spell": the copy is controlled by the player who copies it
        from app.rules.optional_payment import payer_of

        controller = payer_of(plan, ctx, e["by"]) or controller
    job = new_job(ctx, controller=controller, objects=objects, retarget=_retarget_follows(ctx),
                  label=ctx.get("name") or "Copy", excepts=excepts)
    if e.get("bind"):
        from app.rules import context

        job["did"] = e["bind"]
        context.refs(ctx)[e["bind"]] = {"kind": "payment", "ok": False}
    marker_at = int(ctx.get("next") or 0)
    following = ctx.get("effects") or []
    while marker_at < len(following) and following[marker_at].get("do") in ("copy_new_targets", "copy_gain"):
        if following[marker_at]["do"] == "copy_gain":
            field = "permanent_gained_abilities" if following[marker_at].get("if_permanent") else "gained_abilities"
            job[field] = [*job.get(field, []), *following[marker_at]["abilities"]]
        marker_at += 1
    if e.get("choose_source_order"):
        job["choose_source_order"] = True
    if not objects and (who in ("event_spell", "event_ability") or who.startswith("ref:")) and _event_object_left(ctx, who):
        # -- spell copies (wave 31D) -- the spell or ability a trigger is about has left the stack and nothing is kept of it: never silently
        # no copy (707.10; the trigger copies it even if it was countered)
        _manual(plan, job, f"{ctx.get('name') or 'Copy'}: the {'ability' if who == 'event_ability' else 'spell'} to copy left the stack, so its copy "
                           "isn't automated: make the copy by hand, then press Done")
        return False
    return run(plan, job)


def _copy_sources(plan: Plan, ctx: Context, who: str) -> list[tuple[str, str]]:
    """-- spell copies (wave 31D) -- (card, object id) of what a copy instruction copies: what is on the stack, else the spell a cast trigger
    is about that left it, as it last existed there (``lki_spell``)."""
    if who.startswith("ref:"):  # -- retarget (wave 100O) -- "the spell countered this way" (Psychic Rebuttal): one that left the stack, as it last was (608.2h)
        return [(w["card"], w["object_id"]) for w in _countered(ctx, who) if lki_spell(plan, w["card"], w["object_id"])]
    on = _stack_objects(plan, ctx, who)
    if on or who not in ("event_spell", "event_ability"):
        return [(sid, plan.oid(sid)) for sid in on]
    if who == "event_ability":
        source = (ctx.get("event") or {}).get("source") or {}
        card_id, oid = source.get("card"), source.get("object_id")
        return [(card_id, oid)] if card_id and oid and lki_ability(plan, card_id, oid) else []
    from app.rules import context

    return [(r.card, r.object_id) for r in context._object_refs(ctx, context.EVENT) if r.zone == "stack" and lki_spell(plan, r.card, r.object_id)]


def _countered(ctx: Context, who: str) -> list[dict[str, Any]]:
    """-- retarget (wave 100O) -- the objects a "this way" binding was before they moved, only those that left the stack (a spell that can't be
    countered stays: its ruling, no copy)."""
    from app.rules import context

    b = context.refs(ctx).get(who[4:]) or {}
    return [w for w in b.get("was") or [] if w.get("zone") == "stack" and w not in (b.get("objects") or [])]


def _event_object_left(ctx: Context, who: str) -> bool:
    """Was there a spell (a cast trigger's event) or an ability (an activation trigger's) that is no longer there to copy?"""
    if who.startswith("ref:"):  # -- retarget (wave 100O) --
        return bool(_countered(ctx, who))
    if who == "event_ability":
        return bool(((ctx.get("event") or {}).get("source") or {}).get("card"))
    from app.rules import context

    return any(r.zone == "stack" for r in context._object_refs(ctx, context.EVENT))


# -- cast a copy (wave 13C) -- 707.12: "Copy it. You may cast the copy without paying its mana cost."
def copy_cards(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Copy it / that card / those cards [three times]" of a card in exile or a graveyard (707.12): each copy is
    made in the card's own zone and may then be cast while this resolves (permissions.free_cast); one not cast
    ceases to exist (704.5e). Recorded as the instruction's objects ("the copy"). A card in a hidden zone, a
    face-down or double-faced one (707.8, 707.8a) is copied by hand."""
    from app.rules import effects, values

    pid = ctx['controller']
    pending = ctx.pop('card_copy_pending', None)
    if pending is None:
        n = max(0, values.evaluate(plan, ctx, e.get('n', 1)))
        pending = {'todo': [], 'made': [], 'by_hand': []}
        for cid in effects._cards(plan, ctx, e['who']):
            card = plan.state.cards[cid]
            if card.zone.rsplit(':', 1)[-1] not in ('exile', 'graveyard') or card.is_token:
                continue
            if e.get('source_zone') and card.zone.rsplit(':', 1)[-1] != e['source_zone']:
                continue  # The printed copied card must actually have reached that zone.
            data = plan.info.get(card.card_id) if card.card_id else None
            if card.face_down or (data or {}).get('layout') not in ('normal', 'split', 'aftermath', 'modal_dfc', 'transform', 'flip', 'adventure'):
                pending['by_hand'].append(plan.ch(card).name or 'it')
                continue
            if (why := uncopyable(plan, card)) is not None:
                if why:
                    pending['by_hand'].append(plan.ch(card).name or 'it')
                continue
            if n:
                pending['todo'].append({'card': cid, 'object': plan.oid(card), 'left': n})
    made, by_hand = pending['made'], pending['by_hand']
    work = 0
    while pending['todo']:
        if work >= 64 or len(plan.steps) >= plan.max_steps - 24:
            ctx['card_copy_pending'] = pending
            ctx['next'] -= 1
            plan_decide(plan, player=pid, kind='confirm', prompt='Continue creating the card copies (no priority is available).',
                        options=[DecisionOption(id='continue', label='Continue resolving')],
                        resume={'step': 'card_copy_continue', 'ctx': ctx})
            return False
        item = pending['todo'][0]
        current = plan.state.cards.get(item['card'])
        if current is None or plan.oid(current) != item['object'] or not plan.in_game(current):
            pending['todo'].pop(0)
            continue
        created = plan.do({'type': 'copy_card', 'card_id': current.id, 'player': pid, 'count': 1,
                           'zone': current.zone.rsplit(':', 1)[-1]}, actor=pid)
        made.extend(getattr(getattr(created, 'r', None), 'ids', []))
        item['left'] -= 1
        if item['left'] == 0:
            pending['todo'].pop(0)
        work += 1
    effects._remember(plan, ctx, e, made)
    if by_hand:
        job = new_job(ctx, controller=pid, objects=[], retarget=False, label=ctx.get("name") or "Copy")
        plan_decide(plan, player=pid, kind="manual_resolution", options=[DecisionOption(id="done", label="Done")],
                    prompt=f"Copying {', '.join(by_hand)} isn't automated (707.8): make the copy by hand, then press Done"[:300],
                    resume={"step": "copy_manual", "job": job})
        return False
    return True


def resume_card_copy_continue(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    continue_effects(plan, d.resume['ctx'])


def _each_victims(plan: Plan, ctx: Context, pid: str, entry: Any) -> list[str]:
    """The other creatures `pid` controls that every instance of "target" in the spell could target (707.10d)."""
    from app.rules import targets

    source = targets.source_of(plan, entry.source_card, entry.kind == "spell", object_id=entry.source_object)  # (review 41: a copy of a spell is a spell, 707.10, 115.2)
    legal = [set(targets.legal_targets(plan, _spec(entry, p).get("what", "any"), pid, source, entry.source_card, None, source_object=entry.source_object)) for p in positions(entry)]
    return [c for c in plan.state.zones.get(f"{pid}:battlefield", []) if c != ctx.get("source_card") and plan.state.cards[c].controller == pid
            and plan.ch(plan.state.cards[c]).is_creature and all(c in ok for ok in legal)]


# -- copied for each (wave 18F) -- 707.10d: a copy for each object the spell could target, each copy's targets all that object (not
# legal for every instance of "target": no copy), put on the stack in the order its controller chooses
def copy_each(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    found = next(iter(_copy_sources(plan, ctx, "event_spell")), None)  # (wave 31D: a spell that left the stack is copied as it last was there)
    pid = ctx["controller"] if e["by"] == "you" else next(iter(effects._players(plan, ctx, "event_player")), ctx["controller"])
    if found is None:
        return _manual_each(plan, ctx, pid, None) if _event_object_left(ctx, "event_spell") else True  # (never silently no copy)
    spell, oid = found
    card = plan.state.cards[spell]
    mem = lki_spell(plan, spell, oid) if plan.oid(card) != oid else None
    entry = mem.entry if mem is not None else plan.rules.stack.get(spell)
    if entry is None:
        return True
    pos = positions(entry)
    if not pos:
        return True
    reason = uncopyable(plan, card, object_id=oid)
    if reason is not None:
        return True if reason == "" else _manual_each(plan, ctx, pid, card)
    victims = _each_victims(plan, ctx, pid, entry)
    from app.rules import spell_copy_replacements

    job = {"ctx": ctx, "spell": spell, "oid": oid, "controller": pid, "victims": victims,
           "additional": spell_copy_replacements.additional(plan, pid) if victims else 0,
           **({"one": True} if e.get("one") else {})}  # -- one copy (wave 110G) -- Beamsplitter Mage: only one chosen creature gets a copy
    return _each_run(plan, job)


def _manual_each(plan: Plan, ctx: Context, pid: str, card: CardInstance | None) -> bool:
    _manual(plan, new_job(ctx, controller=pid, objects=[], retarget=False, label=ctx.get("name") or "Copy"),
            f"Copying {(plan.ch(card).name if card is not None else '') or 'that spell'} isn't automated: make the copies by hand, then press Done")
    return False


def _each_run(plan: Plan, job: dict[str, Any]) -> bool:
    from app.rules import targets

    pid = job["controller"]
    while job["victims"] or job.get("additional", 0):
        if len(job["victims"]) + int(job.get("additional", 0)) > 1 and not job.get("next"):
            # 707.10d / 614.5: original copies retain their prescribed targets;
            # additional copies can be inserted anywhere and choose new targets.
            options = [DecisionOption(id=v, label=targets.label(plan, v), card_id=v) for v in job["victims"]]
            if job.get("additional", 0):
                options.append(DecisionOption(id="__additional__", label="Additional copy (may choose new targets)"))
            plan_decide(plan, player=pid, kind="choose_one", prompt="Put the next copy on the stack: choose its target or an additional copy",
                        options=options, resume={"step": "copy_each", "job": job})
            return False
        victim = job.pop("next", None) or (job["victims"][0] if job["victims"] else "__additional__")
        if victim != "__additional__":
            job["victims"].remove(victim)
        card = plan.state.cards.get(job["spell"])
        mem = lki_spell(plan, job["spell"], job["oid"]) if card is not None else None  # (wave 31D: a spell that left the stack, as it last was there)
        entry = source_entry102(plan, card, job["oid"]) if card is not None else None
        if card is None or entry is None or (mem is None and (card.zone != "stack" or plan.oid(card) != job["oid"])):
            break
        if victim == "__additional__":
            job["additional"] -= 1
            extra = new_job(None, controller=pid, objects=[(job["spell"], job["oid"], 1)], retarget=True, label="Additional copy")
            extra["replacements_done"], extra["after_each"] = True, job
            if not run(plan, extra):
                return False
            continue
        copy_id = make_copy(plan, card, pid, [], job["oid"])
        if copy_id is None:
            continue
        pos = positions(entry)
        plan.rules.stack[copy_id] = _retargeted(plan.rules.stack[copy_id], pos, [targets.ref(plan, victim)] * len(pos))
        finalize(plan, copy_id, pid)
        if job.get("one"):  # (-- one copy (wave 110G) --)
            job["victims"] = []
    return True


def resume_each(plan: Plan, d: Any, chosen: list[str]) -> None:
    job = d.resume["job"]
    job["next"] = chosen[0]
    if _each_run(plan, job):
        go_on(plan, job)


def new_targets_marker(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    return True  # read by the copy before it (``_retarget_follows``)


def storm(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.40a: "copy it for each other spell that was cast before it this turn. If the spell has
    any targets, you may choose new targets for any of the copies." The spell must still be the
    object it was when it was cast, or — wave 31D — a spell that has left the stack (countered …)
    is copied as it last existed there (608.2h; Grapeshot's and the Storm cycle's rulings: the copies are
    created even if the spell was countered before the trigger resolves)."""
    sid = e["spell"]
    card = plan.state.cards.get(sid)
    if card is not None and plan.manual(card):
        plan.note("Storm: the spell is handled by hand, so there is nothing to copy")
        return True
    job = new_job(ctx, controller=ctx["controller"], objects=[(sid, e["object"], int(e["n"]))], retarget=True, label="Storm",
                  excepts=[CopyExcept.model_validate(ex) for ex in e.get("excepts") or []])
    return run(plan, job)  # (run copies it as it was, or asks for the copy by hand: never silently none)


def resume_storm(plan: Plan, d: Any, chosen: list[str]) -> None:
    """A storm decision saved before this module existed ({"spell", "left", "mode"}): the same
    questions, now answered through the copy system."""
    r = d.resume
    ctx, sid = r["ctx"], r["spell"]
    card = plan.state.cards.get(sid)
    if card is None or card.zone != "stack":
        go_on(plan, {"ctx": ctx})
        return
    left = int(r["left"])
    job = new_job(ctx, controller=d.player, objects=[(sid, plan.oid(sid), left)], retarget=True, label="Storm")
    if r.get("mode") is None:
        job["mode"] = chosen[0]
    else:  # a target chosen for one copy (the old per-copy question)
        copy_id = make_copy(plan, card, d.player, [])
        job["queue"][0]["left"] -= 1
        job["mode"] = "choose"
        entry = plan.rules.stack.get(copy_id or "")
        if copy_id is not None and entry is not None and entry.target_spec and len(entry.targets) == 1:
            from app.rules.targets import ref

            plan.rules.stack[copy_id] = _retargeted(entry, [("plain", 0, 0)], [ref(plan, chosen[0])])
        if copy_id is not None:
            finalize(plan, copy_id, d.player)
        if job["queue"][0]["left"] <= 0:
            _next(job)
    if run(plan, job):
        go_on(plan, job)


# -- token copies ("create a token that's a copy of …") --------------------------------------------
def token_copy_request(plan: Plan, ctx: Context, controller: str, recipe: CopyRecipe, count: int, *,
                       tapped: bool = False, notes: list[str] | None = None, entry_counters: list[dict[str, Any]] | None = None
                       ) -> tuple[str, dict[str, Any], int, str | None, bool] | None:
    """THE one way the engine makes a token copy's creation request — for the token choke point
    (``replace.create_token_batch``): the copied object's printing (or a token's own definition,
    111.3) as the token's base, entering tapped if the copied text says so (614.1d), and the recipe
    (``_copy``) the token's layer-1 copy effect is made from before anything looks at it (707.2),
    then its "enters with" part (``replacements.after_entry``: counters, a planeswalker's loyalty,
    707.5). 111.5: a copy of an instant or sorcery card creates no token (None, a line in ``notes``)."""
    from app.rules import replacements

    if count <= 0:
        return None
    ch = characteristics(recipe, plan.info)
    if ch.is_instant_or_sorcery:
        (notes if notes is not None else []).append(f"No token is created: a copy of an instant or sorcery card (111.5, {ch.name})")
        return None
    if recipe.printing and plan.info.get(recipe.printing) is not None:
        spec: dict[str, Any] = {"card_id": recipe.printing, "name": (ch.name or "Token")[:80]}
    elif recipe.token is not None:
        spec = {k: recipe.token.get(k) for k in ("name", "power", "toughness", "colors", "type_line", "text")}
        if recipe.token.get("mana_cost"):  # (wave 49D: 707.2, a copy copies the mana cost)
            spec["mana_cost"] = recipe.token["mana_cost"]
    else:
        (notes if notes is not None else []).append(f"{recipe.source or 'That object'} isn't in the card database: no copy is created")
        return None
    probe = {"name": ch.name, "power": ch.power, "toughness": ch.toughness, "colors": sorted(ch.colors),
             "type_line": type_line(ch), "text": ch.oracle_text}
    effect_tapped = tapped
    tapped = (tapped or replacements.token_enters_tapped(plan, controller, probe)) and not replacements.token_enters_untapped(plan, controller, probe)  # (wave 45A)
    source = ctx.get("source_card") if ctx.get("source_card") in plan.state.cards else None
    # (the copy's types as it's created, for type-restricted token replacements — Ojer Taq; 614.16, 707.2)
    transport_line = probe['type_line']
    if 'changeling' in ch.keywords:
        from app.rules.creature_types import CREATURE_TYPES

        # The recipe carries Changeling. Its computed subtype expansion is not a
        # printed type line and must not overflow the token transport field.
        transport_line = type_line(replace(ch, subtypes=ch.subtypes - CREATURE_TYPES))
    return (controller, {**spec, "type_line": transport_line, "_copy": recipe.model_dump(mode="json"),
                         '_effect_tapped': bool(effect_tapped),
                         **({"_entry_counters": entry_counters} if entry_counters else {})}, count, source, tapped)


def _entry_choice(plan: Plan, card_id: str) -> str | None:
    """An "As ~ enters, choose …" of a token copy's copied text (707.6: made anew) that the token path
    couldn't ask (a site that can't pause: replace.create_token_batch asks it otherwise, wave 34A, and
    the token then holds its choice), so it is left to the player."""
    from app.rules import scripts

    card = plan.state.cards.get(card_id)
    if card is None or card.choices:
        return None
    if any(ab.kind == "keywords" and "tribute" in ab.keywords for ab in plan.ch(card).abilities):  # -- keywords (wave 50H) -- 702.104a: the opponent's decision as it enters isn't asked of a token
        return "tribute payment (an opponent's choice)"
    for d in scripts.definitions(plan.ch(card)).values():
        if d.get("kind") == "replacement" and d.get("replacement") == "enters_choice":
            return str(next((e.get("what") for e in d.get("effects") or [] if e.get("what")), "value"))
        if d.get("kind") == "replacement" and d.get("replacement") == "enter_cost":  # -- entering for a cost (wave 5G) --
            return "payment (or none) as it would enter"
    return None


def token_copy(plan: Plan, ctx: Context, e: dict[str, Any], *, then: dict[str, Any] | None = None) -> bool:
    """"Create a token that's a copy of target creature [, except …]" / "… of ~" / "… of it"
    (707.1; 111.4 example: its name is the copied object's): the copied object's copiable values
    as it is now (707.2; a card in a graveyard or exile: its printed values), plus the effect's
    exceptions (707.9). The tokens are recorded for "Sacrifice it at the beginning of the next
    end step" and friends."""
    # A replacement/entry choice pauses after the instruction has determined what
    # to copy. Rerunning this same frame must not read a later source incarnation.
    import copy

    from app.rules import effects, values
    from app.rules import replace as replace_

    requests: list[tuple[str, dict[str, Any], int, str | None, bool]]
    notes: list[str]
    refused: list[str]
    recipient_refs: list[str] | None
    frame = {"effect": e, "next": ctx.get("next")}
    packet = ctx.get("_copy_creation_packet")
    if packet is not None and packet.get("frame") == frame:
        requests = [(r[0], r[1], int(r[2]), r[3], bool(r[4])) for r in packet["requests"]]
        notes, refused = list(packet["notes"]), list(packet["refused"])
        recipient_refs, creation_atoms = packet["recipient_refs"], packet["creation_atoms"]
    else:
        ctx.pop("_copy_creation_packet", None)
        creators = effects._players(plan, ctx, e["creator"]) if e.get("creator") else None
        if creators == []:
            return True
        count = 1 if e.get("creation_each_opponent") else values.evaluate(plan, ctx, e.get("n", 1))
        excepts = [CopyExcept.model_validate(x) for x in e.get("excepts") or []]
        entry_counters = [c for ex in excepts for c in ex.enter_counters]
        excepts = [ex.model_copy(update={'enter_counters': []}) for ex in excepts]
        if e.get("half_pt"):
            p = values._signed_stat(plan, ctx, {"power": e["who"]})
            t = values._signed_stat(plan, ctx, {"toughness": e["who"]})
            excepts.append(CopyExcept(power=str((p + 1) // 2), toughness=str((t + 1) // 2)))
        requests = []
        notes = []
        refused = []
        from app.rules import populate

        # -- review 32 -- an object an earlier instruction moved off the battlefield is copied as it last existed there (below), not as the card it
        # became (Kaya, Intangible Slayer's rulings: a copy of a copy, a token)
        gone = {r.card for r in populate.gone_refs(plan, ctx, e["who"])} if e["who"].startswith("ref:") else set()
        for cid in effects._cards(plan, ctx, e["who"]):
            if cid in gone:
                continue
            card = plan.state.cards[cid]
            zone = card.zone.rsplit(":", 1)[-1]
            # Exact publicly revealed library cards are an explicit printed-effect opt-in.
            if zone in ("hand", "library", "stack") and not (
                    zone == 'library' and zone in e.get('public_card_zones', [])
                    and e['who'].startswith('ref:') and '*' in card.revealed_to):
                continue
            problem = supported_source(plan, card, token=True)
            if problem is not None:
                refused.append(f"a copy of {plan.ch(card).name or 'it'} ({problem})")
                continue
            recipe = recipe_of(plan, card) if zone == "battlefield" else base_recipe(card).model_copy(update={"face": 0})
            # -- token copies & attach on entry (wave 5J) -- "its controller creates a token that's a copy of that creature"
            maker = creators[0] if creators else card.controller if e.get("their") else ctx["controller"]
            req = token_copy_request(plan, ctx, maker, with_excepts(recipe, excepts), count,
                                     tapped=bool(e.get("tapped")), notes=notes, entry_counters=entry_counters)
            if req is not None:
                requests.append(req)
        # -- token copies & attach on entry (wave 5J) -- 608.2h, 111.12: the object the trigger (or the source) was about
        # left the battlefield: the copy uses its copiable values as it last existed there
        for recipe_or_why, maker in populate.left_battlefield(plan, ctx, e["who"], bool(e.get("their"))):
            maker = creators[0] if creators else maker
            if isinstance(recipe_or_why, str):
                refused.append(recipe_or_why)
                continue
            req = token_copy_request(plan, ctx, maker, with_excepts(recipe_or_why, excepts), count,
                                     tapped=bool(e.get("tapped")), notes=notes, entry_counters=entry_counters)
            if req is not None:
                requests.append(req)
        # one creation event per copied object, at once (616.1: the creator orders non-commuting
        # replacements — the choice pauses here and the whole instruction runs again with the answer,
        # so the tokens, the binding and the 707.6 check below all follow it)
        recipient_refs = None
        if e.get('each_creator') and creators is not None:
            requests = [(pid, spec, n, source, tapped) for _, spec, n, source, tapped in requests for pid in creators]
        if e.get('each_opponent_attack'):
            opponents = effects._players(plan, ctx, 'each_opponent')
            recipient_refs = [pid for _ in requests for pid in opponents]
            requests = [request for request in requests for _ in opponents]
        if e.get('embalmed'):
            requests = [(pid, {**spec, '_embalmed': True}, n, source, tapped) for pid, spec, n, source, tapped in requests]
        creation_atoms = ["opponent:" + pid for pid in recipient_refs] if recipient_refs is not None else None
        if e.get('creation_recipients') is not None or e.get('creation_each_opponent'):
            recipients = effects._players(plan, ctx, 'each_opponent') if e.get('creation_each_opponent') else list(e['creation_recipients'])
            creation_atoms = ["opponent:" + pid for _ in requests for pid in recipients]
            requests = [request for request in requests for _ in recipients]
        if e.get('creation_each_count'):
            requests = [(pid, spec, 1, source, tapped) for pid, spec, n, source, tapped in requests for _ in range(max(0, n))]
            creation_atoms = ["iteration:" + str(i) for i in range(len(requests))]
        elif e.get('creation_each'):
            creation_atoms = ["original:" + str(i) for i in range(len(requests))]
        ctx["_copy_creation_packet"] = copy.deepcopy({
            "frame": frame, "requests": requests, "notes": notes, "refused": refused,
            "recipient_refs": recipient_refs, "creation_atoms": creation_atoms,
        })
    made: list[str] = []
    if requests:
        out = replace_.create_token_batch(plan, requests, ctx=ctx, bind=None, then=then or replace_.rerun_then(ctx, e), recipient_refs=recipient_refs,
                                          creation_atoms=creation_atoms, receipt_bind=e.get("receipt_bind"))
        if out is None:
            return False
        made = out
    ctx.pop("_copy_creation_packet", None)
    for n in notes:
        plan.note(n, actor=ctx["controller"])
    for tid in made:  # -- refused copy/mana (wave 3R3) -- 707.8a: a double-faced token has the original's face up
        tok = plan.state.cards.get(tid)
        made_from = copy_recipe_of(plan.rules, plan.oid(tid)) if tok is not None else None
        if tok is not None and tok.card_id and made_from is not None and made_from.printing == tok.card_id \
                and made_from.face != tok.face and (plan.info.get(tok.card_id) or {}).get("layout") in TWO_FACED_TOKENS:
            plan.do({"type": "set_face", "card_id": tid, "face": made_from.face}, actor=ctx["controller"])
    effects._remember(plan, ctx, e, made)
    for tid in made:
        what = _entry_choice(plan, tid)
        if what is not None:
            refused.append(f"the {what} chosen for the token copy of {plan.ch(plan.state.cards[tid]).name} (707.6)")
    if refused:
        _manual(plan, new_job(ctx, controller=ctx["controller"], objects=[], retarget=False, label=ctx.get("name") or "Copy"),
                f"{ctx.get('name') or 'Copy'}: do this by hand — {'; '.join(refused)} — then press Done")
        return False
    if e.get("attacking") and made:  # -- token copy (wave 20F) -- "tapped and attacking" (508.4): attacking, never "attacked"
        from app.rules import token_grammar

        return token_grammar.enter_attacking(plan, ctx, made, e.get("at"))
    return True


# -- entering as a copy (707.5, 614.1c, 614.12a) --------------------------------------------------
def _own(plan: Plan, card: CardInstance) -> Characteristics:
    """The entering card's characteristics without the copy effect it is entering with."""
    oid = plan.oid(card)
    best = None
    for e in plan.rules.effects:
        if e.layer == "1" and e.copy_recipe is not None and oid in e.affected and not (e.source or "").startswith(ENTERING) \
                and (best is None or e.timestamp > best.timestamp):
            best = e
    if best is not None and best.copy_recipe is not None:
        return with_level(plan.state, card, characteristics(best.copy_recipe, plan.info), plan.info)
    return with_level(plan.state, card, chars.of(card, plan.info), plan.info)


def enter_definition(plan: Plan, card: CardInstance) -> dict[str, Any] | None:
    """The card's own "You may have ~ enter as a copy of …" replacement effect, if any."""
    from app.rules import scripts

    if plan.manual(card) or card.face_down:
        return None
    for d in scripts.definitions(_own(plan, card)).values():
        if d.get("kind") == "replacement" and d.get("replacement") == "enter_as_copy":
            return d
    return None


def entry_candidates(plan: Plan, controller: str, what: str, card_id: str | None = None) -> list[str]:
    """What an entering permanent may copy ("any creature on the battlefield", "a creature or
    planeswalker you control"): objects on the battlefield (public), never a hidden one. Face-down
    ones (707.2) and Rooms (709.5d) aren't offered. -- enter as copy (wave 5F) -- an Aura is: put onto the battlefield by
    an effect, the copy chooses what it enchants as it enters (303.4f, attachments.enter); resolving as a spell (it wasn't
    cast as an Aura spell, so it has no target), it is attached by hand (engine: manual resolution)."""
    from app.rules import selectors

    phrase = what[: -len(TO_COPY)] if what.endswith(TO_COPY) else what
    limit = None
    if phrase.endswith(MV_SPENT):  # -- enter as copy (wave 5F) -- Mockingbird: the mana spent to cast the entering card
        phrase, limit = phrase[: -len(MV_SPENT)], mana_spent(plan, card_id)
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None:
        return []
    out = []
    for cid in selectors.candidates(plan, sel, controller):
        card = plan.state.cards[cid]
        if cid != card_id and card.zone.rsplit(":", 1)[-1] in sel.zones and supported_source(plan, card) is None \
                and (limit is None or plan.ch(card).mana_value <= limit):
            out.append(cid)
    return out


# -- enter as copy (wave 5F) -- "… with mana value less than or equal to the amount of mana spent to cast this creature"
# (Mockingbird): the mana actually spent on its total cost (601.2h, the payment record), as it enters (614.12a); not cast
# (put onto the battlefield, a copy of the spell: 707.10) — none was spent, 0.
MV_SPENT = " with mana value up to the mana spent to cast it"
_MV_SPENT_TEXT = " with mana value less than or equal to the amount of mana spent to cast ~"


def mana_spent(plan: Plan, card_id: str | None) -> int:
    card = plan.state.cards.get(card_id or "")
    record = plan.rules.payments.get(plan.oid(card)) if card is not None else None
    if card is None or record is None or record.cast_from is None:
        return 0
    if not record.mana_known:  # (cast by hand: what paid for it isn't known — read as 0, said so)
        plan.note(f"{card.name or 'It'} was cast by hand: the mana spent to cast it isn't known (read as 0) — "
                  "copy by hand if more was spent", [card.id])
        return 0
    return sum(record.mana_spent.values())


def entry_options(plan: Plan, controller: str, what: str, card_id: str | None = None) -> list[DecisionOption]:
    """The options of an "enter as a copy" choice (614.12a), for ``effects._choice_options``."""
    ids = entry_candidates(plan, controller, what, card_id)
    if not ids:
        return []
    options = [DecisionOption(id=cid, label=f"{plan.ch(plan.state.cards[cid]).name or 'A permanent'} "
                                            f"({plan.name(plan.state.cards[cid].controller)})"[:200], card_id=cid) for cid in ids]
    return [*options, DecisionOption(id=NONE, label="Don't copy anything (it enters as itself)")]


def _entering_effect(plan: Plan, card: CardInstance) -> ContinuousEffect | None:
    oid = plan.oid(card)
    return next((effect for effect in plan.rules.effects if effect.layer == '1' and effect.source == ENTERING + card.id
                 and oid in effect.affected), None)


def entering_as_copy(plan: Plan, card: CardInstance) -> bool:
    """-- enter as copy (wave 5F) -- Is this card about to enter as a copy (its entering choice made)?"""
    oid = plan.oid(card)
    return any(e.layer == "1" and (e.source or "") == ENTERING + card.id and oid in e.affected for e in plan.rules.effects)


def _drop_entering(plan: Plan, card: CardInstance) -> None:
    oid = plan.oid(card)
    r = plan.rules
    r.effects = [e for e in r.effects if not (e.layer == "1" and (e.source or "") == ENTERING + card.id and oid in e.affected)]


def entering(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str] | None, out: dict[str, Any]) -> bool:
    """-- Essence of the Wild (wave 110F) -- 616.1: the card's own "may enter as a copy" and Essence's both apply; the controller applies
    the own one last, so it wins when used and otherwise the Essence copy stays (declined, or nothing to copy)."""
    if _entering(plan, card, controller, answers, out):
        return True
    from app.rules import wave110b_mirror  # -- Mystic Reflection (wave 110B) --

    wave110b_mirror.apply(plan, [(card, controller)])
    wave110b_mirror.late(plan, card, controller)
    from app.rules import wave110f_cards

    wave110f_cards.copy_on_entry(plan, card, controller)
    from app.rules import wave110e_cards  # -- Infinite Reflection (wave 110E) --

    wave110e_cards.copy_on_entry_host(plan, card, controller)
    return False


def _entering(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str] | None, out: dict[str, Any]) -> bool:
    """``replacements.entry_plan``'s hook for "You may have ~ enter as a copy of …" (707.5, a
    replacement effect: 614.1c). Its choice is made before the permanent enters (614.12a): with no
    answer yet, ``out["choice"]`` asks for it and True stops the rest of the plan (asked through
    the usual entry-choice prompts). With an answer, the copy effect is set up — on the object as it
    is now, so the rest of the plan reads the permanent's other entry replacements from the copied
    text as it would exist on the battlefield (707.5, 614.12); it follows the card onto the
    battlefield, to the object it becomes there (``rules_state._diff``) — and False lets the plan
    go on. Nothing to copy: no choice, it enters as itself."""
    d = enter_definition(plan, card)
    if d is None:
        return False
    if d.get("raid100h"):  # -- turn state (wave 100H) -- "If you attacked this turn, you may have ~ enter as a copy …" (Protean Raider: 508.1, 614.12)
        from app.rules import history

        if controller not in history.log_for(plan).attacked:
            return False
    what = str(d["what"])
    answer = (answers or {}).get(what)
    cached = _entering_effect(plan, card)
    if cached is not None and cached.copy_entry_source is not None and cached.copy_entry_source.card == answer:
        # This replacement was already applied before another entry/order choice. Its copied values and source condition are fixed.
        if d.get("tapped"):
            out["tapped"] = True
        return False
    _drop_entering(plan, card)
    # -- review (wave 22A) -- 614.12: as it would exist on the battlefield (Vesuva under Blood Moon: its ability is gone before it
    # applies, Magus of the Moon ruling)
    from app.game.state import zone_key
    from app.rules import scripts

    probe = card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})
    if not any(x.get("replacement") == "enter_as_copy" for x in scripts.definitions(plan.ch(probe)).values()):
        return False
    if answer is None:
        if not entry_candidates(plan, controller, what, card.id):
            return False
        out["choice"] = {"what": what}
        return True
    if answer in ("", NONE):
        return False
    source = plan.state.cards.get(answer)
    if source is None or answer not in entry_candidates(plan, controller, what, card.id):
        plan.note(f"{card.name or 'It'}: what it was to copy is gone, so it enters as itself", actor=controller)
        return False
    excepts = [keep_colors(ex, _own(plan, card).colors) for ex in (CopyExcept.model_validate(x) for x in d.get("excepts") or [])]
    if any(ex.pt_self110a for ex in excepts):  # -- cards (wave 110A) -- Hulking Metamorph: this creature's own power and toughness (707.9b), prototyped or not (718.3b)
        from app.rules import prototype

        mine = _own(plan, card)
        mine = prototype.overlay(mine) if prototype.is_prototyped(plan.state, card) else mine
        excepts = [ex.model_copy(update={"power": mine.power, "toughness": mine.toughness, "pt_self110a": False}) if ex.pt_self110a else ex for ex in excepts]
    if d.get('embalmed_except') and getattr(card, 'embalmed', False):
        excepts.append(CopyExcept.model_validate(d['embalmed_except']))
    source_characteristics = plan.ch(source)
    if (grant := d.get('copy_if_lacks')) and not any(grant['keyword'] in ability.keywords for ability in source_characteristics.abilities):
        excepts.append(CopyExcept(add_text=[grant['text']]))
    recipe = with_excepts(recipe_of(plan, source), excepts)
    source_snapshot = CopyEntrySource(card=source.id, object_id=plan.oid(source), controller=source.controller)
    # (on the object as it is now; it follows the card to the object it becomes as it enters,
    # whatever its number: rules_state._diff — never a predicted id, 400.7)
    duration: Literal["end_of_turn", "permanent"] = "end_of_turn" if d.get("duration") == "end_of_turn" else "permanent"
    add_copy_effect(plan, [plan.oid(card)], recipe, controller, source=ENTERING + card.id, duration=duration, entry_source=source_snapshot)
    if d.get("tapped"):  # -- enter as copy (wave 5F) -- "enter tapped as a copy" (Vesuva)
        out["tapped"] = True
    return False


def keep_colors(ex: CopyExcept, own: frozenset[str]) -> CopyExcept:
    """-- copy exceptions (wave 24A) -- 707.9c-d: "it doesn't copy that creature's color": the object keeps the colors it has (as its
    copiable values are, before this copy effect), and a color-defining ability or indicator of the copied object isn't copied."""
    return ex.model_copy(update={"keep_color": False, "set_colors": sorted(own)}) if ex.keep_color else ex


def entry_counters(plan: Plan, card: CardInstance, controller: str, ch: Characteristics, choices: dict[str, str] | None,
                   x: int | None) -> dict[str, int]:
    """-- copy exceptions (wave 24A) -- 707.9e: "… except it enters with an additional +1/+1 counter on it [if it's a creature]" is an
    additional effect of the replacement effect, so it happens only while the object enters as that copy, and isn't copied by a later
    copy. 707.9f: "if it's a creature" is judged on what the copy is (``ch``); "if you control that creature" on the copied permanent.
    (review 24A: the exception is lost only when another copy effect is applied after it; the engine applies only the entering card's
    own "enter as a copy" — ``enter_definition`` — never a copied one, so the counters are always put, even when the copied object
    has such a replacement and was itself not copying anything.)"""
    d = enter_definition(plan, card)
    if d is None or not d.get("enter_counters") or not entering_as_copy(plan, card):
        return {}
    source = plan.state.cards.get((choices or {}).get(str(d["what"]), ""))
    out: dict[str, int] = {}
    for c in d["enter_counters"]:
        if c.get("if_type") and c["if_type"] not in ch.types:
            continue
        if c.get("if_control"):
            applied = _entering_effect(plan, card)
            source_controller = applied.copy_entry_source.controller if applied is not None and applied.copy_entry_source is not None else source.controller if source is not None else None
            if source_controller != controller:
                continue
        n = int(x or 0) if c["n"] == "X" else int(c["n"])
        if n > 0:
            out[c["counter"]] = out.get(c["counter"], 0) + n
    return out


# -- becoming a copy (707.4) -------------------------------------------------------------------------
def become_copy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"~ becomes a copy of target creature [until end of turn]" (707.4): a layer-1 effect on the
    permanent where it is — no enters or leaves abilities trigger, its other effects keep applying.
    The copied values are fixed as the effect begins (707.2b, 611.2c)."""
    from app.rules import effects

    who = [c for c in effects._cards(plan, ctx, e.get("who") or "self") if plan.state.cards[c].zone.endswith(":battlefield")]
    of = effects._cards(plan, ctx, e["with"])
    if e.get("others"):  # -- copy exceptions (wave 24A) -- "each other creature": other than the one copied
        who = [c for c in who if c not in of]
    base: CopyRecipe | None = None
    if e["with"] == "event_spell":
        from app.rules import mana_source_cast

        base, problem = mana_source_cast.spell_recipe(plan, ctx)
        if problem is not None:
            _manual(plan, new_job(ctx, controller=ctx["controller"], objects=[], retarget=False, label=ctx.get("name") or "Copy"),
                    f"Becoming a copy of {problem} isn't automated: make the copy by hand, then press Done")
            return False
    if e.get("last_known") and not any(plan.state.cards[c].zone.endswith(":battlefield") for c in of):
        # -- copy exceptions (wave 24A) -- "becomes a copy of that creature" when it died / left: its copiable values as it last existed
        # (608.2h, 111.12; the same last known information a token copy reads)
        from app.rules import populate

        original = e["with"]
        lki_source = original if original.startswith("ref:") or original in ("self", "host", "cost:sacrificed", "cost:exiled") else "event"
        left = populate.left_battlefield(plan, ctx, lki_source, False)  # (review 32: Identity Thief's exiled target)
        if len(left) == 1 and isinstance(left[0][0], CopyRecipe):
            base, of = left[0][0], []
        elif left:
            _manual(plan, new_job(ctx, controller=ctx["controller"], objects=[], retarget=False, label=ctx.get("name") or "Copy"),
                    f"{ctx.get('name') or 'Copy'}: becoming a copy of {left[0][0]} isn't automated — do it by hand, then press Done")
            return False
    if not who or (base is None and len(of) != 1):
        plan.note(f"{ctx.get('name') or 'It'}: nothing becomes a copy (the permanent or what it would copy is gone)",
                  actor=ctx["controller"])
        return True
    if base is None:
        source = plan.state.cards[of[0]]
        problem = supported_source(plan, source)
        if problem is not None:
            _manual(plan, new_job(ctx, controller=ctx["controller"], objects=[], retarget=False, label=ctx.get("name") or "Copy"),
                    f"{ctx.get('name') or 'Copy'}: becoming a copy of {problem} isn't automated — do it by hand, then press Done")
            return False
        base = recipe_of(plan, source)
    own = characteristics(recipe_of(plan, plan.state.cards[who[0]]), plan.info).colors if len(who) == 1 else frozenset()
    recipe = with_excepts(base, [keep_colors(CopyExcept.model_validate(x), own) for x in e.get("excepts") or []])
    duration: Literal["end_of_turn", "permanent", "next_turn"] = "end_of_turn" if e.get("duration") == "end_of_turn" \
        else "next_turn" if e.get("duration") == "next_turn" else "permanent"  # (wave 31C: 500.4 "until your next turn")
    add_copy_effect(plan, [plan.oid(c) for c in who], recipe, ctx["controller"], duration=duration)
    if e.get("duration") == "while_attached110l" and (src110l := plan.state.cards.get(ctx.get("source_card") or "")) is not None:
        # -- (wave 110L) -- "for as long as this Equipment remains attached to it" (611.2b): ends with the attachment (delayed.expire)
        made = plan.rules.effects[-1]
        made.duration, made.source_card, made.source = "while_attached110l", src110l.id, plan.oid(src110l)
    plan.note(f"{', '.join(plan.state.cards[c].name for c in who)} becomes a copy of {recipe.source or 'it'}"
              + {"end_of_turn": " until end of turn", "next_turn": " until your next turn"}.get(duration, ""), who, actor=ctx["controller"])
    return True


def resolved(plan: Plan, card_id: str, old_oid: str) -> None:
    """608.3f / 707.10f: a copy of a permanent spell became a token permanent as it resolved; the
    values its copy effect defined are that token's (613.1), so its copy effect follows it onto
    the battlefield (the new object, 400.7). Layer-6 effects changing the permanent spell
    also continue to apply to that permanent (400.7a), without becoming copiable values."""
    card = plan.state.cards.get(card_id)
    if card is None or not card.is_token or not card.zone.endswith(":battlefield"):
        return
    new_oid = plan.oid(card)
    for e in plan.rules.effects:
        follows = (e.layer == "1" and e.copy_recipe is not None and not (e.source or "").startswith(ENTERING)) or e.layer == "6"
        if follows and old_oid in e.affected and new_oid not in e.affected:
            e.affected.append(new_oid)


# -- state-based actions (704.5d, 704.5e) -------------------------------------------------------------
def ceases_to_exist(plan: Plan, card: CardInstance) -> bool:
    """704.5d: a token outside the battlefield ceases to exist — on the stack, only a copy of a
    spell is shown as a token (it isn't one: 707.10); 704.5e: a copy of a spell outside the stack
    ceases to exist (on the battlefield: an instant or sorcery copy put there by hand; a permanent
    spell's copy became a token as it resolved, 608.3f)."""
    if not card.is_token or card.ability is not None:
        return False
    if card.zone == "stack":
        return card.copy_of is None
    if card.zone.endswith(":battlefield") and card.copy_of is not None:
        return plan.ch(card).is_instant_or_sorcery
    return False


# -- grammar (the templates are registered in app/rules/scripts.py) ------------------------------------
_COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_SUBJECT = r"(?:(?:that )?(?:it|the token|the tokens|the copy|the copies|they|those creatures|those tokens) )?"
_QUOTE = re.compile(r'"[^"]*"')


def parse_excepts(text: str | None, enters: bool = False) -> CopyExcept | None:
    """A copy effect's exceptions (707.9) in the closed wording the engine carries out: "it has
    haste [and "…"]" (707.9a), "it isn't legendary", "it's an artifact / a Spirit in addition to
    its other types" (707.9b; 707.9d: type-defining abilities stay), "it's 7/7" (707.9b; 707.9d:
    a P/T-defining ability isn't copied), "the copy is red" (707.9d), joined by commas and "and".
    None for anything else (the ability stays manual).
    -- copy exceptions (wave 24A) -- also "it enters with [N] additional +1/+1 counters on it [if it's a creature]" (707.9e: an
    additional effect, read only with ``enters``: an object entering as a copy), "if it's a creature, <exceptions>" (707.9f),
    "it's an artifact … and it loses all other card types" (707.9b), "it has hexproof and this ability" (707.9a), "it doesn't copy
    that creature's color" (707.9c)."""
    ex = CopyExcept()
    if not text:
        return ex
    cond = re.fullmatch(r"(?P<head>.*?),? and,? if it(?:'s| is) an? (?P<t>creature|planeswalker), (?P<tail>.+)", text)
    if cond is not None:  # 707.9f: judged on what the copy would be without that exception (``_apply``)
        head, tail = parse_excepts(cond["head"], enters), parse_excepts(cond["tail"], enters)
        kind = cond["t"].capitalize()
        if head is None or tail is None or tail.model_copy(update={"add_text": [], "enter_counters": []}) != CopyExcept():
            return None
        return head.model_copy(update={"text_if": {kind: tail.add_text} if tail.add_text else {},
                                       "enter_counters": [{**c, "if_type": kind} for c in tail.enter_counters]}) \
            if not head.text_if and not head.enter_counters else None
    quotes = [q.replace("‹granter›", "~") for q in _QUOTE.findall(text)]  # (a quoted ability is the copy's own: its name is ~)
    masked = _QUOTE.sub("\x00", text)
    # (wave 24A: "he's a legendary …", "her name is …" — a card that speaks of itself as a person; "is"/"has"/"loses" after a comma or "and")
    masked = re.sub(r"(^|, | and )(?:he|she)(?=['\s])", r"\1it", masked)
    masked = re.sub(r"(?:\b(?:his|her)|~'s) (name|power|other)\b", r"its \1", masked)
    masked = re.sub(r"(^|, | and )~(?=['\s])", r"\1it", masked)  # (scripts._self_pronouns wrote a character's "he" as ~)
    masked = re.sub(r", and its power and toughness are equal to (?:this creature's|its) power and toughness", ", and it is PTSELF110A", masked)  # (wave 110A: Hulking Metamorph)
    parts = re.split(r",? and (?=(?:it|it's|it is|is|has|loses|the token|the copy|they|those creatures)\b)"
                     r"|, (?=(?:it|the token|the copy|they|is|has|those creatures)\b)", masked)
    for part in parts:
        restored = part
        while "\x00" in restored and quotes:
            restored = restored.replace("\x00", quotes.pop(0), 1)
        if "\x00" in restored or not _except_clause(restored.strip(), ex):
            return None
    return ex if enters or not ex.enter_counters else None  # (707.9e: only an object entering as a copy "enters with" more)


def _except_clause(clause: str, ex: CopyExcept) -> bool:
    from app.rules import layers, token_grammar
    from app.rules.creature_types import CREATURE_TYPES

    c = re.sub(r"\bit's\b", "it is", clause)
    c = re.sub(r"\bthey're\b", "they are", c)
    c = c.replace("isn't", "is not").replace("aren't", "are not")
    if re.fullmatch(r"(?:its|his|her) name is [^\"]+", c) and ex.name is None:  # -- enter as copy other (wave 20F) -- 707.9b: a modified name
        ex.name = NAME_MARKER
        return True
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?P<s>(?:legendary|snow)(?: and (?:legendary|snow))?) in addition to (?:its|their) other types", c)
    if m:  # (707.9b; wave 24A: "legendary and snow", Moritte of the Frost)
        ex.add_supertypes = sorted({*ex.add_supertypes, *(w.capitalize() for w in m["s"].split(" and "))})
        return True
    m = re.fullmatch(_SUBJECT + r"enters? with (?P<n>an?|one|two|three|four|X|\d+) (?:additional )?(?P<k>\+1/\+1|loyalty|shield) counters? on (?:it|them)"
                                r"(?: if (?:it is an? (?P<t>creature|planeswalker)|(?P<own>you control that (?:creature|permanent))))?", c)
    if m:  # -- copy exceptions (wave 24A) -- 707.9e: an additional effect of the replacement (``entry_counters``), not a copiable value
        from app.rules import token_grammar

        n: Any = "X" if m["n"] == "X" else int(m["n"]) if m["n"].isdigit() else token_grammar.NUMBERS[m["n"]]
        ex.enter_counters = [*ex.enter_counters, {"counter": m["k"], "n": n, **({"if_type": m["t"].capitalize()} if m["t"] else {}),
                                                    **({"if_control": True} if m["own"] else {})}]
        return True
    if re.fullmatch(_SUBJECT + r"(?:is|are) an artifact creature in addition to (?:its|their) other types", c):  # -- cards (wave 110A) -- 707.9b
        ex.add_types = sorted({*ex.add_types, "Artifact", "Creature"})
        return True
    if c == "it is PTSELF110A" and ex.power is None:  # 707.9b
        ex.pt_self110a = True  # (the entering card's own values, set in ``entering``: it may have been cast prototyped, 718.3b)
        return True
    if re.fullmatch(_SUBJECT + r"loses all other card types", c):  # (707.9b; wave 24A) — with the types the exception names
        return ex.set_types is not None
    if re.fullmatch(_SUBJECT + r"doesn't copy that creature's color", c.replace("does not", "doesn't")) and not ex.keep_color:  # (707.9c)
        ex.keep_color = True
        return True
    if re.fullmatch(_SUBJECT + r"(?:is|are) not legendary(?: if (?:the|that) (?:spell|creature|permanent) is legendary)?", c):
        ex.remove_supertypes = sorted({*ex.remove_supertypes, "Legendary"})
        return True
    if re.fullmatch(_SUBJECT + r"(?:has|have) this ability", c):  # -- enter as copy (wave 5F) -- 707.9a: the ability's own
        ex.add_text = [*ex.add_text, THIS_ABILITY]  # text, written in by ``scripts.define`` (``with_this_ability``)
        return True
    if re.fullmatch(_SUBJECT + r"(?:has|have) its other abilities", c):  # -- copy exceptions (wave 31C) -- 707.9a: "except it has Sakashima's other
        ex.add_text = [*ex.add_text, OTHER_ABILITIES]  # abilities": the card's printed lines but this one, written in by ``with_this_ability``
        return True
    if re.fullmatch(_SUBJECT + r"(?:has|have) no mana cost", c):  # -- keywords (wave 15E) -- 707.9b
        ex.no_mana_cost = True
        return True
    if re.fullmatch(_SUBJECT + r"(?:is|are) legendary", c):  # (707.9b; wave 24A: "except it's legendary", Adagia)
        ex.add_supertypes = sorted({*ex.add_supertypes, "Legendary"})
        return True
    m = re.fullmatch(_SUBJECT + r"(?:has|have) (?P<abil>.+)", c)
    if m and ("this ability" in _QUOTE.sub("", m["abil"])):  # -- copy exceptions (wave 24A) -- "has flying and this ability [and "…"]" (707.9a)
        quotes = _QUOTE.findall(m["abil"])
        bits = [b for b in re.split(r",? and |, ", _QUOTE.sub("\x00", m["abil"])) if b]
        kws: list[str] = []
        added: list[str] = []
        for b in bits:
            if b == "this ability":
                added.append(THIS_ABILITY)
            elif b == "\x00" and quotes:
                q = token_grammar._with(quotes.pop(0))
                if q is None or q[0] or q[1] is None:
                    return False
                added.append(q[1])
            elif (found := token_grammar._with(b)) is not None and found[0] and found[1] is None:
                kws += found[0]
            else:
                return False
        ex.add_text = [*ex.add_text, *(k.capitalize() for k in kws), *added]
        return True
    if m:
        found = token_grammar._with(m["abil"])
        if found is None:
            return False
        kws, quoted = found
        ex.add_text = [*ex.add_text, *(k.capitalize() for k in kws), *([quoted] if quoted else [])]
        return bool(kws or quoted)
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?P<p>\d+)/(?P<t>\d+)", c)
    if m:
        ex.power, ex.toughness = m["p"], m["t"]
        return True
    # "it's a 1/1 red Balloon creature [with flying] in addition to its other [colors and] types" (707.9b):
    # P/T set, the creature type(s) and card types added, the colors set — or added with "colors and"
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?:an? )?(?P<legend>legendary )?(?P<p>\d+)/(?P<t>\d+) (?P<colors>(?:white|blue|black|red|green)"
                                r"(?:,? (?:and )?(?:white|blue|black|red|green))* )?(?P<subs>(?:[A-Z][A-Za-z'-]* )*)"
                                r"(?P<types>artifact(?: creatures?)?|creatures?)?(?: with (?P<kws>[^\"]+?))? ?in addition to "
                                r"(?:its|their) other (?P<both>colors and )?types", c)
    if m:
        artifact = (m["types"] or "").startswith("artifact")
        subs = [s[:-1] if s.endswith("s") and s[:-1] in CREATURE_TYPES and s not in CREATURE_TYPES else s
                for s in m["subs"].split()]
        allowed = CREATURE_TYPES | (token_grammar.ARTIFACT_TYPES if artifact else frozenset())
        with_kws = token_grammar._with(m["kws"]) if m["kws"] else ([], None)
        if with_kws is None or with_kws[1] is not None or not all(s in allowed for s in subs):
            return False
        colors = [_COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", m["colors"] or "")]
        if colors and m["both"]:
            ex.add_colors = sorted({*ex.add_colors, *colors})
        elif colors:
            ex.set_colors = colors
        ex.power, ex.toughness = m["p"], m["t"]
        if m["legend"]:  # (wave 24A: "he's a legendary 4/4 Human Villain creature in addition to his other types", Absorbing Man)
            ex.add_supertypes = sorted({*ex.add_supertypes, "Legendary"})
        # (wave 20F: "a 2/2 black Zombie in addition to its other colors and types": the creature type alone, 707.9b)
        ex.add_types = sorted({*ex.add_types, *(["Creature"] if "creature" in (m["types"] or "") else []), *(["Artifact"] if artifact else [])})
        ex.add_subtypes = sorted({*ex.add_subtypes, *subs})
        ex.add_text = [*ex.add_text, *(k.capitalize() for k in with_kws[0])]
        return True
    # -- token copies & attach on entry (wave 5J) -- "it's a 1/1 green Frog" / "it's a 4/4 black Zombie" (707.9b):
    # P/T and colors set, the creature types set (205.1a: no "in addition": they replace the copied creature types)
    m = re.fullmatch(_SUBJECT + r"(?:is|are) an? (?P<p>\d+)/(?P<t>\d+) (?P<colors>(?:white|blue|black|red|green)"
                                r"(?:,? (?:and )?(?:white|blue|black|red|green))* )?(?P<subs>[A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*)*)(?P<creature> creature)?"
                                r"(?: with (?P<kws>[^\"]+))?", c)  # (wave 24A: "a 6/6 green Dinosaur creature with trample", "a 3/3 black Wraith with menace")
    with_kws = token_grammar._with(m["kws"]) if m and m["kws"] else ([], None)
    if m and with_kws is not None and with_kws[1] is None and all(s in CREATURE_TYPES for s in m["subs"].split()) \
            and ex.set_creature_types is None:
        ex.add_text = [*ex.add_text, *(k.capitalize() for k in with_kws[0])]
        ex.power, ex.toughness = m["p"], m["t"]
        if m["colors"]:
            ex.set_colors = [_COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", m["colors"])]
        ex.set_creature_types = m["subs"].split()
        if m['creature']:
            ex.set_types = ['Creature']  # 205.1a: an explicit card type replaces the copied card types.
        return True
    # -- enter as copy (wave 5F) -- "it's a Synth artifact creature in addition to its other types" (707.9b, 707.9d)
    m = re.fullmatch(_SUBJECT + r"(?:is|are) an? (?P<subs>(?:[A-Z][A-Za-z'-]* )+)(?P<t>artifact creature|artifact|creature)s? "
                                r"in addition to (?:its|their) other types", c)
    if m and all(s in CREATURE_TYPES | layers.ARTIFACT_TYPES for s in m["subs"].split()):  # (wave 24A: "a Vehicle artifact", Dermotaxi)
        ex.add_types = sorted({*ex.add_types, *(w.capitalize() for w in m["t"].split())})
        ex.add_subtypes = sorted({*ex.add_subtypes, *m["subs"].split()})
        return True
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?:an? )?(?P<t>artifact|enchantment)s? in addition to (?:its|their) other types", c)
    if m:
        ex.add_types = sorted({*ex.add_types, m["t"].capitalize()})
        return True
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?:an? )?(?P<s>[A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*)*?) in addition to "
                                r"(?:its|their) other (?:creature )?types", c)
    if m and all(s in CREATURE_TYPES | layers.LAND_TYPES | layers.ARTIFACT_TYPES for s in m["s"].split(" ")):  # (wave 24A: "a Cave")
        ex.add_subtypes = sorted({*ex.add_subtypes, *m["s"].split(" ")})
        return True
    # -- copy exceptions (wave 24A) -- 707.9b: "it's a Vehicle artifact with crew 3" / "it's an artifact": the card types are exactly these
    # (no "in addition to its other types"; "and loses all other card types" says so, Imposter Mech, Machine God's Effigy)
    m = re.fullmatch(_SUBJECT + r"(?:is|are) an? (?P<subs>(?:[A-Z][A-Za-z'-]* )*)(?P<t>artifact|enchantment)(?: with (?P<kws>.+))?", c)
    if m and "in addition" not in _QUOTE.sub("", c) and ex.set_types is None:
        allowed = layers.ARTIFACT_TYPES if m["t"] == "artifact" else layers.ENCHANTMENT_TYPES
        crew = re.findall(r"\bcrew \d+", m["kws"] or "")
        rest = re.sub(r",? ?(?:and )?\bcrew \d+", "", m["kws"] or "").strip()
        found = token_grammar._with(rest) if rest else ([], None)
        if found is None or not all(sub in allowed for sub in m["subs"].split()):
            return False
        ex.set_types = [m["t"].capitalize()]
        ex.add_subtypes = sorted({*ex.add_subtypes, *m["subs"].split()})
        ex.add_text = [*ex.add_text, *(k.capitalize() for k in found[0]), *(k.capitalize() for k in crew), *([found[1]] if found[1] else [])]
        return True
    m = re.fullmatch(_SUBJECT + r"(?:is|are) (?P<c>white|blue|black|red|green)", c)
    if m:
        ex.set_colors = [_COLOR_WORDS[m["c"]]]
        return True
    return False


# -- enter as copy (wave 5F) -- "except it has this ability" (Thespian's Stage, Cryptoplasm, Dimir Doppelganger): the copy
# gains the very ability that made it (707.9a) — its printed line, filled in from the ability being defined
THIS_ABILITY = "\x00this ability"
NAME_MARKER = "\x00name"  # -- enter as copy other (wave 20F) -- ``with_this_ability`` writes the printed name in
OTHER_ABILITIES = "\x00other abilities"  # -- copy exceptions (wave 31C) -- "except it has ~'s other abilities" (Sakashima of a Thousand Faces)


def _spread(x: Any, others: list[str]) -> Any:
    """-- copy exceptions (wave 31C) -- every ``add_text`` marker ``OTHER_ABILITIES`` replaced by the card's other lines."""
    if isinstance(x, dict):
        return {k: [t for v in val for t in (others if v == OTHER_ABILITIES else [v])] if k == "add_text" and isinstance(val, list)
                else _spread(val, others) for k, val in x.items()}
    return [_spread(i, others) for i in x] if isinstance(x, list) else x


def with_this_ability(d: dict[str, Any], ability: Any, ch: Characteristics) -> dict[str, Any] | None:
    """The definition with "this ability" written as the ability's own line (None: the marker is somewhere it can't be).
    -- copy exceptions (wave 31C) -- a line that names the card has the name as "this permanent" (a copy has another name, so "Volrath
    becomes …" would name a stranger there; not when the copy is given the name again, nor the Exhaust / Boast / Power-up / Forecast words), "its other abilities" (707.9a) are the card's
    other lines that don't name it (Sakashima of a Thousand Faces: Partner and the legend-rule line)."""
    import json

    from app.rules import scripts

    text = ability.text
    raw = json.dumps(d)
    if json.dumps(OTHER_ABILITIES)[1:-1] in raw:
        rest = [a for a in ch.abilities if a.index != ability.index and not a.intrinsic]
        if any("~" in scripts.self_text(a.text, ch.name) for a in rest):
            return None
        d = _spread(d, [strip_reminders(a.text).strip() for a in rest])
        raw = json.dumps(d)
    name_marker = json.dumps(NAME_MARKER)[1:-1]
    named = name_marker in raw  # (the copy is given the card's own name again: its text keeps naming it, review 31 ``renamed``)
    if name_marker in raw:  # -- enter as copy other (wave 20F) -- "except its name is Sakashima the Impostor": the name as printed (not ~)
        shown = re.search(r"\b(?:its|his|her) name is (?P<n>.+?)(?=, (?:it|he|she|they)\b| and (?:it|he|she|they)\b|\.(?:\s|$)|$)", text)
        if shown is None or '"' in shown["n"]:
            return None
        raw = raw.replace(name_marker, json.dumps(shown["n"])[1:-1])
        d = json.loads(raw)
    marker = json.dumps(THIS_ABILITY)
    if marker not in raw:
        return d
    if d.get("kind") not in ("activated", "triggered") or "\\u0000" in text or '"' in text:
        return None
    own = text if named or text.startswith(("Exhaust — ", "Boast — ", "Power-up — ", "Forecast — ")) \
        else re.sub(r"(^|: |\. )this permanent", r"\1This permanent", renamed(text, ch.name, "this permanent"))  # (unchanged if it names no one)
    return json.loads(raw.replace(marker, json.dumps(own)))


def _dump(ex: CopyExcept) -> dict[str, Any]:
    return {"excepts": [ex.model_dump(mode="json", exclude_defaults=True)]} if ex != CopyExcept() else {}


def _target_group(phrase: str) -> dict[str, Any] | None:
    """The target group a phrase names (app/rules/language.py), None if it isn't one it reads."""
    from app.rules import language

    try:
        return language.target_group(phrase)
    except language._Fail:
        return None


def parse_conditional_copy_gain(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """A conditional grant changes copies, rather than deciding whether to copy a spell."""
    m = re.fullmatch(r'(?P<copy>.+)\. If it\'s a permanent spell, (?P<gain>the copy gains .+)', body.strip(), re.IGNORECASE)
    if m is None:
        return None
    from app.rules import scripts

    prefix = scripts.parse_effects(m["copy"] + ".", it, event_player=event_player)
    gain = scripts.parse_effects(m["gain"][:1].upper() + m["gain"][1:])
    if prefix is None or gain is None or prefix[2] or gain[1] is not None or gain[2]:
        return None
    if sum(e["do"] == "copy_spell" for e in prefix[0]) != 1 or any(e["do"] not in ("copy_spell", "copy_new_targets") for e in prefix[0]):
        return None
    if len(gain[0]) != 1 or gain[0][0]["do"] != "copy_gain":
        return None
    return [*prefix[0], {**gain[0][0], "if_permanent": True}], prefix[1], False


def parse_multiple_stack_targets(phrase: str) -> tuple[list[dict[str, Any]], Any] | None:
    from app.rules import selectors

    group = _target_group(phrase)
    if group is None or group["min"] != 0 or group["max"] <= 1:
        return None
    sel = selectors.from_key(group["what"]) if group["what"].startswith(selectors.PREFIX) else None
    if sel is None or sel.zones != ("stack",) or sel.ability is not None:
        return None
    return [{"do": "copy_spell", "who": "target", "choose_source_order": True}], group


def parse_copy_target(what: str, exc: str | None) -> tuple[list[dict[str, Any]], Any] | None:
    """"copy target instant or sorcery spell [you control] [, except that the copy is red]" /
    "copy target triggered ability you control" (707.10): the effect and its target."""
    from app.rules import selectors

    group = _target_group("target " + what)
    if group is None or (group["min"], group["max"]) != (1, 1) or "another" in group:
        return None
    sel = selectors.from_key(group["what"]) if group["what"].startswith(selectors.PREFIX) else None
    if sel is None or sel.zones != ("stack",) or "single_target" in sel.extras:
        return None  # "with a single target" is outside this copy grammar
    ex = parse_excepts(exc)
    if ex is None or (sel.ability is not None and exc):
        return None  # (an ability has no characteristics to except)
    hybrid = sel.ability == selectors.SPELL_OR_ABILITY
    do = "copy_ability" if sel.ability is not None and not hybrid else "copy_spell"
    return [{"do": do, "who": "target", **({"hybrid": True} if hybrid else {}), **_dump(ex)}], group["what"]


_SOURCES = {"~": "self", "it": "it", "that creature": "it", "that permanent": "it", "that artifact": "it",
            "that token": "it", "that card": "it", "equipped creature": "host", "enchanted creature": "host",
            "enchanted permanent": "host", "enchanted artifact": "host",
            "the sacrificed creature": "cost:sacrificed",  # -- activated other (wave 52D) -- an activation cost's sacrifice, as it last existed (populate.left_battlefield)
            "the exiled card": "pay_exiled",
            "the card exiled to activate this ability": "cost_exiled"}  # (wave 15E: embalm, 702.128a)  # -- if you do (wave 8C) -- bound to a payment's exiled card (pay_objects.bind)


def parse_token_copy(n: str, tapped: bool, src: str, exc: str | None) -> tuple[list[dict[str, Any]], Any] | None:
    """"create [N] [tapped] token(s) that's a copy / are copies of <source> [, except …]": the source
    is a target, the source itself (~), what an earlier instruction or the trigger was about ("it",
    "that creature") or the permanent the source is attached to."""
    from app.rules import exiled_with, token_grammar

    word = n.lower()
    if word not in token_grammar.NUMBERS and not word.isdigit() and word != "x":
        return None
    if exc == "their power is half that creature's power and their toughness is half that creature's toughness rounded up":
        found = parse_token_copy(n, tapped, src, None)
        if found is None or src != "that creature":
            return None
        return [{**found[0][0], "half_pt": True}], found[1]
    ex = parse_excepts(exc, enters=True)
    if ex is None:
        return None
    effect: dict[str, Any] = {"do": "token_copy", "n": token_grammar._qty(word), **_dump(ex)}
    if tapped:
        effect["tapped"] = True
    if src == "the exiled card":
        from app.rules import pay_objects

        if pay_objects.activation_exiled():
            return [{**effect, "who": "cost:exiled"}], None
    if src == "the exiled card" and exiled_with.linked():  # -- resolution memory (wave 22D) -- 607.2a: the card the linked ability exiled (imprint)
        return [{**effect, "who": "it:exiled"}], None
    if src in _SOURCES:
        return [{**effect, "who": _SOURCES[src]}], None
    # -- resolution memory (wave 22D) -- "create a token that's a copy of each of up to two target creatures you control" (Twinflame): one token
    # for each object chosen (115.1, 608.2b: each still the same object as it resolves)
    each = re.fullmatch(r"each of ((?:up to \w+|any number of) target .+)", src)
    group = _target_group(each[1] if each else src)
    if group is None or (group["max"] != 1 and not each):
        return None
    return [{**effect, "who": "target"}], group


def _dur(until: bool | str) -> dict[str, str]:
    """-- becomes a copy (wave 31C) -- the duration of a "becomes a copy" effect (611.2a): "until end of turn" (True / "end of turn")
    or "until your next turn" (500.4)."""
    return {"duration": "next_turn" if until == "your next turn" else "end_of_turn"} if until else {}


def parse_become(what: str | None, until: bool | str, exc: str | None, pre: str = "", src: str | None = None
                 ) -> tuple[list[dict[str, Any]], Any] | None:
    """"~ becomes a copy of [another / up to one other] target <permanent> [until end of turn] [, except …]" (707.4); -- copy exceptions
    (wave 24A) -- "another" is any object but the source itself (201.5, the selector's ``other``), "up to one" may pick none (then
    nothing becomes a copy, ``become_copy``)."""
    from app.rules import selectors

    if src is not None:  # -- copy exceptions (wave 24A) -- "~ becomes a copy of it / that creature": what the trigger or an earlier instruction named
        ex = parse_excepts(exc)
        if ex is None or src not in _SOURCES or what is not None:
            return None
        return [{"do": "become_copy", "who": "self", "with": _SOURCES[src], **({"last_known": True} if src != "that card" else {}),
                 **_dump(ex), **_dur(until)}], None
    group = _target_group(pre + "target " + (what or ""))
    if what is None or group is None or (group["min"], group["max"]) not in ((1, 1), (0, 1)) or (group["min"] == 0 and not pre.startswith("up to one")):
        return None
    sel = selectors.from_key(group["what"]) if group["what"].startswith(selectors.PREFIX) else None
    # (wave 24A: or a card in a graveyard — public, its printed values are what is copied, 707.2: Lazav, the Multifarious)
    if sel is None or sel.zones not in (("battlefield",), ("graveyard",)) or sel.player is not None or (sel.zones == ("graveyard",) and not sel.card):
        return None
    ex = parse_excepts(exc)
    if ex is None:
        return None
    effect: dict[str, Any] = {"do": "become_copy", "who": "self", "with": "target", **_dump(ex), **_dur(until)}
    # (review 24A: "up to one" keeps its group, min 0 — the ability goes on the stack with no target, 115.1/601.2c, and the rest of it
    # still happens: Irma's "Then put a +1/+1 counter on her")
    return [effect], group if group["min"] == 0 else group["what"]


def parse_become_targets(a: str, b: str, until: str, exc: str | None) -> tuple[list[dict[str, Any]], Any] | None:
    """-- becomes a copy (wave 31C) -- "Target artifact you control becomes a copy of a second / another target artifact you control [until end of
    turn] [, except it isn't legendary]" (Shuri, Saheeli, The Animus): both are targets of the ability (115.1), the first becomes a copy of the
    second (707.4) as it is when the effect begins (707.2b; a card in a graveyard or exile: its printed values); "another" is a different
    object (115.3, `_add_groups`), "a second" or a plain "target" may be the same."""
    from app.rules import selectors

    first, second = _target_group(a), _target_group(b if b.startswith("another ") else b.removeprefix("a second "))
    ex = parse_excepts(exc)
    if ex is None or ex.name is not None or THIS_ABILITY in ex.add_text or OTHER_ABILITIES in ex.add_text or first is None or second is None:
        return None  # (a name, "this ability", "its other abilities" speak of the ability's own source, not of a target)
    if "another" in first or any((g["min"], g["max"]) != (1, 1) for g in (first, second)):
        return None
    s1, s2 = (selectors.from_key(g["what"]) if g["what"].startswith(selectors.PREFIX) else None for g in (first, second))
    if s1 is None or s1.zones != ("battlefield",) or s1.player is not None or s2 is None or s2.player is not None \
            or s2.zones not in (("battlefield",), ("graveyard",), ("exile",)) or s2.card != (s2.zones != ("battlefield",)):
        return None
    return [{"do": "become_copy", "who": "target:0", "with": "target:1", **_dump(ex), **_dur(until)}], [first, second]


def parse_become_group(grp: str, ctl: bool, others: bool, src: str | None, what: str | None, until: bool, exc: str | None
                       ) -> tuple[list[dict[str, Any]], Any] | None:
    """-- copy exceptions (wave 24A) -- "Each other creature [you control] becomes a copy of that creature / target <permanent> [until end of
    turn] [, except it isn't legendary]" (Nanogene Conversion, Mirrorweave, Hall of Mirrors) and "each creature you control other than
    the chosen creature …" (Loki): one layer-1 effect on the group as it is as the effect begins (611.2c), each a copy of the same
    object (707.2: its values as they are then). "Other" is other than the object copied. Exceptions that name one object (its name, "this
    ability", the color it keeps) have no meaning for a group."""
    from app.rules import selectors

    sel = selectors.parse(f"{grp} you control" if ctl else grp)
    if sel is None or sel.zones != ("battlefield",) or sel.player is not None or sel.card or sel.other:
        return None
    ex = parse_excepts(exc)
    if ex is None or ex.name is not None or ex.keep_color or THIS_ABILITY in ex.add_text:
        return None
    effect: dict[str, Any] = {"do": "become_copy", "who": sel.key(), "with": "it" if src else "target", **_dump(ex)}
    if others:
        effect["others"] = True
    if until:
        effect["duration"] = "end_of_turn"
    if src:
        return [effect], None
    group = _target_group("target " + (what or ""))
    if group is None or (group["min"], group["max"]) != (1, 1) or "another" in group:
        return None
    sel2 = selectors.from_key(group["what"]) if group["what"].startswith(selectors.PREFIX) else None
    if sel2 is None or sel2.zones != ("battlefield",) or sel2.player is not None:
        return None
    return [effect], group["what"]


# (wave 31C: "another creature you control" — the entering card isn't on the battlefield, so "another" excludes nothing: Sakashima of a Thousand Faces)
_CLONE = re.compile(r"^You may have ~ enter (?P<tapped>tapped )?as a copy of (?:any|a|an|another) (?P<rest>.+)$")
# -- enter as copy (wave 5F) -- "As ~ enters, you may have it become a copy of any creature on the battlefield until end
# of turn, except it has haste." (Cursed Mirror): an "as enters" replacement (614.1c) — it enters as the copy (707.5),
# and the copy effect ends at the cleanup step (514.2)
_AS_ENTERS = re.compile(r"^As ~ enters, you may have it become a copy of (?:any|a|an) (?P<rest>.+?) until end of turn"
                        r"(?P<tail>(?:, except .+)?\.)$")


def define_static(text: str) -> dict[str, Any] | None:
    """"You may have ~ enter as a copy of any creature on the battlefield [, except …]." (707.5;
    a replacement effect, 614.1c): the definition ``replacements.entry_plan`` reads through
    :func:`entering`. Its choice is named "<what> to copy" (the prompt: "as it enters, choose a
    creature to copy")."""
    from app.rules import selectors

    m = _CLONE.match(text)
    until_eot = False
    if m is None:  # -- enter as copy (wave 5F) -- Cursed Mirror
        m = _AS_ENTERS.match(text)
        if m is None:
            return None
        until_eot = True
    rest = m["rest"] + (m["tail"] if until_eot else "")
    if rest.endswith("."):
        rest = rest[:-1]
    elif not rest.endswith('."'):  # (a quoted ability can end the sentence: its period is inside the quotes)
        return None
    what, _, exc = rest.partition(", except ")
    spent = what.endswith(" on the battlefield" + _MV_SPENT_TEXT)  # -- enter as copy (wave 5F) -- Mockingbird
    what = what.removesuffix(_MV_SPENT_TEXT).removesuffix(" on the battlefield")
    sel = selectors.parse(what)
    # (wave 24A: or a card in a graveyard — "any creature card in a graveyard", Body Double: public, its printed values, 707.2)
    master110k = what.removeprefix("a ") == "creature card in exile with a takeover counter on it"  # -- (wave 110K) -- The Master, Formed Anew: the cards its Body Thief exiled
    if master110k and sel is not None and sel.zones == ("exile",) and sel.card:
        pass
    elif sel is None or sel.player is not None or sel.other or sel.zones not in (("battlefield",), ("graveyard",)) \
            or sel.card != (sel.zones == ("graveyard",)):
        return None
    # -- enter as copy (wave 5F) -- any permanent ("nonland permanent", "artifact or enchantment", "Equipment"): an Aura
    # would have to attach as it enters (303.4f) — not offered as something to copy (``entry_candidates`` / ``supported_source``);
    # a Room is (review 18G: the copy has its halves, 709.5b, and neither door unlocked, 709.5c/d)
    conditional = re.fullmatch(r"it has vanishing (?P<n>\d+) if that creature doesn't have vanishing", exc)
    ex = CopyExcept() if conditional is not None else parse_excepts(exc or None, enters=True)
    if ex is None:
        return None
    counters, ex = ex.enter_counters, ex.model_copy(update={"enter_counters": []})  # (707.9e: not copiable values)
    out = {"kind": "replacement", "replacement": "enter_as_copy", "optional": True,
           "what": what + (MV_SPENT if spent else "") + TO_COPY, "effects": [], **_dump(ex), **({"enter_counters": counters} if counters else {})}
    if conditional is not None:
        out['copy_if_lacks'] = {'keyword':'vanishing', 'text':f"Vanishing {int(conditional['n'])}"}
    if not until_eot and m["tapped"]:
        out["tapped"] = True  # (Vesuva: tapped only if it enters as a copy)
    if until_eot:
        out["duration"] = "end_of_turn"
    return out


# -- cast keywords (wave 43D) -- demonstrate (702.144a): "When you cast this spell, you may copy it and you may choose new targets for the copy. If you
# copy the spell, choose an opponent. That player copies the spell and may choose new targets for that copy." The trigger (casting._demonstrate_trigger)
# is optional ("you may copy it", asked as it resolves); its two effects put the controller's copy on the stack, then the chosen opponent's above it, so the
# opponent's copy resolves first, then yours, then the original (the rulings of the Technique cycle).
def demonstrate_copy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    card = plan.state.cards.get(e["spell"])
    if card is not None and plan.manual(card):
        plan.note("Demonstrate: the spell is handled by hand, so there is nothing to copy")
        return True
    return run(plan, new_job(ctx, controller=ctx["controller"], objects=[(e["spell"], e["object"], 1)], retarget=True, label="Demonstrate"))


def demonstrate_opponent(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    card = plan.state.cards.get(e["spell"])
    if card is None or plan.manual(card) or (card.zone == "stack" and uncopyable(plan, card) == ""):
        return True  # (113.6g: it can't be copied, so it wasn't: "if you copy the spell" didn't happen)
    opponents = [p for p in plan.live() if p != ctx["controller"]]
    if not opponents:
        return True
    if len(opponents) == 1:
        return _opponent_copies(plan, ctx, e, opponents[0])
    plan_decide(plan, player=ctx["controller"], kind="choose_one", prompt="Demonstrate: choose an opponent to also copy the spell",
                options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": "demonstrate", "ctx": ctx, "e": e})
    return False


def _opponent_copies(plan: Plan, ctx: Context, e: dict[str, Any], opponent: str) -> bool:
    return run(plan, new_job(ctx, controller=opponent, objects=[(e["spell"], e["object"], 1)], retarget=True, label="Demonstrate"))


def resume_demonstrate(plan: Plan, d: Any, chosen: list[str]) -> None:
    r = d.resume
    if _opponent_copies(plan, r["ctx"], r["e"], chosen[0]):
        go_on(plan, {"ctx": r["ctx"]})


PRIMITIVES = {"copy_spell": copy_stack_object, "copy_ability": copy_stack_object, "copy_new_targets": new_targets_marker, "copy_gain": new_targets_marker,
              "copy_each": copy_each, "copy_each_marker": new_targets_marker,
              "token_copy": token_copy, "become_copy": become_copy, "copy_cards": copy_cards,
              "demonstrate_copy": demonstrate_copy, "demonstrate_opponent": demonstrate_opponent}
RESUME = {"copy_source_order": resume_source_order, "card_copy_continue": resume_card_copy_continue, "copy_each": resume_each, "copy_mode": resume_mode, "copy_order": resume_copy_order, "copy_target": resume_target, "copy_manual": resume_manual,
          "demonstrate": resume_demonstrate}
