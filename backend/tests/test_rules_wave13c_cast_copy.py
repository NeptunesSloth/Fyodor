"""Casting a copy of a card and prepared (wave 13C), against the stored Comprehensive Rules (2026-09-25): 707.12 (an effect that
instructs a player to cast a copy of an object follows 601.2a-h, the copy created in the zone the object is in and cast
while another ability is resolving; once cast it is a spell that can resolve or be countered), 707.12a (several copies:
each one is cast or not individually), 704.5e (a copy of a card outside the stack and battlefield ceases to exist),
608.3f / 707.10f (a copy of a permanent spell becomes a token as it resolves), 118.9 / 107.3b (without paying its mana
cost). Prepared: 722.3a (the designation, only for a permanent with a prepare spell, once), 722.3c (its controller creates a
copy of it in exile with only the prepare spell's characteristics; it stays there while the permanent remains prepared on
the battlefield, an exception to 704.5e; its controller may cast it; the permanent loses the designation as the copy is
cast, 601.2i), 722.4 (in every other zone only its normal characteristics). Real Oracle text of Mnemonic Deluge, Renegade
Bull, Shiko, Paragon of the Way, Studious First-Year and Woodwork Prodigy."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches, run_until

REAL = [
    card("Mnemonic Deluge", set_code="tst", number="R1301", mana_cost="{6}{U}{U}{U}", cmc=9.0, type_line="Sorcery", colors=["U"],
         color_identity=["U"], oracle_text="Exile target instant or sorcery card from a graveyard. Copy that card three times. You "
         "may cast the copies without paying their mana costs. Exile Mnemonic Deluge."),
    card("Renegade Bull", set_code="tst", number="R1302", mana_cost="{4}{R}", cmc=5.0, type_line="Creature — Ox", colors=["R"],
         color_identity=["R"], power="0", toughness="5", keywords=["Trample"], oracle_text="Trample\nWhenever you cast an instant or "
         "sorcery spell, this creature gets +X/+0 until end of turn, where X is that spell's mana value.\nWhenever this creature "
         "attacks, exile up to one target instant or sorcery card from your graveyard and copy it. You may cast the copy without "
         "paying its mana cost."),
    card("Shiko, Paragon of the Way", set_code="tst", number="R1303", mana_cost="{2}{U}{R}{W}", cmc=5.0,
         type_line="Legendary Creature — Spirit Dragon", colors=["R", "U", "W"], color_identity=["R", "U", "W"], power="4",
         toughness="5", keywords=["Flying", "Vigilance"], oracle_text="Flying, vigilance\nWhen Shiko enters, exile target nonland card "
         "with mana value 3 or less from your graveyard. Copy it, then you may cast the copy without paying its mana cost. (A copy "
         "of a permanent spell becomes a token.)"),    card("Studious First-Year // Rampant Growth", set_code="tst", number="R1304", layout="prepare", mana_cost="{G} // {1}{G}", cmc=1.0,
         type_line="Creature — Bear Wizard // Sorcery", colors=["G"], color_identity=["G"], power="1", toughness="1",
         oracle_text="This creature enters prepared. (While it's prepared, you may cast a copy of its spell. Doing so unprepares "
         "it.)\n//\nSearch your library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
         keywords=["Prepared"], card_faces=[
             {"name": "Studious First-Year", "mana_cost": "{G}", "type_line": "Creature — Bear Wizard", "power": "1", "toughness": "1",
              "oracle_text": "This creature enters prepared. (While it's prepared, you may cast a copy of its spell. Doing so unprepares it.)"},
             {"name": "Rampant Growth", "mana_cost": "{1}{G}", "type_line": "Sorcery",
              "oracle_text": "Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle."}]),
    card("Woodwork Prodigy // Soul Tether", set_code="tst", number="R1305", layout="prepare", mana_cost="{2}{R/G} // {2}{R/G}", cmc=3.0,
         type_line="Creature — Cat Druid // Sorcery", colors=["G", "R"], color_identity=["G", "R"], power="3", toughness="3",
         oracle_text="At the beginning of your upkeep, if this creature isn't prepared, it becomes prepared. (While it's prepared, "
         "you may cast a copy of its spell. Doing so unprepares it.)\n//\nDraw a card.", keywords=["Prepared"], card_faces=[
             {"name": "Woodwork Prodigy", "mana_cost": "{2}{R/G}", "type_line": "Creature — Cat Druid", "power": "3", "toughness": "3",
              "oracle_text": "At the beginning of your upkeep, if this creature isn't prepared, it becomes prepared. (While it's "
              "prepared, you may cast a copy of its spell. Doing so unprepares it.)"},
             {"name": "Soul Tether", "mana_cost": "{2}{R/G}", "type_line": "Sorcery", "oracle_text": "Draw a card."}]),
    card("Cackling Counterpart", set_code="tst", number="R1306", mana_cost="{1}{U}{U}", cmc=3.0, type_line="Instant", colors=["U"],
         color_identity=["U"], oracle_text="Create a token that's a copy of target creature you control.\nFlashback {5}{U}{U} (You may "
         "cast this card from your graveyard for its flashback cost. Then exile it.)", keywords=["Flashback"]),
]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, c["name"]) for c in REAL] + [(2, "Lightning Bolt"), (2, "Grizzly Bears"), (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Grizzly Bears"), (20, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def put(s, name, where, pid="p1", nth=0):
    c = [c for c in s.state.cards.values() if c.name == name and c.owner == pid][nth]
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": where, "player": pid})
    return s.state.cards[c.id]


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def step(s):
    d = s.state.rules.decision
    return (d.resume or {}).get("step") if d is not None else None


def test_wordings_are_full(cards):
    for c in REAL:
        cov = coverage.of_card_data(cards.resolve(c["name"]))
        assert cov.level == "FULL", (c["name"], cov.manual_parts)


def test_mnemonic_deluge_casts_each_copy_individually_and_the_copies_cease_to_exist(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    deluge = put(s, "Mnemonic Deluge", "hand")
    mana(s, U=9)
    act(s, "p1", type="cast_spell", card_id=deluge.id, targets=[bolt.id])
    pass_until_stack_empty(s)
    assert step(s) == "free_cast_pick"
    assert s.state.cards[bolt.id].zone == "p1:exile"
    copies = [c for c in s.state.cards.values() if c.is_token and c.copy_of is not None and c.zone == "p1:exile"]
    assert len(copies) == 3 and {c.name for c in copies} == {"Lightning Bolt"}  # 707.12: made in the card's zone
    first = copies[0]
    choose(s, [first.id])
    choose(s, ["p2"])  # Bolt's target
    assert s.state.cards[first.id].zone == "stack" and step(s) == "free_cast_pick"  # 707.12: a spell on the stack, the next copy next
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {c.id for c in copies[1:]}
    choose(s, [])  # 707.12a: the second copy isn't cast
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37
    assert not [c for c in s.state.cards.values() if c.is_token and c.copy_of is not None]  # 704.5e: none left anywhere
    assert s.state.cards[deluge.id].zone == "p1:exile"
    assert s.state.cards[bolt.id].zone == "p1:exile"
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def test_shiko_copy_of_a_permanent_spell_becomes_a_token(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    shiko = put(s, "Shiko, Paragon of the Way", "hand")
    mana(s, U=1, R=1, W=1, G=2)
    act(s, "p1", type="cast_spell", card_id=shiko.id)
    pass_until_stack_empty(s)
    if step(s) not in ("free_cast_pick", None):
        choose(s, [bears.id])
        pass_until_stack_empty(s)
    assert step(s) == "free_cast_pick"
    copy = next(c for c in s.state.cards.values() if c.is_token and c.copy_of is not None)
    assert s.state.cards[bears.id].zone == "p1:exile" and copy.zone == "p1:exile"
    choose(s, [copy.id])
    pass_until_stack_empty(s)
    made = s.state.cards[copy.id]
    assert made.zone == "p1:battlefield" and made.is_token and made.name == "Grizzly Bears"  # 608.3f
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def test_a_copy_not_cast_ceases_to_exist(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    deluge = put(s, "Mnemonic Deluge", "hand")
    mana(s, U=9)
    act(s, "p1", type="cast_spell", card_id=deluge.id, targets=[bolt.id])
    pass_until_stack_empty(s)
    choose(s, [])
    pass_until_stack_empty(s)
    assert not [c for c in s.state.cards.values() if c.copy_of is not None]
    assert s.state.players["p2"].life == 40
    replay_matches(s)


FIRST_YEAR = "Studious First-Year // Rampant Growth"
PRODIGY = "Woodwork Prodigy // Soul Tether"


def name_of(s, card):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(card).name


def copy_in_exile(s):
    return next(c for c in s.state.cards.values() if c.is_token and c.copy_of is not None and c.zone == "p1:exile")


def test_prepared_enters_prepared_then_cast_the_copy_and_it_unprepares(cards):
    s = build(cards)
    first = put(s, FIRST_YEAR, "hand")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=first.id)
    pass_until_stack_empty(s)
    assert s.state.cards[first.id].zone == "p1:battlefield" and len(s.state.rules.prepared) == 1  # 722.3a
    copy = copy_in_exile(s)
    assert name_of(s, copy) == "Rampant Growth" and copy.face == 1  # 722.3c: the prepare spell's characteristics only
    assert name_of(s, s.state.cards[first.id]) == "Studious First-Year"  # 722.4 / 722.2c: the card itself is unchanged
    forests = sum(1 for c in s.state.cards.values() if c.owner == "p1" and c.zone == "p1:battlefield" and c.name == "Forest")
    act(s, "p1", type="cast_spell", card_id=copy.id)  # sorcery speed, for {1}{G}
    assert s.state.cards[copy.id].zone == "stack"
    assert s.state.rules.prepared == {}  # 722.3c / 601.2i: no longer prepared once the copy is cast
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    if d is not None:
        choose(s, [d.options[0].id])
    pass_until_stack_empty(s)
    assert sum(1 for c in s.state.cards.values() if c.owner == "p1" and c.zone == "p1:battlefield" and c.name == "Forest") == forests + 1
    assert copy.id not in s.state.cards  # 704.5e: the resolved copy is gone
    assert s.state.cards[first.id].zone == "p1:battlefield"
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def test_prepared_copy_ceases_to_exist_when_the_permanent_leaves(cards):
    s = build(cards)
    first = put(s, FIRST_YEAR, "hand")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=first.id)
    pass_until_stack_empty(s)
    copy = copy_in_exile(s)
    put(s, FIRST_YEAR, "graveyard")
    act(s, "p1", type="pass_priority")  # state-based actions
    assert copy.id not in s.state.cards  # 722.3c: it remained only while the permanent stayed prepared on the battlefield
    assert name_of(s, s.state.cards[first.id]) == "Studious First-Year"
    replay_matches(s)


def test_woodwork_prodigy_becomes_prepared_at_upkeep_only_if_it_isnt(cards):
    s = build(cards)
    prodigy = put(s, PRODIGY, "battlefield")
    assert s.state.rules.prepared == {}
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert len(s.state.rules.prepared) == 1 and name_of(s, copy_in_exile(s)) == "Soul Tether"  # 722.3a, 722.3c
    run_until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1")
    assert len(s.state.rules.prepared) == 1 and s.state.cards[prodigy.id].zone == "p1:battlefield"  # still prepared: nothing happens
    assert sum(1 for c in s.state.cards.values() if c.is_token and c.copy_of is not None) == 1
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


# -- review (casting) -- 722.2b: a copy of a preparation card has its prepare spell among its copiable values (the CR's
# Croaking Counterpart example); 722.3c: a prepared permanent that phases in gets its exiled copy anew
def test_a_token_copy_of_a_prepare_creature_becomes_prepared_with_the_copied_cards_spell(cards):
    s = build(cards)
    prodigy = put(s, PRODIGY, "battlefield")
    counterpart = put(s, "Cackling Counterpart", "hand")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=counterpart.id, targets=[prodigy.id])
    pass_until_stack_empty(s)
    tok = next(c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield")
    assert name_of(s, tok) == "Woodwork Prodigy"
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert len(s.state.rules.prepared) == 2  # 722.3a: the card and its token copy each became prepared
    copies = [c for c in s.state.cards.values() if c.is_token and c.copy_of is not None and c.zone == "p1:exile"]
    assert len(copies) == 2 and {name_of(s, c) for c in copies} == {"Soul Tether"}  # 722.3c: the prepare spell's characteristics
    toks = s.state.rules.prepared[s.state.rules.object_id(tok.id)]
    assert s.state.cards[toks].card_id == prodigy.card_id  # 722.2b: the copied card's prepare spell
    mana(s, R=3)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=toks)
    assert len(s.state.rules.prepared) == 1 and s.state.rules.object_id(tok.id) not in s.state.rules.prepared  # 601.2i
    pass_until_stack_empty(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and toks not in s.state.cards  # Soul Tether resolved: 704.5e
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def test_a_prepared_permanent_that_phases_out_loses_its_copy_and_gets_one_as_it_phases_in(cards):
    from tests.test_rules_effects import token

    s = build(cards)
    first = put(s, FIRST_YEAR, "hand")
    stack = token(s, "p1", "Haystack", "1/1", "{2}, {T}: Target creature you control phases out. (Treat it and anything attached "
                  "to it as though they don't exist until your next turn.)")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # (Haystack untapped, no summoning sickness)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=first.id)
    pass_until_stack_empty(s)
    oid = s.state.rules.object_id(first.id)
    copy = copy_in_exile(s)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=stack.id, ability=0, targets=[first.id])
    pass_until_stack_empty(s)
    assert s.state.cards[first.id].zone == "p1:phased" and copy.id not in s.state.cards  # 702.26b: the copy can't stay (722.3c)
    assert s.state.rules.prepared == {oid: copy.id}  # 702.26d: the same object, still with the designation
    replay_matches(s)
    run_until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1")  # past her untap step: it phased in
    assert s.state.cards[first.id].zone == "p1:battlefield" and s.state.rules.object_id(first.id) == oid
    again = copy_in_exile(s)
    assert again.id != copy.id and name_of(s, again) == "Rampant Growth" and s.state.rules.prepared == {oid: again.id}  # 722.3c
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=again.id)
    assert s.state.cards[again.id].zone == "stack" and s.state.rules.prepared == {}
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))
