/** View bookmarks: which side of the table is enlarged, and whether stack / log are open. */
import type { MenuItem } from "../components/ContextMenu";
import { askText } from "../components/Prompt";
import { toast } from "../components/Toasts";
import { perspective, playerName, useGame } from "../state/gameStore";
import { usePrefs, type Bookmark } from "../state/prefs";

export function currentView(name: string): Bookmark {
  const s = useGame.getState();
  return { name, focus: s.focus, stackOpen: s.stackOpen, logOpen: s.logOpen };
}

export function applyView(b: Bookmark): void {
  const s = useGame.getState();
  const exists = !b.focus || !!s.view?.players.some((p) => p.id === b.focus && !p.left);
  s.setLayout({ focus: exists ? b.focus : null, stackOpen: b.stackOpen, logOpen: b.logOpen });
}

export function recallBookmark(slot: number): void {
  const b = usePrefs.getState().bookmarks[slot - 1];
  if (!b) {
    toast(`No view saved in slot ${slot} (Ctrl+Shift+${slot} saves one)`);
    return;
  }
  applyView(b);
  toast(b.name);
}

export async function saveBookmark(slot: number): Promise<void> {
  const s = useGame.getState();
  const suggested = s.focus && s.view ? (s.focus === perspective(s.view, s.actingAs) ? "My board" : `${playerName(s.view, s.focus)}'s board`) : "Whole table";
  const name = await askText(`Name for view ${slot} (Ctrl+${slot})`, suggested);
  if (name === null) return;
  const list = [...usePrefs.getState().bookmarks];
  while (list.length < slot) list.push(null);
  list[slot - 1] = currentView(name || suggested);
  usePrefs.getState().set({ bookmarks: list });
  toast(`Saved view ${slot}: ${name || suggested}`);
}

export function viewsMenu(): MenuItem {
  const s = useGame.getState();
  const v = s.view;
  const me = v ? perspective(v, s.actingAs) : null;
  const marks = usePrefs.getState().bookmarks;
  return {
    label: "Views",
    submenu: [
      { label: "Whole table", onClick: () => s.setLayout({ focus: null }) },
      ...(v?.seat_order ?? []).map((pid) => ({
        label: pid === me ? "My board" : `${playerName(v, pid)}'s board`,
        onClick: () => s.setLayout({ focus: pid }),
      })),
      { label: s.stackOpen ? "Collapse stack" : "Open stack", onClick: () => s.setLayout({ stackOpen: !s.stackOpen }) },
      "separator",
      ...marks.flatMap((b, i) => (b ? [{ label: b.name, hint: `Ctrl+${i + 1}`, onClick: () => recallBookmark(i + 1) }] : [])),
      {
        label: "Save current view…",
        hint: "Ctrl+Shift+1…9",
        onClick: async () => {
          const free = marks.findIndex((b) => !b);
          await saveBookmark(free >= 0 ? free + 1 : Math.min(9, marks.length + 1));
        },
      },
    ],
  };
}
