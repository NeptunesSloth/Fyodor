# Conditional tutors: Demonic Counsel

Oracle text checked against Scryfall's current named-card endpoint on 2026-10-19:
https://api.scryfall.com/cards/named?exact=Demonic%20Counsel

The delirium sentence replaces the complete preceding search instruction. Existing
conditional branch assembly already evaluates the condition before either search;
the missing grammar was the singular phrase "any card". It now uses the same
unrestricted, mandatory one-card search as "a card", including the existing shuffle.
This extension accepts "any card" specifically, without treating "any" as "up to".

Rules checked in the stored 2026-09-25 Comprehensive Rules:

- 205.2a: card types, including artifact and creature on the same card; basic is a
  supertype and contributes no extra card type.
- 608.2c: follow instructions in order; evaluate this condition during resolution.
- 701.23b: a search of a hidden zone for a stated quality may fail to find.
- 701.23d: an unrestricted search for a quantity must find that quantity if available.

Five gameplay cases cover both branches, a Bolt cast in response enabling delirium,
the ability to fail a Demon search, mandatory unrestricted selection, opponent view
privacy, replay, and save/load. Canonical printing metadata is kept in the fixture.
