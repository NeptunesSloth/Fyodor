# The targeted ability's controller pays

Ayesha Tanaka uses the existing optional payment and counter primitives. The “that ability's
controller” wording binds only a single activated or triggered ability target on the stack.
It does not bind an artifact permanent or an unrelated spell. The existing source selector
requires an artifact source; mana abilities never become targetable stack objects.

The targeted ability has its own controller (CR 113.7a). Its source leaving or returning
as a different permanent does not change who receives the optional payment. The normal
payment window applies (CR 118.12a), and an unaffordable cost is declined without a prompt.
The already-activated ability survives only if its controller pays.

Twelve focused scenarios verify pay/decline/unavailable payments, departed and returned
sources, rejection of nonartifact and triggered abilities, and unsafe pronoun near misses.
Gameplay scenarios check replay and saved-state reload. 185 selected regression tests
passed, including stack interaction, ward, and shared payments; Ruff and mypy passed.
