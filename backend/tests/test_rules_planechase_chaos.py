"""-- planechase chaos (wave B) -- chaos abilities read by exact wording (app/rules/planar_chaos.py; 311.7, 901.9b), on real Oracle
text: chaos is rolled with the rules engine on, the trigger (controlled by the planar controller, 901.6) resolves, the effect is
checked, then ``check`` (replay + save/load round trip)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import coverage, planar_chaos
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_planechase import script
from tests.test_rules_conditionals import settle, to_turn, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import card_named, check, pt, put

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    "Krosa": ("Plane — Dominaria", "All creatures get +2/+2.\nWhenever chaos ensues, you may add {W}{U}{B}{R}{G}."),
    "Besieged Viking Village": ("Plane — Earth", 'All creatures have "Boast — {1}: Put a +1/+1 counter on this creature." (Activate only if '
                                "that creature attacked this turn and only once each turn.)\nWhenever chaos ensues, put an indestructible "
                                "counter on target creature you control that attacked this turn."),
    "Kessig": ("Plane — Innistrad", "Prevent all combat damage that would be dealt by non-Werewolf creatures.\nWhenever chaos ensues, each "
               "creature you control gets +2/+2, gains trample, and becomes a Werewolf in addition to its other types until end of turn."),
    "Velis Vel": ("Plane — Lorwyn", "Each creature gets +1/+1 for each other creature on the battlefield that shares at least one creature "
                  "type with it. (For example, if two Elemental Shamans and an Elemental Spirit are on the battlefield, each gets +2/+2.)\n"
                  "Whenever chaos ensues, target creature gains all creature types until end of turn."),
    "Sokenzan": ("Plane — Kamigawa", "All creatures get +1/+1 and have haste.\nWhenever chaos ensues, untap all creatures that attacked this "
                 "turn. If it's a main phase, there is an additional combat phase after this phase, followed by an additional main phase."),
    "Esper": ("Plane — Alara", "Artifact spells cost {1} less to cast.\nWhenever chaos ensues, creatures you control that are white, blue, "
              "and/or black become artifacts in addition to their other types until end of turn. Then each artifact creature you control "
              "gains vigilance, menace, and lifelink until end of turn."),
    "Lair of the Ashen Idol": ("Plane — Azgol", "At the beginning of your upkeep, sacrifice a creature. If you can't, planeswalk.\nWhenever "
                               "chaos ensues, any number of target players each create a 2/2 black Zombie creature token."),
    "Agyrem": ("Plane — Ravnica", "Whenever a white creature dies, return it to the battlefield under its owner's control at the beginning of "
               "the next end step.\nWhenever a nonwhite creature dies, return it to its owner's hand at the beginning of the next end step.\n"
               "Whenever chaos ensues, creatures can't attack you until a player planeswalks."),
    "Eloren Wilds": ("Plane — Shandalar", "Whenever a player taps a permanent for mana, that player adds one mana of any type that permanent "
                     "produced.\nWhenever chaos ensues, target player can't cast spells until a player planeswalks."),
    "Celestine Reef": ("Plane — Luvion", "Creatures without flying or islandwalk can't attack.\nWhenever chaos ensues, until a player "
                       "planeswalks, you can't lose the game and your opponents can't win the game."),
    "Prime Minister's Cabinet Room": ("Plane — Earth", "At the beginning of combat on your turn, up to one target creature you control becomes "
                                      "a copy of target creature an opponent controls.\nWill of the council — Whenever chaos ensues, starting "
                                      "with you, each player votes for a creature you don't control. Exile each creature with the most votes "
                                      "or tied for most votes."),
    "The Western Cloud": ("Plane — Gobakhan", "Prevent all damage that would be dealt to creatures and planeswalkers you control.\nWhenever "
                          "chaos ensues, create three tapped Treasure tokens. They each deal 1 damage to each creature and each planeswalker."),
    "Temple of Atropos": ("Plane — Time", "At the beginning of each of your postcombat main phases, there is an additional beginning phase "
                          "after this phase. (The beginning phase includes the untap, upkeep, and draw steps.)\nWhen chaos ensues, reverse the "
                          "game's turn order. Then planeswalk. (For example, if play had proceeded clockwise around the table, it now goes "
                          "counterclockwise.)"),
    "The Doctor's Tomb": ("Plane — Trenzalore", "If a creature would die, instead exile it and that creature's controller loses 2 life.\n"
                          "Whenever chaos ensues, redistribute any number of players' life totals. (Each of those players gets one life "
                          "total back.)"),
    "The Wilds": ("Plane — Eldraine", "When you planeswalk to The Wilds and at the beginning of your upkeep, create a Food token.\nWhenever "
                  "chaos ensues, target player sacrifices a creature of their choice. If they do, you create a Food token. You create two "
                  "Food tokens instead if the sacrificed creature's toughness was 4 or greater."),
    "The Cheetah Planet": ("Plane — Outside Mutter's Spiral", "When you planeswalk to The Cheetah Planet and at the beginning of your "
                           "upkeep, put two +1/+1 counters on target non-Cat creature you control. It becomes a Cat in addition to its other "
                           "types.\nWhenever chaos ensues, all Cats gain provoke until end of turn. (Whenever a Cat attacks, its controller may "
                           "have target creature defending player controls untap and block it if able.)"),
    "The Great Aerie": ("Plane — Tarkir", "When you planeswalk to The Great Aerie and at the beginning of your upkeep, bolster 3. (Choose a "
                        "creature with the least toughness among creatures you control and put three +1/+1 counters on it.)\nWhenever chaos "
                        "ensues, choose up to one target creature you control and up to one target creature an opponent controls. Each of "
                        "those creatures deals damage equal to its toughness to the other."),
}
EXTRA = [card(n, set_code="opca", number=f"PC-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(PLANES.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Savannah Lions", "{W}", 1, "Creature — Cat", "", ("2", "1"), "W"),
          real("Ornithopter", "{0}", 0, "Artifact Creature — Thopter", "Flying", ("0", "2")),
          real("Craw Wurm", "{4}{G}{G}", 6, "Creature — Wurm", "", ("6", "4"), "G")]
# the chaos lines this wave reads; FULL: the planes whose every line the engine runs
CHAOS_LINES = {n: next(i for i, line in enumerate(o.split("\n")) if "haos ensues" in line) for n, (_, o) in PLANES.items() if n != "Krosa"}
FULL = ["Besieged Viking Village", "Velis Vel", "Sokenzan", "Esper", "Lair of the Ashen Idol", "Agyrem", "Celestine Reef", "The Great Aerie", "Temple of Atropos",
        "The Cheetah Planet", "The Wilds"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


class _InOrder:
    def shuffle(self, items: list) -> None:
        pass

    def randint(self, lo: int, hi: int) -> int:
        return lo


def table(cards, planes: list[str]) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Runeclaw Bear"), (1, "Savannah Lions"), (1, "Ornithopter"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Runeclaw Bear"), (1, "Craw Wurm"), (10, "Island")])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n) for n in planes]
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False, first_player=0,
                     settings=GameSettings(planechase=True, planar_deck_size=len(pool)), planar_pool=lambda: pool, rng=_InOrder())
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def chaos(s, monkeypatch, picks=()):
    """Alice rolls the chaos symbol (901.9b); the chaos trigger's choices take the ``picks`` (card or player ids, in this order of
    preference) when offered."""
    script(monkeypatch, [2])
    act(s, "p1", type="roll_planar_die")
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            chosen = [o.id for p in picks for o in d.options if p in (o.id, o.card_id)][: d.max_choices]
            if len(chosen) < d.min_choices:
                chosen = [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.planechase.last_roll.face == "chaos"


def ch(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize("name", list(CHAOS_LINES))
def test_the_chaos_line_is_read(cards, name):
    cov = coverage.of_card_data(cards.resolve(name))
    assert next(f for f in cov.features if f.id == f"text:{CHAOS_LINES[name]}").supported
    if name in FULL:  # (the others' other lines are read or not by other work: only this line is asserted)
        assert cov.level == "FULL"


def test_velis_vel_target_creature_gains_all_creature_types(cards, monkeypatch):
    s = table(cards, ["Velis Vel", "Krosa"])
    bear, lions = put(s, "Runeclaw Bear"), put(s, "Savannah Lions")
    chaos(s, monkeypatch, picks=[bear.id])
    assert {"Bear", "Cat", "Elf", "Goblin"} <= ch(s, bear).subtypes and "Elf" not in ch(s, lions).subtypes
    assert pt(s, "Runeclaw Bear") == (3, 3) and pt(s, "Savannah Lions") == (3, 2)  # (Velis Vel: now they share the Cat type)
    to_turn(s, 2)
    assert "Elf" not in ch(s, bear).subtypes  # until end of turn (514.2)
    check(s)


def test_kessig_pump_trample_and_werewolf(cards, monkeypatch):
    s = table(cards, ["Kessig", "Krosa"])
    bear = put(s, "Runeclaw Bear")
    theirs = put(s, "Runeclaw Bear", "p2")
    chaos(s, monkeypatch)
    c = ch(s, bear)
    assert pt(s, "Runeclaw Bear") == (4, 4) and "trample" in c.keywords and {"Bear", "Werewolf"} <= c.subtypes
    assert "Werewolf" not in ch(s, theirs).subtypes and pt(s, "Runeclaw Bear", "p2") == (2, 2)
    check(s)


def test_esper_white_blue_black_creatures_become_artifacts_then_artifact_creatures_gain_keywords(cards, monkeypatch):
    s = table(cards, ["Esper", "Krosa"])
    bear, lions, thopter = put(s, "Runeclaw Bear"), put(s, "Savannah Lions"), put(s, "Ornithopter")
    chaos(s, monkeypatch)
    assert "Artifact" in ch(s, lions).types and "Artifact" not in ch(s, bear).types
    for c in (lions, thopter):  # ("Then": the Lions are an artifact by now)
        assert {"vigilance", "menace", "lifelink"} <= set(ch(s, c).keywords)
    assert "lifelink" not in ch(s, bear).keywords
    check(s)


@pytest.mark.parametrize("picks,made", [(["p1", "p2"], {"p1": 1, "p2": 1}), (["p2"], {"p2": 1})])
def test_lair_of_the_ashen_idol_any_number_of_target_players(cards, monkeypatch, picks, made):
    s = table(cards, ["Krosa", "Lair of the Ashen Idol"])
    act(s, "p1", type="planeswalk")  # (not the starting plane: its upkeep trigger would planeswalk away before the roll)
    chaos(s, monkeypatch, picks=picks)
    zombies = [c for c in s.state.cards.values() if c.name == "Zombie" and c.zone.endswith(":battlefield")]
    assert {p: sum(c.controller == p for c in zombies) for p in made} == made and len(zombies) == len(made)
    check(s)


def test_besieged_viking_village_targets_a_creature_that_attacked_this_turn(cards, monkeypatch):
    from tests.test_rules_conditionals import through_combat

    s = table(cards, ["Besieged Viking Village", "Krosa"])
    bear, lions = put(s, "Runeclaw Bear"), put(s, "Savannah Lions")
    to_turn(s, 3)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    through_combat(s)
    assert s.state.turn.phase == "main2"
    chaos(s, monkeypatch, picks=[lions.id])  # (the Lions didn't attack: not a legal target; the Bear is the only one)
    assert s.state.cards[bear.id].counters.get("indestructible") == 1 and not s.state.cards[lions.id].counters.get("indestructible")
    check(s)


def test_sokenzan_untaps_attackers_and_adds_a_combat_after_this_main_phase(cards, monkeypatch):
    from tests.test_rules_conditionals import through_combat

    s = table(cards, ["Sokenzan", "Krosa"])
    bear = put(s, "Runeclaw Bear")  # (haste: Sokenzan)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    through_combat(s)
    assert s.state.cards[bear.id].tapped and s.state.turn.phase == "main2"
    chaos(s, monkeypatch)
    assert not s.state.cards[bear.id].tapped
    act(s, "p1", type="pass_priority")
    assert s.state.turn.number == 1 and s.state.turn.phase in ("begin_combat", "declare_attackers")  # 500.8: the additional combat phase
    check(s)


@pytest.mark.parametrize("walk", [False, True])
def test_agyrem_creatures_cant_attack_you_until_a_player_planeswalks(cards, monkeypatch, walk):
    s = table(cards, ["Agyrem", "Krosa"])
    theirs = put(s, "Runeclaw Bear", "p2")
    chaos(s, monkeypatch)
    assert any(e.duration == planar_chaos.PLANESWALK for e in s.state.rules.effects)
    if walk:  # 611.2a: the effect ends as a player planeswalks (701.31)
        act(s, "p1", type="planeswalk")  # (by hand: the engine takes it in before the next intent)
    to_turn(s, 2)
    assert any(e.duration == planar_chaos.PLANESWALK for e in s.state.rules.effects) != walk  # Bob's turn: still "you" = Alice, the planar controller as the ability resolved
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    if walk:
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": theirs.id, "target": "p1"}])
        assert s.state.cards[theirs.id].tapped
    else:
        with pytest.raises(Exception, match="(?i)attack"):
            act(s, "p2", type="declare_attackers", attackers=[{"card_id": theirs.id, "target": "p1"}])
    check(s)


def test_eloren_wilds_target_player_cant_cast_spells_until_a_player_planeswalks(cards, monkeypatch):
    s = table(cards, ["Eloren Wilds", "Krosa"])
    chaos(s, monkeypatch, picks=["p2"])
    limits = [x for x in s.state.rules.cast_limits if x["until"] == planar_chaos.PLANESWALK]
    assert [x["player"] for x in limits] == ["p2"]
    to_turn(s, 3)  # (no turn ends it)
    assert [x["player"] for x in s.state.rules.cast_limits if x["until"] == planar_chaos.PLANESWALK] == ["p2"]
    act(s, "p1", type="planeswalk")
    act(s, "p1", type="pass_priority")  # (the next intent: the engine takes in the planeswalk made by hand first)
    assert not [x for x in s.state.rules.cast_limits if x["until"] == planar_chaos.PLANESWALK]
    check(s)


def test_celestine_reef_you_cant_lose_until_a_player_planeswalks(cards, monkeypatch):
    s = table(cards, ["Celestine Reef", "Krosa"])
    chaos(s, monkeypatch)
    act(s, "p1", type="set_life", player="p1", value=0)
    settle(s)
    to_turn(s, 2)  # (104.3, 704.5a: not this turn only)
    assert "p1" not in dict(s.state.rules.lost) and s.state.rules.winner is None
    act(s, "p2", type="planeswalk")  # (Bob is the planar controller now, 311.5)
    act(s, s.state.rules.priority, type="pass_priority")
    assert "p1" in dict(s.state.rules.lost)
    check(s)


def test_prime_ministers_cabinet_room_will_of_the_council(cards, monkeypatch):
    s = table(cards, ["Prime Minister's Cabinet Room", "Krosa"])
    mine = put(s, "Runeclaw Bear")
    theirs = put(s, "Runeclaw Bear", "p2")
    chaos(s, monkeypatch, picks=[theirs.id])  # both vote for Bob's Bear (the only creature Alice doesn't control)
    assert s.state.cards[theirs.id].zone == "p2:exile" and s.state.cards[mine.id].zone == "p1:battlefield"
    check(s)


def test_the_western_cloud_treasures_each_deal_one_damage(cards, monkeypatch):
    s = table(cards, ["The Western Cloud", "Krosa"])
    theirs = put(s, "Runeclaw Bear", "p2")
    chaos(s, monkeypatch)
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    assert len(treasures) == 3 and all(c.tapped for c in treasures)
    assert s.state.cards[theirs.id].zone == "p2:graveyard"  # three sources, 1 damage each (120.3)
    check(s)


@pytest.mark.parametrize("both", [True, False])
def test_the_great_aerie_each_deals_damage_equal_to_its_toughness_to_the_other(cards, monkeypatch, both):
    s = table(cards, ["The Great Aerie", "Krosa"])
    lions = put(s, "Savannah Lions")
    theirs = put(s, "Runeclaw Bear", "p2")
    chaos(s, monkeypatch, picks=[lions.id, theirs.id] if both else [lions.id])
    if both:  # the Lions (toughness 1) deal 1 to the Bear; the Bear (toughness 2) deals 2 to the Lions
        assert s.state.cards[lions.id].zone == "p1:graveyard" and s.state.cards[theirs.id].damage == 1
    else:  # up to one: no Bear chosen, "the other" doesn't exist: nothing is dealt
        assert s.state.cards[lions.id].zone == "p1:battlefield" and s.state.cards[theirs.id].damage == 0
    check(s)


def test_temple_of_atropos_reverses_the_turn_order_then_planeswalks(cards, monkeypatch):
    s = table(cards, ["Temple of Atropos", "Krosa"])
    assert not s.state.rules.turn_reversed110m
    chaos(s, monkeypatch)
    assert s.state.rules.turn_reversed110m and s.state.planechase.deck[0].name == "Krosa"
    check(s)


def test_the_doctors_tomb_redistributes_life_totals(cards, monkeypatch):
    s = table(cards, ["The Doctor's Tomb", "Krosa"])
    act(s, "p1", type="set_life", player="p2", value=10)
    chaos(s, monkeypatch, picks=["p2", "p1"])  # both players; Alice gets Bob's total (the last one goes to the last player)
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (10, 40)
    check(s)


def test_the_cheetah_planet_cats_gain_provoke(cards, monkeypatch):
    s = table(cards, ["The Cheetah Planet", "Krosa"])
    lions = put(s, "Savannah Lions")
    theirs = put(s, "Runeclaw Bear", "p2")
    to_turn(s, 3)
    chaos(s, monkeypatch)
    assert "provoke" in ch(s, lions).keywords
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": lions.id, "target": "p2"}])
    for _ in range(20):  # the provoke trigger (702.39a): target Bob's Bear, and do it
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        if d is not None:
            pick = [o.id for o in d.options if o.card_id == theirs.id or o.id in ("yes", "true")] or [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick[:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(Exception, match="(?i)block"):
        act(s, "p2", type="declare_blockers", blocks=[])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": lions.id}])
    check(s)


@pytest.mark.parametrize("victim,foods", [("Runeclaw Bear", 1), ("Craw Wurm", 2), (None, 0)])
def test_the_wilds_sacrifice_then_one_or_two_foods(cards, monkeypatch, victim, foods):
    s = table(cards, ["The Wilds", "Krosa"])
    if victim:
        put(s, victim, "p2")

    def food():
        return sum(c.name == "Food" and c.zone == "p1:battlefield" for c in s.state.cards.values())

    before = food()  # (its upkeep trigger made one already)
    chaos(s, monkeypatch, picks=["p2"])
    assert food() - before == foods  # 614.1a: two instead of one when the sacrificed creature's toughness was 4 or greater (608.2h)
    if victim:
        assert card_named(s, victim, "p2").zone == "p2:graveyard"
    check(s)
