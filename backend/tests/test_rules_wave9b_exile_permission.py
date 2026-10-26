"""Wave 9B: "You may cast that card for as long as it remains exiled" and the spending riders, researched against CR 2026-09-25.

* 611.2b: a permission that lasts for as long as the card stays in exile; the card is a new object once it leaves (400.7h).
* 118.14, 609.4b: "mana of any type can be spent to cast that spell" changes only how the cost may be paid (and only for the
  spell cast with that permission).
* "for as long as you control ~" after "doesn't untap during its controller's untap step" (Ty Lee, Icefall Regent).

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, permissions
from app.rules import mana as M
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Gonti, Lord of Luxury', set_code='tst', number='N01', mana_cost='{2}{B}{B}', cmc=4.0, type_line='Legendary Creature — Aetherborn Rogue', oracle_text="Deathtouch\nWhen Gonti enters, look at the top four cards of target opponent's library, exile one of them face down, then put the rest on the bottom of that library in a random order. You may cast that card for as long as it remains exiled, and mana of any type can be spent to cast that spell.", power='2', toughness='3', colors=['B'], color_identity=['B'], keywords=['Deathtouch']),  # noqa: E501
    card('Savvy Trader', set_code='tst', number='N02', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Human Citizen', oracle_text='When this creature enters, exile target permanent card from your graveyard. You may play that card for as long as it remains exiled.\nSpells you cast from anywhere other than your hand cost {1} less to cast.', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Hostage Taker', set_code='tst', number='N03', mana_cost='{2}{U}{B}', cmc=4.0, type_line='Creature — Human Pirate', oracle_text='When this creature enters, exile another target creature or artifact until this creature leaves the battlefield. You may cast that card for as long as it remains exiled, and mana of any type can be spent to cast that spell.', power='2', toughness='3', colors=['B', 'U'], color_identity=['B', 'U'], keywords=[]),  # noqa: E501
    card('Thief of Sanity', set_code='tst', number='N04', mana_cost='{1}{U}{B}', cmc=3.0, type_line='Creature — Specter', oracle_text="Flying\nWhenever this creature deals combat damage to a player, look at the top three cards of that player's library, exile one of them face down, then put the rest into their graveyard. You may cast that card for as long as it remains exiled, and mana of any type can be spent to cast that spell.", power='2', toughness='2', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Flying']),  # noqa: E501
    card('Ramirez DePietro, Pillager', set_code='tst', number='N05', mana_cost='{2}{U}{B}', cmc=4.0, type_line='Legendary Creature — Human Pirate', oracle_text='When Ramirez DePietro enters, you lose 2 life and create two Treasure tokens.\nWhenever one or more Pirates you control deal combat damage to a player, exile the top card of that player\'s library. You may cast that card for as long as it remains exiled.', power='4', toughness='3', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Treasure']),  # noqa: E501
    card('Rev, Tithe Extractor', set_code='tst', number='N06', mana_cost='{3}{B}', cmc=4.0, type_line='Legendary Creature — Human Rogue', oracle_text='Whenever you attack, target creature gains deathtouch until end of turn.\nWhenever one or more creatures you control deal combat damage to a player, create a Treasure token, then look at the top card of that player\'s library and exile it face down. You may cast that card for as long as it remains exiled. (A Treasure token is an artifact with "{T}, Sacrifice this token: Add one mana of any color.")', power='3', toughness='3', colors=['B'], color_identity=['B'], keywords=['Treasure']),  # noqa: E501
    card('Edward Kenway', set_code='tst', number='N07', mana_cost='{2}{U}{B}{R}', cmc=5.0, type_line='Legendary Creature — Human Assassin Pirate', oracle_text="At the beginning of your end step, create a Treasure token for each tapped Assassin, Pirate, and/or Vehicle you control.\nWhenever a Vehicle you control deals combat damage to a player, look at the top card of that player's library, then exile it face down. You may play that card for as long as it remains exiled.", power='5', toughness='5', colors=['B', 'R', 'U'], color_identity=['B', 'R', 'U'], keywords=['Treasure']),  # noqa: E501
    card('Blightwing Bandit', set_code='tst', number='N08', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Faerie Rogue', oracle_text="Flying, deathtouch\nWhenever you cast your first spell during each opponent's turn, look at the top card of that player's library, then exile it face down. You may play that card for as long as it remains exiled, and mana of any type can be spent to cast it.", power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=['Deathtouch', 'Flying']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    """The table as a fresh session rebuilt from a save (state JSON) and from the recorded history."""
    return GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)


def roundtrip(s):
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def build(cards, p1=(), p2=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def find(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, where, pid="p1", position=None, owner=None):
    c = find(s, name, owner or pid)
    payload = {"type": "move", "card_ids": [c.id], "to": {"player": owner or pid, "zone": where}}
    if position:
        payload["position"] = position
    act(s, pid, **payload)
    return s.state.cards[c.id]


def answer(s, pick=None, limit=30):
    """Resolve the stack; a decision is answered with the option that ``pick`` (a card id) names, else the first."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            chosen = [o.id for o in d.options if pick and o.card_id == pick] or ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen[:max(1, d.max_choices or 1)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_wording_is_exact():
    ok = permissions.parse_clause("you may cast that card for as long as it remains exiled, and mana of any type can be spent to cast that spell")
    assert ok == ([{"do": "grant_play", "who": "it:card", "play": False, "cast": True, "until": "permanent", "optional": True,
                    "spend": "type"}], None)
    assert permissions.parse_clause("you may play that card for as long as it remains exiled")[0][0]["play"] is True
    assert permissions.parse_clause("for as long as it remains exiled, you may play it, and mana of any type can be spent to cast that spell")[0][0]["spend"] == "type"
    assert permissions.parse_clause("you may play that card for as long as it remains exiled, and you may spend mana as though it were mana of any color to cast it")[0][0]["spend"] == "color"
    for text in ("you may cast that card for as long as they remain exiled",  # (the duration names another number)
                 "you may cast those cards for as long as it remains exiled",
                 "you may cast that card for as long as it remains exiled, and mana of any type can be spent to cast them",
                 "you may cast that card for as long as it remains exiled and for as long as it remains exiled",
                 "you may cast that card, and mana of any type can be spent to cast that spell",  # (no duration: refused)
                 "you may cast that card without paying its mana cost for as long as it remains exiled, and mana of any type can be spent to cast that spell",
                 "you may cast that card for as long as it remains exiled, and you may spend mana as though it were mana of any shade to cast it"):
        assert permissions.parse_clause(text) is None, text


def test_spend_as_rewrites_only_how_the_cost_is_paid():
    c = M.parse_cost("{2}{B}{B}")
    assert M.spend_as(c, "type").text() == "{4}"
    assert M.spend_as(c, "color").text() == "{4}"  # (wave 22F: colorless mana is treated as the color, 609.4)
    assert M.spend_as(M.parse_cost("{1}{C}{S}"), "type").text() == "{2}{S}"
    assert M.spend_as(M.parse_cost("{1}{C}"), "color").text() == "{1}{C}"  # ({C} still needs colorless mana)
    assert M.spend_as(M.parse_cost("{W/U}{U/B}"), "type").text() == "{2}"
    assert M.spend_as(M.parse_cost("{2/B}"), "type").text() == "{1}"
    assert M.spend_as(M.parse_cost("{B/P}"), "type").phyrexian == (M.ANY_PHYREXIAN,)  # any mana or two life
    # (a payment prompt can be resumed from its text; the allocation is only the solver's per-symbol hint, rebuilt by spend_as)
    assert M.parse_cost(M.spend_as(c, "color").text()) == replace(M.spend_as(c, "color"), allocation=None)


def test_gonti_exiles_face_down_and_any_type_of_mana_casts_it(cards):
    s = build(cards, p1=("Gonti, Lord of Luxury",), p2=("Ambush Viper",))
    gonti = put(s, "Gonti, Lord of Luxury", "hand")
    viper = put(s, "Ambush Viper", "library", pid="p2", position="top")
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=gonti.id)
    pass_until_stack_empty(s)
    answer(s, pick=viper.id)
    got = s.state.cards[viper.id]
    assert got.zone == "p2:exile" and got.face_down
    assert [p.card for p in s.state.rules.permissions] == [viper.id] and s.state.rules.permissions[0].spend == "type"
    # hidden information: Bob can't see the face-down card, Alice (who looked at it) can
    assert s.view("p1")["cards"][viper.id].get("name") == "Ambush Viper"
    assert s.view("p2")["cards"][viper.id].get("name") is None
    assert "Ambush Viper" not in str(s.view("p2")["log"])  # (nor in the log Bob reads)
    roundtrip(s)
    # the card costs {1}{G}: Alice has only black mana; any type of mana can pay for it (118.14)
    mana(s, B=2)
    from app.rules.casting import castable

    assert castable(s.state, "p1", s.state.cards[viper.id], cards)
    act(s, "p1", type="cast_spell", card_id=viper.id)
    pass_until_stack_empty(s)
    assert s.state.cards[viper.id].zone == "p1:battlefield" and s.state.rules.permissions == []
    roundtrip(s)


def test_the_riders_spending_is_for_that_spell_only(cards):
    """609.4b: the spending rule belongs to the cast made with the permission; a spell cast from the hand pays as usual."""
    s = build(cards, p1=("Gonti, Lord of Luxury", "Ambush Viper"), p2=())
    viper = put(s, "Ambush Viper", "hand")
    mana(s, B=2)
    from app.rules.casting import castable

    assert not castable(s.state, "p1", viper, cards)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=viper.id)


def test_savvy_trader_plays_the_exiled_card_until_it_leaves_exile(cards):
    s = build(cards, p1=("Savvy Trader", "Grizzly Bears", "Forest"))
    trader = put(s, "Savvy Trader", "hand")
    bears = put(s, "Grizzly Bears", "graveyard")
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=trader.id)
    pass_until_stack_empty(s)
    answer(s, pick=bears.id)
    assert s.state.cards[bears.id].zone == "p1:exile"
    [perm] = s.state.rules.permissions
    assert perm.until == "permanent" and perm.card == bears.id and perm.spend == ""
    # a turn later it can still be cast: "for as long as it remains exiled" does not end with the turn (611.2b)
    for _ in range(300):
        if s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            break
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert s.state.rules.permissions and s.state.rules.permissions[0].card == bears.id
    roundtrip(s)
    mana(s, G=1)  # {1}{G} less {1} (Savvy Trader's own cost reduction)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and not s.state.rules.permissions
    roundtrip(s)


def test_the_permission_ends_when_the_card_leaves_exile(cards):
    """400.7h: the card is a new object once it changes zones; the permission was for the old one."""
    s = build(cards, p1=("Savvy Trader", "Grizzly Bears"))
    trader = put(s, "Savvy Trader", "hand")
    bears = put(s, "Grizzly Bears", "graveyard")
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=trader.id)
    pass_until_stack_empty(s)
    answer(s, pick=bears.id)
    put(s, "Grizzly Bears", "hand")  # (a table tool moves it: it is a new object)
    put(s, "Grizzly Bears", "exile")
    mana(s, G=2)
    from app.rules.casting import castable

    assert not castable(s.state, "p1", s.state.cards[bears.id], cards)
    roundtrip(s)


def test_hostage_taker_casts_the_creature_with_any_mana_and_it_returns_if_the_taker_leaves(cards):
    s = build(cards, p1=("Hostage Taker",), p2=("Ambush Viper",))
    taker = put(s, "Hostage Taker", "hand")
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=taker.id)
    pass_until_stack_empty(s)
    answer(s, pick=viper.id)
    assert s.state.cards[viper.id].zone == "p2:exile" and not s.state.cards[viper.id].face_down
    [perm] = s.state.rules.permissions
    assert perm.card == viper.id and perm.spend == "type" and perm.player == "p1"
    from app.rules.casting import castable

    assert not castable(s.state, "p2", s.state.cards[viper.id], cards)  # (Bob, the owner, has no such permission)
    from app.rules import view  # (review 30: offered on Alice's table, though it sits in Bob's exile)

    mana(s, C=2)
    assert viper.id in view.hints(s.state, "p1", cards).get("castable", []) and viper.id not in view.hints(s.state, "p2", cards).get("castable", [])
    roundtrip(s)
    # the taker leaves before the creature is cast: it returns to the battlefield, and the permission was for the exiled object
    act(s, "p1", type="set_damage", card_ids=[taker.id], value=3)
    act(s, s.state.rules.priority, type="pass_priority")  # state-based actions: the Taker dies, the creature comes back (610.3)
    assert taker.id not in s.state.cards or s.state.cards[taker.id].zone != "p1:battlefield"
    assert s.state.cards[viper.id].zone == "p2:battlefield"
    assert not castable(s.state, "p1", s.state.cards[viper.id], cards)
    roundtrip(s)


def test_rev_looks_at_the_top_card_exiles_it_face_down_and_it_stays_castable(cards):
    s = build(cards, p1=("Rev, Tithe Extractor",), p2=("Ambush Viper",))
    put(s, "Rev, Tithe Extractor", "battlefield")
    viper = put(s, "Ambush Viper", "library", pid="p2", position="top")
    act(s, "p1", type="create_token", player="p1", token={"name": "Raider", "type_line": "Token Creature — Test", "power": "2",
                                                         "toughness": "2", "text": "Haste"})
    raider = find(s, "Raider")
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority") if d is None else act(
            s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": raider.id, "target": "p2"}])
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif s.state.cards[viper.id].zone == "p2:exile":
            break
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    got = s.state.cards[viper.id]
    assert got.zone == "p2:exile" and got.face_down
    assert [p.card for p in s.state.rules.permissions] == [viper.id]
    assert s.view("p1")["cards"][viper.id].get("name") == "Ambush Viper"
    assert s.view("p2")["cards"][viper.id].get("name") is None  # 406.3: Bob may not look at it
    roundtrip(s)
    mana(s, G=2)
    pass_until_stack_empty(s)
    for _ in range(30):  # (on to the second main phase, where a creature spell can be cast)
        d = s.state.rules.decision
        if s.state.turn.phase == "main2" and d is None and not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority") if d is None else act(
            s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    act(s, "p1", type="cast_spell", card_id=viper.id)
    pass_until_stack_empty(s)
    assert s.state.cards[viper.id].zone == "p1:battlefield" and not s.state.rules.permissions
    roundtrip(s)


def test_hostage_taker_cast_with_too_little_mana_is_refused(cards):
    s = build(cards, p1=("Hostage Taker",), p2=("Ambush Viper",))
    taker = put(s, "Hostage Taker", "hand")
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=taker.id)
    pass_until_stack_empty(s)
    answer(s, pick=viper.id)
    mana(s, B=1)  # {1}{G} needs two mana, of whatever type
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=viper.id)
    assert s.state.model_dump(mode="json") == before
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=viper.id)
    pass_until_stack_empty(s)
    assert s.state.cards[viper.id].zone == "p1:battlefield" and s.state.cards[viper.id].controller == "p1"
    roundtrip(s)
