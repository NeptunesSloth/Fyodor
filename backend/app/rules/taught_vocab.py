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
    **{f"color_{c}": {"text": c} for c in ("white", "blue", "black", "red", "green")}, "color_white_black": {"text": "white and black"},
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
    # how long an effect lasts (611.2a); "this turn" is the restriction grammar's "until end of turn"
    "dur_eot": {"text": "until end of turn"}, "dur_next_turn": {"text": "until your next turn"},
    "rdur_turn": {"text": "this turn"}, "rdur_next_turn": {"text": "until your next turn"},
    "rdur_combat_attacking": {"text": "until it deals combat damage while attacking"}, "rdur_combat": {"text": "until it deals combat damage"},
    # -- expressiveness sweep (docs/TEACH_FYODOR_COVERAGE.md): every wording below reads FULL (tests/test_teach_matrix.py) --
    # what happened this turn (raid, morbid, revolt …) and what is true right now (lieutenant, ferocious, hellbent, delirium …)
    "tt_attacked": {"text": "you attacked"}, "tt_died": {"text": "a creature died"}, "tt_gained": {"text": "you gained life"},
    "tt_opp_lost": {"text": "an opponent lost life"}, "tt_left": {"text": "a permanent you controlled left the battlefield"},
    "tt_two_spells": {"text": "you cast two or more spells"},
    "st_commander": {"text": "you control your commander"}, "st_power4": {"text": "you control a creature with power 4 or greater"},
    "st_no_hand": {"text": "you have no cards in hand"}, "st_not_your_turn": {"text": "it's not your turn"},
    "st_delirium": {"text": "there are four or more card types among cards in your graveyard"},
    "st_artifact": {"text": "you control an artifact"}, "st_opp_more_creatures": {"text": "an opponent controls more creatures than you"},
    # the counters a creature that just died had (undying, persist)
    "cnt_p1": {"text": "+1/+1"}, "cnt_m1": {"text": "-1/-1"},
    # "sacrifice it unless you …" (echo-like upkeep costs)
    "unl_discard": {"text": "discard a card"}, "unl_sac_land": {"text": "sacrifice a land"},
    "unl_sac_creature": {"text": "sacrifice another creature"}, "unl_return_land": {"text": "return a land you control to its owner's hand"},
    # where a creature that just died comes back to (undying, persist)
    "rd_bf": {"text": "the battlefield under its owner's control"},
    "rd_bf_p1": {"text": "the battlefield under its owner's control with a +1/+1 counter on it"},
    "rd_bf_m1": {"text": "the battlefield under its owner's control with a -1/-1 counter on it"},
    "rd_bf_tapped": {"text": "the battlefield tapped under its owner's control"}, "rd_hand": {"text": "its owner's hand"},
    # one creature's combat rules (defender, "attacks each combat if able", shadow-like blocking)
    "cr_cant_attack": {"text": "can't attack"}, "cr_cant_attack_block": {"text": "can't attack or block"},
    "cr_attacks": {"text": "attacks each combat if able"}, "cr_blocks": {"text": "blocks each combat if able"},
    "cr_extra_block": {"text": "can block an additional creature each combat"}, "cr_any_block": {"text": "can block any number of creatures"},
    "cr_only_fliers": {"text": "can block only creatures with flying"}, "cr_no_fliers": {"text": "can't block creatures with flying"},
    "cr_not_alone": {"text": "can't attack or block alone"},
    # evasion (flying, menace, fear, skulk-like, landwalk)
    "ev_flying_reach": {"text": "creatures with flying or reach"}, "ev_flying": {"text": "creatures with flying"},
    "ev_two": {"text": "two or more creatures"}, "ev_fear": {"text": "artifact creatures and/or black creatures"},
    "eb_more_one": {"text": "more than one creature"}, "eb_greater": {"text": "creatures with greater power"},
    "eb_power2": {"text": "creatures with power 2 or less"},
    "land_plains": {"text": "a Plains"}, "land_island": {"text": "an Island"}, "land_swamp": {"text": "a Swamp"},
    "land_mountain": {"text": "a Mountain"}, "land_forest": {"text": "a Forest"},
    # instead of dying
    "wd_exile": {"text": "die, exile it"}, "wd_top": {"text": "die, put it on top of its owner's library"},
    "wd_gy_exile": {"text": "be put into a graveyard from anywhere, exile it"},
    "pd_combat": {"text": "combat damage"}, "pd_all": {"text": "damage"},
    # why this spell costs less (affinity, undaunted-like)
    "why_each_artifact": {"text": "for each artifact you control"}, "why_each_creature": {"text": "for each creature you control"},
    "why_each_land": {"text": "for each land you control"}, "why_each_opponent": {"text": "for each opponent you have"},
    "why_artifact": {"text": "if you control an artifact"}, "why_turn": {"text": "if it's your turn"},
    "why_gy7": {"text": "if there are seven or more cards in your graveyard"},
    "why_three_creatures": {"text": "if you control three or more creatures"},
    "why_opp_lands": {"text": "if an opponent controls more lands than you"},
    # when an alternative cost may be paid (spectacle-, surge-like)
    "ac_always": {"text": ""}, "ac_opp_lost": {"text": "If an opponent lost life this turn, "},
    "ac_another": {"text": "If you've cast another spell this turn, "}, "ac_turn": {"text": "If it's your turn, "},
    "ac_artifact": {"text": "If you control an artifact, "},
    # a mandatory additional cost
    "xc_sac_creature": {"text": "sacrifice a creature"}, "xc_sac_artifact": {"text": "sacrifice an artifact"},
    "xc_discard": {"text": "discard a card"}, "xc_exile_gy": {"text": "exile a card from your graveyard"},
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

# Roles: "trigger" | "activated" | "static_hat" | "action_hat" start an ability (hat blocks; "action_hat" only heads a taught action); "condition" (If); "cost" (an activated ability's cost);
# "limit" ("Activate only …"); "optional_cost" (a "you may pay …. If you do," container); "effect" (Do); "static" (Always);
# "may" / "ifdo" (containers) and "then" (joins two effects into one sentence). "hats": the only When pieces a piece may go under
# ("Counter it unless they pay" reads only under "Becomes a target", "Return it (it just died)" only under "Dies"). A static's "bare" wording is used without an If piece
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
    {"id": "becomes_blocked", "cat": "when", "role": "trigger", "label": "Becomes blocked", "text": "Whenever {self} becomes blocked"},
    {"id": "blocks_or_blocked", "cat": "when", "role": "trigger", "label": "Blocks or becomes blocked",
     "text": "Whenever {self} blocks or becomes blocked"},
    {"id": "dealt_damage", "cat": "when", "role": "trigger", "label": "Is dealt damage", "text": "Whenever {self} is dealt damage"},
    {"id": "attacks_alone", "cat": "when", "role": "trigger", "label": "A creature of yours attacks alone",
     "text": "Whenever a creature you control attacks alone"},
    {"id": "you_attack", "cat": "when", "role": "trigger", "label": "You attack", "text": "Whenever you attack"},
    {"id": "creature_dies", "cat": "when", "role": "trigger", "label": "Any creature dies", "text": "Whenever a creature dies"},
    {"id": "upkeep", "cat": "when", "role": "trigger", "label": "Your upkeep", "text": "At the beginning of your upkeep"},
    {"id": "combat", "cat": "when", "role": "trigger", "label": "Your combat starts", "text": "At the beginning of combat on your turn"},
    {"id": "end_step", "cat": "when", "role": "trigger", "label": "Your end step", "text": "At the beginning of your end step"},
    {"id": "activated", "cat": "when", "role": "activated", "label": "Pay to use it", "text": "Pay a cost: do something"},
    {"id": "static", "cat": "when", "role": "static_hat", "label": "Always", "text": "Always true"},
    # (an action: the only hat of a taught action; the page sets it, the palette doesn't offer it)
    {"id": "action", "cat": "when", "role": "action_hat", "label": "The action", "text": "When a card says it", "hidden": True},
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
    # (dive, wave DV: the real card's intervening if, 702.82b; and how the spell was cast, 601.2h)
    {"id": "if_devoured", "cat": "if", "role": "condition", "label": "It devoured a creature", "text": "it devoured a creature", "trigger_only": True},
    {"id": "if_devoured_n", "cat": "if", "role": "condition", "label": "It devoured N or more creatures",
     "text": "it devoured {n:word} or more creatures", "slots": {"n": _num(2, 2, 10)}, "trigger_only": True},
    {"id": "if_kicked", "cat": "if", "role": "condition", "label": "It was kicked", "text": "it was kicked", "trigger_only": True},
    {"id": "if_cast", "cat": "if", "role": "condition", "label": "You cast it", "text": "you cast it", "trigger_only": True},
    {"id": "if_this_turn", "cat": "if", "role": "condition", "label": "It happened this turn", "text": "{what} this turn",
     "slots": {"what": _choice(_opts("tt_attacked", "tt_died", "tt_gained", "tt_opp_lost", "tt_left", "tt_two_spells"))}},
    {"id": "if_state", "cat": "if", "role": "condition", "label": "It's true right now", "text": "{what}",
     "slots": {"what": _choice(_opts("st_commander", "st_power4", "st_no_hand", "st_not_your_turn", "st_delirium", "st_artifact",
                                     "st_opp_more_creatures"))}},
    {"id": "if_no_counters", "cat": "if", "role": "condition", "label": "It had no counters", "text": "it had no {kind} counters on it",
     "slots": {"kind": _choice(_opts("cnt_p1", "cnt_m1"))}, "trigger_only": True},
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
    {"id": "cost_discard_self", "cat": "cost", "role": "cost", "label": "Discard this card (from your hand)", "text": "Discard this card"},
    {"id": "cost_exile_self_gy", "cat": "cost", "role": "cost", "label": "Exile this card from your graveyard",
     "text": "Exile this card from your graveyard"},
    {"id": "limit_once", "cat": "cost", "role": "limit", "label": "Only once each turn", "text": "Activate only once each turn."},
    {"id": "limit_attacked", "cat": "cost", "role": "limit", "label": "Only if it attacked, once each turn",
     "text": "Activate only if {self} attacked this turn and only once each turn."},
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
     "slots": {"what": _choice(_opts("t_creature", "t_creature_opp", "t_artifact", "t_enchantment", "t_nonland", "t_gy_card", "t_self"))}},
    {"id": "bounce", "cat": "do", "role": "effect", "may": True, "label": "Return to hand", "text": "return {what} to its owner's hand",
     "slots": {"what": _choice(_opts("t_creature", "t_creature_opp", "t_nonland", "t_artifact", "t_permanent", "t_self"))}},
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
    {"id": "pump", "cat": "do", "role": "effect", "label": "+X/+X until …", "text": "{who} get{who:vs} {p:signed}/{t:signed} {dur}",
     "slots": {"who": _choice(_opts("t_self", "t_creature", "t_creature_yours", "t_creatures_yours")), "p": SIGNED, "t": SIGNED,
               "dur": _choice(_opts("dur_eot", "dur_next_turn"))}},
    {"id": "grant", "cat": "do", "role": "effect", "label": "Gains a keyword until …", "text": "{who} gain{who:vs} {kw} {dur}",
     "slots": {"who": _choice(_opts("t_self", "t_creature", "t_creature_yours", "t_creatures_yours")), "kw": _choice(_KW),
               "dur": _choice(_opts("dur_eot", "dur_next_turn"))}},
    # (dive, wave DV: evasion with a duration — "until it deals combat damage while attacking" is what the keyword action dive means)
    {"id": "unblockable_for", "cat": "do", "role": "effect", "label": "Can't be blocked until …", "text": "{who} can't be blocked {dur}",
     "slots": {"who": _choice(_opts("t_self", "t_creature", "t_creature_yours")),
               "dur": _choice(_opts("rdur_turn", "rdur_next_turn", "rdur_combat_attacking", "rdur_combat"))}},
    {"id": "add_mana", "cat": "do", "role": "effect", "label": "Add mana", "text": "add {mana}", "slots": {"mana": {"kind": "mana", "default": "{G}",
                                                                                                                 "colored": True}}},
    {"id": "add_any", "cat": "do", "role": "effect", "label": "Add one mana of any color", "text": "add one mana of any color"},
    {"id": "investigate", "cat": "do", "role": "effect", "label": "Investigate", "text": "investigate"},
    {"id": "sac_self", "cat": "do", "role": "effect", "may": True, "label": "Sacrifice it", "text": "sacrifice {self}"},
    {"id": "sac_unless_mana", "cat": "do", "role": "effect", "label": "Sacrifice it unless you pay mana",
     "text": "sacrifice {self} unless you pay {mana}", "slots": {"mana": MANA}},
    {"id": "sac_unless_life", "cat": "do", "role": "effect", "label": "Sacrifice it unless you pay life",
     "text": "sacrifice {self} unless you pay {n} life", "slots": {"n": _num(2)}},
    {"id": "sac_unless", "cat": "do", "role": "effect", "label": "Sacrifice it unless you …", "text": "sacrifice {self} unless you {what}",
     "slots": {"what": _choice(_opts("unl_discard", "unl_sac_land", "unl_sac_creature", "unl_return_land"))}},
    {"id": "return_dead", "cat": "do", "role": "effect", "may": True, "label": "Return it (it just died)", "text": "return it to {to}",
     "slots": {"to": _choice(_opts("rd_bf", "rd_bf_p1", "rd_bf_m1", "rd_bf_tapped", "rd_hand"))}, "hats": ["dies"]},
    {"id": "counter_unless", "cat": "do", "role": "effect", "label": "Counter it unless they pay mana",
     "text": "counter that spell or ability unless its controller pays {mana}", "slots": {"mana": MANA}, "hats": ["targeted"]},
    {"id": "counter_unless_life", "cat": "do", "role": "effect", "label": "Counter it unless they pay life",
     "text": "counter that spell or ability unless its controller pays {n} life", "slots": {"n": _num(2)}, "hats": ["targeted"]},
    {"id": "exalt", "cat": "do", "role": "effect", "label": "That creature gets +X/+X",
     "text": "that creature gets {p:signed}/{t:signed} until end of turn", "slots": {"p": SIGNED, "t": SIGNED}, "hats": ["attacks_alone"]},
    {"id": "rally_attackers", "cat": "do", "role": "effect", "label": "Each other attacker gets +X/+X",
     "text": "each other attacking creature gets {p:signed}/{t:signed} until end of turn", "slots": {"p": SIGNED, "t": SIGNED},
     "hats": ["attacks"]},
    {"id": "gy_return_self", "cat": "do", "role": "effect", "label": "Return this card from your graveyard",
     "text": "return this card from your graveyard to {to}", "slots": {"to": _choice(_opts("to_hand", "to_battlefield"))},
     "hats": ["activated"]},
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
    {"id": "combat_rule", "cat": "always", "role": "static", "label": "Attacks or blocks differently", "text": "{self} {rule}",
     "slots": {"rule": _choice(_opts("cr_cant_attack", "cr_cant_attack_block", "cr_attacks", "cr_blocks", "cr_extra_block", "cr_any_block",
                                     "cr_only_fliers", "cr_no_fliers", "cr_not_alone"))}},
    {"id": "evasion", "cat": "always", "role": "static", "label": "Can't be blocked except by …", "text": "{self} can't be blocked except by {who}",
     "slots": {"who": _choice(_opts("ev_flying_reach", "ev_flying", "ev_two", "ev_fear"))}},
    {"id": "evasion_by", "cat": "always", "role": "static", "label": "Can't be blocked by …", "text": "{self} can't be blocked by {who}",
     "slots": {"who": _choice(_opts("eb_more_one", "eb_greater", "eb_power2"))}},
    {"id": "landwalk", "cat": "always", "role": "static", "label": "Unblockable if they control a land type",
     "text": "{self} can't be blocked as long as defending player controls {land}",
     "slots": {"land": _choice(_opts("land_island", "land_plains", "land_swamp", "land_mountain", "land_forest"))}, "no_condition": True},
    {"id": "would_die", "cat": "always", "role": "static", "label": "If it would die, … instead", "text": "If {self} would {what} instead",
     "slots": {"what": _choice(_opts("wd_exile", "wd_top", "wd_gy_exile"))}, "no_condition": True},
    {"id": "prevent_to_self", "cat": "always", "role": "static", "label": "Prevent damage to it",
     "text": "Prevent all {what} that would be dealt to {self}", "slots": {"what": _choice(_opts("pd_combat", "pd_all"))}, "no_condition": True},
    {"id": "uncounterable", "cat": "always", "role": "static", "label": "Can't be countered", "text": "This spell can't be countered",
     "no_condition": True},
    {"id": "self_discount", "cat": "always", "role": "static", "label": "This spell costs less", "text": "This spell costs {n:mana} less to cast {why}",
     "slots": {"n": _num(1, 1, 10), "why": _choice(_opts("why_each_artifact", "why_each_creature", "why_each_land", "why_each_opponent",
                                                          "why_artifact", "why_turn", "why_gy7", "why_three_creatures", "why_opp_lands"))},
     "no_condition": True},
    {"id": "extra_cost", "cat": "always", "role": "static", "label": "An extra cost to cast it",
     "text": "As an additional cost to cast this spell, {what}",
     "slots": {"what": _choice(_opts("xc_sac_creature", "xc_sac_artifact", "xc_discard", "xc_exile_gy"))}, "no_condition": True},
    {"id": "alt_cost", "cat": "always", "role": "static", "label": "Cast it for another cost",
     "text": "{when}you may pay {mana} rather than pay this spell's mana cost",
     "slots": {"when": _choice(_opts("ac_always", "ac_opp_lost", "ac_another", "ac_turn", "ac_artifact")), "mana": MANA}, "no_condition": True},
    # (casting a permanent card from the graveyard; an instant's or a sorcery's "then exile it" is the Flashback piece below)
    {"id": "gy_cast", "cat": "always", "role": "static", "label": "Cast it from your graveyard",
     "text": "You may cast this card from your graveyard by paying {mana} rather than paying its mana cost", "slots": {"mana": MANA},
     "no_condition": True},
    {"id": "gy_cast_exile", "cat": "always", "role": "static", "label": "Cast it from your graveyard, exiling other cards",
     "text": "You may cast this card from your graveyard by paying {mana} and exiling {n:word} other cards from your graveyard rather than "
             "paying its mana cost", "slots": {"mana": MANA, "n": _num(3, 1, 10)}, "no_condition": True},
    {"id": "gy_retrace", "cat": "always", "role": "static", "label": "Cast it from your graveyard, discarding a land",
     "text": "You may cast this card from your graveyard by discarding a land card in addition to paying its other costs", "no_condition": True},
    # (the two casting rules plain Oracle wording doesn't spell out for the engine — an optional additional cost, and "exile it instead
    # of putting it anywhere else" as it leaves the stack — are said with the engine's own keyword for them; a mechanic built on them is
    # still the player's own, e.g. "Rekindle N": Flashback {N} and a When piece of its own)
    {"id": "kicker", "cat": "always", "role": "static", "label": "Optional extra cost (kicker)", "text": "Kicker {mana}", "bare": "Kicker {mana}",
     "slots": {"mana": MANA}, "no_condition": True},
    {"id": "flashback", "cat": "always", "role": "static", "label": "Cast again from your graveyard, then exile (flashback)",
     "text": "Flashback {mana}", "bare": "Flashback {mana}", "slots": {"mana": MANA}, "no_condition": True},
]

PIECE: dict[str, dict[str, Any]] = {p["id"]: p for p in PIECES}

# Numbers the Values palette offers as chips (any number can also be typed into a slot).
VALUE_CHIPS: list[int | str] = [1, 2, 3, 4, 5, "N"]


def vocabulary() -> dict[str, Any]:
    """Everything the Teach Fyodor page needs to draw the palette and read a script back (pure data)."""
    return {"version": 1, "categories": CATEGORIES, "pieces": PIECES, "options": OPTIONS, "values": VALUE_CHIPS}
