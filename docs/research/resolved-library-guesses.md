# Resolved name, number, and color guesses

Tunnel Vision, Mindblaze, and Scrying Glass use canonical Oracle text. Public
card-name and number choices use existing native input validation; the two
positive-number instructions use a typed minimum of one, including values above
40. Existing bounded number choices retain their earlier behavior.

Tunnel Vision reveals the target library through the first current matching
name, moves the other revealed cards to their owner's graveyard (not mill), and
places the exact named object on top. Failure shuffles without moving cards to
the graveyard. Mindblaze reveals the entire library and compares the actual
matching-name count with the chosen positive number, deals eight only on exact
equality, and always shuffles. Scrying Glass counts each card of the chosen
color once and queues a native draw only on equality. Exact object references
end the hand reveal without exposing newly drawn cards from replacement effects.
All damage, draws, library placements, shuffles and replacement continuations
use existing native primitives; no new resume callback or schema.

Validation: 16 canonical tests, including three fresh-process save/view/resume
checks, wrong guesses, guesses above40, atomic zero/land-name refusals, real Rest
in Peace graveyard replacement and Notion Thief draw replacement. 203 related
name, choice, group-choice and library-look tests pass. Replay and JSON checks
are included throughout. Full shared inventory/type/core audit is centralized.
