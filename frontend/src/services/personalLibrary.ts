import { myDecks, type LobbyDeckBody } from "./games";

/** A portable list-only backup: no seat credentials, host paths, or network-dependent references. */
export function exportPersonalLibrary(): string {
  const decks = myDecks().map(deck => {
    const body = deck.body.text ? { text: deck.body.text } : deck.body.json ? { json: deck.body.json } : null;
    if (!body) throw new Error(`Open ${deck.name} once while online before exporting its saved list.`);
    return { name: deck.name, body };
  });
  return JSON.stringify({ format: "fyodor-personal-decks", version: 1, decks }, null, 2);
}

export function personalDeckFile(content: string, filename: string): { label: string; body: LobbyDeckBody }[] {
  const name = filename.replace(/\.[^.]+$/, "");
  const json = filename.toLowerCase().endsWith(".json") || content.trimStart().startsWith("{");
  if (json) {
    const parsed: unknown = JSON.parse(content);
    if (typeof parsed === "object" && parsed !== null && "format" in parsed && parsed.format === "fyodor-personal-decks") {
      if (!("version" in parsed) || parsed.version !== 1 || !("decks" in parsed) || !Array.isArray(parsed.decks)) throw new Error("Unsupported personal-library backup");
      return parsed.decks.map((deck: unknown) => {
        if (typeof deck !== "object" || deck === null || !("name" in deck) || typeof deck.name !== "string" || !("body" in deck)
          || typeof deck.body !== "object" || deck.body === null) throw new Error("Invalid deck in personal-library backup");
        const body = deck.body;
        const text = "text" in body && typeof body.text === "string" ? body.text : undefined;
        const json = "json" in body && typeof body.json === "string" ? body.json : undefined;
        if (!text && !json) throw new Error("A library backup must contain saved lists, not URLs");
        return { label: deck.name, body: { name: deck.name, text, json } };
      });
    }
  }
  return [{ label: filename, body: json ? { json: content, name } : { text: content, name } }];
}
