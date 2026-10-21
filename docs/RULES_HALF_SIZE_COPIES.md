# Copies with half-sized base power and toughness

Saw in Half destroys its target and creates copies only if it died this way. Copies use
the source’s last known recipe and controller, including a token source that ceased to
exist (CR 608.2h, 707.9). Each base power and toughness is half the creature’s last known
value, rounded up separately. Signed arithmetic handles negative power. These exceptions
replace characteristic-defining power/toughness abilities (707.9d).

The controller-copy grammar now accepts multiple tokens and copy exceptions. A narrow
rounding normalization keeps the Oracle’s final rounding sentence with its exception.
The runtime converts that exception into numeric copiable values before making requests
through the existing token replacement machinery.

Twelve focused scenarios passed, covering both players’ creatures, odd and boosted stats,
indestructible, exile instead of dying, negative power, a token source and Tarmogoyf.
Replay and saved-state reloads are checked. All twelve scenarios are included in 128 passing selected regressions. Mypy (341 app files), Ruff
and whitespace checks passed. Catalog promotes exactly Saw in Half: 27,754 FULL / 4,314
PARTIAL, commanders unchanged at 2,949 / 3,501.
