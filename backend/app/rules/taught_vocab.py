"""-- Teach Fyodor -- the pieces a player snaps together to teach the engine a new mechanic or one card's line (docs/TEACH_FYODOR.md).

Every piece is a template of Oracle wording the engine's own parser reads (``scripts.definitions``): a taught ability is written out as
an ordinary Oracle sentence ("When this creature enters, mill two cards. You may put a creature card …") and the parser turns it into
the engine's internal definition, exactly as it does for a printed card. So a taught ability is automated, replayed and kept private
like any other, and it is checked by the same validators (``coverage``). Nothing here is code: pieces, slots and options are data,
served to the Teach Fyodor page as JSON (``vocabulary()``), and ``tests/test_teach_matrix.py`` proves every piece reads FULL.

Template tokens (the same mini-language in ``frontend/src/teach/sentence.ts``):

* ``{self}``: "this creature" / "this artifact" … (the card's own type).
* ``{k}``: a slot's value — a number in digits, an option's words, a mana cost.
* ``{k:word}``: a number in words ("two"); ``{k:a}``: "a" for one, else words; ``{k:s}``: "s" unless the number is one.
* ``{k:signed}``: "+2" / "-1"; ``{k:mana}``: a number as generic mana ("{2}"); ``{k:vs}``: a verb's "s" when the chosen subject is singular ("gets" / "get").

A number slot that allows it may hold ``"N"``: the number written after a taught keyword ("Dive 2"). Unfilled, it reads "N".
"""

from __future__ import annotations

from typing import Any

# -- options: every choice a slot offers (id -> words). "plural": a subject that takes "get" rather than "gets". "cat": the palette
# group a chip of it shows in (targets are orange chips the player can drop into a matching slot).
OPTIONS: dict[str, dict[str, Any]] = {
    # spells you cast
    "spell_any": {"text": "a spell"}, "spell_creature": {"text": "a creature spell"}, "spell_noncreature": {"text": "a noncreature spell"},
    "spell_instant_sorcery": {"text": "an instant or sorcery spell"}, "spell_artifact": {"text": "an artifact spell"},
    "spell_enchantment": {"text": "an enchantment spell"},
    # things you count
    "count_lands": {"text": "lands"}, "count_creatures": {"text": "creatures"}, "count_artifacts": {"text": "artifacts"},
    "count_enchantments": {"text": "enchantments"},
    # targets and recipients
    "t_any": {"text": "any target", "cat": "target"},
    "t_creature": {"text": "target creature", "cat": "target"},
    "t_creature_opp": {"text": "target creature an opponent controls", "cat": "target"},
    "t_creature_yours": {"text": "target creature you control", "cat": "target"},
    "t_player_or_pw": {"text": "target player or planeswalker", "cat": "target"},
    "t_artifact": {"text": "target artifact", "cat": "target"},
    "t_enchantment": {"text": "target enchantment", "cat": "target"},
    "t_artifact_or_enchantment": {"text": "target artifact or enchantment", "cat": "target"},
    "t_nonland": {"text": "target nonland permanent", "cat": "target"},
    "t_planeswalker": {"text": "target planeswalker", "cat": "target"},
    "t_permanent": {"text": "target permanent", "cat": "target"},
    "t_land_yours": {"text": "target land you control", "cat": "target"},
    "t_artifact_opp": {"text": "target artifact an opponent controls", "cat": "target"},
    "t_permanent_opp": {"text": "target permanent an opponent controls", "cat": "target"},
    "t_gy_card": {"text": "target card from a graveyard", "cat": "target"},
    "t_self": {"text": "{self}", "cat": "target"},
    "t_each_opponent": {"text": "each opponent", "cat": "target"},
    "t_opponent": {"text": "target opponent", "cat": "target"},
    "t_player": {"text": "target player", "cat": "target"},
    "t_each_opp_creature": {"text": "each creature your opponents control", "cat": "target", "plural": True},
    "t_each_yours": {"text": "each creature you control", "cat": "target"},
    "t_creatures_yours": {"text": "creatures you control", "cat": "target", "plural": True},
    "t_other_creatures_yours": {"text": "other creatures you control", "cat": "target", "plural": True},
    # keywords
    **{f"kw_{k.replace(' ', '_')}": {"text": k} for k in ("flying", "first strike", "double strike", "deathtouch", "haste", "hexproof",
                                                           "indestructible", "lifelink", "menace", "reach", "trample", "vigilance")},
    # artifact tokens
    **{f"tok_{k.lower()}": {"text": k} for k in ("Treasure", "Food", "Clue", "Blood", "Map")},
    # colors
    **{f"color_{c}": {"text": c} for c in ("white", "blue", "black", "red", "green")},
    # creature types for tokens
    **{f"type_{t.lower()}": {"text": t} for t in ("Spirit", "Zombie", "Goblin", "Soldier", "Saproling", "Beast", "Human", "Elf",
                                                   "Merfolk", "Insect", "Bird", "Cat", "Dragon", "Angel", "Knight", "Wolf", "Elemental",
                                                   "Faerie", "Squirrel", "Rat", "Fish", "Octopus", "Shark", "Crab")},
    # a token's keyword
    "tokkw_none": {"text": ""}, **{f"tokkw_{k}": {"text": f" with {k}"} for k in ("flying", "haste", "trample", "vigilance", "lifelink",
                                                                                  "deathtouch", "menace", "reach")},
    # kinds of card
    "card_creature": {"text": "a creature card"}, "card_land": {"text": "a land card"}, "card_artifact": {"text": "an artifact card"},
    "card_enchantment": {"text": "an enchantment card"}, "card_instant": {"text": "an instant card"},
    "card_sorcery": {"text": "a sorcery card"}, "card_any": {"text": "a card"},
    "basic_land": {"text": "a basic land card"},
    # graveyard targets
    "gy_creature": {"text": "creature"}, "gy_artifact": {"text": "artifact"}, "gy_enchantment": {"text": "enchantment"},
    "gy_land": {"text": "land"}, "gy_instant_sorcery": {"text": "instant or sorcery"}, "gy_permanent": {"text": "permanent"},
    "to_hand": {"text": "your hand"}, "to_battlefield": {"text": "the battlefield"},
    # sacrifices
    "sac_another_creature": {"text": "another creature"}, "sac_creature": {"text": "a creature"}, "sac_artifact": {"text": "an artifact"},
    "sac_land": {"text": "a land"}, "sac_enchantment": {"text": "an enchantment"}, "sac_nonland": {"text": "a nonland permanent"},
    # spells to counter
    "cs_any": {"text": "target spell", "cat": "target"}, "cs_noncreature": {"text": "target noncreature spell", "cat": "target"},
    "cs_creature": {"text": "target creature spell", "cat": "target"},
    "cs_instant_sorcery": {"text": "target instant or sorcery spell", "cat": "target"},
    # spells a static makes cheaper
    "disc_creature": {"text": "Creature spells"}, "disc_noncreature": {"text": "Noncreature spells"},
    "disc_instant_sorcery": {"text": "Instant and sorcery spells"}, "disc_artifact": {"text": "Artifact spells"},
    "disc_enchantment": {"text": "Enchantment spells"},
    # "for each … you control"
    "each_artifact": {"text": "artifact"}, "each_creature": {"text": "creature"}, "each_land": {"text": "land"},
    "each_enchantment": {"text": "enchantment"}, "each_other_creature": {"text": "other creature"},
}

_KW = [k for k in OPTIONS if k.startswith("kw_")]


def _opts(*ids: str) -> list[str]:
    return list(ids)


NUM = {"kind": "number", "min": 1, "max": 20, "param": True, "default": 1}
SIGNED = {"kind": "signed", "min": -10, "max": 10, "param": True, "default": 1}


def _num(default: int = 1, lo: int = 1, hi: int = 20, param: bool = True) -> dict[str, Any]:
    return {"kind": "number", "min": lo, "max": hi, "param": param, "default": default}


def _choice(options: list[str], default: str | None = None) -> dict[str, Any]:
    return {"kind": "choice", "options": options, "default": default or options[0]}


MANA = {"kind": "mana", "default": "{2}"}

# Categories, in palette order, with their colours on the Teach Fyodor page.
CATEGORIES: list[dict[str, str]] = [
    {"id": "when", "label": "When", "hint": "What starts the ability"},
    {"id": "if", "label": "If", "hint": "Only when this is true"},
    {"id": "cost", "label": "Cost", "hint": "What you pay"},
    {"id": "do", "label": "Do", "hint": "What happens"},
    {"id": "always", "label": "Always", "hint": "Something that is always true"},
    {"id": "then", "label": "Then", "hint": "Choices and order"},
    {"id": "target", "label": "Target", "hint": "Who or what it affects — drop one on an orange slot"},
    {"id": "value", "label": "Values", "hint": "Numbers — drop one on a white slot"},
]

# Roles: "trigger" | "activated" | "static_hat" start an ability (hat blocks); "condition" (If); "cost" (an activated ability's cost);
# "limit" ("Activate only …"); "optional_cost" (a "you may pay …. If you do," container); "effect" (Do); "static" (Always);
# "may" / "ifdo" (containers) and "then" (joins two effects into one sentence). A static's "bare" wording is used without an If piece
# ("Flying" rather than "This creature has flying."); "needs_condition": only under an If piece.
PIECES: list[dict[str, Any]] = [
    # ---- When (hats) ----
    {"id": "etb", "cat": "when", "role": "trigger", "label": "Enters", "text": "When {self} enters"},
    {"id": "dies", "cat": "when", "role": "trigger", "label": "Dies", "text": "When {self} dies"},
    {"id": "leaves", "cat": "when", "role": "trigger", "label": "Leaves the battlefield", "text": "When {self} leaves the battlefield"},
    {"id": "attacks", "cat": "when", "role": "trigger", "label": "Attacks", "text": "Whenever {self} attacks"},
    {"id": "blocks", "cat": "when", "role": "trigger", "label": "Blocks", "text": "Whenever {self} blocks"},
    {"id": "combat_damage", "cat": "when", "role": "trigger", "label": "Deals combat damage to a player",
     "text": "Whenever {self} deals combat damage to a player"},
    {"id": "targeted", "cat": "when", "role": "trigger", "label": "Becomes a target",
     "text": "Whenever {self} becomes the target of a spell or ability an opponent controls"},
    {"id": "landfall", "cat": "when", "role": "trigger", "label": "A land of yours enters", "text": "Whenever a land you control enters"},
    {"id": "ally_enters", "cat": "when", "role": "trigger", "label": "Another creature of yours enters",
     "text": "Whenever another creature you control enters"},
    {"id": "ally_dies", "cat": "when", "role": "trigger", "label": "Another creature of yours dies",
     "text": "Whenever another creature you control dies"},
    {"id": "cast", "cat": "when", "role": "trigger", "label": "You cast a spell", "text": "Whenever you cast {spell}",
     "slots": {"spell": _choice(_opts("spell_any", "spell_creature", "spell_noncreature", "spell_instant_sorcery", "spell_artifact",
                                     "spell_enchantment"))}},
    {"id": "opp_cast", "cat": "when", "role": "trigger", "label": "An opponent casts a spell", "text": "Whenever an opponent casts a spell"},
    {"id": "gain_life", "cat": "when", "role": "trigger", "label": "You gain life", "text": "Whenever you gain life"},
    {"id": "upkeep", "cat": "when", "role": "trigger", "label": "Your upkeep", "text": "At the beginning of your upkeep"},
    {"id": "combat", "cat": "when", "role": "trigger", "label": "Your combat starts", "text": "At the beginning of combat on your turn"},
    {"id": "end_step", "cat": "when", "role": "trigger", "label": "Your end step", "text": "At the beginning of your end step"},
    {"id": "activated", "cat": "when", "role": "activated", "label": "Pay to use it", "text": "Pay a cost: do something"},
    {"id": "static", "cat": "when", "role": "static_hat", "label": "Always", "text": "Always true"},
    # ---- If (conditions) ----
    {"id": "if_control", "cat": "if", "role": "condition", "label": "You control N or more …", "text": "you control {n:word} or more {what}",
     "slots": {"n": _num(3), "what": _choice(_opts("count_lands", "count_creatures", "count_artifacts", "count_enchantments"))}},
    {"id": "if_your_turn", "cat": "if", "role": "condition", "label": "It's your turn", "text": "it's your turn"},
    {"id": "if_life", "cat": "if", "role": "condition", "label": "You have N or more life", "text": "you have {n} or more life",
     "slots": {"n": _num(30, 1, 99)}},
    {"id": "if_graveyard", "cat": "if", "role": "condition", "label": "N or more cards in your graveyard",
     "text": "there are {n:word} or more cards in your graveyard", "slots": {"n": _num(7)}},
    {"id": "if_opp_lands", "cat": "if", "role": "condition", "label": "An opponent has more lands",
     "text": "an opponent controls more lands than you", "trigger_only": True},
    # ---- Cost ----
    {"id": "cost_mana", "cat": "cost", "role": "cost", "label": "Mana", "text": "{mana}", "slots": {"mana": MANA}},
    {"id": "cost_tap", "cat": "cost", "role": "cost", "label": "Tap it {T}", "text": "{T}"},
    {"id": "cost_sac_self", "cat": "cost", "role": "cost", "label": "Sacrifice it", "text": "Sacrifice {self}"},
    {"id": "cost_sac", "cat": "cost", "role": "cost", "label": "Sacrifice something", "text": "Sacrifice {what}",
     "slots": {"what": _choice(_opts("sac_another_creature", "sac_creature", "sac_artifact", "sac_land"))}},
    {"id": "cost_discard", "cat": "cost", "role": "cost", "label": "Discard cards", "text": "Discard {n:a} card{n:s}",
     "slots": {"n": _num(1, 1, 3)}},
    {"id": "cost_life", "cat": "cost", "role": "cost", "label": "Pay life", "text": "Pay {n} life", "slots": {"n": _num(2)}},
    {"id": "cost_counters", "cat": "cost", "role": "cost", "label": "Remove +1/+1 counters",
     "text": "Remove {n:a} +1/+1 counter{n:s} from {self}", "slots": {"n": _num(1, 1, 10)}},
    {"id": "cost_exile_gy", "cat": "cost", "role": "cost", "label": "Exile a card from your graveyard",
     "text": "Exile a card from your graveyard"},
    {"id": "cost_tap_creature", "cat": "cost", "role": "cost", "label": "Tap another creature",
     "text": "Tap an untapped creature you control"},
    {"id": "limit_sorcery", "cat": "cost", "role": "limit", "label": "Only as a sorcery", "text": "Activate only as a sorcery."},
    {"id": "limit_once", "cat": "cost", "role": "limit", "label": "Only once each turn", "text": "Activate only once each turn."},
    {"id": "pay_mana", "cat": "cost", "role": "optional_cost", "label": "You may pay mana. If you do:", "text": "you may pay {mana}",
     "slots": {"mana": MANA}},
    {"id": "pay_life", "cat": "cost", "role": "optional_cost", "label": "You may pay life. If you do:", "text": "you may pay {n} life",
     "slots": {"n": _num(2)}},
    {"id": "pay_sac", "cat": "cost", "role": "optional_cost", "label": "You may sacrifice. If you do:", "text": "you may sacrifice {what}",
     "slots": {"what": _choice(_opts("sac_another_creature", "sac_artifact", "sac_land"))}},
    {"id": "pay_discard", "cat": "cost", "role": "optional_cost", "label": "You may discard. If you do:", "text": "you may discard a card"},
    # ---- Then (flow) ----
    {"id": "may", "cat": "then", "role": "may", "label": "You may …", "text": "you may"},
    {"id": "ifdo", "cat": "then", "role": "ifdo", "label": "If you do …", "text": "if you do"},
    {"id": "then", "cat": "then", "role": "then", "label": "Then", "text": "then"},
    # ---- Do (effects) ----
    {"id": "draw", "cat": "do", "role": "effect", "may": True, "label": "Draw cards", "text": "draw {n:a} card{n:s}", "slots": {"n": _num(1)}},
    {"id": "discard", "cat": "do", "role": "effect", "may": True, "label": "Discard cards", "text": "discard {n:a} card{n:s}",
     "slots": {"n": _num(1, 1, 5)}},
    {"id": "opp_discard", "cat": "do", "role": "effect", "label": "A player discards", "text": "{who} discards {n:a} card{n:s}",
     "slots": {"who": _choice(_opts("t_each_opponent", "t_opponent", "t_player")), "n": _num(1, 1, 5)}},
    {"id": "damage", "cat": "do", "role": "effect", "label": "Deal damage", "text": "{self} deals {n} damage to {to}",
     "slots": {"n": _num(2), "to": _choice(_opts("t_any", "t_creature", "t_creature_opp", "t_player_or_pw", "t_each_opponent",
                                                  "t_each_opp_creature"))}},
    {"id": "gain", "cat": "do", "role": "effect", "may": True, "label": "Gain life", "text": "you gain {n} life", "slots": {"n": _num(3)}},
    {"id": "lose", "cat": "do", "role": "effect", "label": "A player loses life", "text": "{who} loses {n} life",
     "slots": {"who": _choice(_opts("t_each_opponent", "t_opponent", "t_player")), "n": _num(2)}},
    {"id": "drain", "cat": "do", "role": "effect", "label": "Drain each opponent", "text": "each opponent loses {n} life and you gain {n} life",
     "slots": {"n": _num(1)}},
    {"id": "token", "cat": "do", "role": "effect", "may": True, "label": "Create Treasure/Food/Clue …", "text": "create {n:a} {kind} token{n:s}",
     "slots": {"n": _num(1, 1, 10), "kind": _choice(_opts("tok_treasure", "tok_food", "tok_clue", "tok_blood", "tok_map"))}},
    {"id": "creature_token", "cat": "do", "role": "effect", "may": True, "label": "Create creature tokens",
     "text": "create {n:a} {p}/{t} {color} {type} creature token{n:s}{kw}",
     "slots": {"n": _num(1, 1, 10), "p": _num(1, 0, 20), "t": _num(1, 1, 20), "color": _choice([k for k in OPTIONS if k.startswith("color_")]),
               "type": _choice([k for k in OPTIONS if k.startswith("type_")]), "kw": _choice([k for k in OPTIONS if k.startswith("tokkw_")])}},
    {"id": "counters", "cat": "do", "role": "effect", "may": True, "label": "Put +1/+1 counters", "text": "put {n:a} +1/+1 counter{n:s} on {on}",
     "slots": {"n": _num(1, 1, 10), "on": _choice(_opts("t_self", "t_creature", "t_creature_yours", "t_each_yours"))}},
    {"id": "destroy", "cat": "do", "role": "effect", "may": True, "label": "Destroy", "text": "destroy {what}",
     "slots": {"what": _choice(_opts("t_creature", "t_creature_opp", "t_artifact", "t_enchantment", "t_artifact_or_enchantment",
                                     "t_nonland", "t_planeswalker"))}},
    {"id": "exile", "cat": "do", "role": "effect", "may": True, "label": "Exile", "text": "exile {what}",
     "slots": {"what": _choice(_opts("t_creature", "t_creature_opp", "t_artifact", "t_enchantment", "t_nonland", "t_gy_card"))}},
    {"id": "bounce", "cat": "do", "role": "effect", "may": True, "label": "Return to hand", "text": "return {what} to its owner's hand",
     "slots": {"what": _choice(_opts("t_creature", "t_creature_opp", "t_nonland", "t_artifact", "t_permanent"))}},
    {"id": "tap", "cat": "do", "role": "effect", "may": True, "label": "Tap", "text": "tap {what}",
     "slots": {"what": _choice(_opts("t_creature", "t_creature_opp", "t_permanent"))}},
    {"id": "untap", "cat": "do", "role": "effect", "may": True, "label": "Untap", "text": "untap {what}",
     "slots": {"what": _choice(_opts("t_self", "t_creature", "t_land_yours", "t_permanent"))}},
    {"id": "mill", "cat": "do", "role": "effect", "label": "Mill cards", "text": "mill {n:a} card{n:s}", "slots": {"n": _num(2)}},
    {"id": "player_mills", "cat": "do", "role": "effect", "label": "A player mills", "text": "target player mills {n:word} card{n:s}",
     "slots": {"n": _num(3)}},
    {"id": "from_milled", "cat": "do", "role": "effect", "may": True, "after": "mill", "label": "Keep one of the milled cards",
     "text": "put {card} with mana value {n} or less from among the cards milled this way into your hand",
     "slots": {"card": _choice(_opts("card_creature", "card_artifact", "card_enchantment", "card_instant", "card_sorcery", "card_land")),
               "n": _num(2, 0, 20)}},
    {"id": "scry", "cat": "do", "role": "effect", "label": "Scry", "text": "scry {n}", "slots": {"n": _num(1)}},
    {"id": "surveil", "cat": "do", "role": "effect", "label": "Surveil", "text": "surveil {n}", "slots": {"n": _num(1)}},
    {"id": "search_land", "cat": "do", "role": "effect", "may": True, "label": "Search for a basic land",
     "text": "search your library for a basic land card, put it onto the battlefield tapped, then shuffle"},
    {"id": "search", "cat": "do", "role": "effect", "may": True, "label": "Search your library",
     "text": "search your library for {card}, reveal it, put it into your hand, then shuffle",
     "slots": {"card": _choice(_opts("card_creature", "card_land", "card_artifact", "card_enchantment", "card_instant", "card_sorcery"))}},
    {"id": "reanimate", "cat": "do", "role": "effect", "may": True, "label": "Return from your graveyard",
     "text": "return target {card} card from your graveyard to {to}",
     "slots": {"card": _choice(_opts("gy_creature", "gy_artifact", "gy_enchantment", "gy_land", "gy_instant_sorcery", "gy_permanent")),
               "to": _choice(_opts("to_hand", "to_battlefield"))}},
    {"id": "opp_sacrifice", "cat": "do", "role": "effect", "label": "Each opponent sacrifices", "text": "each opponent sacrifices {what} of their choice",
     "slots": {"what": _choice(_opts("sac_creature", "sac_artifact", "sac_enchantment", "sac_nonland"))}},
    {"id": "copy_spell", "cat": "do", "role": "effect", "may": True, "label": "Copy a spell",
     "text": "copy target instant or sorcery spell you control. You may choose new targets for the copy"},
    {"id": "counter_spell", "cat": "do", "role": "effect", "may": True, "label": "Counter a spell", "text": "counter {what}",
     "slots": {"what": _choice(_opts("cs_any", "cs_noncreature", "cs_creature", "cs_instant_sorcery"))}},
    {"id": "steal", "cat": "do", "role": "effect", "may": True, "label": "Gain control", "text": "gain control of {what}",
     "slots": {"what": _choice(_opts("t_artifact_opp", "t_creature_opp", "t_permanent_opp"))}},
    {"id": "threaten", "cat": "do", "role": "effect", "label": "Borrow a creature this turn",
     "text": "gain control of target creature an opponent controls until end of turn. Untap that creature. It gains haste until end of turn"},
    {"id": "pump", "cat": "do", "role": "effect", "label": "+X/+X until end of turn", "text": "{who} get{who:vs} {p:signed}/{t:signed} until end of turn",
     "slots": {"who": _choice(_opts("t_self", "t_creature", "t_creature_yours", "t_creatures_yours")), "p": SIGNED, "t": SIGNED}},
    {"id": "grant", "cat": "do", "role": "effect", "label": "Gains a keyword this turn", "text": "{who} gain{who:vs} {kw} until end of turn",
     "slots": {"who": _choice(_opts("t_self", "t_creature", "t_creature_yours", "t_creatures_yours")), "kw": _choice(_KW)}},
    {"id": "add_mana", "cat": "do", "role": "effect", "label": "Add mana", "text": "add {mana}", "slots": {"mana": {"kind": "mana", "default": "{G}",
                                                                                                                 "colored": True}}},
    {"id": "add_any", "cat": "do", "role": "effect", "label": "Add one mana of any color", "text": "add one mana of any color"},
    {"id": "investigate", "cat": "do", "role": "effect", "label": "Investigate", "text": "investigate"},
    {"id": "proliferate", "cat": "do", "role": "effect", "label": "Proliferate", "text": "proliferate"},
    # ---- Always (statics) ----
    {"id": "has_kw", "cat": "always", "role": "static", "label": "It has a keyword", "text": "{self} has {kw}", "bare": "{kw}",
     "slots": {"kw": _choice(_KW)}},
    {"id": "self_pt", "cat": "always", "role": "static", "label": "It gets +X/+X", "text": "{self} gets {p:signed}/{t:signed}",
     "slots": {"p": SIGNED, "t": SIGNED}, "needs_condition": True},
    {"id": "per_each", "cat": "always", "role": "static", "label": "It grows for each …", "text": "{self} gets +1/+1 for each {what} you control",
     "slots": {"what": _choice(_opts("each_artifact", "each_creature", "each_land", "each_enchantment", "each_other_creature"))}},
    {"id": "anthem", "cat": "always", "role": "static", "label": "Your creatures get +X/+X", "text": "{who} get {p:signed}/{t:signed}",
     "slots": {"who": _choice(_opts("t_creatures_yours", "t_other_creatures_yours")), "p": SIGNED, "t": SIGNED}},
    {"id": "team_kw", "cat": "always", "role": "static", "label": "Your creatures have a keyword", "text": "{who} have {kw}",
     "slots": {"who": _choice(_opts("t_creatures_yours", "t_other_creatures_yours")), "kw": _choice(_KW)}},
    {"id": "unblockable", "cat": "always", "role": "static", "label": "Can't be blocked", "text": "{self} can't be blocked"},
    {"id": "cant_block", "cat": "always", "role": "static", "label": "Can't block", "text": "{self} can't block"},
    {"id": "untargetable", "cat": "always", "role": "static", "label": "Opponents can't target it",
     "text": "{self} can't be the target of spells or abilities your opponents control"},
    {"id": "discount", "cat": "always", "role": "static", "label": "Spells cost less", "text": "{spells} you cast cost {n:mana} less to cast",
     "slots": {"spells": _choice(_opts("disc_creature", "disc_noncreature", "disc_instant_sorcery", "disc_artifact", "disc_enchantment")),
               "n": _num(1, 1, 5)}},
    {"id": "enters_counters", "cat": "always", "role": "static", "label": "Enters with +1/+1 counters",
     "text": "{self} enters with {n:a} +1/+1 counter{n:s} on it", "slots": {"n": _num(1, 1, 10)}, "no_condition": True},
    {"id": "enters_tapped", "cat": "always", "role": "static", "label": "Enters tapped", "text": "{self} enters tapped", "no_condition": True},
    {"id": "no_max_hand", "cat": "always", "role": "static", "label": "No maximum hand size", "text": "You have no maximum hand size",
     "no_condition": True},
]

PIECE: dict[str, dict[str, Any]] = {p["id"]: p for p in PIECES}

# Numbers the Values palette offers as chips (any number can also be typed into a slot).
VALUE_CHIPS: list[int | str] = [1, 2, 3, 4, 5, "N"]


def vocabulary() -> dict[str, Any]:
    """Everything the Teach Fyodor page needs to draw the palette and read a script back (pure data)."""
    return {"version": 1, "categories": CATEGORIES, "pieces": PIECES, "options": OPTIONS, "values": VALUE_CHIPS}
