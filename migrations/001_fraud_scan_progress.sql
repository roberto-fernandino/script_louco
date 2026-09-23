CREATE TABLE IF NOT EXISTS importacao_transacoes.fraud_scan_progress (
    scan_name text PRIMARY KEY,
    last_card_record_id bigint NOT NULL DEFAULT 0,
    last_page bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO importacao_transacoes.fraud_scan_progress (scan_name)
VALUES ('fraud_search')
ON CONFLICT (scan_name) DO NOTHING;
