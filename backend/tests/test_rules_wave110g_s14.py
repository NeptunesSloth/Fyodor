"""Wave 110G session 14: Drain Power (605.3a, 106.4 lost mana, 106.3 added); Spellweaver Volute with three players (303.4a, 707.10)."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110g_s13 import EXTRA as S13
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DRAIN = "Target player activates a mana ability of each land they control. Then that player loses all unspent mana and you add the mana lost this way."

SEA = ("(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Create a 2/2 green Alien Salamander creature token with islandwalk. "
       "(It can't be blocked as long as defending player controls an Island.)\nIII — Until end of turn, whenever a Salamander deals combat damage to a player, "
       "it deals that much damage to target creature that player controls.")
EXTRA = [
    real("The Sea Devils", "{2}{U}{U}", 4, "Enchantment \u2014 Saga", SEA, None, "U"),
    real("Test Wall", "{2}", 2, "Creature \u2014 Wall", "", ("0", "9"), ""),
    real("Drain Power", "{U}{U}", 2, "Sorcery", DRAIN, None, "U"),
    *[c for c in S13 if c["name"] in ("Spellweaver Volute", "Test Shock", "Test Jolt", "Test Tonic")],
]


@pytest.fixture
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def _drain(s, limit=30):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if o.id in ("yes", "p2")), d.options[0].id)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Drain Power")).level == "FULL"


def test_drain_power_takes_every_land_and_floating_mana_in_kind(cards):
    """Bob's Forest and Island are activated, his floating {R} too: all of it is lost and Alice adds {G}{U}{R} (106.3, 106.4)."""
    s = build(cards, ["Drain Power"], ["Forest", "Island"])
    put(s, "Forest", "p2"), put(s, "Island", "p2")
    dp = to_hand(s, "Drain Power")
    mana(s, "p2", R=1)
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=dp.id, targets=["p2"])
    _drain(s)
    p2 = s.state.players["p2"]
    assert not any(p2.mana.values()) and not p2.mana_units
    p1 = s.state.players["p1"]
    got = {k: v for k, v in p1.mana.items() if v}
    for u in p1.mana_units:
        got[u.sym] = got.get(u.sym, 0) + 1
    assert got == {"G": 1, "U": 1, "R": 1}
    check(s)


def test_drain_power_on_yourself_keeps_nothing_extra(cards):
    """Targeting yourself: your own lands are activated, your pool is lost, and you add it back (nets the same)."""
    s = build(cards, ["Drain Power", "Forest"], [])
    put(s, "Forest")
    dp = to_hand(s, "Drain Power")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=dp.id, targets=["p1"])
    _drain(s)
    p1 = s.state.players["p1"]
    assert sum(p1.mana.values()) + len(p1.mana_units) == 1  # the Forest's {G}; the cost was paid before
    check(s)


def _three(cards):
    mk = lambda c, n: deck(cards, c, [*((1, x) for x in n), (12, "Island")])  # noqa: E731
    ps = [PlayerSetup("Alice", cards=mk("Krenko, Mob Boss", ["Spellweaver Volute", "Test Tonic"])),
          PlayerSetup("Bob", cards=mk("Atraxa, Praetors' Voice", ["Test Shock"])),
          PlayerSetup("Carol", cards=mk("Krenko, Mob Boss", ["Test Jolt"]))]
    s = GameSession(enable(new_game(ps, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_volute_three_players_enchants_an_opponents_graveyard_instant_and_casts_the_copy(cards):
    """303.4a: any graveyard. The copy of Bob's Test Shock (cast free by Alice) can hit Carol; Bob's card is exiled; the Aura moves to Carol's graveyard instant (707.10)."""
    s = _three(cards)
    shock, jolt = card_named(s, "Test Shock", "p2"), card_named(s, "Test Jolt", "p3")
    for c in (shock, jolt):
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})
    vol = to_hand(s, "Spellweaver Volute")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=vol.id, targets=[shock.id])
    _drain(s)
    assert s.state.cards[vol.id].zone == "p1:battlefield"
    tonic = to_hand(s, "Test Tonic")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=tonic.id)
    for _ in range(14):
        d = s.state.rules.decision
        if d is not None:
            opts = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o for o in opts if o in ("yes", shock.id, "p3", jolt.id)), opts[0])])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.players["p3"].life == 38 and s.state.players["p2"].life == 40
    assert s.state.cards[shock.id].zone == "p2:exile"
    assert s.state.rules.aura_links[s.state.rules.object_id(vol.id)] == [s.state.rules.object_id(jolt.id)]
    check(s)



def test_the_sea_devils_chapter_three_salamanders_hit_a_creature_of_the_damaged_player(cards):
    """714.2c / 603.7: both Salamanders hurt Bob, each deals that much (2) to his Wall at once; a Bear (not a Salamander) does not trigger it: the Wall has 4 damage."""
    s = build(cards, ["The Sea Devils", "Grizzly Bears"], ["Test Wall"])
    wall, bear = put(s, "Test Wall", "p2"), put(s, "Grizzly Bears")
    s.state.rules.controlled_since[bear.id].turn = 0
    saga = to_hand(s, "The Sea Devils")
    mana(s, U=2, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=saga.id)
    for _ in range(600):
        d = s.state.rules.decision
        if s.state.cards[saga.id].zone == "p1:graveyard" and d is not None and d.kind == "declare_attackers":
            break
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((i for i in ids if i in (wall.id, "p2")), ids[0])])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    else:
        raise AssertionError("no attack step")
    sal = [c for c in s.state.cards.values() if c.name == "Alien Salamander" and c.zone == "p1:battlefield"]
    assert len(sal) == 2
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (*sal, bear)])
    for _ in range(80):
        d = s.state.rules.decision
        if s.state.turn.phase in ("main2", "end") and d is None:
            break
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids if d.kind == "order" else [next((i for i in ids if i == wall.id), ids[0])])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == 40 - 6
    assert s.state.cards[wall.id].damage == 4
    check(s)
