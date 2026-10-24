"""Wave 100B: "if you do / if they do / this way" riders (CR 2026-09-25), real Oracle text (tests/fixtures/wave100b_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* Serendib Djinn - "If you sacrifice an Island this way": the instruction's own sacrifice (701.21a), the land as it last existed (608.2h).
* Silvan Reveler - "If you discard a land card this way, put it from your graveyard onto the battlefield tapped." (701.9a; a card a
  replacement effect put elsewhere - Rest in Peace - isn't in the graveyard to be put onto the battlefield: 400.7, 614.6).
* Gisa's Favorite Shovel - "defending player sacrifices a creature of their choice. If they do, you create a Walker token." (118.12).
* Mishra's War Machine, Minion of Leshrac - "… deals N damage to you unless you …. If it deals damage to you this way, tap it."
  (118.12a; 120.3: damage that was prevented wasn't dealt, 615.1: Personal Sanctuary).
* Sonic Shrieker - "If a player is dealt damage this way, they discard a card." (the one target, a player dealt damage).
* Break the Spell - "If a permanent you controlled or a token was destroyed this way, draw a card." (608.2h: as it last existed).
* Reign of the Pit - "the total power of the creatures sacrificed this way" (608.2h).
* Trade Route Envoy - "draw a card if …. If you don't draw a card this way, put a +1/+1 counter on this creature." (608.2c, 121.2).
* Ballista Wielder - "A creature dealt damage this way can't block this turn." (a player or a planeswalker dealt it isn't one).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, stops, to_phase
from tests.wave9c_kit import check, life, mana, pt, put, to_hand
from tests.wave52a_kit import build_n
from tests.wave100b_kit import hand_size, open_repo, run, tokens, zone

DJINN, REVELER, SHOVEL, WAR, MINION = "Serendib Djinn", "Silvan Reveler", "Gisa's Favorite Shovel", "Mishra's War Machine", "Minion of Leshrac"
SHRIEKER, BREAK, PIT, ENVOY, BALLISTA = "Sonic Shrieker", "Break the Spell", "Reign of the Pit", "Trade Route Envoy", "Ballista Watcher // Ballista Wielder"
SANCTUARY, RIP, BEARS, GIANT, PACIFISM = "Personal Sanctuary", "Rest in Peace", "Grizzly Bears", "Hill Giant", "Pacifism"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [DJINN, REVELER, SHOVEL, WAR, MINION, SHRIEKER, BREAK, PIT, ENVOY, BALLISTA])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def pick_card(*cids):
    """Answer a decision whose options name these cards (by card id), else the default."""
    def pick(d):
        ids = [o.id for o in d.options if o.id in cids or getattr(o, "card_id", None) in cids]
        return ids[: max(1, d.min_choices)] if ids else None
    return pick


def answer(word):
    def pick(d):
        ids = [o.id for o in d.options if word.lower() in (o.label or "").lower() or o.id == word]
        return ids[:1] or None
    return pick


# -- Serendib Djinn -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("island", [True, False])
def test_serendib_djinn_hurts_only_when_an_island_was_sacrificed(cards, island):
    s = build_n(cards, [DJINN, (2, "Island")])
    put(s, DJINN)
    isle = put(s, "Island")
    forest = put(s, "Forest")
    put(s, "Forest")
    to_phase(s, "upkeep", turn=3)
    before = life(s)
    run(s, pick_card(isle.id if island else forest.id))
    assert zone(s, isle if island else forest) == "p1:graveyard"
    assert life(s) == before - (3 if island else 0)
    check(s)


# -- Silvan Reveler -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("discard_land,rip", [(True, False), (False, False), (True, True)])
def test_silvan_reveler_puts_a_discarded_land_onto_the_battlefield_tapped(cards, discard_land, rip):
    s = build_n(cards, [REVELER, BEARS, RIP])
    if rip:
        put(s, RIP)
    land = to_hand(s, "Forest")
    bears = to_hand(s, BEARS)
    reveler = to_hand(s, REVELER)
    mana(s, G=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=reveler.id)
    run(s, pick_card(land.id if discard_land else bears.id))
    gone = land if discard_land else bears
    if rip:  # 614.6: exiled instead of put into the graveyard, so it isn't there to be put onto the battlefield
        assert zone(s, gone) == "p1:exile"
    elif discard_land:
        assert zone(s, land) == "p1:battlefield" and s.state.cards[land.id].tapped
    else:
        assert zone(s, bears) == "p1:graveyard" and zone(s, land) == "p1:hand"
    check(s)


# -- Gisa's Favorite Shovel -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bob_has_creature", [True, False])
def test_gisas_favorite_shovel_walker_only_if_they_sacrificed(cards, bob_has_creature):
    s = build_n(cards, [SHOVEL, BEARS], [GIANT])
    shovel = put(s, SHOVEL)
    bears = put(s, BEARS)
    act(s, "p1", type="attach", card_ids=[shovel.id], to=bears.id)
    giant = put(s, GIANT, "p2") if bob_has_creature else None
    to_phase(s, "main1", turn=3)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    run(s)
    if giant is not None:
        assert zone(s, giant) == "p2:graveyard"
    walkers = tokens(s, "p1", "Walker")
    assert len(walkers) == (1 if bob_has_creature else 0)
    check(s)


# -- Mishra's War Machine / Minion of Leshrac -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("pay,sanctuary", [(False, False), (True, False), (False, True)])
def test_mishras_war_machine_taps_only_when_it_dealt_you_damage(cards, pay, sanctuary):
    s = build_n(cards, [WAR, BEARS, SANCTUARY])
    war = put(s, WAR)
    if sanctuary:
        put(s, SANCTUARY)
    bears = to_hand(s, BEARS)
    stops(s)
    to_phase(s, "upkeep", turn=3)
    before = life(s)
    run(s, answer("pay" if pay else "decline"))
    hurt = not pay and not sanctuary
    assert life(s) == before - (3 if hurt else 0)
    assert s.state.cards[war.id].tapped is hurt  # (prevented: no damage was dealt this way, 615.1)
    assert (zone(s, bears) == "p1:graveyard") is pay
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_minion_of_leshrac_sacrifice_or_five_damage_and_tap(cards, pay):
    s = build_n(cards, [MINION, BEARS])
    minion = put(s, MINION)
    bears = put(s, BEARS)
    stops(s)
    to_phase(s, "upkeep", turn=3)
    before = life(s)
    run(s, answer("pay" if pay else "decline"))
    assert life(s) == before - (0 if pay else 5)
    assert s.state.cards[minion.id].tapped is (not pay)
    assert (zone(s, bears) == "p1:graveyard") is pay
    check(s)


# -- Sonic Shrieker -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("target_player", [True, False])
def test_sonic_shrieker_a_player_dealt_damage_discards(cards, target_player):
    s = build_n(cards, [SHRIEKER], [BEARS, GIANT])
    giant = put(s, GIANT, "p2")
    to_hand(s, BEARS, "p2")
    shrieker = to_hand(s, SHRIEKER)
    mana(s, R=1, W=1, B=1, C=2)
    theirs, their_life, mine = hand_size(s, "p2"), life(s, "p2"), life(s)
    act(s, "p1", type="cast_spell", card_id=shrieker.id)
    run(s, pick_card("p2" if target_player else giant.id))
    assert life(s) == mine + 2
    if target_player:
        assert life(s, "p2") == their_life - 2 and hand_size(s, "p2") == theirs - 1
    else:
        assert hand_size(s, "p2") == theirs and s.state.cards[giant.id].damage == 2
    check(s)


# -- Break the Spell ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("whose", ["mine", "theirs", "token"])
def test_break_the_spell_draws_for_your_permanent_or_a_token(cards, whose):
    s = build_n(cards, [BREAK, PACIFISM, BEARS], [PACIFISM, BEARS])
    if whose == "token":
        act(s, "p2", type="create_token", player="p2", token={"name": "Test Rune", "type_line": "Token Enchantment", "power": None, "toughness": None,
                                                             "colors": ["W"], "text": ""})
        ench = next(c for c in s.state.cards.values() if c.name == "Test Rune")
    else:
        pid = "p1" if whose == "mine" else "p2"
        ench = put(s, PACIFISM, pid)
        host = put(s, BEARS, pid)
        act(s, pid, type="attach", card_ids=[ench.id], to=host.id)
    spell = to_hand(s, BREAK)
    mana(s, W=1)
    before = hand_size(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ench.id])
    run(s)
    assert ench.id not in s.state.cards or not s.state.cards[ench.id].zone.endswith("battlefield")
    assert hand_size(s, "p1") == before - 1 + (0 if whose == "theirs" else 1)
    check(s)


# -- Reign of the Pit -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bob_has_creature", [True, False])
def test_reign_of_the_pit_demon_is_the_total_power_sacrificed(cards, bob_has_creature):
    s = build_n(cards, [PIT, GIANT], [BEARS])
    giant = put(s, GIANT)
    act(s, "p1", type="counter", card_ids=[giant.id], kind="+1/+1", delta=1)  # (as it last existed: 4 power, 608.2h — the card in the graveyard has 3)
    if bob_has_creature:
        put(s, BEARS, "p2")
    spell = to_hand(s, PIT)
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    run(s)
    assert len(tokens(s, "p1", "Demon")) == 1 and zone(s, giant) == "p1:graveyard"
    total = 4 + (2 if bob_has_creature else 0)
    assert pt(s, "Demon") == (total, total)
    check(s)


# -- Trade Route Envoy ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("countered", [True, False])
def test_trade_route_envoy_draws_or_gets_a_counter(cards, countered):
    s = build_n(cards, [ENVOY, BEARS])
    bears = put(s, BEARS)
    if countered:
        act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    envoy = to_hand(s, ENVOY)
    mana(s, G=1, C=3)
    before = hand_size(s, "p1")
    act(s, "p1", type="cast_spell", card_id=envoy.id)
    run(s)
    assert hand_size(s, "p1") == before - 1 + (1 if countered else 0)
    assert s.state.cards[envoy.id].counters.get("+1/+1", 0) == (0 if countered else 1)
    check(s)


# -- Ballista Wielder -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("target", ["creature", "player"])
def test_ballista_wielder_a_creature_dealt_damage_cant_block(cards, target):
    s = build_n(cards, [BALLISTA], [GIANT])
    act(s, "p1", type="set_day_night", value="night")
    wielder = put(s, BALLISTA)
    if s.state.cards[wielder.id].face != 1:
        act(s, "p1", type="set_face", card_id=wielder.id, face=1)
    giant = put(s, GIANT, "p2")
    mana(s, R=1, C=2)
    activate(s, "p1", s.state.cards[wielder.id], "can't block", targets=[giant.id if target == "creature" else "p2"])
    run(s)
    imposed = [r for r in s.state.rules.restrictions if giant.id in str(r)] if hasattr(s.state.rules, "restrictions") else None
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[giant.id])
    assert ("cant_block" in ch.imposed) is (target == "creature"), imposed
    check(s)
