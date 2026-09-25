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

## API NestJS/TypeORM

O backend NestJS fica em `api/`, enquanto o frontend existente continua em `apps/web/`.

```bash
cd api
npm install
npm run migration:run
npm run start:dev
```

A rota `POST /cards/check` recebe `{ "number": "..." }` e marca o campo `check` como `true`. A API tem os módulos `CardsModule` e `CustomerModule`, entidades em `entities/`, interfaces em `interfaces/` e repositórios TypeORM em `repositorys/`.

## Rotas

- `GET /health`
- `GET /customers` — filtros `record_id`, `email`, `document_number`, `search`, `limit`, `offset`
- `GET /customers/{record_id}`
- `GET /cards` — filtros `customer_id`, `record_id`, `brand`, `limit`, `offset`
- `GET /tables` — lista todas as tabelas do schema configurado
- `GET /tables/{table}/columns` — lista as colunas de qualquer tabela
- `GET /tables/{table}/rows` — consulta qualquer tabela filtrando por `filter_column` e `filter_value`, além de `order_by`, `descending`, `limit` e `offset`
- `PATCH /cards/{record_id}/check` — altera o campo `check` do cartão
- `POST /fraud/search` — consulta sequencialmente cartões ainda não verificados (`check != true`) e para no primeiro score acima do limite; depois consulta também o BIN do cartão

As rotas genéricas usam `importacao_transacoes` por padrão. Para outro schema permitido pelo usuário do banco, use o parâmetro `schema`.

## Consulta de fraude

O resultado também inclui `related_data`, com todas as colunas do cliente, do card e das demais tabelas que possuam `customer_id`. O número do cartão é mascarado e o CVV não é retornado.

A busca mantém o cursor em `importacao_transacoes.fraud_scan_progress`, continua pelo próximo `card.record_id` e volta ao início somente quando chega ao fim dos cards elegíveis. As migrações de score também são executadas automaticamente quando a API FastAPI inicia; o SQL equivalente está em `migrations/002_customer_scores.sql`.

Configure no `.env` `SNOOP_API_KEY` e, se necessário, `SNOOP_RATE_LIMIT_PER_SECOND` (padrão `15`). O backend chama `POST /api/rendaescore` em lotes de até 400 CPFs, persiste `score_csb8`, `score_csba` e suas faixas em `customer`, e só consulta novamente clientes sem score armazenado. O BIN usa `GET /api/query/bin`, sempre enviando a chave no header `x-api-key`. O score usa a escala de `0` a `1000`; o botão **Buscar fraude** filtra por campos do cliente e do card relacionado e permite marcá-lo como verificado. A chave deve permanecer somente no backend e nunca ser commitada.

Para testar a integração diretamente:

```bash
source .venv/bin/activate
export SNOOP_API_KEY='sua_chave'
curl -X POST 'https://ultra.snoopintelligence.cloud/api/rendaescore' \
  -H "x-api-key: $SNOOP_API_KEY" -H 'Content-Type: application/json' \
  -d '{"cpfs":["09386765632"]}'
curl 'https://ultra.snoopintelligence.cloud/api/query/bin?bin=550209' \
  -H "x-api-key: $SNOOP_API_KEY"
```

Os campos de cartão são dados sensíveis. Restrinja o acesso à API e, em produção, considere mascarar `number` e remover `cvv` das respostas.
