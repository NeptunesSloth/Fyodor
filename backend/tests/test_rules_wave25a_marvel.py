"""Wave 25A: the Marvel and Doctor Who keywords mayhem, web-slinging, airbend and time travel (CR 702.187, 702.188, 701.65, 701.56). Real Oracle text, replay and save/load for each.

* 702.187b: "As long as you discarded this card this turn, you may cast it from your graveyard by paying [cost] rather than paying its
  mana cost" (an alternative cost; the card is that object only: 400.7); 702.187c: a bare "Mayhem" lets you play it from there.
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
from tests.test_rules_effects import mana, token
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Raging Goblinoids', set_code='tst', number='M01', mana_cost='{4}{R}', cmc=5.0, type_line='Creature — Goblin Berserker Villain', oracle_text='Haste\nMayhem {2}{R} (You may cast this card from your graveyard for {2}{R} if you discarded it this turn. Timing rules still apply.)', power='5', toughness='4', colors=['R'], color_identity=['R'], keywords=['Mayhem', 'Haste'], layout='normal'),  # noqa: E501
    card('Oscorp Industries', set_code='tst', number='M02', cmc=0.0, type_line='Land', oracle_text='This land enters tapped.\nWhen this land enters from a graveyard, you lose 2 life.\n{T}: Add {U}, {B}, or {R}.\nMayhem (You may play this card from your graveyard if you discarded it this turn. Timing rules still apply.)', colors=[], color_identity=['B', 'R', 'U'], keywords=['Mayhem'], layout='normal'),  # noqa: E501
    card("Sandman's Quicksand", set_code='tst', number='M03', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Sorcery', oracle_text="Mayhem {3}{B} (You may cast this card from your graveyard for {3}{B} if you discarded it this turn. Timing rules still apply.)\nAll creatures get -2/-2 until end of turn. If this spell's mayhem cost was paid, creatures your opponents control get -2/-2 until end of turn instead.", colors=['B'], color_identity=['B'], keywords=['Mayhem'], layout='normal'),  # noqa: E501
    card('Faithless Looting', set_code='tst', number='M04', mana_cost='{R}', cmc=1.0, type_line='Sorcery', oracle_text='Draw two cards, then discard two cards.\nFlashback {2}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', colors=['R'], color_identity=['R'], keywords=['Flashback'], layout='normal'),  # noqa: E501
    card('Prison Break', set_code='tst', number='M05', mana_cost='{4}{B}', cmc=5.0, type_line='Sorcery', oracle_text='Return target creature card from your graveyard to the battlefield with an additional +1/+1 counter on it.\nMayhem {3}{B} (You may cast this card from your graveyard for {3}{B} if you discarded it this turn. Timing rules still apply.)', colors=['B'], color_identity=['B'], keywords=['Mayhem'], layout='normal'),  # noqa: E501,
    card('Spiders-Man, Heroic Horde', set_code='tst', number='M06', mana_cost='{1}{G}', cmc=2.0, type_line='Legendary Creature — Spider Hero', oracle_text="Web-slinging {4}{G}{G} (You may cast this spell for {4}{G}{G} if you also return a tapped creature you control to its owner's hand.)\nWhen Spiders-Man enters, if they were cast using web-slinging, you gain 3 life and create two 2/1 green Spider creature tokens with reach.", power='2', toughness='3', colors=['G'], color_identity=['G'], keywords=['Web-slinging'], layout='normal'),  # noqa: E501
    card('Spider-UK', set_code='tst', number='M07', mana_cost='{3}{W}', cmc=4.0, type_line='Legendary Creature — Spider Human Hero', oracle_text="Web-slinging {2}{W} (You may cast this spell for {2}{W} if you also return a tapped creature you control to its owner's hand.)\nAt the beginning of your end step, if two or more creatures entered the battlefield under your control this turn, you draw a card and gain 2 life.", power='3', toughness='4', colors=['W'], color_identity=['W'], keywords=['Web-slinging'], layout='normal'),  # noqa: E501
    card('Norman Osborn // Green Goblin', set_code='tst', number='M08', mana_cost='{1}{U} // {1}{U}{B}{R}', cmc=2.0, type_line='Legendary Creature — Human Scientist Villain // Legendary Creature — Goblin Human Villain', oracle_text="Norman Osborn can't be blocked.\nWhenever Norman Osborn deals combat damage to a player, he connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on this creature.)\n{1}{U}{B}{R}: Transform Norman Osborn. Activate only as a sorcery.\n//\nFlying, menace\nSpells you cast from your graveyard cost {2} less to cast.\nGoblin Formula — Each nonland card in your graveyard has mayhem. The mayhem cost is equal to its mana cost. (You may cast a card from your graveyard for its mayhem cost if you discarded it this turn. Timing rules still apply.)", power='1', toughness='1', colors=['B', 'R', 'U'], color_identity=['B', 'R', 'U'], keywords=['Flying', 'Goblin Formula', 'Transform', 'Menace', 'Connive'], layout='modal_dfc', card_faces=[{'name': 'Norman Osborn', 'mana_cost': '{1}{U}', 'type_line': 'Legendary Creature — Human Scientist Villain', 'oracle_text': "Norman Osborn can't be blocked.\nWhenever Norman Osborn deals combat damage to a player, he connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on this creature.)\n{1}{U}{B}{R}: Transform Norman Osborn. Activate only as a sorcery.", 'power': '1', 'toughness': '1', 'colors': ['U']}, {'name': 'Green Goblin', 'mana_cost': '{1}{U}{B}{R}', 'type_line': 'Legendary Creature — Goblin Human Villain', 'oracle_text': 'Flying, menace\nSpells you cast from your graveyard cost {2} less to cast.\nGoblin Formula — Each nonland card in your graveyard has mayhem. The mayhem cost is equal to its mana cost. (You may cast a card from your graveyard for its mayhem cost if you discarded it this turn. Timing rules still apply.)', 'power': '3', 'toughness': '3', 'colors': ['B', 'R', 'U']}], image_uris=None),  # noqa: E501
    card('Peter Parker // Amazing Spider-Man', set_code='tst', number='M09', mana_cost='{1}{W} // {1}{G}{W}{U}', cmc=2.0, type_line='Legendary Creature — Human Scientist Hero // Legendary Creature — Spider Human Hero', oracle_text="When Peter Parker enters, create a 2/1 green Spider creature token with reach.\n{1}{G}{W}{U}: Transform Peter Parker. Activate only as a sorcery.\n//\nVigilance, reach\nEach legendary spell you cast that's one or more colors has web-slinging {G}{W}{U}. (You may cast a spell for its web-slinging cost if you also return a tapped creature you control to its owner's hand.)", power='0', toughness='1', colors=['G', 'U', 'W'], color_identity=['G', 'U', 'W'], keywords=['Reach', 'Vigilance', 'Transform'], layout='modal_dfc', card_faces=[{'name': 'Peter Parker', 'mana_cost': '{1}{W}', 'type_line': 'Legendary Creature — Human Scientist Hero', 'oracle_text': 'When Peter Parker enters, create a 2/1 green Spider creature token with reach.\n{1}{G}{W}{U}: Transform Peter Parker. Activate only as a sorcery.', 'power': '0', 'toughness': '1', 'colors': ['W']}, {'name': 'Amazing Spider-Man', 'mana_cost': '{1}{G}{W}{U}', 'type_line': 'Legendary Creature — Spider Human Hero', 'oracle_text': "Vigilance, reach\nEach legendary spell you cast that's one or more colors has web-slinging {G}{W}{U}. (You may cast a spell for its web-slinging cost if you also return a tapped creature you control to its owner's hand.)", 'power': '4', 'toughness': '4', 'colors': ['G', 'U', 'W']}], image_uris=None),  # noqa: E501
    card('Airbending Lesson', set_code='tst', number='M10', mana_cost='{2}{W}', cmc=3.0, type_line='Instant — Lesson', oracle_text="Airbend target nonland permanent. (Exile it. While it's exiled, its owner may cast it for {2} rather than its mana cost.)\nDraw a card.", colors=['W'], color_identity=['W'], keywords=['Airbend'], layout='normal'),  # noqa: E501
    card('Monk Gyatso', set_code='tst', number='M11', mana_cost='{3}{W}', cmc=4.0, type_line='Legendary Creature — Human Monk', oracle_text="Whenever another creature you control becomes the target of a spell or ability, you may airbend that creature. (Exile it. While it's exiled, its owner may cast it for {2} rather than its mana cost.)", power='3', toughness='3', colors=['W'], color_identity=['W'], keywords=['Airbend'], layout='normal'),  # noqa: E501
    card('Rift Bolt', set_code='tst', number='M14', mana_cost='{2}{R}', cmc=3.0, type_line='Sorcery', oracle_text='Rift Bolt deals 3 damage to any target.\nSuspend 1—{R} (Rather than cast this card from your hand, you may pay {R} and exile it with a time counter on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its mana cost.)', colors=['R'], color_identity=['R'], keywords=['Suspend'], layout='normal'),  # noqa: E501
    card('Wibbly-wobbly, Timey-wimey', set_code='tst', number='M15', mana_cost='{1}{U}', cmc=2.0, type_line='Sorcery', oracle_text='Time travel. (For each suspended card you own and each permanent you control with a time counter on it, you may add or remove a time counter.)\nDraw a card.', colors=['U'], color_identity=['U'], keywords=['Time Travel'], layout='normal'),  # noqa: E501
    card('Aven Riftwatcher', set_code='tst', number='M16', mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Bird Rebel Soldier', oracle_text='Flying\nVanishing 3 (This creature enters with three time counters on it. At the beginning of your upkeep, remove a time counter from it. When the last is removed, sacrifice it.)\nWhen this creature enters or leaves the battlefield, you gain 2 life.', power='2', toughness='3', colors=['W'], color_identity=['W'], keywords=['Flying', 'Vanishing'], layout='normal'),  # noqa: E501
    card('Test Bear', set_code='tst', number='M20', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Bear', power='2', toughness='2', colors=['G'], color_identity=['G'], oracle_text=''),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Raging Goblinoids", "Oscorp Industries", "Sandman's Quicksand", "Prison Break", "Spiders-Man, Heroic Horde", "Spider-UK",
                                  "Norman Osborn // Green Goblin", "Peter Parker // Amazing Spider-Man",
                                  "Airbending Lesson", "Monk Gyatso", "Wibbly-wobbly, Timey-wimey", "Aven Riftwatcher"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def discard(s, name):
    """Discard ``name`` for real (Faithless Looting: draw two, then discard two — the first pick is the named card)."""
    put(s, "Faithless Looting", "hand")
    put(s, name, "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=find(s, "Faithless Looting").id)
    s.state.rules.priority == "p1" and act(s, "p1", type="pass_priority")
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options]
        want = [o.id for o in d.options if o.card_id == find(s, name).id]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=(want + [i for i in ids if i not in want])[: d.max_choices])
    answer(s)


def test_mayhem_casts_a_discarded_creature_from_the_graveyard_for_its_cost(cards):
    s = build(cards, p1=("Raging Goblinoids", "Faithless Looting"))
    discard(s, "Raging Goblinoids")
    gob = find(s, "Raging Goblinoids")
    assert gob.zone == "p1:graveyard"
    mana(s, R=1, C=2)  # mayhem {2}{R}, not its mana cost {4}{R}
    act(s, "p1", type="cast_spell", card_id=gob.id)
    answer(s)
    assert find(s, "Raging Goblinoids").zone == "p1:battlefield"
    roundtrip(s)


def test_mayhem_needs_the_card_to_have_been_discarded_this_turn(cards):
    s = build(cards, p1=("Raging Goblinoids", "Faithless Looting"))
    gob = put(s, "Raging Goblinoids", "graveyard")  # put there, not discarded
    mana(s, R=1, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=gob.id)
    roundtrip(s)


def test_mayhem_is_for_the_object_that_was_discarded(cards):
    s = build(cards, p1=("Raging Goblinoids", "Faithless Looting"))
    discard(s, "Raging Goblinoids")
    put(s, "Raging Goblinoids", "exile")  # a new object (400.7) when it comes back
    gob = put(s, "Raging Goblinoids", "graveyard")
    mana(s, R=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=gob.id)


def test_a_mayhem_cost_paid_changes_the_spell_instead(cards):
    s = build(cards, p1=("Sandman's Quicksand", "Faithless Looting"))
    mine, theirs = token(s, "p1", "Mine", "3/3"), token(s, "p2", "Theirs", "3/3")
    discard(s, "Sandman's Quicksand")
    mana(s, B=1, C=3)  # mayhem {3}{B}
    act(s, "p1", type="cast_spell", card_id=find(s, "Sandman's Quicksand").id)
    answer(s)
    from tests.test_rules_attachments import ch

    assert ch(s, mine).pt == (3, 3) and ch(s, theirs).pt == (1, 1)  # only the opponents' creatures got -2/-2
    assert find(s, "Sandman's Quicksand").zone == "p1:graveyard"  # (not exiled: it isn't flashback)
    roundtrip(s)


def test_the_normal_cast_of_the_same_spell_hits_every_creature(cards):
    s = build(cards, p1=("Sandman's Quicksand",))
    mine, theirs = token(s, "p1", "Mine", "3/3"), token(s, "p2", "Theirs", "3/3")
    put(s, "Sandman's Quicksand", "hand")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=find(s, "Sandman's Quicksand").id)
    answer(s)
    from tests.test_rules_attachments import ch

    assert ch(s, mine).pt == (1, 1) and ch(s, theirs).pt == (1, 1)
    roundtrip(s)


def test_a_bare_mayhem_lets_you_play_the_land_from_the_graveyard(cards):
    s = build(cards, p1=("Oscorp Industries", "Faithless Looting"))
    discard(s, "Oscorp Industries")
    land = find(s, "Oscorp Industries")
    assert land.zone == "p1:graveyard"
    act(s, "p1", type="play_land", card_id=land.id)
    assert find(s, "Oscorp Industries").zone == "p1:battlefield"
    roundtrip(s)


def test_web_slinging_returns_a_tapped_creature_and_the_spell_knows_how_it_was_cast(cards):
    s = build(cards, p1=("Spiders-Man, Heroic Horde", "Test Bear"))
    man = put(s, "Spiders-Man, Heroic Horde", "hand")
    bear = put(s, "Test Bear", "battlefield")
    mana(s, G=2, C=4)  # web-slinging {4}{G}{G}
    with pytest.raises(ActionError):  # 702.188a: the returned creature must be tapped
        act(s, "p1", type="cast_spell", card_id=man.id, alt_cost=f"{man.id}:0", cost_choices=[{"component": 0, "cards": [bear.id]}])
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=True)
    act(s, "p1", type="cast_spell", card_id=man.id, alt_cost=f"{man.id}:0", cost_choices=[{"component": 0, "cards": [bear.id]}])
    answer(s)
    assert find(s, "Test Bear").zone == "p1:hand"
    assert find(s, "Spiders-Man, Heroic Horde").zone == "p1:battlefield"
    assert s.state.players["p1"].life == 43  # "if they were cast using web-slinging": 3 life and two 2/1 Spiders
    assert sum(1 for c in s.state.cards.values() if c.is_token and c.name == "Spider" and c.zone == "p1:battlefield") == 2
    roundtrip(s)


def test_the_same_creature_cast_normally_gets_nothing(cards):
    s = build(cards, p1=("Spiders-Man, Heroic Horde",))
    man = put(s, "Spiders-Man, Heroic Horde", "hand")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=man.id)
    answer(s)
    assert s.state.players["p1"].life == 40
    assert not any(c.is_token and c.name == "Spider" for c in s.state.cards.values())
    roundtrip(s)


def test_a_granted_mayhem_uses_the_mana_cost(cards):
    s = build(cards, p1=("Norman Osborn // Green Goblin", "Faithless Looting", "Test Bear"))
    norman = put(s, "Norman Osborn // Green Goblin", "battlefield")
    act(s, "p1", type="set_face", card_id=norman.id, face=1)  # Goblin Formula: each nonland card in your graveyard has mayhem
    discard(s, "Test Bear")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=find(s, "Test Bear").id)
    answer(s)
    assert find(s, "Test Bear").zone == "p1:battlefield"
    roundtrip(s)


def test_a_granted_web_slinging_casts_a_legendary_colored_spell_for_its_cost(cards):
    s = build(cards, p1=("Peter Parker // Amazing Spider-Man", "Spider-UK", "Test Bear"))
    peter = put(s, "Peter Parker // Amazing Spider-Man", "battlefield")
    act(s, "p1", type="set_face", card_id=peter.id, face=1)
    uk = put(s, "Spider-UK", "hand")
    bear = put(s, "Test Bear", "battlefield")
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=True)
    mana(s, G=1, W=1, U=1)  # web-slinging {G}{W}{U}, not {3}{W}
    from app.rules import casting

    key = next(o["id"] for o in casting.alt_castable(s.state, "p1", uk, s.cards) if "return a tapped creature" in o["label"])
    act(s, "p1", type="cast_spell", card_id=uk.id, alt_cost=key, cost_choices=[{"component": 0, "cards": [bear.id]}])
    answer(s)
    assert find(s, "Spider-UK").zone == "p1:battlefield" and find(s, "Test Bear").zone == "p1:hand"
    roundtrip(s)


def test_airbend_exiles_and_lets_the_owner_cast_it_for_two(cards):
    s = build(cards, p1=("Airbending Lesson", "Test Bear"))
    bear = put(s, "Test Bear", "battlefield")
    lesson = put(s, "Airbending Lesson", "hand")
    mana(s, W=1, C=2)  # {2}{W}
    act(s, "p1", type="cast_spell", card_id=lesson.id, targets=[bear.id])
    answer(s)
    assert find(s, "Test Bear").zone == "p1:exile"  # 701.65a
    mana(s, C=1)
    with pytest.raises(ActionError):  # {2} rather than {2}{G}
        act(s, "p1", type="cast_spell", card_id=bear.id)
    mana(s, C=1)  # (the pool keeps the first one: {2} in all)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    answer(s)
    assert find(s, "Test Bear").zone == "p1:battlefield"
    roundtrip(s)


def test_airbend_gives_a_token_nothing_to_cast(cards):
    s = build(cards, p1=("Airbending Lesson",))
    tok = token(s, "p1", "Soldier", "1/1")
    lesson = put(s, "Airbending Lesson", "hand")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=lesson.id, targets=[tok.id])
    answer(s)
    assert tok.id not in s.state.cards or s.state.cards[tok.id].zone.endswith("exile")
    assert not s.state.rules.permissions
    roundtrip(s)


def test_airbend_by_a_trigger_names_the_creature_that_became_the_target(cards):
    s = build(cards, p1=("Airbending Lesson", "Monk Gyatso", "Test Bear"))
    put(s, "Monk Gyatso", "battlefield")
    bear = put(s, "Test Bear", "battlefield")
    lesson = put(s, "Airbending Lesson", "hand")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=lesson.id, targets=[bear.id])
    for _ in range(8):  # Gyatso's trigger: "you may airbend that creature"
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    assert find(s, "Test Bear").zone == "p1:exile"
    assert any(p.pay == "{2}" and p.card == bear.id for p in s.state.rules.permissions)
    roundtrip(s)


def travel(s, name, picks, how):
    """Cast ``name`` (time travel), choose the objects ``picks`` and for each answer ``how`` ("add" / "remove")."""
    s.state.players["p1"].mana = {}
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=find(s, name).id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        if d.kind == "choose_cards":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id in picks])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[how])
        if (d.resume or {}).get("step") == "time_travel_each" and not d.resume["left"][1:]:
            break


def test_time_travel_adds_a_time_counter_to_a_suspended_card(cards):
    s = build(cards, p1=("Rift Bolt", "Wibbly-wobbly, Timey-wimey"))
    bolt = put(s, "Rift Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=bolt.id, ability=1)  # Suspend 1—{R}
    put(s, "Wibbly-wobbly, Timey-wimey", "hand")
    s.state.players["p1"].mana = {}
    travel(s, "Wibbly-wobbly, Timey-wimey", {bolt.id}, "add")
    answer(s)
    assert s.state.cards[bolt.id].counters == {"time": 2}  # 701.56a
    assert find(s, "Wibbly-wobbly, Timey-wimey").zone == "p1:graveyard"
    roundtrip(s)


def test_time_travel_removing_the_last_counter_lets_you_cast_the_suspended_card(cards):
    s = build(cards, p1=("Rift Bolt", "Wibbly-wobbly, Timey-wimey"))
    bolt = put(s, "Rift Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=bolt.id, ability=1)
    put(s, "Wibbly-wobbly, Timey-wimey", "hand")
    travel(s, "Wibbly-wobbly, Timey-wimey", {bolt.id}, "remove")
    for _ in range(12):  # the time travel resolves, then 702.62c's trigger: "you may cast it without paying its mana cost"
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_one" and "yes" in [o.id for o in d.options]:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
    assert s.state.players["p2"].life == 37  # Rift Bolt, cast without paying {2}{R}
    assert find(s, "Rift Bolt").zone == "p1:graveyard"
    roundtrip(s)


def test_time_travel_with_nothing_to_choose_does_nothing(cards):
    s = build(cards, p1=("Wibbly-wobbly, Timey-wimey",))
    put(s, "Wibbly-wobbly, Timey-wimey", "hand")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=find(s, "Wibbly-wobbly, Timey-wimey").id)
    answer(s)
    assert find(s, "Wibbly-wobbly, Timey-wimey").zone == "p1:graveyard"
    roundtrip(s)


def test_time_travel_on_a_permanent_removing_the_last_counter_triggers_vanishing(cards):
    s = build(cards, p1=("Aven Riftwatcher", "Wibbly-wobbly, Timey-wimey"))
    bird = put(s, "Aven Riftwatcher", "battlefield")
    act(s, "p1", type="counter", card_ids=[bird.id], kind="time", delta=1)
    put(s, "Wibbly-wobbly, Timey-wimey", "hand")
    travel(s, "Wibbly-wobbly, Timey-wimey", {bird.id}, "remove")
    answer(s)
    assert find(s, "Aven Riftwatcher").zone == "p1:graveyard"  # 702.63a: sacrificed when the last time counter is removed
    roundtrip(s)
