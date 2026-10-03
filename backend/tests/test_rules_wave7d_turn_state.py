"""Wave 7D: "this turn" state, second pass, researched against CR 2026-09-25.

* Turn watches (603.7, 603.7b, 611.2a, 514.2; app/rules/watches.py): "Whenever [event] this turn, …" (Glimpse of Nature,
  Rite of Harmony, Thunder of Unity, Vizkopa Guildmage, Massacre Girl) and "When you next cast [spell] this turn, copy that
  spell" (Galvanic Iteration, Teach by Example, Storm King's Thunder): a delayed triggered ability on an ordinary event,
  created as the spell or ability resolves (603.7a), for events after that, until cleanup.

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle, through_combat, until
from tests.test_rules_effects import replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Glimpse of Nature', set_code='tst', number='D01', mana_cost='{G}', cmc=1.0, type_line='Sorcery', oracle_text='Whenever you cast a creature spell this turn, draw a card.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Galvanic Iteration', set_code='tst', number='D02', mana_cost='{U}{R}', cmc=2.0, type_line='Instant', oracle_text='When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.\nFlashback {1}{U}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Flashback']),  # noqa: E501
    card('Vizkopa Guildmage', set_code='tst', number='D03', mana_cost='{W}{B}', cmc=2.0, type_line='Creature — Human Wizard', oracle_text='{1}{W}{B}: Target creature gains lifelink until end of turn.\n{1}{W}{B}: Whenever you gain life this turn, each opponent loses that much life.', power='2', toughness='2', colors=['B', 'W'], color_identity=['B', 'W'], keywords=[]),  # noqa: E501
    card('Revitalize', set_code='tst', number='D04', mana_cost='{1}{W}', cmc=2.0, type_line='Instant', oracle_text='You gain 3 life.\nDraw a card.', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Runeclaw Bear', set_code='tst', number='D05', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Rite of Harmony', set_code='tst', number='D06', mana_cost='{G}{W}', cmc=2.0, type_line='Instant', oracle_text='Whenever a creature or enchantment you control enters this turn, draw a card.\nFlashback {2}{G}{W} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Flashback']),  # noqa: E501
    card("Storm King's Thunder", set_code='tst', number='D07', mana_cost='{X}{R}{R}{R}', cmc=3.0, type_line='Instant', oracle_text='When you next cast an instant or sorcery spell this turn, copy that spell X times. You may choose new targets for the copies.', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Massacre Girl', set_code='tst', number='D08', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Legendary Creature — Human Assassin', oracle_text='Menace\nWhen Massacre Girl enters, each other creature gets -1/-1 until end of turn. Whenever a creature dies this turn, each creature other than Massacre Girl gets -1/-1 until end of turn.', power='4', toughness='4', colors=['B'], color_identity=['B'], keywords=['Menace']),  # noqa: E501
    card('Noxious Assault', set_code='tst', number='D09', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Sorcery', oracle_text='Creatures you control get +2/+2 until end of turn. Whenever a creature blocks this turn, its controller gets a poison counter.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Ambush Viper', set_code='tst', number='D11', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Snake', oracle_text='Flash\nDeathtouch', power='2', toughness='1', colors=['G'], color_identity=['G'], keywords=['Flash', 'Deathtouch']),  # noqa: E501
    card('Theoretical Duplication', set_code='tst', number='D10', mana_cost='{2}{U}', cmc=3.0, type_line='Instant', oracle_text="Whenever a nontoken creature an opponent controls enters this turn, create a token that's a copy of that creature.", colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
]
FULL = ["Noxious Assault", "Theoretical Duplication", "Glimpse of Nature", "Galvanic Iteration", "Vizkopa Guildmage", "Rite of Harmony", "Storm King's Thunder",
        "Massacre Girl"]
STILL_MANUAL: dict[str, str] = {}


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def build(cards, *names, forests=9):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (forests, "Forest")])
    seats = [PlayerSetup("Alice", cards=alice),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(1, "Ambush Viper"), (10, "Island")]))]
    state = enable(new_game(seats, shuffle=False))
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def card_named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_hand(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def put(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s)


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def watches(s):
    return [t for t in s.state.rules.delayed if t.when.get("kind") == "watch"]


# -- coverage ----------------------------------------------------------------------------------------------------
def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


# -- turn watches ------------------------------------------------------------------------------------------------
def test_glimpse_of_nature_draws_for_each_creature_spell_this_turn_only(cards):
    """603.7: each creature spell cast after Glimpse resolved triggers it, until cleanup (514.2); a noncreature spell
    and a creature spell cast the turn after don't."""
    s = build(cards, "Glimpse of Nature", "Runeclaw Bear", "Revitalize")
    for n in ("Glimpse of Nature", "Runeclaw Bear", "Revitalize"):
        to_hand(s, n)
    mana(s, G=1)
    cast(s, "Glimpse of Nature")
    assert len(watches(s)) == 1 and watches(s)[0].once is False
    before = hand(s)
    mana(s, W=1, G=1)
    cast(s, "Revitalize")  # (a noncreature spell: its own draw, no watch draw)
    assert hand(s) == before - 1 + 1
    mana(s, G=1, R=1)
    cast(s, "Runeclaw Bear")
    assert hand(s) == before - 1 + 1 - 1 + 1  # (the Bear left the hand, Glimpse drew one)
    assert len(watches(s)) == 1  # (it keeps watching: "whenever")
    replay_matches(s)
    s = reloaded(s)
    assert len(watches(s)) == 1
    until(s, lambda s: s.state.turn.number == 2)
    assert watches(s) == []  # (514.2)
    replay_matches(s)


def test_the_watch_ignores_what_happened_before_it_existed(cards):
    """603.7a: a creature spell cast before Glimpse resolves never triggers it."""
    s = build(cards, "Glimpse of Nature", "Runeclaw Bear")
    to_hand(s, "Glimpse of Nature")
    to_hand(s, "Runeclaw Bear")
    mana(s, G=3, R=1)
    cast(s, "Runeclaw Bear")
    before = hand(s)
    cast(s, "Glimpse of Nature")
    assert hand(s) == before - 1  # (just the Glimpse leaving the hand)


def test_galvanic_iteration_copies_only_the_next_instant_or_sorcery(cards):
    """603.7b: it triggers once, for the first instant or sorcery spell cast after it resolves (a creature spell is
    neither); the copy is put on the stack, not cast (707.10), so it doesn't trigger it again."""
    s = build(cards, "Galvanic Iteration", "Lightning Bolt", "Runeclaw Bear")
    for n in ("Galvanic Iteration", "Lightning Bolt", "Runeclaw Bear"):
        to_hand(s, n)
    mana(s, U=1, R=1)
    cast(s, "Galvanic Iteration")
    assert len(watches(s)) == 1 and watches(s)[0].once is True
    mana(s, G=1, R=1)
    cast(s, "Runeclaw Bear")
    assert len(watches(s)) == 1  # (not an instant or sorcery)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"], target_counts=[1])
    settle(s)
    assert s.state.players["p2"].life == 40 - 6  # (the Bolt and its copy)
    assert watches(s) == []
    replay_matches(s)
    replay_matches(reloaded(s))


def test_a_next_cast_watch_can_wait_for_a_later_spell_the_same_turn(cards):
    s = build(cards, "Galvanic Iteration", "Lightning Bolt", "Revitalize")
    for n in ("Galvanic Iteration", "Lightning Bolt", "Revitalize"):
        to_hand(s, n)
    mana(s, U=1, R=1)
    cast(s, "Galvanic Iteration")
    mana(s, W=1, R=2, G=1)
    cast(s, "Revitalize")  # (an instant: copied, "You gain 3 life" twice)
    assert s.state.players["p1"].life == 40 + 6
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"], target_counts=[1])
    settle(s)
    assert s.state.players["p2"].life == 40 - 3  # (the watch was used up)
    replay_matches(s)


def test_vizkopa_guildmage_drains_for_each_life_gain_this_turn(cards):
    """"Whenever you gain life this turn, each opponent loses that much life": the amount of the life gained."""
    s = build(cards, "Vizkopa Guildmage", "Revitalize")
    put(s, "Vizkopa Guildmage")
    to_hand(s, "Revitalize")
    mana(s, W=2, B=1, G=2)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Vizkopa Guildmage").id, ability=1)
    settle(s)
    assert len(watches(s)) == 1
    cast(s, "Revitalize")
    assert s.state.players["p1"].life == 43 and s.state.players["p2"].life == 37
    replay_matches(s)
    replay_matches(reloaded(s))


def test_rite_of_harmony_draws_for_a_creature_entering_under_your_control_only(cards):
    s = build(cards, "Rite of Harmony", "Runeclaw Bear")
    to_hand(s, "Rite of Harmony")
    to_hand(s, "Runeclaw Bear")
    mana(s, G=2, W=1)
    cast(s, "Rite of Harmony")
    before = hand(s)
    put(s, "Runeclaw Bear")  # (put onto the battlefield by hand: no trigger, 603.2 — only the engine's own events)
    act(s, "p2", type="create_token", player="p2",
        token={"name": "Imp", "type_line": "Token Creature — Imp", "power": "1", "toughness": "1", "text": ""})
    settle(s)
    assert hand(s) == before - 1  # (an opponent's creature doesn't trigger it)


def test_storm_kings_thunder_copies_the_next_spell_x_times(cards):
    """107.3: the X it was cast with is fixed when the delayed trigger is created."""
    s = build(cards, "Storm King's Thunder", "Lightning Bolt")
    to_hand(s, "Storm King's Thunder")
    to_hand(s, "Lightning Bolt")
    mana(s, R=7)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Storm King's Thunder").id, x_value=2)
    settle(s)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"], target_counts=[1])
    settle(s)
    assert s.state.players["p2"].life == 40 - 9  # (the Bolt and two copies)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_noxious_assault_poisons_the_controller_of_each_blocker(cards):
    """Whenever a creature blocks this turn, its controller (the event's creature's: 603.10) gets a poison counter."""
    s = build(cards, "Noxious Assault")
    bear = token(s, "p1", "Bear", "2/2", "Haste")
    wall = token(s, "p2", "Wall", "0/4")
    to_hand(s, "Noxious Assault")
    mana(s, G=5)
    cast(s, "Noxious Assault")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": bear.id}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert s.state.players["p2"].resources.get("poison") == 1 and not s.state.players["p1"].resources.get("poison")
    through_combat(s)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_theoretical_duplication_copies_only_nontoken_creatures_opponents_control(cards):
    s = build(cards, "Theoretical Duplication", "Runeclaw Bear")
    to_hand(s, "Theoretical Duplication")
    mana(s, U=3)
    cast(s, "Theoretical Duplication")
    bear = card_named(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "hand"})
    settle(s)
    assert [c.name for c in s.state.cards.values() if c.is_token] == []  # (a creature of mine: no copy)
    replay_matches(s)


def test_theoretical_duplication_copies_a_nontoken_creature_an_opponent_casts(cards):
    s = build(cards, "Theoretical Duplication", "Revitalize")
    to_hand(s, "Theoretical Duplication")
    to_hand(s, "Revitalize")
    mana(s, "p1", U=3, W=2)
    cast(s, "Theoretical Duplication")
    act(s, "p2", type="set_stops", others=["main1"], smart_pass=False)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Revitalize").id)  # (Bob responds with his flash creature)
    viper = card_named(s, "Ambush Viper", "p2")
    act(s, "p2", type="move", card_ids=[viper.id], to={"zone": "hand"})
    mana(s, "p2", G=2)
    act(s, "p2", type="cast_spell", card_id=viper.id)
    settle(s)
    vipers = [c for c in s.state.cards.values() if c.name == "Ambush Viper" and c.zone.endswith(":battlefield")]
    assert sorted(c.is_token for c in vipers) == [False, True]
    assert all(c.controller == "p1" for c in vipers if c.is_token)  # (the token is Alice's: she controls the watch)
    replay_matches(s)
    replay_matches(reloaded(s))
