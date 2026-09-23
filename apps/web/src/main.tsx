import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
type Row = Record<string, unknown>;

function App() {
  const [tables, setTables] = useState<string[]>([]);
  const [table, setTable] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 50;

  async function loadTables() {
    const response = await fetch(`${API}/tables`);
    if (!response.ok) throw new Error("Não foi possível carregar as tabelas.");
    const data = await response.json();
    setTables(data.tables);
    if (data.tables.length && !table) setTable(data.tables[0]);
  }

  async function loadRows(nextOffset = offset) {
    if (!table) return;
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ limit: String(limit), offset: String(nextOffset) });
      if (search) params.set("search", search);
      const response = await fetch(`${API}/tables/${encodeURIComponent(table)}/rows?${params}`);
      if (!response.ok) throw new Error("Não foi possível consultar a tabela.");
      const data = await response.json();
      setRows(data.items); setColumns(data.columns); setOffset(nextOffset);
    } catch (err) { setError(err instanceof Error ? err.message : "Erro desconhecido."); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadTables().catch((err) => setError(err.message)); }, []);
  useEffect(() => { if (table) loadRows(0); }, [table]);

  return <main>
    <header><div><span className="eyebrow">TRANSAÇÕES</span><h1>Explorador de dados</h1><p>Consulte as tabelas disponíveis no PostgreSQL.</p></div><span className="status">● API local</span></header>
    <section className="toolbar">
      <label>Tabela<select value={table} onChange={(event) => setTable(event.target.value)}>{tables.map((name) => <option key={name}>{name}</option>)}</select></label>
      <label className="search">Buscar<input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => event.key === "Enter" && loadRows(0)} placeholder="Digite e pressione Enter" /></label>
      <button onClick={() => loadRows(0)} disabled={loading}>{loading ? "Carregando..." : "Consultar"}</button>
    </section>
    {error && <div className="error">{error}</div>}
    <section className="card"><div className="card-head"><strong>{table || "Nenhuma tabela"}</strong><span>{rows.length} registros exibidos</span></div>
      <div className="table-wrap">{rows.length ? <table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table> : <div className="empty">{loading ? "Consultando dados..." : "Nenhum registro encontrado."}</div>}</div>
      <div className="pagination"><button disabled={offset === 0 || loading} onClick={() => loadRows(Math.max(0, offset - limit))}>← Anterior</button><span>{offset + 1}–{offset + rows.length}</span><button disabled={rows.length < limit || loading} onClick={() => loadRows(offset + limit)}>Próxima →</button></div>
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
