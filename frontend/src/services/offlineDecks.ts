import { artStatus, cacheArt, createDeck, waitForJob } from "./decks";
import type { Deck, ImportRequest } from "../types/decks";

export interface SavedImport {
  deck: Deck;
  artwork: "ready" | "incomplete" | "not-requested";
  notice?: string;
}

/** A download failure must never turn an already-saved deck into a failed import. */
export async function saveDeckForOffline(request: ImportRequest, download: boolean): Promise<SavedImport> {
  const deck = await createDeck(request);
  if (!download) return { deck, artwork: "not-requested" };
  try {
    const job = await cacheArt(deck.id);
    const done = await waitForJob(job.id, () => undefined);
    if (done.state === "failed") throw new Error(done.message || "Artwork download failed");
    if (done.failed > 0) return { deck, artwork: "incomplete", notice: `${done.failed} artwork downloads failed, including possible token images. Open the deck to retry.` };
    const art = await artStatus(deck.id);
    if (art.missing > 0) return { deck, artwork: "incomplete", notice: `${art.missing} card images still need downloading. Open the deck to retry.` };
    return { deck, artwork: "ready" };
  } catch (error) {
    return { deck, artwork: "incomplete", notice: `${error instanceof Error ? error.message : String(error)}. Open the deck to retry artwork.` };
  }
}
