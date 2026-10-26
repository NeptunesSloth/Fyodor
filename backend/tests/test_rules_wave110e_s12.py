"""Wave 110E session 12: Emissary of Grudges (entry secret choice, 614.12a; retargeting, 115.7d)."""
from __future__ import annotations

import json

import pytest

import tests.test_rules_wave110e_cards as base
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave110e_cards import cast as cast_card
from tests.test_rules_wave110e_s11 import _three
from tests.wave9c_kit import card_named, check, mana, pt, put, to_hand

EMISSARY = real("Emissary of Grudges", "{5}{R}", 6, "Creature — Efreet",
                "Flying, haste\nAs this creature enters, secretly choose an opponent.\nReveal the player you chose: Choose new targets for target spell or ability if it's controlled by the "
                "chosen player and if it targets you or a permanent you control. Activate only once.", ("6", "5"), "R")
ARCH = real("Archangel of Strife", "{5}{W}{W}", 7, "Creature — Angel",
            "Flying\nAs this creature enters, each player chooses war or peace.\nCreatures controlled by players who chose war get +3/+0.\nCreatures controlled by players who chose peace get +0/+3.",
            ("6", "6"), "W")
BORCA = real("Bell Borca, Spectral Sergeant", "{2}{R}{W}", 4, "Legendary Creature — Spirit Soldier",
             "Note the mana value of each card as it's put into exile.\nBell Borca's power is equal to the greatest number noted for it this turn.\n"
             "At the beginning of your upkeep, exile the top card of your library. You may play that card this turn.", ("*", "5"), "RW")
TAZRI = real("Tazri, Stalwart Survivor", "{2}{W}", 3, "Legendary Creature — Human Warrior",
             "Each creature you control has \"{T}: Add one mana of any of this creature's colors. Spend this mana only to activate an ability of a creature. Activate only if this creature has another activated ability.\"\n"
             "{W}{U}{B}{R}{G}, {T}: Mill five cards. Put all creature cards with activated abilities that aren't mana abilities from among the milled cards into your hand.", ("3", "3"), "W")
SHAMAN = real("Test Shaman", "{1}{R}", 2, "Creature — Goblin Shaman", "{1}, {T}: You gain 1 life.", ("1", "1"), "R")
ELF = real("Test Mana Elf", "{G}", 1, "Creature — Elf Druid", "{T}: Add {G}.", ("1", "1"), "G")
base.EXTRA.extend([EMISSARY, ARCH, BORCA, TAZRI, SHAMAN, ELF])


def test_emissary_full(cards):
    assert coverage.of_card_data(cards.resolve("Emissary of Grudges")).level == "FULL"


def _table(cards, choose):
    """Alice casts Emissary of Grudges and secretly chooses ``choose``; nobody else is told."""
    s = _three(cards, ["Emissary of Grudges"])
    mana(s, R=1, C=5)
    cast_card(s, "Emissary of Grudges")
    for _ in range(3):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and "secretly" in d.prompt:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith(choose))])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s


def test_emissary_choice_is_secret(cards):
    s = _table(cards, "Bob")
    emissary = card_named(s, "Emissary of Grudges")
    assert emissary.zone == "p1:battlefield" and s.state.rules.secret_choices
    for viewer in ("p2", "p3"):
        seen = json.dumps(s.view(viewer))
        assert "secret_choices" not in seen and "secretly" not in json.dumps(s.view(viewer)["log"])
    check(s)


def _bolt(s, target):
    """Alice passes in her main phase; Bob (stops on) casts Test Bolt at ``target``; the others pass until Alice holds priority with it on the stack."""
    act(s, "p2", type="set_stops", own=[], others=["main1"], smart_pass=False)
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Test Bolt", "p2").id, targets=[target])
    for _ in range(4):
        if s.state.rules.priority == "p1":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.priority == "p1" and s.state.zones["stack"]
    return s.state.zones["stack"][-1]


def _reveal(s, bolt):
    emissary = card_named(s, "Emissary of Grudges")
    act(s, "p1", type="activate_ability", card_id=emissary.id, ability=2, targets=[bolt])
    return emissary


def _finish(s, new=None):
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[new if new in ids else ids[0]])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def _lost(s):
    return {p: 40 - s.state.players[p].life for p in ("p1", "p2", "p3")}


@pytest.mark.parametrize(("chose", "target", "new", "lost"), [
    ("Bob", "p1", "p3", {"p1": 0, "p2": 0, "p3": 3}),      # chosen player's spell targets you: new target Carol
    ("Bob", "p1", None, {"p1": 3, "p2": 0, "p3": 0}),      # ... and you may keep the target
    ("Carol", "p1", "p3", {"p1": 3, "p2": 0, "p3": 0}),    # not the chosen player's spell: no new targets
    ("Bob", "p3", "p1", {"p1": 0, "p2": 0, "p3": 3}),      # chosen player's spell, but it targets neither you nor your permanent: no new targets
])
def test_emissary_retargets_only_a_chosen_players_spell_aimed_at_you(cards, chose, target, new, lost):
    """115.7d: its controller chooses new targets; the conditions are read on resolution (608.2c); a wrong player or a spell not aimed at Alice does nothing."""
    s = _table(cards, chose)
    bolt = _bolt(s, target)
    _reveal(s, bolt)
    _finish(s, new)
    assert _lost(s) == lost
    check(s)


def test_archangel_full(cards):
    assert coverage.of_card_data(cards.resolve("Archangel of Strife")).level == "FULL"


def _war(cards, sides):
    """Alice casts Archangel of Strife; Alice, Bob, Carol answer in turn order (``sides``); Bob has a 0/9 Giant, Alice a 2/2 Bear."""
    s = _three(cards, ["Archangel of Strife", "Test Bear"])
    bear, giant = put(s, "Test Bear"), put(s, "Test Giant", "p2")
    mana(s, W=2, C=5)
    cast_card(s, "Archangel of Strife")
    for pid, side in zip(("p1", "p2", "p3"), sides, strict=True):
        for _ in range(4):
            d = s.state.rules.decision
            if d is not None and "war or peace" in d.prompt:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert d.player == pid and {o.label for o in d.options} == {"War", "Peace"}
        act(s, pid, type="choose", decision_id=d.id, option_ids=[side])
    return s, bear, giant


@pytest.mark.parametrize("sides", [("war", "peace", "war"), ("peace", "peace", "war"), ("war", "war", "war")])
def test_archangel_war_gives_plus_three_power_peace_plus_three_toughness(cards, sides):
    """613.4c: creatures of players who chose war get +3/+0, of players who chose peace +0/+3 (the Archangel itself included)."""
    s, bear, giant = _war(cards, sides)
    angel = card_named(s, "Archangel of Strife")
    assert angel.zone == "p1:battlefield"
    for card, pid, base_pt in ((angel, "p1", (6, 6)), (bear, "p1", (2, 2)), (giant, "p2", (0, 9))):
        want = (base_pt[0] + 3, base_pt[1]) if dict(zip(("p1", "p2", "p3"), sides, strict=True))[pid] == "war" else (base_pt[0], base_pt[1] + 3)
        assert pt(s, card.name, pid) == want, (card.name, pt(s, card.name, pid))
    check(s)


def test_borca_full(cards):
    assert coverage.of_card_data(cards.resolve("Bell Borca, Spectral Sergeant")).level == "FULL"


def _exile(s, name, pid="p2"):
    act(s, pid, type="move", card_ids=[to_hand(s, name, pid).id], to={"zone": "exile"})


def test_borca_power_is_the_greatest_mana_value_noted_while_it_is_on_the_battlefield(cards):
    """Note the mana value of each card as it's put into exile (400.1); the greatest noted this turn is its power; only noted while it is on the battlefield."""
    s = _three(cards, ["Bell Borca, Spectral Sergeant"])
    name = "Bell Borca, Spectral Sergeant"
    for n in ("Test Giant",):
        _exile(s, n)  # exiled before Borca is there: never noted
    mana(s, R=1, W=1, C=2)
    cast_card(s, name)
    answer(s)
    assert pt(s, name)[0] == 0
    for card, power in (("Test Bolt", 1), ("Test Giant", 5)):
        _exile(s, card, "p3" if card == "Test Bolt" else "p2")
        assert pt(s, name)[0] == power
    assert pt(s, name)[1] == 5
    _exile(s, "Test Bolt", "p3")
    assert pt(s, name)[0] == 5  # the greatest, not the latest
    check(s)


def test_borca_upkeep_exile_is_noted_and_the_note_is_gone_next_turn(cards):
    """Its own upkeep exile counts (the card is put into exile: 400.1); the note lasts that turn only."""
    from tests.test_rules_conditionals import until
    from tests.wave110b_kit import top

    s = _three(cards, ["Bell Borca, Spectral Sergeant", "Test Giant"])
    name = "Bell Borca, Spectral Sergeant"
    mana(s, R=1, W=1, C=2)
    cast_card(s, name)
    answer(s)
    top(s, "Test Giant")
    act(s, "p1", type="set_prefs", response="on")
    until(s, lambda s: s.state.turn.number == 4 and card_named(s, "Test Giant").zone == "p1:exile", limit=400)
    assert s.state.turn.active_player == "p1" and pt(s, name)[0] == 5
    check(s)
    until(s, lambda s: s.state.turn.number == 5, limit=400)
    assert pt(s, name)[0] == 0


def test_tazri_full(cards):
    assert coverage.of_card_data(cards.resolve("Tazri, Stalwart Survivor")).level == "FULL"


def _mana_ab(s, card):
    from app.rules.plan import Plan

    return next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(card).abilities if a.kind == "mana")


def _ready(s, *cards_):
    for c in cards_:
        s.state.rules.controlled_since[c.id].turn = 0


def test_tazri_gives_a_mana_ability_only_to_creatures_with_another_activated_ability(cards):
    """602.1, 605.1a: a vanilla creature has only the granted ability (not "another"), so it cannot activate it; a creature with an activated ability adds one mana of its color,
    and that mana is for abilities of creatures only."""
    from app.game.errors import ActionError

    s = _three(cards, ["Tazri, Stalwart Survivor", "Test Shaman", "Test Bear", "Test Mana Elf"])
    tazri, shaman, bear, elf = (put(s, n) for n in ("Tazri, Stalwart Survivor", "Test Shaman", "Test Bear", "Test Mana Elf"))
    _ready(s, tazri, shaman, bear, elf)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=bear.id, ability=_mana_ab(s, bear))
    act(s, "p1", type="activate_ability", card_id=shaman.id, ability=_mana_ab(s, shaman))
    units = lambda: [(u.sym, "activate an ability of a creature" in u.note) for u in s.state.players["p1"].mana_units]  # noqa: E731
    assert units() == [("R", True)]  # the color of the Shaman, for abilities of creatures only
    act(s, "p1", type="activate_ability", card_id=elf.id, ability=0)  # its own {T}: Add {G}
    act(s, "p1", type="activate_ability", card_id=tazri.id, ability=_mana_ab(s, tazri))  # Tazri also has the mill ability
    assert sorted(units()) == [("G", False), ("R", True), ("W", True)]
    check(s)


def test_tazri_mill_five_puts_creature_cards_with_non_mana_activated_abilities_into_hand(cards):
    """Mill five; only creature cards with an activated ability that isn't a mana ability go to hand (a mana-only creature, a vanilla creature and a noncreature stay milled)."""
    from tests.wave110b_kit import top

    s = _three(cards, ["Tazri, Stalwart Survivor", "Test Shaman", "Test Shaman", "Test Mana Elf", "Test Bear", "Test Saga"])
    tazri = put(s, "Tazri, Stalwart Survivor")
    _ready(s, tazri)
    shamans = [c for c in s.state.cards.values() if c.name == "Test Shaman" and c.owner == "p1"]
    for n in ("Test Saga", "Test Bear", "Test Mana Elf"):
        top(s, n)
    for c in shamans:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    mana(s, W=1, U=1, B=1, R=1, G=1)
    act(s, "p1", type="activate_ability", card_id=tazri.id, ability=_ability_index(s, tazri, "Mill"))
    answer(s)
    assert {c.id for c in shamans} <= set(s.state.zones["p1:hand"])
    for n in ("Test Saga", "Test Bear", "Test Mana Elf"):
        assert card_named(s, n).zone == "p1:graveyard", n
    check(s)


def _ability_index(s, card, word):
    from app.rules.plan import Plan

    return next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(card).abilities if a.kind == "activated" and word in a.text)
