"""Wave 6A: effect bodies acting on permanents and cards.

* "[Object] doesn't untap during its controller's / your next untap step" (502.3; app/rules/next_untap.py): a
  one-shot effect on named objects; "its controller" is read when an untap step comes, and the effect ends
  with that untap step whether or not the permanent was tapped (611.2c: it modifies the rules, not the
  object). Mass wordings stay manual.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch
from tests.test_rules_conditionals import (
    attack,
    creature,
    on_field,
    pick,
    settle,
    to_hand,
    to_turn,
    until_asked,
)
from tests.test_rules_effects import mana
from tests.test_rules_wave4h_activation_costs import build, roundtrip

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Frost Breath', set_code="tst", number="A01", mana_cost='{2}{U}', cmc=3.0, type_line='Instant', oracle_text="Tap up to two target creatures. Those creatures don't untap during their controller's next untap step.", colors=['U'], color_identity=['U']),  # noqa: E501
    card("Kefnet's Monument", set_code="tst", number="A02", mana_cost='{3}', cmc=3.0, type_line='Legendary Artifact', oracle_text="Blue creature spells you cast cost {1} less to cast.\nWhenever you cast a creature spell, target creature an opponent controls doesn't untap during its controller's next untap step."),  # noqa: E501
    card('Arbalest Elite', set_code="tst", number="A03", mana_cost='{2}{W}{W}', cmc=4.0, type_line='Creature — Human Archer', oracle_text="{2}{W}, {T}: This creature deals 3 damage to target attacking or blocking creature. This creature doesn't untap during your next untap step.", power='2', toughness='3', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Apes of Rath', set_code="tst", number="A04", mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Ape', oracle_text="Whenever this creature attacks, it doesn't untap during its controller's next untap step.", power='5', toughness='4', colors=['G'], color_identity=['G']),  # noqa: E501
    card("Ojutai's Breath", set_code="tst", number="A05", mana_cost='{2}{U}', cmc=3.0, type_line='Instant', oracle_text="Tap target creature. It doesn't untap during its controller's next untap step.\nRebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you may cast this card from exile without paying its mana cost.)", colors=['U'], color_identity=['U'], keywords=['Rebound']),  # noqa: E501
    card('Sleep', set_code="tst", number="A06", mana_cost='{2}{U}{U}', cmc=4.0, type_line='Sorcery', oracle_text="Tap all creatures target player controls. Those creatures don't untap during that player's next untap step.", colors=['U'], color_identity=['U']),  # noqa: E501
    card("Bontu's Last Reckoning", set_code="tst", number="A07", mana_cost='{1}{B}{B}', cmc=3.0, type_line='Sorcery', oracle_text="Destroy all creatures. Lands you control don't untap during your next untap step.", colors=['B'], color_identity=['B']),  # noqa: E501
    card('Sneak Attack', set_code="tst", number="A09", mana_cost='{3}{R}', cmc=4.0, type_line='Enchantment', oracle_text='{R}: You may put a creature card from your hand onto the battlefield. That creature gains haste. Sacrifice the creature at the beginning of the next end step.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Arms Race', set_code="tst", number="A10", mana_cost='{3}{R}', cmc=4.0, type_line='Enchantment', oracle_text='{3}{R}: You may put an artifact card from your hand onto the battlefield. That artifact gains haste. Sacrifice it at the beginning of the next end step.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Kor Skyfisher', set_code="tst", number="B01", mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Kor Soldier', oracle_text="Flying\nWhen this creature enters, return a permanent you control to its owner's hand.", power='2', toughness='3', colors=['W'], color_identity=['W'], keywords=['Flying']),  # noqa: E501
    card('Ambush Krotiq', set_code="tst", number="B02", mana_cost='{5}{G}', cmc=6.0, type_line='Creature — Insect', oracle_text="Trample\nWhen this creature enters, return another creature you control to its owner's hand.", power='5', toughness='5', colors=['G'], color_identity=['G'], keywords=['Trample']),  # noqa: E501
    card('Curfew', set_code="tst", number="B03", mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text="Each player returns a creature they control to its owner's hand.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Peel from Reality', set_code="tst", number="B04", mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text="Return target creature you control and target creature you don't control to their owners' hands.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Reduce to Dreams', set_code="tst", number="B05", mana_cost='{3}{U}{U}', cmc=5.0, type_line='Sorcery', oracle_text="Return all artifacts and enchantments to their owners' hands.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Whelming Wave', set_code="tst", number="B06", mana_cost='{2}{U}{U}', cmc=4.0, type_line='Sorcery', oracle_text="Return all creatures to their owners' hands except for Krakens, Leviathans, Octopuses, and Serpents.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Hill Giant', set_code="tst", number="B07", mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Giant', oracle_text='', power='3', toughness='3', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Ornithopter', set_code="tst", number="B08", mana_cost='{0}', cmc=0.0, type_line='Artifact Creature — Thopter', oracle_text='Flying', power='0', toughness='2', keywords=['Flying']),  # noqa: E501
    card('Gingerbrute', set_code="tst", number="C01", mana_cost='{1}', cmc=1.0, type_line='Artifact Creature — Food Golem', oracle_text="Haste (This creature can attack and {T} as soon as it comes under your control.)\n{1}: This creature can't be blocked this turn except by creatures with haste.\n{2}, {T}, Sacrifice this creature: You gain 3 life.", power='1', toughness='1', keywords=['Haste']),  # noqa: E501
    card('Tower of Coireall', set_code="tst", number="C02", mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text="{T}: Target creature can't be blocked by Walls this turn."),  # noqa: E501
    card('Pym Particles', set_code="tst", number="C03", mana_cost='{U}', cmc=1.0, type_line='Sorcery', oracle_text="Target creature gains vigilance until end of turn and can't be blocked this turn.\nDraw a card.", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Water Wings', set_code="tst", number="C04", mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text="Until end of turn, target creature you control has base power and toughness 4/4 and gains flying and hexproof. (It can't be the target of spells or abilities your opponents control.)", colors=['U'], color_identity=['U']),  # noqa: E501
    card('Doorman', set_code="tst", number="C05", mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Human Advisor', oracle_text='{T}: Until end of turn, target creature can\'t be blocked by creatures with power 2 or less and/or Walls.', power='1', toughness='2', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Cloudcrest Lake', set_code="tst", number="D01", mana_cost='', cmc=0.0, type_line='Land', oracle_text="{T}: Add {C}.\n{T}: Add {W} or {U}. This land doesn't untap during your next untap step.", color_identity=['U', 'W']),  # noqa: E501
    card('Wizard Mentor', set_code="tst", number="D02", mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Human Wizard', oracle_text="{T}: Return this creature and target creature you control to their owner's hand.", power='2', toughness='2', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Grizzly Bears', set_code="tst", number="A08", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
]
FULL = ["Sleep", "Bontu's Last Reckoning", "Frost Breath", "Kefnet's Monument", "Arbalest Elite", "Apes of Rath", "Ojutai's Breath", "Sneak Attack", "Arms Race",
        "Kor Skyfisher", "Ambush Krotiq", "Curfew", "Peel from Reality", "Reduce to Dreams",
        "Gingerbrute", "Tower of Coireall", "Pym Particles", "Water Wings",
        "Cloudcrest Lake", "Wizard Mentor"]
STILL_MANUAL = {  # (card, the line that stays manual)
    "Whelming Wave": "except for Krakens",  # (an exception list: not read)
    "Doorman": "Until end of turn, target creature can't be blocked by",  # (a leading duration on a restriction: not read)
}


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", list(STILL_MANUAL))
def test_still_manual(cards, name):
    cov = coverage.of_card_data(cards.resolve(name))
    assert any(not f.supported and STILL_MANUAL[name] in f.label for f in cov.features)


def tapped(s, c):
    return s.state.cards[c.id].tapped


# -- next untap step -------------------------------------------------------------------------------------
def test_untap_rider_parses_named_objects_only():
    assert scripts.parse_effects("Tap target creature. It doesn't untap during its controller's next untap step.") == (
        [{"do": "tap", "who": "target"}, {"do": "stay_tapped", "who": "target", "during": "controller"}], "creature", False)
    for text in ("Each attacking creature doesn't untap during its controller's next untap step.",
                 "Creatures target player controls don't untap during that player's next untap step.",
                 "Tap target creature. It doesn't untap during its controller's next two untap steps."):
        assert scripts.parse_effects(text) is None, text


def test_frost_breath_keeps_both_tapped_through_one_untap_step(cards):
    s = build(cards, p1=("Frost Breath",))
    breath = to_hand(s, "Frost Breath")
    a, b = creature(s, "p2", "Ox"), creature(s, "p2", "Yak")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=breath.id, targets=[a.id, b.id], target_counts=[2])
    settle(s)
    assert tapped(s, a) and tapped(s, b) and len(s.state.rules.stay_tapped) == 2
    roundtrip(s)
    to_turn(s, 2)  # Bob's untap step: they stay tapped (502.3)
    assert tapped(s, a) and tapped(s, b) and not s.state.rules.stay_tapped
    to_turn(s, 4)  # the next one: they untap
    assert not tapped(s, a) and not tapped(s, b)
    roundtrip(s)


def test_the_effect_is_used_up_even_when_the_permanent_was_untapped(cards):
    """Kefnet's Monument on an untapped creature: it untaps normally in its controller's next untap step, and the
    effect ends there (611.2c / 502.3), so a later tap is undone by the untap step after that."""
    s = build(cards, p1=("Kefnet's Monument", "Grizzly Bears"))
    on_field(s, "Kefnet's Monument")
    ox = creature(s, "p2", "Ox")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    d = s.state.rules.decision
    if d is not None and d.kind != "choose_targets":
        settle(s)
    settle(s)
    assert not tapped(s, ox) and s.state.rules.stay_tapped
    to_turn(s, 2)  # Bob's untap step: the effect ends (the Ox wasn't tapped)
    assert not s.state.rules.stay_tapped
    act(s, "p2", type="tap", card_ids=[ox.id], tapped=True)
    to_turn(s, 4)
    assert not tapped(s, ox)
    roundtrip(s)


def test_its_controller_is_read_when_the_untap_step_comes(cards):
    """Frost Breath on Bob's creature; Alice then gains control of it: it stays tapped during Alice's next untap
    step (its controller's at that time, 611.2c), and Bob's untap step before that doesn't use the effect up."""
    s = build(cards, p1=("Frost Breath",))
    breath = to_hand(s, "Frost Breath")
    ox = creature(s, "p2", "Ox")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=breath.id, targets=[ox.id], target_counts=[1])
    settle(s)
    assert tapped(s, ox)
    act(s, "p1", type="set_controller", card_ids=[ox.id], player="p1")
    to_turn(s, 2)  # Bob's untap step: not the Ox's controller's
    assert tapped(s, ox) and s.state.rules.stay_tapped
    to_turn(s, 3)  # Alice's: it stays tapped, and the effect ends
    assert tapped(s, ox) and not s.state.rules.stay_tapped
    to_turn(s, 5)
    assert not tapped(s, ox)
    roundtrip(s)


def test_a_new_object_is_not_affected(cards):
    s = build(cards, p1=("Frost Breath",), p2=("Grizzly Bears",))
    breath = to_hand(s, "Frost Breath")
    ox = on_field(s, "Grizzly Bears", pid="p2")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=breath.id, targets=[ox.id], target_counts=[1])
    settle(s)
    assert tapped(s, ox)
    act(s, "p2", type="move", card_ids=[ox.id], to={"player": "p2", "zone": "exile"})
    act(s, "p2", type="move", card_ids=[ox.id], to={"player": "p2", "zone": "battlefield"})  # a new object (400.7)
    act(s, "p2", type="tap", card_ids=[ox.id], tapped=True)
    to_turn(s, 2)
    assert not tapped(s, ox) and not s.state.rules.stay_tapped
    roundtrip(s)


def test_apes_of_rath_stay_tapped_after_attacking(cards):
    s = build(cards, p1=("Apes of Rath",))
    apes = on_field(s, "Apes of Rath")
    to_turn(s, 3, phase="main1")
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (apes, "p2"))
    settle(s)
    assert tapped(s, apes) and s.state.rules.stay_tapped
    to_turn(s, 5)  # Alice's next untap step
    assert tapped(s, apes) and not s.state.rules.stay_tapped
    to_turn(s, 7)
    assert not tapped(s, apes)
    roundtrip(s)


# -- put from hand: Sneak Attack's follow-up (the put itself: wave 5J, app/rules/put_from_hand.py) -------------------
def test_sneak_attack_haste_then_sacrifice_at_the_next_end_step(cards):
    s = build(cards, p1=("Sneak Attack", "Grizzly Bears"))
    sneak = on_field(s, "Sneak Attack")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=sneak.id, ability=0)
    settle(s)
    card_ = s.state.cards[bears.id]
    assert card_.zone == "p1:battlefield"
    assert "haste" in ch(s, card_).keywords
    roundtrip(s)
    to_turn(s, 2)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    roundtrip(s)


# -- bounce forms ---------------------------------------------------------------------------------------------------
def zone_of(s, c):
    return s.state.cards[c.id].zone if c.id in s.state.cards else None


def test_kor_skyfisher_returns_a_permanent_you_control_chosen_on_resolution(cards):
    """Not a target (608.2d): the choice is among what Alice controls as it resolves — Bob's permanents aren't offered."""
    s = build(cards, p1=("Kor Skyfisher", "Grizzly Bears"), p2=("Hill Giant",))
    bears = on_field(s, "Grizzly Bears")
    on_field(s, "Hill Giant", pid="p2")
    fisher = to_hand(s, "Kor Skyfisher")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=fisher.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    offered = {o.id for o in d.options}
    assert bears.id in offered and fisher.id in offered
    assert all(s.state.cards[c].controller == "p1" for c in offered)
    pick(s, bears.id)
    settle(s)
    assert zone_of(s, bears) == "p1:hand" and zone_of(s, fisher) == "p1:battlefield"
    roundtrip(s)


def test_ambush_krotiq_returns_another_creature_not_itself(cards):
    s = build(cards, p1=("Ambush Krotiq", "Grizzly Bears"))
    bears = on_field(s, "Grizzly Bears")
    krotiq = to_hand(s, "Ambush Krotiq")
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=krotiq.id)
    settle(s)  # (the Bears are the only other creature: no choice)
    assert zone_of(s, bears) == "p1:hand" and zone_of(s, krotiq) == "p1:battlefield"
    roundtrip(s)


def test_curfew_each_player_returns_one_of_theirs(cards):
    s = build(cards, p1=("Curfew", "Grizzly Bears", "Hill Giant"), p2=("Hill Giant",))
    bears, giant = on_field(s, "Grizzly Bears"), on_field(s, "Hill Giant")
    theirs = on_field(s, "Hill Giant", pid="p2")
    curfew = to_hand(s, "Curfew")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=curfew.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {bears.id, giant.id}
    pick(s, giant.id)
    settle(s)  # (Bob has one: it's chosen without a question)
    assert zone_of(s, giant) == "p1:hand" and zone_of(s, bears) == "p1:battlefield" and zone_of(s, theirs) == "p2:hand"
    roundtrip(s)


def test_peel_from_reality_two_targets_together(cards):
    s = build(cards, p1=("Peel from Reality", "Grizzly Bears"), p2=("Hill Giant",))
    bears = on_field(s, "Grizzly Bears")
    theirs = on_field(s, "Hill Giant", pid="p2")
    peel = to_hand(s, "Peel from Reality")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=peel.id, targets=[bears.id, theirs.id], target_counts=[1, 1])
    settle(s)
    assert zone_of(s, bears) == "p1:hand" and zone_of(s, theirs) == "p2:hand"
    roundtrip(s)


def test_reduce_to_dreams_returns_artifacts_and_enchantments(cards):
    s = build(cards, p1=("Reduce to Dreams", "Ornithopter", "Sneak Attack", "Grizzly Bears"))
    thopter, sneak, bears = on_field(s, "Ornithopter"), on_field(s, "Sneak Attack"), on_field(s, "Grizzly Bears")
    dreams = to_hand(s, "Reduce to Dreams")
    mana(s, U=5)
    act(s, "p1", type="cast_spell", card_id=dreams.id)
    settle(s)
    assert zone_of(s, thopter) == "p1:hand" and zone_of(s, sneak) == "p1:hand" and zone_of(s, bears) == "p1:battlefield"
    roundtrip(s)


# -- turn grants ------------------------------------------------------------------------------------------------------
def imposed(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).imposed


def characteristics(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def test_turn_grants_parse():
    from app.rules import selectors

    walls = selectors.parse("Walls").key()
    assert scripts.parse_effects("Target creature can't be blocked by Walls this turn.") == (
        [{"do": "restrict", "who": "target", "rules": [f"cant_be_blocked_by:{walls}"]}], "sel:{\"types\":[\"Creature\"]}", False)
    assert scripts.parse_effects("Target creature can't be blocked this turn.")[0] == [
        {"do": "restrict", "who": "target", "rules": ["cant_be_blocked"]}]  # (as before)
    for text in ("Target creature gains flying and can't be blocked this turn.",  # (a grant with no duration)
                 "Target creature can't be blocked this combat."):
        assert scripts.parse_effects(text) is None, text


def test_gingerbrute_can_be_blocked_only_by_creatures_with_haste(cards):
    from app.game.errors import ActionError
    from tests.test_rules_combat import block

    s = build(cards, p1=("Gingerbrute",))
    ginger = on_field(s, "Gingerbrute")
    slow = creature(s, "p2", "Slowpoke")
    fast = creature(s, "p2", "Speedy", text="Haste")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=ginger.id, ability=1)
    settle(s)
    assert any(r.startswith("cant_be_blocked_except_by:") for r in imposed(s, ginger))
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (ginger, "p2"))
    to_blockers_after_attack(s)
    with pytest.raises(ActionError):
        block(s, "p2", (slow, ginger))
    block(s, "p2", (fast, ginger))
    roundtrip(s)
    to_turn(s, 2)  # (it ends with the turn, 514.2)
    assert not any(r.startswith("cant_be_blocked") for r in imposed(s, ginger))


def to_blockers_after_attack(s):
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            return d
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blockers step")


def test_tower_of_coireall_walls_cant_block_it(cards):
    s = build(cards, p1=("Tower of Coireall",))
    tower = on_field(s, "Tower of Coireall")
    bear = creature(s, "p1", "Bear")
    act(s, "p1", type="activate_ability", card_id=tower.id, ability=0, targets=[bear.id])
    settle(s)
    from app.rules import selectors

    assert f"cant_be_blocked_by:{selectors.parse('Walls').key()}" in imposed(s, bear)
    roundtrip(s)


def test_pym_particles_and_water_wings_one_subject_two_grants(cards):
    s = build(cards, p1=("Pym Particles", "Water Wings"))
    bear = creature(s, "p1", "Bear")
    pym, wings = to_hand(s, "Pym Particles"), to_hand(s, "Water Wings")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=pym.id, targets=[bear.id])
    settle(s)
    act(s, "p1", type="cast_spell", card_id=wings.id, targets=[bear.id])
    settle(s)
    ch_ = characteristics(s, bear)
    assert "cant_be_blocked" in ch_.imposed and {"vigilance", "flying", "hexproof"} <= set(ch_.keywords)
    assert ch_.pt == (4, 4)  # 613.4b: base 4/4
    roundtrip(s)
    to_turn(s, 2)
    ch_ = characteristics(s, bear)
    assert ch_.pt == (2, 2) and "flying" not in ch_.keywords and "cant_be_blocked" not in ch_.imposed
    roundtrip(s)


def test_cloudcrest_lake_colored_mana_keeps_it_tapped_through_your_next_untap_step(cards):
    """A mana ability's rider (605.3a: no stack): the land stays tapped during Alice's next untap step only (502.3)."""
    s = build(cards, p1=("Cloudcrest Lake",))
    lake = on_field(s, "Cloudcrest Lake")
    act(s, "p1", type="activate_ability", card_id=lake.id, ability=1, mana_choice="W")
    assert tapped(s, lake) and s.state.rules.stay_tapped
    roundtrip(s)
    to_turn(s, 3)
    assert tapped(s, lake) and not s.state.rules.stay_tapped
    to_turn(s, 5)
    assert not tapped(s, lake)
    act(s, "p1", type="activate_ability", card_id=lake.id, ability=0)  # {C}: no rider
    assert not s.state.rules.stay_tapped
    roundtrip(s)


def test_wizard_mentor_returns_itself_and_the_target(cards):
    s = build(cards, p1=("Wizard Mentor", "Grizzly Bears"))
    mentor, bears = on_field(s, "Wizard Mentor"), on_field(s, "Grizzly Bears")
    to_turn(s, 3)  # (summoning sickness: {T}, 302.6)
    act(s, "p1", type="activate_ability", card_id=mentor.id, ability=0, targets=[bears.id])
    settle(s)
    assert zone_of(s, mentor) == "p1:hand" and zone_of(s, bears) == "p1:hand"
    roundtrip(s)
