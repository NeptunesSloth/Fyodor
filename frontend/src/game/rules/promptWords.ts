/**
 * -- playtest (nov 16) -- a prompt's words as a person would say them: the engine writes counts generically ("Curiosity: Draw 1 card(s)?"),
 * and the table reads "Curiosity: Draw a card?". Display only: the decision and its answers are the server's.
 */
export function prettyPrompt(text: string): string {
  return text.replace(/(^|[\s(])(\d+) ([A-Za-z][A-Za-z'-]*)\(s\)/g, (_, pre: string, n: string, word: string) => {
    if (Number(n) !== 1) return `${pre}${n} ${word}s`;
    return `${pre}${/^[aeiou]/i.test(word) ? "an" : "a"} ${word}`;
  });
}
