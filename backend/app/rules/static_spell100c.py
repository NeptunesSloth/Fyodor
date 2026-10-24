"""-- static spells (wave 100C) -- instant and sorcery sentences the grammar doesn't read, by their exact Oracle wording.

Each wording is read here as the instructions the existing primitives carry out, or rewritten to an equivalent sentence the grammar
already reads (the rewrite must mean the same: 608.2c, the instructions in printed order). An unknown or variant wording is never
matched (the line stays manual)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]

OWNED = "owned100c:"  # "all artifacts target player owns": <player reference>|<selector key> (108.3: the owner)
ATTACHED = "attached100c:"  # "all Auras attached to it": <object reference>|<selector key> (301.5, 303.4: what is attached to it)
NOT_SEL = "not_sel100c:"  # a selector extra: the object doesn't match the selector key after it ("except for …", "that isn't …")
CONTROLS = "controls100c:"  # a player selector extra: the player controls a permanent matching the selector key after it
YOUR_LIFE = "your_life100c"  # a selector comparison value: the life total of the player the selector is read for


def _sel(phrase: str) -> str:
    from app.rules import selectors

    s = selectors.parse(phrase)
    assert s is not None, phrase
    return s.key()


def _key(**fields: Any) -> str:
    from app.rules.selectors import Selector

    return Selector(**fields).key()


def _union(*whos: str) -> str:
    return "union:" + "+".join(whos)


# Sentences the grammar reads in other words with the same meaning.
REWRITES = {
    # (the player who untaps them is the target player either way: 701.26a untapping is no choice)
    "Target player untaps all basic lands they control.": "Untap all basic lands target player controls.",
    # (608.2h: the number is determined once, as the instruction is carried out — the count and the new life total are one step)
    "Count the number of cards in your library. Your life total becomes that number.": "Your life total becomes the number of cards in your library.",
    # (611.2a: "until end of turn" leading the sentence is each effect's duration)
    "Until end of turn, target creature gets +6/+6 and gains trample, and all creatures able to block it this turn do so.":
        "Target creature gets +6/+6 and gains trample until end of turn. All creatures able to block it this turn do so.",
    # ("also" adds nothing: the discard is the second instruction, 608.2c)
    "Each opponent sacrifices a creature of their choice. If you control a Liliana planeswalker, each opponent also discards a card.":
        "Each opponent sacrifices a creature of their choice. If you control a Liliana planeswalker, each opponent discards a card.",
    # ("her": the Liliana planeswalker's controller, as it last existed: 608.2h)
    "Destroy target black creature or black planeswalker. If that permanent was a Liliana planeswalker, her controller loses 3 life.":
        "Destroy target black creature or black planeswalker. If that permanent was a Liliana planeswalker, its controller loses 3 life.",
    # ("less life than an opponent" is "an opponent has more life than you"; "fewer creatures than an opponent" likewise)
    "If you have less life than an opponent, you gain 6 life. If you control fewer creatures than an opponent, create three 1/1 white Soldier "
    "creature tokens.": "If an opponent has more life than you, you gain 6 life. If an opponent controls more creatures than you, create three "
                        "1/1 white Soldier creature tokens.",
    # (701.4a: the spell's one optional behold cost; the condition reads whether it was paid, whatever the subtype's capital letter)
    "~ deals 5 damage to target attacking or blocking creature. If a Dragon was beheld, you gain 2 life.":
        "~ deals 5 damage to target attacking or blocking creature. If a dragon was beheld, you gain 2 life.",
    "Destroy target tapped creature. If a Hero was beheld, scry 2.": "Destroy target tapped creature. If a hero was beheld, scry 2.",
    # (the choice is made as the spell resolves, then the same instruction reads it: 608.2c)
    "Destroy all creatures of the creature type of your choice.": "Choose a creature type. Destroy all creatures of the chosen type.",
    "Return all permanents of the color of your choice to their owners' hands.":
        "Choose a color. Return all permanents of the chosen color to their owners' hands.",
    # (502.3: during a player's untap step only that player's permanents untap, so "creatures" are the creatures that player controls then)
    "Creatures don't untap during target player's next untap step.": "Creatures target player controls don't untap during that player's next untap step.",
    # (the same instruction, its object list put first)
    "Put onto the battlefield under your control all creature cards in all graveyards that were put there from the battlefield this turn.":
        "Put all creature cards in all graveyards that were put there from the battlefield this turn onto the battlefield under your control.",
    # (", then" and ", and" are the same series of instructions in order: 608.2c)
    "Target player loses 1 life, discards a card, then sacrifices a permanent of their choice.":
        "Target player loses 1 life, discards a card, and sacrifices a permanent of their choice.",
}


def _upto(parsed: Parsed | None, group: int) -> Parsed | None:
    """The parse of the same sentence with "target" for "up to one target": group ``group`` may have no target (601.2c, 115.1)."""
    if parsed is None or not isinstance(parsed[1], list) or len(parsed[1]) <= group:
        return None
    groups = [dict(g) for g in parsed[1]]
    groups[group]["min"] = 0
    return parsed[0], groups, parsed[2]


def _plain(text: str) -> Parsed | None:
    from app.rules import scripts

    return scripts.parse_effects(text)


def _seq(*texts: str) -> Parsed | None:
    """Sentences read one by one and run in order (608.2c): their target groups in printed order (601.2c), their bindings apart."""
    from app.rules import scripts

    effects: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for i, text in enumerate(texts):
        part = _plain(text)
        if part is None or part[2]:
            return None
        own = scripts._as_groups(part[1])
        index = list(range(len(groups), len(groups) + len(own)))
        effects += scripts.rename_bindings(scripts._renumber(part[0], index), f"q{i}_")
        groups += own
    if not groups:
        return effects, None, False
    if len(groups) == 1 and groups[0].get("min", 1) == 1 and groups[0].get("max", 1) == 1 and set(groups[0]) <= {"what", "min", "max"}:
        return scripts._renumber(effects, None), groups[0]["what"], False
    return effects, groups, False


def _unstable_experiment() -> Parsed | None:
    # 701.50a: the creature's controller draws, then discards; none chosen (or an illegal one, 608.2b): nothing connives
    return _upto(_plain("Target player draws a card, then target creature you control connives."), 1)


def _tricksters_stratagem() -> Parsed | None:
    return _upto(_plain("The owner of target creature an opponent controls puts it into their library second from the top or on the bottom. "
                        "Then target creature you control connives."), 1)


def _aspirants_ascent() -> Parsed | None:
    # one layer-6 effect grants both (613.1f, 613.7): flying and toxic 1 (702.164)
    parsed = _plain("Target creature gets +1/+3 and gains flying until end of turn.")
    if parsed is None or [e["do"] for e in parsed[0]] != ["pump", "grant"]:
        return None
    pump, grant = parsed[0]
    return [pump, {**grant, "abilities": ["Toxic 1."]}], parsed[1], parsed[2]


def _sigil_blessing() -> Parsed:
    # 611.2a: both until end of turn; "other creatures you control": other than the target (bound before the first pump), the group fixed as
    # the spell resolves (611.2c)
    return ([{"do": "pump", "who": "target", "p": 3, "t": 3, "as": "blessed100c"},
             {"do": "pump", "who": "except:blessed100c|" + _sel("creatures you control"), "p": 1, "t": 1}], "creature_you_control", False)


def _arm_the_cathars() -> Parsed:
    # 601.2c: three target groups, each "other" than the ones before (115.3); "those creatures": every one of them still a legal target (608.2b)
    creature = _sel("creature")
    return ([{"do": "pump", "who": "target:0", "p": 3, "t": 3}, {"do": "pump", "who": "target:1", "p": 2, "t": 2},
             {"do": "pump", "who": "target:2", "p": 1, "t": 1}, {"do": "grant", "who": "all_targets", "keywords": ["vigilance"]}],
            [{"what": "creature", "min": 1, "max": 1}, {"what": creature, "min": 0, "max": 1, "distinct_from": [0]},
             {"what": creature, "min": 0, "max": 1, "distinct_from": [0, 1]}], False)


def _panther_pounce() -> Parsed | None:
    # 701.16a: the target player creates the Clue (an investigation of theirs); then the creature's instructions (608.2c)
    clue = _plain("Investigate.")
    rest = _plain("Target creature gets +1/+0 and gains flying until end of turn. Untap it.")
    if clue is None or rest is None or len(clue[0]) != 1 or not clue[0][0].get("investigate78") or rest[1] != "creature":
        return None
    return ([{**clue[0][0], "who": "target:0"}, *[{**e, "who": "target:1"} for e in rest[0]]],
            [{"what": "player", "min": 1, "max": 1}, {"what": "creature", "min": 1, "max": 1}], False)


def _hidetsugus_second_rite() -> Parsed:
    # checked as the spell resolves (608.2b-c): the target player's life total then
    return ([{"do": "only_if", "cond": {"value": {"life": "target"}, "op": "==", "n": 10}, "skip": 1},
             {"do": "damage", "who": "target", "n": 10}], "player", False)


def _hypothesizzle() -> Parsed | None:
    # 603.12: "When you do" is a reflexive ability, its target chosen as it's put on the stack (after the discard)
    return _seq("Draw two cards.", "You may discard a nonland card. When you do, ~ deals 4 damage to target creature.")


def _lithobraking() -> Parsed | None:
    # (the Lander just created is an artifact that may be sacrificed: 608.2c)
    return _seq("Create a Lander token.", "You may sacrifice an artifact. When you do, ~ deals 2 damage to each creature.")


def _sonar_strike() -> Parsed | None:
    rest = _plain("You gain 3 life if you control a Bat.")
    if rest is None or rest[1] is not None:
        return None
    target = _key(either=(_sel("attacking creature"), _sel("blocking creature"), _sel("tapped creature")))
    return [{"do": "damage", "who": "target", "n": 4}, *rest[0]], target, False


def _savage_swipe() -> Parsed:
    # 608.2c: its power is checked as the spell resolves; then it fights (701.14a: nothing if either creature is gone or an illegal target)
    return ([{"do": "only_if", "cond": {"object": "target:0", "is": _key(types=("Creature",), compare=(("power", "==", 2),))}, "skip": 1},
             {"do": "pump", "who": "target:0", "p": 2, "t": 2}, {"do": "fight", "who": "target:0", "with": "target:1"}],
            [{"what": _sel("creature you control"), "min": 1, "max": 1}, {"what": _sel("creature you don't control"), "min": 1, "max": 1}], False)


def _flame_sweep() -> Parsed:
    return [{"do": "damage", "who": _key(types=("Creature",), extras=(NOT_SEL + _sel("creature you control with flying"),)), "n": 2}], None, False


def _disorder() -> Parsed:
    # one damage event (with_next): the creatures and the players who control a white creature as it resolves (120.3, 608.2h)
    white = _sel("white creature")
    return ([{"do": "damage", "who": white, "n": 2, "with_next": True},
             {"do": "damage", "who": _key(player="any", extras=(CONTROLS + white,)), "n": 2}], None, False)


def _death_by_dragons() -> Parsed | None:
    made = _plain("Create a 5/5 red Dragon creature token with flying.")
    if made is None or len(made[0]) != 1 or made[1] is not None:
        return None
    return [{**made[0][0], "who": "others100c:target"}], "player", False


def _natures_resurgence() -> Parsed:
    # 121.2c: each player's count read for them (their own graveyard), all before the first draw (608.2h)
    return [{"do": "draw", "who": "each_player", "n": {"per_player": {"count": _key(card=True, types=("Creature",), zone_owner="you", zones=("graveyard",))}}}], None, False


def _waiting_in_the_weeds() -> Parsed | None:
    made = _plain("Create a 1/1 green Cat creature token.")
    if made is None or len(made[0]) != 1:
        return None
    forests = _key(controller="you", subtypes=("Forest",), tapped=False)
    return [{**made[0][0], "who": "each_player", "n": {"per_player": {"count": forests}}}], None, False


def _perilous_predicament() -> Parsed:
    # 701.21a, 101.4: each opponent chooses one of each kind (APNAP), then everything chosen is sacrificed at once; the kinds don't overlap
    kinds = [_sel("artifact creature"), _sel("nonartifact creature")]
    return [{"do": "edict_kinds100c", "who": "each_opponent", "sels": kinds, "labels": ["artifact creature", "nonartifact creature"], "n": 1,
             "sel": kinds[0], "label": "creature"}], None, False


def _self_inflicted_wound() -> Parsed | None:
    from app.rules import this_way

    made = this_way.parse("permanents sacrificed this way")
    parsed = _plain("Target opponent sacrifices a green or white creature of their choice.")
    if made is None or parsed is None or len(parsed[0]) != 1 or parsed[0][0]["do"] != "edict":
        return None
    # "If that player does": a creature was actually sacrificed (701.21a; none to sacrifice, or none moved: no life loss)
    return ([{**parsed[0][0], "as": "wound100c"}, {"do": "only_if", "cond": {"value": {**made, "ref_count": "wound100c"}, "op": ">=", "n": 1}, "skip": 1},
             {"do": "lose_life", "who": "target", "n": 2}], parsed[1], False)


def _wheel_and_deal() -> Parsed | None:
    # 601.2c "any number of target opponents"; all of them discard, then all of them draw (121.2c APNAP)
    parsed = _plain("Target opponent discards their hand, then draws seven cards.")
    if parsed is None or parsed[1] != "opponent":
        return None
    return [{**e, "who": "target:0"} for e in parsed[0]], [{"what": "opponent", "min": 0, "max": 250}], False


def _biomantic_mastery() -> Parsed:
    creatures = _sel("creatures you control")
    return ([{"do": "draw", "who": "you", "n": {"for_player": "target:0", "of": {"count": creatures}}},
             {"do": "draw", "who": "you", "n": {"for_player": "target:1", "of": {"count": creatures}}}],
            [{"what": "player", "min": 1, "max": 1}, {"what": "player", "min": 1, "max": 1, "distinct_from": [0]}], False)


def _cabal_conditioning() -> Parsed:
    # the number read once, as the spell resolves (608.2h); each target player discards that many (their own choice, 701.9a)
    return ([{"do": "discard", "who": "target:0", "n": {"max": "mana_value", "of": _sel("permanents you control")}}],
            [{"what": "player", "min": 0, "max": 250}], False)


def _laquatus_creativity() -> Parsed:
    # "that many": the number of cards the instruction told them to draw (the cards in their hand as it resolved, 608.2h)
    return ([{"do": "draw", "who": "target", "n": {"hand": "target"}, "did": "creative100c"},
             {"do": "discard", "who": "target", "n": {"ref_amount": "creative100c"}}], "player", False)


def _hellion_eruption() -> Parsed | None:
    from app.rules import this_way

    made = this_way.parse("permanents sacrificed this way")
    first, second = _plain("Sacrifice all creatures you control."), _plain("Create a 4/4 red Hellion creature token.")
    if made is None or first is None or second is None or len(first[0]) != 1 or len(second[0]) != 1:
        return None
    # "that many": the creatures actually sacrificed (701.21a)
    return [{**first[0][0], "as": "erupted100c"}, {**second[0][0], "n": {**made, "ref_count": "erupted100c"}}], None, False


def _hand_count_draw(colour: str, land: str) -> Callable[[], Parsed]:
    def build() -> Parsed:
        # 701.20a: the hand is revealed (public), then counted: a card that is the land type or the color counts once
        return ([{"do": "reveal_hand", "who": "target"}, {"do": "draw_for_revealed100c", "of": "target", "subtype": land, "color": colour}],
                "opponent", False)
    return build


def _blow_your_house_down() -> Parsed:
    return ([{"do": "restrict", "who": "target:0", "rules": ["cant_block"], "as": "blown100c"},
             {"do": "destroy", "who": "ref:blown100c|" + _key(subtypes=("Wall",))}],
            [{"what": _sel("creature"), "min": 0, "max": 3}], False)


def _tangle() -> Parsed:
    # the creatures attacking as it resolves (named objects, not a group read later), each kept tapped during its controller's next untap step
    # (502.3; a new object, 400.7, isn't affected)
    return [{"do": "stay_tapped", "who": _sel("attacking creature"), "during": "controller"}], None, False


def _katara_counter() -> Parsed:
    return [{"do": "counter", "who": "target:0"}], [{"what": _key(ability="spell_or_ability", zones=("stack",)), "min": 0, "max": 4}], False


def _din_of_the_fireherd() -> Parsed | None:
    # 608.2c: the token first (it is black and red, so it counts), then the two sacrifices in order, each count read as it is carried out
    made = _plain("Create a 5/5 black and red Elemental creature token.")
    creatures = _plain("Target opponent sacrifices a creature of their choice for each black creature you control.")
    if made is None or creatures is None or creatures[1] != "opponent" or len(creatures[0]) != 1 or creatures[0][0]["do"] != "edict":
        return None
    lands = {**creatures[0][0], "sel": _sel("land"), "label": "land", "n": {"count": _sel("red creatures you control")}}
    return [*made[0], creatures[0][0], lands], "opponent", False


def _waylay() -> Parsed | None:
    # 514.3a: a delayed trigger at the beginning of the next cleanup step (players then get priority, and another cleanup step follows)
    parsed = _plain("Create three 2/2 white Knight creature tokens. Exile them at the beginning of the next end step.")
    if parsed is None or len(parsed[0]) != 3 or parsed[0][1].get("do") != "delayed" or parsed[0][1]["when"].get("step") != "end":
        return None
    return [parsed[0][0], {**parsed[0][1], "when": {**parsed[0][1]["when"], "step": "cleanup"}}, parsed[0][2]], parsed[1], False


def _counter_other_spells() -> Parsed:
    # 701.6a: every spell on the stack but this one (abilities aren't spells, 113.1a)
    return [{"do": "counter", "who": "all_other_spells100c"}], None, False


def _summary_dismissal() -> Parsed:
    # one sentence, two instructions in order (608.2c): the other spells are exiled (not countered: a spell that can't be countered is exiled too),
    # then every activated and triggered ability on the stack is countered (mana abilities never use it, 605.3a)
    return [{"do": "exile", "who": _key(zones=("stack",), other=True)}, {"do": "counter", "who": "all_abilities100c"}], None, False


def _leadership_vacuum() -> Parsed:
    # 903.3: a commander is a card; each one the target player controls goes to its owner's command zone (408.1, 400.3)
    return [{"do": "return_card", "who": f"controlled:target|{_key(commander=True)}", "to": "command"}], "player", False


def _chance_for_glory() -> Parsed | None:
    turn = _plain("Take an extra turn after this one. At the beginning of that turn's end step, you lose the game.")
    if turn is None or turn[1] is not None:
        return None
    # 611.2a: no duration stated — indestructible for as long as each creature stays (611.2c: the creatures you control as it resolves)
    return [{"do": "grant", "who": _sel("creatures you control"), "keywords": ["indestructible"], "duration": "permanent"}, *turn[0]], None, False


def _abeyance() -> Parsed:
    # "until end of turn" is this turn (514.2); 605.1a: mana abilities stay possible (two records: the casting limit and the activation limit)
    spells = _key(types=("Instant", "Sorcery"), zones=("stack",))
    return ([{"do": "cast_limit", "who": "target", "until": "turn", "filter": spells, "from": None, "act": None},
             {"do": "cast_limit", "who": "target", "until": "turn", "filter": None, "from": None, "act": "nonmana", "spells": False}], "player", False)


def _sudden_salvation() -> Parsed | None:
    parsed = _plain("Choose up to three target permanent cards in graveyards that were put there from the battlefield this turn. Return them to "
                    "the battlefield tapped under their owners' control.")
    if parsed is None or [e["do"] for e in parsed[0]] != ["choose_targets", "return_card"]:
        return None
    first, back = parsed[0]
    # "each opponent who controls one or more of those permanents": the returned permanents, counted as they are once returned (608.2c)
    return [first, {**back, "as": "saved100c"}, {"do": "draw_for_controllers100c", "who": "ref:saved100c"}], parsed[1], False


def _eye_gouge() -> Parsed:
    # 608.2c: the creature is tested as the second sentence is reached (state-based actions wait, 704.3)
    return ([{"do": "pump", "who": "target", "p": -1, "t": -1},
             {"do": "only_if", "cond": {"object": "target", "is": _key(subtypes=("Cyclops",))}, "skip": 1}, {"do": "destroy", "who": "target"}], "creature", False)


def _fight_to_the_death() -> Parsed:
    # 701.8a, 608.2c: one instruction — the blockers and the blocked attackers are destroyed at once (509.1h: an attacker stays blocked)
    return [{"do": "destroy", "who": _union(_sel("blocking creature"), _sel("blocked creature"))}], None, False


def _end_hostilities() -> Parsed:
    # one instruction: the creatures and every permanent attached to a creature as it resolves, destroyed at once (701.8a)
    return [{"do": "destroy", "who": _union(_sel("creature"), _sel("permanent attached to a creature"))}], None, False


def _soulquake() -> Parsed:
    # one move: the creatures and the creature cards in graveyards go to their owners' hands together (400.3, 610.3)
    return [{"do": "bounce", "who": _union(_sel("creature"), _key(card=True, types=("Creature",), zones=("graveyard",)))}], None, False


def _ultimate_nullification() -> Parsed:
    # one exile instruction (the creatures and every card in every graveyard), then the spell itself to the bottom (608.2m: recursion)
    return [{"do": "exile", "who": _union(_sel("creature"), _key(card=True, zones=("graveyard",)))},
            {"do": "to_library", "who": "self", "place": "bottom"}], None, False


def _shadows_verdict() -> Parsed:
    small = (("mv", "<=", 3),)
    return [{"do": "exile", "who": _union(_key(types=("Creature", "Planeswalker"), compare=small),
                                          _key(card=True, types=("Creature", "Planeswalker"), compare=small, zones=("graveyard",)))}], None, False


def _iridian_maelstrom() -> Parsed:
    # 105.1: "all colors" is white, blue, black, red and green
    return [{"do": "destroy", "who": _key(types=("Creature",), extras=(NOT_SEL + _key(extras=("all_colors:WUBRG",)),))}], None, False


def _hurkyls_recall() -> Parsed:
    # 108.3: the artifacts that player owns, whoever controls them; "their hand" is the owner's (400.3)
    return [{"do": "bounce", "who": f"{OWNED}target|{_sel('artifact')}"}], "player", False


def _hubris() -> Parsed:
    # one move: the target and the Auras attached to it as the spell resolves (608.2b: an illegal target, and the spell does nothing)
    return [{"do": "bounce", "who": _union("target", f"{ATTACHED}target|{_sel('Aura')}")}], "creature", False


def _word_of_undoing() -> Parsed:
    return [{"do": "bounce", "who": _union("target", f"{ATTACHED}target|{_sel('white Aura you own')}")}], "creature", False


def _silence_the_believers() -> Parsed:
    # 601.2c "any number of target creatures" (Strive: the cost per target beyond the first is the spell's own line)
    return [{"do": "exile", "who": _union("target:0", f"{ATTACHED}target:0|{_sel('Aura')}")}], \
        [{"what": _sel("creature"), "min": 0, "max": 250}], False


def _telimtors_edict() -> Parsed:
    return [{"do": "exile", "who": "target"}], _key(either=(_key(owner="you"), _key(controller="you"))), False


def _thraben_exorcism() -> Parsed:
    # 702.146: disturb is a keyword of the front face; a permanent that has it (not the transformed back face)
    return [{"do": "exile", "who": "target"}], _key(either=(_sel("Spirit"), _key(types=("Creature",), with_keywords=("disturb",)), _sel("enchantment"))), False


def _blazing_hope() -> Parsed:
    # 608.2b: the comparison is checked as the target is chosen and again as the spell resolves
    return [{"do": "exile", "who": "target"}], _key(types=("Creature",), compare=(("power", ">=", YOUR_LIFE),)), False


def _lose_all_counters() -> Parsed:
    return [{"do": "lose_all_counters100c", "who": "each_opponent"}], None, False


BUILDERS: dict[str, Callable[[], Parsed | None]] = {
    "Target player draws a card, then up to one target creature you control connives.": _unstable_experiment,
    "The owner of target creature an opponent controls puts it into their library second from the top or on the bottom. Then up to one target "
    "creature you control connives.": _tricksters_stratagem,
    "Until end of turn, target creature gets +1/+3 and gains flying and toxic 1.": _aspirants_ascent,
    "Until end of turn, target creature you control gets +3/+3 and other creatures you control get +1/+1.": _sigil_blessing,
    "Until end of turn, target creature gets +3/+3, up to one other target creature gets +2/+2, and up to one other target creature gets +1/+1. "
    "Those creatures gain vigilance until end of turn.": _arm_the_cathars,
    "Target player investigates. Target creature gets +1/+0 and gains flying until end of turn. Untap it.": _panther_pounce,
    "If target player has exactly 10 life, ~ deals 10 damage to that player.": _hidetsugus_second_rite,
    "Target creature gets -1/-1 until end of turn. If it's a Cyclops, destroy it.": _eye_gouge,
    "Draw two cards. Then you may discard a nonland card. When you do, ~ deals 4 damage to target creature.": _hypothesizzle,
    "Create a Lander token. Then you may sacrifice an artifact. When you do, ~ deals 2 damage to each creature.": _lithobraking,
    "~ deals 4 damage to target attacking, blocking, or tapped creature. You gain 3 life if you control a Bat.": _sonar_strike,
    "Target creature you control gets +2/+2 until end of turn if its power is 2. Then it fights target creature you don't control.": _savage_swipe,
    "~ deals 2 damage to each creature except for creatures you control with flying.": _flame_sweep,
    "~ deals 2 damage to each white creature and each player who controls a white creature.": _disorder,
    "Each player other than target player creates a 5/5 red Dragon creature token with flying.": _death_by_dragons,
    "Each player draws a card for each creature card in their graveyard.": _natures_resurgence,
    "Each player creates a 1/1 green Cat creature token for each untapped Forest they control.": _waiting_in_the_weeds,
    "Each opponent sacrifices an artifact creature and a nonartifact creature of their choice.": _perilous_predicament,
    "Target opponent sacrifices a green or white creature of their choice. If that player does, they lose 2 life.": _self_inflicted_wound,
    "Any number of target opponents each discard their hands, then draw seven cards.": _wheel_and_deal,
    "Draw a card for each creature target player controls, then draw a card for each creature another target player controls.": _biomantic_mastery,
    "Any number of target players each discard a number of cards equal to the greatest mana value among permanents you control.": _cabal_conditioning,
    "Target player draws cards equal to the number of cards in their hand, then discards that many cards.": _laquatus_creativity,
    "Sacrifice all creatures you control, then create that many 4/4 red Hellion creature tokens.": _hellion_eruption,
    "Target opponent reveals their hand. You draw a card for each Mountain and red card in it.": _hand_count_draw("R", "Mountain"),
    "Target opponent reveals their hand. You draw a card for each Forest and green card in it.": _hand_count_draw("G", "Forest"),
    "Up to three target creatures can't block this turn. Destroy any of them that are Walls.": _blow_your_house_down,
    "Each attacking creature doesn't untap during its controller's next untap step.": _tangle,
    "Counter up to four target spells and/or abilities.": _katara_counter,
    "Create a 5/5 black and red Elemental creature token. Target opponent sacrifices a creature of their choice for each black creature you control, "
    "then sacrifices a land of their choice for each red creature you control.": _din_of_the_fireherd,
    "Create three 2/2 white Knight creature tokens. Exile them at the beginning of the next cleanup step.": _waylay,
    "Counter all other spells.": _counter_other_spells,
    "Exile all other spells and counter all abilities.": _summary_dismissal,
    "Target player returns each commander they control from the battlefield to the command zone.": _leadership_vacuum,
    "Creatures you control gain indestructible. Take an extra turn after this one. At the beginning of that turn's end step, you lose the game.":
        _chance_for_glory,
    "Until end of turn, target player can't cast instant or sorcery spells, and that player can't activate abilities that aren't mana abilities.":
        _abeyance,
    "Choose up to three target permanent cards in graveyards that were put there from the battlefield this turn. Return them to the battlefield "
    "tapped under their owners' control. You draw a card for each opponent who controls one or more of those permanents.": _sudden_salvation,
    "Destroy all blocking creatures and all blocked creatures.": _fight_to_the_death,
    "Destroy all creatures and all permanents attached to creatures.": _end_hostilities,
    "Return all creatures on the battlefield and all creature cards in graveyards to their owners' hands.": _soulquake,
    "Exile all creatures and graveyards. Put ~ on the bottom of its owner's library.": _ultimate_nullification,
    "Exile all creatures and planeswalkers with mana value 3 or less from the battlefield and all creature and planeswalker cards with mana value 3 or less "
    "from all graveyards.": _shadows_verdict,
    "Destroy each creature that isn't all colors.": _iridian_maelstrom,
    "Return all artifacts target player owns to their hand.": _hurkyls_recall,
    "Return target creature and all Auras attached to it to their owners' hands.": _hubris,
    "Return target creature and all white Auras you own attached to it to their owners' hands.": _word_of_undoing,
    "Exile any number of target creatures and all Auras attached to them.": _silence_the_believers,
    "Exile target permanent you own or control.": _telimtors_edict,
    "Exile target Spirit, creature with disturb, or enchantment.": _thraben_exorcism,
    "Exile target creature with power greater than or equal to your life total.": _blazing_hope,
    "Each opponent loses all counters.": _lose_all_counters,
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """A line of an instant or sorcery that isn't an effect: "Ghostfire is colorless." (604.3, 105.2c: a characteristic-defining ability,
    working in every zone; the card's data already has no colors, so nothing else reads it)."""
    from app.rules import scripts

    if ability.kind == "spell" and ch.is_instant_or_sorcery and not ch.colors and scripts.self_text(ability.text, ch.name) == "~ is colorless.":
        return {"kind": "static", "static": "color_cda100c", "effects": []}
    return None


def parse(body: str) -> Parsed | None:
    text = body.strip()
    if (rewritten := REWRITES.get(text)) is not None:
        from app.rules import scripts

        return scripts.parse_effects(rewritten)
    build = BUILDERS.get(text)
    return build() if build is not None else None


# -- the references these readings use (effects._cards, selectors.matches / matches_player) --
def cards(plan: Any, ctx: Any, who: str) -> list[str]:
    from app.rules import effects, selectors

    if who.startswith(OWNED):
        ref, _, key = who[len(OWNED):].partition("|")
        owners = set(effects._players(plan, ctx, ref))
        return [c for c in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], ctx.get("source_card"))
                if plan.state.cards[c].owner in owners]
    ref, _, key = who[len(ATTACHED):].partition("|")
    hosts = set(effects._cards(plan, ctx, ref))
    return [c for c in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], ctx.get("source_card"))
            if plan.state.cards[c].attached_to in hosts]


def extra_ok(plan: Any, extra: str, card: Any, ch: Any, you: str, source: str | None, attacker: str | None) -> bool:
    from app.rules import selectors

    return not selectors.matches(plan, selectors.from_key(extra[len(NOT_SEL):]), card, ch, you, source, attacker)


def player_extra_ok(plan: Any, extra: str, pid: str, you: str) -> bool:
    from app.rules import selectors

    sel = selectors.from_key(extra[len(CONTROLS):])
    return any(plan.state.cards[c].controller == pid for c in selectors.candidates(plan, sel, you))


def your_life(plan: Any, you: str) -> int:
    return int(plan.state.players[you].life) if you in plan.state.players else 0


def lose_all_counters(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """122.1, 122.8: every counter of every kind the player has is removed (speed is a value, not a counter: 702.179)."""
    from app.rules import effects

    for pid in effects._players(plan, ctx, e["who"]):
        for kind, have in sorted(plan.state.players[pid].resources.items()):
            if kind != "speed" and have > 0:
                plan.do({"type": "resource", "player": pid, "key": kind, "delta": -have}, actor=ctx["controller"])
    return True


def edict_kinds(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"Each opponent sacrifices an artifact creature and a nonartifact creature of their choice": each player chooses one of each kind in
    APNAP order (101.4), then all of them are sacrificed at once (701.21a; effects._choose_next resumes as an edict)."""
    from app.rules import effects

    who = effects._players(plan, ctx, e["who"])
    turns = [(p, k) for p in plan.apnap() if p in who for k in e["sels"]]
    return effects._choose_next(plan, ctx, e, turns, [], "edict")


def draw_for_revealed(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"You draw a card for each Mountain and red card in it": the cards of the hand just revealed (public: 701.20a), counted now (608.2h);
    a card that is both counts once. The draw follows as the next instruction (the draw choke point, 121.2)."""
    from app.rules import effects

    players = effects._players(plan, ctx, e["of"])
    n = sum(1 for p in players for cid in plan.state.zones.get(f"{p}:hand", [])
            if e["subtype"] in (ch := plan.ch(plan.state.cards[cid])).subtypes or e["color"] in ch.colors)
    if n > 0:
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "draw", "who": "you", "n": n}]
    return True


def draw_for_controllers(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"You draw a card for each opponent who controls one or more of those permanents": the permanents the instruction before returned (the
    objects they became, 400.7j), still on the battlefield; each opponent counted once."""
    from app.rules import effects

    me = ctx["controller"]
    held = {plan.state.cards[c].controller for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")}
    n = len([p for p in held if p != me and p in plan.live()])
    if n > 0:
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "draw", "who": "you", "n": n}]
    return True


PRIMITIVES = {"lose_all_counters100c": lose_all_counters, "edict_kinds100c": edict_kinds, "draw_for_revealed100c": draw_for_revealed,
              "draw_for_controllers100c": draw_for_controllers}
