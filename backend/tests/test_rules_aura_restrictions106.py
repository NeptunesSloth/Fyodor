from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import pick, put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase as phase_until
from tests.test_rules_wave30p_combat import attack, block

DATA = json.loads((Path(__file__).parent / "fixtures/aura_restrictions106_cards.json").read_text())
NAMES = ["Artifact Ward", "Anti-Magic Aura", "Consecrate Land"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="cmd95", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup95(cards):
    names = list(
        dict.fromkeys(
            [c["name"] for c in DATA]
            + [
                "Grizzly Bears",
                "Llanowar Elves",
                "Sol Ring",
                "Cloudshift",
                "Murder",
                "Counterspell",
                "Holy Strength",
                "Giant Growth",
                "Wrath of God",
                "Lightning Bolt",
                "Forest",
            ]
        )
    )
    s = table(cards, names, names, names)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", full_control=True, hold_priority=True)
    return s


def to_phase(s, phase, turn=None):
    phase_until(s, phase, turn=turn)
    if phase in ("declare_attackers", "declare_blockers"):
        for _ in range(12):
            d = s.state.rules.decision
            if d is not None or s.state.turn.phase != phase:
                break
            act(s, s.state.rules.priority, type="pass_priority")


def start(s, turn=4):
    to_phase(s, "main1", turn=turn)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", full_control=True, hold_priority=True)


def combat95(s, attackers, blockers=()):
    to_phase(s, "declare_attackers", turn=4)
    attack(s, *[(c, "p2") for c in attackers])
    to_phase(s, "declare_blockers", turn=4)
    if s.state.rules.decision and s.state.rules.decision.kind == "declare_blockers":
        block(s, "p2", *blockers)
    else:
        assert not blockers
    to_phase(s, "main2", turn=4)


def cast95(s, name, targets=(), pid="p1", **extra):
    source = put(s, name, "hand", pid=pid)
    wait_priority(s, pid)
    mana(s, pid=pid, C=20, W=20, U=20, B=20, R=20, G=20)
    act(s, pid, type="cast_spell", card_id=source.id, targets=list(targets), **extra)
    settle(s)
    return source


@pytest.mark.parametrize("name", NAMES)
def test_whole106(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pair106(cards, name, old_aura=False):
    s = setup95(cards)
    host = put(s, "Forest" if name == NAMES[2] else "Grizzly Bears", "battlefield")
    rod = put(s, "Rod of Ruin", "battlefield")
    sorcerer = put(s, "Prodigal Sorcerer", "battlefield")
    coating = put(s, "Liquimetal Coating", "battlefield")
    bow = put(s, "Viridian Longbow", "battlefield")
    start(s)
    old = None
    if old_aura:
        old = cast95(s, "Wild Growth" if name == NAMES[2] else "Holy Strength", [host.id])
    aura = cast95(s, name, [host.id])
    return s, aura, host, rod, sorcerer, coating, bow, old


def activate106(s, source, needle, target):
    from tests.test_rules_wave30m_durations import chars

    # The newest matching ability is the Longbow grant when the host also has
    # an intrinsic ping ability. Its source remains the equipped creature.
    index = max(a.index for a in chars(s, source).abilities if needle in a.text)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index, targets=[target.id])


def test_artifact_source_ability_rejected_before_cost106(cards):
    s, aura, host, rod, *_ = pair106(cards, NAMES[0])
    mana(s, C=3)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        activate106(s, rod, "deals 1 damage", host)
    assert s.state.model_dump_json() == before


def test_ability_granted_by_artifact_has_creature_source106(cards):
    s, aura, host, rod, sorcerer, coating, bow, _ = pair106(cards, NAMES[0])
    act(s, "p1", type="attach", card_ids=[bow.id], to=sorcerer.id)
    activate106(s, sorcerer, "deals 1 damage", host)
    settle(s)
    assert s.state.cards[host.id].damage == 1


def test_source_becoming_artifact_changes_target_legality106(cards):
    from app.rules import targets
    from app.rules.plan import Plan

    s, aura, host, rod, sorcerer, coating, bow, _ = pair106(cards, NAMES[0])
    activate106(s, sorcerer, "deals 1 damage", host)
    activate106(s, coating, "becomes an artifact", sorcerer)
    # Resolve the newest ability only, preserving the lower damage ability.
    for _ in range(12):
        if (
            s.state.cards[coating.id].tapped
            and "Artifact" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[sorcerer.id]).types
        ):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    p = Plan(s.state, "p1", s.cards, None)
    assert "Artifact" in p.ch(p.state.cards[sorcerer.id]).types
    assert not targets.can_target(
        p, "p1", p.state.cards[host.id], p.ch(p.state.cards[host.id]), targets.source_of(p, sorcerer.id)
    )
    settle(s)
    assert s.state.cards[host.id].damage == 0


def test_anti_magic_rejects_spells_but_allows_creature_abilities106(cards):
    s, aura, host, rod, sorcerer, *_ = pair106(cards, NAMES[1])
    growth = put(s, "Giant Growth", "hand")
    mana(s, G=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=growth.id, targets=[host.id])
    assert s.state.model_dump_json() == before
    activate106(s, sorcerer, "deals 1 damage", host)
    settle(s)
    assert s.state.cards[host.id].damage == 1


@pytest.mark.parametrize("name", NAMES[1:])
def test_own_aura_remains_other_existing_aura_falls_off106(cards, name):
    s, aura, host, rod, sorcerer, coating, bow, old = pair106(cards, name, old_aura=True)
    assert s.state.cards[aura.id].zone == "p1:battlefield"
    assert s.state.cards[aura.id].attached_to == host.id
    assert s.state.cards[old.id].zone == "p1:graveyard"


def test_consecrate_land_allows_destroy_spell_but_grants_indestructible106(cards):
    s, aura, host, *_ = pair106(cards, NAMES[2])
    spell = cast95(s, "Stone Rain", [host.id])
    assert s.state.cards[spell.id].zone == "p1:graveyard"
    assert s.state.cards[host.id].zone == "p1:battlefield"


def test_consecrate_land_rejects_other_aura_spell106(cards):
    s, aura, host, *_ = pair106(cards, NAMES[2])
    spell = put(s, "Wild Growth", "hand")
    mana(s, G=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[host.id])
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize("name", NAMES[1:])
def test_nontargeted_aura_entry_cannot_choose_protected_host106(cards, name):
    s, aura, host, *_ = pair106(cards, name)
    incoming = put(s, "Wild Growth" if name == NAMES[2] else "Holy Strength", "graveyard")
    # The other creature available to a creature Aura is a legal nonprotected choice;
    # land Aura has no alternative land on the battlefield.
    cast95(s, "Replenish")
    d = s.state.rules.decision
    if d is not None:
        assert host.id not in {o.id for o in d.options} | {o.card_id for o in d.options}
        pick(s, [o.id for o in d.options][: d.min_choices])
        settle(s)
    assert s.state.cards[aura.id].attached_to == host.id
    assert s.state.cards[incoming.id].attached_to != host.id


def cold95(s, tmp_path, body):
    import subprocess
    import sys

    import app

    saved = tmp_path / "combat95.json"
    saved.write_text(s.state.model_dump_json())
    code = (
        """import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import pick
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
"""
        + body
        + "\nrepo.close()\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(s.cards.db_path)],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", NAMES[1:])
def test_genuine_cold_static_aura_legality106(cards, name, tmp_path):
    s, aura, host, *_ = pair106(cards, name)
    spell = put(s, "Wild Growth" if name == NAMES[2] else "Giant Growth", "hand")
    mana(s, G=2)
    body = "from app.game.errors import ActionError\nbefore=s.state.model_dump_json()\ntry:\n"
    body += f"    act(s,'p1',type='cast_spell',card_id={spell.id!r},targets=[{host.id!r}])\n"
    body += "except ActionError:\n    pass\nelse:\n    raise AssertionError('illegal spell target accepted after cold load')\nassert s.state.model_dump_json()==before"
    cold95(s, tmp_path, body)
