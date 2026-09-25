import { useState } from "react";
import { request, type Row } from "../api";
import { RelationPanel } from "../components/RelationPanel";

function asRows(value: unknown): Row[] {
  return Array.isArray(value) ? value as Row[] : [];
}

export function FraudPage() {
  const [minScore, setMinScore] = useState("800");
  const [fraudSearch, setFraudSearch] = useState("");
  const [fraudDocument, setFraudDocument] = useState("");
  const [fraudBrand, setFraudBrand] = useState("");
  const [fraudCustomerId, setFraudCustomerId] = useState("");
  const [fraudCardId, setFraudCardId] = useState("");
  const [fraudResult, setFraudResult] = useState<Row | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function searchFraud() {
    setLoading(true);
    setError("");
    setFraudResult(null);
    try {
      const data = await request("/fraud/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          min_score: Number(minScore),
          customer_record_id: fraudCustomerId ? Number(fraudCustomerId) : null,
          card_record_id: fraudCardId ? Number(fraudCardId) : null,
          customer_name: fraudSearch || null,
          customer_document: fraudDocument || null,
          card_brand: fraudBrand || null,
        }),
      });
      setFraudResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível consultar fraude.");
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
      setFraudResult((current) => {
        const customer = current?.customer as Row | undefined;
        return customer?.card_record_id === recordId ? { ...current, customer: { ...customer, check: checked } } : current;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível atualizar o check.");
    }
  }

  const found = Boolean(fraudResult?.found);
  const customer = fraudResult?.customer as Row | undefined;
  const bin = fraudResult?.bin as Row | undefined;
  const related = fraudResult?.related_data as Row | undefined;
  const relatedCustomers = asRows(related?.customer);
  const relatedCards = asRows(related?.card);
  const panelCustomer = relatedCustomers[0] ?? customer ?? {};
  const panelCards = relatedCards.length ? relatedCards : fraudResult?.card ? [fraudResult.card as Row] : [];

  return (
    <>
      <section className="fraud-form">
        <div className="fraud-intro">
          <strong>Buscar possível fraude</strong>
          <p>Consulta somente cards não verificados ligados ao cliente filtrado.</p>
        </div>
        <label>
          Score mínimo
          <input type="number" min="0" max="1000" value={minScore} onChange={(event) => setMinScore(event.target.value)} aria-label="Score mínimo" />
        </label>
        <label>
          ID do cliente
          <input type="number" min="1" value={fraudCustomerId} onChange={(event) => setFraudCustomerId(event.target.value)} placeholder="ID do cliente" />
        </label>
        <label>
          ID do card
          <input type="number" min="1" value={fraudCardId} onChange={(event) => setFraudCardId(event.target.value)} placeholder="ID do card" />
        </label>
        <label>
          Nome do cliente
          <input value={fraudSearch} onChange={(event) => setFraudSearch(event.target.value)} placeholder="Nome do cliente" />
        </label>
        <label>
          Documento do cliente
          <input value={fraudDocument} onChange={(event) => setFraudDocument(event.target.value)} placeholder="Documento do cliente" />
        </label>
        <label>
          Brand do card
          <input value={fraudBrand} onChange={(event) => setFraudBrand(event.target.value)} placeholder="Brand do card" />
        </label>
        <div className="fraud-actions">
          <button onClick={() => void searchFraud()} disabled={loading}>{loading ? "Buscando..." : "Buscar fraude"}</button>
        </div>
      </section>
      {error && <div className="error">{error}</div>}
      {fraudResult && (
        <div className="fraud-stage">
          <div className={found ? "fraud-result found" : "fraud-result"}>
            {found ? (
              <>
                <strong>Possível fraude encontrada</strong>
                <p>Score máximo: {String(fraudResult.score)} — Cliente: {String(customer?.name ?? "cliente")}</p>
                <p>BIN: {String(bin?.BIN ?? "não consultado")} — Bandeira: {String(bin?.BANDEIRA ?? "não identificada")} — Banco: {String(bin?.BANCO ?? "não identificado")}</p>
                <button disabled={Boolean(customer?.card_check)} onClick={() => void updateCheck(customer?.card_record_id, true)}>
                  {customer?.card_check ? "Já marcado" : "Marcar como verificado"}
                </button>
              </>
            ) : `Nenhum score acima do limite encontrado após ${String(fraudResult.checked)} consulta(s).`}
          </div>
          {found && (
            <>
              <RelationPanel customer={panelCustomer} cards={panelCards} />
              <pre className="fraud-data">{JSON.stringify({
                card: fraudResult.card,
                related_data: fraudResult.related_data,
                scores: fraudResult.scores,
                score_querybuscas: fraudResult.querybuscas_score,
                bin_querybuscas: fraudResult.bin,
              }, null, 2)}</pre>
            </>
          )}
        </div>
      )}
    </>
  );
}
