import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/$/, "");
type Row = Record<string, unknown>;

async function request(path: string, options?: RequestInit): Promise<any> {
  try {
    const response = await fetch(`${API}${path}`, options);
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.detail ?? `API respondeu com HTTP ${response.status}`);
    return body;
  } catch (error) {
    if (error instanceof TypeError) throw new Error(`Não foi possível conectar à API em ${API}.`);
    throw error;
  }
}

function App() {
  const [tables, setTables] = useState<string[]>([]);
  const [table, setTable] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [minScore, setMinScore] = useState("80");
  const [fraudSearch, setFraudSearch] = useState("");
  const [fraudResult, setFraudResult] = useState<Row | null>(null);
  const limit = 50;

  async function loadTables() {
    const data = await request("/tables");
    setTables(data.tables);
    if (data.tables.length && !table) setTable(data.tables[0]);
  }

  async function loadRows(nextOffset = offset) {
    if (!table) return;
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ limit: String(limit), offset: String(nextOffset) });
      if (search) params.set("search", search);
      const data = await request(`/tables/${encodeURIComponent(table)}/rows?${params}`);
      setRows(data.items); setColumns(data.columns); setOffset(nextOffset);
    } catch (err) { setError(err instanceof Error ? err.message : "Erro desconhecido."); }
    finally { setLoading(false); }
  }

  async function updateCheck(recordId: unknown, checked: boolean) {
    try {
      await request(`/cards/${encodeURIComponent(String(recordId))}/check`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ check: checked }),
      });
      setRows((current) => current.map((row) => row.record_id === recordId ? { ...row, check: checked } : row));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível atualizar o check.");
    }
  }

  async function searchFraud() {
    setLoading(true); setError(""); setFraudResult(null);
    try {
      const data = await request("/fraud/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ min_score: Number(minScore), search: fraudSearch || null }) });
      setFraudResult(data);
    } catch (err) { setError(err instanceof Error ? err.message : "Não foi possível consultar fraude."); }
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
    <section className="fraud-box"><div><strong>Buscar possível fraude</strong><p>Consulta clientes no querybuscas até encontrar um score acima do limite.</p></div><input type="number" min="0" max="100" value={minScore} onChange={(event) => setMinScore(event.target.value)} aria-label="Score mínimo" /><input value={fraudSearch} onChange={(event) => setFraudSearch(event.target.value)} placeholder="Nome, e-mail ou documento (opcional)" /><button onClick={searchFraud} disabled={loading}>Buscar fraude</button></section>
    {fraudResult && <div className={fraudResult.found ? "fraud-result found" : "fraud-result"}>{fraudResult.found ? <><strong>Possível fraude encontrada</strong><br />Score: {String(fraudResult.score)} — Cliente: {String((fraudResult.customer as Row)?.name ?? "cliente")}<br />BIN: {String((fraudResult.bin as Row)?.BIN ?? "não consultado")} — Bandeira: {String((fraudResult.bin as Row)?.BANDEIRA ?? "não identificada")} — Banco: {String((fraudResult.bin as Row)?.BANCO ?? "não identificado")}</> : `Nenhum score acima do limite encontrado após ${String(fraudResult.checked)} consulta(s).`}</div>}
    {error && <div className="error">{error}</div>}
    <section className="card"><div className="card-head"><strong>{table || "Nenhuma tabela"}</strong><span>{rows.length} registros exibidos</span></div>
      <div className="table-wrap">{rows.length ? <table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{table === "card" && column === "check" ? <input type="checkbox" checked={Boolean(row[column])} onChange={(event) => updateCheck(row.record_id, event.target.checked)} aria-label={`Atualizar check do cartão ${String(row.record_id)}`} /> : String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table> : <div className="empty">{loading ? "Consultando dados..." : "Nenhum registro encontrado."}</div>}</div>
      <div className="pagination"><button disabled={offset === 0 || loading} onClick={() => loadRows(Math.max(0, offset - limit))}>← Anterior</button><span>{offset + 1}–{offset + rows.length}</span><button disabled={rows.length < limit || loading} onClick={() => loadRows(offset + limit)}>Próxima →</button></div>
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
