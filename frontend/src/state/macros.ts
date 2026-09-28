/** The macro library, cached for the card menu (refreshed when the table opens or after a save). */
import { create } from "zustand";
import { api } from "../services/api";

export interface StoredMacro {
  id: string;
  scope: "card" | "library";
  oracle_id: string | null;
  name: string;
  definition: { name: string; steps: Record<string, unknown>[] };
}

export const useMacros = create<{ list: StoredMacro[]; refresh: () => void }>((set) => ({
  list: [],
  refresh: () => void api.get<StoredMacro[]>("/macros").then((list) => set({ list }), () => undefined),
}));

export const macrosFor = (oracleId: string | null | undefined) =>
  useMacros.getState().list.filter((m) => m.scope === "library" || (oracleId && m.oracle_id === oracleId));
