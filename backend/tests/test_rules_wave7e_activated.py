"""Wave 7E: activated abilities, second pass, researched against CR 2026-09-25.

* Creature lands (613.1d-f, 613.4b, 205.1b): "{1}: This land becomes a 1/1 Phyrexian Blinkmoth artifact creature with flying and
  infect until end of turn. It's still a land." (Inkmoth Nexus), "… with ward {3}" (Hall of Storm Giants), "… with vigilance
  and all creature types" (Faceless Haven), "… and can't be blocked this turn" (Dimir Keyrune).
* Snow mana (107.4h, 106.3): {S} is paid with mana from a snow source, by tapping one as the cost is paid.
* "You may tap or untap target creature." as an activated ability (701.26a): Puppeteer.
* "Attach this Equipment to target creature you control." / "Attach target Equipment you control to target creature you
  control." (701.3, not equip): Cranial Plating, Brass Squire.
* "… gains your choice of …" / "… gets +1/-1 or -1/+1 …" (608.2d): Assassin Initiate, Brightling.
* "Switch this creature's power and toughness until end of turn." (613.4d, layer 7d): Phantasmal Fiend, Windreaver.
* "Regenerate target Beast." (701.19a): Krosan Warchief, Ezuri.
* "Target white creature gains persist until end of turn." (702.79a): Antler Skulkin.

Every scenario checks the replay and a reload from the saved history.
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
from tests.test_rules_conditionals import settle
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import build, card_named, chars, mana, pt, put, reloaded
from tests.test_rules_wave7b_activation import ability_index

EXTRA = [
    card('Inkmoth Nexus', set_code='tst', number='X01', mana_cost='', cmc=0.0, type_line='Land', oracle_text="{T}: Add {C}.\n{1}: This land becomes a 1/1 Phyrexian Blinkmoth artifact creature with flying and infect until end of turn. It's still a land. (It deals damage to creatures in the form of -1/-1 counters and to players in the form of poison counters.)", colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Hall of Storm Giants', set_code='tst', number='X02', mana_cost='', cmc=0.0, type_line='Land', oracle_text="If you control two or more other lands, this land enters tapped.\n{T}: Add {U}.\n{5}{U}: Until end of turn, this land becomes a 7/7 blue Giant creature with ward {3}. It's still a land. (Whenever it becomes the target of a spell or ability an opponent controls, counter it unless that player pays {3}.)", colors=[], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Faceless Haven', set_code='tst', number='X03', mana_cost='', cmc=0.0, type_line='Snow Land', oracle_text="{T}: Add {C}.\n{S}{S}{S}: This land becomes a 4/3 creature with vigilance and all creature types until end of turn. It's still a land. ({S} can be paid with one mana from a snow source.)", colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Puppeteer', set_code='tst', number='X04', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Human Wizard', oracle_text='{U}, {T}: You may tap or untap target creature.', power='1', toughness='2', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Cranial Plating', set_code='tst', number='X05', mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +1/+0 for each artifact you control.\n{B}{B}: Attach this Equipment to target creature you control.\nEquip {1}', colors=[], color_identity=['B'], keywords=['Equip']),  # noqa: E501
    card('Brass Squire', set_code='tst', number='X06', mana_cost='{3}', cmc=3.0, type_line='Artifact Creature — Myr', oracle_text='{T}: Attach target Equipment you control to target creature you control.', power='1', toughness='3', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Assassin Initiate', set_code='tst', number='X07', mana_cost='{B}', cmc=1.0, type_line='Creature — Human Assassin', oracle_text='{1}: This creature gains your choice of flying, deathtouch, or lifelink until end of turn.', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Brightling', set_code='tst', number='X08', mana_cost='{1}{W}{W}', cmc=3.0, type_line='Creature — Shapeshifter', oracle_text="{W}: This creature gains vigilance until end of turn.\n{W}: This creature gains lifelink until end of turn.\n{W}: Return this creature to its owner's hand.\n{1}: This creature gets +1/-1 or -1/+1 until end of turn.", power='3', toughness='3', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Phantasmal Fiend', set_code='tst', number='X09', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Illusion', oracle_text="{B}: This creature gets +1/-1 until end of turn.\n{1}{U}: Switch this creature's power and toughness until end of turn.", power='1', toughness='5', colors=['B'], color_identity=['B', 'U'], keywords=[]),  # noqa: E501
    card('Krosan Warchief', set_code='tst', number='X10', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Beast', oracle_text='Beast spells you cast cost {1} less to cast.\n{1}{G}: Regenerate target Beast.', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Regenerate']),  # noqa: E501
    card('Antler Skulkin', set_code='tst', number='X11', mana_cost='{5}', cmc=5.0, type_line='Artifact Creature — Scarecrow', oracle_text="{2}: Target white creature gains persist until end of turn. (When it dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)", power='3', toughness='3', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Dimir Keyrune', set_code='tst', number='X12', mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text="{T}: Add {U} or {B}.\n{U}{B}: This artifact becomes a 2/2 blue and black Horror artifact creature until end of turn and can't be blocked this turn.", colors=[], color_identity=['B', 'U'], keywords=[]),  # noqa: E501
    card('Snow-Covered Forest', set_code='tst', number='X13', mana_cost='', cmc=0.0, type_line='Basic Snow Land — Forest', oracle_text='({T}: Add {G}.)', colors=[], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Hailstorm Valkyrie', set_code='tst', number='X14', mana_cost='{3}{B}', cmc=4.0, type_line='Snow Creature — Angel Wizard', oracle_text='Flying, trample\n{S}{S}: This creature gets +2/+2 until end of turn. ({S} can be paid with one mana from a snow source.)', power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=['Flying', 'Trample']),  # noqa: E501
    card('Wandering Fumarole', set_code='tst', number='X15', mana_cost='', cmc=0.0, type_line='Land', oracle_text='This land enters tapped.\n{T}: Add {U} or {R}.\n{2}{U}{R}: Until end of turn, this land becomes a 1/4 blue and red Elemental creature with "{0}: Switch this creature\'s power and toughness until end of turn." It\'s still a land.', colors=[], color_identity=['R', 'U'], keywords=[]),  # noqa: E501
    card('Swarmyard', set_code='tst', number='X16', mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{T}: Regenerate target Insect, Rat, Spider, or Squirrel. (The next time it would be destroyed this turn, instead tap it, remove it from combat, and heal all damage on it.)', colors=[], color_identity=[], keywords=['Heal', 'Regenerate']),  # noqa: E501
    card('Suntail Hawk', set_code='tst', number='X01', mana_cost='{W}', cmc=1.0, type_line='Creature — Bird', oracle_text='Flying', power='1', toughness='1', colors=['W'], color_identity=['W'], keywords=['Flying']),  # noqa: E501
    card('Windreaver', set_code='tst', number='X02', mana_cost='{3}{W}{U}', cmc=5.0, type_line='Creature — Elemental', oracle_text="Flying\n{W}: This creature gains vigilance until end of turn.\n{W}: This creature gets +0/+1 until end of turn.\n{U}: Switch this creature's power and toughness until end of turn.\n{U}: Return this creature to its owner's hand.", power='1', toughness='3', colors=['U', 'W'], color_identity=['U', 'W'], keywords=['Flying']),  # noqa: E501
    card('Ezuri, Renegade Leader', set_code='tst', number='X03', mana_cost='{1}{G}{G}', cmc=3.0, type_line='Legendary Creature — Elf Warrior', oracle_text='{G}: Regenerate another target Elf.\n{2}{G}{G}{G}: Elf creatures you control get +3/+3 and gain trample until end of turn.', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Regenerate']),  # noqa: E501
    card('Silvercoat Lion', set_code='tst', number='X20', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Cat', oracle_text='', power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_definitions_are_full():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in ("Snow-Covered Forest", "Silvercoat Lion"):
            continue
        chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
        assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def activate(s, c, needle, **kw):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability_index(s, c, needle), **kw)
    settle(s)


def test_inkmoth_nexus_is_a_creature_with_flying_and_infect_until_end_of_turn(cards):
    s = build(cards, "Inkmoth Nexus")
    nexus = put(s, "Inkmoth Nexus")
    mana(s, C=1)
    activate(s, nexus, "becomes a 1/1")
    c = chars(s, nexus)
    assert c.is_land and c.is_creature and "Artifact" in c.types and pt(s, nexus) == (1, 1)
    assert {"flying", "infect"} <= set(c.keywords)
    assert {"Phyrexian", "Blinkmoth"} <= set(c.subtypes)
    check(s)
    for _ in range(12):  # (to the cleanup step, 514.2)
        if s.state.turn.number > 1:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    c = chars(s, nexus)
    assert c.is_land and not c.is_creature


def test_hall_of_storm_giants_gains_ward(cards):
    s = build(cards, "Hall of Storm Giants")
    hall = put(s, "Hall of Storm Giants")
    mana(s, U=1, C=5)
    activate(s, hall, "7/7")
    assert pt(s, hall) == (7, 7) and chars(s, hall).is_creature
    assert any(a.text.rstrip(".").lower() == "ward {3}" for a in chars(s, hall).abilities)
    check(s)


def test_faceless_haven_needs_snow_sources(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Faceless Haven"), (3, "Snow-Covered Forest"), (6, "Forest")])
    seats = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    haven = put(s, "Faceless Haven")
    idx = ability_index(s, haven, "4/3")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    for f in forests[:3]:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    with pytest.raises(ActionError):  # (three nonsnow lands don't pay {S}{S}{S}, 107.4h)
        act(s, "p1", type="activate_ability", card_id=haven.id, ability=idx)
    mana(s, G=3)
    with pytest.raises(ActionError):  # (mana already in the pool isn't known to come from a snow source)
        act(s, "p1", type="activate_ability", card_id=haven.id, ability=idx)
    snow = [c for c in s.state.cards.values() if c.name == "Snow-Covered Forest" and c.owner == "p1"]
    for f in snow[:3]:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=haven.id, ability=idx)
    settle(s)
    # (Faceless Haven is a snow land itself: two Snow-Covered Forests and the Haven paid {S}{S}{S}; no plain Forest was tapped)
    assert sum(s.state.cards[f.id].tapped for f in snow) == 2 and s.state.cards[haven.id].tapped
    assert not any(s.state.cards[f.id].tapped for f in forests[:3]) and s.state.players["p1"].mana == {"G": 3}
    c = chars(s, haven)
    assert c.is_creature and c.is_land and pt(s, haven) == (4, 3) and "vigilance" in c.keywords
    check(s)


def test_snow_creature_pump_pays_snow_mana(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Hailstorm Valkyrie"), (3, "Snow-Covered Forest")])
    seats = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    bird = put(s, "Hailstorm Valkyrie")
    for f in [c for c in s.state.cards.values() if c.name == "Snow-Covered Forest" and c.owner == "p1"][:2]:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    activate(s, bird, "{S}{S}")
    assert pt(s, bird) == (4, 4)  # (2/2 and +2/+2)
    check(s)


def test_dimir_keyrune_cannot_be_blocked(cards):
    s = build(cards, "Dimir Keyrune")
    rune = put(s, "Dimir Keyrune")
    mana(s, U=1, B=1)
    activate(s, rune, "Horror")
    assert chars(s, rune).is_creature and pt(s, rune) == (2, 2)
    assert any("cant_be_blocked" in e.imposes for e in s.state.rules.effects)  # (509.1b; this turn only)
    check(s)


def test_puppeteer_taps_or_untaps_or_does_nothing(cards):
    s = build(cards, "Puppeteer", "Krosan Warchief")
    pup = put(s, "Puppeteer")
    beast = put(s, "Krosan Warchief")
    s.state.rules.controlled_since[pup.id].turn = 0  # (not summoning sick, 302.6)
    for choice, tapped in (("tap", True), ("untap", False), ("none", False)):
        mana(s, U=1)
        if s.state.cards[beast.id].tapped != (choice == "untap"):
            act(s, "p1", type="tap", card_ids=[beast.id], tapped=choice == "untap")
        act(s, "p1", type="activate_ability", card_id=pup.id, ability=0, targets=[beast.id])
        act(s, "p1", type="tap", card_ids=[pup.id], tapped=False)
        d = None
        for _ in range(8):
            d = s.state.rules.decision
            if d is not None and d.kind == "choose_one":
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert {o.id for o in d.options} == {"tap", "untap", "none"}
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[choice])
        settle(s)
        assert s.state.cards[beast.id].tapped == tapped
    check(s)


def test_cranial_plating_attaches_without_equip_restrictions(cards):
    s = build(cards, "Cranial Plating", "Krosan Warchief")
    plating = put(s, "Cranial Plating")
    beast = put(s, "Krosan Warchief")
    mana(s, B=2)
    activate(s, plating, "Attach this Equipment", targets=[beast.id])
    assert s.state.cards[plating.id].attached_to == beast.id
    check(s)


def test_brass_squire_attaches_a_target_equipment(cards):
    s = build(cards, "Brass Squire", "Cranial Plating", "Krosan Warchief")
    squire = put(s, "Brass Squire")
    plating = put(s, "Cranial Plating")
    beast = put(s, "Krosan Warchief")
    s.state.rules.controlled_since[squire.id].turn = 0  # (not summoning sick, 302.6)
    activate(s, squire, "Attach target Equipment", targets=[plating.id, beast.id], target_counts=[1, 1])
    assert s.state.cards[plating.id].attached_to == beast.id
    check(s)


def test_assassin_initiate_choice_of_keyword(cards):
    s = build(cards, "Assassin Initiate")
    c = put(s, "Assassin Initiate")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=0)
    for _ in range(4):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert [o.label for o in d.options] == ["Flying", "Deathtouch", "Lifelink"]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[1].id])
    settle(s)
    kws = set(chars(s, c).keywords)
    assert "deathtouch" in kws and "flying" not in kws
    check(s)


def test_brightling_chooses_its_pump(cards):
    s = build(cards, "Brightling")
    c = put(s, "Brightling")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability_index(s, c, "+1/-1"))
    for _ in range(4):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[1].id])  # -1/+1
    settle(s)
    assert pt(s, c) == (2, 4)
    check(s)


def test_switch_power_and_toughness_is_applied_last(cards):
    s = build(cards, "Phantasmal Fiend")
    c = put(s, "Phantasmal Fiend")
    mana(s, U=1, C=1, B=1)
    activate(s, c, "Switch")
    assert pt(s, c) == (5, 1)
    activate(s, c, "+1/-1")  # (a later pump is still applied before the switch, 613.4d)
    assert pt(s, c) == (4, 2)
    check(s)


def test_regenerate_target_beast(cards):
    s = build(cards, "Krosan Warchief")
    c = put(s, "Krosan Warchief")
    mana(s, G=2)
    activate(s, c, "Regenerate", targets=[c.id])
    assert s.state.rules.regen_shields
    check(s)


def test_persist_granted_until_end_of_turn_returns_the_creature(cards):
    s = build(cards, "Antler Skulkin", "Silvercoat Lion", "Murder")
    skulkin = put(s, "Antler Skulkin")
    lion = put(s, "Silvercoat Lion")
    mana(s, C=2)
    activate(s, skulkin, "persist", targets=[lion.id])
    murder = card_named(s, "Murder")
    act(s, "p1", type="move", card_ids=[murder.id], to={"zone": "hand"})
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[lion.id])
    settle(s)
    back = s.state.cards[lion.id]
    assert back.zone == "p1:battlefield" and back.counters.get("-1/-1") == 1 and pt(s, lion) == (1, 1)
    check(s)


def test_wandering_fumarole_grants_a_switch_ability(cards):
    s = build(cards, "Wandering Fumarole")
    land = put(s, "Wandering Fumarole")
    mana(s, U=1, R=1, C=2)
    activate(s, land, "1/4")
    assert pt(s, land) == (1, 4)
    granted = next(a.index for a in chars(s, land).abilities if a.text.startswith("{0}"))
    act(s, "p1", type="activate_ability", card_id=land.id, ability=granted)
    settle(s)
    assert pt(s, land) == (4, 1)
    check(s)
