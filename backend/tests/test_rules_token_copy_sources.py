"""Linked exile abilities grant native exact-object play permissions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_linked_aggregates import cast, ch
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = [
    c["name"]
    for c in json.loads((Path(__file__).parent / "fixtures/token_copy_sources_cards.json").read_text())[:14]
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/token_copy_sources_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="lor", number=str(i), **{k: v for k, v in c.items() if k not in ("name", "set_code")}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    support = [
        "Grizzly Bears",
        "Counterspell",
        "Chatterfang, Squirrel General",
        "Peregrin Took",
        "Birthday Escape",
        "Mizzium Skin",
        "Llanowar Elves",
        "Holy Strength",
        "Liquimetal Torque",
        "March of the Machines",
        "Mycosynth Lattice",
        "Cackling Counterpart",
        "Parallel Lives",
        "Doubling Season",
        "Pithing Needle",
        "Murder",
        "Naturalize",
        "Memnite",
        "Clone",
        "Unsummon",
        "Cloudshift",
        "Lightning Bolt",
        "Siege Mastodon",
    ]
    s = table(cards, [name, *support], support, support)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True)
    return s, put(s, name, "hand")


def test_artifact_aura_copy_chooses_native_host_before_creation_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, spell = setup(cards, "Echo Storm")
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield")
    aura = put(s, "Holy Strength", "hand")
    cast(s, aura, targets=[bear.id])
    settle(s)
    torque = put(s, "Liquimetal Torque", "battlefield")
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=torque.id, ability=1, targets=[aura.id])
    settle(s)
    assert "Artifact" in ch(s, aura).types
    cast(s, spell, targets=[aura.id])
    until(s, lambda s: s.state.rules.decision is not None)
    assert "Aura token" in s.state.rules.decision.prompt
    assert not [c for c in s.state.cards.values() if c.is_token]
    s = cold_choose(s, cards, tmp_path, [elf.id])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(":battlefield")]
    assert len(tokens) == 1
    assert tokens[0].attached_to == elf.id
    assert ch(s, tokens[0]).types == frozenset({"Enchantment"})
    assert not ch(s, tokens[0]).is_creature
    roundtrip(s)


def test_mirrorlake_native_token_entry_counter_is_not_copiable(cards):
    s, land = setup(cards, "Littjara Mirrorlake")
    # Put the land on the field for its native sacrifice activation.
    land = put(s, "Littjara Mirrorlake", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    mana(s, G=2, U=1, C=2)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=land.id, ability=2, targets=[bear.id])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(":battlefield")]
    assert len(tokens) == 1
    assert tokens[0].counters.get("+1/+1") == 1
    assert ch(s, tokens[0]).base_pt == (2, 2)
    assert land.zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_canonical_copy_family_is_full(cards, name):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == "FULL", result


def activate(s, source, ability=0, **kwargs):
    mana(s, W=20, U=20, B=20, R=20, G=20, C=20)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability, **kwargs)


def tokens(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(":battlefield")]


def test_mimic_native_death_replaces_pool_then_hasty_copy_and_cleanup(cards):
    s, source = setup(cards, "Mimic Vat")
    source = put(s, "Mimic Vat", "battlefield")
    victims = []
    for name in ["Grizzly Bears", "Llanowar Elves"]:
        victim = put(s, name, "battlefield", "p2")
        victims.append(victim)
        kill = put(s, "Murder", "hand")
        cast(s, kill, targets=[victim.id])
        settle(s)
    assert victims[0].zone == "p2:graveyard"
    assert victims[1].zone == "p2:exile"
    activate(s, source, 1)
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and made[0].name == "Llanowar Elves"
    assert "haste" in ch(s, made[0]).keywords
    to_phase(s, "end", turn=1)
    settle(s)
    assert not tokens(s)
    roundtrip(s)


def test_dino_native_linked_target_copy_recipe_retains_elf_ability(cards):
    s, source = setup(cards, "Dino DNA")
    source = put(s, "Dino DNA", "battlefield")
    victim = put(s, "Llanowar Elves", "graveyard")
    activate(s, source, targets=[victim.id])
    settle(s)
    activate(s, source, 1, targets=[victim.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1
    derived = ch(s, made[0])
    assert derived.pt == (6, 6)
    assert derived.colors == frozenset({"G"})
    assert derived.subtypes == frozenset({"Dinosaur"})
    assert "trample" in derived.keywords
    assert any(a.kind == "mana" for a in derived.abilities)
    roundtrip(s)


def test_cloning_native_three_chapters_share_original_pool(cards):
    from tests.test_rules_linked_aggregates import choose

    s, source = setup(cards, "The Cloning of Shredder")
    victim = put(s, "Grizzly Bears", "graveyard")
    cast(s, source)
    choose(s, [victim.id])
    settle(s)
    assert len(tokens(s)) == 1 and victim.zone == "p1:exile"
    to_phase(s, "main1", turn=4)
    settle(s)
    assert len(tokens(s)) == 2
    to_phase(s, "main1", turn=7)
    settle(s)
    assert len(tokens(s)) == 3
    assert source.zone == "p1:graveyard"
    assert all("Mutant" in ch(s, c).subtypes and "Legendary" not in ch(s, c).supertypes for c in tokens(s))
    roundtrip(s)


def test_mardu_native_copies_attack_each_explicit_opponent_and_sacrifice(cards):
    from tests.test_rules_linked_aggregates import choose

    s, source = setup(cards, "Mardu Siegebreaker")
    victim = put(s, "Grizzly Bears", "battlefield")
    cast(s, source)
    choose(s, [victim.id])
    settle(s)
    assert victim.zone == "p1:exile"
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    settle(s)
    made = tokens(s)
    assert len(made) == 2
    assert {c.attacking.id for c in made} == {"p2", "p3"}
    assert all(c.tapped for c in made)
    to_phase(s, "end", turn=4)
    settle(s)
    assert not tokens(s)
    assert victim.zone == "p1:exile"
    roundtrip(s)


def test_harvester_native_arrival_filter_copy_then_all_other_nightmares(cards):
    s, source = setup(cards, "Abyssal Harvester")
    source = put(s, "Abyssal Harvester", "battlefield")
    to_phase(s, "main1", turn=4)
    old = None
    for name in ["Grizzly Bears", "Llanowar Elves"]:
        victim = put(s, name, "battlefield")
        kill = put(s, "Murder", "hand")
        cast(s, kill, targets=[victim.id])
        settle(s)
        if s.state.cards[source.id].tapped:
            act(s, "p1", type="tap", card_ids=[source.id], tapped=False)
        activate(s, source, targets=[victim.id])
        settle(s)
        made = tokens(s)
        assert len(made) == 1 and made[0].name == name
        assert "Nightmare" in ch(s, made[0]).subtypes
        if old is not None:
            assert old.id not in s.state.cards or not s.state.cards[old.id].zone.endswith(":battlefield")
        old = made[0]
    roundtrip(s)


def test_artisans_native_opponent_entries_replace_exact_old_created_group(cards):
    s, source = setup(cards, "Faerie Artisans")
    put(s, "Faerie Artisans", "battlefield")
    to_phase(s, "main1", turn=2)
    old = None
    for name in ["Grizzly Bears", "Llanowar Elves"]:
        creature = put(s, name, "hand", "p2")
        mana(s, "p2", G=5, C=5)
        wait_priority(s, "p2")
        act(s, "p2", type="cast_spell", card_id=creature.id)
        settle(s)
        made = tokens(s)
        assert len(made) == 1 and made[0].name == name
        assert "Artifact" in ch(s, made[0]).types
        if old is not None:
            assert old.id not in s.state.cards or not s.state.cards[old.id].zone.endswith(":battlefield")
        old = made[0]
    roundtrip(s)


def test_sauron_native_attack_exiles_card_creates_wraith_then_cleanup(cards):
    from tests.test_rules_linked_aggregates import choose

    s, source = setup(cards, "Sauron, the Necromancer")
    source = put(s, "Sauron, the Necromancer", "battlefield")
    victim = put(s, "Llanowar Elves", "graveyard")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    choose(s, [victim.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and victim.zone == "p1:exile"
    assert ch(s, made[0]).pt == (3, 3)
    assert ch(s, made[0]).subtypes == frozenset({"Wraith"})
    assert ch(s, made[0]).colors == frozenset({"B"})
    assert "menace" in ch(s, made[0]).keywords
    assert made[0].tapped and made[0].attacking is not None
    to_phase(s, "end", turn=4)
    settle(s)
    assert not tokens(s)
    roundtrip(s)


def test_separator_native_sacrificed_source_creates_spirit_and_original_stat_zombie(cards):
    s, source = setup(cards, "Soul Separator")
    source = put(s, "Soul Separator", "battlefield")
    victim = put(s, "Siege Mastodon", "graveyard")
    activate(s, source, targets=[victim.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 2 and victim.zone == "p1:exile"
    spirit = next(c for c in made if "Spirit" in ch(s, c).subtypes)
    zombie = next(c for c in made if c.name == "Zombie")
    assert ch(s, spirit).pt == (1, 1) and "flying" in ch(s, spirit).keywords
    assert ch(s, zombie).pt == (3, 5)
    assert source.zone == "p1:graveyard"
    roundtrip(s)


def test_mirror_march_native_recorded_coin_wins_copy_count_and_cleanup(cards, monkeypatch):
    import importlib

    resolve = importlib.import_module("app.game.resolve")
    original = resolve._rng_int
    flips = iter([1, 1, 0])
    monkeypatch.setattr(
        resolve, "_rng_int", lambda rng, lo, hi: next(flips) if (lo, hi) == (0, 1) else original(rng, lo, hi)
    )
    s, source = setup(cards, "Mirror March")
    put(s, "Mirror March", "battlefield")
    creature = put(s, "Grizzly Bears", "hand")
    cast(s, creature)
    settle(s)
    assert len(tokens(s)) == 2
    assert all("haste" in ch(s, c).keywords for c in tokens(s))
    to_phase(s, "end", turn=1)
    settle(s)
    assert not tokens(s)
    roundtrip(s)


def test_hate_native_two_opponent_targets_copy_and_cleanup(cards):
    s, spell = setup(cards, "Hate Mirage")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    elf = put(s, "Llanowar Elves", "battlefield", "p3")
    cast(s, spell, targets=[bear.id, elf.id], target_counts=[2])
    settle(s)
    assert {c.name for c in tokens(s)} == {"Grizzly Bears", "Llanowar Elves"}
    assert all("haste" in ch(s, c).keywords for c in tokens(s))
    to_phase(s, "end", turn=1)
    settle(s)
    assert not tokens(s)
    roundtrip(s)


def test_life_party_native_opponent_creators_and_permanent_goad_no_recursion(cards):
    from app.rules import keyword_actions

    s, source = setup(cards, "Life of the Party")
    cast(s, source)
    settle(s)
    made = tokens(s)
    assert len(made) == 2
    assert {c.controller for c in made} == {"p2", "p3"}
    assert all(keyword_actions.goaded_by(ch(s, c)) == {"p1"} for c in made)
    for turn, pid, defender in [(2, "p2", "p3"), (3, "p3", "p2")]:
        to_phase(s, "declare_attackers", turn=turn)
        attacker = next(c for c in made if c.controller == pid)
        act(s, pid, type="declare_attackers", attackers=[{"card_id": attacker.id, "target": defender}])
    to_phase(s, "main1", turn=4)
    assert all(keyword_actions.goaded_by(ch(s, c)) == {"p1"} for c in made)
    roundtrip(s)


@pytest.mark.parametrize("name", ["Vesuvan Duplimancy", "Orvar, the All-Form"])
def test_cast_target_source_native_copies_before_original_unsummon(cards, name):
    s, source = setup(cards, name)
    put(s, name, "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    spell = put(s, "Unsummon", "hand")
    cast(s, spell, targets=[bear.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and made[0].name == "Grizzly Bears"
    assert bear.zone == "p1:hand"
    assert ch(s, made[0]).pt == (2, 2)
    roundtrip(s)


def test_aura_copy_replacement_order_then_host_choices_both_resume_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, spell = setup(cards, "Echo Storm")
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield")
    aura = put(s, "Holy Strength", "hand")
    cast(s, aura, targets=[bear.id])
    settle(s)
    torque = put(s, "Liquimetal Torque", "battlefield")
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=torque.id, ability=1, targets=[aura.id])
    settle(s)
    put(s, "Parallel Lives", "battlefield")
    put(s, "Peregrin Took", "battlefield")
    cast(s, spell, targets=[aura.id])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume["step"] == "replace_order"
    assert "Aura token" not in d.prompt
    assert not tokens(s)
    s = cold_choose(s, cards, tmp_path, [d.options[0].id])
    until(s, lambda s: s.state.rules.decision is not None)
    while "Aura token" not in s.state.rules.decision.prompt:
        d = s.state.rules.decision
        s = cold_choose(s, cards, tmp_path, [d.options[0].id])
        until(s, lambda s: s.state.rules.decision is not None)
    s = cold_choose(s, cards, tmp_path, [bear.id])
    until(s, lambda s: s.state.rules.decision is not None)
    assert "Aura token" in s.state.rules.decision.prompt
    assert not tokens(s)
    s = cold_choose(s, cards, tmp_path, [elf.id])
    settle(s)
    auras = [c for c in tokens(s) if "Aura" in ch(s, c).subtypes]
    assert len(auras) == 2
    assert {c.attached_to for c in auras} == {bear.id, elf.id}
    assert all(c.owner == "p1" for c in tokens(s))
    roundtrip(s)


@pytest.mark.parametrize("name", ["Vesuvan Duplimancy", "Orvar, the All-Form"])
def test_cast_target_copy_uses_saved_refs_after_spell_is_countered(cards, tmp_path, name):

    s, source = setup(cards, name)
    put(s, name, "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    spell = put(s, "Unsummon", "hand")
    cast(s, spell, targets=[bear.id])
    counter = put(s, "Counterspell", "hand", "p2")
    mana(s, "p2", U=2)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[spell.id])
    settle(s)
    assert spell.zone == "p1:graveyard"
    assert bear.zone == "p1:battlefield"
    assert len(tokens(s)) == 1 and tokens(s)[0].name == "Grizzly Bears"
    roundtrip(s)


def test_artisans_real_animated_aura_dies_before_trigger_then_copies_lki_attached_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, source = setup(cards, "Faerie Artisans")
    put(s, "Faerie Artisans", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    elf = put(s, "Llanowar Elves", "battlefield")
    put(s, "Mycosynth Lattice", "battlefield")
    march = put(s, "March of the Machines", "battlefield")
    to_phase(s, "main1", turn=2)
    aura = put(s, "Holy Strength", "hand", "p2")
    mana(s, "p2", W=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=aura.id, targets=[bear.id])
    until(s, lambda s: s.state.cards[aura.id].zone == "p2:graveyard")
    # Aura creatures cannot stay attached (303.4d); its entering event still
    # triggered Artisans, which will use the dead permanent's copiable LKI.
    removal = put(s, "Naturalize", "hand")
    cast(s, removal, targets=[march.id])
    until(s, lambda s: s.state.rules.decision is not None)
    assert "Aura token" in s.state.rules.decision.prompt
    assert not tokens(s)
    s = cold_choose(s, cards, tmp_path, [elf.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and made[0].attached_to == elf.id
    assert {"Artifact", "Enchantment"} <= ch(s, made[0]).types
    assert "Aura" in ch(s, made[0]).subtypes
    roundtrip(s)


def test_dino_explicit_creature_card_type_replaces_artifact_type(cards):
    s, source = setup(cards, "Dino DNA")
    source = put(s, "Dino DNA", "battlefield")
    victim = put(s, "Memnite", "graveyard")
    activate(s, source, targets=[victim.id])
    settle(s)
    activate(s, source, 1, targets=[victim.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1
    assert ch(s, made[0]).types == frozenset({"Creature"})
    assert ch(s, made[0]).subtypes == frozenset({"Dinosaur"})
    assert ch(s, made[0]).pt == (6, 6) and "trample" in ch(s, made[0]).keywords
    roundtrip(s)


def test_croaking_subtype_only_exception_retains_artifact_type(cards):
    s, source = setup(cards, "Croaking Counterpart")
    victim = put(s, "Memnite", "battlefield")
    cast(s, source, targets=[victim.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1
    assert ch(s, made[0]).types == frozenset({"Artifact", "Creature"})
    assert ch(s, made[0]).subtypes == frozenset({"Frog"})
    assert ch(s, made[0]).pt == (1, 1)
    roundtrip(s)


def test_sauron_subtype_only_exception_retains_artifact_type(cards):
    from tests.test_rules_linked_aggregates import choose

    s, source = setup(cards, "Sauron, the Necromancer")
    source = put(s, "Sauron, the Necromancer", "battlefield")
    victim = put(s, "Memnite", "graveyard")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    choose(s, [victim.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1
    assert ch(s, made[0]).types == frozenset({"Artifact", "Creature"})
    assert ch(s, made[0]).subtypes == frozenset({"Wraith"})
    assert ch(s, made[0]).pt == (3, 3)
    roundtrip(s)
