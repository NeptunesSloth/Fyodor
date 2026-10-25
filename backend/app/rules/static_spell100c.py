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
PARTNER = "partner100c:"  # "that creature" a creature is paired with (702.95): <object reference>
SAME_MV = "samemv100c:"  # the named objects and each other object of the selector with the same mana value: <object reference>|<selector key>
DUST = "dust100c"  # the creatures that share no creature type with a creature that convoked this spell (702.51a)
LOYALTY = "loyalty100c"  # a selector extra: a loyalty ability (606.3) of a planeswalker on the stack
ATTACKED = "attacked100c"  # a player selector extra: the player declared one or more attackers this turn (508.1)


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
    # (a card in exile is an exiled card: 406.1)
    "Return target exiled card with flashback you own to your hand.": "Return target card with flashback you own from exile to your hand.",
    # ("They have": the tokens are created with it; "one of those tokens": one such token)
    "If you control an Eldrazi Spawn, create three 0/1 colorless Eldrazi Spawn creature tokens. They have \"Sacrifice this token: Add {C}.\" Otherwise, "
    "create one of those tokens.": "If you control an Eldrazi Spawn, create three 0/1 colorless Eldrazi Spawn creature tokens with \"Sacrifice this token: "
                                   "Add {C}.\" Otherwise, create a 0/1 colorless Eldrazi Spawn creature token with \"Sacrifice this token: Add {C}.\"",
    # ("its controller's graveyard" is the token's own controller's: "your" in its own ability)
    "Each player creates a green Elephant creature token. Those creatures have \"This token's power and toughness are each equal to the number of creature "
    "cards in its controller's graveyard.\"": "Each player creates a green Elephant creature token with \"This creature's power and toughness are each "
                                                "equal to the number of creature cards in your graveyard.\"",
    # ("You may put a creature card from it": a choice of one, or none, then the move; "that creature": the permanent it became, 400.7)
    "Target opponent reveals their hand. You may put a creature card from it onto the battlefield under your control. That creature gains haste. Sacrifice "
    "it at the beginning of the next end step.": "Target opponent reveals their hand. You may choose a creature card from it. Put that card onto the "
                                                 "battlefield under your control. It gains haste. Sacrifice it at the beginning of the next end step.",
    # (701.24a: put into the library, then shuffled — the same as a card put on top, then a shuffle)
    "Draw two cards, then shuffle a card from your hand into your library.": "Draw two cards. Put a card from your hand on top of your library. Then shuffle.",
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


def _choice(who: str, *options: tuple[str, str]) -> Parsed | None:
    """"A or B": the controller chooses one as it resolves (608.2d); nothing to choose when ``who`` names nothing (both do nothing)."""
    picked = [(label, _plain(text)) for label, text in options]
    if any(p is None or p[1] is not None for _, p in picked):
        return None
    return [{"do": "choose_effect", "who": who, "options": [{"label": label, "effects": p[0]} for label, p in picked if p is not None]}], None, False


def _essence_filter() -> Parsed | None:
    return _choice(_sel("enchantment"), ("All enchantments", "Destroy all enchantments."), ("All nonwhite enchantments", "Destroy all nonwhite enchantments."))


def _lava_storm() -> Parsed | None:
    return _choice(_union(_sel("attacking creature"), _sel("blocking creature")), ("Each attacking creature", "~ deals 2 damage to each attacking creature."),
                   ("Each blocking creature", "~ deals 2 damage to each blocking creature."))


def _tombfire() -> Parsed:
    # 702.34: a card with flashback; "their graveyard": the target player's (the Mudhole form, player_zones)
    return [{"do": "exile", "who": "zones_of:graveyard:target|" + _key(card=True, zones=(), extras=("has_flashback",))}], "player", False


def _telekinesis() -> Parsed | None:
    tap = _plain("Tap target creature. It doesn't untap during its controller's next untap step.")
    prevent = _plain("Prevent all combat damage that would be dealt by target creature this turn.")
    if tap is None or prevent is None or len(tap[0]) != 2 or len(prevent[0]) != 1:
        return None
    # 502.3: two of its controller's untap steps (next_untap: "more", the untap steps after the first)
    return [tap[0][0], prevent[0][0], {**tap[0][1], "more": 1}], "creature", False


def _fire_and_brimstone() -> Parsed:
    # 508.1: a player who declared one or more attackers this turn (the turn log); one damage event to both players (120.3)
    return ([{"do": "damage", "who": "target", "n": 4, "with_next": True}, {"do": "damage", "who": "you", "n": 4}],
            _key(player="any", extras=(ATTACKED,)), False)


def _structural_collapse() -> Parsed:
    # 701.21a, 101.4: one artifact, then one land, of their choice; a permanent both (an artifact land) is chosen once only
    kinds = [_sel("artifact"), _sel("land")]
    return ([{"do": "edict_kinds100c", "who": "target", "sels": kinds, "labels": ["artifact", "land"], "n": 1, "sel": kinds[0], "label": "artifact",
              "distinct": True}, {"do": "damage", "who": "target", "n": 2}], "player", False)


def _pulse_of_the_forge() -> Parsed:
    # the life totals compared after the damage (608.2c); a planeswalker's controller as it last existed (608.2h); "return ~": the spell to its owner's hand
    return ([{"do": "damage", "who": "target", "n": 4}, {"do": "if_more_life100c", "who": "target_player_or_controller", "skip": 1}, {"do": "bounce", "who": "self"}],
            "player_or_planeswalker", False)


def _feast_of_worms() -> Parsed | None:
    parsed = _plain("Destroy target land. If that land was legendary, its controller sacrifices a land of their choice.")
    if parsed is None or len(parsed[0]) != 3 or parsed[0][2]["do"] != "edict" or parsed[0][0].get("as") != "e0":
        return None
    # "another land": not the destroyed land if it's still there (indestructible, regenerated)
    return [*parsed[0][:2], {**parsed[0][2], "exclude": "e0"}], parsed[1], False


def _isildurs_fateful_strike() -> Parsed | None:
    parsed = _plain("Destroy target creature. Its controller exiles a card from their hand.")
    if parsed is None or len(parsed[0]) != 2 or parsed[0][1]["do"] != "discard":
        return None
    # its controller as it last existed (608.2h); "the difference": the cards in hand beyond four, counted as this is reached (608.2c); their choice (701.9a)
    return [parsed[0][0], {"do": "hand_excess100c", "who": parsed[0][1]["who"], "over": 4}], parsed[1], False


def _no_witnesses() -> Parsed | None:
    most, clue, wipe = (_plain("Each player who controls the most creatures creates a Clue token."), _plain("Investigate."),
                        _plain("Destroy all creatures."))
    if most is None or clue is None or wipe is None or [e["do"] for e in most[0]] != ["players_where", "create_token"] or len(clue[0]) != 1:
        return None
    # 701.16a: each of those players investigates (ties: all of them); then the creatures, the new Clues not among them
    return [most[0][0], {**clue[0][0], "who": most[0][1]["who"]}, *wipe[0]], None, False


def _false_memories() -> Parsed | None:
    parsed = _plain("Mill seven cards. At the beginning of the next end step, exile a card from your graveyard.")
    if parsed is None or [e["do"] for e in parsed[0]] != ["mill", "delayed", "deferred:return_choice"]:
        return None
    # your choice of seven as the delayed trigger resolves (all of them with fewer)
    return [*parsed[0][:2], {**parsed[0][2], "n": 7}], None, False


def _wild_ricochet() -> Parsed | None:
    copy = _plain("Copy target instant or sorcery spell. You may choose new targets for the copy.")
    if copy is None or copy[0][0]["do"] != "copy_spell":
        return None
    # 115.7d: each of its targets kept or changed first; then the copy, of the spell as it now is (707.10, 707.10c)
    return [{"do": "choose_new_targets", "who": "target"}, *copy[0]], copy[1], False


def _bonus_round() -> Parsed | None:
    parsed = _plain("Until end of turn, whenever you cast an instant or sorcery spell, copy that spell. You may choose new targets for the copy.")
    if parsed is None or [e["do"] for e in parsed[0]] != ["delayed", "deferred:copy_spell", "deferred:copy_new_targets"]:
        return None
    head, copy, new = parsed[0]
    when = {**head["when"], "cond": {**head["when"]["cond"], "player": "any"}, "text": "a player casts an instant or sorcery spell"}
    # 707.10: "that player copies it": the caster controls the copy and chooses its new targets
    return [{**head, "when": when}, {**copy, "by": "event_player"}, new], None, False


def _rhystic_scrying() -> Parsed | None:
    unless, draw, discard = _plain("Draw three cards unless any player pays {2}."), _plain("Draw three cards."), _plain("Discard three cards.")
    if unless is None or draw is None or discard is None or [e["do"] for e in unless[0]] != ["each_may", "only_if", "draw"]:
        return None
    pay, gate, _ = unless[0]
    # the offer after the draw (608.2c), each player in turn order (101.4); one payment is enough
    return [*draw[0], pay, {**gate, "cond": {**gate["cond"], "negate": False}}, *discard[0]], None, False


def _become_brutes() -> Parsed | None:
    haste = _plain("Up to two target creatures each gain haste until end of turn.")
    if haste is None or not isinstance(haste[1], list):
        return None
    return [*haste[0], {"do": "each100c", "who": "target:0", "then": {"do": "create_role", "role": "Monster"}}], [{**haste[1][0], "min": 1}], False


def _fateful_handoff() -> Parsed | None:
    draw = _plain("Draw cards equal to the mana value of target artifact or creature you control.")
    if draw is None:
        return None
    # "An opponent": chosen as it resolves, not targeted (608.2d); no duration (611.2a)
    return [*draw[0], {"do": "gain_control", "who": "target", "to": "choose_opponent"}], draw[1], False


def _joint_assault() -> Parsed | None:
    pump = _plain("Target creature gets +2/+2 until end of turn.")
    if pump is None or len(pump[0]) != 1:
        return None
    return [pump[0][0], {**pump[0][0], "who": PARTNER + "target"}], pump[1], False


def _quag_feast() -> Parsed | None:
    choose = _plain("Choose target creature, planeswalker, or Vehicle.")
    if choose is None or len(choose[0]) != 1:
        return None
    # the mana value and the graveyard compared after the mill (608.2c)
    return [*choose[0], {"do": "mill", "who": "you", "n": 2}, {"do": "if_mv_upto_graveyard100c", "who": "target", "skip": 1},
            {"do": "destroy", "who": "target"}], choose[1], False


def _grave_consequences() -> Parsed | None:
    lose = _plain("Each player loses 1 life for each card in their graveyard.")
    if lose is None:
        return None
    # 101.4: each player chooses in turn order, then the chosen cards are exiled together; then the counts (608.2c)
    return [{"do": "player_chooses", "who": "each_player", "sel": _key(card=True, zones=("graveyard",)), "n": 250, "upto": True, "optional": True,
             "label": "card", "as": "grave100c"}, {"do": "exile", "who": "ref:grave100c"}, *lose[0]], None, False


def _turn_the_earth() -> Parsed:
    # 701.24a: each owner puts their targeted cards into their library and shuffles it (a library with none of them isn't shuffled)
    return ([{"do": "shuffle_library", "who": "owners100c:target:0", "zones": [], "cards": "target:0"}, {"do": "gain_life", "who": "you", "n": 2}],
            [{"what": _key(card=True, zones=("graveyard",)), "min": 0, "max": 3}], False)


def _mists_of_lorien() -> Parsed:
    # one move (610.3): the target and the others with its mana value as the spell resolves
    return [{"do": "bounce", "who": f"{SAME_MV}target|{_sel('nonland permanent')}"}], "nonland_permanent", False


def _earth_rumble() -> Parsed | None:
    bend = _plain("Earthbend 2.")
    fight = _plain("You may sacrifice an artifact. When you do, up to one target creature you control fights target creature an opponent controls.")
    if bend is None or fight is None or [e["do"] for e in fight[0]] != ["optional_payment", "reflexive"]:
        return None
    # 603.12: "When you do": the land was earthbent (it is the spell's one target: a legal one was); the fight's targets chosen as it triggers
    return [{**bend[0][0], "as": "earth100c"}, {**fight[0][1], "cond": {"object": "ref:earth100c", "is": _sel("land")}}], bend[1], False


def _earthshape() -> Parsed | None:
    bend, grant, me = (_plain("Earthbend 3."), _plain("Each creature you control with power 3 or less gains hexproof and indestructible until end of turn."),
                       _plain("You gain hexproof until end of turn."))
    if bend is None or grant is None or me is None:
        return None
    # "that land's power": the earthbent land's, read as the next sentence is reached (608.2c), after its counters
    return [{**bend[0][0], "as": "earth100c"}, {"do": "power_cap100c", "of": "ref:earth100c", "then": grant[0][0]}, *me[0]], bend[1], False


def _invoke_despair() -> Parsed | None:
    from app.rules import this_way

    made = this_way.parse("permanents sacrificed this way")
    if made is None:
        return None
    out: list[dict[str, Any]] = []
    for kind in ("creature", "enchantment", "planeswalker"):
        edict = _plain(f"Target opponent sacrifices a {kind} of their choice.")
        if edict is None or len(edict[0]) != 1 or edict[0][0]["do"] != "edict":
            return None
        # "If they can't": nothing was sacrificed (none to sacrifice, 701.21a); the process three times, in order (608.2c)
        out += [{**edict[0][0], "as": f"despair100c_{kind}"}, {"do": "only_if", "cond": {"value": {**made, "ref_count": f"despair100c_{kind}"}, "op": "<=", "n": 0},
                                                                "skip": 2}, {"do": "lose_life", "who": "target", "n": 2}, {"do": "draw", "who": "you", "n": 1}]
    return out, "opponent", False


def _coalition_victory() -> Parsed:
    return [{"do": "if_coalition100c", "skip": 1}, {"do": "win_game", "who": "you"}], None, False


def _ultimate_magic_meteor() -> Parsed | None:
    exiled = _plain("If this spell was cast from exile, draw a card.")
    if exiled is None or exiled[0][0]["do"] != "only_if":
        return None
    # "for each opponent, choose …": the caster chooses one of that player's artifacts or lands (none: nothing), then one destroy (701.8a)
    return [{"do": "damage", "who": "each_creature", "n": 7}, {**exiled[0][0], "skip": 2},
            {"do": "player_chooses", "who": "each_opponent", "by": "you", "sel": _sel("artifact or land"), "n": 1, "label": "artifact or land",
             "as": "meteor100c"}, {"do": "destroy", "who": "ref:meteor100c"}], None, False


def _imposing_grandeur() -> Parsed:
    # each player answers in turn order (101.4), then each who said yes discards their hand and draws; "a commander they own": theirs (903.3)
    mv = {"max": "mana_value", "of": _key(commander=True, owner="you", card=True, zones=("battlefield", "command"))}
    return [{"do": "each_may", "who": "each_player", "act": [{"do": "discard", "who": "you", "n": 0, "all": True}, {"do": "draw", "who": "you", "n": mv}],
             "text": "discard your hand and draw cards"}], None, False


def _everything_comes_to_dust() -> Parsed:
    # one exile instruction (610.3); an artifact or enchantment creature goes as an artifact / enchantment even if it shares a type
    return [{"do": "exile", "who": _union(DUST, _sel("artifact"), _sel("enchantment"))}], None, False


def _waterbending_lesson() -> Parsed | None:
    parsed = _plain("Draw three cards. Then discard a card unless you pay {2}.")
    if parsed is None or [e["do"] for e in parsed[0]] != ["draw", "optional_payment", "only_if", "discard"]:
        return None
    # 701.67a: the same offer, paid by waterbending (each artifact or creature tapped pays {1}: optional_payment, waterbend_payments)
    return [parsed[0][0], {**parsed[0][1], "cost": "Waterbend {2}"}, *parsed[0][2:]], None, False


def _mercurial_transformation() -> Parsed | None:
    forms = [(label, _plain(f"Until end of turn, target nonland permanent loses all abilities and becomes a blue {kind} creature with base power and toughness "
                            f"{pt}.")) for label, kind, pt in (("Frog 1/1", "Frog", "1/1"), ("Octopus 4/4", "Octopus", "4/4"))]
    if any(p is None or len(p[0]) != 1 for _, p in forms):
        return None
    # 608.2d: "your choice of": chosen as it resolves; one layer set either way (613.1d-f, 613.4b)
    return [{"do": "choose_effect", "who": "target", "options": [{"label": label, "effects": p[0]} for label, p in forms if p is not None]}], \
        forms[0][1][1] if forms[0][1] is not None else None, False


def _burning_of_xinye() -> Parsed:
    land = _sel("land")
    # each player chooses four of their own lands (all, with fewer) and destroys them (701.8a), you first, then the target opponent (608.2c)
    steps = [step for who, tag in (("you", "xinye100c_a"), ("target", "xinye100c_b"))
             for step in ({"do": "player_chooses", "who": who, "sel": land, "n": 4, "label": "land", "as": tag}, {"do": "destroy", "who": f"ref:{tag}"})]
    return [*steps, {"do": "damage", "who": "each_creature", "n": 4}], "opponent", False


def _split_the_party() -> Parsed:
    # the caster chooses (608.2d), half rounded up (107.1a); one move to their owners' hands
    return ([{"do": "player_chooses", "who": "target", "by": "you", "sel": _sel("creature"), "n": {"half_own": "up"}, "label": "creature", "as": "split100c"},
             {"do": "bounce", "who": "ref:split100c"}], "player", False)


def _dreams_of_steel_and_oil() -> Parsed | None:
    hand = _plain("Target opponent reveals their hand. You choose an artifact or creature card from it. Exile that card.")
    if hand is None or [e["do"] for e in hand[0]] != ["reveal_hand", "choose_from_hand", "exile"]:
        return None
    reveal, pick, _ = hand[0]
    yard = {"do": "player_chooses", "who": "target", "by": "you", "sel": _key(card=True, types=("Artifact", "Creature"), zones=("graveyard",)), "n": 1,
            "label": "artifact or creature card", "as": pick["as"], "add": True}
    # both choices first (the second joins the first's binding), then one exile of the chosen cards (608.2c)
    return [reveal, pick, yard, {"do": "exile", "who": f"ref:{pick['as']}"}], hand[1], False


def _pox() -> Parsed:
    # each step for every player, then the next (608.2c); each count read as its step is reached, a third rounded up (107.1a)
    creature, land = _sel("creature"), _sel("land")
    return ([{"do": "thirds100c", "what": "life"}, {"do": "thirds100c", "what": "hand"},
             {"do": "edict_each100c", "sel": creature, "label": "creature", "count": creature, "div": 3},
             {"do": "edict_each100c", "sel": land, "label": "land", "count": land, "div": 3}], None, False)


def _omen_of_fire() -> Parsed | None:
    bounce = _plain("Return all Islands to their owners' hands.")
    if bounce is None:
        return None
    # each player's own count of white permanents (after the bounce, 608.2c); their choices in turn order, then one sacrifice (101.4)
    return [*bounce[0], {"do": "edict_each100c", "sel": _key(either=(_sel("Plains"), _sel("white permanent"))), "label": "Plains or white permanent",
                         "count": _sel("white permanent"), "div": 1}], None, False


def _sway_of_the_stars() -> Parsed | None:
    perms, rest, life = (_plain("Put all permanents on top of their owners' libraries."),
                         _plain("Each player shuffles their hand and graveyard into their library, then draws seven cards."), _plain("Your life total becomes 7."))
    if perms is None or rest is None or life is None:
        return None
    # every permanent is owned by a player (108.3): all of them go in with the hands and graveyards, then each library is shuffled (701.24a)
    return [*perms[0], *rest[0], {**life[0][0], "who": "each_player"}], None, False


def _eliminate_the_impossible() -> Parsed | None:
    clue, pump = _plain("Investigate."), _plain("Creatures your opponents control get -2/-0 until end of turn.")
    if clue is None or pump is None:
        return None
    # "any of them": the creatures your opponents control as this is reached (608.2c); 701.60: the designation ends
    return [*clue[0], *pump[0], {"do": "unsuspect100c", "who": pump[0][0]["who"]}], None, False


def _aura_barbs() -> Parsed | None:
    own = _plain("Each enchantment deals 2 damage to its controller.")
    if own is None or len(own[0]) != 1:
        return None
    # two damage events in order (608.2c), each enchantment / Aura its own source (120.3)
    return [*own[0], {**own[0][0], "src": "each:" + _sel("Aura attached to a creature"), "to": "attached100c"}], None, False


def _pollen_lullaby() -> Parsed | None:
    fog, clash = _plain("Prevent all combat damage that would be dealt this turn."), _plain("Clash with an opponent. If you win, draw a card.")
    if fog is None or clash is None or [e["do"] for e in clash[0]] != ["clash", "only_if", "draw"]:
        return None
    # 502.3, 611.2c: the creatures that player controls when their next untap step comes (next_untap's mass record)
    return [*fog[0], *clash[0][:2], {"do": "clash_freeze100c", "sel": [_sel("creature")]}], None, False


def _metamorphose() -> Parsed | None:
    tuck = _plain("Put target permanent an opponent controls on top of its owner's library.")
    put = _plain("That player may put an artifact, creature, enchantment, or land card from their hand onto the battlefield.")
    if tuck is None or put is None or len(tuck[0]) != 1 or len(put[0]) != 1:
        return None
    # "That opponent": the permanent's controller as it last existed (608.2h); their own choice from their hand (hidden until put)
    return [{**tuck[0][0], "as": "meta100c"}, {**put[0][0], "who": "ref:meta100c.controller"}], tuck[1], False


def _battlefield_improvisation() -> Parsed | None:
    pump, attach = _plain("Target creature gets +2/+2 until end of turn."), _plain("Attach any number of Equipment you control to target creature.")
    if pump is None or attach is None:
        return None
    # checked as the second sentence is reached (608.2c); "any number" (701.3a): none is a choice too
    return [*pump[0], {"do": "only_if", "cond": {"object": "target", "is": _sel("attacking creature")}, "skip": 1}, *attach[0]], pump[1], False


def _rite_of_ruin() -> Parsed | None:
    from itertools import permutations

    kinds = {"artifact": ("an artifact", "two artifacts", "three artifacts"), "creature": ("a creature", "two creatures", "three creatures"),
             "land": ("a land", "two lands", "three lands")}
    options = []
    for order in permutations(kinds):  # 608.2d: the order chosen as it resolves; then one, two, three of each kind in that order (608.2c)
        steps = [_plain(f"Each player sacrifices {kinds[k][i]} of their choice.") for i, k in enumerate(order)]
        if any(p is None for p in steps):
            return None
        options.append({"label": ", ".join(k + "s" for k in order).capitalize(), "effects": [e for p in steps if p is not None for e in p[0]]})
    return [{"do": "choose_effect", "who": _sel("permanent"), "options": options}], None, False


def _goldwardens_gambit() -> Parsed | None:
    made = _plain("Create five 2/2 red Rebel creature tokens. They gain haste until end of turn.")
    if made is None or [e["do"] for e in made[0]] != ["create_token", "grant"]:
        return None
    # 701.3a: one optional attachment for each token, in turn (an Equipment may move on to a later one)
    return [*made[0], {"do": "each100c", "who": made[0][1]["who"], "then": {"do": "attach_choose", "n": 1, "kinds": ["Equipment"], "optional": True}}], None, False


def _reckless_crew() -> Parsed | None:  # -- reckless crew (wave 110C) -- 701.3a, as Goldwarden's Gambit: one optional attachment per token
    made = _plain("Create X 2/1 red Dwarf Berserker creature tokens, where X is the number of Vehicles you control plus the number of Equipment you control.")
    if made is None or [e["do"] for e in made[0]] != ["create_token"]:
        return None
    return [{**made[0][0], "as": "crew110c"}, {"do": "each100c", "who": "ref:crew110c", "then": {"do": "attach_choose", "n": 1, "kinds": ["Equipment"], "optional": True}}], None, False


def _memory_theft() -> Parsed | None:
    theft = _plain("Target opponent reveals their hand. You choose a nonland card from it. That player discards that card.")
    if theft is None:
        return None
    # your choice of one or none (608.2d) among the exiled cards with an Adventure that player owns (108.3), to that player's graveyard (400.3)
    yard = {"do": "return_choice", "who": f"{OWNED}target|{_key(card=True, extras=('has_adventure',), zones=('exile',))}", "to": "graveyard", "n": 1,
            "upto": True, "random": False, "label": "card that has an Adventure"}
    return [*theft[0], yard], theft[1], False


BUILDERS: dict[str, Callable[[], Parsed | None]] = {
    "Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. You may put a card that has an Adventure "
    "that player owns from exile into that player's graveyard.": _memory_theft,
    "Create five 2/2 red Rebel creature tokens. They gain haste until end of turn. For each of those tokens, you may attach an Equipment you control to it.":
        _goldwardens_gambit,
    "Create X 2/1 red Dwarf Berserker creature tokens, where X is the number of Vehicles you control plus the number of Equipment you control. "
    "For each of those tokens, you may attach an Equipment you control to it.": _reckless_crew,
    "Choose an order for artifacts, creatures, and lands. Each player sacrifices one permanent of their choice of the first type, sacrifices two of their "
    "choice of the second type, then sacrifices three of their choice of the third type.": _rite_of_ruin,
    "Target creature gets +2/+2 until end of turn. If that creature is attacking, you may attach any number of Equipment you control to it.":
        _battlefield_improvisation,
    "Prevent all combat damage that would be dealt this turn. Clash with an opponent. If you win, creatures that player controls don't untap during the "
    "player's next untap step.": _pollen_lullaby,
    "Put target permanent an opponent controls on top of its owner's library. That opponent may put an artifact, creature, enchantment, or land card from "
    "their hand onto the battlefield.": _metamorphose,
    "Each enchantment deals 2 damage to its controller, then each Aura attached to a creature deals 2 damage to the creature it's attached to.": _aura_barbs,
    # one damage event (120.3), each creature's own amount counted as it resolves (608.2h)
    "~ deals 2 damage to each creature for each Aura attached to that creature.": lambda: ([{"do": "aura_damage100c", "n": 2}], None, False),
    "Investigate. Creatures your opponents control get -2/-0 until end of turn. If any of them are suspected, they're no longer suspected.":
        _eliminate_the_impossible,
    "Until end of turn, target non-Brushwagg creature gets +1/+1 for each supertype, card type, and subtype it has.":
        lambda: ([{"do": "type_pump100c", "who": "target"}], _sel("non-Brushwagg creature"), False),
    # 305.7, 205.1b: the five basic land types added (each one's mana ability with it, 305.6); the lands you control as it resolves (611.2c)
    "Lands you control gain all basic land types until end of turn.": lambda: ([{"do": "become", "who": _sel("lands you control"), "types": [],
                                                                               "duration": "end_of_turn", "retain": True,
                                                                               "land_types": ["Plains", "Island", "Swamp", "Mountain", "Forest"]}], None, False),
    # 509.1h: each attacking creature becomes blocked (one already blocked stays so)
    "Attacking creatures become blocked.": lambda: ([{"do": "become_blocked", "who": _sel("attacking creature")}], None, False),
    "Each player shuffles their hand, graveyard, and all permanents they own into their library, then draws seven cards. Each player's life total "
    "becomes 7.": _sway_of_the_stars,
    "Each player loses a third of their life, then discards a third of the cards in their hand, then sacrifices a third of the creatures they control of "
    "their choice, then sacrifices a third of the lands they control of their choice. Round up each time.": _pox,
    "Return all Islands to their owners' hands. Each player sacrifices a Plains or a white permanent of their choice for each white permanent they control.":
        _omen_of_fire,
    "Choose target player. Return half the creatures they control to their owner's hand, rounded up.": _split_the_party,
    "Target opponent reveals their hand. You choose an artifact or creature card from it, then choose an artifact or creature card from their graveyard. "
    "Exile the chosen cards.": _dreams_of_steel_and_oil,
    "You destroy four lands you control, then target opponent destroys four lands they control. Then ~ deals 4 damage to each creature.": _burning_of_xinye,
    "Draw three cards. Then discard a card unless you waterbend {2}.": _waterbending_lesson,
    "Until end of turn, target nonland permanent loses all abilities and becomes your choice of a blue Frog creature with base power and toughness 1/1 or "
    "a blue Octopus creature with base power and toughness 4/4.": _mercurial_transformation,
    "Counter target loyalty ability of a planeswalker.": lambda: ([{"do": "counter", "who": "target"}],
                                                                 _key(ability="activated", zones=("stack",), extras=(LOYALTY,)), False),
    "Exile all creatures except those that share a creature type with a creature that convoked this spell, all artifacts, and all enchantments.":
        _everything_comes_to_dust,
    # 101.2: from now this turn, one more cast (this spell counts among the casts so far)
    "Add seven {R}. You can cast only one more spell this turn.": lambda: ([{"do": "add_mana", "sym": "R", "n": 7}, {"do": "one_more_spell100c"}], None, False),
    "Earthbend 2. When you do, up to one target creature you control fights target creature an opponent controls.": _earth_rumble,
    "Earthbend 3. Then each creature you control with power less than or equal to that land's power gains hexproof and indestructible until end of turn. "
    "You gain hexproof until end of turn.": _earthshape,
    "Target opponent sacrifices a creature of their choice. If they can't, they lose 2 life and you draw a card. Then repeat this process for an "
    "enchantment and a planeswalker.": _invoke_despair,
    "You win the game if you control a land of each basic land type and a creature of each color.": _coalition_victory,
    "~ deals 7 damage to each creature. If this spell was cast from exile, for each opponent, choose an artifact or land that player controls. Destroy "
    "the chosen permanents.": _ultimate_magic_meteor,
    "Each player may discard their hand and draw cards equal to the greatest mana value of a commander they own on the battlefield or in the command "
    "zone.": _imposing_grandeur,
    "You may choose new targets for target instant or sorcery spell. Then copy that spell. You may choose new targets for the copy.": _wild_ricochet,
    "Until end of turn, whenever a player casts an instant or sorcery spell, that player copies it and may choose new targets for the copy.": _bonus_round,
    "Draw three cards. Then if any player pays {2}, discard three cards.": _rhystic_scrying,
    "One or two target creatures each gain haste until end of turn. For each of those creatures, create a Monster Role token attached to it.": _become_brutes,
    "Draw cards equal to the mana value of target artifact or creature you control. An opponent gains control of that permanent.": _fateful_handoff,
    "Target creature gets +2/+2 until end of turn. If it's paired with a creature, that creature also gets +2/+2 until end of turn.": _joint_assault,
    "Choose target creature, planeswalker, or Vehicle. Mill two cards, then destroy the chosen permanent if its mana value is less than or equal to the "
    "number of cards in your graveyard.": _quag_feast,
    "Each player may exile any number of cards from their graveyard. Then each player loses 1 life for each card in their graveyard.": _grave_consequences,
    "Choose up to three target cards in graveyards. The owners of those cards shuffle them into their libraries. You gain 2 life.": _turn_the_earth,
    "Return target nonland permanent and each other nonland permanent with the same mana value as that permanent to their owners' hands.": _mists_of_lorien,
    "Destroy all enchantments or all nonwhite enchantments.": _essence_filter,
    "~ deals 2 damage to each attacking creature or ~ deals 2 damage to each blocking creature.": _lava_storm,
    "Target player exiles all cards with flashback from their graveyard.": _tombfire,
    "Tap target creature. Prevent all combat damage that would be dealt by that creature this turn. It doesn't untap during its controller's next two untap "
    "steps.": _telekinesis,
    "~ deals 4 damage to target player who attacked this turn and 4 damage to you.": _fire_and_brimstone,
    "Target player sacrifices an artifact and a land of their choice. ~ deals 2 damage to that player.": _structural_collapse,
    "~ deals 4 damage to target player or planeswalker. Then if that player or that planeswalker's controller has more life than you, return ~ to its "
    "owner's hand.": _pulse_of_the_forge,
    "Destroy target land. If that land was legendary, its controller sacrifices another land of their choice.": _feast_of_worms,
    "Destroy target creature. If its controller has more than four cards in hand, they exile cards from their hand equal to the difference.":
        _isildurs_fateful_strike,
    "Each player who controls the most creatures investigates. Then destroy all creatures.": _no_witnesses,
    "Mill seven cards. At the beginning of the next end step, exile seven cards from your graveyard.": _false_memories,
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
    if who == DUST:
        from app.rules import convoke_connive
        from app.rules.creature_types import CREATURE_TYPES
        from app.rules.triggers import _snapshot_card

        kin: set[str] = set()
        for cid, oid, _ in convoke_connive.contributors(plan, ctx):  # (each as it is now, or as it last existed: 608.2h)
            card = plan.state.cards.get(cid)
            snap = plan.rules.lki.get(oid)
            ch = plan.ch(card) if card is not None and plan.oid(card) == oid else _snapshot_card(plan, snap)[1] if snap is not None else None
            kin |= {t for t in ch.subtypes if t in CREATURE_TYPES} if ch is not None else set()
        return [c for c in selectors.candidates(plan, selectors.from_key(_sel("creature")), ctx["controller"], ctx.get("source_card"))
                if not kin & plan.ch(plan.state.cards[c]).subtypes]
    if who.startswith(PARTNER):
        from app.rules import pairing

        oids = {pairing.partner_oid(plan, plan.state.cards[c]) for c in effects._cards(plan, ctx, who[len(PARTNER):])}
        return [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) in oids]
    if who.startswith(SAME_MV):
        ref, _, key = who[len(SAME_MV):].partition("|")
        named = effects._cards(plan, ctx, ref)
        mvs = {plan.ch(plan.state.cards[c]).mana_value for c in named}
        return [*named, *(c for c in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], ctx.get("source_card"))
                          if c not in named and plan.ch(plan.state.cards[c]).mana_value in mvs)]
    ref, _, key = who[len(ATTACHED):].partition("|")
    hosts = set(effects._cards(plan, ctx, ref))
    return [c for c in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], ctx.get("source_card"))
            if plan.state.cards[c].attached_to in hosts]


def extra_ok(plan: Any, extra: str, card: Any, ch: Any, you: str, source: str | None, attacker: str | None) -> bool:
    from app.rules import selectors

    if extra == LOYALTY:  # (the stack object carries the text after the cost: 602.2a; ponytail: matched by that text against the source's loyalty abilities)
        src = plan.state.cards.get(card.ability.source_id or "") if card.ability is not None else None
        sch = plan.ch(src) if src is not None else None
        return sch is not None and "Planeswalker" in sch.types and any(
            a.kind == "loyalty" and a.text.split(":", 1)[-1].strip()[:500] == card.ability.text for a in sch.abilities)

    return not selectors.matches(plan, selectors.from_key(extra[len(NOT_SEL):]), card, ch, you, source, attacker)


def player_extra_ok(plan: Any, extra: str, pid: str, you: str) -> bool:
    from app.rules import selectors

    if extra == ATTACKED:
        from app.rules.history import log_for

        return pid in log_for(plan).attacked
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
    if e.get("distinct") and len(e["sels"]) == 2:  # -- multi (wave 100N) -- one of each if able (To the Slaughter's 2016-04-08 ruling): the only
        # permanent of the second kind can't be taken as the first while another of the first kind is there
        from app.rules import selectors

        kinds = list(e["sels"])
        first = kinds[0]
        for i, (p, _) in enumerate(turns[::2]):
            a, b = (effects._controlled(plan, k, p, ctx.get("source_card")) for k in kinds)
            if len(b) == 1 and b[0] in a and len(a) > 1:
                sel = selectors.from_key(first)
                key = selectors.replace(sel, extras=(*sel.extras, f"not_oid:{plan.oid(b[0])}")).key()
                turns[2 * i] = (p, key)
                e = {**e, "sels": [*e["sels"], key], "labels": [*e["labels"], e["labels"][0]]}
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


def if_more_life(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"Then if that player … has more life than you, [the next ``skip`` instructions]" (608.2c: judged as it is reached)."""
    from app.rules import effects

    mine = plan.state.players[ctx["controller"]].life
    if not any(plan.state.players[p].life > mine for p in effects._players(plan, ctx, e["who"])):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


def hand_excess(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"They exile cards from their hand equal to the difference": each named player with more than ``over`` cards in hand exiles the excess, their choice."""
    from app.rules import effects

    at = ctx["next"]
    for pid in effects._players(plan, ctx, e["who"]):
        if (extra := len(plan.state.zones.get(f"{pid}:hand", [])) - int(e["over"])) > 0:
            ctx["effects"][at:at] = [{"do": "discard", "who": f"player:{pid}", "n": extra, "to": "exile"}]
            at += 1
    return True


def if_mv_upto_graveyard(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"if its mana value is less than or equal to the number of cards in your graveyard": else the next ``skip`` instructions don't happen."""
    from app.rules import effects

    n = len(plan.state.zones.get(f"{ctx['controller']}:graveyard", []))
    if not any(plan.ch(plan.state.cards[c]).mana_value <= n for c in effects._cards(plan, ctx, e["who"])):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


def each(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"For each of those creatures, [instruction] … it": the instruction ``then`` once for each object, in order, each about its own object."""
    from app.rules import context, effects

    at = ctx["next"]
    for i, cid in enumerate(effects._cards(plan, ctx, e["who"])):
        context.bind_objects(plan, ctx, f"each100c_{at}_{i}", [cid])
        ctx["effects"][at + i:at + i] = [{**e["then"], "who": f"ref:each100c_{at}_{i}"}]
    return True


def power_cap(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"each creature you control with power less than or equal to that land's power …": the bound land's power now (as it last existed if gone, 608.2h)."""
    from dataclasses import replace

    from app.rules import context, sba, selectors

    seen = context.infos(plan, ctx, e["of"].removeprefix("ref:"))
    if seen:
        then = e["then"]
        cap = (("power", "<=", sba.power(*seen[0]) or 0),)
        ctx["effects"][ctx["next"]:ctx["next"]] = [{**then, "who": replace(selectors.from_key(then["who"]), compare=cap).key()}]
    return True


def if_coalition(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"if you control a land of each basic land type and a creature of each color" (305.6, 105.1): one permanent may count for several."""
    mine = [plan.ch(c) for c in plan.state.cards.values() if c.zone == f"{ctx['controller']}:battlefield" and c.controller == ctx["controller"]]
    ok = all(any(ch.is_land and t in ch.subtypes for ch in mine) for t in ("Plains", "Island", "Swamp", "Mountain", "Forest")) \
        and all(any(ch.is_creature and c in ch.colors for ch in mine) for c in "WUBRG")
    if not ok:
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


def one_more_spell(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"You can cast only one more spell this turn": a cast limit of this turn's casts so far plus one (cast_limits ``max``)."""
    import secrets

    from app.rules.cast_limits import _cast_this_turn

    pid, label = ctx["controller"], ctx.get("name") or "An effect"
    plan.rules.cast_limits.append({"id": secrets.token_hex(4), "player": pid, "controller": pid, "until": "turn", "turn": plan.state.turn.number,
                                   "filter": None, "from": None, "act": None, "label": label, "max": _cast_this_turn(plan.state, pid, None) + 1})
    plan.note(f"{plan.name(pid)} can cast only one more spell this turn ({label})", actor=pid)
    return True


def _third_up(n: int, div: int) -> int:
    return -(-max(0, n) // div)


def thirds(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"Each player loses a third of their life" / "discards a third of the cards in their hand", rounded up: each player's own number, all
    read now (608.2h), one loss / one discard (lose_life, discard ``counts``)."""
    who = [p for p in plan.apnap() if p in plan.live()]
    have = {p: plan.state.players[p].life if e["what"] == "life" else len(plan.state.zones.get(f"{p}:hand", [])) for p in who}
    counts = {p: _third_up(n, 3) for p, n in have.items()}
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "lose_life" if e["what"] == "life" else "discard", "who": "each_player", "n": 0, "counts": counts}]
    return True


def edict_each(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Each player sacrifices their own number of permanents (those matching ``count`` they control, divided by ``div``, rounded up): one choice at
    a time in turn order, never the same permanent twice (101.4), then all sacrificed at once (701.21a; effects._choose_next resumes as an edict)."""
    from app.rules import effects

    turns = [(p, e["sel"]) for p in plan.apnap() if p in plan.live()
             for _ in range(_third_up(len(effects._controlled(plan, e["count"], p, ctx.get("source_card"))), int(e["div"])))]
    return effects._choose_next(plan, ctx, {**e, "n": 1, "distinct": True}, turns, [], "edict")


def type_pump(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"+1/+1 for each supertype, card type, and subtype it has": counted once as it resolves (608.2h; 205.2-205.4), then the pump."""
    from app.rules import effects

    for cid in effects._cards(plan, ctx, e["who"])[:1]:
        ch = plan.ch(plan.state.cards[cid])
        n = len(ch.supertypes) + len(ch.types) + len(ch.subtypes)
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "pump", "who": e["who"], "p": n, "t": n}]
    return True


def unsuspect(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """701.60: the named creatures stop being suspected (the "Suspected" marker goes with it)."""
    from app.rules import effects

    for cid in effects._cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        if (oid := plan.oid(card)) in plan.rules.suspected:
            plan.rules.suspected.remove(oid)
            for marker in [m for m in card.effects if m.name == "Suspected"]:
                plan.do({"type": "remove_effect", "card_ids": [cid], "effect_id": marker.id}, actor=ctx["controller"])
    return True


def aura_damage(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"~ deals N damage to each creature for each Aura attached to that creature": one damage instruction per creature, joined (with_next)."""
    from app.rules import context, selectors

    you, src = ctx["controller"], ctx.get("source_card")
    auras = [plan.state.cards[c].attached_to for c in selectors.candidates(plan, selectors.from_key(_sel("Aura")), you, src)]
    hits = [(c, auras.count(c)) for c in selectors.candidates(plan, selectors.from_key(_sel("creature")), you, src) if c in auras]
    at = ctx["next"]
    for i, (cid, k) in enumerate(hits):
        context.bind_objects(plan, ctx, f"baki100c_{at}_{i}", [cid])
        ctx["effects"][at + i:at + i] = [{"do": "damage", "who": f"ref:baki100c_{at}_{i}", "n": int(e["n"]) * k, "with_next": i < len(hits) - 1}]
    return True


def clash_freeze(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"creatures that player controls don't untap during the player's next untap step": the opponent clashed with (clash.py)."""
    if (pid := ctx.get("clash_opponent")) in plan.live():
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "stay_tapped", "sel": e["sel"], "who": f"player:{pid}"}]
    return True


PRIMITIVES = {"clash_freeze100c": clash_freeze, "aura_damage100c": aura_damage, "unsuspect100c": unsuspect, "type_pump100c": type_pump, "thirds100c": thirds, "edict_each100c": edict_each, "one_more_spell100c": one_more_spell, "power_cap100c": power_cap, "if_coalition100c": if_coalition, "if_mv_upto_graveyard100c": if_mv_upto_graveyard, "each100c": each, "if_more_life100c": if_more_life, "hand_excess100c": hand_excess, "lose_all_counters100c": lose_all_counters, "edict_kinds100c": edict_kinds, "draw_for_revealed100c": draw_for_revealed,
              "draw_for_controllers100c": draw_for_controllers}
