"""Wave 27D: activated abilities that work from the hand or the command zone (CR 2026-09-25). Real Oracle text; every scenario checks
the replay and a save and a load.

* 113.6m: an ability whose effect moves its own object out of a zone works only in that zone: "Put this card from your hand onto the
  battlefield." (Talon Gates of Madara, Urban Retreat) from the hand, "Put Derevi onto the battlefield from the command zone." from there.
* 602.2 / 601.2h: the ability is activated and its costs paid (a mana cost, "Return a tapped creature you control to its owner's hand"),
  then it goes on the stack; the card is put onto the battlefield as the ability resolves (400.7: only if it is still that object there).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.casting import activatable
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

REAL = [
    ("Talon Gates of Madara", "", "Land", None, None,
     "When this land enters, up to one target creature phases out.\n{T}: Add {C}.\n{1}, {T}: Add one mana of any color.\n"
     "{4}: Put this card from your hand onto the battlefield."),
    ("Urban Retreat", "", "Land", None, None,
     "This land enters tapped.\n{T}: Add {G}, {W}, or {U}.\n{2}, Return a tapped creature you control to its owner's hand: Put this card from your hand onto the battlefield. Activate only as a sorcery."),
    ("Emry, Lurker of the Loch", "{2}{U}", "Legendary Creature — Merfolk Wizard", "1", "2",
     "Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)\nWhen Emry enters, mill four cards.\n"
     "{T}: Choose target artifact card in your graveyard. You may cast that card this turn. (You still pay its costs. Timing rules still apply.)"),
    ("Horde of Notions", "{W}{U}{B}{R}{G}", "Legendary Creature — Elemental", "5", "5",
     "Vigilance, trample, haste\n{W}{U}{B}{R}{G}: You may play target Elemental card from your graveyard without paying its mana cost."),
    ("Probe Elemental", "{5}", "Creature — Elemental", "3", "3", "Trample"),
    ("Derevi, Empyrial Tactician", "{G}{W}{U}", "Legendary Creature — Bird Shaman", "2", "3",
     "Flying\nWhen Derevi enters and whenever a creature you control deals combat damage to a player, you may tap or untap target permanent.\n"
     "{1}{G}{W}{U}: Put Derevi onto the battlefield from the command zone."),
]
EXTRA = [card(n, set_code="t27d", number=f"T{i:02d}", mana_cost=mc, cmc=float(len(mc.replace("{", "").split("}")) - 1), type_line=tl,
              colors=["G"], color_identity=["G"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [r[0] for r in REAL if r[0] not in ("Probe Elemental",)])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def listed(s, card_id):
    return [a["ability"] for a in activatable(s.state, "p1", s.cards) if a["card_id"] == card_id]


def run(s):
    settle(s)
    while s.state.zones.get("stack"):
        act(s, "p1", type="pass_priority")
        act(s, "p2", type="pass_priority")
        settle(s)


def test_talon_gates_enter_from_the_hand(cards):
    s = build(cards, ["Talon Gates of Madara"])
    gates = to_hand(s, "Talon Gates of Madara")
    assert listed(s, gates.id) == []  # (no mana)
    mana(s, C=4)
    assert listed(s, gates.id) == [3]
    act(s, "p1", type="activate_ability", card_id=gates.id, ability=3)
    run(s)
    assert zone_of(s, "Talon Gates of Madara") == "p1:battlefield"
    assert s.state.players["p1"].mana == {}
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 0  # 305.4: put onto the battlefield, not played
    check(s)


def test_talon_gates_only_from_the_hand(cards):
    s = build(cards, ["Talon Gates of Madara"])
    gates = put(s, "Talon Gates of Madara")
    mana(s, C=4)
    assert 3 not in listed(s, gates.id)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=gates.id, ability=3)
    check(s)


def test_urban_retreat_returns_a_tapped_creature_as_a_cost(cards):
    s = build(cards, ["Urban Retreat", "Llanowar Elves"])
    retreat = to_hand(s, "Urban Retreat")
    bear = put(s, "Llanowar Elves")
    mana(s, C=2)
    assert listed(s, retreat.id) == []  # (no tapped creature to return)
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=True)
    assert listed(s, retreat.id) == [2]
    act(s, "p1", type="activate_ability", card_id=retreat.id, ability=2)
    assert s.state.cards[bear.id].zone == "p1:hand"  # paid as the cost
    run(s)
    assert zone_of(s, "Urban Retreat") == "p1:battlefield"
    check(s)


def test_derevi_from_the_command_zone(cards):
    p1 = deck(cards, "Derevi, Empyrial Tactician", [(10, "Forest")])
    p2 = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=p1), PlayerSetup("Bob", cards=p2)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    derevi = card_named(s, "Derevi, Empyrial Tactician")
    assert derevi.zone == "p1:command"
    assert listed(s, derevi.id) == []
    mana(s, G=1, W=1, U=1, C=1)
    assert listed(s, derevi.id) == [2]
    act(s, "p1", type="activate_ability", card_id=derevi.id, ability=2)
    run(s)
    assert zone_of(s, "Derevi, Empyrial Tactician") == "p1:battlefield"
    check(s)


def test_derevi_not_from_the_hand(cards):
    s = build(cards, ["Derevi, Empyrial Tactician"])
    derevi = to_hand(s, "Derevi, Empyrial Tactician")
    mana(s, G=1, W=1, U=1, C=1)
    assert listed(s, derevi.id) == []
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=derevi.id, ability=2)


def to_gy(s, name):
    c = card_named(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def ready(s, name):
    s.state.rules.controlled_since[card_named(s, name).id].turn = 0


def test_emry_chooses_an_artifact_and_may_cast_it_this_turn(cards):
    s = build(cards, ["Emry, Lurker of the Loch", "Sol Ring"])
    ring = to_gy(s, "Sol Ring")
    emry = put(s, "Emry, Lurker of the Loch")
    ready(s, "Emry, Lurker of the Loch")
    act(s, "p1", type="activate_ability", card_id=emry.id, ability=2, targets=[ring.id])
    run(s)
    assert s.state.cards[ring.id].zone == "p1:graveyard"  # (chosen, not moved)
    assert [p.card for p in s.state.rules.permissions] == [ring.id]
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    run(s)
    assert zone_of(s, "Sol Ring") == "p1:battlefield"
    check(s)


def test_emry_permission_ends_with_the_turn(cards):
    s = build(cards, ["Emry, Lurker of the Loch", "Sol Ring"])
    ring = to_gy(s, "Sol Ring")
    emry = put(s, "Emry, Lurker of the Loch")
    ready(s, "Emry, Lurker of the Loch")
    act(s, "p1", type="activate_ability", card_id=emry.id, ability=2, targets=[ring.id])
    run(s)
    for _ in range(40):
        if s.state.turn.number > 1:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.number > 1 and s.state.rules.permissions == []
    check(s)


# -- review (wave 27D) --
def seen_by(s, viewer, c):
    import json

    return c.name in json.dumps(s.view(viewer), default=str)


def test_talon_gates_is_revealed_while_its_ability_is_on_the_stack(cards):
    s = build(cards, ["Talon Gates of Madara"])
    gates = to_hand(s, "Talon Gates of Madara")
    assert not seen_by(s, "p2", gates)  # (the hand is private)
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=gates.id, ability=3)
    (sid,) = s.state.zones["stack"]  # 602.2a / 701.20a: revealed — the ability on the stack names its card for everyone
    assert s.view("p2")["cards"][sid]["ability"]["source_name"] == "Talon Gates of Madara"
    assert gates.id not in s.view("p2")["cards"]  # (the hand itself stays hidden)
    run(s)
    assert zone_of(s, "Talon Gates of Madara") == "p1:battlefield"
    check(s)


def test_talon_gates_second_activation_does_nothing_once_the_card_left_the_hand(cards):
    s = build(cards, ["Talon Gates of Madara"])
    gates = to_hand(s, "Talon Gates of Madara")
    mana(s, C=8)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=gates.id, ability=3)
    act(s, "p1", type="activate_ability", card_id=gates.id, ability=3)  # (holding priority: two on the stack)
    assert len(s.state.zones["stack"]) == 2
    run(s)  # the second one puts it onto the battlefield; then the first finds no card in the hand (400.7): nothing happens
    assert not s.state.zones.get("stack")
    assert zone_of(s, "Talon Gates of Madara") == "p1:battlefield"
    assert s.state.players["p1"].mana == {}
    check(s)


def test_urban_retreat_only_as_a_sorcery(cards):
    s = build(cards, ["Urban Retreat", "Llanowar Elves", "Grizzly Bears"])
    retreat = to_hand(s, "Urban Retreat")
    elves = [put(s, "Llanowar Elves"), put(s, "Grizzly Bears")]
    act(s, "p1", type="tap", card_ids=[c.id for c in elves], tapped=True)
    mana(s, C=4)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=retreat.id, ability=2)
    d = s.state.rules.decision  # (which tapped creature returns: the cost's choice, 601.2h)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[elves[0].id])
    assert s.state.zones.get("stack")  # (the stack isn't empty now: "Activate only as a sorcery" fails, 602.5d / 307.1)
    assert listed(s, retreat.id) == []
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=retreat.id, ability=2)
    run(s)
    assert zone_of(s, "Urban Retreat") == "p1:battlefield"
    assert s.state.cards[retreat.id].tapped  # ("This land enters tapped." applies to a land put onto the battlefield too, 614.1c)
    assert s.state.cards[elves[0].id].zone == "p1:hand" and s.state.cards[elves[1].id].zone == "p1:battlefield"
    check(s)


def test_urban_retreat_needs_a_tapped_creature_you_control(cards):
    s = build(cards, ["Urban Retreat"], theirs=["Llanowar Elves"])
    retreat = to_hand(s, "Urban Retreat")
    theirs = put(s, "Llanowar Elves", "p2")
    act(s, "p2", type="tap", card_ids=[theirs.id], tapped=True)
    mana(s, C=2)
    assert listed(s, retreat.id) == []  # (an opponent's tapped creature can't pay it)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=retreat.id, ability=2)


def derevi_table(cards):
    p1 = deck(cards, "Derevi, Empyrial Tactician", [(10, "Forest")])
    p2 = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=p1), PlayerSetup("Bob", cards=p2)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s, card_named(s, "Derevi, Empyrial Tactician")


def test_derevi_from_the_command_zone_is_not_cast(cards):
    s, derevi = derevi_table(cards)
    mana(s, G=1, W=1, U=1, C=1)
    act(s, "p1", type="activate_ability", card_id=derevi.id, ability=2)
    run(s)
    derevi = card_named(s, "Derevi, Empyrial Tactician")
    assert derevi.zone == "p1:battlefield"
    p1 = s.state.players["p1"]
    assert set(p1.commander_tax.values()) == {0} and not p1.commander_casts  # 903.8: only casting it adds the tax
    assert s.state.rules.spells_this_turn("p1", s.state.turn.number) == 0  # (not a spell: no "cast" triggers, 601.2)
    check(s)


def test_derevi_leaving_the_command_zone_leaves_the_ability_nothing_to_do(cards):
    s, derevi = derevi_table(cards)
    mana(s, G=1, W=1, U=1, C=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=derevi.id, ability=2)
    act(s, "p1", type="move", card_ids=[derevi.id], to={"zone": "hand"})  # (in response it leaves the command zone)
    act(s, "p1", type="move", card_ids=[derevi.id], to={"zone": "command"})  # (and returns: a new object, 400.7)
    run(s)
    assert card_named(s, "Derevi, Empyrial Tactician").zone == "p1:command"  # the ability puts nothing onto the battlefield
    check(s)


def test_derevi_ability_refused_for_a_card_not_in_the_command_zone(cards):
    s, derevi = derevi_table(cards)
    mana(s, G=1, W=1, U=1, C=1)
    act(s, "p1", type="move", card_ids=[derevi.id], to={"zone": "graveyard"})
    derevi = card_named(s, "Derevi, Empyrial Tactician")
    assert listed(s, derevi.id) == []
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=derevi.id, ability=2)


def test_emry_target_gone_at_resolution_grants_nothing(cards):
    s = build(cards, ["Emry, Lurker of the Loch", "Sol Ring"])
    ring = to_gy(s, "Sol Ring")
    emry = put(s, "Emry, Lurker of the Loch")
    ready(s, "Emry, Lurker of the Loch")
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=emry.id, ability=2, targets=[ring.id])
    act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "exile"})  # (in response: the target leaves the graveyard)
    act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "graveyard"})  # (and comes back: a new object, 400.7)
    run(s)
    assert s.state.rules.permissions == []  # 608.2b: its only target is illegal — the ability doesn't resolve
    mana(s, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=ring.id)
    check(s)


def test_horde_of_notions_is_played_as_it_resolves(cards):
    # 608.2g: "You may play target … card … without paying its mana cost." is played as the ability resolves (a land among them only with a
    # land play left, 305.2a/305.3 — Tangled Florahedron's back face): wave 28A models it (tests/test_rules_wave28a_play_now.py), so it is no
    # permission for the turn
    assert coverage.of_card_data(cards.resolve("Horde of Notions")).level == "FULL"
