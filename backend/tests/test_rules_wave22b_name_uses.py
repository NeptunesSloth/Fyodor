"""Wave 22B: what a chosen card name is used for besides the prohibitions (CR 201.4, 709.4a): "a spell with the chosen name" as a trigger event and
as a target, and a name chosen as an instruction resolves ("Choose a card name. … a card with the chosen name"). Real Oracle text; every scenario
checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, to_hand, zone_of

EXTRA = [
    real("Silverquill Silencer", "{W}{B}", 2, "Creature — Human Cleric", "As this creature enters, choose a nonland card name.\nWhenever an opponent casts a spell with the chosen name, they lose 3 life and you draw a card.", ("3", "2"), "WB"),
    real("Declaration of Naught", "{U}{U}", 2, "Enchantment", "As this enchantment enters, choose a card name.\n{U}: Counter target spell with the chosen name.", None, "U"),
    real("Demonic Consultation", "{B}", 1, "Instant", "Choose a card name. Exile the top six cards of your library, then reveal cards from the top of your library until you reveal a card with the chosen name. Put that card into your hand and exile all other cards revealed this way.", None, "B"),
    card("Failure // Comply", set_code="tst", number="22B-FC", layout="split", mana_cost="{1}{U} // {W}", cmc=3.0, type_line="Instant // Sorcery",
         colors=["U", "W"], color_identity=["U", "W"], card_faces=[
             {"object": "card_face", "name": "Failure", "mana_cost": "{1}{U}", "type_line": "Instant", "oracle_text": "Return target spell to its owner's hand."},
             {"object": "card_face", "name": "Comply", "mana_cost": "{W}", "type_line": "Sorcery", "oracle_text": "Aftermath (Cast this spell only from your graveyard. Then exile it.)\nChoose a card name. Until your next turn, your opponents can't cast spells with the chosen name."}]),
    real("Sorcerous Spyglass", "{2}", 2, "Artifact", "As this artifact enters, look at an opponent's hand, then choose any card name.\nActivated abilities of sources with the chosen name can't be activated unless they're mana abilities."),
    real("Probe Pinger", "{1}", 1, "Artifact", "{T}: Probe Pinger deals 1 damage to any target."),
    real("Cabal Therapy", "{B}", 1, "Sorcery", "Choose a nonland card name. Target player reveals their hand and discards all cards with that name.\nFlashback\u2014Sacrifice a creature. (You may cast this card from your graveyard by sacrificing a creature in addition to paying its other costs. Then exile this card.)", None, "B"),
    real("Probe Bolt", "{R}", 1, "Instant", "Probe Bolt deals 1 damage to any target.", None, "R"),
    real("Probe Charm", "{G}", 1, "Instant", "You gain 1 life.", None, "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def name_it(s, text, who="p1"):
    d = s.state.rules.decision
    assert d is not None and d.options[0].id == "__name__" and d.player == who
    act(s, who, type="choose", decision_id=d.id, name=text)


def run(s, *names, limit=30):
    """Resolve the stack; a card-name decision is answered with the next of ``names``, any other with its first option."""
    names = list(names)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.options and d.options[0].id == "__name__":
            act(s, d.player, type="choose", decision_id=d.id, name=names.pop(0))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


@pytest.mark.parametrize("name", ["Silverquill Silencer", "Declaration of Naught", "Demonic Consultation", "Failure // Comply", "Cabal Therapy", "Sorcerous Spyglass"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_silverquill_silencer_triggers_on_a_spell_with_the_chosen_name_only(cards):
    s = build(cards, ["Silverquill Silencer", "Probe Bolt", "Probe Charm"], [])
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1, "B": 1, "R": 2, "G": 2})
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Silverquill Silencer").id)
    run(s, "Probe Bolt")
    assert s.state.cards[card_named(s, "Silverquill Silencer").id].choices["Chosen card name"] == "Probe Bolt"
    # its own controller casting the named spell is no opponent's: 603.2 reads "an opponent"
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Charm").id)
    run(s)
    assert life(s, "p1") == 41 and life(s, "p2") == 40
    check(s)


def test_declaration_of_naught_counters_only_a_spell_with_the_chosen_name(cards):
    s = build(cards, ["Declaration of Naught"], ["Probe Bolt", "Probe Charm"])
    act(s, "p1", type="add_mana", player="p1", mana={"U": 3})
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Declaration of Naught").id)
    run(s, "Probe Bolt")
    doc = card_named(s, "Declaration of Naught")
    s.state.rules.prefs["p1"].response = "on"
    s.state.rules.prefs["p2"].response = "on"
    act(s, "p1", type="pass_priority")  # Alice passes with an empty stack: Bob may cast an instant
    bolt = to_hand(s, "Probe Bolt", "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1, "G": 1})
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    assert s.state.cards[bolt.id].zone == "stack" and s.state.rules.priority == "p1"
    act(s, "p1", type="activate_ability", card_id=doc.id, ability=1, targets=[bolt.id])
    run(s)
    assert zone_of(s, "Probe Bolt", "p2") == "p2:graveyard" and life(s, "p1") == 40  # countered: no damage
    check(s)


def test_declaration_of_naught_cant_target_a_spell_without_the_chosen_name(cards):
    s = build(cards, ["Declaration of Naught"], ["Probe Charm"])
    act(s, "p1", type="add_mana", player="p1", mana={"U": 3})
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Declaration of Naught").id)
    run(s, "Probe Bolt")
    doc = card_named(s, "Declaration of Naught")
    s.state.rules.prefs["p1"].response = "on"
    s.state.rules.prefs["p2"].response = "on"
    act(s, "p1", type="pass_priority")
    charm = to_hand(s, "Probe Charm", "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"G": 1})
    act(s, "p2", type="cast_spell", card_id=charm.id)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=doc.id, ability=1, targets=[charm.id])  # not the chosen name: no legal target
    check(s)


def test_demonic_consultation_reveals_until_the_chosen_name(cards):
    s = build(cards, ["Demonic Consultation", "Probe Charm"], [])
    charm = card_named(s, "Probe Charm")
    act(s, "p1", type="move", card_ids=[charm.id], to={"zone": "library", "player": "p1"}, position="bottom")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Demonic Consultation").id)
    run(s, "Probe Charm")
    assert zone_of(s, "Probe Charm") == "p1:hand"  # past the six exiled blind: revealed, kept; everything revealed before it is exiled
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    assert len(exiled) > 6
    check(s)


def test_demonic_consultation_exiles_the_named_card_when_it_is_among_the_top_six(cards):
    s = build(cards, ["Demonic Consultation", "Probe Charm"], [])
    charm = card_named(s, "Probe Charm")
    act(s, "p1", type="move", card_ids=[charm.id], to={"zone": "library", "player": "p1"})  # on top
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Demonic Consultation").id)
    run(s, "Probe Charm")
    assert zone_of(s, "Probe Charm") == "p1:exile"  # exiled face up with the six: it can't be found, so the whole library goes
    check(s)


def test_comply_stops_the_chosen_name_for_opponents_until_your_next_turn(cards):
    s = build(cards, ["Failure // Comply"], ["Probe Bolt"])
    fc = card_named(s, "Failure // Comply")
    act(s, "p1", type="move", card_ids=[fc.id], to={"zone": "graveyard"})
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=fc.id, face=1)  # aftermath: from the graveyard
    run(s, "Probe Bolt")
    from app.rules import cast_limits
    from app.rules import characteristics as chars

    theirs = to_hand(s, "Probe Bolt", "p2")
    assert "can't cast" in cast_limits.cast_problem(s.state, "p2", theirs, chars.of(theirs, s.cards), s.cards)  # 611.2a: Bob can't
    check(s)


def test_cabal_therapy_discards_every_card_with_the_chosen_name_from_the_revealed_hand(cards):
    s = build(cards, ["Cabal Therapy"], ["Probe Bolt", "Probe Charm"])
    hand = [to_hand(s, "Probe Bolt", "p2"), to_hand(s, "Probe Charm", "p2")]
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Cabal Therapy").id, targets=["p2"])
    run(s, "Probe Bolt")
    assert s.state.cards[hand[0].id].zone == "p2:graveyard" and s.state.cards[hand[1].id].zone == "p2:hand"
    check(s)


def test_with_several_opponents_the_looker_picks_whose_hand_first_and_sees_only_that_one(cards):
    import json

    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from app.game.views import SPECTATOR, build_view
    from app.rules.view import decision_view
    from tests.game_helpers import deck, enable

    mk = lambda n, *names: deck(cards, "Krenko, Mob Boss", [*((1, x) for x in names), (9, "Forest")])  # noqa: E731
    state = new_game([PlayerSetup("Alice", cards=mk("a", "Sorcerous Spyglass")), PlayerSetup("Bob", cards=mk("b", "Probe Bolt")),
                      PlayerSetup("Carol", cards=mk("c", "Probe Charm"))], shuffle=False)
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")
    bolt, charm = to_hand(s, "Probe Bolt", "p2"), to_hand(s, "Probe Charm", "p3")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Sorcerous Spyglass").id)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}  # which opponent: the first question
    assert bolt.id not in json.dumps(decision_view(s.state, d, "p1")) and charm.id not in json.dumps(decision_view(s.state, d, "p1"))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    d = s.state.rules.decision
    assert d.options[0].id == "__name__" and {o.card_id for o in d.options[1:]} == {charm.id}  # Carol's hand only
    assert bolt.id not in json.dumps(decision_view(s.state, d, "p1"))  # (not Bob's)
    assert charm.id not in json.dumps(decision_view(s.state, d, "p2")) and "Probe" not in json.dumps(decision_view(s.state, d, "p3"))
    assert "Probe" not in json.dumps(build_view(s.state, SPECTATOR))
    name_it(s, "Probe Bolt")  # any card name: it needn't be one of those looked at
    assert s.state.cards[card_named(s, "Sorcerous Spyglass").id].choices["Chosen card name"] == "Probe Bolt"
    check(s)


def test_look_at_a_hand_then_name_shows_the_hand_to_the_chooser_alone(cards):
    """Sorcerous Spyglass: "look at an opponent's hand, then choose any card name" (701.20e: only the one looking sees it)."""
    import json

    from app.game.views import SPECTATOR, build_view
    from app.rules.view import decision_view

    s = build(cards, ["Sorcerous Spyglass"], ["Probe Bolt", "Probe Charm"])
    bolt, charm = to_hand(s, "Probe Bolt", "p2"), to_hand(s, "Probe Charm", "p2")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Sorcerous Spyglass").id)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p1" and d.options[0].id == "__name__"
    assert {o.card_id for o in d.options[1:]} == {bolt.id, charm.id}  # the looker is shown that hand
    assert "looks at Bob's hand" in " ".join(p.t or "" for e in s.state.log for p in e.parts)
    # nobody else learns anything: not the decision, not the cards (the other viewers' state), not the log
    mine, theirs = json.dumps(decision_view(s.state, d, "p1")), json.dumps(decision_view(s.state, d, "p2"))
    assert "Probe Bolt" in mine and bolt.id in mine
    assert "Probe" not in theirs and bolt.id not in theirs and decision_view(s.state, d, "p2")["kind"] == "waiting"
    watching = json.dumps(build_view(s.state, SPECTATOR))  # a spectator sees neither the hand nor the decision
    assert "Probe Bolt" not in watching and "Probe Charm" not in watching
    assert not (s.state.cards[bolt.id].revealed_to or s.state.cards[charm.id].revealed_to)
    log = " ".join(p.t or "" for e in s.state.log for p in e.parts)
    assert "Probe Bolt" not in log and "Probe Charm" not in log
    name_it(s, "Probe Charm")
    spy = card_named(s, "Sorcerous Spyglass")
    assert s.state.cards[spy.id].choices["Chosen card name"] == "Probe Charm"
    assert not (s.state.cards[bolt.id].revealed_to or s.state.cards[charm.id].revealed_to)  # still in their hand, still hidden
    check(s)
