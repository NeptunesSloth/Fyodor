"""Wave 30K: per-player choices — "each player chooses one of each kind, then sacrifices the rest" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave30k_cards.json, from data/cards.sqlite). Three players; every scenario replays the history, reloads a save mid-decision
and checks that what an observer sees of the decision is public-only.

* 101.4 / 101.4b / 101.4c: every player makes all of their choices (one per kind, in the order written), the active player first and then in
  turn order, each knowing the earlier ones; only then is everything not chosen sacrificed at once (701.21a).
* One permanent can be chosen for more than one kind (the rulings of Cataclysm, Cataclysmic Gearhulk, Tragic Arrogance, Liliana, Global Ruin);
  a kind a player controls nothing of is skipped; a permanent a player controls but doesn't own is theirs to choose and goes to its owner's
  graveyard (701.21a, 400.3).
* Cataclysm (all permanents), Cataclysmic Gearhulk / Mythos of Snapdax (nonland permanents: lands are never chosen or sacrificed), Liliana,
  Dreadhorde General (110.4: one per permanent type, each opponent), Global Ruin (205.3i: one land per basic land type), Tragic Arrogance (its
  controller chooses for every player), Mythos of Snapdax ("If {B}{R} was spent … you choose the permanents for each player instead"),
  Slaughter the Strong ("any number of creatures … with total power 4 or less": the answer is checked, a power below 0 subtracts).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_scripts import ch
from tests.wave9c_kit import check, mana, reloaded

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30k_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w30k", number=f"K{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build3(cards, hand=()):
    """Alice (p1, active, in her main phase), Bob (p2) and Carol (p3); Alice's deck holds ``hand``; each has Forests / Islands / Mountains
    and Alice and Bob a Breeding Pool (a Forest Island) to put onto the battlefield."""
    seats = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in hand), (6, "Forest"), (1, "Breeding Pool")])),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(6, "Island"), (1, "Breeding Pool"), (1, "Mountain")])),
             PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(6, "Mountain")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def perm(s, pid, name, type_line, pt=None):
    """A token permanent of this type line (a creature when it has a power/toughness)."""
    spec = {"name": name, "type_line": type_line, "text": ""}
    if pt:
        spec["power"], spec["toughness"] = pt.split("/")
    act(s, pid, type="create_token", player=pid, token=spec)
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def land(s, pid, name="Forest", owner=None):
    """The next card of this name in ``owner``'s library onto the battlefield under ``pid``'s control."""
    owner = owner or pid
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == owner and c.zone == f"{owner}:library")
    act(s, owner, type="move", card_ids=[c.id], to={"player": owner, "zone": "battlefield"})
    if pid != owner:
        act(s, "p1", type="set_controller", card_ids=[c.id], player=pid)
    return s.state.cards[c.id]


def settle(s):
    while not s.state.rules.decision and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")


def cast(s, name, **pool):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, **pool)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    return c


def pick(s, *ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))
    settle(s)


def options(s):
    return {o.id for o in s.state.rules.decision.options}


def observer_sees_only_who(s, observer, chooser):
    d = s.view(observer)["rules"]["decision"]
    assert d["public"] == {"type": "PLAYER_MAKING_CHOICE", "chooser": chooser}
    assert d["kind"] == "waiting" and "options" not in d and d["source_id"] is None and "display" not in d


def gone(s, *cs):
    """For each of these permanents: is it no longer on the battlefield?"""
    return [c.id not in s.state.cards or not s.state.cards[c.id].zone.endswith(":battlefield") for c in cs]


# -- Cataclysm ------------------------------------------------------------------------------------------
def test_cataclysm_each_player_keeps_one_of_each_kind_in_apnap_order(cards):
    s = build3(cards, ["Cataclysm"])
    golem = perm(s, "p1", "Golem", "Token Artifact Creature — Golem", "2/2")
    bear = perm(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    ward, wreath = (perm(s, "p1", n, "Token Enchantment — Shrine") for n in ("Ward", "Wreath"))
    forests = [land(s, "p1") for _ in range(2)]
    wolf = perm(s, "p2", "Wolf", "Token Creature — Wolf", "3/3")
    island = land(s, "p2", "Island")
    borrowed = land(s, "p2", "Mountain", owner="p3")  # Bob controls Carol's Mountain
    assert s.state.cards[borrowed.id].owner == "p3" and s.state.cards[borrowed.id].controller == "p2"
    cast(s, "Cataclysm", W=2, C=2)
    # Alice first (101.4): her one artifact is chosen without a question; the creature is a question (the artifact creature counts)
    d = s.state.rules.decision
    assert d.player == "p1" and options(s) == {golem.id, bear.id} and "creature" in d.prompt
    observer_sees_only_who(s, "p3", "Alice")
    pick(s, golem.id)  # the artifact creature is her creature, too (it may be chosen for more than one kind)
    d = s.state.rules.decision
    assert d.player == "p1" and options(s) == {ward.id, wreath.id} and "enchantment" in d.prompt
    pick(s, ward.id)
    assert options(s) == {c.id for c in forests} and "land" in s.state.rules.decision.prompt
    pick(s, forests[0].id)
    # Bob next, knowing what Alice kept (101.4b): his lands include the Mountain he doesn't own
    d = s.state.rules.decision
    assert d.player == "p2" and "Golem" in d.prompt and options(s) == {island.id, borrowed.id} and "land" in d.prompt
    assert gone(s, bear, wreath, forests[1], wolf, island) == [False] * 5  # nothing is sacrificed until everyone has chosen
    again = reloaded(s)
    pick(s, island.id)
    assert s.state.rules.decision is None  # Carol controls nothing: no question for her
    assert gone(s, bear, wreath, forests[1], borrowed) == [True] * 4
    assert gone(s, golem, ward, forests[0], wolf, island) == [False] * 5  # (Bob's Wolf is his only creature: chosen without a question)
    assert s.state.cards[borrowed.id].zone == "p3:graveyard"  # sacrificed by Bob, it goes to its owner's graveyard
    check(s)
    act(again, "p2", type="choose", decision_id=again.state.rules.decision.id, option_ids=[borrowed.id])
    assert gone(again, island, borrowed) == [True, False] and again.state.cards[borrowed.id].zone == "p2:battlefield"
    check(again)


def test_cataclysm_a_player_leaving_mid_choice_makes_no_choice(cards):
    s = build3(cards, ["Cataclysm"])
    a1, a2 = (perm(s, "p1", n, "Token Creature — Bear", "2/2") for n in ("Alpha", "Beta"))
    b1, b2 = (perm(s, "p2", n, "Token Creature — Beast", "1/1") for n in ("Fox", "Owl"))
    c1, c2 = (perm(s, "p3", n, "Token Creature — Cat", "1/1") for n in ("Lynx", "Puma"))
    cast(s, "Cataclysm", W=2, C=2)
    pick(s, a1.id)
    d = s.state.rules.decision
    assert d.player == "p2" and options(s) == {b1.id, b2.id}
    act(s, "p2", type="concede")  # 800.4f-g: his choice isn't made; the others still choose in turn order
    d = s.state.rules.decision
    assert "p2" in s.state.rules.conceded and d.player == "p3" and options(s) == {c1.id, c2.id}
    pick(s, c2.id)
    assert s.state.rules.decision is None and gone(s, a2, c1) == [True, True] and gone(s, a1, c2) == [False, False]
    check(s)


# -- Cataclysmic Gearhulk / Mythos of Snapdax: nonland permanents ------------------------------------------
def test_cataclysmic_gearhulk_spares_lands_and_sacrifices_itself_when_not_chosen(cards):
    s = build3(cards, ["Cataclysmic Gearhulk"])
    golem = perm(s, "p1", "Golem", "Token Artifact Creature — Golem", "2/2")
    bear = perm(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    shrine = perm(s, "p1", "Shrine", "Token Enchantment — Shrine")
    relic = perm(s, "p2", "Relic Land", "Token Artifact Land")  # a land: never chosen, never sacrificed
    sword, spare = (perm(s, "p2", n, "Token Artifact — Equipment") for n in ("Sword", "Spare"))
    gearhulk = cast(s, "Cataclysmic Gearhulk", W=2, C=3)
    # the trigger resolves: Alice's artifacts are the Golem and the Gearhulk (an artifact creature, too)
    d = s.state.rules.decision
    assert d.player == "p1" and options(s) == {golem.id, gearhulk.id} and "artifact" in d.prompt
    pick(s, golem.id)
    assert options(s) == {golem.id, bear.id, gearhulk.id} and "creature" in s.state.rules.decision.prompt
    pick(s, bear.id)
    d = s.state.rules.decision  # (the enchantment is her Shrine alone) → Bob: the Sword and the Spare, not the Relic Land
    assert d.player == "p2" and options(s) == {sword.id, spare.id} and "Shrine" in d.prompt
    again = reloaded(s)
    pick(s, sword.id)
    assert s.state.rules.decision is None
    assert gone(s, gearhulk, spare) == [True, True] and gone(s, golem, bear, shrine, sword, relic) == [False] * 5
    check(s)
    pick(again, spare.id)
    assert gone(again, sword, spare) == [True, False]


def test_mythos_of_snapdax_its_controller_chooses_for_every_player_when_b_and_r_were_spent(cards):
    s = build3(cards, ["Mythos of Snapdax"])
    bear = perm(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    fox, owl = (perm(s, "p2", n, "Token Creature — Beast", "1/1") for n in ("Fox", "Owl"))
    cast(s, "Mythos of Snapdax", W=2, B=1, R=1)  # {2}{W}{W}: the generic part paid with {B}{R}
    d = s.state.rules.decision
    assert d.player == "p1" and options(s) == {fox.id, owl.id} and "for Bob" in d.prompt  # Alice chooses Bob's creature
    observer_sees_only_who(s, "p2", "Alice")
    pick(s, owl.id)
    assert s.state.rules.decision is None and gone(s, fox, owl, bear) == [True, False, False]
    check(s)
    t = build3(cards, ["Mythos of Snapdax"])
    fox, owl = (perm(t, "p2", n, "Token Creature — Beast", "1/1") for n in ("Fox", "Owl"))
    cast(t, "Mythos of Snapdax", W=2, C=2)  # no {B}{R} spent: each player chooses for themselves
    d = t.state.rules.decision
    assert d.player == "p2" and options(t) == {fox.id, owl.id} and " for " not in d.prompt
    pick(t, fox.id)
    assert t.state.rules.decision is None and gone(t, fox, owl) == [False, True]
    check(t)


# -- Liliana, Dreadhorde General -----------------------------------------------------------------------------
def test_liliana_each_opponent_keeps_one_permanent_of_each_permanent_type(cards):
    s = build3(cards, ["Liliana, Dreadhorde General"])
    liliana = next(c for c in s.state.cards.values() if c.name == "Liliana, Dreadhorde General")
    act(s, "p1", type="move", card_ids=[liliana.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="set_counter", card_id=liliana.id, kind="loyalty", value=9)
    mine = perm(s, "p1", "Mine", "Token Creature — Bear", "2/2")  # Alice's own permanents are not touched
    golem = perm(s, "p2", "Golem", "Token Artifact Creature — Golem", "2/2")
    bear = perm(s, "p2", "Bear", "Token Creature — Bear", "2/2")
    shrine = perm(s, "p2", "Shrine", "Token Enchantment — Shrine")
    ring = perm(s, "p2", "Ring", "Token Artifact — Jewelry")
    isle = land(s, "p2", "Island")
    cat = perm(s, "p3", "Cat", "Token Creature — Cat", "1/1")
    dog = perm(s, "p3", "Dog", "Token Creature — Dog", "1/1")
    act(s, "p1", type="activate_ability", card_id=liliana.id, ability=3)  # −9
    settle(s)
    d = s.state.rules.decision  # Bob first (the opponents in turn order)
    assert d.player == "p2" and options(s) == {golem.id, ring.id} and "artifact" in d.prompt
    pick(s, ring.id)
    assert options(s) == {golem.id, bear.id} and "creature" in s.state.rules.decision.prompt
    pick(s, golem.id)  # (his Shrine and his Island are the only ones he has: no questions)
    d = s.state.rules.decision
    assert d.player == "p3" and "Ring" in d.prompt and options(s) == {cat.id, dog.id}  # Carol knows Bob's choices (101.4b)
    again = reloaded(s)
    pick(s, cat.id)
    assert s.state.rules.decision is None
    assert gone(s, bear, dog) == [True, True] and gone(s, mine, ring, golem, shrine, isle, cat) == [False] * 6
    assert s.state.cards[liliana.id].zone == "p1:graveyard"  # (0 loyalty: 704.5i)
    check(s)
    pick(again, dog.id)
    assert gone(again, cat, dog) == [True, False]
    check(again)


# -- Tragic Arrogance: its controller chooses for every player ---------------------------------------------------
def test_tragic_arrogance_its_controller_chooses_what_each_player_keeps(cards):
    s = build3(cards, ["Tragic Arrogance"])
    golem = perm(s, "p1", "Golem", "Token Artifact Creature — Golem", "2/2")
    bear = perm(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    fox, owl = (perm(s, "p2", n, "Token Creature — Beast", "1/1") for n in ("Fox", "Owl"))
    isle = land(s, "p2", "Island")
    cast(s, "Tragic Arrogance", W=2, C=3)
    d = s.state.rules.decision
    assert d.player == "p1" and options(s) == {golem.id, bear.id}
    pick(s, golem.id)
    d = s.state.rules.decision
    assert d.player == "p1" and options(s) == {fox.id, owl.id} and "for Bob" in d.prompt  # Bob's creature, chosen by Alice
    observer_sees_only_who(s, "p3", "Alice")
    again = reloaded(s)
    pick(s, owl.id)
    assert s.state.rules.decision is None
    assert gone(s, bear, fox) == [True, True] and gone(s, golem, owl, isle) == [False] * 3  # all other nonland permanents; the lands stay
    check(s)
    pick(again, fox.id)
    assert gone(again, owl, fox) == [True, False]
    check(again)


def test_tragic_arrogance_never_names_a_face_down_creature_to_the_player_choosing_it(cards):
    """708.5: Alice chooses among Bob's two face-down creatures (2/2s) without being told what they are, in the question and in the log."""
    s = build3(cards, ["Tragic Arrogance"])
    down = [next(c for c in s.state.cards.values() if c.name == n and c.owner == "p2") for n in ("Breeding Pool", "Mountain")]
    for c in down:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "battlefield"}, face_down=True, face_down_kind="manifest")
    cast(s, "Tragic Arrogance", W=2, C=3)
    d = s.state.rules.decision
    assert d.player == "p1" and options(s) == {c.id for c in down}
    shown = s.view("p1")["rules"]["decision"]
    assert "Breeding Pool" not in json.dumps(shown) and "Mountain" not in json.dumps(shown) and len(shown["options"]) == 2
    pick(s, down[0].id)
    assert "Breeding Pool" not in json.dumps(s.view("p1")["log"]) and "Breeding Pool" not in json.dumps(s.view("p3")["log"])
    check(s)


# -- Global Ruin ------------------------------------------------------------------------------------------------
def test_global_ruin_keeps_one_land_of_each_basic_land_type(cards):
    s = build3(cards, ["Global Ruin"])
    forests = [land(s, "p1") for _ in range(2)]
    pool = land(s, "p1", "Breeding Pool")  # Forest Island: it can be chosen for either type, or both
    isles = [land(s, "p2", "Island") for _ in range(2)]
    bear = perm(s, "p2", "Bear", "Token Creature — Bear", "2/2")
    cast(s, "Global Ruin", W=1, C=4)
    d = s.state.rules.decision  # Alice: the Island is the Pool alone (no question); no Plains, Swamp or Mountain; then a Forest
    assert d.player == "p1" and "Forest" in d.prompt and options(s) == {*(c.id for c in forests), pool.id}
    pick(s, pool.id)  # the Pool is her Island and her Forest: both Forests go
    d = s.state.rules.decision
    assert d.player == "p2" and "Island" in d.prompt and options(s) == {c.id for c in isles}
    pick(s, isles[0].id)
    assert s.state.rules.decision is None
    assert gone(s, *forests, isles[1]) == [True] * 3 and gone(s, pool, isles[0], bear) == [False] * 3
    check(s)


# -- Slaughter the Strong -----------------------------------------------------------------------------------------
def test_slaughter_the_strong_checks_the_total_power_and_sacrifices_the_rest(cards):
    s = build3(cards, ["Slaughter the Strong"])
    big = perm(s, "p1", "Big", "Token Creature — Giant", "5/5")
    small = perm(s, "p1", "Small", "Token Creature — Bear", "1/1")
    three, two, one = (perm(s, "p2", n, "Token Creature — Beast", p) for n, p in (("Three", "3/3"), ("Two", "2/2"), ("One", "1/1")))
    cast(s, "Slaughter the Strong", W=2, C=1)
    d = s.state.rules.decision
    assert d.player == "p1" and (d.min_choices, d.max_choices) == (0, 2) and {o.label for o in d.options} == {"Big (5)", "Small (1)"}
    with pytest.raises(ActionError, match="total power"):
        pick(s, big.id)  # 5 is more than 4
    assert s.state.rules.decision.player == "p1"  # still hers to answer
    pick(s, small.id)
    again = reloaded(s)
    d = s.state.rules.decision
    assert d.player == "p2" and "Small" in d.prompt and (d.min_choices, d.max_choices) == (0, 3)
    with pytest.raises(ActionError, match="total power"):
        pick(s, three.id, two.id)  # 5
    pick(s, two.id, one.id)  # 3: allowed
    assert s.state.rules.decision is None and gone(s, big, three) == [True, True] and gone(s, small, two, one) == [False] * 3
    check(s)
    pick(again, three.id, one.id)  # 4: allowed (on the reloaded table)
    assert gone(again, three, two, one) == [False, True, False]
    check(again)


def test_slaughter_the_strong_a_creature_with_negative_power_subtracts(cards):
    s = build3(cards, ["Slaughter the Strong"])
    wall = perm(s, "p1", "Wall", "Token Creature — Wall", "-2/4")
    ogre = perm(s, "p1", "Ogre", "Token Creature — Ogre", "5/5")
    cast(s, "Slaughter the Strong", W=2, C=1)
    pick(s, wall.id, ogre.id)  # 5 + (-2) = 3: both stay
    assert gone(s, wall, ogre) == [False, False]
    check(s)


# -- coverage ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "type_line", "text", "level"), [
    ("Cataclysm", "Sorcery", "Each player chooses from among the permanents they control an artifact, a creature, an enchantment, and a land, "
                             "then sacrifices the rest.", "FULL"),
    ("Mythos of Snapdax", "Sorcery", "Each player chooses an artifact, a creature, an enchantment, and a planeswalker from among the nonland "
                                     "permanents they control, then sacrifices the rest. If {B}{R} was spent to cast this spell, you choose "
                                     "the permanents for each player instead.", "FULL"),
    ("Tragic Arrogance", "Sorcery", "For each player, you choose from among the permanents that player controls an artifact, a creature, an "
                                    "enchantment, and a planeswalker. Then each player sacrifices all other nonland permanents they control.", "FULL"),
    ("Global Ruin", "Sorcery", "Each player chooses from the lands they control a land of each basic land type, then sacrifices the rest.", "FULL"),
    ("Slaughter the Strong", "Sorcery", "Each player chooses any number of creatures they control with total power 4 or less, then sacrifices "
                                        "all other creatures they control.", "FULL"),
    # near misses stay manual: a kind twice, a kind that isn't a permanent type, the rest not sacrificed, another way to choose
    ("Twice", "Sorcery", "Each player chooses an artifact, an artifact from among the permanents they control, then sacrifices the rest.", "PARTIAL"),
    ("Spell kind", "Sorcery", "Each player chooses an instant, a creature from among the permanents they control, then sacrifices the rest.", "PARTIAL"),
    ("Returns", "Sorcery", "Each player chooses an artifact, a creature from among the permanents they control, then returns the rest.", "PARTIAL"),
    ("Single Combat", "Sorcery", "Each player chooses a creature or planeswalker they control, then sacrifices the rest. Players can't cast "
                                 "creature or planeswalker spells until the end of your next turn.", "FULL"),  # (the casting limit since wave 32C)
    ("Stick Together", "Sorcery", "Each player chooses a party from among creatures they control, then sacrifices the rest.", "FULL"),  # (a party, 700.8d, since wave 53D: tests/test_rules_wave53d_choices.py)
])
def test_coverage_levels(name, type_line, text, level):
    assert coverage.of_characteristics(ch(name, type_line, text)).level == level
