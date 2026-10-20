"""Linked exile abilities grant native exact-object play permissions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = [
    c["name"]
    for c in json.loads((Path(__file__).parent / "fixtures/linked_aggregates_cards.json").read_text())[:12]
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/linked_aggregates_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="lor", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_canonical_cards_are_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    if result.level != "FULL":
        from app.rules import scripts
        from app.rules.coverage import printed_from_data

        data = cards.resolve(name)
        for face in range(len(data.get("faces") or [0])):
            ch = printed_from_data(data, face)
            for a in ch.abilities:
                print("DEBUG", scripts.self_text(a.text, ch.name), scripts.define(a, ch))
    assert result.level == "FULL", [(f.label, f.supported) for f in result.features]


def setup(cards, name, *, hand=False):
    support = [
        "Grizzly Bears",
        "Llanowar Elves",
        "Lightning Bolt",
        "Counterspell",
        "Murder",
        "Naturalize",
        "Memnite",
        "Pull from Eternity",
        "Unsummon",
        "Isamaru, Hound of Konda",
        "Ghalta, Primal Hunger",
        "Tarmogoyf",
        "Tormod's Crypt",
        "Voltaic Key",
        "Deathpact Angel",
        "Plains",
        "Siege Mastodon",
        "Craw Wurm",
        "Colossal Dreadmaw",
    ]
    s = table(cards, [name, *support], support, support)
    for p in ["p1", "p2", "p3"]:
        act(s, p, type="set_prefs", hold_priority=True)
    return s, put(s, name, "hand" if hand else "battlefield")


def choose(s, ids):
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    if d.resume.get("step") == "may":
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        until(s, lambda s: s.state.rules.decision is not None)
        d = s.state.rules.decision
    assert set(ids) <= {o.id for o in d.options}, (d.kind, d.resume, [(o.id, o.label) for o in d.options])
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def cast(s, src, **kw):
    mana(s, W=30, U=30, B=30, R=30, G=30, C=30)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=src.id, **kw)


def activate(s, src, ability=0, **kw):
    mana(s, W=30, U=30, B=30, R=30, G=30, C=30)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=src.id, ability=ability, **kw)


def test_battlement_native_untargeted_batch_pump_and_return(cards):
    from app.rules import sba

    s, src = setup(cards, "Lumbering Battlement", hand=True)
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield")
    cast(s, src)
    choose(s, [bear.id, elf.id])
    settle(s)
    assert bear.zone == "p1:exile" and elf.zone == "p1:exile"
    assert sba.power(src, ch(s, src)) == 8
    assert sba.toughness(src, ch(s, src)) == 9
    removal = put(s, "Unsummon", "hand")
    cast(s, removal, targets=[src.id])
    settle(s)
    assert src.zone == "p1:hand"
    assert bear.zone == elf.zone == "p1:battlefield"


def test_duplicant_native_current_creature_traits_and_departure(cards):
    from app.rules import sba

    s, src = setup(cards, "Duplicant", hand=True)
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    cast(s, src)
    choose(s, [bear.id])
    settle(s)
    assert bear.zone == "p2:exile"
    derived = ch(s, src)
    assert (sba.power(src, derived), sba.toughness(src, derived)) == (2, 2)
    assert {"Bear", "Shapeshifter"} <= derived.subtypes
    pull = put(s, "Pull from Eternity", "hand")
    cast(s, pull, targets=[bear.id])
    settle(s)
    assert ch(s, src).subtypes == frozenset({"Shapeshifter"})
    assert (sba.power(src, ch(s, src)), sba.toughness(src, ch(s, src))) == (2, 4)


@pytest.mark.parametrize("name", ["Cemetery Prowler", "Cemetery Illuminator"])
def test_cemetery_native_nontargeted_graveyard_choice(cards, name):
    s, src = setup(cards, name, hand=True)
    bear = put(s, "Grizzly Bears", "graveyard", "p2")
    cast(s, src)
    choose(s, [bear.id])
    settle(s)
    assert bear.zone == "p2:exile"
    assert s.state.rules.exiled_with[s.state.rules.object_id(src.id)] == [s.state.rules.object_id(bear.id)]
    roundtrip(s)
    if name == "Cemetery Prowler":
        hand = put(s, "Grizzly Bears", "hand")
        mana(s, G=1, C=0)
        wait_priority(s, "p1")
        act(s, "p1", type="cast_spell", card_id=hand.id)
        settle(s)
        assert hand.zone == "p1:battlefield"
    else:
        hand = put(s, "Grizzly Bears", "library")
        # Native top permission uses actual current linked types and ordinary cost.
        s.state.zones["p1:library"].remove(hand.id)
        s.state.zones["p1:library"].insert(0, hand.id)
        mana(s, G=1, C=1)
        wait_priority(s, "p1")
        act(s, "p1", type="cast_spell", card_id=hand.id)
        settle(s)
        assert hand.zone == "p1:battlefield"


def test_funeral_native_two_target_max_and_legendary_reduction(cards):
    s, src = setup(cards, "The Kenriths' Royal Funeral", hand=True)
    dog = put(s, "Isamaru, Hound of Konda", "graveyard")
    angel = put(s, "Ghalta, Primal Hunger", "graveyard")
    before = s.state.players["p1"].life
    n = len(s.state.zones["p1:hand"])
    cast(s, src)
    choose(s, [dog.id, angel.id])
    settle(s)
    assert dog.zone == angel.zone == "p1:exile"
    assert s.state.players["p1"].life == before - 12
    assert len(s.state.zones["p1:hand"]) == n - 1 + 12


def ch(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def test_profane_native_third_exile_transforms_and_same_pool_retrieval(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, src = setup(cards, "Profane Procession // Tomb of the Dusk Rose")
    victims = [put(s, n, "battlefield", "p2") for n in ["Grizzly Bears", "Llanowar Elves", "Memnite"]]
    original = s.state.rules.object_id(src.id)
    for victim in victims:
        activate(s, src, 0, targets=[victim.id])
        settle(s)
    assert s.state.cards[src.id].face == 1
    assert s.state.rules.object_id(src.id) == original
    activate(s, src, 1)
    until(s, lambda s: s.state.rules.decision is not None)
    s = cold_choose(s, cards, tmp_path, [victims[0].id])
    settle(s)
    assert s.state.cards[victims[0].id].zone == "p1:battlefield"
    assert s.state.cards[victims[0].id].owner == "p2"
    assert len(s.state.rules.exiled_with[original]) == 3  # stale historical refs are filtered by queries


def test_gateway_native_five_distinct_mana_values_transform(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, src = setup(cards, "Azor's Gateway // Sanctum of the Sun")
    victims = [
        put(s, n, "hand") for n in ["Memnite", "Llanowar Elves", "Grizzly Bears", "Murder", "Deathpact Angel"]
    ]
    before = s.state.players["p1"].life
    for index, victim in enumerate(victims):
        src.tapped = False
        activate(s, src)
        until(s, lambda s: s.state.rules.decision is not None)
        if index == 4:
            s = cold_choose(s, cards, tmp_path, [victim.id])
            src = s.state.cards[src.id]
        else:
            choose(s, [victim.id])
        settle(s)
    assert s.state.cards[src.id].face == 1
    assert s.state.players["p1"].life == before + 5
    assert not s.state.cards[src.id].tapped


def test_redemptor_native_printed_optional_exile_and_attack_pump(cards):
    from app.rules import sba

    s, src = setup(cards, "Redemptor Dreadnought", hand=True)
    angel = put(s, "Deathpact Angel", "graveyard")
    cast(s, src, optional_costs=[src.id + ":exile"], cost_choices=[{"component": 0, "cards": [angel.id]}])
    settle(s)
    assert angel.zone == "p1:exile"
    assert s.state.rules.exiled_with[s.state.rules.object_id(src.id)] == [s.state.rules.object_id(angel.id)]
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": src.id, "target": "p2"}])
    settle(s)
    assert sba.power(src, ch(s, src)) == 9
    assert sba.toughness(src, ch(s, src)) == 9


@pytest.mark.parametrize("departed", [False, True])
def test_urn_native_death_pool_mandatory_return_requires_sacrifice(cards, departed):
    s, src = setup(cards, "Colfenor's Urn")
    for name in ["Siege Mastodon", "Craw Wurm", "Colossal Dreadmaw"]:
        victim = put(s, name, "battlefield")
        kill = put(s, "Murder", "hand")
        cast(s, kill, targets=[victim.id])
        settle(s)
        assert victim.zone == "p1:exile"
    to_phase(s, "end", turn=1)
    if departed:
        # End-step trigger already exists; removing its source cannot satisfy
        # the mandatory sacrifice payment of that resolving trigger.
        kill = put(s, "Naturalize", "hand", "p2")
        mana(s, "p2", G=1, C=1)
        wait_priority(s, "p2")
        act(s, "p2", type="cast_spell", card_id=kill.id, targets=[src.id])
    settle(s)
    zone = "p1:exile" if departed else "p1:battlefield"
    assert all(
        next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == name).zone == zone
        for name in ["Siege Mastodon", "Craw Wurm", "Colossal Dreadmaw"]
    )
    assert src.zone == "p1:graveyard"


def test_portal_native_four_exiles_losing_coin_returns_random_owner_hand(cards, monkeypatch):
    import importlib

    resolve = importlib.import_module("app.game.resolve")
    original = resolve._rng_int
    monkeypatch.setattr(
        resolve, "_rng_int", lambda rng, lo, hi: 0 if (lo, hi) == (0, 1) else original(rng, lo, hi)
    )
    s, src = setup(cards, "Negative Zone Portal")
    victims = [
        put(s, n, "graveyard", "p2") for n in ["Grizzly Bears", "Llanowar Elves", "Memnite", "Tarmogoyf"]
    ]
    for victim in victims:
        src.tapped = False
        activate(s, src, targets=[victim.id])
        settle(s)
    assert len(s.state.rules.exiled_with[s.state.rules.object_id(src.id)]) == 4
    to_phase(s, "upkeep", turn=4)
    settle(s)
    assert src.zone == "p1:graveyard"
    assert sum(s.state.cards[c.id].zone == "p2:hand" for c in victims) == 1
    assert sum(s.state.cards[c.id].zone == "p2:exile" for c in victims) == 3
    roundtrip(s)


@pytest.mark.parametrize("accept", [False, True])
def test_diary_native_from_hand_resolution_exile_and_random_freecast(cards, tmp_path, accept):
    from tests.test_rules_linked_return_family import cold_choose

    s, src = setup(cards, "River Song's Diary")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    elf = put(s, "Llanowar Elves", "battlefield", "p2")
    memnite = put(s, "Memnite", "battlefield", "p2")
    spells = []
    for name, target in [
        ("Lightning Bolt", "p2"),
        ("Unsummon", bear.id),
        ("Naturalize", memnite.id),
        ("Murder", elf.id),
    ]:
        spell = put(s, name, "hand")
        spells.append(spell)
        cast(s, spell, targets=[target])
        settle(s)
        assert spell.zone == "p1:exile"
    assert len(s.state.rules.exiled_with[s.state.rules.object_id(src.id)]) == 4
    put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "upkeep", turn=4)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume["step"] == "suspend_cast"
    s = cold_choose(s, cards, tmp_path, ["yes" if accept else "no"])
    settle(s)
    assert sum(s.state.cards[c.id].zone == "p1:exile" for c in spells) == (3 if accept else 4)
    roundtrip(s)


def test_hostel_native_soul_transform_then_creeping_inn_link_count(cards):
    s, src = setup(cards, "Hostile Hostel // Creeping Inn")
    victims = [put(s, n, "battlefield") for n in ["Grizzly Bears", "Llanowar Elves", "Memnite"]]
    for victim in victims:
        src.tapped = False
        activate(s, src, 1, cost_choices=[{"component": 2, "cards": [victim.id]}])
        settle(s)
    assert s.state.cards[src.id].face == 1
    assert not src.counters.get("soul", 0)
    before = [s.state.players[p].life for p in ["p1", "p2", "p3"]]
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": src.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None)
    choose(s, ["pay"])
    until(s, lambda s: s.state.rules.decision is not None)
    choose(s, [victims[0].id])
    settle(s)
    assert s.state.cards[victims[0].id].zone == "p1:exile"
    assert [s.state.players[p].life for p in ["p1", "p2", "p3"]] == [
        before[0] + 1,
        before[1] - 1,
        before[2] - 1,
    ]


def test_linked_pool_does_not_reattribute_departed_reexiled_physical_card(cards):
    from app.rules import linked_aggregates
    from app.rules.plan import Plan

    s, src = setup(cards, "Cemetery Prowler", hand=True)
    bear = put(s, "Grizzly Bears", "graveyard", "p2")
    cast(s, src)
    choose(s, [bear.id])
    settle(s)
    old = s.state.rules.object_id(bear.id)
    pull = put(s, "Pull from Eternity", "hand")
    cast(s, pull, targets=[bear.id])
    settle(s)
    crypt = put(s, "Tormod's Crypt", "battlefield")
    activate(s, crypt, targets=["p2"])
    settle(s)
    assert s.state.cards[bear.id].zone == "p2:exile"
    assert s.state.rules.object_id(bear.id) != old
    plan = Plan(s.state, "p1", s.cards, None)
    ctx = linked_aggregates.source_context(plan, src, {})
    assert linked_aggregates.aggregate(plan, ctx, {"projection": "count"}) == 0
    roundtrip(s)


def test_premature_battlement_departure_never_exiles_chosen_creatures(cards):
    s, src = setup(cards, "Lumbering Battlement", hand=True)
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, src)
    until(s, lambda s: s.state.cards[src.id].zone == "p1:battlefield")
    unsummon = put(s, "Unsummon", "hand", "p2")
    mana(s, "p2", U=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=unsummon.id, targets=[src.id])
    settle(s)
    assert bear.zone == "p1:battlefield"
    assert src.zone == "p1:hand"


def test_duplicant_native_cda_tracks_exiled_creatures_current_characteristics(cards):
    from app.rules import sba

    s, src = setup(cards, "Duplicant", hand=True)
    target = put(s, "Tarmogoyf", "battlefield", "p2")
    put(s, "Lightning Bolt", "graveyard")
    cast(s, src)
    choose(s, [target.id])
    settle(s)
    assert sba.power(src, ch(s, src)) == 1
    assert sba.toughness(src, ch(s, src)) == 2
    put(s, "Grizzly Bears", "graveyard")
    assert sba.power(src, ch(s, src)) == 2
    assert sba.toughness(src, ch(s, src)) == 3
    assert {"Lhurgoyf", "Shapeshifter"} <= ch(s, src).subtypes
    roundtrip(s)


@pytest.mark.parametrize("countered", [False, True])
def test_diary_opponents_hand_spell_preserves_owner_and_countered_spell_not_exiled(cards, countered):
    s, src = setup(cards, "River Song's Diary")
    bolt = put(s, "Lightning Bolt", "hand", "p2")
    mana(s, "p2", R=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p3"])
    original = s.state.rules.object_id(bolt.id)
    until(s, lambda s: original in s.state.rules.exile_resolves)
    if countered:
        counter = put(s, "Counterspell", "hand")
        cast(s, counter, targets=[bolt.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == ("p2:graveyard" if countered else "p2:exile")
    pool = s.state.rules.exiled_with.get(s.state.rules.object_id(src.id), [])
    assert (s.state.rules.object_id(bolt.id) in pool) == (not countered)
    roundtrip(s)
