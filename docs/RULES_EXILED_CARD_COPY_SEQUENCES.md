# Exiled-card copies and optional casts

Mizzix’s Mastery’s normal and overloaded text normalize into the existing exile,
copy-card, optional free-cast, and self-exile instructions (CR 702.96, 707.12, 608.2g).
The normal version binds its one exiled card; overload binds all instant and sorcery
cards in its controller’s graveyard. Copies may be cast in the player’s chosen order;
uncast copies cease to exist. Originals remain exiled. The overloaded version needs
no targets; a normal version with no legal target does not resolve or exile itself.

Eight real Oracle scenarios, including normal/overloaded costs, zero/one/all casts,
chosen order, filtering, empty graveyard, departed target, replay and saved-state reloads,
are included in 112 passing selected regressions. Mypy (342 app files), Ruff and whitespace
checks passed. Exactly Mizzix’s Mastery is promoted: 27,755 FULL / 4,313 PARTIAL, commanders
unchanged at 2,949 / 3,501.
