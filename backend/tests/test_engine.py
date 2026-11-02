from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.game.errors import ActionError
from app.game.state import ALL, STACK
from app.game.visibility import can_see
from tests.game_helpers import act, find, make_session, zone


@pytest.fixture()
def s(cards):
    return make_session(cards)


def test_new_game_layout(s):
    st = s.state
    assert [p.name for p in st.players.values()] == ["Alice", "Bob"]
    assert st.players["p1"].life == 40
    assert len(zone(st, "p1", "library")) == 15
    assert len(zone(st, "p1", "command")) == 1
    assert len(zone(st, "p1", "sideboard")) == 1
    krenko = find(st, "Krenko, Mob Boss")
    assert krenko.commander_key and krenko.protected
    assert st.players["p1"].commander_tax == {krenko.commander_key: 0}


def test_draw_moves_top_cards(s):
    top = zone(s.state, "p1", "library")[:2]
    act(s, "p1", type="draw", count=2)
    assert zone(s.state, "p1", "hand") == top
    assert len(zone(s.state, "p1", "library")) == 13
    assert s.state.log[-1].parts[1].t == " drew 2 cards"


def test_draw_from_empty_library_is_an_error_and_state_is_untouched(s):
    act(s, "p1", type="draw", count=15)
    seq = s.state.seq
    with pytest.raises(ActionError):
        act(s, "p1", type="draw")
    assert s.state.seq == seq


def test_move_between_all_major_zones(s):
    act(s, "p1", type="draw", count=15)
    sol = find(s.state, "Sol Ring")
    for zone_name in ("battlefield", "graveyard", "exile", "command", "hand", "library", "sideboard", "companion"):
        act(s, "p1", type="move", card_ids=[sol.id], to={"zone": zone_name})
        assert s.state.cards[sol.id].zone == f"p1:{zone_name}"
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "stack"})
    assert s.state.zones[STACK] == [sol.id]


def test_play_to_battlefield_sets_position_and_leaving_resets_state(s):
    act(s, "p1", type="draw", count=15)
    sol = find(s.state, "Sol Ring")
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "battlefield"}, x=300, y=200)
    c = s.state.cards[sol.id]
    assert (c.x, c.y, c.controller) == (300, 200, "p1")
    act(s, "p1", type="tap", card_ids=[sol.id])
    act(s, "p1", type="counter", card_ids=[sol.id], kind="charge", delta=2)
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "graveyard"})
    assert not c.tapped and c.counters == {}
    assert zone(s.state, "p1", "graveyard")[-1] == sol.id


def test_default_placement_rows(s):
    act(s, "p1", type="draw", count=15)
    mountain = find(s.state, "Mountain")
    elves = find(s.state, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[mountain.id, elves.id], to={"zone": "battlefield"})
    assert s.state.cards[mountain.id].y > s.state.cards[elves.id].y  # lands sit closer to the player


def test_library_top_bottom_and_index(s):
    lib = zone(s.state, "p1", "library")
    first, second, last = lib[0], lib[1], lib[-1]
    act(s, "p1", type="move", card_ids=[first], to={"zone": "library"}, position="bottom")
    assert lib[-1] == first and lib[0] == second
    act(s, "p1", type="move", card_ids=[last], to={"zone": "library"}, position="top")
    assert lib[0] == last
    act(s, "p1", type="move", card_ids=[last], to={"zone": "library"}, index=3)
    assert lib[3] == last


def test_tap_toggle_and_untap_all(s):
    act(s, "p1", type="draw", count=15)
    ids = [c.id for c in s.state.cards.values() if c.name == "Mountain"][:3]
    act(s, "p1", type="move", card_ids=ids, to={"zone": "battlefield"})
    act(s, "p1", type="tap", card_ids=ids)
    assert all(s.state.cards[i].tapped for i in ids)
    act(s, "p1", type="tap", card_ids=[ids[0]])
    assert not s.state.cards[ids[0]].tapped
    act(s, "p1", type="untap_all")
    assert not any(s.state.cards[i].tapped for i in ids)
    with pytest.raises(ActionError):
        act(s, "p1", type="tap", card_ids=[zone(s.state, "p2", "library")[0]])  # not on battlefield


def test_counters(s):
    krenko = find(s.state, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[krenko.id], kind="+1/+1", delta=3)
    act(s, "p1", type="counter", card_ids=[krenko.id], kind="shield", delta=1)
    act(s, "p1", type="counter", card_ids=[krenko.id], kind="+1/+1", delta=-1)
    assert krenko.counters == {"+1/+1": 2, "shield": 1}
    act(s, "p1", type="counter", card_ids=[krenko.id], kind="shield", delta=-5)
    assert krenko.counters == {"+1/+1": 2}
    act(s, "p1", type="set_counter", card_id=krenko.id, kind="-1/-1", value=0, rename_from="+1/+1")
    assert krenko.counters == {"-1/-1": 2}


def test_tokens_from_db_and_custom(s):
    from tests.fixtures.cards import GOBLIN

    act(s, "p1", type="create_token", token={"card_id": GOBLIN["id"]}, count=3)
    goblins = [c for c in s.state.cards.values() if c.is_token]
    assert len(goblins) == 3
    assert goblins[0].token.power == "1" and goblins[0].name == "Goblin"
    assert all(c.zone == "p1:battlefield" for c in goblins)
    assert len({(c.x, c.y) for c in goblins}) == 3  # fanned out, not stacked exactly
    act(s, "p2", type="create_token", token={"name": "Spirit", "power": "1", "toughness": "1", "colors": ["W"],
                                             "type_line": "Token Creature — Spirit", "text": "Flying"})
    spirit = find(s.state, "Spirit")
    assert spirit.owner == "p2" and spirit.token.text == "Flying"
    # tokens cease to exist when they leave the battlefield
    act(s, "p1", type="move", card_ids=[goblins[0].id], to={"zone": "graveyard"})
    assert goblins[0].id not in s.state.cards
    act(s, "p1", type="delete_card", card_ids=[goblins[1].id])
    assert goblins[1].id not in s.state.cards
    with pytest.raises(ActionError):
        act(s, "p1", type="delete_card", card_ids=[find(s.state, "Krenko, Mob Boss").id])


def test_copies_reference_source_and_are_independent(s):
    krenko = find(s.state, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"}, x=100, y=100)
    act(s, "p2", type="copy_card", card_id=krenko.id, modifications="not legendary")
    copy = next(c for c in s.state.cards.values() if c.copy_of)
    assert copy.copy_of.source_id == krenko.id
    assert copy.copy_of.modifications == "not legendary"
    assert copy.controller == "p2" and copy.zone == "p2:battlefield" and copy.card_id == krenko.card_id
    act(s, "p2", type="tap", card_ids=[copy.id])
    assert copy.tapped and not krenko.tapped
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "command"})
    assert copy.id in s.state.cards  # independent of its source
    with pytest.raises(ActionError):
        act(s, "p1", type="copy_card", card_id=zone(s.state, "p2", "library")[0])  # hidden card


def test_life_and_history_collapsing(s):
    for _ in range(3):
        act(s, "p2", type="life", player="p1", delta=-1)
    act(s, "p1", type="life", delta=-2)  # same player again -> still collapses
    act(s, "p1", type="set_life", player="p2", value=35)
    act(s, "p1", type="life", delta=7)
    hist = s.state.players["p1"].life_history
    assert [(h.before, h.after) for h in hist] == [(40, 35), (35, 42)]
    assert s.state.players["p1"].life == 42
    assert s.state.players["p2"].life == 35


def test_commander_damage_and_tax(s):
    krenko = find(s.state, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "stack"})
    assert s.state.players["p1"].commander_tax[krenko.commander_key] == 2
    act(s, "p1", type="commander_tax", commander=krenko.commander_key, value=0)
    assert s.state.players["p1"].commander_tax[krenko.commander_key] == 0
    act(s, "p1", type="commander_damage", player="p2", commander=krenko.commander_key, delta=15)
    act(s, "p1", type="commander_damage", player="p2", commander=krenko.commander_key, delta=6)
    bob = s.state.players["p2"]
    assert bob.commander_damage[krenko.commander_key] == 21
    assert bob.life == 19
    assert "21+ commander damage" in s.state.log[-1].parts[-1].t
    act(s, "p1", type="commander_damage", player="p2", commander=krenko.commander_key, delta=-1, affect_life=False)
    assert bob.commander_damage[krenko.commander_key] == 20 and bob.life == 19


def test_resources_and_table_markers(s):
    act(s, "p1", type="resource", player="p2", key="poison", delta=10)
    assert "10+ poison" in s.state.log[-1].parts[-1].t
    act(s, "p1", type="resource", key="Rad", delta=3)
    assert s.state.players["p1"].resources["rad"] == 3
    act(s, "p1", type="set_resource", key="rad", value=None)
    assert "rad" not in s.state.players["p1"].resources
    act(s, "p1", type="set_monarch", player="p2")
    act(s, "p1", type="set_initiative", player="p1")
    act(s, "p1", type="set_day_night", value="night")
    act(s, "p1", type="city_blessing", player="p1")
    assert (s.state.table.monarch, s.state.table.initiative, s.state.table.day_night) == ("p2", "p1", "night")
    assert s.state.players["p1"].city_blessing


def test_shuffle_rekeys_and_randomizes(s):
    before = list(zone(s.state, "p1", "library"))
    names_before = sorted(s.state.cards[c].name for c in before)
    act(s, "p1", type="shuffle")
    after = zone(s.state, "p1", "library")
    assert not set(before) & set(after)  # every id replaced
    assert sorted(s.state.cards[c].name for c in after) == names_before


def test_client_cannot_choose_randomness(s):
    before = list(zone(s.state, "p1", "library"))
    forged = {"perm": list(range(len(before))), "new_ids": before}
    act(s, "p1", type="shuffle", r=forged)
    assert zone(s.state, "p1", "library") != before
    rolled = act(s, "p1", type="roll", sides=6, count=50, r={"results": [6] * 50})
    assert rolled.r.results != [6] * 50
    assert all(1 <= x <= 6 for x in rolled.r.results)


def test_unknown_or_malformed_actions_rejected(s):
    with pytest.raises(ValidationError):
        act(s, "p1", type="launch_missiles")
    with pytest.raises(ValidationError):
        act(s, "p1", type="draw", count=10_000)
    with pytest.raises(ValidationError):
        act(s, "p1", type="move", card_ids=["../../etc"], to={"zone": "hand"})
    with pytest.raises(ValidationError):
        act(s, "p1", type="draw", sneaky=True)
    with pytest.raises(ActionError):
        s.perform("p9", {"type": "draw"})


def test_mulligan(s):
    act(s, "p1", type="draw", count=7)
    act(s, "p1", type="mulligan")
    assert len(zone(s.state, "p1", "hand")) == 7
    assert len(zone(s.state, "p1", "library")) == 8
    assert s.state.players["p1"].mulligans == 1


def test_mill_reveal_look(s):
    top3 = zone(s.state, "p2", "library")[:3]
    act(s, "p1", type="look_top", player="p2", count=2)
    assert [(v.viewer, v.kind, v.card_ids) for v in s.state.views] == [("p1", "look", top3[:2])]
    act(s, "p2", type="mill", count=3)
    assert zone(s.state, "p2", "graveyard") == top3
    act(s, "p2", type="reveal_top")
    assert s.state.cards[zone(s.state, "p2", "library")[0]].revealed_to == [ALL]


def test_stack_resolution(s):
    act(s, "p1", type="draw", count=15)
    bolt, elves = find(s.state, "Lightning Bolt"), find(s.state, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "stack"})
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "stack"})
    act(s, "p1", type="create_ability", text="Add {G}", source_id=elves.id)
    assert len(s.state.zones[STACK]) == 3
    act(s, "p1", type="resolve_top")  # ability disappears
    assert len(s.state.zones[STACK]) == 2
    act(s, "p1", type="resolve_top")  # instant -> graveyard
    assert bolt.zone == "p1:graveyard"
    act(s, "p1", type="resolve_top")  # creature -> battlefield
    assert elves.zone == "p1:battlefield"
    with pytest.raises(ActionError):
        act(s, "p1", type="resolve_top")


def test_adventure_resolves_to_exile(s):
    act(s, "p2", type="draw", count=17)
    giant = find(s.state, "Bonecrusher Giant // Stomp")
    act(s, "p2", type="move", card_ids=[giant.id], to={"zone": "stack"})
    act(s, "p2", type="set_face", card_id=giant.id, face=1)
    act(s, "p2", type="resolve_top")
    assert giant.zone == "p2:exile"


def test_phases_turns_and_combat(s):
    act(s, "p1", type="phase", to="declare_attackers")
    krenko = find(s.state, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="tap", card_ids=[krenko.id])
    act(s, "p1", type="attack", card_ids=[krenko.id], target={"kind": "player", "id": "p2"})
    atraxa = find(s.state, "Atraxa, Praetors' Voice")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"zone": "battlefield"})
    act(s, "p2", type="block", card_id=atraxa.id, attacker_id=krenko.id)
    assert atraxa.blocking == krenko.id and krenko.attacking.id == "p2"
    act(s, "p1", type="phase", to="main2")
    assert krenko.attacking is not None  # nothing clears itself…
    act(s, "p1", type="clear_combat")  # …until a player clears combat
    assert krenko.attacking is None and atraxa.blocking is None
    act(s, "p1", type="configure", auto_clear_combat=True)  # or the table opts in
    act(s, "p1", type="phase", to="declare_attackers")
    act(s, "p1", type="attack", card_ids=[krenko.id], target={"kind": "player", "id": "p2"})
    act(s, "p1", type="phase", to="main2")
    assert krenko.attacking is None
    act(s, "p1", type="next_turn")
    assert (s.state.turn.number, s.state.turn.active_player, s.state.turn.phase) == (2, "p2", "untap")
    assert krenko.tapped  # only the new active player untaps
    act(s, "p2", type="next_turn")
    assert not krenko.tapped
    with pytest.raises(ActionError):
        act(s, "p1", type="phase", to="prev")


def test_face_down_and_faces(s):
    act(s, "p1", type="draw", count=15)
    delver = find(s.state, "Delver of Secrets // Insectile Aberration")
    act(s, "p1", type="move", card_ids=[delver.id], to={"zone": "battlefield"}, face_down=True)
    assert delver.face_down and can_see(s.state, delver, "p1") and not can_see(s.state, delver, "p2")
    act(s, "p1", type="face_down", card_ids=[delver.id], face_down=False)
    act(s, "p1", type="set_face", card_id=delver.id)
    assert delver.face == 1
    act(s, "p1", type="set_face", card_id=delver.id)
    assert delver.face == 0
    act(s, "p1", type="face_down", card_ids=[delver.id])
    # no memory: once face down it is anonymous to opponents, even though they saw it a moment ago
    assert delver.face_down and not can_see(s.state, delver, "p2")


def test_notes_and_control(s):
    krenko = find(s.state, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="note", card_id=krenko.id, text="  exiled with Oblivion Ring ")
    assert krenko.note == "exiled with Oblivion Ring"
    act(s, "p2", type="set_controller", card_ids=[krenko.id], player="p2")
    assert krenko.zone == "p2:battlefield" and krenko.controller == "p2" and krenko.owner == "p1"
    act(s, "p2", type="move", card_ids=[krenko.id], to={"zone": "graveyard"})
    assert krenko.zone == "p1:graveyard"  # cards go to their owner's graveyard


def test_dice_and_coins(s):
    r = act(s, "p1", type="roll", sides=20)
    assert 1 <= r.r.results[0] <= 20
    assert "on a d20" in s.state.log[-1].parts[-1].t
    r = act(s, "p1", type="roll", sides=6, count=3)
    assert len(r.r.results) == 3
    r = act(s, "p1", type="coin", count=5)
    assert set(r.r.results) <= {0, 1}


def test_dice_rolls_carry_their_numbers_to_every_table(s):
    """Every viewer's log has the roll's numbers, so each table can show the dice landing."""
    from app.game.views import build_view

    r = act(s, "p1", type="roll", sides=6, count=2)
    roll = s.state.log[-1].roll
    assert roll is not None and roll.sides == 6 and roll.results == r.r.results and not roll.coin
    for viewer in ("p1", "p2"):
        entry = build_view(s.state, viewer)["log"][-1]
        assert entry["roll"] == {"sides": 6, "results": r.r.results, "coin": False, "ignored": []}
    act(s, "p1", type="coin")
    assert s.state.log[-1].roll is not None and s.state.log[-1].roll.coin
    act(s, "p1", type="chat", text="gg")
    assert "roll" not in build_view(s.state, "p2")["log"][-1]


def test_reveal_until_a_type_reveals_down_to_the_first_one_for_everyone(s):
    """The scripted tables' "reveal until type": the server reads the types, every player sees the cards."""
    from app.game.views import build_view

    top = zone(s.state, "p1", "library")[:4]
    act(s, "p1", type="reveal_until", card_type="Creature")
    elves = find(s.state, "Llanowar Elves")
    dig = s.state.log[-1].dig
    assert dig is not None and dig.mode == "reveal_until" and dig.cards == top[:3] and dig.hit == elves.id
    known = build_view(s.state, "p2")["zones"]["p1:library"]["known"]
    assert [cid for _, cid in known] == top[:3]  # Bob sees the three, not the fourth
    assert len(zone(s.state, "p1", "library")) == 15  # nothing moved
    act(s, "p2", type="reveal_until", card_type="Planeswalker")
    miss = s.state.log[-1]
    assert miss.dig is not None and miss.dig.hit is None and len(miss.dig.cards) == 16
    assert "no Planeswalker" in miss.parts[-1].t


def test_cascade_exiles_down_to_a_cheaper_nonland_card(s):
    act(s, "p1", type="mill", count=3)  # Sol Ring, Lightning Bolt and Llanowar Elves off the top
    act(s, "p1", type="cascade", below=4)
    exile = zone(s.state, "p1", "exile")
    names = [s.state.cards[c].name for c in exile]
    assert names[0] == "Fire // Ice" and names[1].startswith("Delver of Secrets") and len(names) == 2  # mana value 4 isn't less than 4
    assert not any(s.state.cards[c].face_down for c in exile)
    dig = s.state.log[-1].dig
    assert dig is not None and dig.mode == "cascade" and dig.hit == exile[-1]


def test_fetch_a_basic_land_then_shuffle(s):
    before = set(zone(s.state, "p1", "library"))
    act(s, "p1", type="fetch_card", name="Mountain")
    hand = zone(s.state, "p1", "hand")
    assert [s.state.cards[c].name for c in hand] == ["Mountain"]
    assert len(zone(s.state, "p1", "library")) == 14
    assert not set(zone(s.state, "p1", "library")) & before  # shuffled: every library id re-keyed
    act(s, "p1", type="fetch_card", name="mountain", to="battlefield")
    land = s.state.cards[zone(s.state, "p1", "battlefield")[-1]]
    assert land.name == "Mountain" and land.x is not None
    with pytest.raises(ActionError):
        act(s, "p1", type="fetch_card", name="Forest")


def test_discard_at_random(s):
    act(s, "p1", type="draw", count=3)
    drawn = list(zone(s.state, "p1", "hand"))
    act(s, "p1", type="discard_random", count=1)
    grave = zone(s.state, "p1", "graveyard")
    assert len(grave) == 1 and grave[0] in drawn
    assert len(zone(s.state, "p1", "hand")) == 2
    assert "at random" in s.state.log[-2].parts[1].t or any("at random" in (p.t or "") for e in s.state.log[-3:] for p in e.parts)
    act(s, "p1", type="discard_random", count=5)  # more than the hand: discards what there is
    assert zone(s.state, "p1", "hand") == []
    with pytest.raises(ActionError):
        act(s, "p1", type="discard_random")


def test_exact_copy_keeps_counters_and_markers(s):
    """The scripted tables' exact copy: a plain copy starts bare, an exact one takes the counters and markers."""
    act(s, "p1", type="draw", count=3)
    elves = find(s.state, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[elves.id], kind="+1/+1", delta=2)
    act(s, "p1", type="add_effect", card_ids=[elves.id], name="Flying")
    act(s, "p1", type="copy_card", card_id=elves.id)
    plain = s.state.cards[zone(s.state, "p1", "battlefield")[-1]]
    assert plain.counters == {} and plain.effects == []
    act(s, "p1", type="copy_card", card_id=elves.id, exact=True)
    exact = s.state.cards[zone(s.state, "p1", "battlefield")[-1]]
    assert exact.counters == {"+1/+1": 2}
    assert [e.name for e in exact.effects] == ["Flying"] and exact.effects[0].id != elves.effects[0].id
    assert "an exact copy" in "".join(p.t or "" for p in s.state.log[-1].parts)
