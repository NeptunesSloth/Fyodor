"""Review of wave 22E (event history & batched triggers): regression tests for what the review fixed. Real Oracle text,
replay and a save and a load.

* 508.1 / 603.2c: "Whenever you attack with one or more Zombies, draw that many cards" - "that many" / "those creatures" are the
  attackers the condition counted (the Zombies), not every attacking creature.
* 603.2: "for the first time each turn" still reads a mark a save from before wave 22E kept ("targeted:<player>:<object>").
"""

from __future__ import annotations

from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave5j_token_copies import drive
from tests.test_rules_wave22e_history import EXTRA, burst_at, settle_stack, table
from tests.test_rules_wave22e_history import card_db as card_db  # noqa: F401  (the 22E card database)
from tests.wave9c_kit import build, card_named, check, life, zone_of
from tests.wave9c_kit import put as kit_put

EXTRA.append(card("Varina, Lich Queen", set_code="t22e", number="E80", mana_cost="{1}{W}{U}{B}", cmc=4.0,
                  type_line="Legendary Creature — Zombie Wizard", colors=["B", "U", "W"], color_identity=["B", "U", "W"],
                  oracle_text="Whenever you attack with one or more Zombies, draw that many cards, then discard that many cards. "
                              "You gain that much life.\n{2}, Exile two cards from your graveyard: Create a tapped 2/2 black Zombie "
                              "creature token.", power="4", toughness="4"))


def test_that_many_counts_only_the_zombies_varina(cards):
    s = build(cards, ["Varina, Lich Queen", "Probe Soldier", "Probe Soldier"], [])
    attackers = [kit_put(s, "Varina, Lich Queen")] + [c for c in s.state.cards.values() if c.name == "Probe Soldier" and c.owner == "p1"]
    for c in attackers[1:]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    for c in attackers:
        s.state.rules.controlled_since[c.id].turn = 0
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="pass_priority")
    assert s.state.rules.decision.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    drive(s, lambda d: [o.id for o in d.options][:1] or None)
    assert life(s, "p1") == 40 + 1  # one Zombie attacked (Varina), not three creatures
    assert len(s.state.zones["p1:hand"]) == hand and len(s.state.zones["p1:graveyard"]) == 1
    check(s)


def test_first_time_each_turn_reads_an_older_saves_mark_glyph_keeper(cards):
    s = table(cards, ["Glyph Keeper"])
    keeper = card_named(s, "Glyph Keeper")
    # (a save from before wave 22E: Alice's spell already targeted it this turn, kept as "targeted:p1:<object>")
    s.state.rules.once_per_turn[f"targeted:p1:{s.state.rules.object_id(keeper.id)}"] = s.state.turn.number
    burst_at(s, "p2", "p1")
    burst_at(s, keeper.id, "p2")  # Bob's answer: not the first time it became a target this turn, so it resolves
    settle_stack(s)
    assert s.state.cards[keeper.id].damage == 1 and life(s, "p2") == 40 - 1 and zone_of(s, "Glyph Keeper") == "p1:battlefield"
    check(s)


def test_a_static_on_goaded_creatures_stays_manual_bothersome_quasit():
    """613.8a: "Goaded creatures your opponents control can't block" depends on the goad (both layer 6); by timestamp alone it
    misses a creature goaded after it (found blocking in a probe), so the static is refused."""
    from app.rules import coverage

    quasit = card("Bothersome Quasit", set_code="t22e", number="E81", mana_cost="{2}{R}", cmc=3.0, type_line="Creature — Demon",
                  colors=["R"], color_identity=["R"], keywords=["Goad", "Menace"], power="3", toughness="2",
                  oracle_text="Menace\nGoaded creatures your opponents control can't block.\nWhenever you cast a noncreature spell, goad "
                              "target creature an opponent controls. (Until your next turn, that creature attacks each combat if able "
                              "and attacks a player other than you if able.)")
    assert coverage.of_card_data({**quasit, "faces": []}).level != "FULL"
