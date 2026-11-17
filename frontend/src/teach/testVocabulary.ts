/**
 * The vocabulary for the tests: rebuilt from the backend's sentence fixture (every piece appears in it) plus the few facts the
 * fixture can't carry (slots, option words), read from the backend module's JSON dump when present. Tests only.
 */
import { existsSync, readFileSync } from "node:fs";
import type { Vocabulary } from "./types";

/** backend/tests/fixtures/teach_vocabulary.json is written by `python -m tests.teach_matrix` next to the sentences. */
export function vocabulary(): Vocabulary {
  const url = new URL("../../../backend/tests/fixtures/teach_vocabulary.json", import.meta.url);
  if (!existsSync(url)) throw new Error("run: cd backend && python -m tests.teach_matrix");
  return JSON.parse(readFileSync(url, "utf8")) as Vocabulary;
}
