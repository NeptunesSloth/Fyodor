"""Wave 6D: trigger conditions and bodies from the trigger catch-all.

* "That creature" in "Whenever ~ blocks / becomes blocked by a creature" (509.3b / 509.3d: once for each creature on
  the other side) and "Whenever ~ deals [combat] damage to a creature" (120.1): the creature on the other side, carried
  by the trigger event (app/rules/other_side.py). A bare "it" before it is the source: manual.
* "… at end of combat" / "At end of combat, …": a delayed trigger (603.7) as the next end of combat step begins (511.2).
* "Defending player" in an attacking creature's trigger (508.5, 508.5a: app/rules/defending.py), captured as it triggers.
* "a historic spell" (700.6), "attach ~ to it / that creature" (701.3), "tap or untap target permanent" (701.26a).

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import named
from tests.test_rules_conditionals import answer_may, settle, until, until_asked
from tests.test_rules_wave4h_activation_costs import roundtrip
from tests.test_rules_wave5c_combat import build, declare, old, put, to_attack

EXTRA = [
    card('Gorgon Recluse', set_code="tst", number="D01", mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Gorgon', oracle_text='Whenever this creature blocks or becomes blocked by a nonblack creature, destroy that creature at end of combat.\nMadness {B}{B} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.)', power='2', toughness='4', colors=['B'], color_identity=['B'], keywords=['Madness']),  # noqa: E501
    card('Engulfing Slagwurm', set_code="tst", number="D02", mana_cost='{5}{G}{G}', cmc=7.0, type_line='Creature — Wurm', oracle_text="Whenever this creature blocks or becomes blocked by a creature, destroy that creature. You gain life equal to that creature's toughness.", power='7', toughness='7', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Ohran Viper', set_code="tst", number="D03", mana_cost='{1}{G}{G}', cmc=3.0, type_line='Snow Creature — Snake', oracle_text='Whenever this creature deals combat damage to a creature, destroy that creature at end of combat.\nWhenever this creature deals combat damage to a player, you may draw a card.', power='1', toughness='3', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Kashi-Tribe Reaver', set_code="tst", number="D04", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Snake Warrior', oracle_text="Whenever this creature deals combat damage to a creature, tap that creature and it doesn't untap during its controller's next untap step.\n{1}{G}: Regenerate this creature.", power='3', toughness='2', colors=['G'], color_identity=['G'], keywords=['Regenerate']),  # noqa: E501
    card('Wall of Junk', set_code="tst", number="D05", mana_cost='{2}', cmc=2.0, type_line='Artifact Creature — Wall', oracle_text="Defender (This creature can't attack.)\nWhen this creature blocks, return it to its owner's hand at end of combat. (Return it only if it's on the battlefield.)", power='0', toughness='7', keywords=['Defender']),  # noqa: E501
    card('Acolyte of the Inferno', set_code="tst", number="D06", mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Human Monk', oracle_text="Renown 1 (When this creature deals combat damage to a player, if it isn't renowned, put a +1/+1 counter on it and it becomes renowned.)\nWhenever this creature becomes blocked by a creature, it deals 2 damage to that creature.", power='3', toughness='1', colors=['R'], color_identity=['R'], keywords=['Renown']),  # noqa: E501
    card('Shrieking Specter', set_code="tst", number="D07", mana_cost='{5}{B}', cmc=6.0, type_line='Creature — Specter', oracle_text='Flying\nWhenever this creature attacks, defending player discards a card.', power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=['Flying']),  # noqa: E501
    card('Thraximundar', set_code="tst", number="D08", mana_cost='{4}{U}{B}{R}', cmc=7.0, type_line='Legendary Creature — Zombie Assassin', oracle_text='Haste\nWhenever Thraximundar attacks, defending player sacrifices a creature of their choice.\nWhenever a player sacrifices a creature, you may put a +1/+1 counter on Thraximundar.', power='6', toughness='6', colors=['B', 'R', 'U'], color_identity=['B', 'R', 'U'], keywords=['Haste']),  # noqa: E501
    card('Brutal Hordechief', set_code="tst", number="D09", mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Orc Warrior', oracle_text='Whenever a creature you control attacks, defending player loses 1 life and you gain 1 life.\n{3}{R/W}{R/W}: Creatures your opponents control block this turn if able, and you choose how those creatures block.', power='3', toughness='3', colors=['B'], color_identity=['B', 'R', 'W']),  # noqa: E501
    card('Slate Street Ruffian', set_code="tst", number="D10", mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Human Warrior', oracle_text='Whenever this creature becomes blocked, defending player discards a card.', power='2', toughness='2', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Jhoira, Weatherlight Captain', set_code="tst", number="D11", mana_cost='{2}{U}{R}', cmc=4.0, type_line='Legendary Creature — Human Artificer', oracle_text='Whenever you cast a historic spell, draw a card. (Artifacts, legendaries, and Sagas are historic.)', power='3', toughness='3', colors=['R', 'U'], color_identity=['R', 'U']),  # noqa: E501
    card("Hero's Blade", set_code="tst", number="D12", mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +3/+2.\nWhenever a legendary creature you control enters, you may attach this Equipment to it.\nEquip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)', keywords=['Equip']),  # noqa: E501
    card('Ancestral Blade', set_code="tst", number="D13", mana_cost='{1}{W}', cmc=2.0, type_line='Artifact — Equipment', oracle_text='When this Equipment enters, create a 1/1 white Soldier creature token, then attach this Equipment to it.\nEquipped creature gets +1/+1.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)', colors=['W'], color_identity=['W'], keywords=['Equip']),  # noqa: E501
    card('Pestermite', set_code="tst", number="D14", mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Faerie Rogue', oracle_text='Flash\nFlying\nWhen this creature enters, you may tap or untap target permanent.', power='2', toughness='1', colors=['U'], color_identity=['U'], keywords=['Flying', 'Flash']),  # noqa: E501
]
FULL = ["Gorgon Recluse", "Engulfing Slagwurm", "Ohran Viper", "Kashi-Tribe Reaver", "Wall of Junk", "Shrieking Specter",
        "Thraximundar", "Slate Street Ruffian", "Jhoira, Weatherlight Captain", "Hero's Blade", "Ancestral Blade",
        "Pestermite"]
STILL_MANUAL = {
    "Acolyte of the Inferno": "it deals 2 damage to that creature",  # ("it" before "that creature": the source)
    "Brutal Hordechief": "Creatures your opponents control block this turn if able",  # (its trigger is read)
}


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", coverage.of_card_data(cards.resolve(name)).manual_parts


@pytest.mark.parametrize("name", list(STILL_MANUAL))
def test_still_manual(cards, name):
    cov = coverage.of_card_data(cards.resolve(name))
    assert any(not f.supported and STILL_MANUAL[name] in f.label for f in cov.features)


def defined(text, type_line="Creature — Test"):
    from tests.test_rules_scripts import ch

    return scripts.definitions(ch("X", type_line, text))


@pytest.mark.parametrize("text", [
    "Whenever you cast a spell, defending player loses 1 life.",  # not an attacking creature's ability (508.5)
    "Whenever one or more creatures you control attack, defending player loses 1 life.",  # several (508.5a)
    "{T}: Defending player loses 1 life.",
    "Whenever this creature blocks, defending player loses 1 life.",  # a blocker has no defending player of its own
    "Whenever this creature attacks or blocks, defending player loses 1 life.",
    "Whenever this creature becomes blocked by a creature, it deals 2 damage to that creature.",
])
def test_wordings_that_stay_manual(text):
    assert not defined(text), text


def test_end_of_combat_wording():
    assert scripts.parse_effects("Destroy that creature at end of combat.", it="event") == (
        [{"do": "delayed", "when": {"kind": "step", "step": "end_combat", "whose": "next"}, "n": 1},
         {"do": "deferred:destroy", "who": "event"}], None, False)
    assert scripts.parse_effects("At end of combat, sacrifice it.", it="self")[0][0]["when"]["step"] == "end_combat"


def bob_attacks_into(s, blocker, attacker_pt="3/3"):
    """Bob's hasty creature attacks Alice on turn 2; Alice blocks it with ``blocker``. Returns the attacker."""
    raider = old(s, "p2", "Raider", attacker_pt)
    stops(s)
    to_attack(s, 2)
    declare(s, (raider, "p1"), pid="p2")
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_blockers" and d.player == "p1"
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": raider.id}])
    return raider


def stops(s):
    """Both players stop in the combat damage step (to look at the table before the end of combat step)."""
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=["main1", "combat_damage", "main2"], others=["combat_damage"])


def gone(s, c, pid):
    return c.id not in s.state.cards or s.state.cards[c.id].zone != f"{pid}:battlefield"


def zone_of(s, c):
    return s.state.cards[c.id].zone


# -- the creature on the other side ---------------------------------------------------------------------------------
def test_gorgon_recluse_destroys_the_blocked_creature_at_end_of_combat(cards):
    s = build(cards, "Gorgon Recluse")
    gorgon = put(s, "Gorgon Recluse")
    raider = bob_attacks_into(s, gorgon)
    until(s, lambda s: s.state.turn.phase == "combat_damage" and not s.state.zones.get("stack"))
    # (the trigger resolved: a delayed trigger waits for end of combat; 3 toughness, 2 damage: alive so far)
    assert zone_of(s, raider) == "p2:battlefield" and len(s.state.rules.delayed) == 1
    roundtrip(s)
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack"))
    assert gone(s, raider, "p2")
    assert zone_of(s, gorgon) == "p1:battlefield" and not s.state.rules.delayed
    roundtrip(s)


def test_engulfing_slagwurm_destroys_the_attacker_and_gains_its_toughness(cards):
    s = build(cards, "Engulfing Slagwurm")
    wurm = put(s, "Engulfing Slagwurm")
    life = s.state.players["p1"].life
    raider = bob_attacks_into(s, wurm, "2/5")
    until(s, lambda s: s.state.turn.phase == "combat_damage" and not s.state.zones.get("stack"))
    assert gone(s, raider, "p2")
    assert s.state.players["p1"].life == life + 5  # (its toughness as it last existed, 608.2h)
    roundtrip(s)


def test_ohran_viper_destroys_the_creature_it_dealt_combat_damage_to(cards):
    s = build(cards, "Ohran Viper")
    viper = put(s, "Ohran Viper")
    wall = named(s, "Wall p2")  # (0/4: survives the 1 damage)
    stops(s)
    to_attack(s, 3)
    declare(s, (viper, "p2"))
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": viper.id}])
    until(s, lambda s: s.state.turn.phase == "combat_damage" and not s.state.zones.get("stack"))
    assert zone_of(s, wall) == "p2:battlefield" and s.state.rules.delayed
    roundtrip(s)
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack"))
    assert gone(s, wall, "p2")
    assert zone_of(s, viper) == "p1:battlefield"
    roundtrip(s)


def test_kashi_tribe_reaver_taps_the_creature_and_keeps_it_tapped(cards):
    s = build(cards, "Kashi-Tribe Reaver")
    reaver = put(s, "Kashi-Tribe Reaver")
    wall = named(s, "Wall p2")
    to_attack(s, 3)
    declare(s, (reaver, "p2"))
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": reaver.id}])
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack"))
    assert s.state.cards[wall.id].tapped
    roundtrip(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")
    assert s.state.cards[wall.id].tapped  # (Bob's next untap step: it stayed tapped, 502.3)


def test_wall_of_junk_returns_to_hand_at_end_of_combat(cards):
    s = build(cards, "Wall of Junk")
    wall = put(s, "Wall of Junk")
    bob_attacks_into(s, wall)
    until(s, lambda s: s.state.turn.phase == "combat_damage" and not s.state.zones.get("stack"))
    assert zone_of(s, wall) == "p1:battlefield"
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack"))
    assert zone_of(s, wall) == "p1:hand"
    roundtrip(s)


# -- defending player -----------------------------------------------------------------------------------------------
def hand_size(s, pid):
    return len(s.state.zones.get(f"{pid}:hand", []))


def test_shrieking_specter_makes_the_player_it_attacks_discard(cards):
    s = build(cards, "Shrieking Specter")
    specter = put(s, "Shrieking Specter")
    to_attack(s, 3)
    before = hand_size(s, "p2")
    declare(s, (specter, "p2"))
    d = until_asked(s)
    while d is not None and d.kind != "declare_blockers":
        assert d.player == "p2"  # Bob chooses the card he discards (701.9a)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        d = until_asked(s)
    assert hand_size(s, "p2") == before - 1
    roundtrip(s)


def test_thraximundar_the_attacked_player_sacrifices_in_multiplayer(cards):
    s = build(cards, "Thraximundar", players=3)
    thrax = put(s, "Thraximundar")
    bobs, carols = named(s, "Wall p2"), named(s, "Wall p3")
    to_attack(s, 4)
    declare(s, (thrax, "p3"))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers"
          or carols.id not in s.state.cards or s.state.cards[carols.id].zone != "p3:battlefield")
    assert zone_of(s, bobs) == "p2:battlefield"  # (Bob isn't the defending player for it: 508.5a)
    assert carols.id not in s.state.cards or zone_of(s, carols) != "p3:battlefield"
    roundtrip(s)


def test_brutal_hordechief_drains_each_attacked_player(cards):
    s = build(cards, "Brutal Hordechief", players=3)
    put(s, "Brutal Hordechief")
    a, b = old(s, "p1", "A"), old(s, "p1", "B")
    to_attack(s, 1)
    lives = {p: s.state.players[p].life for p in ("p1", "p2", "p3")}
    declare(s, (a, "p2"), (b, "p3"))
    until(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_blockers")  # (the triggers resolved, before any damage)
    assert s.state.players["p2"].life == lives["p2"] - 1 and s.state.players["p3"].life == lives["p3"] - 1
    assert s.state.players["p1"].life == lives["p1"] + 2
    roundtrip(s)


def test_the_defending_player_is_captured_as_it_triggers(cards):
    """508.5: the player it was attacking, even after it left combat — the event keeps it."""
    s = build(cards, "Shrieking Specter")
    specter = put(s, "Shrieking Specter")
    to_attack(s, 3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], others=[], smart_pass=False)
    act(s, "p2", type="set_stops", own=[], others=["declare_attackers"], smart_pass=False)
    declare(s, (specter, "p2"))
    (entry,) = s.state.rules.stack.values()
    assert entry.event is not None and entry.event.defended == "p2"
    roundtrip(s)
    # the Specter leaves before its trigger resolves: Bob is still the player it was attacking (508.5)
    act(s, "p1", type="move", card_ids=[specter.id], to={"zone": "hand"})
    before = hand_size(s, "p2")
    until(s, lambda s: not s.state.zones.get("stack"))
    assert hand_size(s, "p2") == before - 1
    roundtrip(s)


# -- historic, attach, tap or untap ---------------------------------------------------------------------------------
def test_jhoira_draws_for_a_historic_spell_only(cards):
    s = build(cards, "Jhoira, Weatherlight Captain", "Sol Ring", "Grizzly Bears")
    put(s, "Jhoira, Weatherlight Captain")
    ring, bears = named(s, "Sol Ring"), named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[ring.id, bears.id], to={"zone": "hand"})
    before = hand_size(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 3})
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert hand_size(s, "p1") == before - 1  # (a Bear isn't historic)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    settle(s)
    assert hand_size(s, "p1") == before - 1  # (Sol Ring left the hand, a card was drawn)
    roundtrip(s)


def test_heros_blade_attaches_to_a_legendary_creature_entering(cards):
    s = build(cards, "Hero's Blade", "Jhoira, Weatherlight Captain", "Grizzly Bears")
    blade = put(s, "Hero's Blade")
    bears, jhoira = named(s, "Grizzly Bears"), named(s, "Jhoira, Weatherlight Captain")
    act(s, "p1", type="move", card_ids=[bears.id, jhoira.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"G": 2, "U": 1, "R": 1, "C": 2})
    act(s, "p1", type="cast_spell", card_id=bears.id)
    answer_may(s, "yes")
    assert s.state.cards[blade.id].attached_to is None  # (not legendary: no trigger)
    act(s, "p1", type="cast_spell", card_id=jhoira.id)
    answer_may(s, "yes")
    assert s.state.cards[blade.id].attached_to == jhoira.id
    roundtrip(s)


def test_ancestral_blade_makes_a_soldier_and_equips_it(cards):
    s = build(cards, "Ancestral Blade")
    blade = named(s, "Ancestral Blade")
    act(s, "p1", type="move", card_ids=[blade.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1, "G": 1})
    act(s, "p1", type="cast_spell", card_id=blade.id)
    settle(s)
    host = s.state.cards[s.state.cards[blade.id].attached_to]
    assert host.name == "Soldier" and host.is_token
    roundtrip(s)


@pytest.mark.parametrize("choice", ["tap", "untap"])
def test_pestermite_taps_or_untaps_target_permanent(cards, choice):
    s = build(cards, "Pestermite")
    mite = named(s, "Pestermite")
    land = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[land.id], to={"player": "p2", "zone": "battlefield"})
    if choice == "untap":
        act(s, "p2", type="tap", card_ids=[land.id], tapped=True)
    act(s, "p1", type="move", card_ids=[mite.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1, "G": 2})
    act(s, "p1", type="cast_spell", card_id=mite.id)
    for _ in range(20):
        d = until_asked(s)
        if d is None:
            break
        if d.kind == "choose_targets" or any(o.id == land.id for o in d.options):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[land.id])
        elif any(o.id == choice for o in d.options):
            roundtrip(s)  # (a save in the middle of the choice)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[choice])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert s.state.cards[land.id].tapped == (choice == "tap")
    roundtrip(s)



# -- second batch: exiled with (607.2a), blocking it, graveyard owner, monstrous / renowned, state triggers (603.8) ----
EXTRA += [
    card('Oblivion Ring', set_code="tst", number="E01", mana_cost='{2}{W}', cmc=3.0, type_line='Enchantment', oracle_text="When this enchantment enters, exile another target nonland permanent.\nWhen this enchantment leaves the battlefield, return the exiled card to the battlefield under its owner's control.", colors=['W'], color_identity=['W']),  # noqa: E501
    card('Tidehollow Sculler', set_code="tst", number="E02", mana_cost='{W}{B}', cmc=2.0, type_line='Artifact Creature — Zombie', oracle_text="When this creature enters, target opponent reveals their hand and you choose a nonland card from it. Exile that card.\nWhen this creature leaves the battlefield, return the exiled card to its owner's hand.", power='2', toughness='2', colors=['B', 'W'], color_identity=['B', 'W']),  # noqa: E501
    card('Elvish Berserker', set_code="tst", number="E03", mana_cost='{G}', cmc=1.0, type_line='Creature — Elf Berserker', oracle_text='Whenever this creature becomes blocked, it gets +1/+1 until end of turn for each creature blocking it.', power='1', toughness='1', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Plague Wight', set_code="tst", number="E04", mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Zombie', oracle_text='Whenever this creature becomes blocked, each creature blocking it gets -1/-1 until end of turn.', power='2', toughness='1', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Spined Sliver', set_code="tst", number="E05", mana_cost='{R}{G}', cmc=2.0, type_line='Creature — Sliver', oracle_text='Whenever a Sliver becomes blocked, that Sliver gets +1/+1 until end of turn for each creature blocking it.', power='2', toughness='2', colors=['G', 'R'], color_identity=['G', 'R']),  # noqa: E501
    card('Field of Souls', set_code="tst", number="E07", mana_cost='{2}{W}{W}', cmc=4.0, type_line='Enchantment', oracle_text='Whenever a nontoken creature is put into your graveyard from the battlefield, create a 1/1 white Spirit creature token with flying.', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Grim Feast', set_code="tst", number="E08", mana_cost='{1}{B}{G}', cmc=3.0, type_line='Enchantment', oracle_text="At the beginning of your upkeep, this enchantment deals 1 damage to you.\nWhenever a creature is put into an opponent's graveyard from the battlefield, you gain life equal to its toughness.", colors=['B', 'G'], color_identity=['B', 'G']),  # noqa: E501
    card('Keepsake Gorgon', set_code="tst", number="E09", mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Gorgon', oracle_text="Deathtouch\n{5}{B}{B}: Monstrosity 1. (If this creature isn't monstrous, put a +1/+1 counter on it and it becomes monstrous.)\nWhen this creature becomes monstrous, destroy target non-Gorgon creature an opponent controls.", power='2', toughness='5', colors=['B'], color_identity=['B'], keywords=['Monstrosity', 'Deathtouch']),  # noqa: E501
    card('Emperor Crocodile', set_code="tst", number="E12", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Crocodile', oracle_text='When you control no other creatures, sacrifice this creature.', power='5', toughness='5', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Covetous Dragon', set_code="tst", number="E13", mana_cost='{4}{R}', cmc=5.0, type_line='Creature — Dragon', oracle_text='Flying\nWhen you control no artifacts, sacrifice this creature.', power='6', toughness='5', colors=['R'], color_identity=['R'], keywords=['Flying']),  # noqa: E501
    card('Fiend Hunter', set_code="tst", number="F01", mana_cost='{1}{W}{W}', cmc=3.0, type_line='Creature — Human Cleric', oracle_text="When this creature enters, you may exile another target creature.\nWhen this creature leaves the battlefield, return the exiled card to the battlefield under its owner's control.", power='1', toughness='3', colors=['W'], color_identity=['W']),  # noqa: E501
]
FULL += ["Oblivion Ring", "Tidehollow Sculler", "Elvish Berserker", "Plague Wight", "Field of Souls", "Grim Feast",
         "Keepsake Gorgon", "Emperor Crocodile", "Covetous Dragon", "Fiend Hunter"]
STILL_MANUAL["Spined Sliver"] = "that Sliver gets +1/+1"  # ("blocking it": it isn't the source there)


def resolve(s, *picks, limit=40):
    """Resolve the stack: a decision offering one of ``picks`` gets it, a "you may" gets yes, the rest the first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        chosen = [p for p in picks if p in ids]
        if chosen:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen[:1])
        elif d.kind == "confirm":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: max(1, d.min_choices)])
    raise AssertionError("never settled")


def cast_from_hand(s, name, pid="p1", **mana_):
    c = named(s, name)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="add_mana", player=pid, mana=mana_)
    act(s, pid, type="cast_spell", card_id=c.id)
    return c


def murder(s, victim):
    m = next(c for c in s.state.cards.values() if c.name == "Murder" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[m.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": 1})
    act(s, "p1", type="cast_spell", card_id=m.id, targets=[victim.id])


def test_fiend_hunter_returns_the_exiled_creature_when_it_leaves(cards):
    s = build(cards, "Fiend Hunter", "Murder", bob=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "p2")
    hunter = cast_from_hand(s, "Fiend Hunter", W=2, G=1)
    resolve(s, bears.id)
    assert s.state.cards[bears.id].zone.endswith("exile")
    assert s.state.rules.exiled_with  # (recorded under Fiend Hunter, 607.2a)
    roundtrip(s)
    murder(s, hunter)
    resolve(s)
    assert zone_of(s, bears) == "p2:battlefield" and s.state.cards[bears.id].controller == "p2"
    roundtrip(s)


def test_fiend_hunter_leaving_before_its_enters_trigger_resolves_exiles_for_good(cards):
    """607.2a + 603.10a: the leaves ability resolves first and returns nothing; the exile that follows is for good."""
    s = build(cards, "Fiend Hunter", "Murder", bob=("Grizzly Bears",))
    act(s, "p1", type="set_stops", own=["main1"], others=[], smart_pass=False)
    bears = put(s, "Grizzly Bears", "p2")
    hunter = cast_from_hand(s, "Fiend Hunter", W=2, G=1)
    for _ in range(20):  # the creature spell resolves; its enters trigger goes on the stack with its target
        d = s.state.rules.decision
        if d is not None and bears.id in [o.id for o in d.options]:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears.id])
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.zones.get("stack") and zone_of(s, hunter) == "p1:battlefield"
    murder(s, hunter)  # in response
    resolve(s)
    assert s.state.cards[bears.id].zone.endswith("exile")
    roundtrip(s)


def test_tidehollow_sculler_returns_the_card_to_its_owners_hand(cards):
    s = build(cards, "Tidehollow Sculler", "Murder", bob=("Grizzly Bears",))
    bears = named(s, "Grizzly Bears")
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "hand"})
    sculler = cast_from_hand(s, "Tidehollow Sculler", W=1, B=1)
    resolve(s, "p2", bears.id)
    assert s.state.cards[bears.id].zone.endswith("exile")
    murder(s, sculler)
    resolve(s)
    assert s.state.cards[bears.id].zone == "p2:hand"
    roundtrip(s)


def test_blocking_it_counts_the_creatures_blocking_the_source(cards):
    from tests.test_rules_attachments import ch as chars

    s = build(cards, "Elvish Berserker", "Plague Wight")
    berserker, wight = put(s, "Elvish Berserker"), put(s, "Plague Wight")
    a, b = old(s, "p2", "A", "0/5"), old(s, "p2", "B", "0/5")
    c = old(s, "p2", "C", "0/5")
    stops(s)
    to_attack(s, 3)
    declare(s, (berserker, "p2"), (wight, "p2"))
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": a.id, "attacker_id": berserker.id},
                                                  {"blocker_id": b.id, "attacker_id": berserker.id},
                                                  {"blocker_id": c.id, "attacker_id": wight.id}])
    until(s, lambda s: s.state.turn.phase == "combat_damage" and not s.state.zones.get("stack"))
    assert s.state.cards[berserker.id].zone == "p1:battlefield" and chars(s, berserker).pt == (3, 3)  # (two blockers)
    assert chars(s, a).pt == (0, 5) and chars(s, c).pt == (-1, 4)  # (only the Wight's blocker: -1/-1)
    roundtrip(s)


def test_put_into_your_graveyard_is_the_owners_graveyard(cards):
    s = build(cards, "Field of Souls", "Grim Feast", "Murder", "Grizzly Bears", bob=("Grizzly Bears",))
    put(s, "Field of Souls")
    put(s, "Grim Feast")
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    life = s.state.players["p1"].life
    murder(s, mine)
    resolve(s)
    spirits = [c for c in s.state.cards.values() if c.name == "Spirit" and c.zone == "p1:battlefield"]
    assert len(spirits) == 1 and s.state.players["p1"].life == life
    murder(s, theirs)
    resolve(s)
    assert len([c for c in s.state.cards.values() if c.name == "Spirit"]) == 1  # (Bob's graveyard: not Field of Souls)
    assert s.state.players["p1"].life == life + 2  # (Grim Feast: its toughness)
    roundtrip(s)


def test_keepsake_gorgon_becoming_monstrous_destroys_a_creature(cards):
    s = build(cards, "Keepsake Gorgon")
    gorgon = put(s, "Keepsake Gorgon")
    victim = old(s, "p2", "Victim")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": 5})
    act(s, "p1", type="activate_ability", card_id=gorgon.id, ability=1)
    resolve(s, victim.id)
    assert victim.id not in s.state.cards or s.state.cards[victim.id].zone != "p2:battlefield"
    assert s.state.cards[gorgon.id].counters.get("+1/+1") == 1
    roundtrip(s)


def test_emperor_crocodile_is_sacrificed_once_it_is_alone(cards):
    s = build(cards, "Emperor Crocodile", "Murder")
    croc = put(s, "Emperor Crocodile")
    friend = old(s, "p1", "Friend")
    resolve(s)
    assert zone_of(s, croc) == "p1:battlefield"
    murder(s, friend)
    resolve(s)
    assert zone_of(s, croc) == "p1:graveyard"
    roundtrip(s)


def test_a_state_trigger_doesnt_trigger_again_while_it_waits(cards):
    """603.8: it triggers as the state matches after the table changes, and once until it has left the stack."""
    s = build(cards, "Covetous Dragon", "Grizzly Bears", "Murder")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=["main1"], others=["main1"], smart_pass=False)
    dragon = put(s, "Covetous Dragon")  # (a hand-made move: no automation runs for it)
    victim = old(s, "p2", "Victim")
    cast_from_hand(s, "Grizzly Bears", G=2)  # the table changes: no artifacts, so it triggers
    assert len(s.state.rules.pending_triggers) + sum(e.kind == "trigger" for e in s.state.rules.stack.values()) == 1
    murder(s, victim)  # another change while it waits: no second instance
    assert len(s.state.rules.pending_triggers) + sum(e.kind == "trigger" for e in s.state.rules.stack.values()) == 1
    roundtrip(s)
    resolve(s)
    assert zone_of(s, dragon) == "p1:graveyard"
    roundtrip(s)
