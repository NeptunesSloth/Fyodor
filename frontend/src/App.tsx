import { ContextMenuHost } from "./components/ContextMenu";
import { PromptHost } from "./components/Prompt";
import { Toasts } from "./components/Toasts";
import { useHashRoute } from "./hooks/useHashRoute";
import { CardBrowser } from "./pages/CardBrowser";
import { DeckEditor } from "./pages/DeckEditor";
import { DeckLibrary } from "./pages/DeckLibrary";
import { GamePage } from "./pages/GamePage";
import { Home } from "./pages/Home";
import { PlayPage } from "./pages/PlayPage";

const NAV = [
  { href: "#/play", label: "Play", key: "play" },
  { href: "#/decks", label: "Decks", key: "decks" },
  { href: "#/cards", label: "Cards", key: "cards" },
];

export function App() {
  const route = useHashRoute();
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
    case "decks":
      page = sub ? <DeckEditor key={sub} id={sub} jobId={route.query.get("job")} /> : <DeckLibrary />;
      break;
    case "play":
      page = <PlayPage route={route} />;
      break;
    default:
      page = <Home />;
  }

  return (
    <div className="app">
      <nav className="topnav">
        <a className="brand" href="#/">Fyodor</a>
        {NAV.map((n) => (
          <a key={n.key} href={n.href} className={section === n.key ? "active" : ""}>
            {n.label}
          </a>
        ))}
      </nav>
      <main className="app-main">{page}</main>
      <Toasts />
      <PromptHost />
      <ContextMenuHost />
    </div>
  );
}
