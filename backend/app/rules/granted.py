"""Temporary quoted grants (CR 113.10, 611.2, 613.1f), researched against CR 2026-09-25.

"Until end of turn, target creature gets +2/+0 and gains "When this creature dies, return it to the
battlefield tapped under its owner's control."", "Until end of turn, creatures you control gain "{T}:
This creature deals 1 damage to any target."", "{2}{R}{G}: Until end of turn, this land becomes a 3/3
… Elemental creature with "Whenever this creature attacks, put a +1/+1 counter on it." It's still a
land.": a resolving spell or ability gives objects an ability, for the duration it states (611.2a;
none stated: the game). This module holds what the pieces that read and run such a grant share.

* **The sentence.** The quoted abilities are set aside (``protect``) while the sentence around them
  is read by the ordinary grammar (app/rules/language.py "quoted grants"), each one is checked on
  its own (``quote``), and the grant effect carries their texts (``{"do": "grant", "who": …,
  "keywords": […], "abilities": ["When this creature dies, …."]}``). A quote the engine can't
  carry out, or can't read where it would be granted, leaves the whole sentence manual.
* **One continuous effect** (app/rules/effects.py ``grant``): keywords and quoted abilities go in the
  same layer-6 effect (613.1f), with one timestamp (613.7b); the objects it affects are fixed when
  it begins (611.2c: an ability is a characteristic, 109.3 — a creature that enters later doesn't
  get it, and one that changes controller keeps it), and a permanent that changes zones is a new
  object that has none of it (400.7). Whoever granted it leaving the battlefield changes nothing
  (only "for as long as …" wordings say it does, 611.2b: app/rules/delayed.py).
* **Numbering** (``index_of``). An ability a player can activate is named by its index in the
  object's abilities (113.10a: the instructions are part of the granted ability). Printed ones are
  0…99, the ones static abilities grant 100…, and the ones resolved effects grant are numbered from
  the effect's own timestamp, so the number doesn't change when another grant ends (113.10c: each
  grant is its own ability, and the latest add or remove prevails: 613.7).
* **Last known information** (``last_existed`` / ``as_last_existed``). An ability that triggers as
  its object leaves the battlefield looks back in time at the abilities it had immediately before
  (603.10a): "When this creature dies, return it …" granted until end of turn still triggers when
  it is destroyed. The rules engine records them on the object's snapshot as it moves it
  (app/rules/plan.py), and the trigger collector rebuilds its characteristics from them
  (app/rules/triggers.py ``_lki_characteristics``).

Only abilities the engine reads from the object as it is now are granted: triggered and activated
abilities (incl. mana abilities), characteristic-defining P/T, "If ~ would die, exile it instead".
Static abilities that other objects' characteristics depend on (anthems, "can't be blocked" and
the like, which app/rules/layers.py reads from printed text) are refused here, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.rules.oracle import AbilityText

if TYPE_CHECKING:
    from app.game.rules_state import ContinuousEffect, ObjectSnapshot
    from app.rules.characteristics import Characteristics

# -- the numbering of abilities that resolved effects grant ----------------------------------------
# Above every other key an object's abilities are known by: printed (0…99), static-granted (100…),
# the keyword triggers' (1000 + 10 × index + k), exalted (2000…), achievements (4200…), delayed (7000).
INDEX_BASE = 10_000
INDEX_STRIDE = 16  # abilities one effect can grant
MAX_INDEX = 2_000_000  # app/game/actions.py ActivateAbility.ability's bound (a game with ~120 000 effects; borrowed abilities, abilities_of.py, above)
MAX_GRANTED = INDEX_STRIDE


def index_of(timestamp: int, k: int) -> int:
    """The index of the ``k``-th ability the effect with this timestamp grants."""
    return INDEX_BASE + INDEX_STRIDE * timestamp + min(k, INDEX_STRIDE - 1)


# -- quoted abilities in a sentence ------------------------------------------------------------------
_QUOTED = re.compile(r'"([^"]*)"')
OPEN, CLOSE = "⟦", "⟧"  # ⟦n⟧: where the n-th quoted ability was
PLACEHOLDER = re.compile(rf"{OPEN}(\d+){CLOSE}")


def protect(text: str) -> tuple[str, list[str]] | None:
    """The sentence with each quoted ability replaced by ⟦n⟧ and the quoted texts in order; None
    when the quotation marks don't pair up (nothing is guessed)."""
    if text.count('"') % 2:
        return None
    quotes: list[str] = []

    def hide(m: re.Match[str]) -> str:
        quotes.append(m.group(1))
        return f"{OPEN}{len(quotes) - 1}{CLOSE}"

    return _QUOTED.sub(hide, text), quotes


def normalize_loyalty_quote(text: str) -> str:
    # Oracle brackets a loyalty symbol inside an ability quotation. The native
    # loyalty path owns its timing, use limit and counter payment once restored.
    text = re.sub(r"^\[([+−-]?(?:\d+|X))\]:", r"\1:", text)
    # Only the final delimiting quote closes this nested emblem. A possessive
    # such as "player's turn" is part of its text, not another quotation.
    text = re.sub(r"\b(gets? an emblem with) '(.+)'(?=\.?$)", r'\1 "\2"', text)
    return text


@lru_cache(maxsize=4096)
def quote(text: str) -> str | None:
    """A quoted ability the engine carries out when an effect grants it, as the text the grant
    carries (its last sentence's full stop restored: Oracle leaves it off a quote that ends the
    clause, ``gains "{T}: Draw a card" for as long as …``), else None.

    Triggered and activated abilities (they run from the object's current abilities, 603.2 / 602.2),
    mana abilities, keyword abilities, a characteristic-defining P/T (613.4a) and the object's own
    "If ~ would die, exile it instead" (614.1a) are read from the object as it is now. Anything
    else static is left alone: the static abilities other objects' characteristics depend on are
    read from printed text by app/rules/layers.py, so a granted one would silently do nothing."""
    # ("~" is what the sentence's own "this creature" / "this land" became: here it names the object
    # that has the ability — scripts.self_text leaves the granter's name alone inside a quote)
    # (a comma just before the closing quotation mark belongs to the sentence around it: "…, each creature,")
    t = re.sub(r"(^|: |\. )~", r"\1This permanent", text.strip().rstrip(",;")).replace("~", "this permanent")
    t = re.sub(r"^((?:When|Whenever) )this token( dies\b)", r"\1this permanent\2", t)  # -- token copies (wave 31C) -- "When this token dies, draw a card." (Jaxis): the object that has it
    t = normalize_loyalty_quote(t)
    t = re.sub(r"\bwith '([^']+)'", r'with "\1"', t)  # -- saga grants (wave 51B) -- Urza's Saga: a token's quoted ability inside a quoted ability uses single quotes (113.10)
    if not t or "‹granter" in t:  # (wave 18F: a granter is bound only by a static grant, layers.py — a resolved effect's isn't)
        return None
    if not t.endswith((".", "!", "?")):
        t += "."
    from app.rules import scripts
    from app.rules.characteristics import Characteristics
    from app.rules.coverage import definition_supported

    ab = scripts.granted_ability(t)
    if ab is None or ab.kind == "spell":
        return None
    if ab.kind in ("mana", "keywords"):
        return t
    d = scripts.define(ab, Characteristics(name="\u0000", abilities=(ab,)))
    if d is None or not definition_supported(d):
        return None
    if d.get('kind') == 'static' and d.get('static') == 'replace' and d.get('event') == 'damage':
        from app.rules import prevention_unpreventable_outcomes44

        if prevention_unpreventable_outcomes44.supported_quote(t, d):
            return t
    if d["kind"] in ("triggered", "activated"):
        return t
    if d["kind"] == "replacement" and d.get("replacement") == "exile_instead":
        return t
    if d["kind"] == "static" and d.get("static") == "cda":
        return t
    if d["kind"] == "static" and d.get("static") == "assign_unblocked":
        return t  # -- combat (wave 110E) -- 510.1c: combat.py reads it through scripts.statics(ch), the current abilities
    if d.get("static") == "no_regen_damaged110k":
        return t  # -- (wave 110K) -- Bone Shaman: regeneration.shielded / regeneration_choices.options read it from the source's current abilities
    if d.get("static") == "creature_combat_cost" and d.get("who") == "self":
        return t  # Declaration costs read the holder's completed layer-6 abilities.
    # -- granted abilities (wave 111R1) -- 613.1f: a static read from its source's current abilities
    from app.rules import wave111r1_grants

    if wave111r1_grants.current_static(d):
        return t  # ("You may play lands from your graveyard", "You may play an additional land on each of your turns": Nog, Ambitious Cadet)
    if (d.get("static") == "grant" and d.get("who") == "self" and not d.get("conditions")
            and d.get("rules") == ["attack_despite_defender"]):
        # scripts.statics reads this self-only combat permission directly from
        # current abilities, including its removal by later layer-6 effects.
        return t
    return None


@lru_cache(maxsize=1024)
def rules_of(text: str) -> tuple[str, ...] | None:
    """The rules a quoted rules-only static puts on its object — "This creature can't be blocked.",
    "… can't block.", "… attacks each combat if able.", "… can't be blocked by more than one creature."
    (app/rules/statics.py vocabulary: cant_be_blocked, cant_block, must_attack, max_one_blocker …) —
    or None. The layers read statics that restrict combat from printed text, so a grant of one
    becomes a rule-modifying effect on the objects it's given to (``restrict``, their set fixed as it
    begins: 611.2c; 113.12: stating a quality isn't quite granting an ability, but it lasts as long
    and affects the same objects)."""
    t = re.sub(r"(^|: |\. )~", r"\1This permanent", text.strip().rstrip(",;")).replace("~", "this permanent")
    t = re.sub(r"^((?:When|Whenever) )this token( dies\b)", r"\1this permanent\2", t)  # -- token copies (wave 31C) -- "When this token dies, draw a card." (Jaxis): the object that has it
    if not t:
        return None
    # -- wave 110J -- 502.3: "This creature doesn't untap during your untap step if it has a fungus counter on it." (Mindbender Spores): the counter is read when it untaps
    if kept := re.fullmatch(r"[Tt]his \w+ doesn't untap during your untap step if it has an? ([\w+/-]+) counter on it\.?", t):
        return (f"doesnt_untap_counter:{kept[1]}",)
    from app.rules import scripts
    from app.rules.characteristics import Characteristics

    ab = scripts.granted_ability(t if t.endswith((".", "!", "?")) else t + ".")
    if ab is None or ab.kind != "static":
        return None
    d = scripts.define(ab, Characteristics(name="\u0000", abilities=(ab,)))
    if d is None or d.get("kind") != "static" or d.get("static") != "grant" or d.get("who") != "self" or d.get("conditions"):
        return None
    if d["p"] or d["t"] or d.get("base") or d["keywords"] or d["grants"] or d.get("each") or not d.get("rules"):
        return None
    return tuple(d["rules"])


def items(text: str) -> tuple[list[str], list[int]]:
    """What a grant list names — ("flying, ⟦0⟧, and ⟦1⟧" → (["flying"], [0, 1])): the keywords and
    the quoted abilities (their numbers), in order."""
    words = [w for w in re.split(r", and | and |, ", text) if w]
    quotes = [int(m.group(1)) for w in words if (m := PLACEHOLDER.fullmatch(w))]
    return [w for w in words if not PLACEHOLDER.fullmatch(w)], quotes


# -- layer 6 (613.1f) ---------------------------------------------------------------------------------
def with_final_stop(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else text + "."


def _enchant(line: str) -> AbilityText | None:
    """-- licids (wave 50A) -- 702.5: "enchant creature", given by a resolved effect that makes the object an Aura (app/rules/licids.py)."""
    from app.rules.attachments import enchant_selector_of

    return AbilityText(index=0, text=line, kind="keywords", keywords=("enchant",)) if enchant_selector_of(line) is not None else None


def layer6(ch: Characteristics, effects: list[ContinuousEffect], wipe: tuple[int, int, int] | None) -> Characteristics:
    """The abilities resolved effects granted (613.1f), numbered from each effect's timestamp, after
    the printed and static-granted ones. An effect a later "loses all abilities" follows is gone
    (``wipe``: its ordering key, 613.7); ones after it grant again."""
    from app.rules.scripts import granted_ability

    extra: list[AbilityText] = []
    for e in effects:  # (``layers.affecting`` sorts by timestamp)
        if e.layer != "6" or not e.add_abilities or (wipe is not None and (e.object_seq, 1, e.timestamp) < wipe):
            continue
        from app.rules import quoted_prevention_loss47

        for k, text in enumerate(e.add_abilities[:MAX_GRANTED]):
            if e.id.startswith('sticker101:'):
                from app.rules.oracle import parse_abilities

                # A sticker grants its printed abilities even when a resulting
                # ability needs the ordinary manual-resolution path. Never drop it.
                extra.extend(replace(a, index=index_of(e.timestamp, part))
                             for part, a in enumerate(parse_abilities(with_final_stop(text))))
                continue

            if quoted_prevention_loss47.lost(with_final_stop(text), ch.name, (e.object_seq, 1, e.timestamp), effects):
                continue
            ab = granted_ability(line := with_final_stop(text)) or _enchant(line)
            if ab is not None:
                extra.append(replace(ab, index=index_of(e.timestamp, k), activation_player=e.activation_player, spend_blue110i=e.spend_blue110i))
    return replace(ch, abilities=ch.abilities + tuple(extra)) if extra else ch


# -- last known information (603.10a, 608.2h) ----------------------------------------------------------
def last_existed(printed: Characteristics, now: Characteristics) -> tuple[Any, Any, Any]:
    """What an object that is about to leave looks like now, in the form an ``ObjectSnapshot`` keeps
    it: (abilities, keywords, traits) — each None while it is the printed one (the snapshot then
    stores nothing: most objects have no grants and no type changes). ``traits``: its types,
    subtypes, supertypes and colors, when layers 4 and 5 changed them (an animated land dies as a
    creature, 700.4; the last known information of a Vehicle that was crewed says so too)."""
    abilities = None
    if now.abilities != printed.abilities:
        abilities = [{"index": a.index, "text": a.text, "kind": a.kind, "keywords": list(a.keywords), "cost": a.cost,
                      "intrinsic": a.intrinsic,
                      # -- lent abilities -- a lent ability keeps its lending path as it last existed (607.5: its link scope, abilities_of.link_scope)
                      **({"borrowed_origin": list(a.borrowed_origin), "borrowed_scope": a.borrowed_scope} if a.borrowed_origin else {})}
                     for a in now.abilities]
    keywords = sorted(now.keywords) if now.keywords != printed.keywords else None
    traits = None
    if now.name != printed.name or (now.types, now.subtypes, now.supertypes, now.colors) != (printed.types, printed.subtypes, printed.supertypes, printed.colors):
        traits = {"types": sorted(now.types), "subtypes": sorted(now.subtypes), "supertypes": sorted(now.supertypes),
                  "colors": sorted(now.colors), "name101": [now.name]}
    return abilities, keywords, traits


def as_last_existed(ch: Characteristics, snap: ObjectSnapshot) -> Characteristics:
    """``ch`` (the object's printed characteristics) with the abilities, keywords and types it had when
    it last existed on the battlefield, if they were recorded and differed."""
    if snap.abilities is not None:
        ch = replace(ch, abilities=tuple(AbilityText(index=int(a["index"]), text=str(a["text"]), kind=a["kind"],
                                                     keywords=tuple(a.get("keywords") or ()), cost=a.get("cost"),
                                                     intrinsic=bool(a.get("intrinsic")), borrowed_origin=tuple(a.get("borrowed_origin") or ()),
                                                     borrowed_scope=a.get("borrowed_scope")) for a in snap.abilities))
    if snap.keywords is not None:
        printed = frozenset(k for a in ch.abilities if a.kind == "keywords" for k in a.keywords)
        now = frozenset(snap.keywords)
        ch = replace(ch, granted=now - printed, lost=printed - now)
    if snap.traits is not None:
        t = snap.traits
        ch = replace(ch, name=(t.get("name101") or [ch.name])[0], types=frozenset(t["types"]), subtypes=frozenset(t["subtypes"]),
                     supertypes=frozenset(t["supertypes"]), colors=frozenset(t["colors"]))
    return ch
