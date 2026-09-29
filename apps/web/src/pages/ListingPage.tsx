import { useEffect, useState } from "react";
import { request, type Row } from "../api";
import { RelationPanel } from "../components/RelationPanel";
import { SelectField } from "../components/SelectField";
import { formatValue } from "../formatters";

const PAGE_SIZE = 50;

type Relation = { key: string; customer: Row; cards: Row[] };

function asRows(value: unknown): Row[] {
  return Array.isArray(value) ? value as Row[] : [];
}

async function loadRelations(table: string, items: Row[]): Promise<Relation[]> {
  if (table === "card") {
    const details = await Promise.all(items.map((row) => request(`/cards/${encodeURIComponent(String(row.record_id))}/details`)));
    return details.map((detail, index) => {
      const related = (detail.related_data ?? {}) as Row;
      const customers = asRows(related.customer);
      const cards = asRows(related.card);
      return {
        key: String(items[index].record_id),
        customer: customers[0] ?? (detail.customer as Row) ?? {},
        cards: cards.length ? cards : detail.card ? [detail.card as Row] : [],
      };
    });
  }

  const results = await Promise.all(items.map(async (row) => {
    const id = String(row.record_id);
    const [customer, cards] = await Promise.all([
      request(`/customers/${encodeURIComponent(id)}`),
      request(`/cards?customer_id=${encodeURIComponent(id)}&limit=200`),
    ]);
    return { key: id, customer: customer as Row, cards: asRows(cards.items) };
  }));
  return results;
}

export function ListingPage() {
  const [tables, setTables] = useState<string[]>([]);
  const [table, setTable] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [filterColumn, setFilterColumn] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const [relations, setRelations] = useState<Relation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [binInput, setBinInput] = useState("");
  const [binData, setBinData] = useState<Row | null>(null);
  const [binLoading, setBinLoading] = useState(false);

  const relationMode = (table === "customer" || table === "card") && relations.length > 0;

  async function loadTables() {
    const data = await request("/tables");
    setTables(data.tables);
    if (data.tables.length && !table) setTable(data.tables[0]);
  }

  async function loadRows(nextOffset = offset, column = filterColumn, value = filterValue, selectedTable = table) {
    if (!selectedTable) return;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(nextOffset) });
      if (column && value) {
        params.set("filter_column", column);
        params.set("filter_value", value);
      }
      const data = await request(`/tables/${encodeURIComponent(selectedTable)}/rows?${params}`);
      const items = data.items as Row[];
      const filtered = (selectedTable === "customer" || selectedTable === "card") && Boolean(column && value.trim() && items.length);
      const nextRelations = filtered ? await loadRelations(selectedTable, items) : [];
      setRows(items);
      setColumns(data.columns);
      setOffset(nextOffset);
      setRelations(nextRelations);
    } catch (err) {
      setRelations([]);
      setError(err instanceof Error ? err.message : "Erro desconhecido.");
    } finally {
      setLoading(false);
    }
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

  async function queryBin() {
    const bin = binInput.replace(/\D/g, "").slice(0, 6);
    if (bin.length !== 6) {
      setError("Informe os 6 primeiros dígitos do cartão.");
      return;
    }
    setBinLoading(true);
    setError("");
    try {
      setBinData(await request(`/bin/${bin}`));
    } catch (err) {
      setBinData(null);
      setError(err instanceof Error ? err.message : "Não foi possível consultar o BIN.");
    } finally {
      setBinLoading(false);
    }
  }

  useEffect(() => { loadTables().catch((err) => setError(err.message)); }, []);
  useEffect(() => { if (table) void loadRows(0, filterColumn, filterValue, table); }, [table]);

  function changeTable(next: string) {
    setFilterColumn("");
    setFilterValue("");
    setRelations([]);
    setRows([]);
    setTable(next);
  }

  return (
    <>
      <section className="toolbar">
        <SelectField
          label="Tabela"
          value={table}
          onChange={changeTable}
          options={tables.map((name) => ({ value: name, label: name }))}
          placeholder="Selecione uma tabela"
        />
        <SelectField
          label="Coluna"
          value={filterColumn}
          onChange={setFilterColumn}
          options={[{ value: "", label: "Selecione uma coluna" }, ...columns.map((column) => ({ value: column, label: column }))]}
        />
        <label className="search">
          Valor
          <input
            value={filterValue}
            onChange={(event) => setFilterValue(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") void loadRows(0); }}
            placeholder="Filtrar pela coluna selecionada"
          />
        </label>
        <button onClick={() => void loadRows(0)} disabled={loading}>{loading ? "Carregando..." : "Consultar"}</button>
      </section>
      <section className="toolbar bin-toolbar">
        <label className="search">
          Consulta por BIN
          <input
            value={binInput}
            onChange={(event) => setBinInput(event.target.value.replace(/\D/g, "").slice(0, 6))}
            onKeyDown={(event) => { if (event.key === "Enter") void queryBin(); }}
            inputMode="numeric"
            maxLength={6}
            placeholder="Ex.: 550209"
          />
        </label>
        <button onClick={() => void queryBin()} disabled={binLoading}>
          {binLoading ? "Consultando..." : "Consultar BIN"}
        </button>
      </section>
      {binData && (
        <div className="fraud-stage bin-result">
          {asRows(binData.matches).map((match, index) => {
            const related = (match.related_data ?? {}) as Row;
            const customers = asRows(related.customer);
            const cards = asRows(related.card);
            const panelCustomer = customers[0] ?? (match.customer as Row) ?? {};
            const panelCards = cards.length ? cards : match.card ? [match.card as Row] : [];
            return (
              <RelationPanel
                key={String((match.card as Row | undefined)?.record_id ?? index)}
                customer={panelCustomer}
                cards={panelCards}
              />
            );
          })}
          <pre className="fraud-data">{JSON.stringify(binData, null, 2)}</pre>
        </div>
      )}
      {error && <div className="error">{error}</div>}
      {relationMode ? (
        <section>
          <div className="card-head standalone">
            <strong>{table}</strong>
            <span>{relations.length} relações exibidas</span>
          </div>
          {relations.map((relation) => <RelationPanel key={relation.key} customer={relation.customer} cards={relation.cards} />)}
          <div className="pagination standalone">
            <button disabled={offset === 0 || loading} onClick={() => void loadRows(Math.max(0, offset - PAGE_SIZE))}>← Anterior</button>
            <span>{offset + 1}–{offset + rows.length}</span>
            <button disabled={rows.length < PAGE_SIZE || loading} onClick={() => void loadRows(offset + PAGE_SIZE)}>Próxima →</button>
          </div>
        </section>
      ) : (
        <section className="card">
          <div className="card-head">
            <strong>{table || "Nenhuma tabela"}</strong>
            <span>{rows.length} registros exibidos</span>
          </div>
          <div className="table-wrap">
            {rows.length ? (
              <table>
                <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={index}>
                      {columns.map((column) => (
                        <td key={column}>
                          {table === "card" && column === "check" ? (
                            <input
                              type="checkbox"
                              checked={Boolean(row[column])}
                              onChange={(event) => void updateCheck(row.record_id, event.target.checked)}
                              aria-label={`Atualizar check do cartão ${String(row.record_id)}`}
                            />
                          ) : formatValue(column, row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <div className="empty">{loading ? "Consultando dados..." : "Nenhum registro encontrado."}</div>}
          </div>
          <div className="pagination">
            <button disabled={offset === 0 || loading} onClick={() => void loadRows(Math.max(0, offset - PAGE_SIZE))}>← Anterior</button>
            <span>{offset + 1}–{offset + rows.length}</span>
            <button disabled={rows.length < PAGE_SIZE || loading} onClick={() => void loadRows(offset + PAGE_SIZE)}>Próxima →</button>
          </div>
        </section>
      )}
    </>
  );
}
