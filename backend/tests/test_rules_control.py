"""Gain / exchange control (wave 3K), read against CR 613.1b (layer 2: control-changing effects), 613.7
(timestamps), 611.2a-c (durations; the objects a resolved effect affects are fixed when it begins), 701.12
(exchange: all or nothing), 302.6 (summoning sickness restarts), 400.7 (a control change is not a new
object), 800.4a (a leaving player's control effects end) and 110.2. The cards are real Commander cards, their
Oracle text transcribed from the card database. Every scenario also checks that replaying the recorded
history reproduces the table exactly, and most that a reload does."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_delayed import next_end_step, reloaded, responsive
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches


def sorcery(name, number, text, cost, cmc, colors, type_line="Sorcery"):
    return card(name, set_code="tst", number=number, mana_cost=cost, cmc=float(cmc), type_line=type_line, oracle_text=text,
                colors=colors, color_identity=colors)


REAL = [
    sorcery("Threaten", "K1", "Untap target creature and gain control of it until end of turn. That creature gains haste until end of turn. "
            "(It can attack and {T} this turn.)", "{2}{R}", 3, ["R"]),
    sorcery("Act of Treason", "K2", "Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. "
            "(It can attack and {T} this turn.)", "{2}{R}", 3, ["R"]),
    sorcery("Mind Control", "K3", "Enchant creature\nYou control enchanted creature.", "{3}{U}{U}", 5, ["U"], "Enchantment — Aura"),
    sorcery("Switcheroo", "K4", "Exchange control of two target creatures.", "{4}{U}", 5, ["U"]),
    card("Sower of Temptation", set_code="tst", number="K5", mana_cost="{2}{U}{U}", cmc=4.0, type_line="Creature — Faerie Wizard",
         oracle_text="Flying\nWhen this creature enters, gain control of target creature for as long as this creature remains on the battlefield.",
         power="2", toughness="2", colors=["U"], color_identity=["U"]),
    card("Zealous Conscripts", set_code="tst", number="K6", mana_cost="{4}{R}", cmc=5.0, type_line="Creature — Human Warrior",
         oracle_text="Haste\nWhen this creature enters, gain control of target permanent until end of turn. Untap that permanent. "
                     "It gains haste until end of turn.", power="3", toughness="3", colors=["R"], color_identity=["R"]),
    sorcery("Dominate", "K7", "Gain control of target creature with mana value X or less.", "{X}{1}{U}{U}", 3, ["U"], "Instant"),
    card("Agent of Treachery", set_code="tst", number="K8", mana_cost="{5}{U}{U}", cmc=7.0, type_line="Creature — Human Rogue",
         oracle_text="When this creature enters, gain control of target permanent.\nAt the beginning of your end step, if you control three "
                     "or more permanents you don't own, draw three cards.", power="2", toughness="3", colors=["U"], color_identity=["U"]),
    sorcery("Wrong Turn", "K9", "Target opponent gains control of target creature. (If an attacking or blocking creature changes "
            "controllers, it's removed from combat.)", "{2}{U}", 3, ["U"], "Instant"),
    sorcery("Harmless Offering", "K10", "Target opponent gains control of target permanent you control.", "{2}{R}", 3, ["R"]),
    card("Vedalken Plotter", set_code="tst", number="K11", mana_cost="{2}{U}", cmc=3.0, type_line="Creature — Vedalken Wizard",
         oracle_text="When this creature enters, exchange control of target land you control and target land an opponent controls.",
         power="1", toughness="1", colors=["U"], color_identity=["U"]),
    card("Olivia Voldaren", set_code="tst", number="K12", mana_cost="{2}{B}{R}", cmc=4.0, type_line="Legendary Creature — Vampire",
         oracle_text="Flying\n{3}{B}{B}: Gain control of target Vampire for as long as you control Olivia Voldaren.",
         power="3", toughness="3", colors=["B", "R"], color_identity=["B", "R"]),
    card("Vampire Test", set_code="tst", number="K15", mana_cost="{1}{B}", cmc=2.0, type_line="Creature — Vampire",
         oracle_text="", power="2", toughness="2", colors=["B"], color_identity=["B"]),
    card("Hill Giant Test", set_code="tst", number="K13", mana_cost="{3}{R}", cmc=4.0, type_line="Creature — Giant",
         oracle_text="", power="3", toughness="3", colors=["R"], color_identity=["R"]),
    card("Captivating Crew", set_code="tst", number="K14", mana_cost="{3}{R}", cmc=4.0, type_line="Creature — Human Pirate",
         oracle_text="{3}{R}: Gain control of target creature an opponent controls until end of turn. Untap that creature. It gains haste "
                     "until end of turn. Activate only as a sorcery.", power="4", toughness="3", colors=["R"], color_identity=["R"]),
]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ["Threaten", "Act of Treason", "Mind Control", "Switcheroo", "Sower of Temptation", "Zealous Conscripts", "Dominate",
         "Agent of Treachery", "Wrong Turn", "Harmless Offering", "Vedalken Plotter", "Olivia Voldaren", "Hill Giant Test",
         "Captivating Crew"]


def build(cards, three=False):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in NAMES), (2, "Grizzly Bears"), (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Grizzly Bears"), (1, "Llanowar Elves"), (1, "Hill Giant Test"), (1, "Vampire Test"),
                                                  (20, "Island")])
    players = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)]
    if three:
        players.append(PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(2, "Grizzly Bears"), (20, "Mountain")])))
    state = new_game(players, shuffle=False)
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def put(s, name, zone="battlefield", pid="p1", nth=0):
    cs = [c for c in s.state.cards.values() if c.name == name and c.owner == pid]
    c = cs[nth]
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": zone, "player": pid} if zone != "battlefield" else {"zone": zone, "player": pid})
    return s.state.cards[c.id]


def cast(s, name, targets=None, pid="p1", counts=None, **m):
    c = put(s, name, "hand", pid)
    if m:
        mana(s, pid, **m)
    kw = {"targets": targets} if targets is not None else {}
    if counts is not None:
        kw["target_counts"] = counts
    act(s, pid, type="cast_spell", card_id=c.id, **kw)
    pass_until_stack_empty(s)
    return c


def answer(s, *ids):
    """Choose the targets a triggered ability asks for (each pending decision takes the next id)."""
    for want in ids:
        d = s.state.rules.decision
        assert d is not None, "no decision to answer"
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[want])
    pass_until_stack_empty(s)


def look(s):
    """The engine looks at the table again with the next action (after something was moved by hand)."""
    act(s, s.state.rules.priority, type="pass_priority")


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def oid(s, c):
    return s.state.rules.object_id(c.id)


def check(s):
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


# -- the wording --------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,do", [
    ("Untap target creature and gain control of it until end of turn. That creature gains haste until end of turn.", "gain_control"),
    ("Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.", "gain_control"),
    ("Gain control of target creature with mana value X or less.", "gain_control"),
    ("Gain control of target permanent.", "gain_control"),
    ("Target opponent gains control of target creature.", "gain_control"),
    ("Exchange control of two target creatures.", "exchange_control"),
    ("Exchange control of target artifact or creature you control and target creature an opponent controls with power 3 or less.",
     "exchange_control"),
    ("Untap all creatures and gain control of them until end of turn. They gain haste until end of turn.", "gain_control"),
])
def test_the_grammar_reads_control_changes(text, do):
    found = scripts.parse_effects(text)
    assert found is not None and found[0][0]["do"] == do


@pytest.mark.parametrize("text", [
    "Gain control of target creature until the end of your next turn.",  # (a duration the engine doesn't model)
    "Each opponent gains control of a creature of their choice.",  # (a choice on resolution)
    "Exchange control of target creature and another target creature you control and two target lands.",
])
def test_unread_wordings_stay_manual(text):
    assert scripts.parse_effects(text) is None


def test_the_static_line_of_an_aura_is_read():
    ch = characteristics_of_text("You control enchanted creature.")
    assert ch["static"] == "control" and ch["who"] == "host"


def characteristics_of_text(text):
    from app.rules.characteristics import AbilityText, Characteristics

    ab = AbilityText(index=0, kind="static", text=text)
    return scripts.define(ab, Characteristics(name="Mind Control", abilities=(ab,)))


# -- Threaten / Act of Treason: until end of turn (611.2a, 514.2) --------------------------------------
def test_threaten_takes_untaps_hastes_and_gives_it_back_at_cleanup(cards):
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p2")
    act(s, "p2", type="tap", card_ids=[bear.id], tapped=True)
    before = oid(s, bear)
    cast(s, "Threaten", [bear.id], R=3)
    now = s.state.cards[bear.id]
    assert now.controller == "p1" and now.zone == "p1:battlefield" and not now.tapped  # 613.1b, "untap it"
    assert "haste" in chars(s, now).keywords
    assert oid(s, now) == before  # 400.7: a control change is not a new object
    assert s.state.rules.controlled_since[bear.id].controller == "p1"  # 302.6: it starts over; haste is why it may attack
    assert [e.layer for e in s.state.rules.effects if e.new_controller] == ["2"]
    next_end_step(s)
    back = s.state.cards[bear.id]
    assert back.controller == "p2" and back.zone == "p2:battlefield" and oid(s, back) == before
    assert not any(e.new_controller for e in s.state.rules.effects) and s.state.rules.control_changed == []
    assert "haste" not in chars(s, back).keywords
    check(s)


def test_act_of_treason_can_attack_only_thanks_to_haste(cards):
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p2")
    cast(s, "Act of Treason", [bear.id], R=3)
    assert s.state.cards[bear.id].controller == "p1" and "haste" in chars(s, bear).keywords
    check(s)


def test_the_effect_locks_its_objects_when_it_begins(cards):
    """611.2c: a creature that enters later is not affected, and a creature that left and returned is a new object."""
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p2")
    cast(s, "Act of Treason", [bear.id], R=3)
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "hand", "player": "p2"})
    act(s, "p2", type="move", card_ids=[bear.id], to={"zone": "battlefield", "player": "p2"})
    assert s.state.cards[bear.id].controller == "p2"  # the new object isn't under the old effect (400.7)
    check(s)


def test_a_target_that_changed_before_resolution_is_not_taken(cards):
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p2")
    spell = put(s, "Act of Treason", "hand")
    mana(s, "p1", R=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    act(s, "p2", type="move", card_ids=[bear.id], to={"zone": "graveyard", "player": "p2"})  # (gone in response)
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].zone == "p2:graveyard" and s.state.cards[bear.id].controller == "p2"
    check(s)


# -- Mind Control: a static ability of the Aura (611.3, 613.1b) -------------------------------------------
def test_mind_control_lasts_while_the_aura_is_attached(cards):
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p2")
    aura = cast(s, "Mind Control", [bear.id], U=2, C=3)
    assert s.state.cards[aura.id].attached_to == bear.id
    assert s.state.cards[bear.id].controller == "p1" and s.state.cards[bear.id].zone == "p1:battlefield"
    next_end_step(s)  # no duration: it stays under control
    assert s.state.cards[bear.id].controller == "p1"
    act(s, "p1", type="move", card_ids=[aura.id], to={"zone": "graveyard", "player": "p1"})  # the Aura leaves
    look(s)
    assert s.state.cards[bear.id].controller == "p2" and s.state.cards[bear.id].zone == "p2:battlefield"
    check(s)


def test_the_later_timestamp_wins_between_an_aura_and_a_resolved_effect(cards):
    """613.7: Alice's Mind Control (a static, earlier) is beaten by Wrong Turn's later effect; the creature stays with Bob
    when the Aura goes."""
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p2")
    aura = cast(s, "Mind Control", [bear.id], U=2, C=3)
    assert s.state.cards[bear.id].controller == "p1"
    cast(s, "Wrong Turn", ["p2", bear.id], counts=[1, 1], U=1, C=2)
    assert s.state.cards[bear.id].controller == "p2"  # the later effect beats the Aura's static ability
    act(s, "p1", type="move", card_ids=[aura.id], to={"zone": "graveyard", "player": "p1"})
    look(s)
    assert s.state.cards[bear.id].controller == "p2"
    check(s)


# -- permanent: Agent of Treachery (611.2a: no duration, the game) -------------------------------------------
def test_agent_of_treachery_steals_for_good(cards):
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p2")
    agent = cast(s, "Agent of Treachery", None, U=2, C=5)
    answer(s, bear.id)
    assert s.state.cards[agent.id].zone == "p1:battlefield"
    assert s.state.cards[bear.id].controller == "p1"
    next_end_step(s)
    assert s.state.cards[bear.id].controller == "p1"
    act(s, "p1", type="move", card_ids=[agent.id], to={"zone": "graveyard", "player": "p1"})  # the thief leaves: still stolen
    look(s)
    assert s.state.cards[bear.id].controller == "p1"
    check(s)


def test_stolen_permanent_reverts_to_the_earlier_thief_not_the_owner(cards):
    """Alice's Bear is stolen for good by Bob (Agent of Treachery in Bob's hands is not in the deck: use Wrong Turn-style
    permanent give), then Alice takes it back until end of turn: at cleanup it is Bob's again, not Alice's."""
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p1")
    cast(s, "Wrong Turn", ["p2", bear.id], counts=[1, 1], U=1, C=2)  # Alice gives her own Bear to Bob (permanent)
    # (Wrong Turn: "Target opponent gains control of target creature")
    assert s.state.cards[bear.id].controller == "p2"
    cast(s, "Act of Treason", [bear.id], R=3)
    assert s.state.cards[bear.id].controller == "p1"
    next_end_step(s)
    assert s.state.cards[bear.id].controller == "p2"  # back to Bob's permanent effect, not the owner
    assert s.state.cards[bear.id].owner == "p1"
    check(s)


# -- target opponent gains control ---------------------------------------------------------------------------
def test_wrong_turn_gives_a_creature_to_an_opponent(cards):
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p1")
    cast(s, "Wrong Turn", ["p2", bear.id], counts=[1, 1], U=1, C=2)
    assert s.state.cards[bear.id].controller == "p2" and s.state.cards[bear.id].zone == "p2:battlefield"
    check(s)


# -- exchange (701.12) ---------------------------------------------------------------------------------------------
def test_switcheroo_exchanges_two_creatures(cards):
    s = build(cards)
    mine = put(s, "Grizzly Bears", pid="p1")
    theirs = put(s, "Llanowar Elves", pid="p2")
    cast(s, "Switcheroo", [mine.id, theirs.id], counts=[2], U=1, C=4)
    assert s.state.cards[mine.id].controller == "p2" and s.state.cards[theirs.id].controller == "p1"
    assert s.state.cards[mine.id].owner == "p1"
    next_end_step(s)  # permanent
    assert s.state.cards[mine.id].controller == "p2" and s.state.cards[theirs.id].controller == "p1"
    check(s)


def test_exchange_with_an_illegal_target_does_nothing(cards):
    """701.12a: if the entire exchange can't be completed, no part of it occurs (the other creature stays put)."""
    s = build(cards)
    mine = put(s, "Grizzly Bears", pid="p1")
    theirs = put(s, "Llanowar Elves", pid="p2")
    spell = put(s, "Switcheroo", "hand")
    mana(s, "p1", U=1, C=4)
    responsive(s)  # (Bob gets priority with the spell on the stack)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[mine.id, theirs.id], target_counts=[2])
    act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "graveyard", "player": "p2"})  # destroyed in response
    pass_until_stack_empty(s)
    print("DBG2", [(e.layer, e.new_controller, e.affected) for e in s.state.rules.effects], s.state.cards[mine.id].controller, s.state.cards[theirs.id].controller, s.state.cards[theirs.id].zone)
    assert s.state.cards[mine.id].controller == "p1" and s.state.cards[mine.id].zone == "p1:battlefield"
    check(s)


def test_exchange_of_two_creatures_one_player_controls_does_nothing(cards):
    s = build(cards)
    a = put(s, "Grizzly Bears", pid="p1", nth=0)
    b = put(s, "Grizzly Bears", pid="p1", nth=1)
    cast(s, "Switcheroo", [a.id, b.id], counts=[2], U=1, C=4)
    assert s.state.cards[a.id].controller == "p1" and s.state.cards[b.id].controller == "p1"  # 701.12b
    assert not any(e.new_controller for e in s.state.rules.effects)
    check(s)


def test_vedalken_plotter_exchanges_lands_of_two_players(cards):
    s = build(cards)
    mine = put(s, "Forest", pid="p1")
    theirs = put(s, "Island", pid="p2")
    cast(s, "Vedalken Plotter", None, U=1, C=2)
    answer(s, mine.id, theirs.id)
    assert s.state.cards[mine.id].controller == "p2" and s.state.cards[theirs.id].controller == "p1"
    check(s)


# -- "for as long as ~ remains on the battlefield" (611.2b) -------------------------------------------------------
def test_sower_of_temptation_controls_while_it_remains(cards):
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p2")
    sower = cast(s, "Sower of Temptation", None, U=2, C=2)
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
        pass_until_stack_empty(s)
    assert s.state.cards[bear.id].controller == "p1"
    next_end_step(s)  # no end-of-turn limit
    assert s.state.cards[bear.id].controller == "p1"
    act(s, "p1", type="move", card_ids=[sower.id], to={"zone": "graveyard", "player": "p1"})  # it leaves: the effect ends
    look(s)
    assert s.state.cards[bear.id].controller == "p2" and s.state.cards[bear.id].zone == "p2:battlefield"
    check(s)


def test_olivia_controls_a_vampire_only_while_you_control_olivia(cards):
    s = build(cards)
    olivia = put(s, "Olivia Voldaren", pid="p1")
    theirs = put(s, "Vampire Test", pid="p2")
    mana(s, "p1", B=2, C=3)
    act(s, "p1", type="activate_ability", card_id=olivia.id, ability=1, targets=[theirs.id])
    pass_until_stack_empty(s)
    assert s.state.cards[theirs.id].controller == "p1"
    next_end_step(s)  # no end-of-turn limit
    assert s.state.cards[theirs.id].controller == "p1"
    assert any(e.duration == "source_controlled" for e in s.state.rules.effects)
    act(s, "p1", type="set_controller", card_ids=[olivia.id], player="p2")  # Olivia changes hands: "you control Olivia" is untrue (611.2b)
    look(s)
    assert s.state.cards[theirs.id].controller == "p2"
    assert not any(e.new_controller for e in s.state.rules.effects)  # the effect ended; it did not wait for the turn to end
    check(s)


def test_a_duration_that_is_already_over_does_nothing(cards):
    """611.2b: Sower's trigger finds Sower gone as it resolves: it does nothing (the creature is never taken)."""
    s = build(cards)
    bear = put(s, "Grizzly Bears", pid="p2")
    sower = put(s, "Sower of Temptation", "hand")
    mana(s, "p1", U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=sower.id)
    pass_until_stack_empty(s)
    responsive(s)  # (Bob gets priority with the trigger on the stack)
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
    assert s.state.zones.get("stack")
    act(s, "p1", type="move", card_ids=[sower.id], to={"zone": "graveyard", "player": "p1"})  # (in response to its trigger)
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].controller == "p2"
    check(s)


def test_a_player_leaving_ends_their_control_effects(cards):
    """800.4a: when Alice leaves, her Act of Treason's effect ends and the creature is Bob's again (and stays his)."""
    s = build(cards, three=True)
    bear = put(s, "Grizzly Bears", pid="p2")
    cast(s, "Act of Treason", [bear.id], R=3)
    assert s.state.cards[bear.id].controller == "p1"
    act(s, "p1", type="concede")
    assert s.state.cards[bear.id].controller == "p2" and s.state.cards[bear.id].zone == "p2:battlefield"
    act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[bear.id].controller == "p2"
    replay_matches(s)


# -- Zealous Conscripts: a permanent until end of turn ------------------------------------------------------------
def test_zealous_conscripts_takes_a_permanent_until_end_of_turn(cards):
    s = build(cards)
    land = put(s, "Island", pid="p2")
    cast(s, "Zealous Conscripts", [land.id], R=1, C=4)
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[land.id])
        pass_until_stack_empty(s)
    assert s.state.cards[land.id].controller == "p1"
    next_end_step(s)
    assert s.state.cards[land.id].controller == "p2"
    check(s)


# -- Dominate (X) ------------------------------------------------------------------------------------------------------
def test_dominate_takes_a_creature_with_mana_value_x_or_less(cards):
    s = build(cards)
    giant = put(s, "Hill Giant Test", pid="p2")  # mana value 4
    bear = put(s, "Grizzly Bears", pid="p2")  # mana value 2
    spell = put(s, "Dominate", "hand")
    mana(s, "p1", U=2, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[giant.id], x_value=2)  # 4 > X
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], x_value=2)
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].controller == "p1" and s.state.cards[giant.id].controller == "p2"
    check(s)


# -- an activated ability: Captivating Crew ---------------------------------------------------------------------------
def test_captivating_crew_steals_until_end_of_turn(cards):
    s = build(cards)
    crew = put(s, "Captivating Crew", pid="p1")
    bear = put(s, "Grizzly Bears", pid="p2")
    mana(s, "p1", R=1, C=3)
    act(s, "p1", type="activate_ability", card_id=crew.id, ability=0, targets=[bear.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].controller == "p1"
    next_end_step(s)
    assert s.state.cards[bear.id].controller == "p2"
    check(s)
