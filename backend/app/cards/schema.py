"""Schema of the card database (``cards.sqlite``). Rebuilt wholesale by the importer."""

from __future__ import annotations

CARD_DB_VERSION = 1

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE printings (
    id TEXT PRIMARY KEY,
    oracle_id TEXT NOT NULL,
    name TEXT NOT NULL,
    lang TEXT NOT NULL,
    layout TEXT NOT NULL,
    set_code TEXT NOT NULL,
    set_name TEXT NOT NULL,
    set_type TEXT NOT NULL,
    collector_number TEXT NOT NULL,
    released_at TEXT,
    rarity TEXT,
    mana_cost TEXT,
    cmc REAL,
    type_line TEXT,
    oracle_text TEXT,
    power TEXT,
    toughness TEXT,
    loyalty TEXT,
    defense TEXT,
    colors TEXT NOT NULL,          -- JSON list
    color_identity TEXT NOT NULL,  -- JSON list
    keywords TEXT NOT NULL,        -- JSON list
    produced_mana TEXT,            -- JSON list or NULL
    card_faces TEXT,               -- JSON list of trimmed faces or NULL
    all_parts TEXT,                -- JSON list of related objects or NULL
    image_uris TEXT,               -- JSON {size: url} for single-faced cards
    legalities TEXT,               -- JSON {format: status}
    is_token INTEGER NOT NULL,
    digital INTEGER NOT NULL,
    promo INTEGER NOT NULL,
    artist TEXT,
    edhrec_rank INTEGER
);
CREATE INDEX printings_oracle ON printings(oracle_id);
CREATE INDEX printings_set ON printings(set_code, collector_number);

CREATE TABLE oracle_defaults (
    oracle_id TEXT PRIMARY KEY,
    printing_id TEXT NOT NULL REFERENCES printings(id),
    name TEXT NOT NULL,
    is_token INTEGER NOT NULL
);

CREATE TABLE card_names (
    name_norm TEXT NOT NULL,
    oracle_id TEXT NOT NULL,
    is_token INTEGER NOT NULL,
    PRIMARY KEY (name_norm, oracle_id)
) WITHOUT ROWID;

CREATE VIRTUAL TABLE oracle_fts USING fts5(
    name, type_line, oracle_text,
    tokenize = "unicode61 remove_diacritics 2"
);
"""
