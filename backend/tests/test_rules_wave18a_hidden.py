"""Wave 18A: hidden exile and face-down objects (CR 2026-09-25), real Oracle text.

* Foretell 702.143: the special action (any time you have priority during your turn: pay {2}, exile the card from your hand
  face down), casting it for its foretell cost after the turn has ended, and who may look at it.
Every scenario checks the replay and a save/load round trip; the privacy checks build each player's and a spectator's view.
"""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, until, until_asked
from tests.test_rules_effects import replay_matches
from tests.test_rules_keywords3f import REAL as FACE_DOWN_CARDS
from tests.test_rules_keywords3f import build as build3, ch, hidden_from, named
from tests.test_rules_keywords3f import mana as mana3
from tests.test_rules_keywords3f import to_hand as to_hand3
from tests.test_rules_wave6c_tokens_pumps import build, mana, reloaded, to_hand, token_of

EXTRA = [
    card('Demon Bolt', set_code='tst', number='Y00', mana_cost='{2}{R}', cmc=3.0, type_line='Instant', oracle_text='Demon Bolt deals 4 damage to target creature or planeswalker.\nForetell {R} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)', power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=['Foretell']),  # noqa: E501
    card('Break Open', set_code='tst', number='Y02', mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text='Turn target face-down creature an opponent controls face up.', power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Wall of Deceit', set_code='tst', number='Y03', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Wall', oracle_text="Defender (This creature can't attack.)\n{3}: Turn this creature face down.\nMorph {U} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)", power='0', toughness='5', colors=['U'], color_identity=['U'], keywords=['Morph', 'Defender']),  # noqa: E501
    card('Skirk Alarmist', set_code='tst', number='Y04', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Wizard', oracle_text='Haste\n{T}: Turn target face-down creature you control face up. At the beginning of the next end step, sacrifice it.', power='1', toughness='2', colors=['R'], color_identity=['R'], keywords=['Haste']),  # noqa: E501
    card('Backslide', set_code='tst', number='Y05', mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='Turn target creature with a morph ability face down.\nCycling {U}', power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=['Cycling']),  # noqa: E501
    card('Smoke Teller', set_code='tst', number='Y06', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Human Shaman', oracle_text='{1}{U}: Look at target face-down creature.', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Lens of Clarity', set_code='tst', number='Y07', mana_cost='{1}', cmc=1.0, type_line='Artifact', oracle_text="You may look at the top card of your library and at face-down creatures you don't control any time.", power=None, toughness=None, colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Sumala Sentry', set_code='tst', number='Y08', mana_cost='{G}{W}', cmc=2.0, type_line='Creature — Elf Archer', oracle_text="Reach\nWhenever a face-down permanent you control is turned face up, put a +1/+1 counter on it and a +1/+1 counter on this creature.", power='1', toughness='3', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Reach']),  # noqa: E501
    card('Pine Walker', set_code='tst', number='Y09', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Elemental', oracle_text="Morph {4}{G} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)\nWhenever this creature or another creature you control is turned face up, untap that creature.", power='5', toughness='5', colors=['G'], color_identity=['G'], keywords=['Morph']),  # noqa: E501
    card('Outrageous Robbery', set_code='tst', number='Y10', mana_cost='{X}{B}{B}', cmc=2.0, type_line='Instant', oracle_text="Target opponent exiles the top X cards of their library face down. You may look at and play those cards for as long as they remain exiled. If you cast a spell this way, you may spend mana as though it were mana of any type to cast it.", power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Siphon Insight', set_code='tst', number='Y11', mana_cost='{U}{B}', cmc=2.0, type_line='Instant', oracle_text="Look at the top two cards of target opponent's library. Exile one of them face down and put the other on the bottom of that library. You may play the exiled card for as long as it remains exiled, and you may spend mana as though it were mana of any color to cast that spell.\nFlashback {1}{U}{B}", power=None, toughness=None, colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Flashback']),  # noqa: E501
    card('Ruthless Ripper', set_code='tst', number='Y12', mana_cost='{B}', cmc=1.0, type_line='Creature — Human Assassin', oracle_text='Deathtouch\nMorph—Reveal a black card in your hand. (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)\nWhen this creature is turned face up, target player loses 2 life.', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=['Morph', 'Deathtouch']),  # noqa: E501
    card('Gathan Raiders', set_code='tst', number='Y13', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Creature — Human Warrior', oracle_text='Hellbent — This creature gets +2/+2 as long as you have no cards in hand.\nMorph—Discard a card. (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)', power='3', toughness='3', colors=['R'], color_identity=['R'], keywords=['Morph', 'Hellbent']),  # noqa: E501
    card('Zombie Cutthroat', set_code='tst', number='Y14', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Zombie', oracle_text='Morph—Pay 5 life. (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)', power='3', toughness='4', colors=['B'], color_identity=['B'], keywords=['Morph']),  # noqa: E501
    card("Fortune's Favor", set_code='tst', number='Y15', mana_cost='{3}{U}', cmc=4.0, type_line='Instant', oracle_text='Target opponent looks at the top four cards of your library and separates them into a face-down pile and a face-up pile. Put one pile into your hand and the other into your graveyard.', power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Riddles in the Dark', set_code='tst', number='Y16', mana_cost='{2}{U}', cmc=3.0, type_line='Instant', oracle_text='Look at the top four cards of your library and separate them into a face-down pile and a face-up pile. An opponent chooses one of the piles. Put that pile into your hand and the other into your graveyard.', power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Doomskar', set_code='tst', number='Y01', mana_cost='{3}{W}{W}', cmc=5.0, type_line='Sorcery', oracle_text='Destroy all creatures.\nForetell {1}{W}{W} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)', power=None, toughness=None, colors=['W'], color_identity=['W'], keywords=['Foretell']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA]
HERMIT = [c for c in FACE_DOWN_CARDS if c["name"] == "Thelonite Hermit"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *HERMIT], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def to_own_turn(s, n):
    until(s, lambda s: s.state.turn.number >= n and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")


def blob(s, pid):
    return json.dumps(s.view(pid))


def test_foretell_then_cast_for_the_foretell_cost_on_a_later_turn(cards):
    s = build(cards, "Demon Bolt")
    bolt = to_hand(s, "Demon Bolt")
    bear = token_of(s, "p2", "Bear", "Token Creature — Bear", "2/2")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=bolt.id, ability=1)  # the foretell special action (702.143b)
    assert s.state.cards[bolt.id].zone == "p1:foretell"
    # 702.143a: its owner alone may look at it; nobody else's view (or a spectator's) names it
    for viewer in ("p2", SPECTATOR):
        assert "Demon Bolt" not in blob(s, viewer) and bolt.card_id not in blob(s, viewer)
    assert "Demon Bolt" in blob(s, "p1")
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bear.id])  # 702.143a: not the turn it was foretold
    to_own_turn(s, 3)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bear.id])  # for {R}, not {2}{R}
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and bear.id not in s.state.zones["p2:battlefield"]
    assert bolt.id not in s.state.rules.foretold
    check(s)


def test_foretold_card_costs_its_foretell_cost_only(cards):
    s = build(cards, "Doomskar")
    doom = to_hand(s, "Doomskar")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=doom.id, ability=1)
    to_own_turn(s, 3)
    mana(s, W=2)  # {1}{W}{W} needs three mana
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=doom.id)
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=doom.id)
    settle(s)
    assert s.state.cards[doom.id].zone == "p1:graveyard"
    check(s)


def test_foretell_only_during_your_turn(cards):
    s = build(cards, "Demon Bolt")
    bolt = to_hand(s, "Demon Bolt")
    mana(s, C=2)
    until(s, lambda s: s.state.turn.active_player == "p2")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=bolt.id, ability=1)


def test_break_open_turns_an_opponents_face_down_creature_up_and_it_triggers(cards):
    s = build3(cards, "Break Open", bob=("Thelonite Hermit",), players=2)
    act(s, "p1", type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")  # Bob's turn
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    hermit = to_hand3(s, "Thelonite Hermit", "p2")
    mana3(s, "p2", C=3)
    act(s, "p2", type="cast_spell", card_id=hermit.id, face_down=True)
    settle(s)
    assert s.state.cards[hermit.id].face_down and s.state.cards[hermit.id].zone == "p2:battlefield"
    for viewer in ("p1", SPECTATOR):  # 708.5: only its controller may look at it
        assert hidden_from(s, viewer, hermit)
    assert not hidden_from(s, "p2", hermit)
    brk = to_hand3(s, "Break Open", "p1")
    act(s, "p2", type="pass_priority")  # (Alice gets priority in Bob's main phase)
    mana3(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=brk.id, targets=[hermit.id])
    settle(s)
    assert not s.state.cards[hermit.id].face_down and ch(s, hermit).name == "Thelonite Hermit"
    assert "Thelonite Hermit" in blob(s, "p1")  # now face up: public
    assert sum(1 for c in s.state.cards.values() if c.name == "Saproling" and c.zone == "p2:battlefield") == 4  # 702.37e: turned face up
    check(s)


def test_turn_face_down_then_up_with_the_morph_cost(cards):
    s = build(cards, "Wall of Deceit")
    wall = to_hand(s, "Wall of Deceit")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=wall.id)
    settle(s)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=wall.id, ability=1)  # {3}: Turn this creature face down.
    settle(s)
    c = s.state.cards[wall.id]
    assert c.face_down and c.face_down_kind == "generic"
    assert hidden_from_session(s, "p2", wall)
    act(s, "p1", type="activate_ability", card_id=wall.id, ability=1) if False else None
    mana(s, U=1)
    act(s, "p1", type="turn_face_up", card_id=wall.id)  # 702.37e: its morph cost {U}
    assert not s.state.cards[wall.id].face_down
    check(s)


def hidden_from_session(s, pid, c):
    """The card's own entry in the view (a log line may keep naming it: it was face up and public when it was turned over)."""
    entry = json.dumps(s.view(pid)["cards"].get(c.id, {}))
    return c.name not in entry and c.card_id not in entry


def test_backslide_turns_a_creature_with_a_morph_ability_face_down(cards):
    s = build(cards, "Wall of Deceit", "Backslide")
    wall = to_hand(s, "Wall of Deceit")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=wall.id)
    settle(s)
    slide = to_hand(s, "Backslide")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=slide.id, targets=[wall.id])
    settle(s)
    assert s.state.cards[wall.id].face_down and hidden_from_session(s, "p2", wall)
    check(s)


def face_down_hermit(s):
    """Bob's Thelonite Hermit on his battlefield face down (the table tool; the rules treat it as any face-down morph)."""
    hermit = named(s, "Thelonite Hermit", "p2")
    act(s, "p2", type="move", card_ids=[hermit.id], to={"player": "p2", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
    return hermit


def test_turned_face_up_triggers_of_other_permanents(cards):
    s = build3(cards, "Sumala Sentry", "Thelonite Hermit", "Pine Walker", players=2)
    sentry = to_hand3(s, "Sumala Sentry", "p1")
    act(s, "p1", type="move", card_ids=[sentry.id], to={"player": "p1", "zone": "battlefield"})
    hermit = named(s, "Thelonite Hermit", "p1")
    act(s, "p1", type="move", card_ids=[hermit.id], to={"player": "p1", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
    walker = named(s, "Pine Walker", "p1")
    act(s, "p1", type="move", card_ids=[walker.id], to={"player": "p1", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
    mana3(s, "p1", G=2, C=3)
    act(s, "p1", type="turn_face_up", card_id=hermit.id)  # 702.37e: {3}{G}{G}
    settle(s)
    assert not s.state.cards[hermit.id].face_down
    assert s.state.cards[hermit.id].counters.get("+1/+1") == 1 and s.state.cards[sentry.id].counters.get("+1/+1") == 1
    assert sum(1 for c in s.state.cards.values() if c.name == "Saproling" and c.zone == "p1:battlefield") == 4
    check(s)


def test_outrageous_robbery_exiles_unseen_cards_only_the_caster_may_look_at(cards):
    from tests.test_rules_wave9b_exile_permission import answer, build as build9, put as put9

    s = build9(cards, p1=("Outrageous Robbery",), p2=("Ambush Viper", "Lightning Bolt"))
    robbery = put9(s, "Outrageous Robbery", "hand")
    bolt = put9(s, "Lightning Bolt", "library", pid="p2", position="top")
    viper = put9(s, "Ambush Viper", "library", pid="p2", position="top")
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=robbery.id, x_value=2, targets=["p2"])
    answer(s)
    for c in (viper, bolt):
        assert s.state.cards[c.id].zone == "p2:exile" and s.state.cards[c.id].face_down and s.state.cards[c.id].unseen
        # 406.3a: nobody has looked yet; the caster does at once ("look at and play"), the owner who exiled them blind and everyone else never
        assert s.view("p1")["cards"][c.id].get("name") == c.name
        for viewer in ("p2", SPECTATOR):
            assert c.name not in json.dumps(s.view(viewer)) and c.card_id not in json.dumps(s.view(viewer))
    assert {p.card for p in s.state.rules.permissions} == {viper.id, bolt.id}
    assert all(p.spend == "type" for p in s.state.rules.permissions)
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=viper.id)  # any type of mana pays for the {1}{G} creature (609.4b)
    answer(s)
    assert s.state.cards[viper.id].zone == "p1:battlefield" and s.state.cards[bolt.id].face_down
    check(s)


def test_siphon_insight_privacy_while_choosing_and_after(cards):
    from tests.test_rules_wave9b_exile_permission import answer, build as build9, put as put9

    s = build9(cards, p1=("Siphon Insight",), p2=("Ambush Viper", "Lightning Bolt"))
    siphon = put9(s, "Siphon Insight", "hand")
    bolt = put9(s, "Lightning Bolt", "library", pid="p2", position="top")
    viper = put9(s, "Ambush Viper", "library", pid="p2", position="top")
    mana(s, U=1, B=1)
    act(s, "p1", type="cast_spell", card_id=siphon.id, targets=["p2"])
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    assert {o.card_id for o in d.options} == {viper.id, bolt.id}  # Alice looks at the top two (701.20e)
    for viewer in ("p2", SPECTATOR):  # mid-decision: nothing about the two cards reaches Bob or a spectator
        seen = json.dumps(s.view(viewer))
        for c in (viper, bolt):
            assert c.name not in seen and c.card_id not in seen
        assert "options" not in s.view(viewer)["rules"]["decision"]
    answer(s, pick=viper.id)
    assert s.state.cards[viper.id].zone == "p2:exile" and s.state.cards[viper.id].face_down
    assert s.view("p1")["cards"][viper.id].get("name") == "Ambush Viper"
    for viewer in ("p2", SPECTATOR):
        seen = json.dumps(s.view(viewer))
        assert "Ambush Viper" not in seen and "Lightning Bolt" not in seen
    assert s.state.zones["p2:library"][-1] == bolt.id
    check(s)


def cast_face_down(s, name, pid="p1"):
    c = to_hand3(s, name, pid)
    mana3(s, pid, C=3)
    act(s, pid, type="cast_spell", card_id=c.id, face_down=True)
    settle(s)
    assert s.state.cards[c.id].face_down
    return c


def test_non_mana_morph_costs(cards):
    # Ruthless Ripper: reveal a black card from your hand (the choice is private; the revealed card is shown to everyone)
    s = build3(cards, "Ruthless Ripper", "Gathan Raiders", "Zombie Cutthroat", "Break Open", players=2)
    ripper = cast_face_down(s, "Ruthless Ripper")
    with pytest.raises(ActionError):  # 118.3: no black card to reveal
        act(s, "p1", type="turn_face_up", card_id=ripper.id)
    cutthroat = to_hand3(s, "Zombie Cutthroat")  # a black card
    act(s, "p1", type="turn_face_up", card_id=ripper.id)
    assert not s.state.cards[ripper.id].face_down and s.state.cards[cutthroat.id].zone == "p1:hand"  # (one candidate: no choice asked)
    assert any("Reveal a black card" in json.dumps(l) for l in s.view("p2")["log"])  # 702.37e: the cost is shown to all players
    assert hidden_from_session(s, "p2", cutthroat)  # the card revealed for the cost is hidden again
    settle(s)  # "target player loses 2 life"
    check(s)


def test_discard_and_life_morph_costs(cards):
    s = build3(cards, "Gathan Raiders", "Zombie Cutthroat", "Break Open", players=2)
    raiders = cast_face_down(s, "Gathan Raiders")
    open_ = to_hand3(s, "Break Open")
    cut = to_hand3(s, "Zombie Cutthroat")
    act(s, "p1", type="turn_face_up", card_id=raiders.id)  # Morph—Discard a card: two cards in hand, so Alice chooses (privately)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    assert {o.card_id for o in d.options} == {open_.id, cut.id}
    for viewer in ("p2", SPECTATOR):
        assert "Break Open" not in json.dumps(s.view(viewer)) and "options" not in s.view(viewer)["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[cut.id])
    assert not s.state.cards[raiders.id].face_down and s.state.cards[cut.id].zone == "p1:graveyard"
    # pay 5 life
    s2 = build3(cards, "Zombie Cutthroat", players=2)
    zc = cast_face_down(s2, "Zombie Cutthroat")
    act(s2, "p1", type="turn_face_up", card_id=zc.id)
    assert s2.state.players["p1"].life == 35 and not s2.state.cards[zc.id].face_down
    check(s)
    check(s2)


TOP4 = ("Ambush Viper", "Lightning Bolt", "Giant Growth", "Murder")


def stack_library(s, names, owner="p1"):
    from tests.test_rules_wave9b_exile_permission import put as put9

    return [put9(s, n, "library", pid=owner, position="top") for n in reversed(names)][::-1]  # (names[0] ends on top)


def view_text(s, pid):
    return json.dumps(s.view(pid))


def test_fortunes_favor_the_opponent_separates_and_you_choose_blind(cards):
    from tests.test_rules_wave9b_exile_permission import build as build9, put as put9

    s = build9(cards, p1=("Fortune's Favor", *TOP4), p2=())
    favor = put9(s, "Fortune's Favor", "hand")
    top = stack_library(s, TOP4)
    mana(s, U=4)
    act(s, "p1", type="cast_spell", card_id=favor.id, targets=["p2"])
    d = until_asked(s)
    assert d is not None and d.player == "p2" and {o.card_id for o in d.options} == {c.id for c in top}  # Bob looks at the top four
    for viewer in ("p1", SPECTATOR):  # mid-decision: Alice (whose library it is) and spectators learn nothing about the cards
        assert not any(c.name in view_text(s, viewer) for c in top)
        assert "options" not in s.view(viewer)["rules"]["decision"]
    assert all(c.name not in view_text(s, "p1") for c in top)
    down = [top[1].id, top[3].id]  # Lightning Bolt and Murder face down
    act(s, "p2", type="choose", decision_id=d.id, option_ids=down)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    labels = [o.label for o in d.options]
    assert labels[0] == "Face-down pile: 2 cards" and "Ambush Viper" in labels[1] and "Giant Growth" in labels[1]
    seen = view_text(s, "p1")
    assert "Lightning Bolt" not in seen and "Murder" not in seen  # the face-down pile stays Bob's secret
    for viewer in ("p1", "p2", SPECTATOR):  # the face-up pile is public
        assert "Ambush Viper" in view_text(s, viewer)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["down"])
    settle(s)
    hand = set(s.state.zones["p1:hand"])
    assert {top[1].id, top[3].id} <= hand and s.state.cards[top[0].id].zone == "p1:graveyard"
    assert s.state.cards[top[2].id].zone == "p1:graveyard"  # the other pile is public in the graveyard
    check(s)


def test_riddles_in_the_dark_you_separate_and_the_opponent_chooses_blind(cards):
    from tests.test_rules_wave9b_exile_permission import build as build9, put as put9

    s = build9(cards, p1=("Riddles in the Dark", *TOP4), p2=())
    riddles = put9(s, "Riddles in the Dark", "hand")
    top = stack_library(s, TOP4)
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=riddles.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    for viewer in ("p2", SPECTATOR):
        assert not any(c.name in view_text(s, viewer) for c in top)
        assert "options" not in s.view(viewer)["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[top[2].id])  # Giant Growth face down, the rest face up
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"
    assert [o.label for o in d.options][0] == "Face-down pile: 1 card" and "Giant Growth" not in " ".join(o.label for o in d.options)
    assert "Giant Growth" not in view_text(s, "p2") and "Giant Growth" not in view_text(s, SPECTATOR)
    assert "Ambush Viper" in view_text(s, "p2")  # the face-up pile
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["up"])  # Alice gets the face-up pile; the face-down card goes to her graveyard
    settle(s)
    assert {top[0].id, top[1].id, top[3].id} <= set(s.state.zones["p1:hand"]) and s.state.cards[top[2].id].zone == "p1:graveyard"
    assert "Giant Growth" in view_text(s, "p2")  # revealed in the graveyard
    check(s)


def test_look_at_target_face_down_creature_is_private_to_the_looker(cards):
    s = build3(cards, "Smoke Teller", bob=("Thelonite Hermit",), players=2)
    teller = to_hand3(s, "Smoke Teller", "p1")
    act(s, "p1", type="move", card_ids=[teller.id], to={"player": "p1", "zone": "battlefield"})
    hermit = face_down_hermit(s)
    assert hidden_from(s, "p1", hermit)
    mana3(s, "p1", U=1, C=1)
    act(s, "p1", type="activate_ability", card_id=teller.id, ability=0, targets=[hermit.id])
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    assert "Thelonite Hermit" in blob(s, "p1")  # the looker sees it now ...
    for viewer in ("p2", SPECTATOR):  # ... and nobody else's view of the decision shows anything
        assert "Thelonite Hermit" not in json.dumps(s.view(viewer)["rules"]["decision"])
    assert hidden_from(s, SPECTATOR, hermit) and hidden_from(s, "p2", named(s, "Smoke Teller", "p1")) is False
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["ok"])
    settle(s)
    assert hidden_from_session(s, "p1", hermit) and s.state.cards[hermit.id].face_down  # looking changes nothing (its log line stays)
    check(s)


def test_lens_of_clarity_lets_you_look_at_face_down_creatures_you_dont_control(cards):
    s = build3(cards, "Lens of Clarity", bob=("Thelonite Hermit",), players=2)
    lens = to_hand3(s, "Lens of Clarity", "p1")
    hermit = face_down_hermit(s)
    assert hidden_from(s, "p1", hermit)
    act(s, "p1", type="move", card_ids=[lens.id], to={"player": "p1", "zone": "battlefield"})
    assert "Thelonite Hermit" in blob(s, "p1")  # 708.5 exception: any time, as long as the artifact is there
    assert hidden_from(s, SPECTATOR, hermit)
    assert not hidden_from(s, "p2", hermit)  # (its controller always may)
    act(s, "p1", type="move", card_ids=[lens.id], to={"zone": "graveyard"})
    assert hidden_from(s, "p1", hermit)
    check(s)
