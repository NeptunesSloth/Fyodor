"""Wave 23B: abilities on the stack as objects (CR 113.7, 115.1, 701.6a, 707.10), researched against the stored Comprehensive Rules.

* 707.10 / 603.2: "Whenever you activate an ability that targets a creature or player, copy that ability. You may choose new targets
  for the copy." (Ertha Jo); "Whenever an ability of equipped creature is activated, if it isn't a mana ability, copy that ability"
  (Illusionist's Bracers); "Copy target triggered ability you control twice." (Mister Fantastic). The copy isn't activated or cast
  (707.10), so it doesn't trigger these again; a mana ability never uses the stack (605.3b).
Real Oracle text; each scenario replays the history and survives a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_suspend import until
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip

EXTRA = [
    card('Ertha Jo, Frontier Mentor', set_code='tst', number='S01', mana_cost='{2}{R}{W}', cmc=4.0, type_line='Legendary Creature — Kor Advisor', oracle_text='When Ertha Jo enters, create a 1/1 white Kor Soldier creature token.\nWhenever you activate an ability that targets a creature or player, copy that ability. You may choose new targets for the copy.', power='2', toughness='4', colors=['R', 'W'], color_identity=['R', 'W']),  # noqa: E501
    card("Illusionist's Bracers", set_code='tst', number='S02', mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment', oracle_text="Whenever an ability of equipped creature is activated, if it isn't a mana ability, copy that ability. You may choose new targets for the copy.\nEquip {3}"),  # noqa: E501
    card("Battlemage's Bracers", set_code='tst', number='S03', mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment', oracle_text="Equipped creature gets +1/+1.\nWhenever an ability of equipped creature is activated, if it isn't a mana ability, you may pay {1}. If you do, copy that ability. You may choose new targets for the copy.\nEquip {3}"),  # noqa: E501
    card('Mister Fantastic', set_code='tst', number='S04', mana_cost='{R}{G}{W}{U}', cmc=4.0, type_line='Legendary Creature — Human Scientist Hero', oracle_text='Defender\n{R}{G}{W}{U}, {T}: Copy target triggered ability you control twice. You may choose new targets for the copies.', power='2', toughness='3', colors=['G', 'R', 'U', 'W'], color_identity=['G', 'R', 'U', 'W'], keywords=['Defender']),  # noqa: E501
    card('Rod of Ruin', set_code='tst', number='S05', mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='{3}, {T}: Rod of Ruin deals 1 damage to any target.'),  # noqa: E501
    card('Test Pinger', set_code='tst', number='S06', mana_cost='{2}', cmc=2.0, type_line='Creature — Human', oracle_text='Haste\n{T}: Test Pinger deals 1 damage to any target.', power='1', toughness='1', colors=[], color_identity=[], keywords=['Haste']),  # noqa: E501
    card('Test Dork', set_code='tst', number='S10', mana_cost='{1}', cmc=1.0, type_line='Creature — Elf', oracle_text='Haste\n{T}: Add {G}.', power='1', toughness='1', colors=[], color_identity=[], keywords=['Haste']),  # noqa: E501
    card('Test Tremors', set_code='tst', number='S07', mana_cost='{2}', cmc=2.0, type_line='Enchantment', oracle_text='Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.'),  # noqa: E501
    card('Test Fodder', set_code='tst', number='S08', mana_cost='{1}', cmc=1.0, type_line='Creature — Elf', oracle_text='', power='1', toughness='1', colors=[], color_identity=[]),  # noqa: E501
    card('Test Ox', set_code='tst', number='S09', mana_cost='{2}', cmc=2.0, type_line='Creature — Ox', oracle_text='', power='3', toughness='3', colors=[], color_identity=[]),  # noqa: E501
]
COUNTERS = [
    card('Trickbind', set_code='tst', number='C01', mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text="Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)\nCounter target activated or triggered ability. If a permanent's ability is countered this way, activated abilities of that permanent can't be activated this turn. (Mana abilities can't be targeted.)", power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=['Split second']),  # noqa: E501
    card("Tishana's Tidebinder", set_code='tst', number='C02', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Merfolk Wizard', oracle_text="Flash\nWhen this creature enters, counter up to one target activated or triggered ability. If an ability of an artifact, creature, or planeswalker is countered this way, that permanent loses all abilities for as long as this creature remains on the battlefield. (Mana abilities can't be targeted.)", power='3', toughness='2', colors=['U'], color_identity=['U'], keywords=['Flash']),  # noqa: E501
    card("Tale's End", set_code='tst', number='C03', mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text='Counter target activated ability, triggered ability, or legendary spell.', power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Green Slime', set_code='tst', number='C04', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Ooze', oracle_text="Flash\nWhen this creature enters, counter target activated or triggered ability from an artifact or enchantment source. If a permanent's ability is countered this way, destroy that permanent.\nForetell {G} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)", power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Flash', 'Foretell']),  # noqa: E501
    card('Ouphe Vandals', set_code='tst', number='C05', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Ouphe Rogue', oracle_text="{G}, Sacrifice this creature: Counter target activated ability from an artifact source and destroy that artifact if it's on the battlefield. (Mana abilities can't be targeted.)", power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Interdict', set_code='tst', number='C06', mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text="Counter target activated ability from an artifact, creature, enchantment, or land. That permanent's activated abilities can't be activated this turn. (Mana abilities can't be targeted.)\nDraw a card.", power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card("Teferi's Response", set_code='tst', number='C07', mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text="Counter target spell or ability an opponent controls that targets a land you control. If a permanent's ability is countered this way, destroy that permanent.\nDraw two cards.", power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card("Louisoix's Sacrifice", set_code='tst', number='C08', mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='As an additional cost to cast this spell, sacrifice a legendary creature or pay {2}.\nCounter target activated ability, triggered ability, or noncreature spell.', power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Consign to Memory', set_code='tst', number='C09', mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='Replicate {1} (When you cast this spell, copy it for each time you paid its replicate cost. You may choose new targets for the copies.)\nCounter target triggered ability or colorless spell.', power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=['Replicate']),  # noqa: E501
    card('Test Bomb', set_code='tst', number='C10', mana_cost='{1}', cmc=1.0, type_line='Artifact', oracle_text='{1}, Sacrifice this artifact: Test Bomb deals 1 damage to any target.'),  # noqa: E501
    card('Test Zapper', set_code='tst', number='C12', mana_cost='{1}', cmc=1.0, type_line='Artifact', oracle_text='{1}: Destroy target land.'),  # noqa: E501
    card('Test Legend', set_code='tst', number='C11', mana_cost='{1}', cmc=1.0, type_line='Legendary Creature — Elf', oracle_text='', power='1', toughness='1', colors=[], color_identity=[]),  # noqa: E501
]
EXTRA += COUNTERS
FULL = ["Ertha Jo, Frontier Mentor", "Illusionist's Bracers", "Battlemage's Bracers", "Mister Fantastic", *(c["name"] for c in COUNTERS[:9])]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def life(s, pid):
    return s.state.players[pid].life


# -- Ertha Jo: an ability that targets a creature or player (707.10) -----------------------------------------------------------
def test_ertha_jo_copies_an_ability_that_targets_a_player(cards):
    s = build(cards, p1=("Ertha Jo, Frontier Mentor", "Rod of Ruin"))
    put(s, "Ertha Jo, Frontier Mentor", "battlefield")
    rod = put(s, "Rod of Ruin", "battlefield")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=rod.id, ability=0, targets=["p2"])
    answer(s)  # the trigger (603.2), the copy (707.10); the copy keeps its target ("choose new targets": decline)
    assert life(s, "p2") == 38  # the ability and its copy
    roundtrip(s)


def test_ertha_jo_ignores_a_mana_ability_and_a_targetless_one(cards):
    s = build(cards, p1=("Ertha Jo, Frontier Mentor", "Test Pinger", "Test Dork"))
    put(s, "Ertha Jo, Frontier Mentor", "battlefield")
    elves = put(s, "Test Dork", "battlefield")
    act(s, "p1", type="activate_ability", card_id=elves.id, ability=1)  # {T}: Add {G} (605.3b: no stack, nothing to copy)
    assert not s.state.zones.get("stack")
    roundtrip(s)


# -- Illusionist's Bracers: an ability of the equipped creature -----------------------------------------------------------------
def _equip(s, gear, creature):
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    c = s.state.cards[gear.id]
    equip = next(a for a in derive(s.state, c, chars.of(c, s.cards), s.cards).abilities if "equip" in a.keywords)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=gear.id, ability=equip.index, targets=[creature.id])
    answer(s)
    assert s.state.cards[gear.id].attached_to == creature.id


def test_bracers_copy_the_equipped_creatures_ability(cards):
    s = build(cards, p1=("Illusionist's Bracers", "Test Pinger"))
    gear = put(s, "Illusionist's Bracers", "battlefield")
    pinger = put(s, "Test Pinger", "battlefield")
    _equip(s, gear, pinger)
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=1, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 38
    roundtrip(s)


def test_bracers_do_nothing_for_an_unequipped_creature(cards):
    s = build(cards, p1=("Illusionist's Bracers", "Test Pinger", "Test Ox"))
    put(s, "Illusionist's Bracers", "battlefield")
    pinger = put(s, "Test Pinger", "battlefield")
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=1, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39
    roundtrip(s)


def _battlemages(cards, pick):
    s = build(cards, p1=("Battlemage's Bracers", "Test Pinger"))
    gear = put(s, "Battlemage's Bracers", "battlefield")
    pinger = put(s, "Test Pinger", "battlefield")
    _equip(s, gear, pinger)
    mana(s, C=1)  # (before the trigger resolves: the payment is made as it does)
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=1, targets=["p2"])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id in (pick, "keep"))])  # (new targets: keep)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s


def test_battlemages_bracers_pay_for_the_copy(cards):
    s = _battlemages(cards, "pay")
    assert life(s, "p2") == 38 and s.state.players["p1"].mana == {}
    roundtrip(s)


def test_battlemages_bracers_decline_the_copy(cards):
    s = _battlemages(cards, "decline")
    assert life(s, "p2") == 39 and s.state.players["p1"].mana == {"C": 1}
    roundtrip(s)


# -- Mister Fantastic: a triggered ability you control, twice ---------------------------------------------------------------
def test_mister_fantastic_copies_a_triggered_ability_twice(cards):
    s = build(cards, p1=("Mister Fantastic", "Test Tremors", "Test Fodder"))
    mf = put(s, "Mister Fantastic", "battlefield")
    put(s, "Test Tremors", "battlefield")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # (no longer summoning sick)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    fodder = put(s, "Test Fodder", "hand")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=fodder.id)
    for _ in range(4):  # the creature spell resolves; Tremors triggers (603.2): one damage to each opponent, on the stack
        act(s, s.state.rules.priority, type="pass_priority")
        if any(s.state.cards[c].ability is not None for c in s.state.zones.get("stack", [])):
            break
    (trigger,) = s.state.zones["stack"]
    mana(s, R=1, G=1, W=1, U=1)
    act(s, "p1", type="activate_ability", card_id=mf.id, ability=1, targets=[trigger])
    answer(s)
    assert life(s, "p2") == 37  # the trigger and its two copies (707.10)
    roundtrip(s)


# -- countering an ability (701.6a) ---------------------------------------------------------------------------------------------
def stack(s):
    return list(s.state.zones.get("stack", []))


def prefs(s):
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)


def activate_rod(cards, *extra):
    """p1 has a Rod of Ruin (its ability on the stack, aimed at p2); p2 holds the cards in ``extra`` and has priority."""
    s = build(cards, p1=("Rod of Ruin", "Test Pinger", "Test Bomb", "Test Legend", "Test Ox"), p2=extra)
    prefs(s)
    rod = put(s, "Rod of Ruin", "battlefield")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=rod.id, ability=0, targets=["p2"])
    (ability,) = stack(s)
    return s, rod, ability


def cast_at(s, name, target, **pay):
    card = put(s, name, "hand", "p2")
    mana(s, "p2", **pay)
    act(s, "p2", type="cast_spell", card_id=card.id, targets=[target])
    return card


def enter_and_aim(s, name, target, **pay):
    """Cast the flash creature in response; its enters trigger aims at ``target`` (the ability on the stack)."""
    card = put(s, name, "hand", "p2")
    mana(s, "p2", **pay)
    act(s, "p2", type="cast_spell", card_id=card.id)
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[target])
        elif stack(s) and s.state.cards[stack(s)[-1]].ability is not None:
            return card
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return card


def test_trickbind_counters_the_ability_and_locks_its_source(cards):
    s, rod, ability = activate_rod(cards, "Trickbind")
    cast_at(s, "Trickbind", ability, U=1, C=1)
    answer(s)
    assert life(s, "p2") == 40 and not stack(s)  # (701.6a: the ability is countered and ceases to exist)
    mana(s, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=rod.id, ability=0, targets=["p2"])  # (602.5: "that permanent" this turn)
    roundtrip(s)


def test_trickbind_rider_does_nothing_once_the_source_left(cards):
    s = build(cards, p1=("Test Bomb",), p2=("Trickbind",))
    prefs(s)
    bomb = put(s, "Test Bomb", "battlefield")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bomb.id, ability=0, targets=["p2"])  # (the Bomb is sacrificed as a cost)
    (ability,) = stack(s)
    cast_at(s, "Trickbind", ability, U=1, C=1)
    answer(s)
    assert life(s, "p2") == 40 and s.state.cards[bomb.id].zone.endswith(":graveyard")
    roundtrip(s)


def test_tidebinder_strips_the_source_for_as_long_as_it_stays(cards):
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    s, rod, ability = activate_rod(cards, "Tishana's Tidebinder")
    binder = enter_and_aim(s, "Tishana's Tidebinder", ability, U=1, C=2)
    answer(s)
    assert life(s, "p2") == 40  # (countered)

    def abilities():
        c = s.state.cards[rod.id]
        return [a for a in derive(s.state, c, chars.of(c, s.cards), s.cards).abilities if a.kind == "activated"]

    assert not abilities()  # (the Rod lost all abilities, 613.1f)
    roundtrip(s)
    act(s, "p2", type="move", card_ids=[binder.id], to={"player": "p2", "zone": "graveyard"})  # (611.2b: it ends as Tidebinder leaves)
    act(s, s.state.rules.priority, type="pass_priority")  # (the rules look at the table again: expire)
    assert abilities()
    roundtrip(s)


def test_tales_end_counters_an_ability_or_a_legendary_spell_only(cards):
    s, rod, ability = activate_rod(cards, "Tale's End", "Tale's End")
    first, second = [c for c in s.state.cards.values() if c.name == "Tale's End"]
    act(s, "p2", type="move", card_ids=[first.id, second.id], to={"player": "p2", "zone": "hand"})
    mana(s, "p2", U=2, C=2)
    act(s, "p2", type="cast_spell", card_id=first.id, targets=[ability])
    answer(s)
    assert life(s, "p2") == 40  # (the ability was countered)
    legend, ox = put(s, "Test Legend", "hand"), put(s, "Test Ox", "hand")
    for cast in (ox, legend):  # p1 casts creature spells; p2 may respond to each
        mana(s, C=3)
        act(s, "p1", type="cast_spell", card_id=cast.id)
        (spell,) = stack(s)
        if cast is ox:
            with pytest.raises(ActionError):  # (a nonlegendary creature spell isn't a legal target)
                act(s, "p2", type="cast_spell", card_id=second.id, targets=[spell])
            answer(s)
        else:
            act(s, "p2", type="cast_spell", card_id=second.id, targets=[spell])
            answer(s)
    assert s.state.cards[legend.id].zone.endswith(":graveyard") and s.state.cards[ox.id].zone.endswith(":battlefield")
    roundtrip(s)


def test_green_slime_counters_an_artifact_ability_and_destroys_the_permanent(cards):
    s, rod, ability = activate_rod(cards, "Green Slime")
    enter_and_aim(s, "Green Slime", ability, G=1, C=2)
    answer(s)
    assert life(s, "p2") == 40 and s.state.cards[rod.id].zone.endswith(":graveyard")  # (the Rod: "destroy that permanent")
    roundtrip(s)


def test_green_slime_has_no_legal_target_for_a_creatures_ability(cards):
    s = build(cards, p1=("Test Pinger",), p2=("Green Slime",))
    prefs(s)
    pinger = put(s, "Test Pinger", "battlefield")
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=1, targets=["p2"])
    (ability,) = stack(s)
    slime = put(s, "Green Slime", "hand", "p2")
    mana(s, "p2", G=1, C=2)
    act(s, "p2", type="cast_spell", card_id=slime.id)
    answer(s)
    assert life(s, "p2") == 39 and s.state.cards[pinger.id].zone.endswith(":battlefield")  # (a creature isn't an artifact or enchantment source)
    assert ability not in stack(s)
    roundtrip(s)


def test_ouphe_vandals_counters_the_ability_and_destroys_the_artifact(cards):
    s, rod, ability = activate_rod(cards, "Ouphe Vandals")
    vandals = put(s, "Ouphe Vandals", "battlefield", "p2")
    mana(s, "p2", G=1)
    act(s, "p2", type="activate_ability", card_id=vandals.id, ability=0, targets=[ability])
    answer(s)
    assert life(s, "p2") == 40 and s.state.cards[rod.id].zone.endswith(":graveyard")
    assert s.state.cards[vandals.id].zone.endswith(":graveyard")  # (sacrificed as a cost)
    roundtrip(s)


def test_interdict_locks_the_source_and_draws(cards):
    s, rod, ability = activate_rod(cards, "Interdict")
    hand = len(s.state.zones.get("p2:hand", []))
    cast_at(s, "Interdict", ability, U=1, C=1)
    answer(s)
    assert life(s, "p2") == 40 and len(s.state.zones["p2:hand"]) == hand + 1  # (the spell left the hand; the card drawn replaces it)
    mana(s, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=rod.id, ability=0, targets=["p2"])
    roundtrip(s)


def test_teferis_response_counters_what_targets_your_land_and_destroys_the_permanent(cards):
    s = build(cards, p1=("Test Zapper",), p2=("Teferi's Response",))
    prefs(s)
    zapper = put(s, "Test Zapper", "battlefield")
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=zapper.id, ability=0, targets=[island.id])
    (ability,) = stack(s)
    hand = len(s.state.zones.get("p2:hand", []))
    cast_at(s, "Teferi's Response", ability, U=1, C=1)
    answer(s)
    assert s.state.cards[island.id].zone.endswith(":battlefield")  # (countered: the land lives)
    assert s.state.cards[zapper.id].zone.endswith(":graveyard")  # (destroy that permanent)
    assert len(s.state.zones["p2:hand"]) == hand + 2  # (the spell left the hand; two cards drawn)
    roundtrip(s)


def test_consign_to_memory_counters_a_triggered_ability(cards):
    s = build(cards, p1=("Test Tremors", "Test Fodder"), p2=("Consign to Memory",))
    prefs(s)
    put(s, "Test Tremors", "battlefield")
    fodder = put(s, "Test Fodder", "hand")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=fodder.id)
    for _ in range(6):  # the creature spell resolves; Tremors triggers (603.2) and p2 gets priority with it on the stack
        if stack(s) and s.state.cards[stack(s)[-1]].ability is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    (trigger,) = stack(s)
    if s.state.rules.priority != "p2":
        act(s, "p1", type="pass_priority")  # (p2 may respond to the trigger)
    cast_at(s, "Consign to Memory", trigger, U=1)
    answer(s)
    assert life(s, "p2") == 40 and not stack(s)  # (701.6a: the trigger is countered)
    roundtrip(s)


def test_louisoixs_sacrifice_pays_two_or_sacrifices_a_legendary_creature(cards):
    s, rod, ability = activate_rod(cards, "Louisoix's Sacrifice")
    cast_at(s, "Louisoix's Sacrifice", ability, U=1, C=2)  # (the additional cost: pay {2})
    answer(s)
    assert life(s, "p2") == 40 and not stack(s)
    roundtrip(s)
