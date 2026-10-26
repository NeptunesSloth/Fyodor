"""Wave 13A: emblems (CR 114). "You get an emblem with "…"" / "Target opponent gets an emblem with "…"" puts an object with
only those abilities into the command zone; it is never removed (114.4). Real Oracle text, replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.rules import coverage, designations, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, named, token
from tests.test_rules_conditionals import settle, to_turn, until_asked
from tests.test_rules_effects import replay_matches
from tests.wave9c_kit import build as kit_build

ELSPETH = 'You get an emblem with "Creatures you control get +2/+2 and have flying."'
OB_NIXILIS = 'Target opponent gets an emblem with "Whenever a player draws a card, you lose 2 life."'


def check(s):
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def walker(s, text, pid="p1"):
    act(s, pid, type="create_token", player=pid, token={
        "name": "Test Walker", "type_line": "Token Legendary Planeswalker — Test", "text": f"−1: {text}"})
    w = named(s, "Test Walker")
    act(s, pid, type="counter", card_ids=[w.id], kind="loyalty", delta=8)
    return w


def get_emblem(s, text, *picks):
    w = walker(s, text)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0, **({"targets": list(picks)} if picks else {}))
    settle(s)
    return w


def emblems(s, pid):
    return [s.state.cards[c] for c in zone(s.state, pid, "command") if s.state.cards[c].token is not None]


def ch(s, card):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id])


def test_the_emblem_text_is_checked():
    assert designations.emblem_text_ok("Creatures you control get +3/+3 and have trample.")
    assert not designations.emblem_text_ok("Artifacts you control have 'Vigil'.")  # not a grammar match
    assert designations.emblem_text_ok("{1}{B}, Sacrifice a creature: You gain X life and draw X cards, where X is the sacrificed creature's power.")  # (wave 110O: activated from the command zone)
    assert not designations.emblem_text_ok("{2}: Draw a card.")  # (an emblem cost the engine does not pay from the command zone)
    assert designations.emblem_text_ok("You have no maximum hand size.")  # (wave 20C: hand_size.maximum reads emblems, 114.4)
    assert scripts.parse_effects('You get an emblem with "Creatures you control get +1/+1 until I say so."') is None


def test_an_emblem_anthem_stays_and_its_owner_alone_gets_it(cards):
    s = build(cards)
    mine, theirs = token(s, "p1", "Bear"), token(s, "p2", "Wolf")
    get_emblem(s, ELSPETH)
    [em] = emblems(s, "p1")
    assert em.name == "Test Walker Emblem" and not em.is_token and em.owner == "p1" and em.controller == "p1"
    assert emblems(s, "p2") == []
    assert ch(s, mine).pt == (4, 4) and "flying" in ch(s, mine).granted and ch(s, theirs).pt == (2, 2)  # 114.3, 613
    check(s)
    act(s, "p1", type="move", card_ids=[named(s, "Test Walker").id], to={"player": "p1", "zone": "graveyard"})
    assert ch(s, mine).pt == (4, 4)  # 114.4: nothing removes it (the planeswalker leaving doesn't matter)


def test_target_opponent_gets_the_emblem_and_its_trigger_is_theirs(cards):
    s = build(cards)
    get_emblem(s, OB_NIXILIS, "p2")
    assert emblems(s, "p1") == [] and len(emblems(s, "p2")) == 1
    life = {p: s.state.players[p].life for p in ("p1", "p2")}
    to_turn(s, 2, "main1")  # Bob's draw step: "you lose 2 life" is Bob's
    assert s.state.players["p2"].life == life["p2"] - 2 and s.state.players["p1"].life == life["p1"]
    check(s)


def life(s, pid):
    return s.state.players[pid].life


def bf(s, pid):
    return sorted(s.state.cards[c].name for c in zone(s.state, pid, "battlefield"))


def cast_sol_ring(s):
    ring = named(s, "Sol Ring")
    act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="cast_spell", card_id=ring.id)


def test_cast_triggers_of_an_emblem(cards):
    s = build(cards, "Sol Ring")
    wolf = token(s, "p2", "Wolf")
    get_emblem(s, 'You get an emblem with "Whenever you cast a spell, exile target permanent."')  # Venser, the Sojourner
    cast_sol_ring(s)
    d = s.state.rules.decision
    assert d is not None and wolf.id in {o.id for o in d.options} and d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[wolf.id])
    settle(s)
    assert wolf.id not in zone(s.state, "p2", "battlefield") and "Sol Ring" in bf(s, "p1")
    check(s)


def test_a_cast_trigger_of_any_player_is_the_emblem_owners(cards):
    s = build(cards, "Sol Ring")
    get_emblem(s, 'You get an emblem with "Whenever a player casts a spell, you create a 2/1 blue Ninja creature token."')  # Kaito
    cast_sol_ring(s)
    settle(s)
    assert bf(s, "p1").count("Ninja") == 1 and "Ninja" not in bf(s, "p2")
    check(s)


def test_enters_triggers_of_an_emblem(cards):
    s = build(cards, "Llanowar Elves")
    get_emblem(s, 'You get an emblem with "Whenever a creature you control enters, you may draw a card."')  # Huatli, Radiant Champion
    hand = len(zone(s.state, "p1", "hand"))
    elves = named(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
    act(s, "p1", type="cast_spell", card_id=elves.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1"  # "you may": its controller, the emblem's owner
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    check(s)


def test_step_triggers_of_an_emblem(cards):
    s = build(cards)
    get_emblem(s, 'You get an emblem with "At the beginning of your end step, create three 1/1 white Cat creature tokens with lifelink."')
    to_turn(s, 2, "main1")  # (Alice's end step passed)
    assert bf(s, "p1").count("Cat") == 3
    check(s)
    s = build(cards)
    get_emblem(s, 'You get an emblem with "At the beginning of your end step, create X 2/2 black Zombie creature tokens, where X is two plus the number of Zombies you control."')  # Liliana, the Last Hope
    to_turn(s, 2, "main1")
    assert bf(s, "p1").count("Zombie") == 2
    check(s)


def test_an_upkeep_trigger_of_an_emblem_is_its_controllers(cards):
    s = build(cards)
    get_emblem(s, 'You get an emblem with "At the beginning of your upkeep, this emblem deals 1 damage to you."')  # Chandra, Awakened Inferno
    start = life(s, "p1")
    to_turn(s, 2, "main1")
    assert life(s, "p1") == start  # (Bob's upkeep)
    to_turn(s, 3, "main1")
    assert life(s, "p1") == start - 1
    check(s)


def test_an_opponents_upkeep_trigger_of_an_emblem(cards):
    s = build(cards)
    token(s, "p2", "Wolf")
    get_emblem(s, 'You get an emblem with "At the beginning of each opponent\'s upkeep, that player sacrifices a creature of their choice."')
    to_turn(s, 2, "main1")
    assert "Wolf" not in bf(s, "p2")
    check(s)


def test_a_combat_damage_trigger_of_an_emblem(cards):
    s = build(cards)
    bear = token(s, "p1", "Bear")
    get_emblem(s, 'You get an emblem with "Whenever a creature you control deals combat damage to a player, that player loses the game."')  # Vraska, Golgari Queen
    to_turn(s, 3, "main1")
    for _ in range(4):
        act(s, "p1", type="pass_priority")
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    for _ in range(12):
        if s.state.rules.winner is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.winner == "p1"
    check(s)


def test_a_life_gain_trigger_of_an_emblem(cards):
    s = build(cards)
    get_emblem(s, 'You get an emblem with "Whenever you gain life, target opponent loses that much life."')  # Professor Dellian Fel
    for pid in ("p1", "p2"):
        act(s, pid, type="create_token", player=pid, token={"name": f"Font {pid}", "type_line": "Token Artifact", "text": "{T}: You gain 3 life."})
    start = life(s, "p2")
    act(s, "p1", type="activate_ability", card_id=named(s, "Font p1").id, ability=0)
    settle(s)
    assert life(s, "p2") == start - 3 and life(s, "p1") == 43
    to_turn(s, 2, "main1")
    act(s, "p2", type="activate_ability", card_id=named(s, "Font p2").id, ability=0)
    settle(s)
    assert life(s, "p2") == start and life(s, "p1") == 43  # (Bob's life gain isn't Alice's: no trigger)
    check(s)


def test_a_static_grant_of_an_emblem_reaches_lands(cards):
    s = build(cards)
    get_emblem(s, 'You get an emblem with "Lands you control have indestructible."')  # Nissa, Who Shakes the World
    forest = named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    assert "indestructible" in ch(s, forest).granted
    check(s)


def test_the_emblem_is_the_damage_source(cards):
    s = build(cards, "Mountain")
    get_emblem(s, 'You get an emblem with "Whenever a Mountain you control enters, this emblem deals 4 damage to any target."')  # Koth, Fire of Resistance
    mountain = named(s, "Mountain")
    act(s, "p1", type="move", card_ids=[mountain.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=mountain.id)
    d = until_asked(s)
    assert d is not None and "p2" in {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    assert life(s, "p2") == 36
    check(s)


def test_an_opponent_cast_trigger_of_an_emblem(cards):
    s = kit_build(cards, [], ["Sol Ring", "Sol Ring"])
    get_emblem(s, 'You get an emblem with "Whenever an opponent casts their first spell each turn, counter that spell."')  # Jace, Unraveler of Secrets
    to_turn(s, 2, "main1")
    for n in (1, 2):
        ring = [c for c in s.state.cards.values() if c.name == "Sol Ring" and c.owner == "p2" and c.zone != "p2:graveyard" and c.zone != "stack"][0]
        act(s, "p2", type="move", card_ids=[ring.id], to={"zone": "hand"})
        act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
        act(s, "p2", type="cast_spell", card_id=ring.id)
        settle(s)
        assert bf(s, "p2").count("Sol Ring") == n - 1  # the first is countered, the second resolves
    check(s)


def test_the_emblem_is_public_and_a_view_shows_its_text(cards):
    from app.game.views import build_view
    from app.game.visibility import SPECTATOR

    s = build(cards)
    get_emblem(s, ELSPETH)
    [em] = emblems(s, "p1")
    for viewer in ("p2", SPECTATOR):
        v = build_view(s.state, viewer)
        assert v["cards"][em.id]["token"]["text"].startswith("Creatures you control get +2/+2") and not v["cards"][em.id].get("hidden")


def planeswalker(name, text):
    return card(name, set_code="tst", number=f"13A-{name[:7]}", mana_cost="{4}", cmc=4.0, type_line="Legendary Planeswalker — Test",
                oracle_text=text, loyalty="5", keywords=[])


@pytest.mark.parametrize("name,text,level", [
    ("Elspeth, Sun's Champion", "+1: Create three 1/1 white Soldier creature tokens.\n−3: Destroy all creatures with power 4 or greater.\n"
     "−7: " + ELSPETH, "FULL"),
    ("Ob Nixilis Reignited", "+1: You draw a card and you lose 1 life.\n−3: Destroy target creature.\n−8: " + OB_NIXILIS, "FULL"),
    # two quoted abilities, each read (wave 26A); refused: a text the grammar can't read / an activated ability / a rule the command zone isn't read for
    ("Tamiyo, the Moon Sage", '−8: You get an emblem with "You have no maximum hand size" and "Whenever a card is put into your graveyard from '
     'anywhere, you may return it to your hand."', "FULL"),
    ("Two-Ability Refusal", '−8: You get an emblem with "You have no maximum hand size" and "{2}: Draw a card."',
     "PARTIAL"),
    ("Ob Nixilis of the Black Oath", "−8: You get an emblem with \"{1}{B}, Sacrifice a creature: You gain X life and draw X cards, where X is "
     "the sacrificed creature's power.\"", "FULL"),  # (wave 110O: activated from the command zone)
    ("Mordenkainen", '−7: You get an emblem with "You have no maximum hand size."', "FULL"),  # (wave 20C: the command zone is read for it)
])
def test_emblem_cards_are_full_only_when_every_quoted_ability_is_read(name, text, level, tmp_path):
    assert coverage.of_card_data(planeswalker(name, text)).level == level

