"""Wave 4G: kicked spells and "If …, … instead" clauses (app/rules/kicked_instead.py).

* 702.33d-e: "If this spell was kicked, …" reads the kicked status announced as the spell was cast (601.2b);
  "… instead" replaces the sentence before it. 608.2c: an elliptical alternative ("it deals 4 damage instead",
  "create four of those tokens instead", "investigate twice instead") is the replaced instruction with another
  amount.
* 601.2c / 702.33g: targets that depend on the kicker. Kicked-only targets are chosen only if the spell is kicked;
  an "instead" alternative with targets of its own replaces the replaced sentence's targets ("a spell may require
  alternative targets only if an alternative or additional cost was chosen for it"); the others are cast "as
  though it did not require those targets" (groups of zero targets, never asked).
* 605.3a / 608.2c: a mana ability's "If you control …, add … instead" checked as it resolves.
* "If C1, X. If C2, Y instead." with C2 only true when C1 is (Dega Sanctuary).
* 205.3j: planeswalker types in selectors ("If you control a Jace planeswalker, …").

Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from app.rules.casting import mana_abilities
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, mana_pool, zone
from tests.test_rules_conditionals import creature, life, on_field, to_hand, to_turn, until_asked
from tests.test_rules_effects import mana, replay_matches


def _spell(name, cost, cmc, types, text, colors, identity=None, number="X0"):
    return card(name, set_code="tst", number=number, mana_cost=cost, cmc=cmc, type_line=types, oracle_text=text,
                colors=colors, color_identity=identity or colors, keywords=["Kicker"] if "Kicker" in text else [])


# Real Oracle wording (the local card database, current).
EXTRA = [
    _spell("Burst Lightning", "{R}", 1.0, "Instant", "Kicker {4} (You may pay an additional {4} as you cast this spell.)\n"
           "Burst Lightning deals 2 damage to any target. If this spell was kicked, it deals 4 damage instead.", ["R"],
           number="X701"),
    _spell("Saproling Migration", "{1}{G}", 2.0, "Sorcery", "Kicker {4} (You may pay an additional {4} as you cast this "
           "spell.)\nCreate two 1/1 green Saproling creature tokens. If this spell was kicked, create four of those tokens "
           "instead.", ["G"], number="X702"),
    _spell("Tear Asunder", "{1}{G}", 2.0, "Instant", "Kicker {1}{B} (You may pay an additional {1}{B} as you cast this "
           "spell.)\nExile target artifact or enchantment. If this spell was kicked, exile target nonland permanent "
           "instead.", ["G"], ["B", "G"], number="X703"),
    _spell("Rite of Replication", "{2}{U}{U}", 4.0, "Sorcery", "Kicker {5} (You may pay an additional {5} as you cast "
           "this spell.)\nCreate a token that's a copy of target creature. If this spell was kicked, create five of those "
           "tokens instead.", ["U"], number="X704"),
    _spell("Jilt", "{1}{U}", 2.0, "Instant", "Kicker {1}{R} (You may pay an additional {1}{R} as you cast this spell.)\n"
           "Return target creature to its owner's hand. If this spell was kicked, it deals 2 damage to another target "
           "creature.", ["U"], ["R", "U"], number="X705"),
    _spell("Blood Beckoning", "{B}", 1.0, "Sorcery", "Kicker {3} (You may pay an additional {3} as you cast this spell.)\n"
           "Return target creature card from your graveyard to your hand. If this spell was kicked, instead return two "
           "target creature cards from your graveyard to your hand.", ["B"], number="X706"),
    _spell("Heroic Charge", "{2}{W}{W}", 4.0, "Instant", "Kicker {1}{R} (You may pay an additional {1}{R} as you cast "
           "this spell.)\nCreatures you control get +2/+1 until end of turn. If this spell was kicked, those creatures "
           "also gain trample until end of turn.", ["W"], ["R", "W"], number="X707"),
    _spell("Leafkin Druid", "{1}{G}", 2.0, "Creature — Elemental Druid",
           "{T}: Add {G}. If you control four or more creatures, add {G}{G} instead.", ["G"], number="X708"),
    _spell("Ilysian Caryatid", "{1}{G}", 2.0, "Creature — Plant", "{T}: Add one mana of any color. If you control a "
           "creature with power 4 or greater, add two mana of any one color instead.", ["G"], number="X709"),
    _spell("Goldnight Castigator", "{2}{R}{R}", 4.0, "Creature — Angel", "Flying, haste\nIf a source would deal damage to "
           "you, it deals double that damage to you instead.\nIf a source would deal damage to this creature, it deals "
           "double that damage to this creature instead.", ["R"], number="X710"),
    _spell("Jace's Triumph", "{2}{U}", 3.0, "Sorcery", "Draw two cards. If you control a Jace planeswalker, draw three "
           "cards instead.", ["U"], number="X711"),
    _spell("Jace Beleren", "{1}{U}{U}", 3.0, "Legendary Planeswalker — Jace", "+2: Each player draws a card.\n−1: Target "
           "player draws a card.\n−10: Target player mills twenty cards.", ["U"], number="X712"),
    _spell("Dega Sanctuary", "{2}{W}", 3.0, "Enchantment", "At the beginning of your upkeep, if you control a black or red "
           "permanent, you gain 2 life. If you control a black permanent and a red permanent, you gain 4 life instead.",
           ["W"], number="X713"),
    _spell("Court of Ire", "{3}{R}{R}", 5.0, "Enchantment", "When this enchantment enters, you become the monarch.\nAt the "
           "beginning of your upkeep, this enchantment deals 2 damage to any target. If you're the monarch, it deals 7 "
           "damage instead.", ["R"], number="X714"),
    _spell("Reverberate", "{R}{R}", 2.0, "Instant", "Copy target instant or sorcery spell. You may choose new targets for "
           "the copy.", ["R"], number="X715"),
    _spell("Fight with Fire", "{2}{R}", 3.0, "Sorcery", "Kicker {5}{R} (You may pay an additional {5}{R} as you cast this "
           "spell.)\nFight with Fire deals 5 damage to target creature. If this spell was kicked, it deals 10 damage divided "
           "as you choose among any number of targets instead. (Those targets can include players and planeswalkers.)",
           ["R"], number="X716"),
    _spell("Court of Ardenvale", "{2}{W}{W}", 4.0, "Enchantment", "When this enchantment enters, you become the monarch.\n"
           "At the beginning of your upkeep, return target permanent card with mana value 3 or less from your graveyard to "
           "your hand. If you're the monarch, return that permanent card to the battlefield instead.", ["W"],
           number="X717"),
]
# Printed P/T is needed for state-based actions (CR 208.5, 704.5f).
for name, power, toughness in (("Leafkin Druid", "0", "3"), ("Ilysian Caryatid", "1", "1"),
                                ("Goldnight Castigator", "4", "9")):
    next(c for c in EXTRA if c["name"] == name).update(power=power, toughness=toughness)
EXTRA[11]["loyalty"] = "3"
FULL = ["Burst Lightning", "Saproling Migration", "Tear Asunder", "Rite of Replication", "Jilt", "Blood Beckoning",
        "Heroic Charge", "Leafkin Druid", "Ilysian Caryatid", "Goldnight Castigator", "Jace's Triumph", "Dega Sanctuary",
        "Court of Ire", "Fight with Fire", "Court of Ardenvale"]


@pytest.fixture()
def card_db(settings):
    """The fixture cards plus this module's real-Oracle cards."""
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def roundtrip(s):
    replay_matches(s)  # (the recorded history rebuilds the same table)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)  # a save, loaded
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def settle(s):
    assert until_asked(s) is None


def tokens(s, name, pid="p1"):
    return [c for c in zone(s.state, pid, "battlefield") if s.state.cards[c].name == name]


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


# -- the wording ------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_wordings():
    burst = scripts.parse_effects("~ deals 2 damage to any target. If this spell was kicked, it deals 4 damage instead.")
    assert burst is not None and burst[0] == [
        {"do": "kicked_gate", "kicked": False, "n": 1}, {"do": "damage", "who": "target", "n": 2},
        {"do": "kicked_gate", "kicked": True, "n": 1}, {"do": "damage", "who": "target", "n": 4}]
    tear = scripts.parse_effects("Exile target artifact or enchantment. If this spell was kicked, exile target nonland "
                                 "permanent instead.")
    assert tear is not None and [g.get("kicked") for g in tear[1]] == [False, True]
    jilt = scripts.parse_effects("Return target creature to its owner's hand. If this spell was kicked, it deals 2 damage "
                                 "to another target creature.")
    assert jilt is not None and "kicked" not in jilt[1][0] and jilt[1][1]["kicked"] is True
    assert jilt[1][1]["distinct_from"] == [0]
    clues = scripts.parse_effects("Investigate. If this spell was cast from a graveyard, investigate twice instead.")
    assert clues is not None and [e["do"] for e in clues[0]].count("create_token") == 3  # (twice: two investigations)


@pytest.mark.parametrize("text", [
    # an alternative naming the target of a sentence it replaces, with targets of its own: what would "it" be?
    "Exile target artifact. If this spell was kicked, exile target creature and its controller loses 2 life instead.",
    # a restatement of more than one instruction
    "Draw a card and you gain 2 life. If this spell was kicked, create four of those tokens instead.",
    # "those tokens" with no token made before
    "Draw a card. If this spell was kicked, create four of those tokens instead.",
    # "that land": the trigger's object, not the damage's target (Akoum Hellkite)
    # "If C1, X. If C2, Y instead." where C2 doesn't imply C1 (whether Y needs C1 isn't read)
    "If you control a Forest, you gain 2 life. If you control an Island, you gain 4 life instead.",
])
def test_refused(text):
    assert scripts.parse_effects(text) is None


def test_akoum_hellkite_stays_manual():
    """Akoum Hellkite: "If that land is a Mountain, this creature deals 2 damage instead." — "that land" is the land that
    entered, not the damage's target: the restatement isn't read with a pronoun naming the trigger's object."""
    body = "~ deals 1 damage to any target. If that land is a Mountain, ~ deals 2 damage instead."
    assert scripts.parse_effects(body, "event") is None


def test_kicker_targets_only_on_spells(cards):
    """702.33g is about a spell's targets: a triggered ability's "If it was kicked, destroy target creature" stays
    manual (its targets aren't filtered as it's put on the stack)."""
    fake = _spell("Fake Kicked Elf", "{G}", 1.0, "Creature — Elf", "Kicker {1}\nWhen this creature enters, draw a card. "
                  "If it was kicked, destroy target creature.", ["G"], number="X799")
    line = next(f for f in coverage.of_card_data({**fake, "faces": []}).features if f.id == "text:1")
    assert not line.supported


# -- elliptical "instead" (608.2c) ------------------------------------------------------------------------
@pytest.mark.parametrize(("kicked", "damage"), [(0, 2), (1, 4)])
def test_burst_lightning(cards, kicked, damage):
    s = build(cards, ("Burst Lightning",))
    bolt = to_hand(s, "Burst Lightning")
    mana(s, R=1, C=4 * kicked)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], kicker=kicked)
    settle(s)
    assert life(s, "p2") == 40 - damage
    roundtrip(s)


@pytest.mark.parametrize(("kicked", "made"), [(0, 2), (1, 4)])
def test_saproling_migration(cards, kicked, made):
    s = build(cards, ("Saproling Migration",))
    spell = to_hand(s, "Saproling Migration")
    mana(s, G=1, C=1 + 4 * kicked)
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=kicked)
    settle(s)
    assert len(tokens(s, "Saproling")) == made
    roundtrip(s)


def test_rite_of_replication_kicked_makes_five_copies(cards):
    s = build(cards, ("Rite of Replication",))
    bear = creature(s, "p2", "Bear", "2/2")
    spell = to_hand(s, "Rite of Replication")
    mana(s, U=2, C=7)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], kicker=1)
    settle(s)
    assert len(tokens(s, "Bear")) == 5
    roundtrip(s)


# -- targets tied to the kicker (601.2c, 702.33g) ---------------------------------------------------------
def test_tear_asunder_unkicked_targets_only_artifacts_and_enchantments(cards):
    s = build(cards, ("Tear Asunder",))
    bear = creature(s, "p2", "Bear", "2/2")
    relic = creature(s, "p2", "Relic", "1/1", type_line="Token Artifact")
    spell = to_hand(s, "Tear Asunder")
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], target_counts=[1, 0])
    act(s, "p1", type="cast_spell", card_id=spell.id)  # asked: only the unkicked group (601.2c)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {relic.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[relic.id])
    settle(s)
    assert relic.id not in s.state.cards or s.state.cards[relic.id].zone != "p2:battlefield"
    assert s.state.cards[bear.id].zone == "p2:battlefield"
    roundtrip(s)


def test_tear_asunder_kicked_exiles_a_creature(cards):
    s = build(cards, ("Tear Asunder",))
    bear = creature(s, "p2", "Bear", "2/2")
    creature(s, "p2", "Relic", "1/1", type_line="Token Artifact")
    spell = to_hand(s, "Tear Asunder")
    mana(s, G=1, B=1, C=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1)
    d = s.state.rules.decision  # (the artifact-or-enchantment group isn't asked: the spell is kicked)
    assert d is not None and bear.id in {o.id for o in d.options} and "group 2 of 2" in d.prompt
    roundtrip(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bear.id])
    entry = next(iter(s.state.rules.stack.values()))
    assert entry.kicked == 1 and [len(g) for g in entry.groups] == [0, 1]
    settle(s)
    assert bear.id not in zone(s.state, "p2", "battlefield")
    roundtrip(s)


def test_tear_asunder_kicked_with_explicit_counts(cards):
    s = build(cards, ("Tear Asunder",))
    bear = creature(s, "p2", "Bear", "2/2")
    spell = to_hand(s, "Tear Asunder")
    mana(s, G=1, B=1, C=2)
    with pytest.raises(ActionError):  # (the unkicked group takes no target when kicked)
        act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1, targets=[bear.id, bear.id], target_counts=[1, 1])
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1, targets=[bear.id], target_counts=[0, 1])
    settle(s)
    assert bear.id not in zone(s.state, "p2", "battlefield")
    roundtrip(s)


@pytest.mark.parametrize("kicked", [0, 1])
def test_jilt(cards, kicked):
    s = build(cards, ("Jilt",))
    bear = creature(s, "p2", "Bear", "2/2")
    ogre = creature(s, "p2", "Ogre", "3/3")
    spell = to_hand(s, "Jilt")
    mana(s, U=1, R=kicked, C=1 + kicked)
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=kicked, targets=[bear.id], target_counts=[1])
    if kicked:  # 702.33g: the kicked-only "another target creature" (115.3: not the bounced one)
        d = s.state.rules.decision
        assert d is not None and {o.id for o in d.options} == {ogre.id}
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[ogre.id])
    else:
        assert s.state.rules.decision is None  # (cast as though it didn't require that target)
    settle(s)
    assert bear.id not in zone(s.state, "p2", "battlefield")
    assert s.state.cards[ogre.id].damage == 2 * kicked
    roundtrip(s)


def test_blood_beckoning_kicked_returns_two(cards):
    s = build(cards, ("Blood Beckoning", "Grizzly Bears", "Llanowar Elves"))
    bears, elves = (next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1")
                    for n in ("Grizzly Bears", "Llanowar Elves"))
    act(s, "p1", type="move", card_ids=[bears.id, elves.id], to={"zone": "graveyard"})
    spell = to_hand(s, "Blood Beckoning")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1, targets=[bears.id, elves.id], target_counts=[0, 2])
    settle(s)
    hand = zone(s.state, "p1", "hand")
    assert bears.id in hand and elves.id in hand
    roundtrip(s)


def test_kicked_spell_copy_keeps_the_kicked_groups(cards):
    """707.10: a copy keeps the kicked status and the targets' shape: a new target for the kicked group only
    (707.10c), none for the unkicked one."""
    from app.rules import copying

    s = build(cards, ("Tear Asunder", "Reverberate"))
    bear = creature(s, "p2", "Bear", "2/2")
    ogre = creature(s, "p2", "Ogre", "3/3")
    tear, rev = to_hand(s, "Tear Asunder"), to_hand(s, "Reverberate")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, G=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=tear.id, kicker=1, targets=[bear.id], target_counts=[0, 1])
    entry = next(iter(s.state.rules.stack.values()))
    assert [g.get("max") for g in entry.group_specs] == [0, 1]
    assert copying.positions(entry) == [("group", 1, 0)]
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[tear.id])
    for _ in range(12):  # (Reverberate resolves; its copy asks for the new target)
        d = s.state.rules.decision
        if d is not None:
            ids = {o.id for o in d.options}
            act(s, d.player, type="choose", decision_id=d.id,
                option_ids=[ogre.id] if ogre.id in ids else [o.id for o in d.options][:max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    battlefield = zone(s.state, "p2", "battlefield")
    assert bear.id not in battlefield and ogre.id not in battlefield
    roundtrip(s)


def test_heroic_charge_kicked_grants_trample_to_those_creatures_only(cards):
    s = build(cards, ("Heroic Charge",))
    bear = creature(s, "p1", "Bear", "2/2")
    spell = to_hand(s, "Heroic Charge")
    mana(s, W=2, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1)
    settle(s)
    late = creature(s, "p1", "Late", "1/1")
    assert "trample" in chars(s, bear).keywords and chars(s, bear).pt == (4, 3)
    assert "trample" not in chars(s, late).keywords  # (611.2c: the creatures it affected as it resolved)
    roundtrip(s)


# -- mana abilities (605.3a) -------------------------------------------------------------------------------
def test_leafkin_druid_adds_two_with_four_creatures(cards):
    s = build(cards, ("Leafkin Druid",))
    druid = on_field(s, "Leafkin Druid")
    for i in range(2):
        creature(s, "p1", f"Bear {i}")
    assert dict(mana_abilities(s.state, s.state.cards[druid.id], s.cards))[0].options == (("G",),)
    creature(s, "p1", "Bear 2")  # (four creatures, the Druid among them)
    assert dict(mana_abilities(s.state, s.state.cards[druid.id], s.cards))[0].options == (("G", "G"),)
    to_turn(s, 3)
    act(s, "p1", type="activate_ability", card_id=druid.id, ability=0)
    assert mana_pool(s) == {"G": 2}
    roundtrip(s)


def test_ilysian_caryatid_needs_a_big_creature(cards):
    s = build(cards, ("Ilysian Caryatid",))
    caryatid = on_field(s, "Ilysian Caryatid")
    creature(s, "p1", "Small", "3/3")
    creature(s, "p2", "Theirs", "5/5")  # (an opponent's doesn't count)
    assert len(dict(mana_abilities(s.state, s.state.cards[caryatid.id], s.cards))[0].options[0]) == 1
    creature(s, "p1", "Big", "4/1")
    options = dict(mana_abilities(s.state, s.state.cards[caryatid.id], s.cards))[0].options
    assert set(options) == {(c, c) for c in "WUBRG"}
    to_turn(s, 3)
    act(s, "p1", type="activate_ability", card_id=caryatid.id, ability=0)
    d = s.state.rules.decision  # (which color: two of one color)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[str(list(options).index(("R", "R")))])
    assert mana_pool(s) == {"R": 2}
    roundtrip(s)


# -- other "instead" wordings ------------------------------------------------------------------------------
def test_goldnight_castigator_doubles_damage_to_you(cards):
    s = build(cards, ("Goldnight Castigator", "Burst Lightning"))
    on_field(s, "Goldnight Castigator")
    bolt = to_hand(s, "Burst Lightning")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p1"])
    settle(s)
    assert life(s) == 36
    roundtrip(s)


@pytest.mark.parametrize(("walker", "drawn"), [("Jace Beleren", 3), ("Gideon Jura", 2), (None, 2)])
def test_jaces_triumph(cards, walker, drawn):
    s = build(cards, tuple(n for n in ("Jace's Triumph", walker) if n))
    if walker:
        pw = on_field(s, walker)
        act(s, "p1", type="counter", card_ids=[pw.id], kind="loyalty", delta=3)  # (put onto the battlefield by hand)
    spell = to_hand(s, "Jace's Triumph")
    before = len(zone(s.state, "p1", "hand"))
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    assert len(zone(s.state, "p1", "hand")) == before - 1 + drawn
    roundtrip(s)


@pytest.mark.parametrize(("colors", "gained"), [((), 0), (("B",), 2), (("B", "R"), 4)])
def test_dega_sanctuary(cards, colors, gained):
    s = build(cards, ("Dega Sanctuary",))
    on_field(s, "Dega Sanctuary")
    for c in colors:
        act(s, "p1", type="create_token", player="p1",
            token={"name": f"Tok {c}", "type_line": "Token Creature — Test", "power": "1", "toughness": "1", "colors": [c]})
    to_turn(s, 3, phase="main1")
    assert life(s) == 40 + gained
    roundtrip(s)


@pytest.mark.parametrize(("monarch", "damage"), [(True, 7), (False, 2)])
def test_court_of_ire(cards, monarch, damage):
    s = build(cards, ("Court of Ire",))
    if monarch:  # (cast: its enters trigger makes Alice the monarch)
        court = to_hand(s, "Court of Ire")
        mana(s, R=2, C=3)
        act(s, "p1", type="cast_spell", card_id=court.id)
        settle(s)
    else:  # (put onto the battlefield by hand: no monarch)
        on_field(s, "Court of Ire")
    assert s.state.table.monarch == ("p1" if monarch else None)
    to_turn(s, 3, phase="upkeep")
    d = until_asked(s)
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    assert life(s, "p2") == 40 - damage
    roundtrip(s)


@pytest.mark.parametrize("kicked", [0, 1])
def test_fight_with_fire(cards, kicked):
    """Kicked: 10 damage divided among any number of targets (601.2d), the creature target not required (601.2c)."""
    s = build(cards, ("Fight with Fire",))
    ogre = creature(s, "p2", "Ogre", "7/7")
    spell = to_hand(s, "Fight with Fire")
    mana(s, R=1 + kicked, C=2 + 5 * kicked)
    if kicked:
        act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1, targets=[ogre.id, "p2"], target_counts=[0, 2],
            division=[6, 4])
    else:
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ogre.id], target_counts=[1, 0])
    settle(s)
    if kicked:
        assert s.state.cards[ogre.id].damage == 6 and life(s, "p2") == 36
    else:
        assert s.state.cards[ogre.id].damage == 5 and life(s, "p2") == 40
    roundtrip(s)


@pytest.mark.parametrize("monarch", [True, False])
def test_court_of_ardenvale(cards, monarch):
    """"return that permanent card to the battlefield instead": the card the replaced instruction targeted (608.2c)."""
    s = build(cards, ("Court of Ardenvale", "Grizzly Bears"))
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    if monarch:
        court = to_hand(s, "Court of Ardenvale")
        mana(s, W=2, C=2)
        act(s, "p1", type="cast_spell", card_id=court.id)
        settle(s)
    else:
        on_field(s, "Court of Ardenvale")
    to_turn(s, 3, phase="upkeep")
    d = until_asked(s)
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == ("p1:battlefield" if monarch else "p1:hand")
    roundtrip(s)
