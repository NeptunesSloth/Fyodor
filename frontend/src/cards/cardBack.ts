/**
 * The Magic card back, for library piles and hidden cards. The host fetches it from Scryfall with the card art
 * (it's never shipped with Fyodor) and serves it at /api/images/card-back; until it has it, tables draw their own
 * back. 2D backs switch on the class this sets; the 3D table loads the same URL with its own fallback.
 */
export const CARD_BACK_URL = "/api/images/card-back";

let checked: Promise<boolean> | null = null;

/** Is the card back cached on the host? Sets `has-card-back` on the page when it is. */
export function checkCardBack(force = false): Promise<boolean> {
  if (!checked || force) {
    checked = fetch(CARD_BACK_URL, { cache: "force-cache" })
      .then((r) => r.ok)
      .catch(() => false)
      .then((ok) => {
        document.documentElement.classList.toggle("has-card-back", ok);
        return ok;
      });
  }
  return checked;
}
