import type { Row } from "../api";

function formatValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "sim" : "não";
  return String(value);
}

function FieldList({ data }: { data: Row }) {
  const entries = Object.entries(data).filter(([, value]) => value == null || typeof value !== "object");
  return (
    <dl>
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{formatValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function RelationPanel({ customer, cards }: { customer: Row; cards: Row[] }) {
  return (
    <article className="relation">
      <div className="relation-grid">
        <section>
          <h2>Customer</h2>
          <FieldList data={customer} />
        </section>
        <section>
          <h2>Card</h2>
          {cards.length ? cards.map((card, index) => (
            <div className="relation-card" key={String(card.record_id ?? index)}>
              {cards.length > 1 && <strong>Card {index + 1}</strong>}
              <FieldList data={card} />
            </div>
          )) : <p className="muted">Nenhum card vinculado.</p>}
        </section>
      </div>
    </article>
  );
}
