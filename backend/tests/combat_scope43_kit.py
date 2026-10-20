"""Canonical combat-player trigger and compatibility fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ('life_total_damage43_cards.json','named_control_recipient_cards.json','combat_player_scope43_cards.json'):
        for i, row in enumerate(json.loads((Path(__file__).parent/'fixtures'/filename).read_text())):
            base[row['name']]=card(row['name'],number=str(i),**{k:v for k,v in row.items() if k!='name'})
    settings.ensure_dirs()
    build_database(base.values(),settings.cards_db_path)
    repo=CardRepository(settings.cards_db_path,ImageStore(settings.images_dir))
    yield repo
    repo.close()
