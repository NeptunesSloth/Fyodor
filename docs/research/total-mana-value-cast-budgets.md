# Total mana-value budgets for immediate casts

Invoke Calamity and Rod of Absorption use the same native immediate-casting loop with a shared mana-value budget. Full canonical Oracle characteristics are in `tests/fixtures/total_mv_casts_cards.json`.

The new `mv_total` instruction evaluates the budget once when casting starts and saves the remaining value in the resolution context. It filters each offered spell face against the remainder and charges only a completed cast using that actual spell's stack mana value. Choices and cancelled announcements consume nothing. An announced Rod X is independent of a later spell's own X (zero under a free alternative cost). Split and Adventure halves use the chosen spell's mana value, rather than the card's combined or front-face value. Ending the instruction clears its budget; subsequent casting instructions start afresh.

Invoke uses the caster's current hand and graveyard, a two-spell cap, the existing “exile instead of your graveyard” rider, and native self-exile. Rod uses exact originally linked exiled objects from all owners, even after it is sacrificed. Existing casting legality, targets, additional costs, optional decline, cancellation, and save/replay continuations remain native. A later cast can target the earlier spell before either resolves (CR 608.2g).

## Rod's resolved-exile linkage and replacement choices

The existing resolved-exile primitive now participates in linked exile and preserves source/controller/borrowed-link metadata. It records a card only after the actual chosen replacement exiles that original object. A countered spell never resolves and is not captured (CR 608.2b, 701.6).

Multiple cast-triggered exile replacements previously kept only the first record. They now retain alternatives and use the existing zone replacement candidates and pending-616 protocol. The spell's controller chooses between distinct Rod links, Feather's later return, or Rest in Peace. Only the chosen replacement records its link or runs its rider, including when the source has left. Candidate identifiers remain within the protocol's 64-character limit. Source-card presentation distinguishes otherwise identical Rods.

Primeval Spawn and Uldaros Theorix share the budget grammar but retain independent missing mechanics; this work makes no FULL claim for those cards. The broad old total-value refusal is exempted only for the supported casting instruction, while ordinary definition checks continue to require every remaining instruction.

Validation: 30 focused canonical cases include both cards' coverage; exact and remaining budgets; count limits; hand/graveyard origins; newly legal spell targets; Adventure/split/X/no-mana-cost spells; mandatory sacrifice costs; cancellation without charge; owner/controller preservation; stale originals; cast prohibitions; countered-spell exclusion; multiple Rods and Feather/Rest in Peace choices; a departed token-Feather source that has ceased to exist; and four actual cold-process resumes across budget or replacement decisions. Every gameplay scenario verifies history replay and saved-state equality.
