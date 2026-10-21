# Conditional casting after a private search

Beseech the Mirror searches and exiles a card face down, then permits an optional free
cast only when bargained and within its mana-value limit. A card not cast returns to hand,
including a card whose cast was cancelled at target selection. The chosen card remains
private until casting makes it public. Ineligible cards still show a private empty casting
choice, preserving the existing hidden-information policy. Bargain’s sacrifice remains paid
when Beseech is countered (CR 702.166, 601.2, 608.2g).

A typed sequence uses the existing search, cast-condition, optional cast and return
primitives. Its search-object reference and cast-success binding survive private decisions,
save/load and replay. Ten focused scenarios are included in 87 passing selected regressions;
mypy (343 app files), Ruff and whitespace checks passed. The catalog promotes only Beseech: 27,756 FULL / 4,312 PARTIAL.
