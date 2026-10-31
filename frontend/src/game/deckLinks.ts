/**
 * Deck links the table importer can place. The host fetches Archidekt decks itself (a public deck feed); other sites
 * don't offer one, so for those the importer says how to bring the deck as text instead.
 */
export const ARCHIDEKT = /archidekt\.com\/(?:api\/)?decks\/\d+|^\s*\d{1,12}\s*$/i; // a deck URL, or just its number
export const OTHER_SITES = /moxfield|tappedout|mtggoldfish|deckstats|scryfall\.com\/@/i;

/** What to tell someone whose link the host can't fetch (only Archidekt has a public deck feed). */
export function linkProblem(link: string): string | null {
  const url = link.trim();
  if (!url || ARCHIDEKT.test(url)) return null;
  if (!/^(https?:\/\/|www\.)/i.test(url) && !/\.(com|net|org|gg|io)\//i.test(url)) return "That isn't a deck link. Paste a list in the box below instead.";
  const site = /moxfield/i.test(url) ? "Moxfield" : /tappedout/i.test(url) ? "TappedOut" : /mtggoldfish/i.test(url) ? "MTGGoldfish"
    : /deckstats/i.test(url) ? "Deckstats" : /scryfall/i.test(url) ? "Scryfall" : "That site";
  return `${site} links can't be fetched (only Archidekt's can). On the deck's page, export it as text, then paste the list below.`;
}
