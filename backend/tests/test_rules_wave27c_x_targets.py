"""Wave 27C: "up to X target …, where X is <a count>" (CR 107.3c, 601.2c): the number of targets is that count as the targets are chosen,
and doesn't change after (601.2c), so a source sacrificed to pay the cost (601.2h, after the targets) still gives its X.
Every scenario checks the replay and a save/load round trip (wave9c_kit.check)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, until_asked
from tests.test_rules_wave12a_counters_keywords import answer
from tests.test_rules_wave18d_merged import MUTATE_REMINDER, mutate_key
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

REAL = [
    ("Recantation", "{2}{U}{U}", "Enchantment", None, None, "U",
     "At the beginning of your upkeep, you may put a verse counter on this enchantment.\n"
     "{U}, Sacrifice this enchantment: Return up to X target permanents to their owners' hands, where X is the number of verse counters on this enchantment."),
    ("Marshal's Anthem", "{1}{W}{W}", "Enchantment", None, None, "W",
     "Multikicker {1}{W} (You may pay an additional {1}{W} any number of times as you cast this spell.)\nCreatures you control get +1/+1.\n"
     "When this enchantment enters, return up to X target creature cards from your graveyard to the battlefield, where X is the number of times this enchantment was kicked."),
    ("Endurance Bobblehead", "{3}", "Artifact — Bobblehead", None, None, "",
     "{T}: Add one mana of any color.\n{3}, {T}: Up to X target creatures you control get +1/+0 and gain indestructible until end of turn, where X is the "
     "number of Bobbleheads you control as you activate this ability. Activate only as a sorcery."),
    ("Aether Burst", "{1}{U}", "Instant", None, None, "U",
     "Return up to X target creatures to their owners' hands, where X is one plus the number of cards named Aether Burst in all graveyards as you cast this spell."),
    ("Mogis's Marauder", "{2}{B}", "Creature — Human Berserker", "2", "2", "B",
     "When this creature enters, up to X target creatures each gain intimidate and haste until end of turn, where X is your devotion to black. (A creature "
     "with intimidate can't be blocked except by artifact creatures and/or creatures that share a color with it. Each {B} in the mana costs of permanents you "
     "control counts toward your devotion to black.)"),
    ("Vile Requiem", "{3}{B}{B}", "Enchantment", None, None, "B",
     "At the beginning of your upkeep, you may put a verse counter on this enchantment.\n"
     "{1}{B}, Sacrifice this enchantment: Destroy up to X target nonblack creatures, where X is the number of verse counters on this enchantment. They can't be regenerated."),
    ("Archipelagore", "{5}{U}{U}", "Creature — Leviathan", "7", "7", "U",
     "Mutate {5}{U}" + MUTATE_REMINDER + "\nWhenever this creature mutates, tap up to X target creatures, where X is the number of times this creature has mutated. "
     "Those creatures don't untap during their controller's next untap step."),
]
EXTRA = [card(n, set_code="t27c", number=f"T{i:02d}", mana_cost=mc, cmc=float(sum(int(x) if x.isdigit() else 1 for x in mc.strip("{}").split("}{"))),
              type_line=tl, oracle_text=text, colors=list(c), color_identity=list(c), keywords=[], **({"power": p, "toughness": t} if p else {}))
         for i, (n, mc, tl, p, t, c, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [r[0] for r in REAL])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_a_count_that_needs_a_target_or_the_event_stays_manual():
    # (review 27C: read while the targets are chosen, a target's or the trigger event's count would be 0)
    assert scripts.parse_effects("Tap up to X target creatures, where X is the number of cards in target opponent's hand.") is None
    assert scripts.parse_effects("Tap X target creatures, where X is the number of Elves you control.") is None  # (exactly X: manual)
    got = scripts.parse_effects("Tap up to X target creatures, where X is the number of cards in your hand.")
    assert got is not None and got[1][0]["x_value"] == {"hand": "you"}


def test_bobblehead_one_bobblehead_allows_one_target(cards):
    s = build(cards, ["Endurance Bobblehead"])
    put(s, "Endurance Bobblehead")
    a, b = creature(s, "p1", "Bear A"), creature(s, "p1", "Bear B")
    mana(s, C=3)
    with pytest.raises(ActionError):  # (X = 1 Bobblehead: two targets are too many)
        act(s, "p1", type="activate_ability", card_id=card_named(s, "Endurance Bobblehead").id, ability=1,
            targets=[a.id, b.id], target_counts=[2])
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Endurance Bobblehead").id, ability=1, targets=[a.id], target_counts=[1])
    answer(s)
    assert pt(s, "Bear A") == (3, 2) and pt(s, "Bear B") == (2, 2)
    check(s)


def test_recantation_counts_its_verse_counters_though_it_is_sacrificed(cards):
    s = build(cards, ["Recantation"])
    put(s, "Recantation")
    a, b, c = (creature(s, "p2", n, type_line="Creature — Bear") for n in ("Bear A", "Bear B", "Bear C"))
    rec = card_named(s, "Recantation").id
    act(s, "p1", type="counter", card_ids=[rec], kind="verse", delta=2)
    mana(s, U=1)
    with pytest.raises(ActionError):  # (two verse counters: three targets are too many)
        act(s, "p1", type="activate_ability", card_id=rec, ability=1, targets=[a.id, b.id, c.id], target_counts=[3])
    act(s, "p1", type="activate_ability", card_id=rec, ability=1)  # (asked: up to two, 601.2c; then it is sacrificed, 601.2h)
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 2 and d.min_choices == 0
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[a.id, b.id])
    assert s.state.cards[rec].zone.endswith("graveyard")  # (the counters are gone with it; the number of targets doesn't change, 601.2c)
    answer(s)
    assert a.id not in s.state.cards or s.state.cards[a.id].zone.endswith("battlefield") is False  # (tokens leave the battlefield, 111.7)
    assert b.id not in s.state.cards or s.state.cards[b.id].zone.endswith("battlefield") is False
    assert s.state.cards[c.id].zone.endswith("battlefield")
    check(s)


def test_vile_requiem_with_no_counters_has_no_targets(cards):
    s = build(cards, ["Vile Requiem"])
    put(s, "Vile Requiem")
    a = creature(s, "p2", "Bear A")
    mana(s, B=2)
    with pytest.raises(ActionError):  # (X = 0: no target can be chosen)
        act(s, "p1", type="activate_ability", card_id=card_named(s, "Vile Requiem").id, ability=1, targets=[a.id], target_counts=[1])
    check(s)


def test_aether_burst_counts_the_ones_in_every_graveyard(cards):
    s = build(cards, ["Aether Burst"], theirs=["Aether Burst"])
    act(s, "p2", type="move", card_ids=[card_named(s, "Aether Burst", "p2").id], to={"zone": "graveyard"})
    a, b, c = (creature(s, "p2", n) for n in ("Bear A", "Bear B", "Bear C"))
    spell = to_hand(s, "Aether Burst")
    mana(s, U=2)
    with pytest.raises(ActionError):  # (X = 1 + one in Bob's graveyard: three targets are too many)
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[a.id, b.id, c.id], target_counts=[3])
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[a.id, b.id], target_counts=[2])
    answer(s)
    assert s.state.cards[c.id].zone.endswith("battlefield")
    assert all(t not in s.state.cards or s.state.cards[t].zone.endswith("battlefield") is False for t in (a.id, b.id))
    check(s)


def test_mogis_marauder_reads_devotion_as_its_trigger_is_put_on_the_stack(cards):
    s = build(cards, ["Mogis's Marauder", "Vile Requiem"])
    put(s, "Vile Requiem")  # ({B}{B} + the Marauder's {B}: devotion to black 3)
    for n in ("Bear A", "Bear B", "Bear C", "Bear D"):
        creature(s, "p1", n)
    spell = to_hand(s, "Mogis's Marauder")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = until_asked(s)
    assert d is not None and d.max_choices == 3
    check(s)


def test_archipelagore_counts_this_mutation(cards):
    s = build(cards, ["Archipelagore"])
    bear = creature(s, "p1", "Bear", type_line="Creature — Bear")
    a, b = creature(s, "p2", "Foe A"), creature(s, "p2", "Foe B")
    spell = to_hand(s, "Archipelagore")
    mana(s, U=6)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], alt_cost=mutate_key(s, spell))
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.resume and d.resume.get("step") == "mutate_choice":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["over"])
        elif d is not None:
            break
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 1  # (it has mutated once)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[a.id])
    answer(s)
    assert s.state.cards[a.id].tapped and not s.state.cards[b.id].tapped
    check(s)


@pytest.mark.parametrize("kicks", [0, 1])
def test_marshals_anthem_trigger_counts_its_kicks(cards, kicks):
    s = build(cards, ["Marshal's Anthem", "Llanowar Elves"])
    act(s, "p1", type="move", card_ids=[card_named(s, "Llanowar Elves").id], to={"zone": "graveyard"})
    spell = to_hand(s, "Marshal's Anthem")
    mana(s, W=6)
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=kicks)
    d = until_asked(s)
    if kicks:  # (X = 1: one of the creature cards may be chosen)
        assert d is not None and d.max_choices == 1
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[card_named(s, "Llanowar Elves").id])
        answer(s)
        assert card_named(s, "Llanowar Elves").zone.endswith("battlefield")
    else:  # (X = 0: no targets, nothing to choose)
        assert d is None
        assert card_named(s, "Llanowar Elves").zone.endswith("graveyard")
    check(s)
