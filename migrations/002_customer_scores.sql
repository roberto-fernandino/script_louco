ALTER TABLE importacao_transacoes.customer
    ADD COLUMN IF NOT EXISTS score_csb8 numeric,
    ADD COLUMN IF NOT EXISTS score_csba numeric,
    ADD COLUMN IF NOT EXISTS score_csb8_faixa text,
    ADD COLUMN IF NOT EXISTS score_csba_faixa text,
    ADD COLUMN IF NOT EXISTS score_updated_at timestamptz;

CREATE INDEX IF NOT EXISTS customer_score_missing_idx
    ON importacao_transacoes.customer (record_id)
    WHERE score_csb8 IS NULL AND score_csba IS NULL;
