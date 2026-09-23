# Transactions Query Monorepo

Monorepo com uma API FastAPI e uma UI React para consultar as tabelas PostgreSQL do schema `importacao_transacoes`.

## Executar tudo localmente

```bash
# API
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edite DATABASE_URL no .env

# UI, em outro terminal
npm install
npm run dev

# API, se necessário
uvicorn app.main:app --reload
```

UI: `http://localhost:5173`.
Documentação da API: `http://localhost:8000/docs`.

## Rotas

- `GET /health`
- `GET /customers` — filtros `record_id`, `email`, `document_number`, `search`, `limit`, `offset`
- `GET /customers/{record_id}`
- `GET /cards` — filtros `customer_id`, `record_id`, `brand`, `limit`, `offset`
- `GET /tables` — lista todas as tabelas do schema configurado
- `GET /tables/{table}/columns` — lista as colunas de qualquer tabela
- `GET /tables/{table}/rows` — consulta qualquer tabela com `search`, `order_by`, `descending`, `limit` e `offset`

As rotas genéricas usam `importacao_transacoes` por padrão. Para outro schema permitido pelo usuário do banco, use o parâmetro `schema`.

Os campos de cartão são dados sensíveis. Restrinja o acesso à API e, em produção, considere mascarar `number` e remover `cvv` das respostas.
