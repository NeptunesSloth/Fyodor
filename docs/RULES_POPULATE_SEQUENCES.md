# Repeated populate and references to created tokens

Rules source: Comprehensive Rules effective 2026-09-25, stored locally.

## Rules question and current authority

Does each populate repetition make a fresh choice, and which tokens receive a subsequent
haste grant and delayed sacrifice?

- CR 701.36a: populate chooses a creature token you control and creates a copy of that token.
- CR 701.36b: no creature tokens means no token is created.
- CR 608.2c: repeated instructions execute in order, so a token just created can be chosen
  by the next populate.
- CR 707.2–3: the copy uses copiable values, including those of an existing copy.
- CR 614.16 and 616.1: token creation replacements apply to each creation event.
- CR 603.7 and 400.7: delayed actions identify the created objects and survive their source's
  departure without acting on unrelated or new objects.

## Oracle examples and implementation

Full Flowering's “Populate X times” emits an ordinary repeat instruction followed by populate.
Each repetition rechecks the battlefield and independently chooses its token. Its {X}{X}{G}
cost is handled by existing casting rules.

Determined Iteration's “The token created this way” is normalized to the existing token
reference grammar. Populate registers as a token-producing introducer and carries its binding
into token_copy, including when a replacement choice pauses resolution. With no eligible
token it records an empty binding. Haste and delayed sacrifice use that binding, including
all tokens created when token doubling applies.

No new GameState fields or continuation type. Unrelated attachment and noun-mismatch
refusals remain unsupported.

## Edge cases, tests, and coverage

11 focused gameplay/coverage scenarios passed, with replay and save/load checks. They cover
zero repetitions, independently chosen copies, choosing a newly created token, noncreature
token exclusion, no eligible tokens, replacement application per repetition, two token
doublers, paused choices, source departure, and sacrifice of only the new tokens.

282 selected copy, token, replacement, X, and duration regression tests passed (overlaps).
Ruff, mypy (348 app/tools files), and whitespace checks passed. Catalog comparison found only
these two promotions and no lost FULL support: 27,644 FULL / 4,424 PARTIAL.
