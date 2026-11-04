import { drawnBackUrl } from "./drawnBack";
import { linkedCheck } from "./linkedAsset";

/**
 * The Magic card back, for library piles and hidden cards. The host fetches it from Scryfall with the card database
 * (it's never shipped with Fyodor; backend/app/cards/linked.py) and serves it at /api/images/card-back; until it has
 * it, tables draw their own back (cards/drawnBack.ts). Every 2D back is a `.card-back`, which switches to the real one
 * on the `has-card-back` class this sets; the 3D table and the launcher load the same URL and listen for it arriving.
 */
export const CARD_BACK_URL = "/api/images/card-back";

/** Is the card back cached on the host? Sets `has-card-back` on the page when it is; asks again later while it isn't. */
export const checkCardBack = linkedCheck("has-card-back", () => fetch(CARD_BACK_URL).then((r) => r.ok));

/** Called when the host's card back becomes available (or goes). Returns the unsubscribe. */
export const onCardBack = checkCardBack.subscribe;

// the drawn back, for the 2D styles (`.card-back` paints `--card-back-drawn` until the real one is there)
if (typeof document !== "undefined") document.documentElement.style.setProperty("--card-back-drawn", `url("${drawnBackUrl()}")`);
