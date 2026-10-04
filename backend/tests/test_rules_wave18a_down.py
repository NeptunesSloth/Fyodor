"""Wave 18A (2): hidden exile and face-down objects, real Oracle text (CR 2026-09-25).

* 708.4 / 708.2a: a card put onto the battlefield face down (by "return it … face down", "put … onto the battlefield face down") is a 2/2
  face-down creature — or what the instruction says ("2/2 Cyberman artifact creature", "Forest land") — only its controller may look at
  it (708.5), and it is revealed as it leaves (708.9).
* 406.3 / 406.3a: cards exiled face down can't be examined except where an instruction lets a player look (Ugin, Scroll Rack).
* 614.12 / 708.2a: "As this creature enters, turn all other nontoken creatures face down" (Ixidron).
Every scenario checks the replay and a save/load round trip, and builds each player's and a spectator's view mid-decision.
"""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from app.rules.characteristics import face_down_characteristics, parse_spec
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Ashcloud Phoenix', set_code='tst', number='Z20', mana_cost='{2}{R}{R}', cmc=4.0, type_line='Creature — Phoenix', oracle_text='Flying\nWhen this creature dies, return it to the battlefield face down under your control.\nMorph {4}{R}{R} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)\nWhen this creature is turned face up, it deals 2 damage to each player.', power='4', toughness='1', colors=['R'], color_identity=['R'], keywords=['Flying', 'Morph']),  # noqa: E501
    card('Shorecrasher Elemental', set_code='tst', number='Z21', mana_cost='{U}{U}{U}', cmc=3.0, type_line='Creature — Elemental', oracle_text="{U}: Exile this creature, then return it to the battlefield face down under its owner's control.\n{1}: This creature gets +1/-1 or -1/+1 until end of turn.\nMegamorph {4}{U} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its megamorph cost and put a +1/+1 counter on it.)", power='3', toughness='3', colors=['U'], color_identity=['U'], keywords=['Megamorph']),  # noqa: E501
    card('Ixidron', set_code='tst', number='Z22', mana_cost='{3}{U}{U}', cmc=5.0, type_line='Creature — Illusion', oracle_text="As this creature enters, turn all other nontoken creatures face down. (They're 2/2 creatures.)\nIxidron's power and toughness are each equal to the number of face-down creatures on the battlefield.", power='*', toughness='*', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Scroll Rack', set_code='tst', number='Z23', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='{1}, {T}: Exile any number of cards from your hand face down. Put that many cards from the top of your library into your hand. Then look at the exiled cards and put them on top of your library in any order.', power=None, toughness=None, colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Ignorant Bliss', set_code='tst', number='Z24', mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text='Exile all cards from your hand face down. At the beginning of the next end step, return those cards to your hand, then draw a card.', power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Inverter of Truth', set_code='tst', number='Z25', mana_cost='{2}{B}{B}', cmc=4.0, type_line='Creature — Eldrazi', oracle_text='Devoid (This card has no color.)\nFlying\nWhen this creature enters, exile all cards from your library face down, then shuffle all cards from your graveyard into your library.', power='6', toughness='6', colors=[], color_identity=['B'], keywords=['Flying', 'Devoid']),  # noqa: E501
    card('Doomsday Excruciator', set_code='tst', number='Z26', mana_cost='{B}{B}{B}{B}{B}{B}', cmc=6.0, type_line='Creature — Demon', oracle_text='Flying\nWhen this creature enters, if it was cast, each player exiles all but the bottom six cards of their library face down.\nAt the beginning of your upkeep, draw a card.', power='6', toughness='6', colors=['B'], color_identity=['B'], keywords=['Flying']),  # noqa: E501
    card('Ugin, the Ineffable', set_code='tst', number='Z27', mana_cost='{6}', cmc=6.0, type_line='Legendary Planeswalker — Ugin', oracle_text="Colorless spells you cast cost {2} less to cast.\n+1: Exile the top card of your library face down and look at it. Create a 2/2 colorless Spirit creature token. When that token leaves the battlefield, put the exiled card into your hand.\n−3: Destroy target permanent that's one or more colors.", power=None, toughness=None, colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Glitch Interpreter', set_code='tst', number='Z28', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Human Wizard', oracle_text="When this creature enters, if you control no face-down permanents, return this creature to its owner's hand and manifest dread.\nWhenever one or more colorless creatures you control deal combat damage to a player, draw a card.", power='2', toughness='3', colors=['U'], color_identity=['U'], keywords=['Manifest', 'Manifest dread']),  # noqa: E501
    card('Cyber Conversion', set_code='tst', number='Z29', mana_cost='{U}{U}', cmc=2.0, type_line='Instant', oracle_text="Turn target creature face down. It's a 2/2 Cyberman artifact creature.", power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Yedora, Grave Gardener', set_code='tst', number='Z30', mana_cost='{4}{G}', cmc=5.0, type_line='Legendary Creature — Treefolk Druid', oracle_text="Whenever another nontoken creature you control dies, you may return it to the battlefield face down under its owner's control. It's a Forest land. (It has no other types or abilities.)", power='5', toughness='5', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Tezzeret, Cruel Machinist', set_code='tst', number='Z31', mana_cost='{4}{U}{U}', cmc=6.0, type_line='Legendary Planeswalker — Tezzeret', oracle_text="+1: Draw a card.\n0: Until your next turn, target artifact you control becomes a 5/5 creature in addition to its other types.\n−7: Put any number of cards from your hand onto the battlefield face down. They're 5/5 artifact creatures.", power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Cybership', set_code='tst', number='Z32', mana_cost='{6}', cmc=6.0, type_line='Artifact — Vehicle', oracle_text="Flying\nWhenever this Vehicle deals combat damage to a player, put the top two cards of that player's library onto the battlefield face down under your control. They're 2/2 Cyberman artifact creatures.\nCrew 4", power='8', toughness='8', colors=[], color_identity=[], keywords=['Flying', 'Crew']),  # noqa: E501
    card('Ethereal Valkyrie', set_code='tst', number='Z33', mana_cost='{4}{W}{U}', cmc=6.0, type_line='Creature — Spirit Angel', oracle_text='Flying\nWhenever this creature enters or attacks, draw a card, then exile a card from your hand face down. It becomes foretold. Its foretell cost is its mana cost reduced by {2}. (On a later turn, you may cast it for its foretell cost, even if this creature has left the battlefield.)', power='4', toughness='4', colors=['U', 'W'], color_identity=['U', 'W'], keywords=['Flying']),  # noqa: E501
    card('The Foretold Soldier', set_code='tst', number='Z34', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Alien Zombie Soldier', oracle_text="This creature must be blocked if able.\nThis creature can't be blocked by more than one creature.\nWhenever this creature deals damage, exile it face down. It becomes foretold.\nForetell {1}{G} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)", power='6', toughness='6', colors=['G'], color_identity=['G'], keywords=['Foretell']),  # noqa: E501
    card('Ghastly Conscription', set_code='tst', number='Z35', mana_cost='{5}{B}{B}', cmc=7.0, type_line='Sorcery', oracle_text="Exile all creature cards from target player's graveyard in a face-down pile, shuffle that pile, then manifest those cards. (To manifest a card, put it onto the battlefield face down as a 2/2 creature. Turn it face up any time for its mana cost if it's a creature card.)", power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=['Manifest']),  # noqa: E501
    card('Jeskai Infiltrator', set_code='tst', number='Z36', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Human Monk', oracle_text="This creature can't be blocked as long as you control no other creatures.\nWhen this creature deals combat damage to a player, exile it and the top card of your library in a face-down pile, shuffle that pile, then manifest those cards. (To manifest a card, put it onto the battlefield face down as a 2/2 creature. Turn it face up any time for its mana cost if it's a creature card.)", power='2', toughness='3', colors=['U'], color_identity=['U'], keywords=['Manifest']),  # noqa: E501
    card('Become Anonymous', set_code='tst', number='Z37', mana_cost='{2}{U}{U}', cmc=4.0, type_line='Instant', oracle_text="Exile target nontoken creature you own and the top two cards of your library in a face-down pile, shuffle that pile, then cloak those cards. They enter tapped. (To cloak a card, put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)", power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=['Cloak']),  # noqa: E501
    card('Hauntwoods Shrieker', set_code='tst', number='Z38', mana_cost='{1}{G}{G}', cmc=3.0, type_line='Creature — Beast Mutant', oracle_text="Whenever this creature attacks, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\n{1}{G}: Reveal target face-down permanent. If it's a creature card, you may turn it face up.", power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=['Manifest', 'Manifest dread']),  # noqa: E501
    card('Spy Network', set_code='tst', number='Z39', mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text="Look at target player's hand, the top card of that player's library, and any face-down creatures they control. Look at the top four cards of your library, then put them back in any order.", power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Illithid Harvester // Plant Tadpoles', set_code='tst', number='Z40', layout='adventure', mana_cost='{4}{U} // {X}{U}{U}', cmc=5.0, type_line='Creature — Horror // Sorcery — Adventure', colors=['U'], color_identity=['U'], keywords=['Ceremorphosis'], card_faces=[  # noqa: E501
        {"object": "card_face", "name": "Illithid Harvester", "mana_cost": "{4}{U}", "type_line": "Creature — Horror", "oracle_text": "Ceremorphosis — When this creature enters, turn any number of target tapped nontoken creatures face down. They're 2/2 Horror creatures.", "power": "4", "toughness": "4"},  # noqa: E501
        {"object": "card_face", "name": "Plant Tadpoles", "mana_cost": "{X}{U}{U}", "type_line": "Sorcery — Adventure", "oracle_text": "Tap X target creatures. They don't untap during their controllers' next untap steps. (Then exile this card. You may cast the creature later from exile.)"}]),  # noqa: E501
    card('Poison the Cup', set_code='tst', number='Z41', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Instant', oracle_text='Destroy target creature. If this spell was foretold, scry 2.\nForetell {1}{B} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)', power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=['Foretell', 'Scry']),  # noqa: E501
    card('Scroll of Fate', set_code='tst', number='Z42', mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text="{T}: Manifest a card from your hand. (Put that card onto the battlefield face down as a 2/2 creature. Turn it face up any time for its mana cost if it's a creature card.)", power=None, toughness=None, colors=[], color_identity=[], keywords=['Manifest']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def blob(s, viewer):
    return json.dumps(s.view(viewer))


def card_view(s, viewer, c):
    return json.dumps(s.view(viewer)["cards"].get(c.id, {}))


def unseen_by(s, c, *viewers):
    return all(c.name not in card_view(s, v, c) and c.card_id not in card_view(s, v, c) for v in viewers)


def chars_of(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def test_the_spec_of_a_face_down_permanent():
    assert parse_spec("a 2/2 Cyberman artifact creature") == "2/2 Cyberman artifact creature"
    assert parse_spec("5/5 artifact creatures") == "5/5 artifact creature"
    assert parse_spec("a Forest land") == "Forest land"
    assert parse_spec("2/2 Horror creatures") == "2/2 Horror creature"
    assert parse_spec("a Forest creature") is None and parse_spec("2/2 Forest land") is None and parse_spec("a face-down card") is None
    ch = face_down_characteristics("generic", "2/2 Cyberman artifact creature")
    assert ch.name == "" and ch.types == {"Artifact", "Creature"} and ch.subtypes == {"Cyberman"} and (ch.power, ch.toughness) == ("2", "2")
    land = face_down_characteristics("generic", "Forest land")
    assert land.types == {"Land"} and land.subtypes == {"Forest"} and land.power is None and land.abilities  # 305.6: {T}: Add {G}


def test_ashcloud_phoenix_returns_face_down_and_turns_up_with_its_morph_cost(cards):
    s = build(cards, p1=("Ashcloud Phoenix", "Lightning Bolt"))
    phoenix = put(s, "Ashcloud Phoenix", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[phoenix.id])
    answer(s)
    c = s.state.cards[phoenix.id]
    assert c.zone == "p1:battlefield" and c.face_down  # 708.4: it returned face down under Alice's control
    assert unseen_by(s, phoenix, "p2", SPECTATOR) and not unseen_by(s, phoenix, "p1")  # 708.5
    assert (chars_of(s, phoenix).power, chars_of(s, phoenix).toughness) == ("2", "2")
    mana(s, R=2, C=4)
    act(s, "p1", type="turn_face_up", card_id=phoenix.id)  # 702.37e: Morph {4}{R}{R}
    answer(s)
    assert not s.state.cards[phoenix.id].face_down
    assert s.state.players["p1"].life == 38 and s.state.players["p2"].life == 38  # "it deals 2 damage to each player"
    roundtrip(s)


def test_shorecrasher_elemental_flickers_itself_face_down(cards):
    s = build(cards, p1=("Shorecrasher Elemental",))
    elemental = put(s, "Shorecrasher Elemental", "battlefield")
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=elemental.id, ability=0)
    answer(s)
    c = s.state.cards[elemental.id]
    assert c.zone == "p1:battlefield" and c.face_down and c.face_down_kind == "generic"
    assert unseen_by(s, elemental, "p2", SPECTATOR)
    mana(s, U=1, C=4)
    act(s, "p1", type="turn_face_up", card_id=elemental.id)  # megamorph {4}{U}: and a +1/+1 counter
    answer(s)
    assert not s.state.cards[elemental.id].face_down and s.state.cards[elemental.id].counters.get("+1/+1") == 1
    roundtrip(s)


def test_ixidron_turns_the_other_nontoken_creatures_face_down_as_it_enters(cards):
    s = build(cards, p1=("Ixidron", "Grizzly Bears"), p2=("Ambush Viper",))
    bears = put(s, "Grizzly Bears", "battlefield")
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    token = find(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[token.id], to={"player": "p1", "zone": "battlefield"})
    ixidron = put(s, "Ixidron", "hand")
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=ixidron.id)
    answer(s)
    for c in (bears, viper, token):
        assert s.state.cards[c.id].face_down  # 708.2a
    assert not s.state.cards[ixidron.id].face_down
    assert unseen_by(s, viper, "p1", SPECTATOR) and unseen_by(s, bears, "p2", SPECTATOR)
    ch = chars_of(s, ixidron)
    assert (ch.pt or (0, 0)) == (3, 3)  # "equal to the number of face-down creatures on the battlefield"
    roundtrip(s)


def test_scroll_rack_exiles_your_cards_face_down_then_puts_them_back_on_top(cards):
    s = build(cards, p1=("Scroll Rack", "Grizzly Bears", "Ambush Viper", "Giant Growth", "Lightning Bolt", "Murder"))
    rack = put(s, "Scroll Rack", "battlefield")
    bears = put(s, "Grizzly Bears", "hand")
    viper = put(s, "Ambush Viper", "hand")
    growth = put(s, "Giant Growth", "hand")
    top1 = put(s, "Lightning Bolt", "library", position="top")
    top2 = put(s, "Murder", "library", position="top")
    hand = len(s.state.zones["p1:hand"])
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=rack.id, ability=0)
    d = until_asked(s)
    assert d.player == "p1" and {o.card_id for o in d.options} >= {bears.id, viper.id, growth.id}
    for viewer in ("p2", SPECTATOR):  # mid-decision: no card of Alice's hand and no options reach anyone else
        assert "options" not in s.view(viewer)["rules"]["decision"] and "Ambush Viper" not in json.dumps(s.view(viewer)["rules"])
        assert all(unseen_by(s, c, viewer) for c in (bears, viper, growth))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id, viper.id])
    d = until_asked(s)  # the order they go back on top (401.4: a private choice)
    assert d.player == "p1"
    for viewer in ("p2", SPECTATOR):  # the exiled cards are face down: nothing about them reaches anyone but Alice
        assert "options" not in s.view(viewer)["rules"]["decision"] and "Ambush Viper" not in json.dumps(s.view(viewer)["rules"])
        assert all(s.state.cards[c.id].face_down and s.state.cards[c.id].zone == "p1:exile" and unseen_by(s, c, viewer) for c in (bears, viper))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[viper.id, bears.id])
    answer(s)
    for viewer in ("p2", SPECTATOR):  # the log never names a card Alice exiled face down or took into her hand
        text = json.dumps(s.view(viewer)["log"])
        assert not any(n in text for n in ("Ambush Viper", "Grizzly Bears", "Lightning Bolt", "Murder"))
    assert {c for c in s.state.zones["p1:hand"]} >= {top1.id, top2.id}  # "put that many cards from the top of your library into your hand"
    assert len(s.state.zones["p1:hand"]) == hand - 2 + 2
    assert s.state.zones["p1:library"][:2] == [viper.id, bears.id] or s.state.zones["p1:library"][:2] == [bears.id, viper.id]
    assert not any(s.state.cards[c].face_down for c in (bears.id, viper.id))
    roundtrip(s)


def until_asked(s, limit=20):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


def test_ignorant_bliss_exiles_your_hand_face_down_and_returns_it_at_the_end_step(cards):
    s = build(cards, p1=("Ignorant Bliss", "Grizzly Bears", "Giant Growth"))
    bliss = put(s, "Ignorant Bliss", "hand")
    bears = put(s, "Grizzly Bears", "hand")
    growth = put(s, "Giant Growth", "hand")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bliss.id)
    answer(s)
    for c in (bears, growth):
        assert s.state.cards[c.id].zone == "p1:exile" and s.state.cards[c.id].face_down
        assert unseen_by(s, c, "p2", SPECTATOR)
    until(s, lambda s: s.state.cards[bears.id].zone == "p1:hand")  # "at the beginning of the next end step, return those cards"
    assert s.state.cards[growth.id].zone == "p1:hand" and not s.state.cards[bears.id].face_down
    roundtrip(s)


def test_inverter_of_truth_exiles_the_whole_library_face_down(cards):
    s = build(cards, p1=("Inverter of Truth",))
    inverter = put(s, "Inverter of Truth", "hand")
    library = [s.state.cards[c] for c in s.state.zones["p1:library"]]  # (the objects: they are renumbered as they go face down)
    mana(s, B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=inverter.id)
    answer(s)
    exiled = [c for c in library if c.zone == "p1:exile"]
    assert exiled and all(c.face_down and c.unseen for c in exiled)  # 406.3: nobody may look
    for viewer in ("p1", "p2", SPECTATOR):  # not even the one who exiled them
        assert all(unseen_by(s, c, viewer) for c in exiled)
    roundtrip(s)


def test_doomsday_excruciator_only_when_cast(cards):
    s = build(cards, p1=("Doomsday Excruciator",))
    doom = put(s, "Doomsday Excruciator", "hand")
    mana(s, B=6)
    act(s, "p1", type="cast_spell", card_id=doom.id)
    answer(s)
    for pid in ("p1", "p2"):
        assert len(s.state.zones[f"{pid}:library"]) == 6  # all but the bottom six, exiled face down
        assert all(c.face_down and c.unseen for c in s.state.cards.values() if c.zone == f"{pid}:exile" and c.owner == pid)
    roundtrip(s)
    t = build(cards, p1=("Doomsday Excruciator",))
    before = len(t.state.zones["p2:library"])
    put(t, "Doomsday Excruciator", "battlefield")  # not cast: nothing happens
    answer(t)
    assert len(t.state.zones["p2:library"]) == before


def test_ugin_the_ineffable_exiles_face_down_you_look_and_the_token_leaving_gives_it_to_you(cards):
    s = build(cards, p1=("Ugin, the Ineffable", "Lightning Bolt", "Giant Growth"))
    ugin = put(s, "Ugin, the Ineffable", "battlefield")
    top = put(s, "Giant Growth", "library", position="top")
    act(s, "p1", type="activate_ability", card_id=ugin.id, ability=1)  # +1
    answer(s)
    c = s.state.cards[top.id]
    assert c.zone == "p1:exile" and c.face_down
    assert s.view("p1")["cards"][top.id].get("name") == "Giant Growth"  # "and look at it"
    assert unseen_by(s, top, "p2", SPECTATOR)
    spirit = next(x for x in s.state.cards.values() if x.zone == "p1:battlefield" and x.name == "Spirit")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[spirit.id])
    answer(s)
    assert s.state.cards[top.id].zone == "p1:hand"  # "When that token leaves the battlefield, put the exiled card into your hand"
    assert unseen_by(s, top, "p2", SPECTATOR)
    roundtrip(s)


def test_glitch_interpreter_manifests_dread_when_you_control_no_face_down_permanent(cards):
    s = build(cards, p1=("Glitch Interpreter",))
    glitch = put(s, "Glitch Interpreter", "hand")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=glitch.id)
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1"
    for viewer in ("p2", SPECTATOR):  # mid-decision: the two cards looked at stay secret
        assert "options" not in s.view(viewer)["rules"]["decision"]
    answer(s)
    assert s.state.cards[glitch.id].zone == "p1:hand"
    assert any(c.face_down and c.zone == "p1:battlefield" for c in s.state.cards.values())
    roundtrip(s)


def test_cyber_conversion_turns_a_creature_face_down_as_a_cyberman_artifact_creature(cards):
    s = build(cards, p1=("Cyber Conversion",), p2=("Ambush Viper",))
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    conv = put(s, "Cyber Conversion", "hand")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=conv.id, targets=[viper.id])
    answer(s)
    c = s.state.cards[viper.id]
    assert c.face_down and c.face_down_as == "2/2 Cyberman artifact creature"
    ch = chars_of(s, viper)
    assert ch.types == {"Artifact", "Creature"} and ch.subtypes == {"Cyberman"} and (ch.power, ch.toughness) == ("2", "2")
    assert unseen_by(s, viper, "p1", SPECTATOR) and not unseen_by(s, viper, "p2")
    roundtrip(s)


def test_yedora_returns_a_dying_creature_face_down_as_a_forest_land(cards):
    s = build(cards, p1=("Yedora, Grave Gardener", "Ambush Viper", "Lightning Bolt"))
    put(s, "Yedora, Grave Gardener", "battlefield")
    viper = put(s, "Ambush Viper", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[viper.id])
    answer(s)
    c = s.state.cards[viper.id]
    assert c.zone == "p1:battlefield" and c.face_down and c.face_down_as == "Forest land"
    ch = chars_of(s, viper)
    assert ch.types == {"Land"} and ch.subtypes == {"Forest"} and not ch.is_creature
    assert unseen_by(s, viper, "p2", SPECTATOR)
    roundtrip(s)


def test_tezzeret_puts_cards_from_your_hand_onto_the_battlefield_face_down_as_5_5_artifact_creatures(cards):
    s = build(cards, p1=("Tezzeret, Cruel Machinist", "Grizzly Bears", "Giant Growth"))
    tez = put(s, "Tezzeret, Cruel Machinist", "battlefield")
    act(s, "p1", type="counter", card_ids=[tez.id], kind="loyalty", delta=7)
    bears = put(s, "Grizzly Bears", "hand")
    growth = put(s, "Giant Growth", "hand")
    act(s, "p1", type="activate_ability", card_id=tez.id, ability=2)  # −7
    d = until_asked(s)
    assert d.player == "p1"
    for viewer in ("p2", SPECTATOR):
        assert "options" not in s.view(viewer)["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id, growth.id])
    answer(s)
    for c in (bears, growth):
        assert s.state.cards[c.id].zone == "p1:battlefield" and s.state.cards[c.id].face_down
        ch = chars_of(s, c)
        assert ch.types == {"Artifact", "Creature"} and (ch.power, ch.toughness) == ("5", "5")
        assert unseen_by(s, c, "p2", SPECTATOR)
    roundtrip(s)


def test_a_card_that_leaves_the_battlefield_face_down_is_revealed(cards):
    s = build(cards, p1=("Ashcloud Phoenix", "Lightning Bolt", "Murder"))
    phoenix = put(s, "Ashcloud Phoenix", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[phoenix.id])
    answer(s)
    assert s.state.cards[phoenix.id].face_down
    murder = put(s, "Murder", "hand")
    mana(s, B=3, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[phoenix.id])
    answer(s)
    assert s.state.cards[phoenix.id].zone == "p1:graveyard" and not s.state.cards[phoenix.id].face_down
    assert "Ashcloud Phoenix" in blob(s, "p2")  # 708.9: revealed to all players as it moves
    roundtrip(s)


def to_own_turn(s, n):
    until(s, lambda s: s.state.turn.number >= n and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")


def test_ethereal_valkyrie_foretells_a_card_from_your_hand_for_its_mana_cost_less_two(cards):
    s = build(cards, p1=("Ethereal Valkyrie", "Grizzly Bears"))
    valkyrie = put(s, "Ethereal Valkyrie", "hand")
    bears = put(s, "Grizzly Bears", "hand")
    mana(s, W=1, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=valkyrie.id)
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and d.min_choices == 1  # exile a card from your hand face down: a private choice
    for viewer in ("p2", SPECTATOR):
        assert "options" not in s.view(viewer)["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:foretell" and s.state.rules.foretold[bears.id] == s.state.turn.number  # 702.143d
    assert s.state.rules.foretell_costs[bears.id] == "{G}"  # {1}{G} reduced by {2}
    assert unseen_by(s, bears, "p2", SPECTATOR) and not unseen_by(s, bears, "p1")
    mana(s, G=1)
    with pytest.raises(ActionError):  # not the turn it became foretold
        act(s, "p1", type="cast_spell", card_id=bears.id)
    to_own_turn(s, 3)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"  # cast for {G}
    roundtrip(s)


def attack_with(s, c):
    for _ in range(60):
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers" and d.player == "p1":
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"}])
            return
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never attacked")


def test_the_foretold_soldier_exiles_itself_face_down_and_becomes_foretold(cards):
    s = build(cards, p1=("The Foretold Soldier",))
    soldier = put(s, "The Foretold Soldier", "battlefield")
    to_own_turn(s, 3)
    attack_with(s, soldier)
    until(s, lambda s: s.state.cards[soldier.id].zone == "p1:foretell")  # "Whenever this creature deals damage, exile it face down"
    assert unseen_by(s, soldier, "p2", SPECTATOR) and s.state.rules.foretold[soldier.id] == s.state.turn.number
    to_own_turn(s, 5)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=soldier.id)  # for its printed foretell cost {1}{G}
    answer(s)
    assert s.state.cards[soldier.id].zone == "p1:battlefield"
    roundtrip(s)


def test_cybership_puts_the_top_cards_of_their_library_onto_the_battlefield_face_down(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, turn_on
    from tests.test_rules_combat import creature
    from tests.test_rules_effects import pass_until_stack_empty, run_until

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Cybership"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Ambush Viper"), (1, "Grizzly Bears"), (10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    ship = find(s, "Cybership")
    act(s, "p1", type="move", card_ids=[ship.id], to={"zone": "battlefield"})
    viper = put(s, "Ambush Viper", "library", pid="p2", position="top")
    bears = put(s, "Grizzly Bears", "library", pid="p2", position="top")
    pilot = creature(s, "p1", "Pilot", "4/4")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    from app.rules.casting import activatable

    crew = next(a for a in activatable(s.state, "p1", cards) if a["card_id"] == ship.id)
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=crew["ability"], crew=[pilot.id])
    pass_until_stack_empty(s)
    act(s, "p1", type="pass_priority")  # → combat
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ship.id, "target": "p2"}])
    run_until(s, lambda s: s.state.cards[bears.id].zone == "p1:battlefield")
    for c in (bears, viper):
        card_ = s.state.cards[c.id]
        assert card_.zone == "p1:battlefield" and card_.face_down and card_.owner == "p2" and card_.controller == "p1"
        ch = chars_of(s, c)
        assert ch.types == {"Artifact", "Creature"} and ch.subtypes == {"Cyberman"} and (ch.power, ch.toughness) == ("2", "2")
        assert unseen_by(s, c, "p2", SPECTATOR) and not unseen_by(s, c, "p1")
    replay_matches(s)


def test_ghastly_conscription_manifests_the_creature_cards_of_a_graveyard(cards):
    s = build(cards, p1=("Ghastly Conscription",), p2=("Ambush Viper", "Grizzly Bears", "Lightning Bolt"))
    viper = put(s, "Ambush Viper", "graveyard", pid="p2")
    bears = put(s, "Grizzly Bears", "graveyard", pid="p2")
    bolt = put(s, "Lightning Bolt", "graveyard", pid="p2")
    spell = put(s, "Ghastly Conscription", "hand")
    mana(s, B=2, C=5)
    old = [viper.id, bears.id]  # (a rekey renames the same objects)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    answer(s)
    down = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.face_down]
    # the creature cards only, as face-down 2/2 creatures under Alice's control (701.40a)
    assert sorted(c.name for c in down) == ["Ambush Viper", "Grizzly Bears"]
    for c in down:
        assert c.face_down_kind == "manifest" and c.controller == "p1"
        assert unseen_by(s, c, "p2", SPECTATOR) and not unseen_by(s, c, "p1")
    # -- review (sys 18A) -- 406.3: the shuffled pile is re-keyed, so the ids Bob saw in his graveyard don't say which is which
    assert old[0] not in s.state.cards and old[1] not in s.state.cards
    for viewer in ("p2", SPECTATOR):
        assert old[0] not in blob(s, viewer) and old[1] not in blob(s, viewer)
    assert s.state.cards[bolt.id].zone == "p2:graveyard"
    replay_matches(s)
    roundtrip(s)


def test_become_anonymous_cloaks_your_creature_and_the_top_two_cards_tapped(cards):
    s = build(cards, p1=("Become Anonymous", "Ambush Viper", "Grizzly Bears", "Giant Growth"))
    viper = put(s, "Ambush Viper", "battlefield")
    put(s, "Grizzly Bears", "library", position="top")
    put(s, "Giant Growth", "library", position="top")
    spell = put(s, "Become Anonymous", "hand")
    mana(s, U=2, C=2)
    old = viper.id
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[viper.id])
    answer(s)
    down = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.face_down]
    assert sorted(c.name for c in down) == ["Ambush Viper", "Giant Growth", "Grizzly Bears"] and old not in s.state.cards
    for card_ in down:
        assert card_.face_down_kind == "cloak" and card_.tapped  # "They enter tapped"
        assert unseen_by(s, card_, "p2", SPECTATOR)
        assert any(a.text.startswith("Ward") for a in chars_of(s, card_).abilities)  # 701.58a: ward {2}
    replay_matches(s)
    roundtrip(s)


def test_jeskai_infiltrator_manifests_itself_and_the_top_card(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, turn_on
    from tests.test_rules_effects import run_until

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Jeskai Infiltrator"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    infiltrator = find(s, "Jeskai Infiltrator")
    act(s, "p1", type="move", card_ids=[infiltrator.id], to={"zone": "battlefield"})
    top = s.state.zones["p1:library"][0]
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    act(s, "p1", type="pass_priority")  # → combat
    old = infiltrator.id  # (a rekey renames the same object)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": old, "target": "p2"}])
    run_until(s, lambda s: any(c.face_down for c in s.state.cards.values() if c.zone == "p1:battlefield"))
    run_until(s, lambda s: s.state.rules.decision is None and not s.state.zones.get("stack"))
    mine = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.face_down]
    assert sorted(c.name for c in mine) == ["Forest", "Jeskai Infiltrator"] and all(c.face_down_kind == "manifest" for c in mine)
    assert old not in s.state.cards and top not in s.state.cards  # (406.3: the shuffled pile is re-keyed)
    for c in mine:
        assert unseen_by(s, c, "p2", SPECTATOR)
    replay_matches(s)


def test_hauntwoods_shrieker_reveals_a_face_down_permanent_and_may_turn_a_creature_card_up(cards):
    s = build(cards, p1=("Hauntwoods Shrieker",), p2=("Grizzly Bears", "Giant Growth"))
    shrieker = put(s, "Hauntwoods Shrieker", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    growth = put(s, "Giant Growth", "battlefield", pid="p2")
    for c in (bears, growth):
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
        assert unseen_by(s, c, "p1", SPECTATOR)
    mana(s, G=1, C=1)
    act(s, "p1", type="activate_ability", card_id=shrieker.id, ability=1, targets=[growth.id])
    answer(s)  # a noncreature card: revealed, stays face down, nothing to decide
    assert s.state.cards[growth.id].face_down and not s.state.cards[growth.id].revealed_to  # hidden again
    mana(s, G=1, C=1)
    act(s, "p1", type="activate_ability", card_id=shrieker.id, ability=1, targets=[bears.id])
    d = None
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and d.kind == "confirm"  # a creature card: Alice may turn it face up
    assert "Grizzly Bears" in blob(s, "p2")  # 701.20a: revealed to all players while she decides
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    answer(s)
    assert not s.state.cards[bears.id].face_down and s.state.cards[bears.id].zone == "p2:battlefield"
    roundtrip(s)


def test_spy_network_looks_at_the_hand_the_top_card_and_the_face_down_creatures(cards):
    s = build(cards, p1=("Spy Network", "Giant Growth", "Murder", "Lightning Bolt", "Grizzly Bears"),
              p2=("Ambush Viper", "Giant Growth", "Lightning Bolt"))
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    act(s, "p2", type="move", card_ids=[viper.id], to={"player": "p2", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
    growth = put(s, "Giant Growth", "hand", pid="p2")
    bolt = put(s, "Lightning Bolt", "library", pid="p2", position="top")
    spy = put(s, "Spy Network", "hand")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spy.id, targets=["p2"])
    seen_by_alice = set()
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        assert d.player == "p1"
        seen_by_alice |= {n for n, c in (("Giant Growth", growth), ("Lightning Bolt", bolt), ("Ambush Viper", viper))
                          if not unseen_by(s, c, "p1")}
        for viewer in ("p2", SPECTATOR):  # mid-decision: Alice's looking shows nobody else anything
            assert "options" not in s.view(viewer)["rules"]["decision"] or d.kind == "confirm"
            assert unseen_by(s, viper, viewer) and unseen_by(s, bolt, viewer) or viewer == "p2"
            for o in d.options:  # (her own top cards, when she orders them)
                if o.card_id and s.state.cards[o.card_id].owner == "p1":
                    assert unseen_by(s, s.state.cards[o.card_id], viewer)
        assert unseen_by(s, growth, SPECTATOR) and unseen_by(s, bolt, SPECTATOR) and unseen_by(s, viper, SPECTATOR)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert seen_by_alice == {"Giant Growth", "Lightning Bolt", "Ambush Viper"}  # 701.20e: she looked at all three
    assert s.state.cards[viper.id].face_down
    assert unseen_by(s, growth, SPECTATOR) and unseen_by(s, bolt, "p2", SPECTATOR) and unseen_by(s, viper, SPECTATOR)  # only Alice ever saw them
    roundtrip(s)


def test_illithid_harvester_turns_any_number_of_tapped_nontoken_creatures_face_down_as_horrors(cards):
    s = build(cards, p1=("Illithid Harvester // Plant Tadpoles",), p2=("Ambush Viper", "Grizzly Bears"))
    tapped = put(s, "Ambush Viper", "battlefield", pid="p2")
    untapped = put(s, "Grizzly Bears", "battlefield", pid="p2")
    act(s, "p2", type="tap", card_ids=[tapped.id], tapped=True)
    harvester = put(s, "Illithid Harvester // Plant Tadpoles", "hand")
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=harvester.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_cards" or d.kind == "choose_targets":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == tapped.id] or [o.id for o in d.options][:1])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    card_ = s.state.cards[tapped.id]
    assert card_.face_down and card_.face_down_as == "2/2 Horror creature" and not s.state.cards[untapped.id].face_down
    ch = chars_of(s, tapped)
    assert ch.types == {"Creature"} and ch.subtypes == {"Horror"} and (ch.power, ch.toughness) == ("2", "2")
    assert unseen_by(s, tapped, "p1", SPECTATOR) and not unseen_by(s, tapped, "p2")
    roundtrip(s)


def test_poison_the_cup_scries_only_when_foretold(cards):
    s = build(cards, p1=("Poison the Cup",), p2=("Ambush Viper", "Grizzly Bears"))
    cup = put(s, "Poison the Cup", "hand")
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=cup.id, targets=[viper.id])  # not foretold: no scry
    answer(s)
    assert s.state.cards[viper.id].zone == "p2:graveyard"
    t = build(cards, p1=("Poison the Cup",), p2=("Ambush Viper",))
    cup = put(t, "Poison the Cup", "hand")
    mana(t, B=2)
    act(t, "p1", type="activate_ability", card_id=cup.id, ability=1)  # foretell {2}
    viper = put(t, "Ambush Viper", "battlefield", pid="p2")
    to_own_turn(t, 3)
    mana(t, B=2)
    act(t, "p1", type="cast_spell", card_id=cup.id, targets=[viper.id])
    d = None
    for _ in range(20):
        d = t.state.rules.decision
        if d is not None:
            break
        act(t, t.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and "scry" in d.prompt.lower()  # 702.143c: it was foretold
    for viewer in ("p2", SPECTATOR):
        assert "options" not in t.view(viewer)["rules"]["decision"]
    answer(t)
    assert t.state.cards[viper.id].zone == "p2:graveyard"
    roundtrip(t)


def test_scroll_of_fate_manifests_a_card_from_your_hand_privately(cards):
    s = build(cards, p1=("Scroll of Fate", "Grizzly Bears", "Giant Growth"))
    scroll = put(s, "Scroll of Fate", "battlefield")
    bears = put(s, "Grizzly Bears", "hand")
    growth = put(s, "Giant Growth", "hand")
    act(s, "p1", type="activate_ability", card_id=scroll.id, ability=0)
    d = until_asked(s)
    assert d.player == "p1" and {o.card_id for o in d.options} >= {bears.id, growth.id}
    for viewer in ("p2", SPECTATOR):  # nobody else sees which cards Alice may choose from
        assert "options" not in s.view(viewer)["rules"]["decision"]
        assert unseen_by(s, bears, viewer) and unseen_by(s, growth, viewer)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[growth.id])
    answer(s)
    c = s.state.cards[growth.id]
    assert c.zone == "p1:battlefield" and c.face_down and c.face_down_kind == "manifest"  # 701.40a
    assert unseen_by(s, growth, "p2", SPECTATOR) and not unseen_by(s, growth, "p1")
    assert s.state.cards[bears.id].zone == "p1:hand"
    roundtrip(s)
