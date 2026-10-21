# Multiversal Passage

The canonical card and supporting fixtures are in `backend/tests/fixtures/chosen_land_life_cards.json`. Its two abilities require an entry choice followed by an optional life payment, and a characteristic-defining land subtype.

The combined replacement reuses native named entry choices and life-payment handling. The basic land type is chosen first, before life is paid or the land enters. The payment remains optional when another effect already requires tapped entry. Low life and life-change prohibitions are checked normally. Yasharn does not prohibit this payment because it only restricts costs of spells and activated abilities.

CR 604.3a and 613.2 put the land's own subtype-defining ability before ordinary type effects. Its chosen value is not copiable (707.2), so the layer derivation and group-layer solver apply it after copy values, without modifying the copy recipe. The chosen basic subtype provides its intrinsic mana ability (305.6–7); it does not make the land basic. Dryad of the Ilysian Grove adds its types afterward regardless of timestamp. Blood Moon suppresses the entry abilities under the normal prospective-entry rules.

Verification covers all five choices with both payment answers, actual mana production, Spelunking, prohibited and unaffordable life payments, Yasharn, Dryad timestamps, a real Elvish Reclaimer search putting the land in tapped, and replay/save/load. A Vesuva scenario checks that the copy chooses its own type rather than copying the original choice.
