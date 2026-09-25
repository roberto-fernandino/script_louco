import { useState } from "react";
import { FraudPage } from "./pages/FraudPage";
import { ListingPage } from "./pages/ListingPage";

type Page = "listing" | "fraud";

const copy: Record<Page, { title: string; description: string }> = {
  listing: {
    title: "Explorador de dados",
    description: "Consulte as tabelas e a relação entre customer e card.",
  },
  fraud: {
    title: "Busca por fraude",
    description: "Consulte cards pelo score mínimo e veja o resultado completo.",
  },
};

export function App() {
  const [page, setPage] = useState<Page>("listing");
  const current = copy[page];

  return (
    <main>
      <header>
        <div>
          <span className="eyebrow">TRANSAÇÕES</span>
          <h1>{current.title}</h1>
          <p>{current.description}</p>
        </div>
        <div className="header-side">
          <nav className="nav">
            <button type="button" className={page === "listing" ? "nav-btn active" : "nav-btn"} onClick={() => setPage("listing")}>Listagem</button>
            <button type="button" className={page === "fraud" ? "nav-btn active" : "nav-btn"} onClick={() => setPage("fraud")}>Fraude</button>
          </nav>
          <span className="status">● API local</span>
        </div>
      </header>
      {page === "listing" ? <ListingPage /> : <FraudPage />}
    </main>
  );
}
