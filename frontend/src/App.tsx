import { Toasts } from "./components/Toasts";
import { useHashRoute } from "./hooks/useHashRoute";
import { CardBrowser } from "./pages/CardBrowser";
import { DeckEditor } from "./pages/DeckEditor";
import { DeckLibrary } from "./pages/DeckLibrary";
import { Home } from "./pages/Home";

const NAV = [
  { href: "#/play", label: "Play", key: "play" },
  { href: "#/decks", label: "Decks", key: "decks" },
  { href: "#/cards", label: "Cards", key: "cards" },
];

export function App() {
  const route = useHashRoute();
  const [section] = route.path;

  let page: React.ReactNode;
  switch (section) {
    case "cards":
      page = <CardBrowser />;
      break;
    case "decks":
      page = route.path[1] ? <DeckEditor key={route.path[1]} id={route.path[1]} /> : <DeckLibrary />;
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
    </div>
  );
}
