/**
 * Deck links the table importer can place. The host fetches Archidekt decks itself (a public deck feed). The other deck
 * sites were checked (docs/DECK_FORMAT.md, "Deck links"): none has an export the host may fetch, so for those the importer
 * says why and gives that site's steps to bring the deck as text. The host answers the same (backend app/decks/sites.py).
 */
export const ARCHIDEKT = /archidekt\.com\/(?:api\/)?decks\/\d+|^\s*\d{1,12}\s*$/i; // a deck URL, or just its number
export const OTHER_SITES = /moxfield|tappedout|mtggoldfish|deckstats|scryfall\.com\/@/i;

const SITES: { host: RegExp; why: string; steps: string }[] = [
  { host: /\bmoxfield\.com\b/i, why: "Moxfield has no public export link (its deck data is only open to apps with a Moxfield API key).",
    steps: "In Moxfield, open the deck and choose More → Export → Copy Plain Text" },
  { host: /\bmtggoldfish\.com\b/i, why: "MTGGoldfish doesn't let programs download decks (its robots.txt and a browser check block it).",
    steps: "On the deck's page choose Download → Text File (Default), open the file and copy the list" },
  { host: /\btappedout\.net\b/i, why: "TappedOut asks every visitor for a browser check, so the host can't fetch the deck.",
    steps: "In your browser, add ?fmt=txt to the deck's address to see it as text, copy that" },
  { host: /\bdeckstats\.net\b/i, why: "Deckstats asks every visitor for a browser check, so the host can't fetch the deck.",
    steps: "In your browser, add ?export_txt=1 to the deck's address to get it as text, copy that" },
];

/** What to tell someone whose link the host can't fetch (only Archidekt has a public deck feed). */
export function linkProblem(link: string): string | null {
  const url = link.trim();
  if (!url || ARCHIDEKT.test(url)) return null;
  const site = SITES.find((s) => s.host.test(url));
  if (site) return `${site.why} ${site.steps}, then paste it in the box below.`;
  if (!/^(https?:\/\/|www\.)/i.test(url) && !/\.(com|net|org|gg|io)\//i.test(url)) return "That isn't a deck link. Paste a list in the box below instead.";
  const name = /scryfall/i.test(url) ? "Scryfall" : "That site";
  return `${name} links can't be fetched (only Archidekt's can). On the deck's page, export it as text, then paste the list below.`;
}
