"""Wave 110G session 14: Drain Power (605.3a, 106.4 lost mana, 106.3 added); Spellweaver Volute with three players (303.4a, 707.10)."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
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
    real("Urgent Necropsy", "{2}{B}{G}", 4, "Instant", "As an additional cost to cast this spell, collect evidence X, where X is the total mana value of the permanents this spell targets.\nDestroy up to one target artifact, up to one target creature, up to one target enchantment, and up to one target planeswalker.", None, "BG"),
    real("Next of Kin", "{2}{G}", 3, "Enchantment \u2014 Aura", "Enchant creature\nWhen enchanted creature dies, you may put a creature card you own with lesser mana value from your hand or from the command zone onto the battlefield. If you do, return this card to the battlefield attached to that creature at the beginning of the next end step.", None, "G"),
    real("Test Big", "{4}{G}", 5, "Creature \u2014 Beast", "", ("1", "1"), "G"),
    real("Test Elf", "{G}", 1, "Creature \u2014 Elf", "", ("1", "1"), "G"),
    real("Test Giant", "{2}{G}", 3, "Creature \u2014 Giant", "", ("3", "3"), "G"),
    real("Test Small", "{G}", 1, "Creature \u2014 Beast", "", ("1", "1"), "G"),
    real("Storm Herald", "{2}{R}", 3, "Creature \u2014 Human Shaman", "Haste\nWhen this creature enters, return any number of Aura cards from your graveyard to the battlefield attached to creatures you control. Exile those Auras at the beginning of your next end step. If those Auras would leave the battlefield, exile them instead of putting them anywhere else.", ("3", "2"), "R"),
    real("Test Boon", "{G}", 1, "Enchantment \u2014 Aura", "Enchant creature\nEnchanted creature gets +1/+1.", None, "G"),
    real("Test Fertile", "{G}", 1, "Enchantment \u2014 Aura", "Enchant land\nEnchanted land has \"{T}: Add {G}.\"", None, "G"),
    real("The Face of Boe", "{1}{U}{R}{W}", 4, "Legendary Creature \u2014 Alien Advisor", "{T}: You may cast a spell with suspend from your hand. If you do, pay its suspend cost rather than its mana cost. Activate only as a sorcery.", ("0", "4"), "URW"),
    real("Rift Bolt", "{2}{R}", 3, "Sorcery", "Rift Bolt deals 3 damage to any target.\nSuspend 1\u2014{R} (Rather than cast this card from your hand, you may pay {R} and exile it with a time counter on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its mana cost.)", None, "R"),
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


def _boe(cards, pick, pool):
    s = build(cards, ["The Face of Boe", "Rift Bolt", "Test Tonic"], [])
    boe = put(s, "The Face of Boe")
    s.state.rules.controlled_since[boe.id].turn = 0
    to_hand(s, "Rift Bolt"), to_hand(s, "Test Tonic")
    mana(s, **pool)
    act(s, "p1", type="activate_ability", card_id=boe.id, ability=0)
    return s, boe


def _finish(s, pick):
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((i for i in ids if i in pick), ids[0])])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_face_of_boe_casts_rift_bolt_for_its_suspend_cost(cards):
    """118.9 / 702.62a: only the card with suspend is offered (Test Tonic is not); Rift Bolt is cast for {R} (not {2}{R}) and hits Bob for 3."""
    s, boe = _boe(cards, "x", {"R": 1})
    d = s.state.rules.decision
    names = sorted(s.state.cards[o.id].name for o in d.options if o.id != "no")
    assert names == ["Rift Bolt"]
    _finish(s, ("p2", card_named(s, "Rift Bolt").id))
    assert s.state.players["p2"].life == 37
    assert s.state.cards[boe.id].tapped
    check(s)


def test_face_of_boe_can_decline(cards):
    s, boe = _boe(cards, "x", {"R": 1})
    _finish(s, ("no",))
    assert s.state.players["p2"].life == 40 and s.state.cards[card_named(s, "Rift Bolt").id].zone == "p1:hand"
    check(s)


def _herald(cards, take):
    s = build(cards, ["Storm Herald", "Test Boon", "Test Fertile", "Grizzly Bears"], [])
    bear = put(s, "Grizzly Bears")
    for n in ("Test Boon", "Test Fertile"):
        c = card_named(s, n)
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    herald = to_hand(s, "Storm Herald")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=herald.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        ids = [o.id for o in d.options]
        if d.kind == "choose_cards" and s.state.cards[ids[0]].name.startswith("Test"):
            pick = [i for i in ids if s.state.cards[i].name in take]
        else:
            pick = [bear.id] if bear.id in ids else ids[:1]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    return s, bear


def test_storm_herald_returns_the_chosen_creature_aura_and_exiles_it_at_the_end_step(cards):
    """303.4f: the Enchant land Aura can't be attached to a creature and stays; the Boon enchants the Bear, then is exiled at the next end step (603.7)."""
    s, bear = _herald(cards, {"Test Boon", "Test Fertile"})
    boon, fertile = card_named(s, "Test Boon"), card_named(s, "Test Fertile")
    assert s.state.cards[boon.id].zone == "p1:battlefield" and s.state.cards[fertile.id].zone == "p1:graveyard"
    for _ in range(120):
        if s.state.cards[boon.id].zone != "p1:battlefield":
            break
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[boon.id].zone == "p1:exile"
    check(s)


def test_storm_herald_aura_that_would_leave_is_exiled_instead_and_none_is_fine(cards):
    s, bear = _herald(cards, {"Test Boon"})
    boon = card_named(s, "Test Boon")
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="pass_priority")  # 704.5m: the unattached Aura is put into the graveyard as a state-based action, here exile instead
    assert s.state.cards[boon.id].zone == "p1:exile"  # 614.1a, never the graveyard
    check(s)
    s2, _ = _herald(cards, set())
    assert s2.state.cards[card_named(s2, "Test Boon").id].zone == "p1:graveyard"


def _kin(cards, big=True):
    """Alice's Next of Kin enchants her 1/1 (mana value 5, or 1) and Test Shock kills it; returns the table after the "may" and the creature choice."""
    s = build(cards, ["Next of Kin", "Test Big" if big else "Test Small", "Test Shock", "Test Elf", "Test Giant"], [])
    victim = put(s, "Test Big" if big else "Test Small")
    kin = to_hand(s, "Next of Kin")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=kin.id, targets=[victim.id])
    _drain(s)
    to_hand(s, "Test Elf"), to_hand(s, "Test Giant")
    shock = to_hand(s, "Test Shock")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=[victim.id])
    return s, kin, victim


def test_next_of_kin_offers_hand_and_command_zone_and_returns_attached_at_end_step(cards):
    """Lesser mana value (5): Elves, Test Giant and the commander (Krenko, 4) are offered; Krenko is put in from the command zone and at the end step the Aura returns on it."""
    s, kin, victim = _kin(cards)
    seen = []
    for _ in range(200):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            seen = [s.state.cards[o.id].name for o in d.options]
            krenko = next(o.id for o in d.options if s.state.cards[o.id].name == "Krenko, Mob Boss")
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[krenko])
        elif d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if "yes" in [o.id for o in d.options] else [d.options[0].id])
        elif s.state.cards[kin.id].zone == "p1:battlefield" and seen:
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert sorted(seen) == ["Krenko, Mob Boss", "Test Elf", "Test Giant"]
    krenko = card_named(s, "Krenko, Mob Boss")
    assert s.state.cards[krenko.id].zone == "p1:battlefield" and s.state.cards[kin.id].attached_to == krenko.id
    check(s)


def test_next_of_kin_nothing_cheaper_means_no_card_and_no_aura_return(cards):
    """Mana value 1: nothing in hand or the command zone is lesser: nothing is put, so the Aura stays in the graveyard."""
    s, kin, victim = _kin(cards, big=False)
    for _ in range(120):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["no"] if "no" in [o.id for o in d.options] else [])  # (the hand holds cards: asked, nothing to pick)
        elif s.state.turn.number >= 2:
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[kin.id].zone == "p1:graveyard"
    assert s.state.cards[card_named(s, "Krenko, Mob Boss").id].zone != "p1:battlefield"
    check(s)


def _necropsy(cards, in_graveyard):
    s = build(cards, ["Urgent Necropsy", *in_graveyard], ["Test Giant"])
    giant = put(s, "Test Giant", "p2")
    for n in in_graveyard:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    nec = to_hand(s, "Urgent Necropsy")
    mana(s, B=1, G=1, C=2)
    return s, nec, giant


def test_urgent_necropsy_evidence_is_the_total_mana_value_of_its_targets(cards):
    """701.59a / 601.2b: the Giant (mana value 3) needs evidence 3: two 1-mana cards are not enough; adding a 5-mana card is, and only the chosen cards are exiled."""
    s, nec, giant = _necropsy(cards, ["Test Elf", "Test Small"])
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=nec.id, targets=[giant.id], target_counts=[0, 1, 0, 0])
    s, nec, giant = _necropsy(cards, ["Test Elf", "Test Small", "Test Big"])
    act(s, "p1", type="cast_spell", card_id=nec.id, targets=[giant.id], target_counts=[0, 1, 0, 0])
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    big = card_named(s, "Test Big")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[big.id])
    _drain(s)
    assert s.state.cards[big.id].zone == "p1:exile" and s.state.cards[card_named(s, "Test Elf").id].zone == "p1:graveyard"
    assert s.state.cards[giant.id].zone == "p2:graveyard"
    check(s)


def test_urgent_necropsy_without_targets_costs_no_evidence(cards):
    """X is 0 with no targets: nothing to exile, nothing in the graveyard needed."""
    s, nec, giant = _necropsy(cards, [])
    act(s, "p1", type="cast_spell", card_id=nec.id, targets=[], target_counts=[0, 0, 0, 0])
    _drain(s)
    assert s.state.cards[giant.id].zone == "p2:battlefield"
    check(s)
