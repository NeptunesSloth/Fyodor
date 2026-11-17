import { useEffect } from "react";
import { toast } from "./components/Toasts";
import { adoptRestoredDecks } from "./services/backups";
import { syncMyDecks } from "./services/games";
import { ContextMenuHost } from "./components/ContextMenu";
import { PromptHost } from "./components/Prompt";
import { Toasts } from "./components/Toasts";
import { useHashRoute } from "./hooks/useHashRoute";
import { useApplyPrefs } from "./state/applyPrefs";
import { AssetManager } from "./pages/AssetManager";
import { CardBrowser } from "./pages/CardBrowser";
import { DeckEditor } from "./pages/DeckEditor";
import { DeckLibrary } from "./pages/DeckLibrary";
import { GamePage } from "./pages/GamePage";
import { Home } from "./pages/Home";
import { PlayPage } from "./pages/PlayPage";
import { PodStatsPage } from "./pages/PodStatsPage";
import { SettingsPanel } from "./pages/SettingsPanel";
import { TeachPage } from "./pages/TeachPage";

const NAV = [
  { href: "#/play", label: "Play", key: "play" },
  { href: "#/decks", label: "Decks", key: "decks" },
  { href: "#/cards", label: "Cards", key: "cards" },
  { href: "#/teach", label: "Teach", key: "teach" }, // -- Teach Fyodor -- (pages/TeachPage.tsx)
  { href: "#/stats", label: "Pod stats", key: "stats" },
  { href: "#/assets", label: "Assets", key: "assets" },
  { href: "#/settings", label: "Settings", key: "settings" },
];

export function App() {
  const route = useHashRoute();
  useApplyPrefs();
  useEffect(() => {
    void adoptRestoredDecks().then((n) => { if (n) toast(`Restored ${n} deck${n > 1 ? "s" : ""} to My decks`); syncMyDecks(); });
  }, []);
  const [section, sub] = route.path;

  if (section === "game" && sub) {
    return (
      <>
        <GamePage key={sub} id={sub} viewer={route.query.get("viewer")} />
        <Toasts />
        <PromptHost />
        <ContextMenuHost />
      </>
    );
  }

  let page: React.ReactNode;
  switch (section) {
    case "cards":
      page = <CardBrowser />;
      break;
    case "teach":
      page = <TeachPage />;
      break;
    case "decks":
      page = sub ? <DeckEditor key={sub} id={sub} jobId={route.query.get("job")} /> : <DeckLibrary />;
      break;
    case "play":
      page = <PlayPage route={route} />;
      break;
    case "stats":
      page = <PodStatsPage />;
      break;
    case "assets":
      page = <AssetManager />;
      break;
    case "settings":
      page = <div className="page settings-page"><h1>Settings</h1><SettingsPanel /></div>;
      break;
    default:
      page = <Home />;
  }

  const home = !section;
  return (
    <div className={`app ${home ? "app-home" : ""}`}>
      {!home && <nav className="topnav">
        <a className="brand" href="#/">Fyodor</a>
        {NAV.map((n) => (
          <a key={n.key} href={n.href} className={section === n.key ? "active" : ""}>
            {n.label}
          </a>
        ))}
      </nav>}
      <main className="app-main">{page}</main>
      <Toasts />
      <PromptHost />
      <ContextMenuHost />
    </div>
  );
}
